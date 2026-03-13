"""
Boss 直聘适配器
负责在 Boss 直聘上找到候选人、发送面试邀约消息、获取候选人回复。

实现方式：
1. 预留浏览器自动化接口（Playwright），后续接入
2. 当前阶段用"操作指引"模式：系统生成消息模板，HR 手动发送后录入回复

后续可接入 Playwright 实现全自动：
  - 自动登录 Boss 直聘
  - 搜索候选人聊天
  - 发送消息
  - 监听回复
"""
from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Resume, Position, InterviewSlot, BossConfig, PipelineLog, ResumeStatus

logger = logging.getLogger(__name__)


def generate_interview_message(
    db: Session,
    resume: Resume,
    position: Position,
) -> dict:
    """
    生成发送给候选人的面试邀约消息。
    包含可选的面试时间段。
    """
    slots = (
        db.query(InterviewSlot)
        .filter(
            InterviewSlot.position_id == position.id,
            InterviewSlot.is_available == True,
        )
        .order_by(InterviewSlot.date, InterviewSlot.start_time)
        .all()
    )

    if not slots:
        return {
            "success": False,
            "error": "该岗位暂无可用面试时间段，请先在系统中录入",
        }

    time_lines = []
    for i, slot in enumerate(slots, 1):
        loc = ""
        if slot.is_online and slot.meeting_link:
            loc = "（线上面试）"
        elif slot.location:
            loc = f"（{slot.location}）"
        time_lines.append(f"  {i}. {slot.date} {slot.start_time}-{slot.end_time} {loc}")

    time_text = "\n".join(time_lines)

    config = db.query(BossConfig).first()
    template = (config.message_template if config else None) or (
        "您好，我们对您投递的{position}岗位非常感兴趣，"
        "想和您约一个面试时间。\n\n"
        "以下是可选的面试时间：\n{time_slots}\n\n"
        "请回复您方便的时间编号即可，谢谢！"
    )

    message = template.format(
        position=position.title,
        company=position.department or "我们公司",
        time_slots=time_text,
        candidate=resume.candidate_name or "您",
    )

    return {
        "success": True,
        "message": message,
        "slots_count": len(slots),
        "candidate_name": resume.candidate_name,
        "instruction": (
            f"请在 Boss 直聘上找到候选人「{resume.candidate_name}」的聊天窗口，"
            f"发送以上消息。候选人回复后，请在系统中录入回复内容。"
        ),
    }


def mark_message_sent(
    db: Session,
    resume_id: int,
    operator: str = "hr",
) -> dict:
    """标记消息已发送"""
    resume = db.query(Resume).get(resume_id)
    if not resume:
        return {"success": False, "error": "简历不存在"}

    current = resume.status if isinstance(resume.status, str) else resume.status.value
    if current not in ("contacting", "dept_approved"):
        return {"success": False, "error": f"当前状态 {current} 不适合标记发送"}

    resume.status = ResumeStatus.TIME_SENT
    db.add(PipelineLog(
        resume_id=resume.id,
        from_status=current,
        to_status="time_sent",
        action="message_sent",
        detail="面试时间消息已发送给候选人",
        operator=operator,
    ))
    db.commit()
    return {"success": True}


def submit_candidate_reply(
    db: Session,
    resume_id: int,
    reply_text: str,
    operator: str = "hr",
) -> dict:
    """
    HR 录入候选人回复。
    系统自动解析回复中的时间选择，尝试自动分配时间段。
    """
    from .pipeline import record_candidate_reply
    return record_candidate_reply(db, resume_id, reply_text)


def get_pending_contacts(db: Session, position_id: int = None) -> list[dict]:
    """获取待联系的候选人列表（已通过部门审核但还没联系的）"""
    query = db.query(Resume).filter(Resume.status == ResumeStatus.DEPT_APPROVED)
    if position_id:
        query = query.filter(Resume.position_id == position_id)

    resumes = query.order_by(Resume.jd_match_score.desc().nullslast()).all()
    return [
        {
            "id": r.id,
            "name": r.candidate_name,
            "phone": r.phone,
            "position": r.position.title if r.position else None,
            "jd_score": r.jd_match_score,
            "status": r.status if isinstance(r.status, str) else r.status.value,
        }
        for r in resumes
    ]


def get_awaiting_replies(db: Session, position_id: int = None) -> list[dict]:
    """获取已发消息等待回复的候选人"""
    query = db.query(Resume).filter(Resume.status == ResumeStatus.TIME_SENT)
    if position_id:
        query = query.filter(Resume.position_id == position_id)

    resumes = query.order_by(Resume.updated_at.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.candidate_name,
            "position": r.position.title if r.position else None,
            "jd_score": r.jd_match_score,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in resumes
    ]
