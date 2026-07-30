"""AstrBot B站内容解析插件

功能:
1. 被动解析：自动识别消息中的 B站链接，发送文本卡片 + 封面图
2. 手动下载：/bili下载 <链接> 下载并发送视频文件
3. 自动下载：管理员控制群内自动下载
4. 扫码登录：/bili 登录
5. 状态查询：/bili 状态
"""

import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Image, Json, Plain, Video as MessageVideo
from astrbot.api.star import Context, Star, StarTools

from bilibili_api import Credential, select_client, request_settings
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents
from bilibili_api.user import get_self_info
from bilibili_api.comment import CommentResourceType, OrderType, get_comments
from bilibili_api.video import (
    AudioStreamDownloadURL,
    Video,
    VideoCodecs,
    VideoDownloadURLDataDetecter,
    VideoQuality,
    VideoStreamDownloadURL,
)

PLUGIN_NAME = "astrbot_plugin_parse_bilicomp"

# ── URL 正则 ─────────────────────────────────────────

BV_PATTERN = re.compile(r"\b(?P<bvid>BV[0-9A-Za-z]{10})\b")
AV_PATTERN = re.compile(r"\b(?P<avid>av\d{6,})\b", re.IGNORECASE)
URL_PATTERN = re.compile(
    r'(?P<url>(?:https?://)?(?:www\.)?(?:b23\.tv|bili2233\.cn|(?:m\.)?bilibili\.com|space\.bilibili\.com)[^\s<>"\']+)',
    re.IGNORECASE,
)
SHORT_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:b23\.tv|bili2233\.cn)/", re.IGNORECASE
)
TRAILING_PUNCTUATION = "'\"）)]】}>，。！？；：,.!?;:"

# ── 图标字体 ─────────────────────────────────────────

FONT_PATH = Path(__file__).parent / "vanfont.ttf"
FONT_BASE64_CONTENT = ""
try:
    if FONT_PATH.exists():
        with open(FONT_PATH, "rb") as f:
            font_bytes = f.read()
        FONT_BASE64_CONTENT = base64.b64encode(font_bytes).decode()
        logger.debug("成功加载并编码 vanfont.ttf")
    else:
        logger.error(f"图标字体文件未找到: {FONT_PATH}")
except Exception as e:
    logger.error(f"加载或编码 vanfont.ttf 时出错: {e}")

# ── 默认模板 ─────────────────────────────────────────

DEFAULT_PARSE_TEMPLATE = (
    "📺 {title}\n"
    "UP: {up_name}\n"
    "时长: {duration}\n"
    "发布时间: {pub_time}\n"
    "播放: {view}  点赞: {like}  弹幕: {danmaku}\n"
    "简介: {desc}\n"
    "链接: {link}"
)

# ── HTML 卡片模板 ─────────────────────────────────────

