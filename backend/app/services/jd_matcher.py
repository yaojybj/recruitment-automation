"""
JD 匹配引擎
将简历与职位 JD 进行多维度匹配打分。

打分维度：
1. 必备技能匹配 (30分) — must_have 关键词命中率
2. 加分技能匹配 (15分) — nice_to_have 关键词命中率
3. 工作年限匹配 (15分) — 是否满足最低年限
4. 学历匹配 (15分) — 是否满足学历要求
5. JD 全文语义相似度 (25分) — TF-IDF 余弦相似度
"""
from __future__ import annotations

import re
import math
import logging
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Resume, Position, ResumeStatus, PipelineLog, OperationLog

logger = logging.getLogger(__name__)

EDUCATION_RANK = {
    "博士": 7, "硕士": 6, "研究生": 6,
    "本科": 5, "大专": 4, "专科": 4,
    "高中": 3, "中专": 2,
}

STOPWORDS = set("的了在是我有和就不人都一个上也很到说要去你会着没看好自己这他她它们".split() + list("，。、；：？！""''（）【】"))


def match_resume_to_position(db: Session, resume: Resume, position: Position) -> dict:
    """
    对单份简历执行 JD 匹配，返回:
    {
        "total_score": 78.5,
        "dimensions": {...},
        "matched_must_have": [...],
        "missing_must_have": [...],
        "matched_nice_to_have": [...],
        "passed": True
    }
    """
    resume_text = _build_resume_text(resume)
    jd_text = position.jd_text or ""
    must_have = position.jd_must_have or []
    nice_to_have = position.jd_nice_to_have or []
    jd_education = position.jd_education
    jd_min_years = position.jd_min_years
    threshold = position.match_threshold or 60.0

    dimensions = {}

    # 1. 必备技能 (30分)
    must_score, matched_must, missing_must = _keyword_match_score(
        resume_text, resume.skills or [], must_have
    )
    dimensions["must_have"] = {
        "score": round(must_score * 30, 1),
        "max": 30,
        "matched": matched_must,
        "missing": missing_must,
    }

    # 2. 加分技能 (15分)
    nice_score, matched_nice, _ = _keyword_match_score(
        resume_text, resume.skills or [], nice_to_have
    )
    dimensions["nice_to_have"] = {
        "score": round(nice_score * 15, 1),
        "max": 15,
        "matched": matched_nice,
    }

    # 3. 工作年限 (15分)
    years_score = _years_score(resume.work_years, jd_min_years)
    dimensions["work_years"] = {
        "score": round(years_score * 15, 1),
        "max": 15,
        "actual": resume.work_years,
        "required": jd_min_years,
    }

    # 4. 学历 (15分)
    edu_score = _education_score(resume.education, jd_education)
    dimensions["education"] = {
        "score": round(edu_score * 15, 1),
        "max": 15,
        "actual": resume.education,
        "required": jd_education,
    }

    # 5. JD 全文相似度 (25分)
    if jd_text and resume_text:
        sim_score = _text_similarity(resume_text, jd_text)
    else:
        sim_score = 0
    dimensions["text_similarity"] = {
        "score": round(sim_score * 25, 1),
        "max": 25,
    }

    total = sum(d["score"] for d in dimensions.values())
    total = round(min(total, 100), 1)
    passed = total >= threshold

    result = {
        "total_score": total,
        "threshold": threshold,
        "dimensions": dimensions,
        "matched_must_have": matched_must,
        "missing_must_have": missing_must,
        "matched_nice_to_have": matched_nice,
        "passed": passed,
    }

    resume.jd_match_score = total
    resume.jd_match_detail = result
    resume.position_id = position.id
    if passed:
        _transition(db, resume, ResumeStatus.JD_MATCHED, "jd_match_passed",
                    f"JD匹配通过: {total}分 (阈值{threshold})")
    else:
        _transition(db, resume, ResumeStatus.REJECTED, "jd_match_failed",
                    f"JD匹配未达标: {total}分 (阈值{threshold})")

    db.commit()
    return result


def batch_match(db: Session, position_id: int, resume_ids: list[int] = None) -> list[dict]:
    """批量匹配：对指定简历（或所有待处理简历）执行 JD 匹配"""
    position = db.query(Position).get(position_id)
    if not position:
        return []

    query = db.query(Resume)
    if resume_ids:
        query = query.filter(Resume.id.in_(resume_ids))
    else:
        query = query.filter(Resume.status == ResumeStatus.PENDING)
    resumes = query.all()

    results = []
    for resume in resumes:
        try:
            result = match_resume_to_position(db, resume, position)
            results.append({
                "resume_id": resume.id,
                "name": resume.candidate_name,
                **result,
            })
        except Exception as e:
            logger.error(f"匹配简历 {resume.id} 失败: {e}")
            results.append({
                "resume_id": resume.id,
                "name": resume.candidate_name,
                "error": str(e),
            })

    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return results


