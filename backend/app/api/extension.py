from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Resume, Position, ResumeStatus, OperationLog, PipelineLog,
    ExtensionTask, InterviewSlot,
)
from ..services.pipeline import advance_status

router = APIRouter(prefix="/extension", tags=["Chrome 插件"])


# ══════════════════════════════════════
#  候选人导入（Boss 直聘插件用）
# ══════════════════════════════════════

class ImportCandidateRequest(BaseModel):
    candidate_name: str
    education: Optional[str] = None
    work_years: Optional[float] = None
    city: Optional[str] = None
    age: Optional[int] = None
    current_company: Optional[str] = None
    current_position: Optional[str] = None
    skills: list = []
    boss_candidate_id: Optional[str] = None
    source: str = "boss_extension"
    position_id: Optional[int] = None
    raw_text: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


@router.post("/import-candidate")
def import_candidate(req: ImportCandidateRequest, db: Session = Depends(get_db)):
    if req.boss_candidate_id:
        existing = db.query(Resume).filter(
            Resume.boss_candidate_id == req.boss_candidate_id
        ).first()
        if existing:
            return {
                "resume_id": existing.id,
                "status": "already_exists",
                "message": f"候选人 {existing.candidate_name} 已存在",
            }

    existing_by_name = db.query(Resume).filter(
        Resume.candidate_name == req.candidate_name,
        Resume.current_company == req.current_company,
    ).first()
    if existing_by_name:
        return {
            "resume_id": existing_by_name.id,
            "status": "already_exists",
            "message": f"候选人 {existing_by_name.candidate_name} 已存在",
        }

    if req.position_id:
        position = db.query(Position).get(req.position_id)
        if not position:
            raise HTTPException(400, f"岗位 ID {req.position_id} 不存在")

    resume = Resume(
        candidate_name=req.candidate_name,
        education=req.education,
        work_years=req.work_years,
        city=req.city,
        age=req.age,
        current_company=req.current_company,
        current_position=req.current_position,
        skills=req.skills,
        phone=req.phone,
        email=req.email,
        boss_candidate_id=req.boss_candidate_id,
        source=req.source,
        raw_text=req.raw_text,
        position_id=req.position_id,
        status=ResumeStatus.PENDING,
        pipeline_status="pending",
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    db.add(PipelineLog(
        resume_id=resume.id, from_status=None, to_status="pending",
        action="extension_import",
        detail=f"Boss直聘插件导入: {req.candidate_name}",
        operator="extension",
    ))
    db.commit()

    return {
        "resume_id": resume.id,
        "status": "created",
        "message": f"候选人 {req.candidate_name} 导入成功",
    }


@router.get("/search")
def search_candidate(name: str = None, boss_id: str = None, db: Session = Depends(get_db)):
    if boss_id:
        resume = db.query(Resume).filter(Resume.boss_candidate_id == boss_id).first()
    elif name:
        resume = db.query(Resume).filter(Resume.candidate_name == name).first()
    else:
        raise HTTPException(400, "请提供 name 或 boss_id")

    if not resume:
        return {"found": False}

    return {
        "found": True,
        "resume_id": resume.id,
        "name": resume.candidate_name,
        "status": resume.status if isinstance(resume.status, str) else resume.status.value,
        "pipeline_status": resume.pipeline_status,
        "jd_match_score": resume.jd_match_score,
        "position_title": resume.position.title if resume.position else None,
    }


# ══════════════════════════════════════
#  任务队列（双插件轮询）
# ══════════════════════════════════════

@router.get("/pending-tasks")
def get_pending_tasks(
    platform: str = Query(..., description="boss 或 moka"),
    db: Session = Depends(get_db),
):
    """插件轮询：获取待执行的任务"""
    tasks = db.query(ExtensionTask).filter(
        ExtensionTask.platform == platform,
        ExtensionTask.status == "pending",
    ).order_by(ExtensionTask.created_at.asc()).limit(10).all()

    return [_task_to_dict(t, db) for t in tasks]


@router.post("/task-start/{task_id}")
def start_task(task_id: int, db: Session = Depends(get_db)):
    """插件开始执行任务"""
    task = db.query(ExtensionTask).get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    task.status = "running"
    task.started_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


class TaskCompleteRequest(BaseModel):
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/task-complete/{task_id}")
def complete_task(task_id: int, req: TaskCompleteRequest, db: Session = Depends(get_db)):
    """插件完成任务后回报"""
    task = db.query(ExtensionTask).get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    task.completed_at = datetime.utcnow()

    if req.success:
        task.status = "done"
        task.result = req.result or {}
        _on_task_success(db, task)
    else:
        task.retry_count += 1
        if task.retry_count >= task.max_retries:
            task.status = "failed"
            task.error = req.error
        else:
            task.status = "pending"
            task.error = req.error

    db.commit()
    return {"ok": True, "status": task.status}


# ══════════════════════════════════════
#  创建任务（由流程推进时自动触发）
# ══════════════════════════════════════

def create_task(
    db: Session,
    task_type: str,
    platform: str,
    resume_id: int = None,
    position_id: int = None,
    payload: dict = None,
) -> ExtensionTask:
    task = ExtensionTask(
        task_type=task_type,
        platform=platform,
        resume_id=resume_id,
        position_id=position_id,
        payload=payload or {},
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/create-boss-tasks")
def create_boss_tasks_for_approved(db: Session = Depends(get_db)):
    """为所有部门已通过的候选人创建 Boss 约面任务"""
    resumes = db.query(Resume).filter(Resume.pipeline_status == "dept_approved").all()
    created = 0
    for r in resumes:
        existing = db.query(ExtensionTask).filter(
            ExtensionTask.resume_id == r.id,
            ExtensionTask.task_type == "boss_send_message",
            ExtensionTask.status.in_(["pending", "running"]),
        ).first()
        if existing:
            continue

        if not r.position:
            continue

        slots = db.query(InterviewSlot).filter(
            InterviewSlot.position_id == r.position_id,
            InterviewSlot.is_available == True,
        ).order_by(InterviewSlot.date.asc()).limit(5).all()

        slot_texts = []
        for i, s in enumerate(slots, 1):
            loc = s.meeting_link if s.is_online else (s.location or "待定")
            slot_texts.append(f"{i}. {s.date} {s.start_time}-{s.end_time} ({'线上' if s.is_online else '线下'}: {loc})")

        message = (
            f"您好，我是HR，您投递的{r.position.title}岗位我们非常感兴趣，"
            f"想跟您约一个面试时间。以下是可选的面试时间：\n"
            + "\n".join(slot_texts) +
            "\n请回复您方便的时间编号即可，谢谢！"
        ) if slot_texts else None

        create_task(db, "boss_send_message", "boss",
                    resume_id=r.id, position_id=r.position_id,
                    payload={
                        "candidate_name": r.candidate_name,
                        "message": message,
                        "boss_candidate_id": r.boss_candidate_id,
                    })
        created += 1

    return {"created": created}


@router.post("/create-moka-tasks")
def create_moka_tasks_for_matched(db: Session = Depends(get_db)):
    """为所有 JD 匹配通过的候选人创建 Moka 推荐任务"""
    resumes = db.query(Resume).filter(Resume.pipeline_status == "jd_matched").all()
    created = 0
    for r in resumes:
        existing = db.query(ExtensionTask).filter(
            ExtensionTask.resume_id == r.id,
            ExtensionTask.task_type == "moka_create_candidate",
            ExtensionTask.status.in_(["pending", "running", "done"]),
        ).first()
        if existing:
            continue
        if not r.position:
            continue

        create_task(db, "moka_create_candidate", "moka",
                    resume_id=r.id, position_id=r.position_id,
                    payload={
                        "candidate_name": r.candidate_name,
                        "phone": r.phone,
                        "email": r.email,
                        "education": r.education,
                        "school": r.school,
                        "work_years": r.work_years,
                        "current_company": r.current_company,
                        "current_position": r.current_position,
                        "city": r.city,
                        "position_title": r.position.title,
                        "file_path": r.file_path,
                        "jd_match_score": r.jd_match_score,
                    })
        created += 1

    return {"created": created}


@router.post("/create-moka-interview-tasks")
def create_moka_interview_tasks(db: Session = Depends(get_db)):
    """为已确认面试时间的候选人创建 Moka 面试安排任务"""
    resumes = db.query(Resume).filter(Resume.pipeline_status == "time_confirmed").all()
    created = 0
    for r in resumes:
        existing = db.query(ExtensionTask).filter(
            ExtensionTask.resume_id == r.id,
            ExtensionTask.task_type == "moka_schedule_interview",
            ExtensionTask.status.in_(["pending", "running", "done"]),
        ).first()
        if existing:
            continue

        slot = r.interview_slot
        if not slot or not r.position:
            continue

        create_task(db, "moka_schedule_interview", "moka",
                    resume_id=r.id, position_id=r.position_id,
                    payload={
                        "candidate_name": r.candidate_name,
                        "position_title": r.position.title,
                        "date": slot.date,
                        "start_time": slot.start_time,
                        "end_time": slot.end_time,
                        "interviewer_name": slot.interviewer_name,
                        "interviewer_email": slot.interviewer_email,
                        "is_online": slot.is_online,
                        "meeting_link": slot.meeting_link,
                        "location": slot.location,
                    })
        created += 1

    return {"created": created}


# ══════════════════════════════════════
#  内部辅助
# ══════════════════════════════════════

def _task_to_dict(task: ExtensionTask, db: Session) -> dict:
    d = {
        "id": task.id,
        "task_type": task.task_type,
        "platform": task.platform,
        "resume_id": task.resume_id,
        "position_id": task.position_id,
        "payload": task.payload,
        "status": task.status,
        "retry_count": task.retry_count,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
    if task.resume:
        d["candidate_name"] = task.resume.candidate_name
    if task.position:
        d["position_title"] = task.position.title
    return d


def _on_task_success(db: Session, task: ExtensionTask):
    """任务成功后的流程推进"""
    if not task.resume_id:
        return

    if task.task_type == "moka_create_candidate":
        moka_id = (task.result or {}).get("moka_candidate_id")
        if moka_id:
            resume = db.query(Resume).get(task.resume_id)
            if resume:
                resume.moka_candidate_id = moka_id
        advance_status(db, task.resume_id, "recommended", "Moka插件自动推荐", "moka_extension")

    elif task.task_type == "boss_send_message":
        advance_status(db, task.resume_id, "time_sent", "Boss插件自动发送约面消息", "boss_extension")

    elif task.task_type == "boss_read_reply":
        reply_text = (task.result or {}).get("reply_text", "")
        if reply_text:
            resume = db.query(Resume).get(task.resume_id)
            if resume:
                resume.candidate_reply = reply_text
                resume.candidate_reply_time = datetime.utcnow()
            from ..services.boss_adapter import submit_candidate_reply
            submit_candidate_reply(db, task.resume_id, reply_text)

    elif task.task_type == "moka_schedule_interview":
        advance_status(db, task.resume_id, "interview_scheduled",
                       "Moka插件自动安排面试", "moka_extension")
