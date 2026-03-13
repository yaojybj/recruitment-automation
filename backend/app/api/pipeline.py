from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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
from ..services.moka_adapter import get_moka_adapter

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


# ── 推荐给用人部门 ──

class RecommendRequest(BaseModel):
    resume_ids: list[int]


@router.post("/recommend")
def recommend(req: RecommendRequest, db: Session = Depends(get_db)):
    results = recommend_to_dept(db, req.resume_ids, "hr")
    moka = get_moka_adapter(db)
    moka_results = []
    if moka:
        for r in results:
            if r.get("success"):
                resume = db.query(Resume).get(r["resume_id"])
                if resume and resume.position:
                    mr = moka.recommend_candidate(resume, resume.position)
                    moka_results.append({"resume_id": r["resume_id"], **mr})
                    if mr.get("moka_candidate_id"):
                        resume.moka_candidate_id = mr["moka_candidate_id"]
                        resume.moka_application_id = mr.get("moka_application_id")
                        db.commit()
    return {"pipeline_results": results, "moka_results": moka_results}


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


@router.post("/dept-review-batch")
def review_batch(
    resume_ids: list[int],
    approved: bool,
    reviewer: str = "",
    db: Session = Depends(get_db),
):
    results = []
    for rid in resume_ids:
        r = dept_review(db, rid, approved, reviewer)
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


# ── 面试安排 ──

@router.post("/schedule-interview/{resume_id}")
def schedule_interview(resume_id: int, db: Session = Depends(get_db)):
    """在 Moka 上安排面试"""
    resume = db.query(Resume).get(resume_id)
    if not resume:
        raise HTTPException(404, "简历不存在")
    if not resume.interview_slot:
        raise HTTPException(400, "候选人尚未确认面试时间")
    if not resume.position:
        raise HTTPException(400, "简历未关联岗位")

    slot = resume.interview_slot
    moka = get_moka_adapter(db)
    moka_result = {}
    if moka:
        moka_result = moka.create_interview(
            resume=resume,
            position=resume.position,
            interview_date=slot.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            interviewer_email=slot.interviewer_email or "",
            location=slot.location or "",
            meeting_link=slot.meeting_link or "",
        )

    result = advance_status(
        db, resume_id, "interview_scheduled",
        f"面试已安排: {slot.date} {slot.start_time}-{slot.end_time}",
        "system",
    )
    return {"pipeline": result, "moka": moka_result}


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
