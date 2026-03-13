"""
时间匹配引擎
解析候选人回复的时间关键词，与面试官可面时间做交集匹配
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from models.interview import TimeSlot
from utils.config_loader import get_reply_patterns
from utils.logger import get_logger


WEEKDAY_MAP = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class TimeMatcher:
    def __init__(self):
        self.logger = get_logger()

    def parse_candidate_reply(self, reply: str,
                               available_slots: list[TimeSlot]) -> dict:
        """
        解析候选人回复
        返回:
            {"type": "selected", "slot_index": int, "slot": TimeSlot}
            {"type": "time_direct", "parsed_time": str}
            {"type": "rejected"}
            {"type": "unknown", "raw": str}
        """
        reply = reply.strip()

        if self._is_rejection(reply):
            return {"type": "rejected"}

        slot_idx = self._parse_number_selection(reply)
        if slot_idx is not None and 0 <= slot_idx < len(available_slots):
            return {
                "type": "selected",
                "slot_index": slot_idx,
                "slot": available_slots[slot_idx],
            }

        parsed_time = self._parse_direct_time(reply)
        if parsed_time:
            return {
                "type": "time_direct",
                "parsed_time": parsed_time,
            }

        return {"type": "unknown", "raw": reply}

    def match_time(self, candidate_result: dict,
                   interviewer_slots: list[TimeSlot]) -> TimeSlot | None:
        """
        将候选人选择/回复的时间与面试官时间做匹配
        返回匹配的 TimeSlot 或 None
        """
        if candidate_result["type"] == "selected":
            return candidate_result["slot"]

        if candidate_result["type"] == "time_direct":
            parsed = candidate_result["parsed_time"]
            return self._find_matching_slot(parsed, interviewer_slots)

        return None

    def get_best_slot(self, slots: list[TimeSlot]) -> TimeSlot | None:
        """选出最优时间：优先 > 普通 > 备选，同优先级取最早"""
        if not slots:
            return None

        priority_order = {"优先": 0, "普通": 1, "备选": 2}
        sorted_slots = sorted(
            slots,
            key=lambda s: (
                priority_order.get(s.priority, 1),
                s.date,
                s.start_time,
            )
        )
        return sorted_slots[0]

    def format_time_options(self, slots: list[TimeSlot]) -> str:
        """格式化时间选项列表（用于发送给候选人）"""
        lines = []
        for i, slot in enumerate(slots, 1):
            priority_tag = f" ({slot.priority})" if slot.priority != "普通" else ""
            lines.append(
                f"【{i}】{slot.date} {slot.weekday} "
                f"{slot.start_time}-{slot.end_time}{priority_tag}"
            )
        return "\n".join(lines)

    def _is_rejection(self, reply: str) -> bool:
        rejection_keywords = [
            "不考虑", "暂不考虑", "不方便", "放弃", "不去了",
            "已找到工作", "已入职", "拒绝", "不面了", "算了",
        ]
        return any(kw in reply for kw in rejection_keywords)

    def _parse_number_selection(self, reply: str) -> int | None:
        """解析编号选择，如 "选1" "选择2" "1号" "第3个" "【2】" """
        patterns = [
            r"选择?\s*(\d+)",
            r"(\d+)\s*号",
            r"第\s*(\d+)\s*个",
            r"【(\d+)】",
            r"^(\d)$",
        ]
        for pattern in patterns:
            m = re.search(pattern, reply)
            if m:
                return int(m.group(1)) - 1
        return None

    def _parse_direct_time(self, reply: str) -> str | None:
        """
        解析直接时间表述
        如 "3月15日14点" -> "2026-03-15 14:00"
           "周三14点" -> 最近的周三 14:00
        """
        # "X月X日X点"
        m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]\s*(\d{1,2})\s*[点时:]?\s*(\d{0,2})", reply)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            hour = int(m.group(3))
            minute = int(m.group(4)) if m.group(4) else 0
            year = datetime.now().year
            return f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"

        # "周X X点"
        m = re.search(r"(?:周|星期)([一二三四五六日天\d])\s*(\d{1,2})\s*[点时:]?\s*(\d{0,2})", reply)
        if m:
            wd_char = m.group(1)
            hour = int(m.group(2))
            minute = int(m.group(3)) if m.group(3) else 0
            target_wd = WEEKDAY_MAP.get(wd_char)
            if target_wd is not None:
                target_date = self._next_weekday(target_wd)
                return f"{target_date} {hour:02d}:{minute:02d}"

        # "M/D HH:MM"
        m = re.search(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", reply)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            hour = int(m.group(3))
            minute = int(m.group(4))
            year = datetime.now().year
            return f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"

        return None

    def _next_weekday(self, target_weekday: int) -> str:
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        target = today + timedelta(days=days_ahead)
        return target.strftime("%Y-%m-%d")

    def _find_matching_slot(self, parsed_time: str,
                            slots: list[TimeSlot]) -> TimeSlot | None:
        """在面试官时间列表中查找匹配的时段"""
        parts = parsed_time.split(" ")
        if len(parts) != 2:
            return None
        date_str = parts[0]
        time_str = parts[1]

        for slot in slots:
            if slot.date == date_str:
                if slot.start_time <= time_str and time_str <= slot.end_time:
                    return slot

        for slot in slots:
            if slot.date == date_str:
                return slot

        return None
