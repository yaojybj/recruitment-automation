"""
邮件监听服务
定时连接 IMAP 邮箱，拉取 Boss 直聘简历通知邮件，
解析后自动入库到简历池。
"""
from __future__ import annotations

import imaplib
import email
from email.header import decode_header
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Resume, EmailConfig, ResumeSource, ResumeStatus, OperationLog
from .resume_parser import parse_boss_email

logger = logging.getLogger(__name__)


def check_email_for_resumes(db: Session) -> list[dict]:
    """检查所有活跃邮箱配置，拉取新简历"""
    configs = db.query(EmailConfig).filter(EmailConfig.is_active == True).all()
    all_results = []
    for config in configs:
        try:
            results = _fetch_from_mailbox(db, config)
            all_results.extend(results)
            config.last_check_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            logger.error(f"邮箱 {config.email_address} 检查失败: {e}")
    return all_results


def _fetch_from_mailbox(db: Session, config: EmailConfig) -> list[dict]:
    results = []
    mail = None
    try:
        if config.use_ssl:
            mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
        else:
            mail = imaplib.IMAP4(config.imap_server, config.imap_port)

        mail.login(config.email_address, config.password)
        mail.select("INBOX")

        search_criteria = f'(UNSEEN FROM "{config.sender_filter}")'
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
    from_addr = _decode_header_value(msg["From"])

    body = _get_email_body(msg)
    if not body:
        return None

    parsed = parse_boss_email(subject, body)

    if _is_duplicate(db, parsed):
        logger.info(f"跳过重复简历: {parsed.get('candidate_name')}")
        return None

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
        raw_text=parsed.get("raw_text"),
        source=ResumeSource.EMAIL,
        status=ResumeStatus.PENDING,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    db.add(OperationLog(
        action="resume_imported",
        target_type="resume",
        target_id=resume.id,
        detail=f"从邮件导入简历: {resume.candidate_name}, 来源: {from_addr}",
        operator="email_monitor",
    ))
    db.commit()

    logger.info(f"成功导入简历: {resume.candidate_name} (ID: {resume.id})")
    return {"id": resume.id, "name": resume.candidate_name, "source": "email"}


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
    phone = parsed.get("phone")
    if name and phone:
        existing = db.query(Resume).filter(
            Resume.candidate_name == name,
            Resume.phone == phone,
        ).first()
        return existing is not None
    return False
