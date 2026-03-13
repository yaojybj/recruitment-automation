"""统一日志系统 - 记录所有操作，支持导出排查"""

from __future__ import annotations

import logging
import os
import json
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class OperationLogger:
    """操作日志记录器，分离系统日志与操作审计日志"""

    def __init__(self, log_dir: str = "./data/logs", level: str = "INFO",
                 max_size_mb: int = 50, backup_count: int = 10,
                 log_to_console: bool = True):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._system_logger = self._create_logger(
            "recruitment_controller",
            self.log_dir / "system.log",
            level, max_size_mb, backup_count, log_to_console
        )

        self._audit_logger = self._create_logger(
            "audit",
            self.log_dir / "audit.log",
            "INFO", max_size_mb, backup_count, False
        )

    def _create_logger(self, name, filepath, level, max_size_mb,
                       backup_count, console) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        fh = RotatingFileHandler(
            filepath,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        if console:
            ch = logging.StreamHandler()
            ch.setFormatter(fmt)
            logger.addHandler(ch)

        return logger

    def info(self, msg: str, **kwargs):
        self._system_logger.info(msg)
        if kwargs:
            self._system_logger.debug(f"  details: {kwargs}")

    def warning(self, msg: str, **kwargs):
        self._system_logger.warning(msg)
        if kwargs:
            self._system_logger.debug(f"  details: {kwargs}")

    def error(self, msg: str, **kwargs):
        self._system_logger.error(msg)
        if kwargs:
            self._system_logger.error(f"  details: {kwargs}")

    def debug(self, msg: str):
        self._system_logger.debug(msg)

    def audit(self, action: str, module: str, target: str,
              result: str, details: dict | None = None):
        """审计日志：记录每一步操作（筛选、匹配、发送、API调用）"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "module": module,
            "target": target,
            "result": result,
            "details": details or {}
        }
        self._audit_logger.info(json.dumps(record, ensure_ascii=False))

        audit_jsonl = self.log_dir / "audit_records.jsonl"
        with open(audit_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def export_audit_logs(self, output_path: str | None = None,
                          start_date: str | None = None,
                          end_date: str | None = None) -> str:
        """导出审计日志，支持日期过滤"""
        audit_file = self.log_dir / "audit_records.jsonl"
        if not audit_file.exists():
            return "无审计记录"

        records = []
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if start_date and record.get("timestamp", "") < start_date:
                    continue
                if end_date and record.get("timestamp", "") > end_date:
                    continue
                records.append(record)

        if not output_path:
            output_path = str(
                self.log_dir / f"audit_export_{datetime.now():%Y%m%d_%H%M%S}.json"
            )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        return output_path


_logger_instance: OperationLogger | None = None


def get_logger(**kwargs) -> OperationLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = OperationLogger(**kwargs)
    return _logger_instance
