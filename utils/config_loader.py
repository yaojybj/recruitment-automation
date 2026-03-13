"""配置文件加载器 - YAML配置统一管理"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import yaml


CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_yaml(filename: str) -> dict:
    filepath = CONFIG_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"配置文件不存在: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_settings() -> dict:
    return load_yaml("settings.yaml")


def get_screening_rules(position: str | None = None) -> dict:
    """获取筛选规则，优先使用职位专属规则，缺失字段回退到默认规则"""
    rules = load_yaml("screening_rules.yaml")
    default = rules.get("default", {})

    if position and position in rules.get("positions", {}):
        pos_rules = rules["positions"][position]
        merged = _deep_merge(default, pos_rules)
        return merged

    return default


def get_message_template(position: str | None, template_key: str) -> str:
    """获取话术模板，优先使用职位专属模板"""
    templates = load_yaml("message_templates.yaml")

    if position and position in templates.get("positions", {}):
        pos_templates = templates["positions"][position]
        if template_key in pos_templates:
            return pos_templates[template_key]

    return templates.get("default", {}).get(template_key, "")


def get_reply_patterns() -> dict:
    templates = load_yaml("message_templates.yaml")
    return templates.get("reply_patterns", {})


def get_education_levels() -> dict:
    rules = load_yaml("screening_rules.yaml")
    return rules.get("education_levels", {})


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并字典，override 覆盖 base"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def reload_settings():
    """清除缓存，重新加载配置"""
    get_settings.cache_clear()