VIDEO_CARD_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  @font-face {
    font-family: 'van';
    src: url(data:font/truetype;base64,{{ font_van_base64 }}) format('truetype');
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    margin: 0; padding: 0;
    background-color: #ffffff;
    width: 750px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  }
  .card {
    position: relative; display: inline-block;
    width: 750px; padding: 0;
    background-color: #ffffff;
    border-radius: 12px;
    box-shadow: 0 5px 20px rgba(251, 114, 153, 0.15);
    overflow: hidden;
    margin: 0;
  }
  .video-cover {
    position: relative; margin-bottom: 0; overflow: hidden;
  }
  .video-cover .cover-img {
    width: 100%; height: auto; display: block;
    aspect-ratio: 16 / 9; object-fit: cover;
  }
  .video-cover .category {
    position: absolute; top: 12px; right: 12px;
    border-radius: 6px; font-size: 22px; line-height: 1.4;
    background-color: rgba(0, 0, 0, 0.4); color: #ffffff;
    padding: 5px 10px; font-weight: 500;
  }
  .video-cover .duration {
    position: absolute; bottom: 8px; right: 12px;
    border-radius: 6px; font-size: 24px; line-height: 1.4;
    background-color: rgba(0, 0, 0, 0.6); color: #ffffff;
    padding: 4px 10px;
  }
  .up {
    display: flex; align-items: center;
    padding: 15px 20px;
    border-bottom: 1px solid #f0f0f0;
  }
  .up .avatar {
    width: 70px; height: 70px; border: 1px solid #eee;
    border-radius: 50%; object-fit: cover;
    margin-right: 12px;
  }
  .up .name {
    font-size: 28px; font-weight: 500; color: #fb7299;
    overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
  }
  .video-info {
    width: 100%; padding: 18px 22px 15px 22px;
  }
  .video-info .title {
    font-size: 32px; font-weight: 600; line-height: 1.45;
    margin-bottom: 12px; color: #1a1a1a;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;
  }
  .video-info .meta {
    display: flex; justify-content: space-between;
    margin-top: 8px; margin-bottom: 15px;
    font-size: 24px; color: #999;
  }
  .video-info .summary {
    margin-bottom: 18px; font-size: 25px; color: #666;
    line-height: 1.6; word-wrap: break-word;
    display: -webkit-box; -webkit-line-clamp: 3;
    -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;
    border-left: 3px solid #fce4ec; padding-left: 10px;
  }
  .video-info .stats {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 18px 10px; font-size: 24px; color: #555;
    text-align: center;
    border-top: 1px solid #f0f0f0; padding-top: 15px;
  }
  .video-info .stats > span {
    display: flex; flex-direction: column; align-items: center;
  }
  .video-info .stats > span::before {
    display: block; font-family: 'van';
    font-size: 42px; margin-bottom: 4px; color: #fb7299;
  }
  .video-info .stats .view::before   { content: "\\e6e6"; }
  .video-info .stats .dm::before     { content: "\\e6e7"; }
  .video-info .stats .like::before   { content: "\\e6e0"; }
  .video-info .stats .coin::before   { content: "\\e6e4"; }
  .video-info .stats .fav::before    { content: "\\e6e1"; }
  .video-info .stats .share::before  { content: "\\e70f"; }
  .video-info .stats .reply::before  { content: "\\e639"; }

  .comments {
    padding: 10px 18px 15px 18px;
    border-top: 1px solid #f0f0f0; margin-top: 10px;
  }
  .comments-title {
    font-size: 25px; font-weight: 600; color: #555; margin-bottom: 8px;
  }
  .comment-item {
    font-size: 24px; line-height: 1.5; margin-bottom: 8px; color: #333;
    display: flex; align-items: flex-start;
  }
  .comment-item:last-child { margin-bottom: 0; }
  .commenter {
    color: #fb7299; font-weight: 500; margin-right: 5px;
    white-space: nowrap;
  }
  .comment-text {
    word-break: break-all; flex-grow: 1;
  }
  .comment-likes {
    font-size: 22px; color: #999; margin-left: 8px; white-space: nowrap;
  }
  .comment-likes::before {
    font-family: 'van'; content: "\\e6e0"; font-size: 22px;
    margin-right: 2px; vertical-align: -1px;
  }

  .portal {
    position: relative; width: 100%; height: 70px;
    background-color: #fff8fa; margin-top: 0;
    display: flex; align-items: center; justify-content: center;
    padding: 0 22px; border-top: 1px solid #f0f0f0;
  }
  .portal .bili-logo {
    font-size: 28px; font-weight: bold; color: #fb7299; margin: 0 auto;
  }
