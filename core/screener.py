"""
模块1：简历精准筛选引擎
分层筛选：硬门槛层 → 匹配度打分层 → 自动过滤层 → 待复核清单
"""

from __future__ import annotations

import re
import json
from datetime import datetime
from pathlib import Path
from collections import Counter

from models.resume import Resume, ScreeningStatus
from utils.config_loader import get_screening_rules, get_education_levels
from utils.logger import get_logger
from utils.notifier import notify


# 本地持久化文件
DATA_DIR = Path("./data")
REVIEW_QUEUE_FILE = DATA_DIR / "review_queue.json"
SCREENING_HISTORY_FILE = DATA_DIR / "screening_history.json"


class ResumeScreener:
    """简历筛选引擎"""

    def __init__(self):
        self.logger = get_logger()
        self.education_levels = get_education_levels()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def screen_batch(self, resumes: list[Resume]) -> dict[str, list[Resume]]:
        """
        批量筛选简历
        返回: {"approved": [...], "rejected": [...], "pending_review": [...]}
        """
        results = {
            "approved": [],
            "rejected": [],
            "pending_review": [],
        }

        for resume in resumes:
            result = self.screen_single(resume)
            if resume.screening_status == ScreeningStatus.AUTO_REJECTED:
                results["rejected"].append(resume)
            elif resume.screening_status == ScreeningStatus.PENDING_REVIEW:
                results["pending_review"].append(resume)

        self._save_review_queue(results["pending_review"])
        self._save_screening_history(resumes)

        self.logger.info(
            f"批量筛选完成: 待复核={len(results['pending_review'])}, "
            f"自动淘汰={len(results['rejected'])}, 总计={len(resumes)}"
        )
        self.logger.audit(
            action="screen_batch",
            module="screener",
            target=f"{len(resumes)} resumes",
            result="completed",
            details={
                "pending_review": len(results["pending_review"]),
                "rejected": len(results["rejected"]),
            }
        )
        return results

    def screen_single(self, resume: Resume) -> Resume:
        """单份简历完整筛选流程"""
        rules = get_screening_rules(resume.applied_position)

        # 第一层：自动过滤
        auto_filter = rules.get("auto_filter", {})
        filter_reason = self._apply_auto_filter(resume, auto_filter)
        if filter_reason:
            resume.screening_status = ScreeningStatus.AUTO_REJECTED
            resume.reject_reason = filter_reason
            self.logger.audit(
                action="auto_filter",
                module="screener",
                target=resume.name,
                result="rejected",
                details={"reason": filter_reason}
            )
            return resume

        # 第二层：硬门槛检查
        hard_reqs = rules.get("hard_requirements", {})
        hard_fail = self._check_hard_requirements(resume, hard_reqs)
        if hard_fail:
            resume.screening_status = ScreeningStatus.AUTO_REJECTED
            resume.reject_reason = f"硬门槛不满足: {hard_fail}"
            self.logger.audit(
                action="hard_requirement_check",
                module="screener",
                target=resume.name,
                result="rejected",
                details={"reason": hard_fail}
            )
            return resume

        # 第三层：匹配度打分
        weights = rules.get("scoring_weights", {})
        score, breakdown = self._calculate_score(resume, rules)
        resume.match_score = score
        resume.score_breakdown = breakdown

        # 第四层：风险标记
        risk_config = rules.get("risk_flags", {})
        resume.risk_flags = self._detect_risks(resume, hard_reqs, risk_config)

        # 分数判定
        min_score = 85
        if score >= min_score:
            resume.screening_status = ScreeningStatus.PENDING_REVIEW
        else:
            resume.screening_status = ScreeningStatus.AUTO_REJECTED
            resume.reject_reason = f"匹配分不足: {score}分 (要求≥{min_score})"

        self.logger.audit(
            action="score_screening",
            module="screener",
            target=resume.name,
            result=resume.screening_status.value,
            details={
                "score": score,
                "breakdown": breakdown,
                "risks": resume.risk_flags,
            }
        )
        return resume

    def _apply_auto_filter(self, resume: Resume, config: dict) -> str:
        """自动过滤层"""
        if config.get("reject_no_project_experience") and resume.project_count == 0:
            if not resume.work_experiences:
                return "无项目经验"

        if config.get("reject_no_portfolio") and not resume.has_portfolio:
            return "无作品集"

        if config.get("reject_keyword_stuffing"):
            threshold = config.get("keyword_stuffing_threshold", 15)
            all_text = " ".join([
                resume.name,
                " ".join(resume.skills),
                " ".join(exp.description for exp in resume.work_experiences),
            ])
            word_counts = Counter(all_text.lower().split())
            for word, count in word_counts.items():
                if len(word) >= 2 and count >= threshold:
                    return f"关键词堆砌: '{word}' 出现{count}次"

        if config.get("reject_irrelevant_position"):
            if resume.applied_position and resume.skills:
                pass

        return ""

    def _check_hard_requirements(self, resume: Resume, reqs: dict) -> str:
        """硬门槛检查，返回不满足原因或空字符串"""
        # 学历
        min_edu = reqs.get("min_education", "")
        if min_edu and resume.education:
            min_level = self.education_levels.get(min_edu, 0)
            candidate_level = self.education_levels.get(resume.education, 0)
            if candidate_level < min_level:
                return f"学历不满足: 要求{min_edu}, 实际{resume.education}"

        # 工作年限
        min_years = reqs.get("min_work_years", 0)
        if min_years and resume.total_work_years < min_years:
            return f"工作年限不足: 要求{min_years}年, 实际{resume.total_work_years}年"

        # 城市
        cities = reqs.get("cities", [])
        if cities and resume.city and resume.city not in cities:
            return f"城市不匹配: 要求{cities}, 实际{resume.city}"

        # 核心技能
        required_skills = reqs.get("required_skills", [])
        if required_skills and resume.skills:
            candidate_skills_lower = [s.lower() for s in resume.skills]
            missing = [
                s for s in required_skills
                if s.lower() not in candidate_skills_lower
            ]
            if missing:
                return f"缺少核心技能: {', '.join(missing)}"

        # 期望薪资
        salary_range = reqs.get("salary_range", [])
        if len(salary_range) == 2 and resume.expected_salary_min > 0:
            if resume.expected_salary_min > salary_range[1]:
                return f"期望薪资超出范围: 候选人{resume.expected_salary_min}-{resume.expected_salary_max}, 岗位上限{salary_range[1]}"

        # 作品集
        if reqs.get("require_portfolio") and not resume.has_portfolio:
            return "未提供作品集"

        return ""

    def _calculate_score(self, resume: Resume, rules: dict) -> tuple[int, dict]:
        """匹配度打分，返回 (总分, 分项明细)"""
        weights = rules.get("scoring_weights", {})
        breakdown = {}
        total = 0

        # 行业匹配
        max_industry = weights.get("industry_match", 20)
        industry_score = self._score_industry(resume, rules)
        scaled = min(int(industry_score * max_industry / 100), max_industry)
        breakdown["行业匹配"] = scaled
        total += scaled

        # 项目经验
        max_project = weights.get("project_experience", 25)
        project_score = self._score_project_experience(resume)
        scaled = min(int(project_score * max_project / 100), max_project)
        breakdown["项目经验"] = scaled
        total += scaled

        # 技能熟练度
        max_skill = weights.get("skill_proficiency", 25)
        skill_score = self._score_skills(resume, rules)
        scaled = min(int(skill_score * max_skill / 100), max_skill)
        breakdown["技能熟练度"] = scaled
        total += scaled

        # 稳定性
        max_stability = weights.get("stability", 15)
        stability_score = self._score_stability(resume)
        scaled = min(int(stability_score * max_stability / 100), max_stability)
        breakdown["稳定性"] = scaled
        total += scaled

        # 学历加分
        max_edu = weights.get("education_bonus", 10)
        edu_score = self._score_education(resume)
        scaled = min(int(edu_score * max_edu / 100), max_edu)
        breakdown["学历加分"] = scaled
        total += scaled

        # 作品集加分
        max_portfolio = weights.get("portfolio_bonus", 5)
        portfolio_score = 100 if resume.has_portfolio else 0
        scaled = min(int(portfolio_score * max_portfolio / 100), max_portfolio)
        breakdown["作品集加分"] = scaled
        total += scaled

        return total, breakdown

    def _score_industry(self, resume: Resume, rules: dict) -> int:
        """行业匹配度评分 0-100"""
        if resume.work_experiences:
            score = 60
            if len(resume.work_experiences) >= 2:
                score += 20
            if any(exp.duration_months >= 24 for exp in resume.work_experiences):
                score += 20
            return min(score, 100)

        if resume.total_work_years >= 5:
            return 85
        elif resume.total_work_years >= 3:
            return 70
        elif resume.total_work_years >= 1:
            return 55
        return 30

    def _score_project_experience(self, resume: Resume) -> int:
        if resume.project_count >= 5:
            return 100
        elif resume.project_count >= 3:
            return 80
        elif resume.project_count >= 1:
            return 60
        elif resume.work_experiences or resume.total_work_years >= 3:
            return 50
        return 10

    def _score_skills(self, resume: Resume, rules: dict) -> int:
        required = rules.get("hard_requirements", {}).get("required_skills", [])
        if not required:
            return 70

        candidate_lower = [s.lower() for s in resume.skills]
        matched = sum(1 for s in required if s.lower() in candidate_lower)

        if not required:
            return 70
        ratio = matched / len(required)

        extra_skills = len(resume.skills) - matched
        bonus = min(extra_skills * 2, 10)

        return min(int(ratio * 90 + bonus), 100)

    def _score_stability(self, resume: Resume) -> int:
        """稳定性评分：跳槽频率"""
        if resume.work_experiences:
            if resume.total_work_years <= 0:
                return 50
            job_count = len(resume.work_experiences)
            avg_tenure_years = resume.total_work_years / max(job_count, 1)
            if avg_tenure_years >= 3:
                return 100
            elif avg_tenure_years >= 2:
                return 80
            elif avg_tenure_years >= 1:
                return 50
            return 20

        if resume.total_work_years >= 5:
            return 80
        elif resume.total_work_years >= 3:
            return 70
        return 55

    def _score_education(self, resume: Resume) -> int:
        level = self.education_levels.get(resume.education, 0)
        if level >= 4:
            return 100
        elif level >= 3:
            return 70
        elif level >= 2:
            return 40
        return 10

    def _detect_risks(self, resume: Resume, hard_reqs: dict,
                      risk_config: dict) -> list[str]:
        """检测风险点"""
        risks = []

        # 薪资偏高
        deviation = risk_config.get("high_salary_deviation_percent", 30)
        salary_range = hard_reqs.get("salary_range", [])
        if len(salary_range) == 2 and resume.expected_salary_min > 0:
            upper = salary_range[1]
            if resume.expected_salary_min > upper * (1 - deviation / 100):
                risks.append(
                    f"薪资偏高: 期望{resume.expected_salary_min}-{resume.expected_salary_max}, "
                    f"岗位上限{upper}"
                )

        # 频繁跳槽
        threshold = risk_config.get("frequent_job_change_threshold", 3)
        recent_jobs = [
            exp for exp in resume.work_experiences
            if exp.duration_months > 0 and exp.duration_months < 36
        ]
        if len(recent_jobs) >= threshold:
            risks.append(f"频繁跳槽: 近期{len(recent_jobs)}份工作少于3年")

        # 单份工作时间过短
        short_months = risk_config.get("short_tenure_months", 6)
        short_jobs = [
            exp for exp in resume.work_experiences
            if 0 < exp.duration_months < short_months
        ]
        if short_jobs:
            risks.append(f"存在{len(short_jobs)}份工作不满{short_months}个月")

        return risks

    # ========== 复核操作 ==========

    def approve_resume(self, resume: Resume, reviewer: str = "HR") -> Resume:
        """复核通过"""
        resume.screening_status = ScreeningStatus.REVIEW_APPROVED
        resume.reviewed_at = datetime.now().isoformat()
        resume.reviewed_by = reviewer
        self.logger.audit(
            action="review_approve",
            module="screener",
            target=resume.name,
            result="approved",
            details={"reviewer": reviewer, "score": resume.match_score}
        )
        return resume

    def reject_resume(self, resume: Resume, reason: str = "",
                      reviewer: str = "HR") -> Resume:
        """复核驳回"""
        resume.screening_status = ScreeningStatus.REVIEW_REJECTED
        resume.reject_reason = reason or "人工复核驳回"
        resume.reviewed_at = datetime.now().isoformat()
        resume.reviewed_by = reviewer
        self.logger.audit(
            action="review_reject",
            module="screener",
            target=resume.name,
            result="rejected",
            details={"reviewer": reviewer, "reason": reason}
        )
        return resume

    def batch_approve(self, resumes: list[Resume],
                      reviewer: str = "HR") -> list[Resume]:
        """批量通过"""
        return [self.approve_resume(r, reviewer) for r in resumes]

    def batch_reject(self, resumes: list[Resume], reason: str = "",
                     reviewer: str = "HR") -> list[Resume]:
        """批量驳回"""
        return [self.reject_resume(r, reason, reviewer) for r in resumes]

    # ========== 准确率反馈 ==========

    def calculate_accuracy(self, position: str = "",
                           error_notes: list[dict] | None = None) -> dict:
        """
        计算筛选准确率
        error_notes: Moka 备注中含 '筛错' 关键词的记录
        """
        history = self._load_screening_history()
        if position:
            history = [r for r in history if r.get("applied_position") == position]

        total_approved = len([
            r for r in history
            if r.get("screening_status") == ScreeningStatus.REVIEW_APPROVED.value
        ])
        error_count = len(error_notes) if error_notes else 0

        accuracy = (
            (total_approved - error_count) / max(total_approved, 1)
        ) if total_approved > 0 else 1.0

        result = {
            "position": position or "全部",
            "total_approved": total_approved,
            "error_count": error_count,
            "accuracy": round(accuracy, 4),
            "accuracy_percent": f"{accuracy * 100:.1f}%",
        }

        if accuracy < 0.80:
            notify(
                "筛选准确率偏低",
                f"{'职位'+position+' ' if position else ''}准确率={result['accuracy_percent']}，建议收紧规则",
                level="warning"
            )

        return result

    def export_inaccurate_resumes(self, error_notes: list[dict]) -> str:
        """导出筛选不准的简历列表"""
        export_path = DATA_DIR / "exports" / f"inaccurate_{datetime.now():%Y%m%d_%H%M%S}.json"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(error_notes, f, ensure_ascii=False, indent=2)
        self.logger.info(f"筛选不准列表已导出: {export_path}")
        return str(export_path)

    # ========== 持久化 ==========

    def _save_review_queue(self, resumes: list[Resume]):
        data = [r.to_dict() for r in resumes]
        existing = self._load_review_queue_raw()
        existing_ids = {r["id"] for r in existing}
        for d in data:
            if d["id"] not in existing_ids:
                existing.append(d)
        with open(REVIEW_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def _load_review_queue_raw(self) -> list[dict]:
        if REVIEW_QUEUE_FILE.exists():
            with open(REVIEW_QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def load_review_queue(self) -> list[Resume]:
        raw = self._load_review_queue_raw()
        return [Resume.from_dict(d) for d in raw
                if d.get("screening_status") == ScreeningStatus.PENDING_REVIEW.value]

    def _save_screening_history(self, resumes: list[Resume]):
        data = [r.to_dict() for r in resumes]
        existing = self._load_screening_history()
        existing.extend(data)
        with open(SCREENING_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def _load_screening_history(self) -> list[dict]:
        if SCREENING_HISTORY_FILE.exists():
            with open(SCREENING_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def update_review_queue(self, resumes: list[Resume]):
        """更新复核队列中已处理的简历状态"""
        raw = self._load_review_queue_raw()
        updated_ids = {r.id: r for r in resumes}
        for i, item in enumerate(raw):
            if item["id"] in updated_ids:
                raw[i] = updated_ids[item["id"]].to_dict()
        with open(REVIEW_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
