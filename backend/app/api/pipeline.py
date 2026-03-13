from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Resume, Position, InterviewSlot, ResumeStatus
from ..services.pipeline import (
    advance_status, recommend_to_dept, dept_review,
    assign_interview_slot, get_pipeline_summary, get_pipeline_resumes,
    get_resume_timeline,
)
from ..services.jd_matcher import match_resume_to_position, batch_match, auto_match_new_resumes
from ..services.boss_adapter import (
    generate_interview_message, mark_message_sent,
    submit_candidate_reply, get_pending_contacts, get_awaiting_replies,
)
from ..services.dept_review import generate_batch_review_links, generate_review_summary_email
from ..services.moka_adapter import generate_moka_entry_guide

router = APIRouter(prefix="/pipeline", tags=["招聘流程"])


# ── JD 匹配 ──

class JDMatchRequest(BaseModel):
    position_id: int
    resume_ids: Optional[list[int]] = None


@router.post("/jd-match")
def jd_match(req: JDMatchRequest, db: Session = Depends(get_db)):
    results = batch_match(db, req.position_id, req.resume_ids)
    passed = sum(1 for r in results if r.get("passed"))
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }


@router.post("/jd-match/{resume_id}")
def jd_match_single(resume_id: int, position_id: int, db: Session = Depends(get_db)):
    resume = db.query(Resume).get(resume_id)
    position = db.query(Position).get(position_id)
    if not resume:
        raise HTTPException(404, "简历不存在")
    if not position:
        raise HTTPException(404, "岗位不存在")
    result = match_resume_to_position(db, resume, position)
    return result


@router.post("/auto-match")
def trigger_auto_match(db: Session = Depends(get_db)):
    auto_match_new_resumes(db)
    return {"message": "自动匹配完成"}


# ── 流程推进 ──

class StatusAdvanceRequest(BaseModel):
    new_status: str
    detail: str = ""
    operator: str = "hr"


@router.post("/advance/{resume_id}")
def advance(resume_id: int, req: StatusAdvanceRequest, db: Session = Depends(get_db)):
    result = advance_status(db, resume_id, req.new_status, req.detail, req.operator)
    if not result["success"]:
        raise HTTPException(400, result["error"])
    return result


# ── 推荐给用人部门（系统内审核） ──

class RecommendRequest(BaseModel):
    resume_ids: list[int]


@router.post("/recommend")
def recommend(req: RecommendRequest, db: Session = Depends(get_db)):
    results = recommend_to_dept(db, req.resume_ids, "hr")
    return {"results": results}


class NotifyDeptRequest(BaseModel):
    resume_ids: list[int]
    reviewer_name: str = ""
    base_url: str = ""


@router.post("/notify-dept")
def notify_dept(req: NotifyDeptRequest, db: Session = Depends(get_db)):
    """生成发给用人部门的审核通知内容（用于邮件/企微/钉钉发送）"""
    if not req.resume_ids:
        raise HTTPException(400, "请选择简历")

    first_resume = db.query(Resume).get(req.resume_ids[0])
    if not first_resume or not first_resume.position:
        raise HTTPException(400, "简历未关联岗位")

    position = first_resume.position
    email_content = generate_review_summary_email(
        db, req.resume_ids, position, req.reviewer_name, req.base_url
    )
    review_links = generate_batch_review_links(db, req.resume_ids, req.base_url)

    return {
        "email": email_content,
        "review_links": review_links,
    }


# ── 用人部门审核 ──

class DeptReviewRequest(BaseModel):
    approved: bool
    reviewer: str = ""
    comment: str = ""


@router.post("/dept-review/{resume_id}")
def review(resume_id: int, req: DeptReviewRequest, db: Session = Depends(get_db)):
    result = dept_review(db, resume_id, req.approved, req.reviewer, req.comment)
    if not result["success"]:
        raise HTTPException(400, result["error"])
    return result


class BatchReviewRequest(BaseModel):
    resume_ids: list[int]
    approved: bool
    reviewer: str = ""