def auto_match_new_resumes(db: Session):
    """自动匹配：新入池的简历自动与活跃岗位匹配"""
    pending = db.query(Resume).filter(Resume.status == ResumeStatus.PENDING).all()
    if not pending:
        return

    active_positions = db.query(Position).filter(
        Position.is_active == True,
        Position.jd_text != None,
        Position.jd_text != "",
    ).all()

    for resume in pending:
        best_score = 0
        best_position = None
        best_result = None

        for position in active_positions:
            try:
                result = _calc_match_only(resume, position)
                if result["total_score"] > best_score:
                    best_score = result["total_score"]
                    best_position = position
                    best_result = result
            except Exception as e:
                logger.error(f"自动匹配异常: resume={resume.id}, pos={position.id}, err={e}")

        if best_position and best_result:
            resume.jd_match_score = best_score
            resume.jd_match_detail = best_result
            resume.position_id = best_position.id
            threshold = best_position.match_threshold or 60.0

            if best_score >= threshold:
                resume.status = ResumeStatus.JD_MATCHED
                _log_pipeline(db, resume, "pending", "jd_matched", "auto_match",
                              f"自动匹配到「{best_position.title}」: {best_score}分")
                if best_position.auto_recommend:
                    resume.status = ResumeStatus.RECOMMENDED
                    _log_pipeline(db, resume, "jd_matched", "recommended", "auto_recommend",
                                  f"自动推荐到用人部门")

    db.commit()


# ── 内部工具函数 ──

def _calc_match_only(resume: Resume, position: Position) -> dict:
    """只计算分数，不写库"""
    resume_text = _build_resume_text(resume)
    jd_text = position.jd_text or ""
    must_have = position.jd_must_have or []
    nice_to_have = position.jd_nice_to_have or []

    must_score, matched_must, missing_must = _keyword_match_score(resume_text, resume.skills or [], must_have)
    nice_score, matched_nice, _ = _keyword_match_score(resume_text, resume.skills or [], nice_to_have)
    years_score = _years_score(resume.work_years, position.jd_min_years)
    edu_score = _education_score(resume.education, position.jd_education)
    sim_score = _text_similarity(resume_text, jd_text) if jd_text and resume_text else 0

    total = round(min(
        must_score * 30 + nice_score * 15 + years_score * 15 + edu_score * 15 + sim_score * 25,
        100
    ), 1)

    return {
        "total_score": total,
        "matched_must_have": matched_must,
        "missing_must_have": missing_must,
        "passed": total >= (position.match_threshold or 60.0),
    }


def _build_resume_text(resume: Resume) -> str:
    parts = []
    if resume.raw_text:
        parts.append(resume.raw_text)
    if resume.skills:
        parts.append(" ".join(resume.skills))
    if resume.current_position:
        parts.append(resume.current_position)
    if resume.current_company:
        parts.append(resume.current_company)
    if resume.major:
        parts.append(resume.major)
    return " ".join(parts)


def _keyword_match_score(text: str, skills: list, keywords: list) -> tuple:
    if not keywords:
        return 1.0, [], []

    text_lower = text.lower()
    skills_lower = [s.lower() for s in skills]
    skills_joined = " ".join(skills_lower)

    matched = []
    missing = []
    for kw in keywords:
        kw_lower = kw.lower()
        alts = [a.strip().lower() for a in kw.split("/")]
        found = False
        for alt in alts:
            if alt in text_lower or alt in skills_joined:
                found = True
                break
        if found:
            matched.append(kw)
        else:
            missing.append(kw)

    score = len(matched) / len(keywords) if keywords else 1.0
    return score, matched, missing


def _years_score(actual: Optional[float], required: Optional[float]) -> float:
    if required is None or required <= 0:
        return 1.0
    if actual is None:
        return 0.3
    if actual >= required:
        return 1.0
    elif actual >= required * 0.7:
        return 0.6
    elif actual >= required * 0.5:
        return 0.3
    return 0.0


def _education_score(actual: Optional[str], required: Optional[str]) -> float:
    if not required:
        return 1.0
    if not actual:
        return 0.3
    actual_rank = EDUCATION_RANK.get(actual, 0)
    required_rank = EDUCATION_RANK.get(required, 0)
    if actual_rank >= required_rank:
        return 1.0
    elif actual_rank >= required_rank - 1:
        return 0.5
    return 0.0


def _text_similarity(text1: str, text2: str) -> float:
    """TF-IDF 余弦相似度"""
    words1 = _tokenize(text1)
    words2 = _tokenize(text2)
    if not words1 or not words2:
        return 0.0

    tf1 = Counter(words1)
    tf2 = Counter(words2)
    all_words = set(tf1.keys()) | set(tf2.keys())

    dot = sum(tf1.get(w, 0) * tf2.get(w, 0) for w in all_words)
    norm1 = math.sqrt(sum(v * v for v in tf1.values()))
    norm2 = math.sqrt(sum(v * v for v in tf2.values()))

    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _tokenize(text: str) -> list:
    text = text.lower()
    text = re.sub(r'[^\w\u4e00-\u9fff]', ' ', text)
    en_words = re.findall(r'[a-z][a-z0-9+#.]*', text)
    cn_chars = re.findall(r'[\u4e00-\u9fff]{2,}', text)
    cn_bigrams = []
    for phrase in cn_chars:
        for i in range(len(phrase) - 1):
            bigram = phrase[i:i + 2]
            if bigram not in STOPWORDS:
                cn_bigrams.append(bigram)
    return en_words + cn_bigrams


def _transition(db: Session, resume: Resume, new_status: ResumeStatus, action: str, detail: str):
    old_status = resume.status if isinstance(resume.status, str) else resume.status.value
    resume.status = new_status
    _log_pipeline(db, resume, old_status, new_status.value, action, detail)


def _log_pipeline(db: Session, resume: Resume, from_s: str, to_s: str, action: str, detail: str):
    db.add(PipelineLog(
        resume_id=resume.id,
        from_status=from_s,
        to_status=to_s,
        action=action,
        detail=detail,
    ))
