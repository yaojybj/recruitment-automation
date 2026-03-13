"""简历数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ScreeningStatus(Enum):
    PENDING_SCREEN = "pending_screen"       # 待筛选
    AUTO_REJECTED = "auto_rejected"         # 自动淘汰
    PENDING_REVIEW = "pending_review"       # 待人工复核
    REVIEW_APPROVED = "review_approved"     # 复核通过
    REVIEW_REJECTED = "review_rejected"     # 复核驳回
    PUSHED_TO_MOKA = "pushed_to_moka"       # 已推送至Moka


@dataclass
class WorkExperience:
    company: str = ""
    position: str = ""
    start_date: str = ""
    end_date: str = ""
    duration_months: int = 0
    industry: str = ""
    description: str = ""


@dataclass
class Resume:
    id: str = ""
    moka_id: str = ""
    boss_candidate_id: str = ""

    name: str = ""
    phone: str = ""
    email: str = ""
    city: str = ""
    education: str = ""
    school: str = ""
    major: str = ""

    total_work_years: int = 0
    expected_salary_min: int = 0
    expected_salary_max: int = 0
    current_salary: int = 0

    skills: list[str] = field(default_factory=list)
    work_experiences: list[WorkExperience] = field(default_factory=list)
    project_count: int = 0
    has_portfolio: bool = False
    portfolio_url: str = ""

    applied_position: str = ""
    source: str = "Boss直聘"

    match_score: int = 0
    score_breakdown: dict = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)
    screening_status: ScreeningStatus = ScreeningStatus.PENDING_SCREEN
    reject_reason: str = ""

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_at: str = ""
    reviewed_by: str = ""

    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "moka_id": self.moka_id,
            "boss_candidate_id": self.boss_candidate_id,
            "name": self.name,
            "phone": self.phone,
            "city": self.city,
            "education": self.education,
            "total_work_years": self.total_work_years,
            "expected_salary": f"{self.expected_salary_min}-{self.expected_salary_max}",
            "skills": self.skills,
            "applied_position": self.applied_position,
            "match_score": self.match_score,
            "score_breakdown": self.score_breakdown,
            "risk_flags": self.risk_flags,
            "screening_status": self.screening_status.value,
            "reject_reason": self.reject_reason,
            "has_portfolio": self.has_portfolio,
            "project_count": self.project_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Resume":
        status_str = data.get("screening_status", "pending_screen")
        status = ScreeningStatus(status_str) if isinstance(status_str, str) else status_str

        experiences = []
        for exp in data.get("work_experiences", []):
            if isinstance(exp, dict):
                experiences.append(WorkExperience(**exp))
            else:
                experiences.append(exp)

        return cls(
            id=data.get("id", ""),
            moka_id=data.get("moka_id", ""),
            boss_candidate_id=data.get("boss_candidate_id", ""),
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            city=data.get("city", ""),
            education=data.get("education", ""),
            school=data.get("school", ""),
            major=data.get("major", ""),
            total_work_years=data.get("total_work_years", 0),
            expected_salary_min=data.get("expected_salary_min", 0),
            expected_salary_max=data.get("expected_salary_max", 0),
            skills=data.get("skills", []),
            work_experiences=experiences,
            project_count=data.get("project_count", 0),
            has_portfolio=data.get("has_portfolio", False),
            portfolio_url=data.get("portfolio_url", ""),
            applied_position=data.get("applied_position", ""),
            source=data.get("source", "Boss直聘"),
            match_score=data.get("match_score", 0),
            score_breakdown=data.get("score_breakdown", {}),
            risk_flags=data.get("risk_flags", []),
            screening_status=status,
            reject_reason=data.get("reject_reason", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            raw_data=data.get("raw_data", {}),
        )
