import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


class ResumeStatus(str, enum.Enum):
    PENDING = "pending"              # 入池待处理
    JD_MATCHED = "jd_matched"        # JD匹配完成（有分数）
    RECOMMENDED = "recommended"      # 已推荐给用人部门（推到Moka）
    DEPT_APPROVED = "dept_approved"  # 用人部门审核通过
    DEPT_REJECTED = "dept_rejected"  # 用人部门审核不通过
    CONTACTING = "contacting"        # 正在Boss上联系候选人
    TIME_SENT = "time_sent"          # 已发送面试时间选项
    TIME_CONFIRMED = "time_confirmed"  # 候选人已确认时间
    INTERVIEW_SCHEDULED = "interview_scheduled"  # Moka面试已安排
    INTERVIEW_DONE = "interview_done"  # 面试已完成
    OFFER = "offer"
    ONBOARD = "onboard"
    REJECTED = "rejected"            # 筛选淘汰
    ELIMINATED = "eliminated"        # 流程中淘汰


class ResumeSource(str, enum.Enum):
    EMAIL = "email"
    MANUAL_UPLOAD = "manual_upload"
    FOLDER_IMPORT = "folder_import"
    BOSS_EXTENSION = "boss_extension"


class RuleOperator(str, enum.Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    IN = "in"
    NOT_IN = "not_in"
    REGEX = "regex"


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    department = Column(String(100))
    location = Column(String(100))
    description = Column(Text)
    requirements = Column(Text)
    jd_text = Column(Text)
    jd_keywords = Column(JSON, default=list)
    jd_must_have = Column(JSON, default=list)
    jd_nice_to_have = Column(JSON, default=list)
    jd_education = Column(String(50))
    jd_min_years = Column(Float)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    headcount = Column(Integer, default=1)
    match_threshold = Column(Float, default=60.0)
    auto_recommend = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    moka_job_id = Column(String(100))
    moka_stage_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    resumes = relationship("Resume", back_populates="position")
    screening_rules = relationship("ScreeningRule", back_populates="position", cascade="all, delete-orphan")
    interview_slots = relationship("InterviewSlot", back_populates="position", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_name = Column(String(100))
    phone = Column(String(20))
    email = Column(String(200))
    gender = Column(String(10))
    age = Column(Integer)
    education = Column(String(50))
    school = Column(String(200))
    major = Column(String(200))
    work_years = Column(Float)
    current_company = Column(String(200))
    current_position = Column(String(200))
    city = Column(String(50))
    expected_salary_min = Column(Integer)
    expected_salary_max = Column(Integer)
    skills = Column(JSON, default=list)
    work_experience = Column(JSON, default=list)
    project_experience = Column(JSON, default=list)
    education_history = Column(JSON, default=list)
    raw_text = Column(Text)
    file_path = Column(String(500))
    source = Column(String(50), default="manual_upload")
    status = Column(SAEnum(ResumeStatus), default=ResumeStatus.PENDING)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    screening_score = Column(Float)
    screening_detail = Column(JSON)
    screening_risks = Column(JSON, default=list)
    jd_match_score = Column(Float)
    jd_match_detail = Column(JSON)
    pipeline_status = Column(String(50), default="pending")
    boss_chat_id = Column(String(200))
    boss_candidate_id = Column(String(200))
    moka_candidate_id = Column(String(200))
    moka_application_id = Column(String(200))
    interview_slot_id = Column(Integer, ForeignKey("interview_slots.id"), nullable=True)
    candidate_reply = Column(Text)
    candidate_reply_time = Column(DateTime)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    position = relationship("Position", back_populates="resumes")
    interview_slot = relationship("InterviewSlot")


class ScreeningRule(Base):
    __tablename__ = "screening_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    name = Column(String(200), nullable=False)
    field = Column(String(100), nullable=False)
    operator = Column(SAEnum(RuleOperator), nullable=False)
    value = Column(String(500), nullable=False)
    is_knockout = Column(Boolean, default=False)
    weight = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    position = relationship("Position", back_populates="screening_rules")


class ScreeningLog(Base):
    __tablename__ = "screening_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    rule_id = Column(Integer, ForeignKey("screening_rules.id"), nullable=True)
    rule_name = Column(String(200))
    field = Column(String(100))
    expected_value = Column(String(500))
    actual_value = Column(String(500))
    passed = Column(Boolean)
    score = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    resume = relationship("Resume")


class EmailConfig(Base):
    __tablename__ = "email_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    imap_server = Column(String(200), nullable=False)
    imap_port = Column(Integer, default=993)
    email_address = Column(String(200), nullable=False)
    password = Column(String(500), nullable=False)
    use_ssl = Column(Boolean, default=True)
    sender_filter = Column(String(200), default="bosszhipin")
    is_active = Column(Boolean, default=True)
    last_check_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class InterviewSlot(Base):
    """面试时间段：HR 录入可用的面试时间"""
    __tablename__ = "interview_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    date = Column(String(20), nullable=False)
    start_time = Column(String(10), nullable=False)
    end_time = Column(String(10), nullable=False)
    interviewer_name = Column(String(100))
    interviewer_email = Column(String(200))
    location = Column(String(200))
    is_online = Column(Boolean, default=False)
    meeting_link = Column(String(500))
    capacity = Column(Integer, default=1)
    booked_count = Column(Integer, default=0)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    position = relationship("Position", back_populates="interview_slots")


class PipelineLog(Base):
    """流程流转日志：记录每份简历在流程中的每一步"""
    __tablename__ = "pipeline_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    from_status = Column(String(50))
    to_status = Column(String(50), nullable=False)
    action = Column(String(100))
    detail = Column(Text)
    operator = Column(String(100), default="system")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    resume = relationship("Resume")


class ExtensionTask(Base):
    """插件任务队列：后台派发任务给 Chrome 插件执行"""
    __tablename__ = "extension_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(50), nullable=False)
    platform = Column(String(20), nullable=False)  # "boss" or "moka"
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    payload = Column(JSON, default=dict)
    status = Column(String(20), default="pending")  # pending / running / done / failed
    result = Column(JSON)
    error = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    resume = relationship("Resume")
    position = relationship("Position")


class BossConfig(Base):
    """Boss 直聘自动化配置"""
    __tablename__ = "boss_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cookie = Column(Text)
    token = Column(Text)
    auto_contact = Column(Boolean, default=False)
    message_template = Column(Text, default="您好，我是{company}的HR，您投递的{position}岗位我们非常感兴趣，想跟您约一个面试时间。以下是可选的面试时间：\n{time_slots}\n请回复您方便的时间编号即可，谢谢！")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50))
    target_id = Column(Integer)
    detail = Column(Text)
    operator = Column(String(100), default="system")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
