"""工具函数：格式化、解析、清理等纯函数（无副作用，方便单元测试）。"""

import json
import re
import time
from typing import Any, Sequence

from .constants import BV_PATTERN, TRAILING_PUNCTUATION, URL_PATTERN


def safe_int(value, default=0, minimum=None, maximum=None):
    """安全地将值转为 int，支持默认值和边界限制。"""
    try:
        n = int(value)
    except Exception:
        n = default
    if minimum is not None and n < minimum:
        n = minimum
    if maximum is not None and n > maximum:
        n = maximum
    return n


def strip_punctuation(value: str) -> str:
    """去除字符串末尾的中英文标点符号。"""
    return value.strip().rstrip(TRAILING_PUNCTUATION)


def format_count(value) -> str:
    """将数字格式化为中文习惯的 万/亿 单位。"""
    v = max(0, int(value))
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}亿"
    if v >= 10_000:
        return f"{v / 10_000:.1f}万"
    return str(v)


def format_timestamp(ts: int) -> str:
    """Unix 时间戳 → YYYY-MM-DD HH:MM:SS 字符串。"""
    if ts <= 0:
        return "未知"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def format_duration(seconds: int) -> str:
    """将秒数格式化为 MM:SS 或 HH:MM:SS。"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def sanitize_desc(desc: str, limit: int = 120) -> str:
    """合并空白字符并截断文本，超出部分用 … 表示。"""
    cleaned = " ".join(str(desc or "").split())
    if limit <= 0:
        return cleaned
    return cleaned[:limit - 1] + "…" if len(cleaned) > limit else cleaned


def extract_json_url(data) -> str | None:
    """从 QQ 小程序卡片（Comp.Json data）中提取 B站 URL 或 BV 号。"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return None
    if not isinstance(data, dict):
        return None

    # 优先从已知 meta 字段提取
    meta = data.get("meta")
    if isinstance(meta, dict):
        for section_key, url_key in (
            ("detail_1", "qqdocurl"),
            ("news", "jumpUrl"),
            ("music", "jumpUrl"),
            ("music", "musicUrl"),
        ):
            section = meta.get(section_key)
            if isinstance(section, dict):
                url = section.get(url_key)
                if isinstance(url, str) and url:
                    return strip_punctuation(url)

    # 递归扫描所有字符串
    for value in _iter_strings(data):
        match = URL_PATTERN.search(value)
        if match:
            return strip_punctuation(match.group("url"))
        match = BV_PATTERN.search(value)
        if match:
            return match.group("bvid")
    return None


def _iter_strings(payload):
    """递归生成嵌套结构中所有的字符串值。"""
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for v in payload.values():
            yield from _iter_strings(v)
    elif isinstance(payload, list):
        for v in payload:
            yield from _iter_strings(v)
