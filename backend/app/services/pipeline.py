"""
招聘流程状态机
管理简历从入池到面试安排的全生命周期。

流程：入池(pending) → JD匹配(jd_matched) → 推荐(recommended)
     → 部门审核通过(dept_approved) → 联系候选人(contacting)
     → 已发时间(time_sent) → 时间确认(time_confirmed)
     → 面试安排(interview_scheduled) → 面试完成(interview_done)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    Resume, Position, ResumeStatus, InterviewSlot,
    PipelineLog, OperationLog,
)

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "pending": ["jd_matched", "rejected"],
    "jd_matched": ["recommended", "rejected", "eliminated"],
    "recommended": ["dept_approved", "dept_rejected"],
    "dept_approved": ["contacting", "eliminated"],
    "dept_rejected": ["eliminated", "pending"],
    "contacting": ["time_sent", "eliminated"],
    "time_sent": ["time_confirmed", "eliminated"],
    "time_confirmed": ["interview_scheduled", "eliminated"],
    "interview_scheduled": ["interview_done", "eliminated"],
    "interview_done": ["offer", "eliminated"],
    "offer": ["onboard", "eliminated"],
}


def advance_status(
    db: Session,
    resume_id: int,
    new_status: str,
    detail: str = "",
    operator: str = "system",
) -> dict:
    """推进简历到下一个流程节点"""
    resume = db.query(Resume).get(resume_id)
    if not resume:
        return {"success": False, "error": "简历不存在"}

    current = resume.status if isinstance(resume.status, str) else resume.status.value
    allowed = VALID_TRANSITIONS.get(current, [])

    if new_status not in allowed:
        return {
            "success": False,
            "error": f"不允许从 {current} 转到 {new_status}，可选: {allowed}",
        }

    old_status = current
    resume.status = new_status
    resume.pipeline_status = new_status

    db.add(PipelineLog(
        resume_id=resume.id,
        from_status=old_status,
        to_status=new_status,
        action=f"status_change",
        detail=detail,
        operator=operator,
    ))
    db.commit()

    logger.info(f"简历 {resume.id}({resume.candidate_name}): {old_status} → {new_status}")
    return {"success": True, "from": old_status, "to": new_status}


def recommend_to_dept(db: Session, resume_ids: list[int], operator: str = "system") -> list[dict]:
    """将 JD 匹配通过的简历推荐给用人部门"""
    results = []
    for rid in resume_ids:
        resume = db.query(Resume).get(rid)
        if not resume:
            results.append({"resume_id": rid, "success": False, "error": "不存在"})
            continue
        current = resume.status if isinstance(resume.status, str) else resume.status.value
        if current != "jd_matched":
            results.append({"resume_id": rid, "success": False, "error": f"当前状态 {current}，需为 jd_matched"})
            continue
        result = advance_status(db, rid, "recommended", "推荐给用人部门审核", operator)
        results.append({"resume_id": rid, **result})
    return results


def dept_review(
    db: Session,
    resume_id: int,
    approved: bool,
    reviewer: str = "",
    comment: str = "",
) -> dict:
    """用人部门审核"""
    new_status = "dept_approved" if approved else "dept_rejected"
    detail = f"{'通过' if approved else '未通过'}"
    if reviewer:
        detail += f" (审核人: {reviewer})"
    if comment:
        detail += f" 备注: {comment}"
    return advance_status(db, resume_id, new_status, detail, reviewer or "dept")


def assign_interview_slot(
    db: Session,
    resume_id: int,
    slot_id: int,
    operator: str = "system",
) -> dict:
    """为候选人分配面试时间段"""
    resume = db.query(Resume).get(resume_id)
    slot = db.query(InterviewSlot).get(slot_id)
    if not resume:
        return {"success": False, "error": "简历不存在"}
    if not slot:
        return {"success": False, "error": "时间段不存在"}
    if not slot.is_available or slot.booked_count >= slot.capacity:
        return {"success": False, "error": "该时间段已满"}

    resume.interview_slot_id = slot.id
    slot.booked_count += 1
    if slot.booked_count >= slot.capacity:
        slot.is_available = False

    result = advance_status(
        db, resume_id, "time_confirmed",
        f"确认面试时间: {slot.date} {slot.start_time}-{slot.end_time}",
        operator,
    )
    return result


def record_candidate_reply(
    db: Session,
    resume_id: int,
    reply_text: str,
) -> dict:
    """记录候选人的回复"""
    resume = db.query(Resume).get(resume_id)
    if not resume:
        return {"success": False, "error": "简历不存在"}

    resume.candidate_reply = reply_text
    resume.candidate_reply_time = datetime.utcnow()

    slot_choice = _parse_time_choice(reply_text)
    result = {"success": True, "reply": reply_text, "parsed_choice": slot_choice}

    if slot_choice is not None and resume.position_id:
        slots = (
            db.query(InterviewSlot)
            .filter(
                InterviewSlot.position_id == resume.position_id,
                InterviewSlot.is_available == True,
            )
            .order_by(InterviewSlot.date, InterviewSlot.start_time)
            .all()
        )
        if 0 < slot_choice <= len(slots):
            chosen = slots[slot_choice - 1]
            assign_result = assign_interview_slot(db, resume_id, chosen.id)
            result["slot_assigned"] = assign_result
        else:
            result["note"] = f"候选人选择了 {slot_choice}，但没有对应时间段"

    db.commit()
    return result


def get_pipeline_summary(db: Session, position_id: int = None) -> dict:
    """获取流程各阶段的简历数量"""
    query = db.query(Resume)
    if position_id:
        query = query.filter(Resume.position_id == position_id)

    all_resumes = query.all()
    summary = {}
    for status in ResumeStatus:
        val = status.value
        count = sum(1 for r in all_resumes
                    if (r.status if isinstance(r.status, str) else r.status.value) == val)
        summary[val] = count

    return summary


def get_pipeline_resumes(db: Session, status: str, position_id: int = None) -> list:
    """获取某个流程阶段的所有简历"""
    query = db.query(Resume).filter(Resume.status == status)
    if position_id:
        query = query.filter(Resume.position_id == position_id)
    return query.order_by(Resume.jd_match_score.desc().nullslast()).all()


def get_resume_timeline(db: Session, resume_id: int) -> list[dict]:
    """获取简历的流程时间线"""
    logs = (
        db.query(PipelineLog)
        .filter(PipelineLog.resume_id == resume_id)
        .order_by(PipelineLog.created_at)
        .all()
    )
    return [
        {
            "id": log.id,
            "from": log.from_status,
            "to": log.to_status,
            "action": log.action,
            "detail": log.detail,
            "operator": log.operator,
            "time": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


def _parse_time_choice(text: str) -> Optional[int]:
    """解析候选人回复中的时间选择编号"""
    import re
    number_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

    match = re.search(r"选?\s*(\d+)", text)
    if match:
        return int(match.group(1))

    for cn, num in number_map.items():
        if f"选{cn}" in text or f"第{cn}" in text or f"方案{cn}" in text:
            return num

    return None
