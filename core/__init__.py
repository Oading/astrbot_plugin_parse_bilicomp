"""B站内容解析插件 — 核心模块。

重导出常用符号，简化 main.py 的导入。
"""

from .card_builder import CardBuilder
from .constants import (
    AV_PATTERN,
    BV_PATTERN,
    CV_PATTERN,
    OPUS_PATTERN,
    PLUGIN_NAME,
    quality_display,
    resolve_quality,
)
from .credential import CredentialManager
from .models import ArticleCard, OpusCard, VideoCard
from .resolver import LinkResolver
from .service import BilibiliService
from .utils import safe_int

__all__ = [
    "CardBuilder",
    "AV_PATTERN",
    "BV_PATTERN",
    "CV_PATTERN",
    "OPUS_PATTERN",
    "PLUGIN_NAME",
    "quality_display",
    "resolve_quality",
    "CredentialManager",
    "ArticleCard",
    "OpusCard",
    "VideoCard",
    "LinkResolver",
    "BilibiliService",
    "safe_int",
]
