"""候选人数据模型 - Boss直聘匹配与触达状态跟踪"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CandidateMatchStatus(Enum):
    UNMATCHED = "unmatched"             # 未匹配 Boss 聊天
    MATCHED = "matched"                 # 已匹配
    AMBIGUOUS = "ambiguous"             # 姓名重复，需人工确认
    MANUAL_CONFIRMED = "manual_confirmed"  # 人工确认后匹配


class TouchStatus(Enum):
    NOT_CONTACTED = "not_contacted"
    FIRST_SENT = "first_sent"
    FOLLOWUP_1_SENT = "followup_1_sent"
    FOLLOWUP_2_SENT = "followup_2_sent"
    REPLIED = "replied"
    REJECTED = "rejected"
    NO_RESPONSE = "no_response"


@dataclass
class Candidate:
    id: str = ""
    name: str = ""
    phone: str = ""
    applied_position: str = ""

    moka_resume_id: str = ""
    boss_chat_id: str = ""
    boss_candidate_id: str = ""

    match_status: CandidateMatchStatus = CandidateMatchStatus.UNMATCHED
    touch_status: TouchStatus = TouchStatus.NOT_CONTACTED

    last_message_sent_at: str = ""
    last_reply_at: str = ""
    last_reply_content: str = ""
    total_messages_sent: int = 0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def can_send_followup(self, cooldown_hours: int = 24) -> bool:
        if self.touch_status in (TouchStatus.REJECTED, TouchStatus.NO_RESPONSE):
            return False
        if not self.last_message_sent_at:
            return True
        last_sent = datetime.fromisoformat(self.last_message_sent_at)
        hours_since = (datetime.now() - last_sent).total_seconds() / 3600
        return hours_since >= cooldown_hours

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "applied_position": self.applied_position,
            "moka_resume_id": self.moka_resume_id,
            "boss_chat_id": self.boss_chat_id,
            "boss_candidate_id": self.boss_candidate_id,
            "match_status": self.match_status.value,
            "touch_status": self.touch_status.value,
            "last_message_sent_at": self.last_message_sent_at,
            "last_reply_at": self.last_reply_at,
            "last_reply_content": self.last_reply_content,
            "total_messages_sent": self.total_messages_sent,
            "created_at": self.created_at,
        }