@router.post("/dept-review-batch")
def review_batch(req: BatchReviewRequest, db: Session = Depends(get_db)):
    results = []
    for rid in req.resume_ids:
        r = dept_review(db, rid, req.approved, req.reviewer)
        results.append({"resume_id": rid, **r})
    return results


# ── Boss 直聘操作 ──

@router.get("/pending-contacts")
def pending_contacts(position_id: int = None, db: Session = Depends(get_db)):
    return get_pending_contacts(db, position_id)


@router.post("/generate-message/{resume_id}")
def gen_message(resume_id: int, db: Session = Depends(get_db)):
    resume = db.query(Resume).get(resume_id)
    if not resume or not resume.position:
        raise HTTPException(400, "简历不存在或未关联岗位")
    result = generate_interview_message(db, resume, resume.position)
    if not result["success"]:
        raise HTTPException(400, result["error"])

    current = resume.status if isinstance(resume.status, str) else resume.status.value
    if current == "dept_approved":
        advance_status(db, resume_id, "contacting", "开始联系候选人", "hr")

    return result


@router.post("/message-sent/{resume_id}")
def msg_sent(resume_id: int, db: Session = Depends(get_db)):
    result = mark_message_sent(db, resume_id)
    if not result["success"]:
        raise HTTPException(400, result["error"])
    return result


@router.get("/awaiting-replies")
def awaiting_replies(position_id: int = None, db: Session = Depends(get_db)):
    return get_awaiting_replies(db, position_id)


class CandidateReplyRequest(BaseModel):
    reply_text: str


@router.post("/candidate-reply/{resume_id}")
def candidate_reply(resume_id: int, req: CandidateReplyRequest, db: Session = Depends(get_db)):
    result = submit_candidate_reply(db, resume_id, req.reply_text)
    return result


# ── 面试安排（系统内 + Moka 手动指引） ──

@router.post("/schedule-interview/{resume_id}")
def schedule_interview(resume_id: int, db: Session = Depends(get_db)):
    resume = db.query(Resume).get(resume_id)
    if not resume:
        raise HTTPException(404, "简历不存在")
    if not resume.interview_slot:
        raise HTTPException(400, "候选人尚未确认面试时间")
    if not resume.position:
        raise HTTPException(400, "简历未关联岗位")

    slot = resume.interview_slot

    moka_guide = generate_moka_entry_guide(db, resume, resume.position, slot)

    result = advance_status(
        db, resume_id, "interview_scheduled",
        f"面试已安排: {slot.date} {slot.start_time}-{slot.end_time}",
        "system",
    )
    return {
        "pipeline": result,
        "moka_guide": moka_guide,
    }


@router.get("/moka-guide/{resume_id}")
def get_moka_guide(resume_id: int, db: Session = Depends(get_db)):
    """获取某个候选人的 Moka 录入指引"""
    resume = db.query(Resume).get(resume_id)
    if not resume or not resume.position:
        raise HTTPException(400, "简历不存在或未关联岗位")
    guide = generate_moka_entry_guide(db, resume, resume.position, resume.interview_slot)
    return guide


# ── 流程看板 ──

@router.get("/summary")
def pipeline_summary(position_id: int = None, db: Session = Depends(get_db)):
    return get_pipeline_summary(db, position_id)


@router.get("/by-status/{status}")
def by_status(status: str, position_id: int = None, db: Session = Depends(get_db)):
    resumes = get_pipeline_resumes(db, status, position_id)
    return [
        {
            "id": r.id,
            "name": r.candidate_name,
            "phone": r.phone,
            "education": r.education,
            "work_years": r.work_years,
            "current_company": r.current_company,
            "jd_match_score": r.jd_match_score,
            "position_title": r.position.title if r.position else None,
            "status": r.status if isinstance(r.status, str) else r.status.value,
            "candidate_reply": r.candidate_reply,
            "interview_time": (
                f"{r.interview_slot.date} {r.interview_slot.start_time}-{r.interview_slot.end_time}"
                if r.interview_slot else None
            ),
        }
        for r in resumes
    ]


@router.get("/timeline/{resume_id}")
def timeline(resume_id: int, db: Session = Depends(get_db)):
    return get_resume_timeline(db, resume_id)
