from __future__ import annotations

import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..database import get_db
from ..config import UPLOAD_DIR
from ..models import Resume, Position, ResumeStatus, OperationLog
from ..schemas import ResumeOut, ResumeUpdate, ResumeBatchAction, PaginatedResponse
from ..services.folder_watcher import import_uploaded_file

router = APIRouter(prefix="/resumes", tags=["简历管理"])

STATUS_LABELS = {s.value: s.value for s in ResumeStatus}


@router.get("")
def list_resumes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    position_id: int = None,
    keyword: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    query = db.query(Resume)

    if status:
        query = query.filter(Resume.status == status)
    if position_id:
        query = query.filter(Resume.position_id == position_id)
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(or_(
            Resume.candidate_name.like(kw),
            Resume.phone.like(kw),
            Resume.email.like(kw),
            Resume.current_company.like(kw),
            Resume.current_position.like(kw),
            Resume.school.like(kw),
            Resume.raw_text.like(kw),
        ))

    total = query.count()
    sort_col = getattr(Resume, sort_by, Resume.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    items = query.offset((page - 1) * page_size).limit(page_size).all()

    result_items = []
    for r in items:
        out = ResumeOut.model_validate(r)
        if r.position:
            out.position_title = r.position.title
        result_items.append(out)

    total_pages = (total + page_size - 1) // page_size
    return PaginatedResponse(
        items=[item.model_dump() for item in result_items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats")
def resume_stats(db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    total = db.query(func.count(Resume.id)).scalar()
    by_status = {}
    for s in ResumeStatus:
        count = db.query(func.count(Resume.id)).filter(Resume.status == s.value).scalar()
        by_status[s.value] = count

    today_new = db.query(func.count(Resume.id)).filter(Resume.created_at >= today).scalar()
    week_new = db.query(func.count(Resume.id)).filter(Resume.created_at >= week_ago).scalar()

    return {
        "total": total,
        "by_status": by_status,
        "today_new": today_new,
        "week_new": week_new,
    }


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).get(resume_id)
    if not r:
        raise HTTPException(404, "简历不存在")
    out = ResumeOut.model_validate(r)
    if r.position:
        out.position_title = r.position.title
    return out


@router.put("/{resume_id}", response_model=ResumeOut)
def update_resume(resume_id: int, data: ResumeUpdate, db: Session = Depends(get_db)):
    r = db.query(Resume).get(resume_id)
    if not r:
        raise HTTPException(404, "简历不存在")
    updates = data.model_dump(exclude_unset=True)
    for key, val in updates.items():
        setattr(r, key, val)
    db.commit()
    db.refresh(r)

    db.add(OperationLog(
        action="resume_updated",
        target_type="resume",
        target_id=r.id,
        detail=f"更新字段: {list(updates.keys())}",
        operator="user",
    ))
    db.commit()

    out = ResumeOut.model_validate(r)
    if r.position:
        out.position_title = r.position.title
    return out


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).get(resume_id)
    if not r:
        raise HTTPException(404, "简历不存在")
    db.delete(r)
    db.commit()
    return {"message": "已删除"}


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(400, "未选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".pdf", ".docx", ".doc", ".txt"}:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = str(UPLOAD_DIR / save_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    result = import_uploaded_file(db, save_path, file.filename)
    return {"message": "上传成功", **result}


@router.post("/upload-batch")
async def upload_resumes_batch(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    results = []
    for file in files:
        if not file.filename:
            continue
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in {".pdf", ".docx", ".doc", ".txt"}:
            results.append({"filename": file.filename, "error": f"不支持的格式: {ext}"})
            continue
        save_name = f"{uuid.uuid4().hex}{ext}"
        save_path = str(UPLOAD_DIR / save_name)
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
        try:
            result = import_uploaded_file(db, save_path, file.filename)
            results.append({"filename": file.filename, **result})
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
    return {"message": f"处理完成: {len(results)} 个文件", "results": results}


@router.post("/batch-action")
def batch_action(data: ResumeBatchAction, db: Session = Depends(get_db)):
    resumes = db.query(Resume).filter(Resume.id.in_(data.resume_ids)).all()
    if not resumes:
        raise HTTPException(404, "未找到简历")

    if data.action == "pass":
        for r in resumes:
            r.status = ResumeStatus.PASSED
    elif data.action == "reject":
        for r in resumes:
            r.status = ResumeStatus.REJECTED
            if data.reason:
                r.remark = data.reason
    elif data.action == "assign_position":
        if not data.position_id:
            raise HTTPException(400, "请指定岗位")
        for r in resumes:
            r.position_id = data.position_id
    elif data.action == "interview":
        for r in resumes:
            r.status = ResumeStatus.INTERVIEW
    elif data.action == "screen":
        if not data.position_id:
            raise HTTPException(400, "请指定岗位进行筛选")
        from ..services.screener import batch_screen
        results = batch_screen(db, data.resume_ids, data.position_id)
        return {"message": "筛选完成", "results": results}
    else:
        raise HTTPException(400, f"不支持的操作: {data.action}")

    db.commit()

    db.add(OperationLog(
        action=f"batch_{data.action}",
        target_type="resume",
        detail=f"批量操作 {len(resumes)} 份简历: {data.action}",
        operator="user",
    ))
    db.commit()

    return {"message": f"操作成功: {len(resumes)} 份简历"}
