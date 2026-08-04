"""常量定义：正则模式、HTML 模板、默认配置、图标字体加载。

本模块包含所有在插件各处共享的字面常量，避免散落在业务逻辑中。
"""

import base64
import re
from pathlib import Path

from astrbot.api import logger

# ── 插件标识 ─────────────────────────────────────────────

PLUGIN_NAME = "astrbot_plugin_parse_bilicomp"

# ── URL 正则 ─────────────────────────────────────────────

BV_PATTERN = re.compile(r"\b(?P<bvid>BV[0-9A-Za-z]{10})\b")
AV_PATTERN = re.compile(r"\b(?P<avid>av\d{6,})\b", re.IGNORECASE)
URL_PATTERN = re.compile(
    r'(?P<url>(?:https?://)?(?:www\.)?(?:b23\.tv|bili2233\.cn|(?:m\.)?bilibili\.com|space\.bilibili\.com)[^\s<>"\']+)',
    re.IGNORECASE,
)
SHORT_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:b23\.tv|bili2233\.cn)/", re.IGNORECASE
)
CV_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?bilibili\.com/read/(cv\d+)", re.IGNORECASE
)
OPUS_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.bilibili\.com/opus/|t\.bilibili\.com/)(\d+)", re.IGNORECASE
)
TRAILING_PUNCTUATION = "'\"）)]】}>，。！？；：,.!?;:"

# ── 图标字体 ─────────────────────────────────────────────

FONT_PATH = Path(__file__).parent.parent / "vanfont.ttf"
FONT_BASE64_CONTENT = ""


def _load_font_base64() -> str:
    """加载 vanfont.ttf 并编码为 base64，供 HTML 模板内嵌使用。"""
    try:
        if FONT_PATH.exists():
            with open(FONT_PATH, "rb") as f:
                font_bytes = f.read()
            encoded = base64.b64encode(font_bytes).decode()
            logger.debug("成功加载并编码 vanfont.ttf")
            return encoded
        else:
            logger.error(f"图标字体文件未找到: {FONT_PATH}")
    except Exception as e:
        logger.error(f"加载或编码 vanfont.ttf 时出错: {e}")
    return ""


# 模块加载时立即读取字体（保持与原始行为一致）
FONT_BASE64_CONTENT = _load_font_base64()

# ── 清晰度映射 ─────────────────────────────────────────
# bilibili_api 的 VideoQuality 枚举成员名带下划线前缀（如 _720P），
# 此映射将用户友好的键名转换为枚举成员名，避免在 WebUI 中暴露下划线。

QUALITY_OPTIONS = ["360P", "480P", "720P", "1080P"]
QUALITY_DEFAULT = "480P"

_QUALITY_TO_ENUM = {
    "360P": "_360P",
    "480P": "_480P",
    "720P": "_720P",
    "1080P": "_1080P",
}


def resolve_quality(key: str) -> str:
    """将用户配置的清晰度键名（如 '480P'）转换为 bilibili_api 枚举名（'_480P'）。"""
    return _QUALITY_TO_ENUM.get(key, "_480P")


# 反向映射：枚举名 → 显示名
_ENUM_TO_QUALITY = {v: k for k, v in _QUALITY_TO_ENUM.items()}


def quality_display(enum_name: str) -> str:
    """将 bilibili_api 枚举名（'_720P'）转换为显示名（'720P'）。"""
    return _ENUM_TO_QUALITY.get(enum_name, enum_name.lstrip("_"))


# ── 默认解析模板 ─────────────────────────────────────────

DEFAULT_PARSE_TEMPLATE = (
    "📺 {title}\n"
    "UP: {up_name}\n"
    "时长: {duration}\n"
    "发布时间: {pub_time}\n"
    "播放: {view}  点赞: {like}  弹幕: {danmaku}\n"
    "简介: {desc}\n"
    "链接: {link}"
)

# ── HTML 卡片模板 ─────────────────────────────────────────
# 以下模板使用 Jinja2 语法的占位符（{{ var }}、{% if %} 等），
# 由 AstrBot Star 基类的 html_render() 方法渲染为图片。

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

