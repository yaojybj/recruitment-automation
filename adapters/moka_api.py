"""
Moka 招聘系统 API 适配器（基于 Moka Open API 官方文档）
支持两种鉴权：Basic Auth（api_key）或 OAuth2（clientID + clientSecret）
核心接口：候选人列表、面试创建、面试列表、面试官忙闲、申请状态移动
"""
from __future__ import annotations

import base64
import time
import json
from datetime import datetime
from typing import Any

import requests

from utils.logger import get_logger
from models.interview import TimeSlot


class MokaAPIError(Exception):
    def __init__(self, message: str, code: int = 0, response: dict | None = None):
        super().__init__(message)
        self.code = code
        self.response = response or {}


class MokaAPI:
    """Moka Open API 适配器"""

    BASE_URL = "https://api.mokahr.com/api-platform"

    def __init__(self, org_id: str,
                 api_key: str = "",
                 client_id: str = "", client_secret: str = "",
                 retry_max: int = 3, retry_delay: float = 5.0,
                 rate_limit_per_minute: int = 60):
        """
        鉴权二选一：
        - Basic Auth: 传 api_key
        - OAuth2: 传 client_id + client_secret
        """
        self.org_id = org_id
        self.api_key = api_key
        self.client_id = client_id
        self.client_secret = client_secret
        self.retry_max = retry_max
        self.retry_delay = retry_delay
        self.rate_limit_per_minute = rate_limit_per_minute

        self._access_token: str = ""
        self._token_expires_at: float = 0
        self._request_timestamps: list[float] = []

        self.use_oauth2 = bool(client_id and client_secret)
        self.logger = get_logger()

    # ========== 鉴权 ==========

    def _get_auth_headers(self) -> dict:
        if self.use_oauth2:
            token = self._get_oauth2_token()
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        else:
            encoded = base64.b64encode(f"{self.api_key}:".encode()).decode()
            return {
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/json",
            }

    def _get_oauth2_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.BASE_URL}/v1/auth/oauth2/getToken"
        payload = {
            "clientID": self.client_id,
            "clientSecret": self.client_secret,
            "grantType": "client_credentials",
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise MokaAPIError(
                f"OAuth2 token 获取失败: {data.get('msg', '')}",
                code=data.get("code", -1), response=data
            )

        self._access_token = data["data"]["accessToken"]
        expires_in = data["data"].get("expiresIn", 7200)
        self._token_expires_at = time.time() + expires_in - 300
        self.logger.info("Moka OAuth2 token 刷新成功")
        return self._access_token

    # ========== 通用请求 ==========

    def _rate_limit(self):
        now = time.time()
        self._request_timestamps = [
            t for t in self._request_timestamps if t > now - 60
        ]
        if len(self._request_timestamps) >= self.rate_limit_per_minute:
            sleep_time = 60 - (now - self._request_timestamps[0]) + 0.1
            self.logger.warning(f"API限流，等待 {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._request_timestamps.append(time.time())

    def _request(self, method: str, path: str,
                 params: dict | None = None,
                 json_data: dict | None = None) -> dict:
        url = path if path.startswith("http") else f"{self.BASE_URL}/{path.lstrip('/')}"
        last_error = None

        for attempt in range(1, self.retry_max + 1):
            self._rate_limit()
            headers = self._get_auth_headers()
            try:
                resp = requests.request(
                    method, url, headers=headers,
                    params=params, json=json_data, timeout=30
                )

                if resp.status_code == 401 and self.use_oauth2:
                    self._access_token = ""
                    headers = self._get_auth_headers()
                    continue

                resp.raise_for_status()
                data = resp.json()

                self.logger.audit(
                    action=f"MOKA_{method}",
                    module="moka_api",
                    target=path,
                    result="success",
                    details={"status": resp.status_code}
                )
                return data

            except requests.exceptions.RequestException as e:
                last_error = e
                self.logger.warning(
                    f"Moka API 请求失败 (第{attempt}/{self.retry_max}次): {path} - {e}"
                )
                self.logger.audit(
                    action=f"MOKA_{method}",
                    module="moka_api",
                    target=path,
                    result="retry" if attempt < self.retry_max else "failed",
                    details={"attempt": attempt, "error": str(e)}
                )
                if attempt < self.retry_max:
                    time.sleep(self.retry_delay * attempt)

        raise MokaAPIError(f"API 请求 {self.retry_max} 次重试后仍失败: {last_error}")

    # ========== 候选人/申请 ==========

    def get_moved_applications(self, stage: str = "all",
                                from_time: str = "",
                                limit: int = 100) -> list[dict]:
        """
        获取全部阶段下的候选人信息（分页版）
        stage: all / preliminary_filter / interview / offer / pending_checkin / filter
        返回完整的候选人简历数据（含 experienceInfo, educationInfo, projectInfo 等）
        """
        params: dict[str, Any] = {"stage": stage}
        if from_time:
            params["fromTime"] = from_time
        if limit:
            params["limit"] = limit

        all_records = []
        data = self._request("GET", "v1/data/movedApplications", params=params)

        records = data.get("data", [])
        all_records.extend(records)

        while data.get("next"):
            params = {"next": data["next"]}
            if limit:
                params["limit"] = limit
            data = self._request("GET", "v1/data/movedApplications", params=params)
            records = data.get("data", [])
            if not records:
                break
            all_records.extend(records)

        self.logger.info(f"Moka 获取候选人: stage={stage}, 共 {len(all_records)} 条")
        return all_records

    def get_application_status(self, application_id: int) -> dict:
        """获取申请状态"""
        data = self._request("GET", f"v1/applications/{application_id}")
        return data.get("data", data)

    def move_application_stage(self, application_id: int, stage_id: int) -> dict:
        """移动申请到指定阶段"""
        return self._request(
            "PUT",
            f"v1/applications/move_application_stage",
            params={"applicationId": application_id, "stageId": stage_id}
        )

    # ========== 面试 ==========

    def create_interview(self, stage_id: int, start_time: str,
                         duration: int, type_code: int,
                         arranger_email: str, location_id: int,
                         round_num: int, application_ids: list[int],
                         interviewer_emails: list[str],
                         signed_in_at: str = "",
                         meeting_room_id: int | None = None) -> dict:
        """
        创建面试
        type_code: 1=现场面试 2=集体面试 3=电话面试 4=视频面试
        start_time / signed_in_at 格式: "yyyy-MM-dd HH:mm:ss"
        """
        payload = {
            "stageId": stage_id,
            "startTime": start_time,
            "duration": duration,
            "typeCode": type_code,
            "orgId": self.org_id,
            "interviewArrangerEmail": arranger_email,
            "locationId": location_id,
            "round": round_num,
            "signedInAt": signed_in_at or start_time,
            "applicationIds": application_ids,
            "interviewerEmails": interviewer_emails,
        }
        if meeting_room_id:
            payload["meetingRoomId"] = meeting_room_id

        data = self._request("POST", "v1/interview/create", json_data=payload)

        if data.get("code") != 0:
            raise MokaAPIError(
                f"面试创建失败: {data.get('message', '')}",
                code=data.get("code", -1), response=data
            )

        self.logger.audit(
            action="create_interview",
            module="moka_api",
            target=str(application_ids),
            result="success",
            details={"interview_id": data.get("data", {}).get("groupInterviewId")}
        )
        return data.get("data", {})

    def get_interviews(self, start_date: str, end_date: str,
                       hire_mode: int = 1) -> list[dict]:
        """
        拉取面试列表
        start_date / end_date: ISO8601 格式
        """
        data = self._request("GET", "v1/interviews", params={
            "startDate": start_date,
            "endDate": end_date,
            "hireMode": hire_mode,
        })
        return data.get("data", [])

    def get_interviewer_busy_time(self, interviewer_ids: list[int],
                                   start_time: str, end_time: str) -> dict:
        """获取面试官忙闲时间"""
        data = self._request("POST", "v1/interview/busyTime", json_data={
            "orgId": self.org_id,
            "interviewerIds": interviewer_ids,
            "startTime": start_time,
            "endTime": end_time,
        })
        return data.get("data", {})

    # ========== 职位 ==========

    def get_jobs(self, page: int = 1, page_size: int = 50) -> list[dict]:
        """获取职位列表"""
        data = self._request("GET", "v1/jobs", params={
            "page": page,
            "pageSize": page_size,
        })
        return data.get("data", {}).get("records", data.get("data", []))

    def get_pipeline_stages(self) -> list[dict]:
        """获取招聘流程及阶段信息"""
        data = self._request("GET", "v1/pipelines")
        return data.get("data", [])

    # ========== Moka 数据 → 本地模型转换 ==========

    def parse_candidate_to_resume_data(self, candidate: dict) -> dict:
        """将 Moka API 返回的候选人数据转换为本地 Resume 所需的字段"""
        experience_info = candidate.get("experienceInfo", [])
        education_info = candidate.get("educationInfo", [])
        project_info = candidate.get("projectInfo", [])
        custom_fields = candidate.get("customFields", [])

        skills = self._extract_skills(experience_info, custom_fields)

        work_experiences = []
        for exp in experience_info:
            duration = self._calc_duration_months(
                exp.get("startDate", ""), exp.get("endDate", ""), exp.get("now", False)
            )
            work_experiences.append({
                "company": exp.get("company", ""),
                "position": exp.get("title", ""),
                "start_date": exp.get("startDate", ""),
                "end_date": exp.get("endDate", "") if not exp.get("now") else "至今",
                "duration_months": duration,
                "industry": "",
                "description": exp.get("summary", ""),
            })

        total_years = candidate.get("experience") or 0
        if not total_years and work_experiences:
            total_months = sum(w.get("duration_months", 0) for w in work_experiences)
            total_years = total_months // 12

        salary_raw = candidate.get("aimSalary") or candidate.get("salary") or ""
        sal_min, sal_max = self._parse_salary(salary_raw)

        portfolio_url = ""
        has_portfolio = False
        for cf in custom_fields:
            name_lower = cf.get("name", "").lower()
            if "作品" in name_lower or "portfolio" in name_lower:
                portfolio_url = str(cf.get("value", ""))
                has_portfolio = bool(portfolio_url)
                break

        city = candidate.get("location", "") or ""

        education = candidate.get("academicDegree", "")
        school = ""
        if education_info:
            latest_edu = education_info[0]
            school = latest_edu.get("school", "")
            if not education:
                education = latest_edu.get("academicDegree", "")

        job = candidate.get("job", {})

        return {
            "id": str(candidate.get("candidateId", "")),
            "moka_id": str(candidate.get("applicationId", "")),
            "name": candidate.get("name", ""),
            "phone": candidate.get("phone", ""),
            "email": candidate.get("email", ""),
            "city": city,
            "education": education,
            "school": school,
            "total_work_years": int(total_years),
            "expected_salary_min": sal_min,
            "expected_salary_max": sal_max,
            "skills": skills,
            "work_experiences": work_experiences,
            "project_count": len(project_info),
            "has_portfolio": has_portfolio,
            "portfolio_url": portfolio_url,
            "applied_position": job.get("title", ""),
            "source": candidate.get("source", ""),
            "stage_name": candidate.get("stageName", ""),
            "stage_type": candidate.get("stageType", ""),
            "raw_data": candidate,
        }

    def _extract_skills(self, experience_info: list, custom_fields: list) -> list[str]:
        """从工作经历和自定义字段中提取技能"""
        skills = set()

        for cf in custom_fields:
            name = cf.get("name", "").lower()
            if "技能" in name or "skill" in name or "擅长" in name:
                val = cf.get("value", "")
                if isinstance(val, str):
                    for s in val.replace("，", ",").replace("、", ",").replace("/", ",").split(","):
                        s = s.strip()
                        if s:
                            skills.add(s)

        common_skills = [
            "Java", "Python", "JavaScript", "TypeScript", "Go", "C++", "C#", "PHP", "Ruby", "Swift", "Kotlin",
            "React", "Vue", "Angular", "Node.js", "Spring", "Django", "Flask", "FastAPI",
            "MySQL", "PostgreSQL", "MongoDB", "Redis", "Kafka", "RabbitMQ", "Elasticsearch",
            "Docker", "Kubernetes", "AWS", "Azure", "GCP",
            "AE", "PR", "C4D", "Photoshop", "Illustrator", "Sketch", "Figma", "Blender",
            "After Effects", "Premiere", "InDesign", "XD",
            "Axure", "Tableau", "Power BI", "SQL", "Excel",
            "需求分析", "产品设计", "用户研究", "数据分析", "项目管理",
        ]
        for exp in experience_info:
            text = (exp.get("title", "") + " " + exp.get("summary", "")).lower()
            for skill in common_skills:
                if skill.lower() in text:
                    skills.add(skill)

        return list(skills)

    def _calc_duration_months(self, start: str, end: str, is_now: bool) -> int:
        try:
            start_parts = start.split("-")
            if is_now:
                end_dt = datetime.now()
            else:
                end_parts = end.split("-")
                end_dt = datetime(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 1, 1)
            start_dt = datetime(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 1, 1)
            return max(0, (end_dt.year - start_dt.year) * 12 + end_dt.month - start_dt.month)
        except (ValueError, IndexError):
            return 0

    def _parse_salary(self, raw) -> tuple[int, int]:
        if not raw:
            return 0, 0
        raw = str(raw)
        raw = raw.replace("k", "000").replace("K", "000").replace("元", "").replace(",", "").replace("￥", "")
        parts = raw.split("-")
        try:
            if len(parts) == 2:
                return int(float(parts[0])), int(float(parts[1]))
            elif len(parts) == 1:
                val = int(float(parts[0]))
                return val, val
        except ValueError:
            pass
        return 0, 0
