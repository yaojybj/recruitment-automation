from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date

from ..database import get_db
from ..models import Resume, Position, ResumeStatus, OperationLog

router = APIRouter(prefix="/dashboard", tags=["数据看板"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    total = db.query(func.count(Resume.id)).scalar()
    pending = db.query(func.count(Resume.id)).filter(Resume.status == ResumeStatus.PENDING).scalar()
    passed = db.query(func.count(Resume.id)).filter(Resume.status == ResumeStatus.PASSED).scalar()
    rejected = db.query(func.count(Resume.id)).filter(Resume.status == ResumeStatus.REJECTED).scalar()
    interview = db.query(func.count(Resume.id)).filter(Resume.status == ResumeStatus.INTERVIEW).scalar()
    active_positions = db.query(func.count(Position.id)).filter(Position.is_active == True).scalar()
    today_new = db.query(func.count(Resume.id)).filter(Resume.created_at >= today).scalar()
    week_new = db.query(func.count(Resume.id)).filter(Resume.created_at >= week_ago).scalar()

    return {
        "total_resumes": total,
        "pending_resumes": pending,
        "passed_resumes": passed,
        "rejected_resumes": rejected,
        "interview_resumes": interview,
        "active_positions": active_positions,
        "today_new_resumes": today_new,
        "this_week_new_resumes": week_new,
    }


@router.get("/trend")
def get_trend(days: int = 30, db: Session = Depends(get_db)):
    """最近 N 天的简历入池趋势"""
    start_date = datetime.utcnow() - timedelta(days=days)
    results = (
        db.query(
            cast(Resume.created_at, Date).label("date"),
            func.count(Resume.id).label("count"),
        )
        .filter(Resume.created_at >= start_date)
        .group_by(cast(Resume.created_at, Date))
        .order_by(cast(Resume.created_at, Date))
        .all()
    )
    return [{"date": str(r.date), "count": r.count} for r in results]


@router.get("/by-position")
def resumes_by_position(db: Session = Depends(get_db)):
    results = (
        db.query(
            Position.title,
            func.count(Resume.id).label("count"),
        )
        .join(Resume, Resume.position_id == Position.id)
        .group_by(Position.id)
        .all()
    )
    return [{"position": r.title, "count": r.count} for r in results]


@router.get("/by-source")
def resumes_by_source(db: Session = Depends(get_db)):
    results = (
        db.query(
            Resume.source,
            func.count(Resume.id).label("count"),
        )
        .group_by(Resume.source)
        .all()
    )
    source_labels = {"email": "邮件导入", "manual_upload": "手动上传", "folder_import": "文件夹导入"}
    return [{"source": source_labels.get(r.source, r.source), "count": r.count} for r in results]


@router.get("/recent-logs")
def recent_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = (
        db.query(OperationLog)
        .order_by(OperationLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "operator": log.operator,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
