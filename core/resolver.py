"""链接解析器：从消息文本/组件中提取 B站标识符（BV/AV/CV/opus/短链）。

所有方法均为静态方法，无状态、无副作用，方便测试。
"""

import re
from typing import Any, Sequence
from urllib.parse import parse_qs, urlparse

from astrbot.api.message_components import Json

from .constants import (
    AV_PATTERN,
    BV_PATTERN,
    CV_PATTERN,
    OPUS_PATTERN,
    SHORT_URL_PATTERN,
    URL_PATTERN,
)
from .utils import extract_json_url, strip_punctuation


def _extract_page(url: str) -> int:
    """从 URL 查询参数中提取分P页码（默认 1）。"""
    try:
        return max(1, int(parse_qs(urlparse(url).query).get("p", ["1"])[0]))
    except Exception:
        return 1


class LinkResolver:
    """从消息中提取 B站内容标识符。

    返回值: (bvid_or_aid_or_url, source_kind, page_num)

    source_kind 取值:
        "article" — 专栏 cv
        "opus"    — 图文动态
        "code"    — 纯 BV/AV 号（非 URL）
        "link"    — 完整 URL 中的 BV/AV
        "short"   — b23.tv / bili2233.cn 短链
    """

    @staticmethod
    def extract_target(messages: Sequence[Any], text: str) -> tuple[str | None, str, int]:
        """从消息列表和文本中提取 (标识符, 类型, 页码)。"""
        # 1. 文本
        if text and not text.startswith("/"):
            result = LinkResolver._from_text(text.strip())
            if result:
                return result

        # 2. 消息组件（QQ 小程序卡片等）
        for comp in messages:
            if isinstance(comp, Json):
                card_url = extract_json_url(comp.data)
                if card_url:
                    return LinkResolver._from_text(card_url)

        return None, "", 1

    @staticmethod
    def _from_text(text: str) -> tuple[str | None, str, int]:
        """从一段文本中提取 B站标识符。

        优先级: CV（专栏） > OPUS（动态） > BV > AV > 完整 URL。
        """
        # 专栏 cv
        m = CV_PATTERN.search(text)
        if m:
            return m.group(1), "article", 1
        # 图文动态 opus
        m = OPUS_PATTERN.search(text)
        if m:
            return m.group(1), "opus", 1
        # BV 号
        m = BV_PATTERN.search(text)
        if m:
            return m.group("bvid"), "code", _extract_page(text)
        # AV 号
        m = AV_PATTERN.search(text)
        if m:
            return m.group("avid"), "code", _extract_page(text)
        # 完整 URL
        m = URL_PATTERN.search(text)
        if m:
            url = strip_punctuation(m.group("url"))
            # URL 中也要区分内容类型
            bm = CV_PATTERN.search(url)
            if bm:
                return bm.group(1), "article", 1
            bm = OPUS_PATTERN.search(url)
            if bm:
                return bm.group(1), "opus", 1
            bm = BV_PATTERN.search(url)
            if bm:
                return bm.group("bvid"), "link", _extract_page(url)
            am = AV_PATTERN.search(url)
            if am:
                return am.group("avid"), "link", _extract_page(url)
            if SHORT_URL_PATTERN.search(url):
                return url, "short", 1
        return None, "", 1
