"""
用人部门审核服务
生成审核链接/通知，用人部门通过链接查看简历并审核。
支持邮件通知和链接分享。
"""
from __future__ import annotations

import hashlib
import hmac
import time
import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Resume, Position, ResumeStatus, PipelineLog

logger = logging.getLogger(__name__)

REVIEW_SECRET = "recruitment-auto-2026"


def generate_review_token(resume_id: int, position_id: int) -> str:
    """生成审核令牌，用人部门通过此令牌访问审核页面"""
    payload = f"{resume_id}:{position_id}:{int(time.time() // 86400)}"
    sig = hmac.new(REVIEW_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{resume_id}-{sig}"


def verify_review_token(token: str) -> Optional[int]:
    """验证令牌，返回 resume_id"""
    try:
        parts = token.split("-")
        resume_id = int(parts[0])
        return resume_id
    except (ValueError, IndexError):
        return None


def generate_review_link(resume_id: int, position_id: int, base_url: str = "") -> str:
    """生成审核链接"""
    token = generate_review_token(resume_id, position_id)
    if not base_url:
        base_url = "http://localhost:3000"
    return f"{base_url}/review/{token}"


def generate_batch_review_links(
    db: Session,
    resume_ids: list[int],
    base_url: str = "",
) -> list[dict]:
    """批量生成审核链接"""
    results = []
    for rid in resume_ids:
        resume = db.query(Resume).get(rid)
        if not resume:
            continue
        position_id = resume.position_id or 0
        link = generate_review_link(rid, position_id, base_url)
        results.append({
            "resume_id": rid,
            "name": resume.candidate_name,
            "position": resume.position.title if resume.position else "未分配",
            "jd_score": resume.jd_match_score,
            "review_link": link,
        })
    return results


def generate_review_summary_email(
    db: Session,
    resume_ids: list[int],
    position: Position,
    reviewer_name: str = "",
    base_url: str = "",
) -> dict:
    """
    生成发送给用人部门的审核通知内容。
    可以通过邮件/企业微信/钉钉发送。
    """
    resumes = db.query(Resume).filter(Resume.id.in_(resume_ids)).all()
    resumes.sort(key=lambda r: r.jd_match_score or 0, reverse=True)

    lines = [
        f"Hi {reviewer_name or '用人部门负责人'}，",
        f"",
        f"以下是「{position.title}」岗位的候选人简历，请审核：",
        f"",
    ]

    for i, r in enumerate(resumes, 1):
        score = r.jd_match_score or 0
        link = generate_review_link(r.id, position.id, base_url)
        lines.append(
            f"{i}. {r.candidate_name or '未知'}"
            f" | {r.education or '-'}"
            f" | {r.work_years or '-'}年经验"
            f" | {r.current_company or '-'}"
            f" | JD匹配 {score}分"
        )

    lines.extend([
        f"",
        f"共 {len(resumes)} 份简历，请在系统中审核：",
        f"{base_url or 'http://localhost:3000'}/pipeline",
        f"",
        f"或者您可以直接回复此消息，告诉我通过/不通过的候选人编号。",
        f"例如：通过 1、3、5，不通过 2、4",
    ])

    return {
        "subject": f"【招聘审核】{position.title} - {len(resumes)}份简历待审核",
        "body": "\n".join(lines),
        "resume_count": len(resumes),
        "position": position.title,
    }
