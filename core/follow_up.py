"""
模块3：候选人未选时间二次触达
24小时未回复 → Boss直聘二次发送 → 最多重试2次 → 超时标记失败
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from models.interview import InterviewSchedule, InterviewStatus
from models.candidate import Candidate, CandidateMatchStatus, TouchStatus
from core.time_matcher import TimeMatcher
from core.scheduler import InterviewScheduler
from adapters.boss_plugin import BossPluginAdapter, BossPluginError
from adapters.moka_api import MokaAPI, MokaAPIError
from utils.config_loader import get_settings, get_message_template
from utils.logger import get_logger
from utils.notifier import notify


DATA_DIR = Path("./data")
FOLLOWUP_STATE_FILE = DATA_DIR / "followup_state.json"


class FollowUpManager:
    """二次触达管理器"""

    def __init__(self, scheduler: InterviewScheduler,
                 boss: BossPluginAdapter | None = None,
                 moka_api: MokaAPI | None = None):
        self.scheduler = scheduler
        self.boss = boss or BossPluginAdapter()
        self.moka_api = moka_api
        self.time_matcher = TimeMatcher()
        self.logger = get_logger()
        self.settings = get_settings()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        scheduling = self.settings.get("scheduling", {})
        self.timeout_hours = scheduling.get("candidate_response_timeout_hours", 24)
        self.max_retries = scheduling.get("max_followup_retries", 2)
        self.cooldown_hours = scheduling.get("followup_cooldown_hours", 24)

    def check_and_followup(self) -> list[dict]:
        """
        主入口：检测所有未回复的约面记录，执行二次触达
        由调度器每30分钟调用
        """
        self.logger.info("开始检查未回复候选人...")
        schedules = self.scheduler.get_all_schedules()
        results = []

        for schedule in schedules:
            if not self._needs_followup(schedule):
                continue

            result = self._process_followup(schedule)
            results.append(result)

        if results:
            self.logger.info(
                f"二次触达检查完成: 处理 {len(results)} 条"
            )
        return results

    def check_replies(self) -> list[dict]:
        """
        检查所有已发送约面消息的候选人回复
        """
        schedules = self.scheduler.get_all_schedules()
        results = []

        for schedule in schedules:
            if schedule.status not in (
                InterviewStatus.TIME_SENT,
                InterviewStatus.FOLLOWUP_1,
                InterviewStatus.FOLLOWUP_2,
            ):
                continue

            if not schedule.candidate_boss_id:
                continue

            reply = self.boss.get_candidate_latest_reply(
                schedule.candidate_boss_id,
                since=schedule.first_contact_time
            )

            if reply:
                self.logger.info(
                    f"收到候选人回复: {schedule.candidate_name} -> {reply['content']}"
                )
                updated = self.scheduler.process_candidate_reply(
                    schedule, reply["content"]
                )
                results.append({
                    "candidate": schedule.candidate_name,
                    "action": "reply_processed",
                    "status": updated.status.value,
                    "reply": reply["content"],
                })

        return results

    def _needs_followup(self, schedule: InterviewSchedule) -> bool:
        """判断是否需要二次触达"""
        if schedule.status not in (
            InterviewStatus.TIME_SENT,
            InterviewStatus.FOLLOWUP_1,
            InterviewStatus.FOLLOWUP_2,
        ):
            return False

        ref_time = schedule.last_followup_time or schedule.first_contact_time
        if not ref_time:
            return False

        last_sent = datetime.fromisoformat(ref_time)
        hours_since = (datetime.now() - last_sent).total_seconds() / 3600

        if hours_since < self.timeout_hours:
            return False

        if schedule.followup_count >= self.max_retries:
            self._mark_no_response(schedule)
            return False

        return True

    def _process_followup(self, schedule: InterviewSchedule) -> dict:
        """执行单条二次触达"""
        result = {
            "candidate": schedule.candidate_name,
            "position": schedule.applied_position,
            "action": "",
            "status": "",
        }

        first_reply = self.boss.get_candidate_latest_reply(
            schedule.candidate_boss_id,
            since=schedule.first_contact_time
        )
        if first_reply:
            updated = self.scheduler.process_candidate_reply(
                schedule, first_reply["content"]
            )
            result["action"] = "reply_found"
            result["status"] = updated.status.value
            return result

        followup_num = schedule.followup_count + 1
        template_key = f"followup_{'first' if followup_num == 1 else 'second'}"
        template = get_message_template(
            schedule.applied_position, template_key
        )

        time_options = self.time_matcher.format_time_options(
            schedule.interviewer_time_slots
        )
        message = template.format(
            position=schedule.applied_position,
            time_options=time_options,
        )

        try:
            self.boss.send_message(schedule.candidate_boss_id, message)

            schedule.followup_count = followup_num
            schedule.last_followup_time = datetime.now().isoformat()

            if followup_num == 1:
                schedule.status = InterviewStatus.FOLLOWUP_1
            else:
                schedule.status = InterviewStatus.FOLLOWUP_2

            self.scheduler._update_schedule(schedule)

            result["action"] = f"followup_{followup_num}_sent"
            result["status"] = schedule.status.value

            self.logger.audit(
                action=f"followup_{followup_num}",
                module="follow_up",
                target=schedule.candidate_name,
                result="sent",
                details={"schedule_id": schedule.id}
            )

        except BossPluginError as e:
            result["action"] = "send_failed"
            result["status"] = "error"
            self.logger.error(
                f"二次触达发送失败: {schedule.candidate_name} - {e}"
            )
            notify("二次触达发送失败",
                   f"{schedule.candidate_name}: {e}",
                   level="error")

        return result

    def _mark_no_response(self, schedule: InterviewSchedule):
        """标记约面失败-未回复"""
        schedule.status = InterviewStatus.NO_RESPONSE
        schedule.updated_at = datetime.now().isoformat()
        self.scheduler._update_schedule(schedule)

        if self.moka_api and schedule.moka_resume_id:
            try:
                self.moka_api.add_candidate_note(
                    schedule.moka_resume_id,
                    "约面失败-未回复"
                )
            except MokaAPIError as e:
                self.logger.warning(f"Moka备注更新失败: {e}")

        self.logger.audit(
            action="mark_no_response",
            module="follow_up",
            target=schedule.candidate_name,
            result="no_response",
            details={"followup_count": schedule.followup_count}
        )

    def get_followup_summary(self) -> dict:
        """获取二次触达统计摘要"""
        schedules = self.scheduler.get_all_schedules()
        summary = {
            "total_scheduled": len(schedules),
            "pending": 0,
            "time_sent": 0,
            "followup_1": 0,
            "followup_2": 0,
            "confirmed": 0,
            "created": 0,
            "no_response": 0,
            "rejected": 0,
            "manual_required": 0,
            "failed": 0,
        }

        status_map = {
            InterviewStatus.PENDING_SCHEDULE: "pending",
            InterviewStatus.TIME_SENT: "time_sent",
            InterviewStatus.FOLLOWUP_1: "followup_1",
            InterviewStatus.FOLLOWUP_2: "followup_2",
            InterviewStatus.TIME_CONFIRMED: "confirmed",
            InterviewStatus.INTERVIEW_CREATED: "created",
            InterviewStatus.INVITE_SENT: "created",
            InterviewStatus.NO_RESPONSE: "no_response",
            InterviewStatus.CANDIDATE_REJECTED: "rejected",
            InterviewStatus.MANUAL_REQUIRED: "manual_required",
            InterviewStatus.FAILED: "failed",
        }

        for s in schedules:
            key = status_map.get(s.status, "failed")
            summary[key] += 1

        return summary