ARTICLE_CARD_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    margin: 0; padding: 0;
    background-color: #ffffff;
    width: 750px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  }
  .card {
    width: 750px; padding: 0;
    background-color: #ffffff;
    border-radius: 12px;
    box-shadow: 0 5px 20px rgba(251, 114, 153, 0.15);
    overflow: hidden;
    margin: 0;
  }
  {% if cover_url %}
  .cover img {
    width: 100%; height: auto; display: block;
    aspect-ratio: 16 / 9; object-fit: cover;
  }
  {% endif %}
  .header {
    padding: 22px 24px 0 24px;
  }
  .header .article-title {
    font-size: 32px; font-weight: 600; line-height: 1.45;
    color: #1a1a1a;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;
  }
  .header .author {
    font-size: 22px; color: #fb7299; font-weight: 500;
    margin-top: 10px;
  }
  .divider {
    width: 100%; height: 1px; background: #f0f0f0;
    margin: 16px 0 0 0;
  }
  .content {
    padding: 18px 24px 20px 24px;
  }
  .content .summary {
    font-size: 24px; color: #555; line-height: 1.7;
    word-wrap: break-word;
    border-left: 3px solid #fce4ec; padding-left: 12px;
  }
  .footer {
    display: flex; align-items: center; justify-content: center;
    height: 52px; background: #fff8fa;
    font-size: 14px; color: #fb7299; font-weight: 700;
    border-top: 1px solid #f0f0f0; letter-spacing: 2px;
  }
</style>
</head>
<body>
<div class="card">
  {% if cover_url %}
  <div class="cover">
    <img src="{{ cover_url }}" alt=""/>
  </div>
  {% endif %}
  <div class="header">
    <div class="article-title">{{ title }}</div>
    <div class="author">作者：{{ author }}</div>
  </div>
  <div class="divider"></div>
  <div class="content">
    <div class="summary">{{ summary }}</div>
  </div>
  <div class="footer">bilibili</div>
</div>
</body>
</html>'''

OPUS_CARD_HTML = '''<!DOCTYPE html>
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
    width: 750px; padding: 0;
    background-color: #ffffff;
    border-radius: 12px;
    box-shadow: 0 5px 20px rgba(251, 114, 153, 0.15);
    overflow: hidden;
    margin: 0;
  }
  .header {
    display: flex; align-items: center;
    padding: 18px 22px;
    border-bottom: 1px solid #f0f0f0;
  }
  .header .avatar {
    width: 64px; height: 64px; border-radius: 50%;
    object-fit: cover; border: 1px solid #eee;
    margin-right: 12px;
  }
  .header .name {
    font-size: 26px; font-weight: 500; color: #fb7299;
    overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
  }
  .header .time {
    font-size: 20px; color: #999; margin-left: auto;
  }
  .content {
    padding: 20px 22px;
  }
  .content .text {
    font-size: 26px; color: #333; line-height: 1.6;
    word-wrap: break-word;
  }
  {% if images %}
  .images {
    display: grid; grid-template-columns: repeat({{ img_cols }}, 1fr);
    gap: 8px; margin-top: 14px;
  }
  .images img {
    width: 100%; border-radius: 8px;
    object-fit: cover; aspect-ratio: 1;
  }
  {% endif %}
  .stats {
    display: flex; gap: 30px;
    padding: 14px 22px;
    border-top: 1px solid #f0f0f0;
    font-size: 22px; color: #9499a0;
    text-align: center;
  }
  .stat {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    flex: 1;
  }
  .stat::before {
    display: block; font-family: 'van';
    font-size: 36px; color: #fb7299;
  }
  .stat.like::before    { content: "\\e6e0"; }
  .stat.comment::before { content: "\\e639"; }
  .stat.forward::before { content: "\\e70f"; }
  .footer {
    display: flex; align-items: center; justify-content: center;
    height: 52px; background: #fff8fa;
    font-size: 14px; color: #fb7299; font-weight: 700;
    border-top: 1px solid #f0f0f0; letter-spacing: 2px;
  }
</style>
</head>
<body>
<div class="card">
  <div class="header">
    {% if author_face %}<img class="avatar" src="{{ author_face }}" alt=""/>{% endif %}
    <span class="name">{{ author }}</span>
    <span class="time">{{ pub_time }}</span>
  </div>
  <div class="content">
    <div class="text">{{ content }}</div>
    {% if images %}
    <div class="images">
      {% for img in images %}
      <img src="{{ img }}" alt=""/>
      {% endfor %}
    </div>
    {% endif %}
  </div>
  <div class="stats">
    <span class="stat like">{{ like_count }}<br>点赞</span>
    <span class="stat comment">{{ comment_count }}<br>评论</span>
    <span class="stat forward">{{ forward_count }}<br>转发</span>
  </div>
  <div class="footer">bilibili 动态</div>
</div>
</body>
</html>'''
