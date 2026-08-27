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
  .video-info .pages-info {
    display: inline-block;
    font-size: 22px; line-height: 1.4; color: #fb7299;
    background-color: #fff0f5; border-radius: 6px;
    padding: 3px 12px; margin-bottom: 12px;
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
    gap: 20px 10px;
    border-top: 1px solid #f0f0f0; padding-top: 18px;
  }
  .stat-item {
    display: flex; flex-direction: column; align-items: center;
    gap: 5px;
  }
  .stat-item::before {
    display: block; font-family: 'van';
    font-size: 40px; line-height: 1; color: #fb7299;
  }
  .stat-num {
    font-size: 24px; line-height: 1; color: #555;
  }
  .stat-label {
    font-size: 22px; line-height: 1; color: #999;
  }
  .stat-view::before     { content: "\\e6e6"; }
  .stat-danmaku::before  { content: "\\e6e7"; }
  .stat-like::before     { content: "\\e6e0"; }
  .stat-coin::before     { content: "\\e6e4"; }
  .stat-favorite::before { content: "\\e6e1"; }
  .stat-share::before    { content: "\\e70f"; }
  .stat-reply::before    { content: "\\e639"; }

  .comments {
    padding: 10px 18px 15px 18px;
    border-top: 1px solid #f0f0f0; margin-top: 10px;
  }
  .comments-title {
    font-size: 25px; font-weight: 600; color: #555; margin-bottom: 8px;
  }
  .comment-item {
    display: flex; align-items: flex-start; justify-content: space-between;
    font-size: 24px; line-height: 1.5; margin-bottom: 8px; color: #333;
  }
  .comment-item:last-child { margin-bottom: 0; }
  .comment-main {
    flex: 1; min-width: 0;
  }
  .commenter {
    color: #fb7299; font-weight: 500; margin-right: 5px;
    white-space: nowrap;
  }
  .comment-text {
    word-break: break-all;
  }
  .comment-likes {
    flex-shrink: 0;
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
  .portal .bili-icon {
    width: 34px; height: 34px;
  }
  .portal .x-symbol {
    font-size: 26px; color: #fb7299; margin: 0 8px; line-height: 1;
  }
  .portal .camera-icon {
    width: 34px; height: 34px;
  }
  .ai-conclusion {
    padding: 16px 18px;
    border-top: 1px solid #f0f0f0;
    background-color: #fafbfc;
  }
  .ai-conclusion .ai-conclusion-title {
    margin-bottom: 8px;
  }
  .ai-conclusion .ai-conclusion-title .ai-icon {
    width: 26px; height: 26px;
    display: block;
  }
  .ai-conclusion .ai-conclusion-text {
    font-size: 24px; line-height: 1.6; color: #333;
    word-break: break-all; white-space: pre-wrap;
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
    {% if page_info %}
    <div class="pages-info">{{ page_info }}</div>
    {% endif %}
    <div class="meta">
      <span>发布于: {{ pub_time }}</span>
      <span>{{ avid }}</span>
    </div>
    {% if desc %}<div class="summary">{{ desc }}</div>{% endif %}
    <div class="stats">
      {% for s in stats %}
      <div class="stat-item stat-{{ s.key }}">
        <span class="stat-num">{{ s.value }}</span>
        <span class="stat-label">{{ s.label }}</span>
      </div>
      {% endfor %}
    </div>
    {% if comments %}
    <div class="comments">
      <div class="comments-title">热门评论</div>
      {% for c in comments %}
      <div class="comment-item">
        <div class="comment-main">
          <span class="commenter">{{ c.uname }}:</span>
          <span class="comment-text">{{ c.text }}</span>
        </div>
        {% if c.likes %}<span class="comment-likes">{{ c.likes }}</span>{% endif %}
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>
  {% if ai_conclusion %}
  <div class="ai-conclusion">
    <div class="ai-conclusion-title">
      <svg class="ai-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" preserveAspectRatio="xMidYMid meet">
        <g transform="translate(0.8 0.9)">
          <g transform="translate(0 32)">
            <path d="m246.3 328.1-17.8 41.2c-6.4 14.8-26.9 14.8-33.3 0l-17.8-41.2c-14.9-34.2-41.8-61.4-75.3-76.3l-48.8-21.6c-14.7-6.5-14.7-27.9 0-34.4l47.2-21c34.4-15.3 61.7-43.5 76.4-78.8l18-43.7c6.3-15.2 27.3-15.2 33.6 0l18 43.7c14.7 35.3 42 63.6 76.4 78.8l47.2 21c14.7 6.5 14.7 27.9 0 34.4l-48.8 21.6c-33.5 14.8-60.4 42.1-75.3 76.2z" fill="#2f86bd" transform="translate(0 35)" />
            <path d="m402.2 449.3-5.3 12.2c-3.5 7.9-14.4 7.9-17.9 0l-5.3-12.2c-8.4-19.3-23.6-34.6-42.4-43l-15.4-6.9c-7.9-3.5-7.9-14.9 0-18.4l14.5-6.5c19.4-8.6 34.8-24.5 43.1-44.5l5.4-13.1c3.4-8.1 14.6-8.1 18 0l5.4 13.1c8.3 19.9 23.7 35.8 43.1 44.5l14.5 6.5c7.9 3.5 7.9 14.9 0 18.4l-15.4 6.9c-19 8.3-34.1 23.7-42.5 43z" fill="#ff69b4" transform="matrix(0.95 0 0 0.95 22 -278)" />
          </g>
        </g>
      </svg>
    </div>
    <div class="ai-conclusion-text">{{ ai_conclusion }}</div>
  </div>
  {% endif %}
  <div class="portal">
    <svg class="bili-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" preserveAspectRatio="xMidYMid meet">
      <g transform="translate(0.8 0.9)">
        <g transform="translate(0 32)">
          <path d="m246.3 328.1-17.8 41.2c-6.4 14.8-26.9 14.8-33.3 0l-17.8-41.2c-14.9-34.2-41.8-61.4-75.3-76.3l-48.8-21.6c-14.7-6.5-14.7-27.9 0-34.4l47.2-21c34.4-15.3 61.7-43.5 76.4-78.8l18-43.7c6.3-15.2 27.3-15.2 33.6 0l18 43.7c14.7 35.3 42 63.6 76.4 78.8l47.2 21c14.7 6.5 14.7 27.9 0 34.4l-48.8 21.6c-33.5 14.8-60.4 42.1-75.3 76.2z" fill="#ff69b4" transform="translate(0 35)" />
          <path d="m402.2 449.3-5.3 12.2c-3.5 7.9-14.4 7.9-17.9 0l-5.3-12.2c-8.4-19.3-23.6-34.6-42.4-43l-15.4-6.9c-7.9-3.5-7.9-14.9 0-18.4l14.5-6.5c19.4-8.6 34.8-24.5 43.1-44.5l5.4-13.1c3.4-8.1 14.6-8.1 18 0l5.4 13.1c8.3 19.9 23.7 35.8 43.1 44.5l14.5 6.5c7.9 3.5 7.9 14.9 0 18.4l-15.4 6.9c-19 8.3-34.1 23.7-42.5 43z" fill="#2f86bd" transform="matrix(0.95 0 0 0.95 22 -278)" />
        </g>
      </g>
    </svg>
    <span class="x-symbol">x</span>
    <svg class="camera-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <g>
        <path fill="none" d="M0 0h24v24H0z"/>
        <path d="M18.223 3.086a1.25 1.25 0 0 1 0 1.768L17.08 5.996h1.17A3.75 3.75 0 0 1 22 9.747v7.5a3.75 3.75 0 0 1-3.75 3.75H5.75A3.75 3.75 0 0 1 2 17.247v-7.5a3.75 3.75 0 0 1 3.75-3.75h1.166L5.775 4.855a1.25 1.25 0 1 1 1.767-1.768l2.652 2.652c.079.079.145.165.198.257h3.213c.053-.092.12-.18.199-.258l2.651-2.652a1.25 1.25 0 0 1 1.768 0zm.027 5.42H5.75a1.25 1.25 0 0 0-1.247 1.157l-.003.094v7.5c0 .659.51 1.199 1.157 1.246l.093.004h12.5a1.25 1.25 0 0 0 1.247-1.157l.003-.093v-7.5c0-.69-.56-1.25-1.25-1.25zm-10 2.5c.69 0 1.25.56 1.25 1.25v1.25a1.25 1.25 0 1 1-2.5 0v-1.25c0-.69.56-1.25 1.25-1.25zm7.5 0c.69 0 1.25.56 1.25 1.25v1.25a1.25 1.25 0 1 1-2.5 0v-1.25c0-.69.56-1.25 1.25-1.25z" fill="#ff69b4"/>
      </g>
    </svg>
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