</style>
</head>
<body>
<div class="card">
  {% if cover %}
  <div class="video-cover">
    <img class="cover-img" src="{{ cover }}" alt=""/>
    <span class="category">{{ tname }}</span>
    <span class="duration">{{ duration }}</span>
  </div>
  {% endif %}
  <div class="up">
    {% if up_face %}<img class="avatar" src="{{ up_face }}" alt=""/>{% endif %}
    <span class="name">{{ up_name }}</span>
  </div>
  <div class="video-info">
    <div class="title">{{ title }}</div>
    <div class="meta">
      <span>发布于: {{ pub_time }}</span>
      <span>{{ avid }}</span>
    </div>
    {% if desc %}<div class="summary">{{ desc }}</div>{% endif %}
    <div class="stats">
      <span class="view">{{ view }}<br>播放</span>
      <span class="dm">{{ danmaku }}<br>弹幕</span>
      <span class="like">{{ like }}<br>点赞</span>
      <span class="coin">{{ coin }}<br>投币</span>
      <span class="fav">{{ favorite }}<br>收藏</span>
      <span class="share">{{ share }}<br>分享</span>
      <span class="reply">{{ reply }}<br>评论</span>
      <span></span>
    </div>
    {% if comments %}
    <div class="comments">
      <div class="comments-title">热门评论</div>
      {% for c in comments %}
      <div class="comment-item">
        <span class="commenter">{{ c.uname }}:</span>
        <span class="comment-text">{{ c.text }}</span>
        {% if c.likes %}<span class="comment-likes">{{ c.likes }}</span>{% endif %}
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>
  <div class="portal">
    <span class="bili-logo">bilibili</span>
  </div>
