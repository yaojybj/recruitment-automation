"""
Boss 直聘插件通信适配器
通过本地 HTTP API 与已有的 Boss 直聘自动打招呼/收简历插件通信
支持：发送消息、查询聊天列表、匹配候选人、获取回复
"""

from __future__ import annotations

import time
from datetime import datetime

import requests

from models.candidate import Candidate, CandidateMatchStatus, TouchStatus
from utils.logger import get_logger


class BossPluginError(Exception):
    pass


class BossPluginAdapter:
    """与 Boss 直聘插件的本地 API 通信"""

    def __init__(self, api_url: str = "http://localhost:8800",
                 timeout: int = 10, retry_max: int = 3):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.retry_max = retry_max
        self.logger = get_logger()

    def _request(self, method: str, path: str,
                 json_data: dict | None = None,
                 params: dict | None = None) -> dict:
        url = f"{self.api_url}{path}"
        last_error = None

        for attempt in range(1, self.retry_max + 1):
            try:
                resp = requests.request(
                    method, url,
                    json=json_data, params=params,
                    timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()

                self.logger.audit(
                    action=f"boss_{method.lower()}",
                    module="boss_plugin",
                    target=path,
                    result="success",
                    details={"status_code": resp.status_code}
                )
                return data

            except requests.exceptions.RequestException as e:
                last_error = e
                self.logger.warning(
                    f"Boss插件请求失败 (第{attempt}次): {path} - {e}"
                )
                if attempt < self.retry_max:
                    time.sleep(2 * attempt)

        self.logger.audit(
            action=f"boss_{method.lower()}",
            module="boss_plugin",
            target=path,
            result="failed",
            details={"error": str(last_error)}
        )
        raise BossPluginError(f"Boss插件请求失败: {last_error}")

    def is_plugin_alive(self) -> bool:
        """检查插件是否在线"""
        try:
            self._request("GET", "/health")
            return True
        except BossPluginError:
            return False

    def get_chat_list(self, keyword: str = "",
                      page: int = 1,
                      page_size: int = 50) -> list[dict]:
        """
        获取 Boss 直聘聊天列表
        返回: [{"chat_id": "...", "candidate_name": "...", "position": "...", "last_message": "...", "last_time": "..."}]
        """
        data = self._request("GET", "/chats", params={
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
        })
        return data.get("data", [])

    def get_chat_messages(self, chat_id: str,
                          since: str = "") -> list[dict]:
        """
        获取指定聊天的消息记录
        since: ISO时间字符串，只返回该时间之后的消息
        """
        params = {"chat_id": chat_id}
        if since:
            params["since"] = since
        data = self._request("GET", "/chat/messages", params=params)
        return data.get("data", [])

    def send_message(self, chat_id: str, message: str) -> dict:
        """向候选人发送消息"""
        data = self._request("POST", "/chat/send", json_data={
            "chat_id": chat_id,
            "message": message,
        })
        self.logger.audit(
            action="send_message",
            module="boss_plugin",
            target=chat_id,
            result="success",
            details={"message_preview": message[:80]}
        )
        return data

    def match_candidate_in_chats(self, name: str,
                                  position: str) -> Candidate:
        """
        按姓名+应聘职位匹配 Boss 聊天列表中的候选人
        返回匹配后的 Candidate 对象（含匹配状态）
        """
        candidate = Candidate(name=name, applied_position=position)

        chats = self.get_chat_list(keyword=name)

        matches = []
        for chat in chats:
            chat_name = chat.get("candidate_name", "")
            chat_position = chat.get("position", "")
            if chat_name == name:
                if position and chat_position and position in chat_position:
                    matches.insert(0, chat)
                else:
                    matches.append(chat)

        if len(matches) == 1:
            candidate.boss_chat_id = matches[0]["chat_id"]
            candidate.boss_candidate_id = matches[0].get("candidate_id", "")
            candidate.match_status = CandidateMatchStatus.MATCHED
            self.logger.info(f"Boss候选人匹配成功: {name} -> chat_id={candidate.boss_chat_id}")

        elif len(matches) > 1:
            exact = [m for m in matches
                     if m.get("position", "") and position in m.get("position", "")]
            if len(exact) == 1:
                candidate.boss_chat_id = exact[0]["chat_id"]
                candidate.boss_candidate_id = exact[0].get("candidate_id", "")
                candidate.match_status = CandidateMatchStatus.MATCHED
                self.logger.info(f"Boss候选人精确匹配: {name} -> chat_id={candidate.boss_chat_id}")
            else:
                candidate.match_status = CandidateMatchStatus.AMBIGUOUS
                self.logger.warning(
                    f"Boss候选人匹配歧义: {name}, 找到 {len(matches)} 个同名候选人，需人工确认"
                )

        else:
            candidate.match_status = CandidateMatchStatus.UNMATCHED
            self.logger.warning(f"Boss候选人未匹配: {name}")

        self.logger.audit(
            action="match_candidate",
            module="boss_plugin",
            target=name,
            result=candidate.match_status.value,
            details={"position": position, "match_count": len(matches)}
        )
        return candidate

    def get_candidate_latest_reply(self, chat_id: str,
                                    since: str = "") -> dict | None:
        """
        获取候选人最新回复（排除自己发送的消息）
        返回: {"content": "...", "time": "...", "is_candidate": True} 或 None
        """
        messages = self.get_chat_messages(chat_id, since=since)
        candidate_msgs = [m for m in messages if m.get("is_candidate", False)]

        if candidate_msgs:
            latest = candidate_msgs[-1]
            return {
                "content": latest.get("content", ""),
                "time": latest.get("time", ""),
                "is_candidate": True,
            }
        return None

    def send_scheduling_message(self, chat_id: str, message: str,
                                 candidate: Candidate) -> bool:
        """发送约面消息并更新候选人状态"""
        try:
            self.send_message(chat_id, message)
            candidate.last_message_sent_at = datetime.now().isoformat()
            candidate.total_messages_sent += 1

            if candidate.touch_status == TouchStatus.NOT_CONTACTED:
                candidate.touch_status = TouchStatus.FIRST_SENT
            elif candidate.touch_status == TouchStatus.FIRST_SENT:
                candidate.touch_status = TouchStatus.FOLLOWUP_1_SENT
            elif candidate.touch_status == TouchStatus.FOLLOWUP_1_SENT:
                candidate.touch_status = TouchStatus.FOLLOWUP_2_SENT

            return True

        except BossPluginError as e:
            self.logger.error(f"发送约面消息失败: {candidate.name} - {e}")
            return False
