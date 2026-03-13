"""
Moka 适配器
负责与 Moka 招聘系统对接：推荐简历给用人部门、创建面试安排。

实现方式预留两种：
1. API 对接（需要 Moka 开放 API 权限）
2. Webhook 通知（通过邮件/企业微信通知用人部门）
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import Resume, Position, MokaConfig, PipelineLog

logger = logging.getLogger(__name__)


class MokaAdapter:
    def __init__(self, config: MokaConfig):
        self.base_url = config.api_base_url or "https://api.mokahr.com"
        self.api_key = config.api_key
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self._token = None

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def recommend_candidate(
        self,
        resume: Resume,
        position: Position,
    ) -> dict:
        """
        推荐简历到 Moka。
        如果有 API 权限就走 API；没有就返回需要手动操作的提示。
        """
        if not self.api_key:
            return {
                "success": False,
                "method": "manual",
                "message": f"请手动在 Moka 中为「{position.title}」岗位添加候选人「{resume.candidate_name}」",
                "candidate_info": {
                    "name": resume.candidate_name,
                    "phone": resume.phone,
                    "email": resume.email,
                    "position": position.title,
                    "jd_match_score": resume.jd_match_score,
                },
            }

        try:
            payload = {
                "name": resume.candidate_name,
                "phone": resume.phone,
                "email": resume.email,
                "job_id": position.moka_job_id,
            }
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{self.base_url}/api/v1/candidates",
                    headers=self._get_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "method": "api",
                    "moka_candidate_id": data.get("id"),
                    "moka_application_id": data.get("application_id"),
                }
        except Exception as e:
            logger.error(f"Moka API 推荐失败: {e}")
            return {"success": False, "method": "api", "error": str(e)}

    def create_interview(
        self,
        resume: Resume,
        position: Position,
        interview_date: str,
        start_time: str,
        end_time: str,
        interviewer_email: str = "",
        location: str = "",
        meeting_link: str = "",
    ) -> dict:
        """在 Moka 上创建面试安排"""
        if not self.api_key:
            return {
                "success": False,
                "method": "manual",
                "message": (
                    f"请手动在 Moka 中安排面试:\n"
                    f"候选人: {resume.candidate_name}\n"
                    f"岗位: {position.title}\n"
                    f"时间: {interview_date} {start_time}-{end_time}\n"
                    f"面试官: {interviewer_email}\n"
                    f"地点: {location or meeting_link}"
                ),
            }

        try:
            payload = {
                "application_id": resume.moka_application_id,
                "stage_id": position.moka_stage_id,
                "start_time": f"{interview_date}T{start_time}:00",
                "end_time": f"{interview_date}T{end_time}:00",
                "interviewer_emails": [interviewer_email] if interviewer_email else [],
                "location": location,
                "online_meeting_link": meeting_link,
            }
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{self.base_url}/api/v1/interviews",
                    headers=self._get_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "method": "api",
                    "interview_id": data.get("id"),
                }
        except Exception as e:
            logger.error(f"Moka API 创建面试失败: {e}")
            return {"success": False, "method": "api", "error": str(e)}


def get_moka_adapter(db: Session) -> Optional[MokaAdapter]:
    config = db.query(MokaConfig).filter(MokaConfig.is_active == True).first()
    if config:
        return MokaAdapter(config)
    return None
