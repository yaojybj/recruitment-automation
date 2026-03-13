"""面试数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class InterviewStatus(Enum):
    PENDING_SCHEDULE = "pending_schedule"       # 待约面
    TIME_SENT = "time_sent"                     # 已发送时间选项
    FOLLOWUP_1 = "followup_1"                   # 第一次二次触达
    FOLLOWUP_2 = "followup_2"                   # 第二次二次触达
    TIME_CONFIRMED = "time_confirmed"           # 候选人已确认时间
    INTERVIEW_CREATED = "interview_created"     # 面试已创建
    INVITE_SENT = "invite_sent"                 # 邀约已发送
    NO_RESPONSE = "no_response"                 # 约面失败-未回复
    CANDIDATE_REJECTED = "candidate_rejected"   # 候选人拒绝
    MANUAL_REQUIRED = "manual_required"         # 需人工协调
    FAILED = "failed"                           # 流程失败


class InterviewType(Enum):
    ONLINE = "线上面试"
    ONSITE = "现场面试"
    PHONE = "电话面试"


@dataclass
class TimeSlot:
    date: str = ""           # YYYY-MM-DD
    start_time: str = ""     # HH:MM
    end_time: str = ""       # HH:MM
    priority: str = "普通"   # 优先/备选/普通
    weekday: str = ""

    @property
    def display(self) -> str:
        return f"{self.date} {self.weekday} {self.start_time}-{self.end_time} ({self.priority})"


@dataclass
class InterviewSchedule:
    id: str = ""
    resume_id: str = ""
    moka_resume_id: str = ""
    candidate_name: str = ""
    candidate_boss_id: str = ""
    applied_position: str = ""

    interviewer_name: str = ""
    interviewer_id: str = ""
    interview_type: InterviewType = InterviewType.ONLINE

    interviewer_time_slots: list[TimeSlot] = field(default_factory=list)
    candidate_selected_slot: TimeSlot | None = None
    matched_slot: TimeSlot | None = None

    status: InterviewStatus = InterviewStatus.PENDING_SCHEDULE
    moka_interview_id: str = ""

    first_contact_time: str = ""
    last_followup_time: str = ""
    followup_count: int = 0
    candidate_reply: str = ""

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resume_id": self.resume_id,
            "moka_resume_id": self.moka_resume_id,
            "candidate_name": self.candidate_name,
            "candidate_boss_id": self.candidate_boss_id,
            "applied_position": self.applied_position,
            "interviewer_name": self.interviewer_name,
            "interviewer_id": self.interviewer_id,
            "interview_type": self.interview_type.value,
            "interviewer_time_slots": [
                {"date": s.date, "start_time": s.start_time,
                 "end_time": s.end_time, "priority": s.priority,
                 "weekday": s.weekday}
                for s in self.interviewer_time_slots
            ],
            "candidate_selected_slot": (
                {"date": self.candidate_selected_slot.date,
                 "start_time": self.candidate_selected_slot.start_time,
                 "end_time": self.candidate_selected_slot.end_time}
                if self.candidate_selected_slot else None
            ),
            "matched_slot": (
                {"date": self.matched_slot.date,
                 "start_time": self.matched_slot.start_time,
                 "end_time": self.matched_slot.end_time}
                if self.matched_slot else None
            ),
            "status": self.status.value,
            "moka_interview_id": self.moka_interview_id,
            "followup_count": self.followup_count,
            "first_contact_time": self.first_contact_time,
            "last_followup_time": self.last_followup_time,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewSchedule":
        slots = []
        for s in data.get("interviewer_time_slots", []):
            if isinstance(s, dict):
                slots.append(TimeSlot(**s))
            else:
                slots.append(s)

        selected = data.get("candidate_selected_slot")
        if isinstance(selected, dict):
            selected = TimeSlot(**selected)

        matched = data.get("matched_slot")
        if isinstance(matched, dict):
            matched = TimeSlot(**matched)

        return cls(
            id=data.get("id", ""),
            resume_id=data.get("resume_id", ""),
            moka_resume_id=data.get("moka_resume_id", ""),
            candidate_name=data.get("candidate_name", ""),
            candidate_boss_id=data.get("candidate_boss_id", ""),
            applied_position=data.get("applied_position", ""),
            interviewer_name=data.get("interviewer_name", ""),
            interviewer_id=data.get("interviewer_id", ""),
            interview_type=InterviewType(
                data.get("interview_type", "线上面试")
            ),
            interviewer_time_slots=slots,
            candidate_selected_slot=selected,
            matched_slot=matched,
            status=InterviewStatus(
                data.get("status", "pending_schedule")
            ),
            moka_interview_id=data.get("moka_interview_id", ""),
            first_contact_time=data.get("first_contact_time", ""),
            last_followup_time=data.get("last_followup_time", ""),
            followup_count=data.get("followup_count", 0),
            candidate_reply=data.get("candidate_reply", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error_message=data.get("error_message", ""),
        )
