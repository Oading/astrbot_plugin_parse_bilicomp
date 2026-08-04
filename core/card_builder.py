"""卡片渲染器：将数据模型渲染为 AstrBot MessageChain。

负责 HTML 模板数据组装、html_render 调用及纯文本回退。
通过依赖注入接收 html_render 可调用对象和 BilibiliService，
解耦对 Star 基类的直接依赖，方便单元测试。
"""

from typing import Callable

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Video as MessageVideo

from .constants import (
    ARTICLE_CARD_HTML,
    DEFAULT_PARSE_TEMPLATE,
    FONT_BASE64_CONTENT,
    OPUS_CARD_HTML,
    VIDEO_CARD_HTML,
)
from .models import ArticleCard, OpusCard, SafeFormatDict, VideoCard
from .service import BilibiliService
from .utils import format_count, format_timestamp, sanitize_desc


# html_render 可调用对象的签名: (template: str, data: dict, options: dict) -> str (返回图片 URL)
HtmlRenderFunc = Callable[..., str]


class CardBuilder:
    """将 VideoCard / ArticleCard / OpusCard 渲染为消息链。

    参数:
        config:      插件配置。
        html_render: Star 基类的 html_render 方法（或兼容的可调用对象）。
        service:     BilibiliService 实例（用于下载图片、获取评论）。
    """

    def __init__(
        self,
        config: AstrBotConfig,
        html_render: HtmlRenderFunc,
        service: BilibiliService,
    ):
        self._config = config
        self._html_render = html_render
        self._service = service

    # ── 文本渲染 ──────────────────────────────────────

    def render_text(self, card: VideoCard) -> str:
        """根据配置模板渲染视频信息文本。"""
        fmt = str(
            self._config.get("parse_template", "") or DEFAULT_PARSE_TEMPLATE
        ).replace("\\n", "\n")
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

    # ── HTML 数据组装 ─────────────────────────────────

    async def _build_video_html_data(self, card: VideoCard) -> dict:
        """组装视频 HTML 卡片渲染数据（含 base64 封面、UP 头像、评论、图标字体）。"""
        cover_b64 = await self._service.download_b64(card.cover_url)
        up_face_b64 = (
            await self._service.download_b64(card.up_face_url)
            if card.up_face_url
            else ""
        )
        comments = await self._service.fetch_comments(card.aid, count=3)
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

    async def _build_article_html_data(self, card: ArticleCard) -> dict:
        """组装专栏 HTML 卡片渲染数据。"""
        return {
            "title": card.title,
            "author": card.author,
            "summary": card.summary,
            "cover_url": (
                await self._service.download_b64(card.cover_url)
                if card.cover_url
                else ""
            ),
            "url": card.url,
        }

    async def _build_opus_html_data(self, card: OpusCard) -> dict:
        """组装图文动态 HTML 卡片渲染数据。"""
        face_b64 = (
            await self._service.download_b64(card.author_face)
            if card.author_face
            else ""
        )
        images_b64 = []
        for url in card.images[:4]:
            b64 = await self._service.download_b64(url)
            if b64:
                images_b64.append(b64)
        img_cols = min(len(images_b64), 3) if len(images_b64) <= 3 else 2
        if img_cols == 0:
            img_cols = 1
        content = card.content.strip()[:300]
        if len(card.content.strip()) > 300:
            content += "…"

        return {
            "font_van_base64": FONT_BASE64_CONTENT,
            "author": card.author,
            "author_face": face_b64,
            "pub_time": format_timestamp(card.pub_ts),
            "content": content,
            "images": images_b64,
            "img_cols": img_cols,
            "like_count": format_count(card.like_count),
            "comment_count": format_count(card.comment_count),
            "forward_count": format_count(card.forward_count),
        }

    # ── 消息链构建 ────────────────────────────────────

    async def build_video_chains(self, card: VideoCard) -> list[MessageChain]:
        """构建视频消息链：优先 HTML 图片卡片 → 回退文本+封面。"""
        chains: list[MessageChain] = []
        send_video = self._config.get("send_video", True) and card.video_path is not None
        render_image = self._config.get("render_as_image", True)

        rich_chain = MessageChain()

        if render_image:
            try:
                data = await self._build_video_html_data(card)
                img_url = await self._html_render(
                    VIDEO_CARD_HTML,
                    data,
                    options={
                        "type": "jpeg",
                        "quality": 90,
                        "full_page": True,
                        "clip": {"x": 0, "y": 0, "width": 750, "height": 3000},
                    },
                )
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

        # 回退：文本 + 封面 URL
        rich_chain.message(self.render_text(card))
        if self._config.get("send_cover", True) and card.cover_url:
            rich_chain.url_image(card.cover_url)
        chains.append(rich_chain)

        if send_video:
            vc = MessageChain()
            vc.chain.append(MessageVideo.fromFileSystem(str(card.video_path)))
            chains.append(vc)

        return chains

    async def build_article_chains(self, card: ArticleCard) -> list[MessageChain]:
        """构建专栏消息链：优先 HTML 图片卡片 → 回退纯文本。"""
        chains: list[MessageChain] = []
        rich_chain = MessageChain()
        render_image = self._config.get("render_as_image", True)

        if render_image:
            try:
                data = await self._build_article_html_data(card)
                img_url = await self._html_render(
                    ARTICLE_CARD_HTML,
                    data,
                    options={
                        "type": "jpeg",
                        "quality": 90,
                        "full_page": True,
                        "clip": {"x": 0, "y": 0, "width": 750, "height": 3000},
                    },
                )
                if img_url:
                    rich_chain.chain.append(Image.fromURL(img_url))
                    chains.append(rich_chain)
                    return chains
            except Exception as e:
                logger.debug(f"专栏 HTML 渲染失败，回退文本: {e}")

        rich_chain.message(
            f"【专栏】{card.title}\n作者：{card.author}\n\n{card.summary}\n\n链接：{card.url}"
        )
        chains.append(rich_chain)
        return chains

    async def build_opus_chains(self, card: OpusCard) -> list[MessageChain]:
        """构建图文动态消息链：优先 HTML 图片卡片 → 回退纯文本。"""
        chains: list[MessageChain] = []
        rich_chain = MessageChain()
        render_image = self._config.get("render_as_image", True)

        if render_image:
            try:
                data = await self._build_opus_html_data(card)
                img_url = await self._html_render(
                    OPUS_CARD_HTML,
                    data,
                    options={
                        "type": "jpeg",
                        "quality": 90,
                        "full_page": True,
                        "clip": {"x": 0, "y": 0, "width": 750, "height": 3000},
                    },
                )
                if img_url:
                    rich_chain.chain.append(Image.fromURL(img_url))
                    chains.append(rich_chain)
                    return chains
            except Exception as e:
                logger.debug(f"opus HTML 渲染失败，回退文本: {e}")

        content = card.content.strip()[:200]
        if len(card.content.strip()) > 200:
            content += "…"
        rich_chain.message(
            f"📢 {card.author} 的动态\n\n{content}\n\n"
            f"👍 {format_count(card.like_count)}  💬 {format_count(card.comment_count)}  🔄 {format_count(card.forward_count)}\n"
            f"链接：{card.url}"
        )
        chains.append(rich_chain)
        return chains
