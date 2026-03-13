from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Position ──

class PositionCreate(BaseModel):
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    jd_text: Optional[str] = None
    jd_keywords: Optional[list] = None
    jd_must_have: Optional[list] = None
    jd_nice_to_have: Optional[list] = None
    jd_education: Optional[str] = None
    jd_min_years: Optional[float] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    headcount: int = 1
    match_threshold: float = 60.0
    auto_recommend: bool = False
    moka_job_id: Optional[str] = None
    moka_stage_id: Optional[str] = None


class PositionUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    jd_text: Optional[str] = None
    jd_keywords: Optional[list] = None
    jd_must_have: Optional[list] = None
    jd_nice_to_have: Optional[list] = None
    jd_education: Optional[str] = None
    jd_min_years: Optional[float] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    headcount: Optional[int] = None
    match_threshold: Optional[float] = None
    auto_recommend: Optional[bool] = None
    moka_job_id: Optional[str] = None
    moka_stage_id: Optional[str] = None
    is_active: Optional[bool] = None


class PositionOut(BaseModel):
    id: int
    title: str
    department: Optional[str]
    location: Optional[str]
    description: Optional[str]
    requirements: Optional[str]
    jd_text: Optional[str]
    jd_keywords: Optional[list]
    jd_must_have: Optional[list]
    jd_nice_to_have: Optional[list]
    jd_education: Optional[str]
    jd_min_years: Optional[float]
    salary_min: Optional[int]
    salary_max: Optional[int]
    headcount: int
    match_threshold: Optional[float]
    auto_recommend: bool
    is_active: bool
    resume_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Resume ──

class ResumeOut(BaseModel):
    id: int
    candidate_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    gender: Optional[str]
    age: Optional[int]
    education: Optional[str]
    school: Optional[str]
    major: Optional[str]
    work_years: Optional[float]
    current_company: Optional[str]
    current_position: Optional[str]
    city: Optional[str]
    expected_salary_min: Optional[int]
    expected_salary_max: Optional[int]
    skills: list = []
    work_experience: list = []
    project_experience: list = []
    education_history: list = []
    raw_text: Optional[str]
    file_path: Optional[str]
    source: str
    status: str
    position_id: Optional[int]
    position_title: Optional[str] = None
    screening_score: Optional[float]
    screening_detail: Optional[dict]
    screening_risks: list = []
    jd_match_score: Optional[float]
    jd_match_detail: Optional[dict]
    pipeline_status: Optional[str]
    candidate_reply: Optional[str]
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResumeUpdate(BaseModel):
    candidate_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    education: Optional[str] = None
    school: Optional[str] = None
    major: Optional[str] = None
    work_years: Optional[float] = None
    current_company: Optional[str] = None
    current_position: Optional[str] = None
    city: Optional[str] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    skills: Optional[list] = None
    status: Optional[str] = None
    position_id: Optional[int] = None
    remark: Optional[str] = None


class ResumeBatchAction(BaseModel):
    resume_ids: list[int]
    action: str  # "pass", "reject", "assign_position", "screen"
    position_id: Optional[int] = None
    reason: Optional[str] = None


# ── Screening Rule ──

class ScreeningRuleCreate(BaseModel):
    position_id: int
    name: str
    field: str
    operator: str
    value: str
    is_knockout: bool = False
    weight: float = 1.0
    is_active: bool = True
    order: int = 0


class ScreeningRuleUpdate(BaseModel):
    name: Optional[str] = None
    field: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[str] = None
    is_knockout: Optional[bool] = None
    weight: Optional[float] = None
    is_active: Optional[bool] = None
    order: Optional[int] = None


class ScreeningRuleOut(BaseModel):
    id: int
    position_id: int
    name: str
    field: str
    operator: str
    value: str
    is_knockout: bool
    weight: float
    is_active: bool
    order: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Email Config ──

class EmailConfigCreate(BaseModel):
    imap_server: str
    imap_port: int = 993
    email_address: str
    password: str
    use_ssl: bool = True
    sender_filter: str = "bosszhipin"


class EmailConfigUpdate(BaseModel):
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    email_address: Optional[str] = None
    password: Optional[str] = None
    use_ssl: Optional[bool] = None
    sender_filter: Optional[str] = None
    is_active: Optional[bool] = None


class EmailConfigOut(BaseModel):
    id: int
    imap_server: str
    imap_port: int
    email_address: str
    use_ssl: bool
    sender_filter: str
    is_active: bool
    last_check_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard ──

class DashboardStats(BaseModel):
    total_resumes: int
    pending_resumes: int
    passed_resumes: int
    rejected_resumes: int
    interview_resumes: int
    active_positions: int
    today_new_resumes: int
    this_week_new_resumes: int


# ── Pagination ──

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
