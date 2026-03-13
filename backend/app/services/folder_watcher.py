"""
文件夹监控服务
监控 uploads/inbox 文件夹，新增简历文件自动解析入库。
"""
from __future__ import annotations

import shutil
import logging
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import FOLDER_WATCH_DIR, ARCHIVE_DIR
from ..models import Resume, ResumeSource, ResumeStatus, OperationLog
from .resume_parser import parse_resume_file

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


def scan_folder(db: Session) -> list[dict]:
    """扫描 inbox 文件夹，解析新文件并入库"""
    results = []
    if not FOLDER_WATCH_DIR.exists():
        return results

    for file_path in FOLDER_WATCH_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                result = _import_file(db, file_path)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"处理文件失败 {file_path.name}: {e}")

    return results


def import_uploaded_file(db: Session, file_path: str, original_filename: str) -> dict:
    """处理通过 API 上传的文件"""
    parsed = parse_resume_file(file_path)

    resume = Resume(
        candidate_name=parsed.get("candidate_name") or Path(original_filename).stem,
        phone=parsed.get("phone"),
        email=parsed.get("email"),
        gender=parsed.get("gender"),
        age=parsed.get("age"),
        education=parsed.get("education"),
        school=parsed.get("school"),
        major=parsed.get("major"),
        work_years=parsed.get("work_years"),
        current_company=parsed.get("current_company"),
        current_position=parsed.get("current_position"),
        city=parsed.get("city"),
        expected_salary_min=parsed.get("expected_salary_min"),
        expected_salary_max=parsed.get("expected_salary_max"),
        skills=parsed.get("skills", []),
        raw_text=parsed.get("raw_text"),
        file_path=file_path,
        source=ResumeSource.MANUAL_UPLOAD,
        status=ResumeStatus.PENDING,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    db.add(OperationLog(
        action="resume_uploaded",
        target_type="resume",
        target_id=resume.id,
        detail=f"手动上传简历: {original_filename}",
        operator="user",
    ))
    db.commit()

    return {"id": resume.id, "name": resume.candidate_name, "source": "upload"}


def _import_file(db: Session, file_path: Path) -> dict | None:
    parsed = parse_resume_file(str(file_path))

    name = parsed.get("candidate_name") or file_path.stem
    phone = parsed.get("phone")

    if name and phone:
        existing = db.query(Resume).filter(
            Resume.candidate_name == name,
            Resume.phone == phone,
        ).first()
        if existing:
            logger.info(f"跳过重复简历: {name}")
            _archive_file(file_path)
            return None

    archive_path = _archive_file(file_path)

    resume = Resume(
        candidate_name=name,
        phone=phone,
        email=parsed.get("email"),
        gender=parsed.get("gender"),
        age=parsed.get("age"),
        education=parsed.get("education"),
        school=parsed.get("school"),
        major=parsed.get("major"),
        work_years=parsed.get("work_years"),
        current_company=parsed.get("current_company"),
        current_position=parsed.get("current_position"),
        city=parsed.get("city"),
        expected_salary_min=parsed.get("expected_salary_min"),
        expected_salary_max=parsed.get("expected_salary_max"),
        skills=parsed.get("skills", []),
        raw_text=parsed.get("raw_text"),
        file_path=str(archive_path),
        source=ResumeSource.FOLDER_IMPORT,
        status=ResumeStatus.PENDING,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    db.add(OperationLog(
        action="resume_imported",
        target_type="resume",
        target_id=resume.id,
        detail=f"从文件夹导入: {file_path.name}",
        operator="folder_watcher",
    ))
    db.commit()

    logger.info(f"文件夹导入简历: {resume.candidate_name} (ID: {resume.id})")
    return {"id": resume.id, "name": resume.candidate_name, "source": "folder"}


def _archive_file(file_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{timestamp}_{file_path.name}"
    archive_path = ARCHIVE_DIR / archive_name
    shutil.move(str(file_path), str(archive_path))
    return archive_path