</div>
</body>
</html>'''

# ── 数据模型 ─────────────────────────────────────────

@dataclass
class VideoCard:
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

    @property
    def duration_text(self) -> str:
        m, s = divmod(self.duration_seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


# ── 辅助函数 ─────────────────────────────────────────

def safe_int(value, default=0, minimum=None, maximum=None):
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
    return value.strip().rstrip(TRAILING_PUNCTUATION)


def format_count(value):
    v = max(0, int(value))
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}亿"
    if v >= 10_000:
        return f"{v / 10_000:.1f}万"
    return str(v)


def format_timestamp(ts):
    if ts <= 0:
        return "未知"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def sanitize_desc(desc, limit=120):
    cleaned = " ".join(str(desc or "").split())
    if limit <= 0:
        return cleaned
    return cleaned[:limit - 1] + "…" if len(cleaned) > limit else cleaned


def extract_json_url(data) -> str | None:
    """从 Comp.Json data 中提取 B站 URL"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return None
    if not isinstance(data, dict):
        return None

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

    for value in _iter_strings(data):
        match = URL_PATTERN.search(value)
        if match:
            return strip_punctuation(match.group("url"))
        match = BV_PATTERN.search(value)
        if match:
            return match.group("bvid")
    return None


def _iter_strings(payload):
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for v in payload.values():
            yield from _iter_strings(v)
    elif isinstance(payload, list):
        for v in payload:
            yield from _iter_strings(v)


# ── 凭证管理 ─────────────────────────────────────────

class CredentialManager:
    def __init__(self, data_dir: Path, config: AstrBotConfig):
        self._file = data_dir / "credential.json"
        self._config = config
        self._credential: Credential | None = None
        self._qr: QrCodeLogin | None = None
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                self._credential = Credential.from_cookies(data)
            except Exception as e:
                logger.error(f"加载凭证失败: {e}")

    def _save(self):
        if self._credential:
            self._file.write_text(
                json.dumps(self._credential.get_cookies(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    async def get(self) -> Credential | None:
        # 优先从配置读取
        cookie_str = str(self._config.get("bilibili_cookies", "") or "").strip()
        if cookie_str:
            cookies = {}
            for item in cookie_str.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    cookies[k.strip()] = v.strip()
            if cookies:
                try:
                    cred = Credential.from_cookies(cookies)
                    if await cred.check_valid():
                        self._credential = cred
                        self._save()
                        return cred
                except Exception:
                    pass

        if self._credential:
            try:
                if await self._credential.check_valid():
                    if await self._credential.check_refresh():
                        if self._credential.has_ac_time_value() and self._credential.has_bili_jct():
                            await self._credential.refresh()
                            self._save()
                    return self._credential
            except Exception:
                pass
        return None

    async def login_qrcode(self) -> bytes:
        self._qr = QrCodeLogin()
        await self._qr.generate_qrcode()
        return self._qr.get_qrcode_picture().content

    async def poll_qr(self):
        if not self._qr:
            yield "二维码未生成"
            return
        for _ in range(90):
            try:
                state = await self._qr.check_state()
            except Exception as e:
                yield f"检查失败: {e}"
                return
            if state == QrCodeLoginEvents.DONE:
                self._credential = self._qr.get_credential()
                self._save()
                try:
                    profile = await get_self_info(self._credential)
                    uname = profile.get("name", "未知")
                    yield f"✅ 登录成功！账号: {uname}"
                except Exception:
                    yield "✅ 登录成功！"
                return
            if state == QrCodeLoginEvents.CONF:
                yield "📱 已扫描，请在手机上确认..."
            elif state == QrCodeLoginEvents.TIMEOUT:
                yield "⏰ 二维码已过期"
                return
            await asyncio.sleep(2)
        yield "⏰ 登录超时"

    async def status(self) -> str:
        cred = await self.get()
        if not cred:
            return "❌ 未登录"
        try:
            profile = await get_self_info(cred)
            return f"✅ 已登录: {profile.get('name', '未知')} (UID: {profile.get('mid', '?')})"
        except Exception as e:
            return f"⚠️ 凭证可能无效: {e}"

    async def clear(self):
        self._credential = None
        self._file.unlink(missing_ok=True)


# ── B站服务 ──────────────────────────────────────────

class BilibiliService:
    def __init__(self, client: httpx.AsyncClient, cred_mgr: CredentialManager, cache_dir: Path):
        self._client = client
        self._cred_mgr = cred_mgr
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_video_card(self, bvid: str = "", aid: int = 0, page: int = 1) -> VideoCard:
        cred = await self._cred_mgr.get()
        if aid:
            v = Video(aid=aid, credential=cred)
        elif bvid:
            v = Video(bvid=bvid, credential=cred)
        else:
            raise ValueError("缺少 bvid 或 aid")

        info = await v.get_info()
        pages = info.get("pages") or []
        page_idx = max(0, page - 1)
        if page_idx >= len(pages):
            page_idx = 0
        pg = pages[page_idx] if pages else {}

        owner = info.get("owner", {})
        stat = info.get("stat", {})
        _bvid = str(info.get("bvid", bvid))
        _aid = safe_int(info.get("aid", aid))
        link = f"https://www.bilibili.com/video/{_bvid}"
        if page_idx > 0:
            link += f"?p={page_idx + 1}"

        dur = safe_int(pg.get("duration", info.get("duration", 0)))

        # 尝试下载视频
        video_path = None
        try:
            video_path = await self._download_video(v, page_idx)
        except Exception as e:
            logger.debug(f"视频下载失败（将仅发送图文）: {e}")

        return VideoCard(
            aid=_aid, bvid=_bvid, title=str(info.get("title", "")),
            link=link, up_name=str(owner.get("name", "未知UP")),
            cover_url=str(info.get("pic", "")),
            desc=str(info.get("desc", "")),
            up_face_url=str(owner.get("face", "")),
            duration_seconds=dur,
            pub_ts=safe_int(info.get("pubdate", 0)),
            view=safe_int(stat.get("view", 0)),
            like=safe_int(stat.get("like", 0)),
            danmaku=safe_int(stat.get("danmaku", 0)),
            reply=safe_int(stat.get("reply", 0)),
            favorite=safe_int(stat.get("favorite", 0)),
            coin=safe_int(stat.get("coin", 0)),
            share=safe_int(stat.get("share", 0)),
            tname=str(info.get("tname", "")),
            video_path=video_path,
        )

    async def _download_video(self, v: Video, page_idx: int) -> Path | None:
        download_data = await v.get_download_url(page_index=page_idx)
        detecter = VideoDownloadURLDataDetecter(download_data)
        streams = detecter.detect_best_streams(
            video_max_quality=VideoQuality._720P,
            codecs=[VideoCodecs.AVC],
            no_dolby_video=True,
            no_hdr=True,
        )
        if not streams:
            return None

        vs = streams[0]
        video_url = getattr(vs, "url", "")
        if not video_url:
            return None

        bvid = str(getattr(v, "get_bvid", lambda: "")())
        stem = f"{bvid}-p{page_idx + 1}"
        output = self._cache_dir / f"{stem}.mp4"
        if output.exists() and output.stat().st_size > 0:
            return output

        headers = {"Referer": "https://www.bilibili.com/"}
        cred = await self._cred_mgr.get()
        if cred:
            cookie = "; ".join(f"{k}={v}" for k, v in cred.get_cookies().items() if v)
            if cookie:
                headers["Cookie"] = cookie

        audio_stream = streams[1] if len(streams) > 1 else None
        audio_url = getattr(audio_stream, "url", "") if isinstance(audio_stream, AudioStreamDownloadURL) else ""

        if audio_url:
            v_temp = self._cache_dir / f"{stem}.video.m4s"
            a_temp = self._cache_dir / f"{stem}.audio.m4s"
            try:
                await asyncio.gather(
                    self._download(video_url, v_temp, headers),
                    self._download(audio_url, a_temp, headers),
                )
                await self._ffmpeg_merge(v_temp, a_temp, output)
            finally:
                v_temp.unlink(missing_ok=True)
                a_temp.unlink(missing_ok=True)
        else:
            await self._download(video_url, output, headers)

        return output if (output.exists() and output.stat().st_size > 0) else None

    async def _download(self, url: str, path: Path, headers: dict):
        async with self._client.stream("GET", url, headers=headers, timeout=300, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                async for chunk in resp.aiter_bytes(1024 * 1024):
                    f.write(chunk)

    async def _ffmpeg_merge(self, video: Path, audio: Path, output: Path):
        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-c", "copy", "-map", "0:v:0", "-map", "1:a:0", str(output)]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg 合并失败: {stderr.decode(errors='ignore')[:200]}")


# ── URL 解析器 ───────────────────────────────────────

class LinkResolver:
    @staticmethod
    def extract_target(messages: Sequence[Any], text: str) -> tuple[str | None, str, int]:
        """从消息提取 (bvid_or_aid, source_kind, page_num)"""
        # 1. 文本
        if text and not text.startswith("/"):
            result = LinkResolver._from_text(text.strip())
            if result:
                return result

        # 2. 消息组件
        for comp in messages:
            if isinstance(comp, Json):
                card_url = extract_json_url(comp.data)
                if card_url:
                    return LinkResolver._from_text(card_url)

        return None, "", 1

    @staticmethod
    def _from_text(text: str) -> tuple[str | None, str, int]:
        # BV
        m = BV_PATTERN.search(text)
        if m:
            return m.group("bvid"), "code", _extract_page(text)
        # AV
        m = AV_PATTERN.search(text)
        if m:
            return m.group("avid"), "code", _extract_page(text)
        # URL
        m = URL_PATTERN.search(text)
        if m:
            url = strip_punctuation(m.group("url"))
            bm = BV_PATTERN.search(url)
            if bm:
                return bm.group("bvid"), "link", _extract_page(url)
            am = AV_PATTERN.search(url)
            if am:
                return am.group("avid"), "link", _extract_page(url)
            if SHORT_URL_PATTERN.search(url):
                return url, "short", 1
        return None, "", 1


def _extract_page(url: str) -> int:
    from urllib.parse import parse_qs, urlparse
    try:
        return max(1, int(parse_qs(urlparse(url).query).get("p", ["1"])[0]))
    except Exception:
        return 1


# ═════════════════════════════════════════════════════════
# 插件主类
# ═════════════════════════════════════════════════════════

class ParseBilibiliPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config

        # 数据目录
        self._data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self._media_dir = self._data_dir / "media_cache"
        self._auto_dl_file = self._data_dir / "auto_download.json"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._media_dir.mkdir(parents=True, exist_ok=True)

        # HTTP 客户端
        self._client = httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
        )

        # 服务
        self._cred_mgr = CredentialManager(self._data_dir, config)
        self._service = BilibiliService(self._client, self._cred_mgr, self._media_dir)
        self._debounce: dict[str, dict[str, float]] = {}  # umo -> {key: expires_at}

        # 自动下载
        self._auto_dl_groups: set[str] = set()
        self._load_auto_dl()

    # ── 生命周期 ──────────────────────────────────

    async def initialize(self):
        self._load_auto_dl()
        asyncio.create_task(self._cleanup_loop())
        logger.info(f"{PLUGIN_NAME} 已加载")

    async def terminate(self):
        await self._client.aclose()
        logger.info(f"{PLUGIN_NAME} 已卸载")

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(86400)
            try:
                for f in self._media_dir.rglob("*"):
                    if f.is_file():
                        f.unlink(missing_ok=True)
            except Exception:
                pass

    # ── 自动下载配置 ────────────────────────────────

    def _load_auto_dl(self):
        try:
            if self._auto_dl_file.exists():
                data = json.loads(self._auto_dl_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._auto_dl_groups = {str(g) for g in data}
        except Exception:
            pass

    def _save_auto_dl(self):
        self._auto_dl_file.write_text(json.dumps(list(self._auto_dl_groups)), encoding="utf-8")

    # ── 去重 ──────────────────────────────────────

    def _is_debounced(self, umo: str, key: str) -> bool:
        ttl = self.config.get("cache_ttl", 5) * 60
        if ttl <= 0:
            return False
        now = time.time()
        if umo not in self._debounce:
            self._debounce[umo] = {}
        entry = self._debounce[umo]
        if key in entry and entry[key] > now:
            return True
        entry[key] = now + ttl
        # 清理过期
        expired = [k for k, v in entry.items() if v <= now]
        for k in expired:
            del entry[k]
        return False

    # ── 消息构建 ──────────────────────────────────

    def _render_text(self, card: VideoCard) -> str:
        fmt = str(self.config.get("parse_template", "") or DEFAULT_PARSE_TEMPLATE).replace("\\n", "\n")
        payload = SafeFormatDict(
            title=card.title,
            up_name=card.up_name,
            link=card.link,
            bvid=card.bvid,
            aid=str(card.aid),
            duration=card.duration_text,
            pub_time=format_timestamp(card.pub_ts),
            view=format_count(card.view),
            like=format_count(card.like),
            danmaku=format_count(card.danmaku),
            reply=format_count(card.reply),
            favorite=format_count(card.favorite),
            coin=format_count(card.coin),
            share=format_count(card.share),
            tname=card.tname,
            desc=sanitize_desc(card.desc, 120),
        )
        return fmt.format_map(payload)

    async def _download_b64(self, url: str) -> str:
        """下载图片并转为 base64 data URI"""
        if not url:
            return ""
        try:
            resp = await self._client.get(url, follow_redirects=True, timeout=15)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg")
            fmt = "jpeg" if "jpeg" in ct else "png"
            b64 = base64.b64encode(resp.content).decode()
            return f"data:image/{fmt};base64,{b64}"
        except Exception:
            return ""

    async def _fetch_comments(self, oid: int, count: int = 3) -> list[dict]:
        """获取视频热门评论"""
        try:
            c = await get_comments(oid=oid, type_=CommentResourceType.VIDEO, order=OrderType.LIKE)
            result = []
            for cmt in c.get("replies", [])[:count]:
                if cmt and isinstance(cmt, dict) and cmt.get("member") and cmt.get("content"):
                    text = cmt["content"].get("message", "")
                    text = re.sub(r"\[.*?\]", "", text).strip()  # 去掉表情标记
                    if text:
                        result.append({
                            "uname": cmt["member"].get("uname", "未知"),
                            "text": text[:60] + ("..." if len(text) > 60 else ""),
                            "likes": format_count(cmt.get("like", 0)),
                        })
            return result
        except Exception as e:
            logger.debug(f"获取评论失败: {e}")
            return []

    async def _build_card_html_data(self, card: VideoCard) -> dict:
        """构建 HTML 卡片渲染数据（含 base64 封面、UP头像、评论、图标字体）"""
        cover_b64 = await self._download_b64(card.cover_url)
        up_face_b64 = await self._download_b64(card.up_face_url) if card.up_face_url else ""
        comments = await self._fetch_comments(card.aid, count=3)
        return {
            "cover": cover_b64,
            "tname": card.tname or "视频",
            "duration": card.duration_text,
            "title": card.title,
            "up_face": up_face_b64,
            "up_name": card.up_name,
            "pub_time": format_timestamp(card.pub_ts),
            "avid": f"av{card.aid}",
            "view": format_count(card.view),
            "danmaku": format_count(card.danmaku),
            "like": format_count(card.like),
            "coin": format_count(card.coin),
            "favorite": format_count(card.favorite),
            "reply": format_count(card.reply),
            "share": format_count(card.share),
            "desc": sanitize_desc(card.desc, 150),
            "comments": comments,
            "font_van_base64": FONT_BASE64_CONTENT,
        }

    async def _build_chains(self, card: VideoCard) -> list[MessageChain]:
        chains: list[MessageChain] = []
        send_video = self.config.get("send_video", True) and card.video_path is not None
        render_image = self.config.get("render_as_image", True)

        rich_chain = MessageChain()

        if render_image:
            # 尝试 HTML 渲染成图片
            try:
                data = await self._build_card_html_data(card)
                img_url = await self.html_render(VIDEO_CARD_HTML, data, options={"type": "jpeg", "quality": 90, "full_page": True, "clip": {"x": 0, "y": 0, "width": 750, "height": 3000}})
                if img_url:
                    rich_chain.chain.append(Image.fromURL(img_url))
                    chains.append(rich_chain)
                    if send_video:
                        vc = MessageChain()
                        vc.chain.append(MessageVideo.fromFileSystem(str(card.video_path)))
                        chains.append(vc)
                    return chains
            except Exception as e:
                logger.debug(f"HTML 渲染失败，回退文本+封面: {e}")

        # 回退：文本 + 封面URL
        rich_chain.message(self._render_text(card))
        if self.config.get("send_cover", True) and card.cover_url:
            rich_chain.url_image(card.cover_url)
        chains.append(rich_chain)

        if send_video:
            vc = MessageChain()
            vc.chain.append(MessageVideo.fromFileSystem(str(card.video_path)))
            chains.append(vc)

        return chains

    # ═══════════════════════════════════════════════════
    # 被动解析
    # ═══════════════════════════════════════════════════

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not self.config.get("enable_passive_parse", True):
            return
        if str(event.get_sender_id()) == str(event.get_self_id()):
            return

        messages = event.get_messages() or []
        if messages:
            first = messages[0]
            if isinstance(first, At) and str(first.qq) != str(event.get_self_id()):
                return

        bvid_or_url, source_kind, page = LinkResolver.extract_target(
            messages, event.message_str or ""
        )
        if not bvid_or_url:
            return

        umo = event.unified_msg_origin
        key = bvid_or_url
        if self._is_debounced(umo, key):
            return

        # 处理短链接
        bvid = bvid_or_url
        if source_kind == "short":
            bvid = await self._resolve_short(bvid_or_url)

        if not BV_PATTERN.fullmatch(bvid) and not AV_PATTERN.fullmatch(bvid):
            return

        try:
            if AV_PATTERN.fullmatch(bvid):
                aid_val = int(bvid.lstrip("avAV"))
                card = await self._service.fetch_video_card(aid=aid_val, page=page)
            else:
                card = await self._service.fetch_video_card(bvid=bvid, page=page)
        except Exception as e:
            logger.error(f"被动解析失败: {e}")
            return

        # 发送
        chains = await self._build_chains(card)
        for chain in chains:
            if len(chain.chain) == 1 and isinstance(chain.chain[0], MessageVideo):
                try:
                    await self.context.send_message(umo, chain)
                except Exception as e:
                    logger.warning(f"视频发送失败: {e}")
            else:
                yield event.chain_result(chain.chain)

        # 自动下载
        gid = event.get_group_id()
        if gid and str(gid) in self._auto_dl_groups:
            max_dur = safe_int(self.config.get("auto_download_max_duration", 10), 10)
            if max_dur <= 0 or card.duration_seconds <= max_dur * 60:
                if card.video_path:
                    try:
                        vc = MessageChain()
                        vc.chain.append(MessageVideo.fromFileSystem(str(card.video_path)))
                        await self.context.send_message(umo, vc)
                    except Exception as e:
                        logger.warning(f"自动下载发送失败: {e}")

        event.stop_event()

    async def _resolve_short(self, url: str) -> str:
        if not url.startswith("http"):
            url = f"https://{url}"
        try:
            resp = await self._client.get(url, follow_redirects=True)
            final = str(resp.url)
            m = BV_PATTERN.search(final)
            if m:
                return m.group("bvid")
            m = AV_PATTERN.search(final)
            if m:
                return m.group("avid")
        except Exception:
            pass
        return url

    # ═══════════════════════════════════════════════════
    # 指令: /bili下载
    # ═══════════════════════════════════════════════════

    @filter.command("bili下载", alias={"b站下载"})
    async def cmd_download(self, event: AstrMessageEvent, link: str = ""):
        if not link:
            link = event.message_str or ""
        if not link:
            yield event.plain_result("请提供B站链接或视频ID，例如: /bili下载 BV1xx411c7mD")
            return

        messages = event.get_messages() or []
        bvid_or_url, source_kind, page = LinkResolver.extract_target(messages, link)
        if not bvid_or_url:
            # 尝试从完整消息提取
            bvid_or_url, source_kind, page = LinkResolver.extract_target(messages, event.message_str or "")

        if not bvid_or_url:
            yield event.plain_result("未识别到有效的B站链接或BV/AV号")
            return

        if source_kind == "short":
            bvid_or_url = await self._resolve_short(bvid_or_url)

        yield event.plain_result("⏳ 正在获取视频信息...")

        try:
            if AV_PATTERN.fullmatch(bvid_or_url):
                aid_val = int(bvid_or_url.lstrip("avAV"))
                card = await self._service.fetch_video_card(aid=aid_val, page=page)
            else:
                card = await self._service.fetch_video_card(bvid=bvid_or_url, page=page)
        except Exception as e:
            yield event.plain_result(f"获取视频失败: {e}")
            return

        chains = await self._build_chains(card)
        for chain in chains:
            if len(chain.chain) == 1 and isinstance(chain.chain[0], MessageVideo):
                yield event.plain_result(f"✅ {card.title} ({card.duration_text})")
            yield event.chain_result(chain.chain)

    # ═══════════════════════════════════════════════════
    # 指令组: /bili ...
    # ═══════════════════════════════════════════════════

    @filter.command_group("bili")
    def bili(self):
        pass

    @bili.command("下载")
    async def _cmd_dl(self, event: AstrMessageEvent, link: str = ""):
        async for r in self.cmd_download(event, link):
            yield r

    @bili.command("自动下载")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_auto(self, event: AstrMessageEvent, action: str = ""):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("仅限群聊使用")
            return
        gs = str(gid)
        if action == "on":
            if gs in self._auto_dl_groups:
                yield event.plain_result("已开启")
            else:
                self._auto_dl_groups.add(gs)
                self._save_auto_dl()
                yield event.plain_result("✅ 已开启自动下载")
        elif action == "off":
            self._auto_dl_groups.discard(gs)
            self._save_auto_dl()
            yield event.plain_result("✅ 已关闭自动下载")
        else:
            yield event.plain_result("用法: /bili 自动下载 on|off")

    @bili.command("登录")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_login(self, event: AstrMessageEvent):
        try:
            qr = await self._cred_mgr.login_qrcode()
        except Exception as e:
            yield event.plain_result(f"生成二维码失败: {e}")
            return
        yield event.chain_result([Image.fromBytes(qr)])
        yield event.plain_result("请用哔哩哔哩客户端扫码（3分钟内）")
        async for msg in self._cred_mgr.poll_qr():
            yield event.plain_result(msg)

    @bili.command("状态")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_status(self, event: AstrMessageEvent):
        s = await self._cred_mgr.status()
        yield event.plain_result(s)
