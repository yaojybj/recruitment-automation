"""
模块2：自动化约面 + 面试官-候选人时间匹配
监听 Moka 待约面状态 → 发送时间选项 → 解析回复 → 匹配 → 创建面试
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from models.interview import InterviewSchedule, InterviewStatus, TimeSlot, InterviewType
from models.candidate import Candidate, CandidateMatchStatus
from core.time_matcher import TimeMatcher
from adapters.moka_api import MokaAPI, MokaAPIError
from adapters.moka_csv import MokaCSVParser
from adapters.boss_plugin import BossPluginAdapter, BossPluginError
from utils.config_loader import get_settings, get_message_template
from utils.logger import get_logger
from utils.notifier import notify


DATA_DIR = Path("./data")
SCHEDULE_FILE = DATA_DIR / "interview_schedules.json"


class InterviewScheduler:
    """面试约面调度器"""

    def __init__(self, moka_api: MokaAPI | None = None,
                 moka_csv: MokaCSVParser | None = None,
                 boss: BossPluginAdapter | None = None):
        self.moka_api = moka_api
        self.moka_csv = moka_csv or MokaCSVParser()
        self.boss = boss or BossPluginAdapter()
        self.time_matcher = TimeMatcher()
        self.logger = get_logger()
        self.settings = get_settings()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def poll_pending_interviews(self) -> list[InterviewSchedule]:
        """
        轮询 Moka 待约面简历，创建或更新约面记录
        核心入口方法，由调度器定期调用
        """
        self.logger.info("开始轮询 Moka 待约面简历...")
        pending_candidates = self._fetch_pending_candidates()
        existing = self._load_schedules()
        existing_moka_ids = {s.moka_resume_id for s in existing}

        new_schedules = []
        for candidate_data in pending_candidates:
            moka_id = candidate_data.get("candidate_id", "")
            if moka_id in existing_moka_ids:
                continue

            schedule = self._create_schedule_from_candidate(candidate_data)
            if schedule:
                new_schedules.append(schedule)
                existing.append(schedule)

        if new_schedules:
            self._save_schedules(existing)
            self.logger.info(f"新增 {len(new_schedules)} 条待约面记录")

        return new_schedules

    def process_new_schedule(self, schedule: InterviewSchedule) -> InterviewSchedule:
        """
        处理单条新约面记录：匹配Boss候选人 → 发送时间选项
        """
        # 匹配 Boss 聊天
        if not schedule.candidate_boss_id:
            candidate = self.boss.match_candidate_in_chats(
                schedule.candidate_name,
                schedule.applied_position
            )
            if candidate.match_status == CandidateMatchStatus.AMBIGUOUS:
                schedule.status = InterviewStatus.MANUAL_REQUIRED
                schedule.error_message = "Boss候选人匹配歧义，需人工确认"
                notify("约面匹配歧义",
                       f"{schedule.candidate_name} 在Boss中有多个同名候选人",
                       level="warning")
                self._update_schedule(schedule)
                return schedule

            if candidate.match_status == CandidateMatchStatus.UNMATCHED:
                schedule.status = InterviewStatus.MANUAL_REQUIRED
                schedule.error_message = "未在Boss聊天列表中找到候选人"
                self._update_schedule(schedule)
                return schedule

            schedule.candidate_boss_id = candidate.boss_chat_id

        # 发送时间选项
        if schedule.interviewer_time_slots:
            return self._send_time_options(schedule)
        else:
            schedule.status = InterviewStatus.MANUAL_REQUIRED
            schedule.error_message = "面试官未设置可面时间"
            self._update_schedule(schedule)
            return schedule

    def _send_time_options(self, schedule: InterviewSchedule) -> InterviewSchedule:
        """发送时间选项给候选人"""
        time_options = self.time_matcher.format_time_options(
            schedule.interviewer_time_slots
        )

        template = get_message_template(
            schedule.applied_position, "first_contact"
        )
        message = template.format(
            position=schedule.applied_position,
            time_options=time_options,
            interview_type=schedule.interview_type.value,
            duration=60,
        )

        try:
            self.boss.send_message(schedule.candidate_boss_id, message)
            schedule.status = InterviewStatus.TIME_SENT
            schedule.first_contact_time = datetime.now().isoformat()
            self.logger.audit(
                action="send_time_options",
                module="scheduler",
                target=schedule.candidate_name,
                result="success",
                details={"slot_count": len(schedule.interviewer_time_slots)}
            )
        except BossPluginError as e:
            schedule.error_message = f"消息发送失败: {e}"
            self.logger.error(f"约面消息发送失败: {schedule.candidate_name} - {e}")
            notify("消息发送失败",
                   f"{schedule.candidate_name} 约面消息发送失败",
                   level="error")

        self._update_schedule(schedule)
        return schedule

    def process_candidate_reply(self, schedule: InterviewSchedule,
                                 reply_content: str) -> InterviewSchedule:
        """
        处理候选人回复：解析时间 → 匹配 → 创建面试
        """
        schedule.candidate_reply = reply_content

        result = self.time_matcher.parse_candidate_reply(
            reply_content, schedule.interviewer_time_slots
        )

        if result["type"] == "rejected":
            schedule.status = InterviewStatus.CANDIDATE_REJECTED
            self._mark_moka_status(schedule, "候选人拒绝")
            self._update_schedule(schedule)
            self.logger.audit(
                action="candidate_reply",
                module="scheduler",
                target=schedule.candidate_name,
                result="rejected"
            )
            return schedule

        matched_slot = self.time_matcher.match_time(
            result, schedule.interviewer_time_slots
        )

        if matched_slot:
            schedule.matched_slot = matched_slot
            schedule.status = InterviewStatus.TIME_CONFIRMED
            self._update_schedule(schedule)
            return self._create_interview(schedule)

        # 无匹配时间，推送备选
        if result["type"] == "time_direct":
            return self._send_alternative_times(schedule)

        if result["type"] == "unknown":
            schedule.status = InterviewStatus.MANUAL_REQUIRED
            schedule.error_message = f"无法解析回复: {reply_content}"
            self._update_schedule(schedule)
            return schedule

        return schedule

    def _create_interview(self, schedule: InterviewSchedule) -> InterviewSchedule:
        """在 Moka 创建面试并发送邀约"""
        slot = schedule.matched_slot
        if not slot:
            return schedule

        interview_time = f"{slot.date} {slot.start_time}"

        if self.moka_api:
            try:
                result = self.moka_api.create_interview(
                    candidate_id=schedule.moka_resume_id,
                    interviewer_id=schedule.interviewer_id,
                    interview_time=interview_time,
                    interview_type=schedule.interview_type.value,
                    position=schedule.applied_position,
                )
                schedule.moka_interview_id = result.get("interview_id", "")
                schedule.status = InterviewStatus.INTERVIEW_CREATED

                self.moka_api.send_interview_invitation(schedule.moka_interview_id)
                schedule.status = InterviewStatus.INVITE_SENT

                notify("面试创建成功",
                       f"{schedule.candidate_name} - {interview_time}",
                       level="info")

                self._send_confirmation(schedule)

            except MokaAPIError as e:
                schedule.status = InterviewStatus.FAILED
                schedule.error_message = f"面试创建失败: {e}"
                notify("面试创建失败",
                       f"{schedule.candidate_name}: {e}",
                       level="error")
        else:
            schedule.status = InterviewStatus.MANUAL_REQUIRED
            schedule.error_message = "Moka API 不可用，需人工在 Moka 创建面试"
            notify("需人工创建面试",
                   f"{schedule.candidate_name} 时间确认: {interview_time}",
                   level="warning")

        schedule.updated_at = datetime.now().isoformat()
        self._update_schedule(schedule)

        self.logger.audit(
            action="create_interview",
            module="scheduler",
            target=schedule.candidate_name,
            result=schedule.status.value,
            details={
                "time": interview_time,
                "moka_interview_id": schedule.moka_interview_id,
            }
        )
        return schedule

    def _send_confirmation(self, schedule: InterviewSchedule):
        """发送面试确认消息给候选人"""
        if not schedule.candidate_boss_id or not schedule.matched_slot:
            return

        template = get_message_template(
            schedule.applied_position, "interview_confirmed"
        )
        message = template.format(
            position=schedule.applied_position,
            interview_time=f"{schedule.matched_slot.date} {schedule.matched_slot.start_time}-{schedule.matched_slot.end_time}",
            interview_type=schedule.interview_type.value,
            interviewer_name=schedule.interviewer_name,
            extra_info="",
        )
        try:
            self.boss.send_message(schedule.candidate_boss_id, message)
        except BossPluginError as e:
            self.logger.warning(f"确认消息发送失败: {e}")

    def _send_alternative_times(self, schedule: InterviewSchedule) -> InterviewSchedule:
        """候选人选的时间不匹配，发送面试官备选时间"""
        template = get_message_template(
            schedule.applied_position, "no_time_match"
        )
        time_options = self.time_matcher.format_time_options(
            schedule.interviewer_time_slots
        )
        message = template.format(alternative_times=time_options)

        try:
            self.boss.send_message(schedule.candidate_boss_id, message)
        except BossPluginError as e:
            self.logger.warning(f"备选时间消息发送失败: {e}")

        self._update_schedule(schedule)
        return schedule

    def _mark_moka_status(self, schedule: InterviewSchedule, status: str):
        """更新 Moka 候选人状态"""
        if self.moka_api and schedule.moka_resume_id:
            try:
                self.moka_api.add_candidate_note(
                    schedule.moka_resume_id, status
                )
            except MokaAPIError as e:
                self.logger.warning(f"Moka 状态更新失败: {e}")

    def _fetch_pending_candidates(self) -> list[dict]:
        """从 Moka 获取待约面候选人"""
        if self.moka_api:
            try:
                return self.moka_api.get_candidates_by_status("待约面")
            except MokaAPIError as e:
                self.logger.warning(f"Moka API 获取待约面失败，切换 CSV: {e}")

        return self.moka_csv.parse_pending_interviews_csv()

    def _create_schedule_from_candidate(self, data: dict) -> InterviewSchedule | None:
        """从 Moka 候选人数据创建约面记录"""
        candidate_id = data.get("candidate_id", "")
        name = data.get("name", "")
        position = data.get("position", "")

        if not name:
            return None

        # 获取面试官可面时间
        interviewer_times = data.get("interviewer_times", "")
        interviewer_name = data.get("interviewer", "")
        interviewer_id = data.get("interviewer_id", "")

        if isinstance(interviewer_times, str):
            slots = self.moka_csv.parse_interviewer_times_from_csv(interviewer_times)
        elif isinstance(interviewer_times, list) and self.moka_api:
            slots = self.moka_api.parse_interviewer_times(interviewer_times)
        else:
            slots = []

        schedule = InterviewSchedule(
            id=str(uuid.uuid4())[:8],
            moka_resume_id=candidate_id,
            candidate_name=name,
            applied_position=position,
            interviewer_name=interviewer_name,
            interviewer_id=interviewer_id,
            interviewer_time_slots=slots,
            status=InterviewStatus.PENDING_SCHEDULE,
        )
        return schedule

    # ========== 持久化 ==========

    def _load_schedules(self) -> list[InterviewSchedule]:
        if SCHEDULE_FILE.exists():
            with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [InterviewSchedule.from_dict(d) for d in data]
        return []

    def _save_schedules(self, schedules: list[InterviewSchedule]):
        data = [s.to_dict() for s in schedules]
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _update_schedule(self, schedule: InterviewSchedule):
        schedules = self._load_schedules()
        for i, s in enumerate(schedules):
            if s.id == schedule.id:
                schedules[i] = schedule
                break
        else:
            schedules.append(schedule)
        self._save_schedules(schedules)

    def get_all_schedules(self) -> list[InterviewSchedule]:
        return self._load_schedules()

    def get_schedule_by_id(self, schedule_id: str) -> InterviewSchedule | None:
        for s in self._load_schedules():
            if s.id == schedule_id:
                return s
        return None
