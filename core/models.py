"""数据模型：视频卡片、专栏卡片、图文动态卡片及辅助类型。

所有 dataclass 仅承载数据，不包含业务逻辑（VideoCard.duration_text 除外）。
"""

from dataclasses import dataclass
from pathlib import Path


class SafeFormatDict(dict):
    """安全的格式化字典 —— 当 key 缺失时返回占位符而非抛出 KeyError。"""

    def __missing__(self, key):
        return "{" + key + "}"


@dataclass
class VideoCard:
    """B站视频信息卡片。"""

    aid: int
    bvid: str
    title: str
    link: str
    up_name: str
    cover_url: str
    desc: str
    duration_seconds: int
    pub_ts: int
    view: int
    like: int
    danmaku: int
    reply: int = 0
    favorite: int = 0
    coin: int = 0
    share: int = 0
    up_face_url: str = ""
    tname: str = ""
    video_path: Path | None = None
    cid: int = 0  # 第一P的cid，用于获取AI总结
    pages: list = None  # 所有P的信息 [{page, part, duration}, ...]
    downloaded_pages: list = None  # 已下载的P号列表（多P模式用于汇总卡片显示）

    def __post_init__(self):
        if self.pages is None:
            self.pages = []
        if self.downloaded_pages is None:
            self.downloaded_pages = []

    @property
    def page_count(self) -> int:
        """总 P 数（至少 1）。"""
        return max(1, len(self.pages)) if self.pages is not None else 1

    @property
    def duration_text(self) -> str:
        """将秒数格式化为 MM:SS 或 HH:MM:SS。"""
        m, s = divmod(self.duration_seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@dataclass
class ArticleCard:
    """B站专栏文章信息卡片。"""

    cv_id: str
    title: str
    author: str
    url: str
    summary: str
    content_md: str
    cover_url: str = ""
    image_urls: list = None

    def __post_init__(self):
        if self.image_urls is None:
            self.image_urls = []


@dataclass
class OpusCard:
    """B站图文动态信息卡片。"""

    opus_id: str
    author: str
    author_face: str
    content: str
    images: list
    like_count: int
    comment_count: int
    forward_count: int
    pub_ts: int
    url: str


@dataclass
class DownloadPlan:
    """下载计划：由 BilibiliService.prepare_download 生成。

    将 get_download_url 的结果缓存起来，供预估大小与实际下载共用，
    避免对 B站 API 重复请求（重复请求易触发风控限流）。
    """

    video_url: str
    audio_url: str = ""
    video_bandwidth: int = 0
    audio_bandwidth: int = 0
    actual_quality: str = ""
    duration_s: int = 0
    stem: str = "video"
    page_idx: int = 0
