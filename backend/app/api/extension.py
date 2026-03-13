from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Resume, Position, ResumeStatus, OperationLog, PipelineLog

router = APIRouter(prefix="/extension", tags=["Chrome 插件"])


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
        resume_id=resume.id,
        from_status=None,
        to_status="pending",
        action="extension_import",
        detail=f"通过 Boss 直聘插件导入: {req.candidate_name}",
        operator="extension",
    ))
    db.add(OperationLog(
        action="extension_import",
        target_type="resume",
        target_id=resume.id,
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
    """插件查询候选人是否已在系统中"""
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


@router.post("/batch-import")
def batch_import(candidates: list[ImportCandidateRequest], db: Session = Depends(get_db)):
    """批量导入候选人"""
    results = []
    for req in candidates:
        try:
            result = import_candidate(req, db)
            results.append({"name": req.candidate_name, **result})
        except Exception as e:
            results.append({"name": req.candidate_name, "status": "error", "message": str(e)})
    return {
        "total": len(results),
        "created": sum(1 for r in results if r.get("status") == "created"),
        "existing": sum(1 for r in results if r.get("status") == "already_exists"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
        "results": results,
    }
