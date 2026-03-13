from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Resume, ScreeningLog
from ..services.screener import screen_resume, batch_screen

router = APIRouter(prefix="/screening", tags=["简历筛选"])


@router.post("/{resume_id}")
def screen_single(resume_id: int, position_id: int, db: Session = Depends(get_db)):
    resume = db.query(Resume).get(resume_id)
    if not resume:
        raise HTTPException(404, "简历不存在")
    result = screen_resume(db, resume, position_id)
    return result


@router.post("/batch")
def screen_batch(resume_ids: list[int], position_id: int, db: Session = Depends(get_db)):
    results = batch_screen(db, resume_ids, position_id)
    return {"results": results}


@router.get("/logs/{resume_id}")
def get_screening_logs(resume_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(ScreeningLog)
        .filter(ScreeningLog.resume_id == resume_id)
        .order_by(ScreeningLog.created_at.desc())
        .all()
    )
    return [
        {
            "id": log.id,
            "rule_name": log.rule_name,
            "field": log.field,
            "expected": log.expected_value,
            "actual": log.actual_value,
            "passed": log.passed,
            "score": log.score,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
