"""
Moka 同步助手（手动模式）
Moka API 因集团权限不可用，改为：
- 系统内完成所有审核/约面流程
- 面试确定后生成 Moka 录入指引，HR 手动录入一次即可
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from ..models import Resume, Position, InterviewSlot

logger = logging.getLogger(__name__)


def generate_moka_entry_guide(
    db: Session,
    resume: Resume,
    position: Position,
    slot: InterviewSlot | None = None,
) -> dict:
    """
    生成 Moka 手动录入指引。
    HR 在面试安排确定后，按指引在 Moka 中录入候选人和面试信息。
    """
    candidate_info = {
        "姓名": resume.candidate_name or "",
        "手机": resume.phone or "",
        "邮箱": resume.email or "",
        "学历": resume.education or "",
        "工作年限": f"{resume.work_years}年" if resume.work_years else "",
        "当前公司": resume.current_company or "",
        "当前职位": resume.current_position or "",
    }

    guide_lines = [
        f"=== Moka 录入指引 ===",
        f"",
        f"【候选人信息】",
    ]
    for k, v in candidate_info.items():
        if v:
            guide_lines.append(f"  {k}: {v}")

    guide_lines.append(f"")
    guide_lines.append(f"【应聘岗位】{position.title}")
    if position.department:
        guide_lines.append(f"【部门】{position.department}")

    guide_lines.append(f"【JD匹配分】{resume.jd_match_score or '-'}")

    if slot:
        guide_lines.append(f"")
        guide_lines.append(f"【面试安排】")
        guide_lines.append(f"  日期: {slot.date}")
        guide_lines.append(f"  时间: {slot.start_time} - {slot.end_time}")
        if slot.interviewer_name:
            guide_lines.append(f"  面试官: {slot.interviewer_name}")
        if slot.is_online:
            guide_lines.append(f"  方式: 线上面试")
            if slot.meeting_link:
                guide_lines.append(f"  会议链接: {slot.meeting_link}")
        else:
            guide_lines.append(f"  方式: 线下面试")
            if slot.location:
                guide_lines.append(f"  地点: {slot.location}")

    guide_lines.append(f"")
    guide_lines.append(f"【操作步骤】")
    guide_lines.append(f"  1. 打开 Moka → 找到「{position.title}」岗位")
    guide_lines.append(f"  2. 添加候选人 → 填入以上信息")
    if slot:
        guide_lines.append(f"  3. 进入候选人详情 → 安排面试")
        guide_lines.append(f"  4. 选择面试时间 {slot.date} {slot.start_time}")
        if slot.interviewer_name:
            guide_lines.append(f"  5. 添加面试官: {slot.interviewer_name}")

    return {
        "guide_text": "\n".join(guide_lines),
        "candidate_info": candidate_info,
        "position_title": position.title,
        "has_interview": slot is not None,
    }
