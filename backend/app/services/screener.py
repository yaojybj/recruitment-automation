"""
规则筛选引擎
支持硬性淘汰规则和加权评分规则，按岗位独立配置。
"""
from __future__ import annotations

import re
import logging
from typing import Optional
from sqlalchemy.orm import Session

from ..models import Resume, ScreeningRule, ScreeningLog, RuleOperator, ResumeStatus

logger = logging.getLogger(__name__)

FIELD_MAP = {
    "education": "education",
    "work_years": "work_years",
    "age": "age",
    "city": "city",
    "school": "school",
    "major": "major",
    "skills": "skills",
    "gender": "gender",
    "expected_salary_min": "expected_salary_min",
    "expected_salary_max": "expected_salary_max",
    "current_company": "current_company",
    "current_position": "current_position",
    "raw_text": "raw_text",
}

EDUCATION_ORDER = {
    "博士": 7, "硕士": 6, "研究生": 6,
    "本科": 5, "大专": 4, "专科": 4,
    "高中": 3, "中专": 2, "初中": 1,
}


def screen_resume(db: Session, resume: Resume, position_id: int) -> dict:
    """
    对简历执行指定岗位的所有筛选规则。
    返回 {"passed": bool, "score": float, "details": [...], "risks": [...]}
    """
    rules = (
        db.query(ScreeningRule)
        .filter(ScreeningRule.position_id == position_id, ScreeningRule.is_active == True)
        .order_by(ScreeningRule.order)
        .all()
    )
    if not rules:
        return {"passed": True, "score": 0, "details": [], "risks": ["该岗位暂无筛选规则"]}

    details = []
    risks = []
    total_weight = 0
    weighted_score = 0
    knockout = False

    for rule in rules:
        actual_value = _get_field_value(resume, rule.field)
        passed = _evaluate_rule(actual_value, rule.operator, rule.value, rule.field)
        score = rule.weight if passed else 0

        detail = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "field": rule.field,
            "operator": rule.operator.value if isinstance(rule.operator, RuleOperator) else rule.operator,
            "expected": rule.value,
            "actual": str(actual_value) if actual_value is not None else "未填写",
            "passed": passed,
            "score": score,
            "is_knockout": rule.is_knockout,
        }
        details.append(detail)

        log_entry = ScreeningLog(
            resume_id=resume.id,
            position_id=position_id,
            rule_id=rule.id,
            rule_name=rule.name,
            field=rule.field,
            expected_value=rule.value,
            actual_value=str(actual_value) if actual_value is not None else None,
            passed=passed,
            score=score,
        )
        db.add(log_entry)

        if rule.is_knockout and not passed:
            knockout = True
            risks.append(f"[淘汰] {rule.name}: 期望 {rule.value}, 实际 {actual_value}")

        if not rule.is_knockout:
            total_weight += rule.weight
            weighted_score += score

    final_score = (weighted_score / total_weight * 100) if total_weight > 0 else 0
    overall_passed = not knockout

    resume.screening_score = round(final_score, 1)
    resume.screening_detail = details
    resume.screening_risks = risks
    resume.status = ResumeStatus.PASSED if overall_passed else ResumeStatus.REJECTED
    resume.position_id = position_id

    db.commit()

    return {
        "passed": overall_passed,
        "score": round(final_score, 1),
        "details": details,
        "risks": risks,
    }


def batch_screen(db: Session, resume_ids: list[int], position_id: int) -> list[dict]:
    results = []
    for rid in resume_ids:
        resume = db.query(Resume).get(rid)
        if resume:
            result = screen_resume(db, resume, position_id)
            results.append({"resume_id": rid, "name": resume.candidate_name, **result})
    return results


def _get_field_value(resume: Resume, field: str):
    mapped = FIELD_MAP.get(field, field)
    return getattr(resume, mapped, None)


def _evaluate_rule(actual, operator, expected: str, field: str) -> bool:
    if actual is None:
        return False

    op = operator if isinstance(operator, str) else operator.value

    if field == "education":
        return _compare_education(actual, op, expected)

    if field == "skills":
        return _match_skills(actual, op, expected)

    if field in ("raw_text",):
        return _match_text(actual, op, expected)

    if op == "equals":
        return str(actual).strip() == expected.strip()
    elif op == "not_equals":
        return str(actual).strip() != expected.strip()
    elif op == "contains":
        return expected.lower() in str(actual).lower()
    elif op == "not_contains":
        return expected.lower() not in str(actual).lower()
    elif op in ("greater_than", "greater_equal", "less_than", "less_equal"):
        return _compare_numeric(actual, op, expected)
    elif op == "in":
        values = [v.strip() for v in expected.split(",")]
        return str(actual).strip() in values
    elif op == "not_in":
        values = [v.strip() for v in expected.split(",")]
        return str(actual).strip() not in values
    elif op == "regex":
        return bool(re.search(expected, str(actual), re.IGNORECASE))

    return False


def _compare_education(actual, op: str, expected: str) -> bool:
    actual_level = EDUCATION_ORDER.get(str(actual), 0)
    expected_level = EDUCATION_ORDER.get(expected, 0)
    if op in ("greater_equal", "contains"):
        return actual_level >= expected_level
    elif op == "greater_than":
        return actual_level > expected_level
    elif op == "less_than":
        return actual_level < expected_level
    elif op == "less_equal":
        return actual_level <= expected_level
    elif op == "equals":
        return actual_level == expected_level
    return actual_level >= expected_level


def _compare_numeric(actual, op: str, expected: str) -> bool:
    try:
        a = float(actual)
        e = float(expected)
    except (ValueError, TypeError):
        return False
    if op == "greater_than":
        return a > e
    elif op == "greater_equal":
        return a >= e
    elif op == "less_than":
        return a < e
    elif op == "less_equal":
        return a <= e
    return False


def _match_skills(actual_skills, op: str, expected: str) -> bool:
    if not isinstance(actual_skills, list):
        actual_skills = []
    actual_lower = [s.lower() for s in actual_skills]
    expected_list = [s.strip().lower() for s in expected.split(",")]

    if op in ("contains", "in"):
        return any(exp in " ".join(actual_lower) for exp in expected_list)
    elif op == "not_contains":
        return not any(exp in " ".join(actual_lower) for exp in expected_list)
    elif op == "equals":
        return all(exp in " ".join(actual_lower) for exp in expected_list)
    return False


def _match_text(actual_text: str, op: str, expected: str) -> bool:
    text = str(actual_text).lower()
    keywords = [k.strip().lower() for k in expected.split(",")]
    if op == "contains":
        return any(kw in text for kw in keywords)
    elif op == "not_contains":
        return not any(kw in text for kw in keywords)
    elif op == "regex":
        return bool(re.search(expected, text, re.IGNORECASE))
    return False
