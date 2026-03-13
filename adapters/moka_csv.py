"""
Moka CSV 兜底方案
当 Moka API 不可用时，解析 Moka 定时导出的 CSV 文件获取候选人数据
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from models.resume import Resume, WorkExperience
from models.interview import InterviewSchedule, InterviewStatus, TimeSlot
from utils.logger import get_logger


class MokaCSVParser:
    """解析 Moka 导出的 CSV 文件"""

    def __init__(self, import_dir: str = "./data/moka_csv_import",
                 export_dir: str = "./data/moka_csv_export"):
        self.import_dir = Path(import_dir)
        self.export_dir = Path(export_dir)
        self.import_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger()

    def parse_candidates_csv(self, filepath: str | None = None) -> list[Resume]:
        """解析候选人/简历 CSV"""
        if filepath is None:
            filepath = self._find_latest_csv("candidates")
        if not filepath:
            self.logger.warning("未找到候选人 CSV 文件")
            return []

        resumes = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    resume = self._row_to_resume(row)
                    resumes.append(resume)
                except Exception as e:
                    self.logger.warning(f"解析 CSV 行失败: {e}, row={row}")
                    continue

        self.logger.info(f"CSV 解析完成，共 {len(resumes)} 条简历")
        self.logger.audit(
            action="parse_csv",
            module="moka_csv",
            target=filepath,
            result="success",
            details={"count": len(resumes)}
        )
        return resumes

    def parse_pending_interviews_csv(self, filepath: str | None = None) -> list[dict]:
        """解析待约面状态的 CSV"""
        if filepath is None:
            filepath = self._find_latest_csv("interviews")
        if not filepath:
            self.logger.warning("未找到待约面 CSV 文件")
            return []

        pending = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stage = row.get("阶段", row.get("stage", ""))
                if "待约面" in stage or stage == "pending_schedule":
                    pending.append({
                        "candidate_id": row.get("候选人ID", row.get("candidate_id", "")),
                        "name": row.get("姓名", row.get("name", "")),
                        "position": row.get("应聘职位", row.get("position", "")),
                        "stage": stage,
                        "interviewer": row.get("面试官", row.get("interviewer", "")),
                        "interviewer_times": row.get("面试官可面时间", row.get("available_times", "")),
                    })

        self.logger.info(f"CSV 待约面解析完成，共 {len(pending)} 条")
        return pending

    def parse_interviewer_times_from_csv(self, raw: str) -> list[TimeSlot]:
        """
        解析面试官时间字符串
        格式示例: "2026-03-15 10:00-11:00 优先; 2026-03-16 14:00-15:00 备选"
        """
        slots = []
        if not raw:
            return slots

        entries = raw.split(";")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split()
            if len(parts) < 2:
                continue

            date_str = parts[0]
            time_range = parts[1]
            priority = parts[2] if len(parts) > 2 else "普通"

            if "-" in time_range:
                time_parts = time_range.split("-")
                start_t = time_parts[0]
                end_t = time_parts[1]
            else:
                continue

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                weekday = weekday_names[dt.weekday()]
            except ValueError:
                weekday = ""

            slots.append(TimeSlot(
                date=date_str,
                start_time=start_t,
                end_time=end_t,
                priority=priority,
                weekday=weekday,
            ))

        return slots

    def export_screening_report(self, resumes: list[Resume],
                                output_name: str | None = None) -> str:
        """导出筛选报告 CSV"""
        if not output_name:
            output_name = f"screening_report_{datetime.now():%Y%m%d_%H%M%S}.csv"

        filepath = self.export_dir / output_name
        fieldnames = [
            "姓名", "应聘职位", "匹配分", "筛选状态",
            "核心技能", "工作年限", "学历", "城市",
            "风险点", "驳回原因", "创建时间"
        ]

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in resumes:
                writer.writerow({
                    "姓名": r.name,
                    "应聘职位": r.applied_position,
                    "匹配分": r.match_score,
                    "筛选状态": r.screening_status.value,
                    "核心技能": ", ".join(r.skills),
                    "工作年限": r.total_work_years,
                    "学历": r.education,
                    "城市": r.city,
                    "风险点": "; ".join(r.risk_flags),
                    "驳回原因": r.reject_reason,
                    "创建时间": r.created_at,
                })

        self.logger.info(f"筛选报告已导出: {filepath}")
        return str(filepath)

    def _row_to_resume(self, row: dict) -> Resume:
        name = row.get("姓名", row.get("name", ""))
        skills_raw = row.get("技能", row.get("skills", ""))
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if skills_raw else []

        salary_raw = row.get("期望薪资", row.get("expected_salary", ""))
        sal_min, sal_max = self._parse_salary(salary_raw)

        return Resume(
            id=row.get("候选人ID", row.get("candidate_id", "")),
            moka_id=row.get("Moka ID", row.get("moka_id", "")),
            name=name,
            phone=row.get("电话", row.get("phone", "")),
            email=row.get("邮箱", row.get("email", "")),
            city=row.get("城市", row.get("city", "")),
            education=row.get("学历", row.get("education", "")),
            school=row.get("学校", row.get("school", "")),
            total_work_years=int(row.get("工作年限", row.get("work_years", 0)) or 0),
            expected_salary_min=sal_min,
            expected_salary_max=sal_max,
            skills=skills,
            project_count=int(row.get("项目数量", row.get("project_count", 0)) or 0),
            has_portfolio=row.get("有作品集", row.get("has_portfolio", "否")) in ("是", "true", "True", "1"),
            portfolio_url=row.get("作品集链接", row.get("portfolio_url", "")),
            applied_position=row.get("应聘职位", row.get("position", "")),
            source=row.get("来源", row.get("source", "Boss直聘")),
            raw_data=dict(row),
        )

    def _parse_salary(self, raw: str) -> tuple[int, int]:
        if not raw:
            return 0, 0
        raw = raw.replace("k", "000").replace("K", "000").replace("元", "").replace(",", "")
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

    def _find_latest_csv(self, prefix: str) -> str | None:
        csv_files = list(self.import_dir.glob(f"{prefix}*.csv"))
        if not csv_files:
            csv_files = list(self.import_dir.glob("*.csv"))
        if not csv_files:
            return None
        return str(max(csv_files, key=os.path.getmtime))
