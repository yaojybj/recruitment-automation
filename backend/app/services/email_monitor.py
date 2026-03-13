"""
邮件监听服务
定时连接 IMAP 邮箱，拉取 Boss 直聘简历通知邮件，
下载附件简历（PDF/Word），解析后自动入库，并根据岗位名自动关联。
"""
from __future__ import annotations

import imaplib
import email
import os
import uuid
from email.header import decode_header
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Resume, Position, EmailConfig, OperationLog, PipelineLog
from ..config import UPLOAD_DIR
from .resume_parser import (
    parse_boss_email, parse_resume_file, is_boss_resume_email,
)

logger = logging.getLogger(__name__)

RESUME_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


def check_email_for_resumes(db: Session, include_read: bool = False) -> list[dict]:
    configs = db.query(EmailConfig).filter(EmailConfig.is_active == True).all()
    all_results = []
    for config in configs:
        try:
            results = _fetch_from_mailbox(db, config, include_read=include_read)
            all_results.extend(results)
            config.last_check_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            logger.error(f"邮箱 {config.email_address} 检查失败: {e}")
    return all_results


def _fetch_from_mailbox(db: Session, config: EmailConfig, include_read: bool = False) -> list[dict]:
    results = []
    mail = None
    try:
        if config.use_ssl:
            mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
        else:
            mail = imaplib.IMAP4(config.imap_server, config.imap_port)

        mail.login(config.email_address, config.password)
        mail.select("INBOX")

        search_criteria = "ALL" if include_read else "UNSEEN"
        status, message_ids = mail.search(None, search_criteria)

        if status != "OK" or not message_ids[0]:
            return results

        for msg_id in message_ids[0].split():
            try:
                result = _process_email_message(db, mail, msg_id)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"处理邮件 {msg_id} 失败: {e}")

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP 连接失败: {e}")
        raise
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass

    return results


def _process_email_message(db: Session, mail: imaplib.IMAP4, msg_id: bytes) -> Optional[dict]:
    status, msg_data = mail.fetch(msg_id, "(RFC822)")
    if status != "OK":
        return None

    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    subject = _decode_header_value(msg["Subject"])

    if not is_boss_resume_email(subject):
        return None

    # 从邮件主题提取基本信息（姓名、岗位、城市等）
    body = _get_email_body(msg)
    parsed = parse_boss_email(subject, body or "")

    if _is_duplicate(db, parsed):
        logger.info(f"跳过重复简历: {parsed.get('candidate_name')}")
        return None

    # 下载并解析附件简历
    attachment_data, file_path = _extract_attachment(msg)
    if attachment_data:
        for key, val in attachment_data.items():
            if val and not parsed.get(key):
                parsed[key] = val
        if attachment_data.get("skills"):
            existing = parsed.get("skills", [])
            merged = list(dict.fromkeys(existing + attachment_data["skills"]))
            parsed["skills"] = merged

    # 自动关联岗位
    position_id = _auto_match_position(db, parsed)

    resume = Resume(
        candidate_name=parsed.get("candidate_name"),
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
        work_experience=parsed.get("work_experience", []),
        project_experience=parsed.get("project_experience", []),
        education_history=parsed.get("education_history", []),
        raw_text=parsed.get("raw_text"),
        file_path=file_path,
        source="email",
        status="pending",
        pipeline_status="pending",
        position_id=position_id,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    position_name = ""
    if position_id:
        pos = db.query(Position).get(position_id)
        position_name = f", 关联岗位: {pos.title}" if pos else ""

    db.add(PipelineLog(
        resume_id=resume.id,
        from_status=None,
        to_status="pending",
        action="email_import",
        detail=f"邮件导入: {resume.candidate_name}{position_name}",
        operator="email_monitor",
    ))
    db.add(OperationLog(
        action="resume_imported",
        target_type="resume",
        target_id=resume.id,
        detail=f"邮件导入: {resume.candidate_name}, 附件: {'有' if file_path else '无'}{position_name}",
        operator="email_monitor",
    ))
    db.commit()

    logger.info(f"导入简历: {resume.candidate_name} (ID:{resume.id}, 附件:{bool(file_path)}{position_name})")
    return {
        "id": resume.id,
        "name": resume.candidate_name,
        "source": "email",
        "has_attachment": bool(file_path),
        "position": position_name.replace(", 关联岗位: ", "") if position_name else None,
    }


def _extract_attachment(msg: email.message.Message) -> tuple[Optional[dict], Optional[str]]:
    """下载邮件附件（PDF/Word），保存到本地并解析内容"""
    if not msg.is_multipart():
        return None, None

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition") or "")
        if "attachment" not in content_disposition:
            continue

        filename = _decode_header_value(part.get_filename() or "")
        if not filename:
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext not in RESUME_EXTENSIONS:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        save_name = f"{uuid.uuid4().hex}{ext}"
        save_path = str(UPLOAD_DIR / save_name)

        with open(save_path, "wb") as f:
            f.write(payload)

        logger.info(f"保存附件: {filename} -> {save_name}")

        try:
            parsed = parse_resume_file(save_path)
            return parsed, save_path
        except Exception as e:
            logger.error(f"解析附件失败 {filename}: {e}")
            return None, save_path

    return None, None


def _auto_match_position(db: Session, parsed: dict) -> Optional[int]:
    """根据邮件中的岗位名自动匹配系统中的职位"""
    applied = parsed.get("applied_position", "")
    if not applied:
        return None

    applied_clean = re.sub(r"\s*\([^)]*\)\s*", "", applied).strip()

    positions = db.query(Position).filter(Position.is_active == True).all()
    for pos in positions:
        if pos.title == applied_clean:
            return pos.id
        if applied_clean in pos.title or pos.title in applied_clean:
            return pos.id

    for pos in positions:
        pos_words = set(re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", pos.title.lower()))
        applied_words = set(re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", applied_clean.lower()))
        if pos_words and applied_words:
            overlap = pos_words & applied_words
            if len(overlap) >= len(pos_words) * 0.5:
                return pos.id

    return None


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="ignore"))
        else:
            result.append(part)
    return " ".join(result)


def _get_email_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in content_disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore")
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="ignore")
                return _html_to_text(html)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="ignore")
    return ""


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_duplicate(db: Session, parsed: dict) -> bool:
    name = parsed.get("candidate_name")
    if not name:
        return False
    phone = parsed.get("phone")
    if name and phone:
        existing = db.query(Resume).filter(
            Resume.candidate_name == name,
            Resume.phone == phone,
        ).first()
        return existing is not None
    if name:
        existing = db.query(Resume).filter(
            Resume.candidate_name == name,
            Resume.source == "email",
        ).first()
        return existing is not None
    return False
