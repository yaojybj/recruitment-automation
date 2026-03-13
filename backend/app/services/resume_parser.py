"""
简历解析模块
支持 PDF、Word、纯文本格式的简历解析，
以及 Boss 直聘邮件正文的结构化提取。
"""
from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EDUCATION_LEVELS = ["博士", "硕士", "研究生", "本科", "大专", "专科", "高中", "中专"]
EDUCATION_ORDER = {level: i for i, level in enumerate(EDUCATION_LEVELS)}


def parse_resume_file(file_path: str) -> dict:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf_text(file_path)
    elif suffix in (".docx", ".doc"):
        text = _extract_docx_text(file_path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")

    return extract_structured_data(text)


def parse_boss_email(subject: str, body: str) -> dict:
    """解析 Boss 直聘发送的简历通知邮件"""
    data = extract_structured_data(body)
    title_match = re.search(r"收到.*?(?:的|投递).*?简历", subject)
    if not data.get("candidate_name"):
        name_match = re.search(r"([^\s·]+)\s*(?:投递|应聘)", subject)
        if name_match:
            data["candidate_name"] = name_match.group(1)
    position_match = re.search(r"(?:投递|应聘)[了]?\s*[《「]?(.+?)[》」]?\s*(?:岗位|职位)?", subject)
    if position_match:
        data["applied_position"] = position_match.group(1).strip()
    data["raw_text"] = f"主题: {subject}\n\n{body}"
    return data


def extract_structured_data(text: str) -> dict:
    """从简历文本中提取结构化数据"""
    data = {
        "candidate_name": _extract_name(text),
        "phone": _extract_phone(text),
        "email": _extract_email(text),
        "gender": _extract_gender(text),
        "age": _extract_age(text),
        "education": _extract_education(text),
        "school": _extract_school(text),
        "major": _extract_major(text),
        "work_years": _extract_work_years(text),
        "current_company": _extract_field(text, ["目前公司", "当前公司", "现公司", "所在公司", "在职公司"]),
        "current_position": _extract_field(text, ["目前职位", "当前职位", "现任职位", "在职职位"]),
        "city": _extract_city(text),
        "expected_salary_min": None,
        "expected_salary_max": None,
        "skills": _extract_skills(text),
        "raw_text": text,
    }
    sal_min, sal_max = _extract_salary(text)
    data["expected_salary_min"] = sal_min
    data["expected_salary_max"] = sal_max
    return data


def _extract_pdf_text(file_path: str) -> str:
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
        return "\n".join(texts)
    except Exception as e:
        logger.error(f"PDF 解析失败: {e}")
        return ""


def _extract_docx_text(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception as e:
        logger.error(f"Word 文档解析失败: {e}")
        return ""


def _extract_name(text: str) -> Optional[str]:
    lines = text.strip().split("\n")
    for line in lines[:5]:
        line = line.strip()
        if not line:
            continue
        name_match = re.match(r"^(?:姓\s*名\s*[:：]\s*)?([^\d\s:：@]{2,4})$", line)
        if name_match:
            candidate = name_match.group(1)
            if not any(kw in candidate for kw in ["简历", "求职", "应聘", "联系", "电话", "邮箱"]):
                return candidate
    field_match = re.search(r"(?:姓\s*名|候选人)\s*[:：]\s*(\S{2,4})", text)
    if field_match:
        return field_match.group(1)
    return None


def _extract_phone(text: str) -> Optional[str]:
    match = re.search(r"(?:1[3-9]\d{9})", text)
    return match.group(0) if match else None


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else None


def _extract_gender(text: str) -> Optional[str]:
    match = re.search(r"(?:性\s*别\s*[:：]\s*)(男|女)", text)
    if match:
        return match.group(1)
    if re.search(r"(?<!\w)男(?:\s|[,，|/·])", text[:200]):
        return "男"
    if re.search(r"(?<!\w)女(?:\s|[,，|/·])", text[:200]):
        return "女"
    return None


def _extract_age(text: str) -> Optional[int]:
    match = re.search(r"(?:年\s*龄\s*[:：]\s*|(\d{2,3})\s*岁)", text)
    if match:
        age_str = match.group(1) or re.search(r"\d+", match.group(0))
        if age_str:
            try:
                val = int(age_str if isinstance(age_str, str) else age_str.group(0))
                if 18 <= val <= 65:
                    return val
            except ValueError:
                pass
    birth_match = re.search(r"(?:19|20)\d{2}\s*[-/年]\s*\d{1,2}", text)
    if birth_match:
        year_m = re.search(r"((?:19|20)\d{2})", birth_match.group(0))
        if year_m:
            from datetime import date
            age = date.today().year - int(year_m.group(1))
            if 18 <= age <= 65:
                return age
    return None


def _extract_education(text: str) -> Optional[str]:
    for level in EDUCATION_LEVELS:
        if level in text:
            return level
    match = re.search(r"(?:学\s*历\s*[:：]\s*)(\S+)", text)
    if match:
        return match.group(1)
    return None


def _extract_school(text: str) -> Optional[str]:
    match = re.search(r"(?:学\s*校|毕业院校|院校)\s*[:：]\s*(.+?)(?:\n|$)", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"(\S+(?:大学|学院|学校))", text)
    if match:
        return match.group(1)
    return None


def _extract_major(text: str) -> Optional[str]:
    match = re.search(r"(?:专\s*业)\s*[:：]\s*(.+?)(?:\n|$|[,，])", text)
    if match:
        return match.group(1).strip()
    return None


def _extract_work_years(text: str) -> Optional[float]:
    match = re.search(r"(\d+)\s*年(?:\s*以上)?(?:工作)?(?:经验|工作经验)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"(?:工作年限|工作经验|经验)\s*[:：]\s*(\d+)", text)
    if match:
        return float(match.group(1))
    return None


def _extract_city(text: str) -> Optional[str]:
    match = re.search(
        r"(?:所在城市|城市|现居|所在地|期望城市|工作地点)\s*[:：]\s*(\S+?)(?:\n|$|[,，])",
        text
    )
    if match:
        return match.group(1).strip()
    return None


def _extract_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    match = re.search(r"(?:期望薪资|薪资|期望薪酬|月薪)\s*[:：]?\s*(\d+)\s*[-~到至]\s*(\d+)\s*[kK千]?", text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if low < 100:
            low *= 1000
        if high < 100:
            high *= 1000
        return low, high
    match = re.search(r"(\d+)\s*[-~到至]\s*(\d+)\s*[kK]", text)
    if match:
        return int(match.group(1)) * 1000, int(match.group(2)) * 1000
    return None, None


def _extract_skills(text: str) -> list[str]:
    match = re.search(r"(?:技能|技术栈|专业技能|技术能力)\s*[:：]\s*(.+?)(?:\n\n|\n[^\s])", text, re.DOTALL)
    if match:
        raw = match.group(1)
        skills = re.split(r"[,，;；、/|·\n]+", raw)
        return [s.strip() for s in skills if s.strip() and len(s.strip()) < 30]
    return []


def _extract_field(text: str, keys: list[str]) -> Optional[str]:
    for key in keys:
        match = re.search(rf"{key}\s*[:：]\s*(.+?)(?:\n|$|[,，])", text)
        if match:
            return match.group(1).strip()
    return None
