"""B站服务层：视频/专栏/动态数据获取、视频下载、短链解析、图片下载。

所有 B站 API 调用和网络 I/O 集中在此模块，便于 mock 和测试。
"""

import asyncio
import base64
import re
from pathlib import Path

import httpx
from bilibili_api import Credential
from bilibili_api.article import Article
from bilibili_api.comment import CommentResourceType, OrderType, get_comments
from bilibili_api.dynamic import Dynamic
from bilibili_api.video import (
    AudioStreamDownloadURL,
    Video,
    VideoCodecs,
    VideoDownloadURLDataDetecter,
    VideoQuality,
)

from astrbot.api import logger

from .constants import AV_PATTERN, BV_PATTERN
from .credential import CredentialManager
from .models import ArticleCard, DownloadPlan, OpusCard, VideoCard
from .utils import format_count, safe_int, sanitize_desc


class BilibiliService:
    """B站内容获取与下载服务。

    参数:
        client:    httpx.AsyncClient（连接池复用）。
        cred_mgr:  CredentialManager 实例。
        cache_dir: 视频下载缓存目录。
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        cred_mgr: CredentialManager,
        cache_dir: Path,
    ):
        self._client = client
        self._cred_mgr = cred_mgr
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ── 视频 ───────────────────────────────────────────

    async def fetch_video_card(
        self,
        bvid: str = "",
        aid: int = 0,
        page: int = 1,
        quality: str = "_480P",
    ) -> VideoCard:
        """获取视频信息（不下载视频文件）。

        Args:
            bvid: BV 号。
            aid:  AV 号。
            page: 分P 页码。
            quality: 下载清晰度（预留，实际下载走 prepare_download/download_video）。
        """
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

        # 构建所有 P 的信息列表（供多 P 下载使用）
        pages_info = []
        for i, p in enumerate(pages):
            pages_info.append({
                "page": safe_int(p.get("page", i + 1)),
                "part": str(p.get("part", "")),
                "duration": safe_int(p.get("duration", 0)),
            })

        owner = info.get("owner", {})
        stat = info.get("stat", {})
        _bvid = str(info.get("bvid", bvid))
        _aid = safe_int(info.get("aid", aid))
        link = f"https://www.bilibili.com/video/{_bvid}"
        if page_idx > 0:
            link += f"?p={page_idx + 1}"

        dur = safe_int(pg.get("duration", info.get("duration", 0)))
        cid = safe_int(pages[0].get("cid", 0)) if pages else 0

        return VideoCard(
            aid=_aid,
            bvid=_bvid,
            title=str(info.get("title", "")),
            link=link,
            up_name=str(owner.get("name", "未知UP")),
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
            video_path=None,
            cid=cid,
            pages=pages_info,
        )

    async def fetch_ai_conclusion(
        self, bvid: str = "", aid: int = 0, cid: int = 0
    ) -> str | None:
        """获取视频 AI 总结文本。

        Returns:
            总结文本；空字符串表示无总结或获取失败；None 表示未登录。
        """
        if cid <= 0:
            return ""
        cred = await self._cred_mgr.get()
        if cred is None:
            logger.warning("未登录 B站账号，无法获取 AI 总结")
            return None
        if aid:
            v = Video(aid=aid, credential=cred)
        elif bvid:
            v = Video(bvid=bvid, credential=cred)
        else:
            return ""

        try:
            data = await v.get_ai_conclusion(cid=cid)
        except Exception as e:
            logger.debug(f"获取AI总结失败: {e}")
            return ""

        # 提取总结文本：get_ai_conclusion 默认已提取 data 字段
        result = data.get("data") or data if isinstance(data, dict) else {}
        model_result = result.get("model_result") or {}
        summary = model_result.get("summary", "")
        if isinstance(summary, str):
            return summary.strip()
        return ""

    async def prepare_download(
        self,
        bvid: str = "",
        aid: int = 0,
        page: int = 1,
        quality: str = "_480P",
        duration_s: int = 0,
        stem: str = "video",
    ) -> DownloadPlan | None:
        """获取视频下载流信息（仅一次 get_download_url）。

        Returns:
            DownloadPlan（含视频/音频 URL、码率、实际画质等）或 None（获取失败）。
            该计划可复用于 estimate_size 与 download_video，避免重复请求。
        """
        cred = await self._cred_mgr.get()
        if aid:
            v = Video(aid=aid, credential=cred)
        elif bvid:
            v = Video(bvid=bvid, credential=cred)
        else:
            return None

        page_idx = max(0, page - 1)

        try:
            download_data = await v.get_download_url(page_index=page_idx)
        except Exception as e:
            logger.warning(f"获取下载地址失败: {e}")
            return None

        detecter = VideoDownloadURLDataDetecter(download_data)
        video_quality = getattr(VideoQuality, quality, VideoQuality._480P)
        try:
            streams = detecter.detect_best_streams(
                video_max_quality=video_quality,
                codecs=[VideoCodecs.AVC],
                no_dolby_video=True,
                no_hdr=True,
            )
        except Exception as e:
            logger.warning(f"解析下载流失败: {e}")
            return None

        if not streams:
            logger.warning("未获取到可用下载流（可能触发 B站限流）")
            return None

        vs = streams[0]
        video_url = getattr(vs, "url", "")
        if not video_url:
            logger.warning("视频流 URL 为空")
            return None

        video_bandwidth = getattr(vs, "bandwidth", 0)
        audio_bandwidth = 0
        audio_url = ""
        if len(streams) > 1 and isinstance(streams[1], AudioStreamDownloadURL):
            audio_stream = streams[1]
            audio_url = getattr(audio_stream, "url", "")
            audio_bandwidth = getattr(audio_stream, "bandwidth", 0)

        quality_enum = getattr(vs, "video_quality", None)
        actual_quality = quality_enum.name if quality_enum else ""

        return DownloadPlan(
            video_url=video_url,
            audio_url=audio_url,
            video_bandwidth=video_bandwidth,
            audio_bandwidth=audio_bandwidth,
            actual_quality=actual_quality,
            duration_s=duration_s,
            stem=stem,
            page_idx=page_idx,
        )

    def estimate_size(self, plan: DownloadPlan) -> dict:
        """根据下载计划计算预估大小（纯计算，无网络请求）。"""
        video_bytes = plan.video_bandwidth * plan.duration_s / 8
        audio_bytes = plan.audio_bandwidth * plan.duration_s / 8
        total_bytes = video_bytes + audio_bytes
        return {
            "video_mb": round(video_bytes / 1024 / 1024, 2),
            "audio_mb": round(audio_bytes / 1024 / 1024, 2),
            "total_mb": round(total_bytes / 1024 / 1024, 2),
            "duration_s": plan.duration_s,
            "video_bandwidth": plan.video_bandwidth,
            "audio_bandwidth": plan.audio_bandwidth,
            "actual_quality": plan.actual_quality,
        }

    async def download_video(self, plan: DownloadPlan) -> Path | None:
        """根据下载计划下载视频（复用 plan 中的 URL，不再请求 B站）。"""
        return await self._download_from_plan(plan)

    # ── 专栏 ───────────────────────────────────────────

    async def fetch_article_info(self, cv_id: str) -> ArticleCard:
        """获取 B站专栏文章信息。"""
        cvid = int(cv_id[2:]) if cv_id.lower().startswith("cv") else int(cv_id)
        cred = await self._cred_mgr.get()
        art = Article(cvid=cvid, credential=cred)

        info = await art.get_info()
        title = info.get("title", "未知标题")
        author = info.get("author_name", "未知作者")
        image_urls = info.get("image_urls") or []
        origin_urls = info.get("origin_image_urls") or []
        cover = image_urls[0] if image_urls else (origin_urls[0] if origin_urls else "")

        md = ""
        try:
            await art.fetch_content()
            md = art.markdown() or ""
            logger.info(f"Article markdown len={len(md)}")
            if not md:
                try:
                    j = art.json()
                    md = j.get("content", "") or j.get("summary", "") or ""
                    logger.info(f"Article json content len={len(md)}")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Article.fetch_content 异常: {e}")
        if not md:
            md = info.get("summary", "") or ""
            logger.info(f"Article fallback to info.summary len={len(md)}")

        if not md:
            md = info.get("summary", "") or ""

        # 去掉 YAML frontmatter
        md = re.sub(r'^---\s*\n.*?\n---\s*\n', '', md, count=1, flags=re.DOTALL)
        plain = re.sub(r"[#*`~_>]", "", re.sub(r"!\[.*?\]\(.*?\)", "[图片]", md))
        summary = sanitize_desc(plain, 250)

        return ArticleCard(
            cv_id=cv_id,
            title=title,
            author=author,
            url=f"https://www.bilibili.com/read/{cv_id}",
            summary=summary,
            content_md=md,
            cover_url=cover,
            image_urls=image_urls,
        )

    # ── 图文动态 ───────────────────────────────────────

    async def fetch_opus_info(self, opus_id: str, try_article: bool = True) -> OpusCard:
        """获取 B站图文动态信息。"""
        cred = await self._cred_mgr.get()
        headers = {"Referer": "https://www.bilibili.com/"}
        if cred:
            cookie = "; ".join(f"{k}={v}" for k, v in cred.get_cookies().items() if v)
            if cookie:
                headers["Cookie"] = cookie

        resp = await self._client.get(
            "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail",
            params={"id": opus_id, "timezone_offset": "-480"},
            headers=headers,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取动态失败: {data.get('message', '未知错误')}")

        item = (data.get("data") or {}).get("item") or {}
        modules = item.get("modules") or {}
        author_info = modules.get("module_author") or {}
        author = author_info.get("name", "未知用户")
        author_face = author_info.get("face", "")
        pub_ts = author_info.get("pub_ts", 0)

        dyn_info = modules.get("module_dynamic") or {}
        desc = dyn_info.get("desc") or {}
        major = dyn_info.get("major") or {}
        major_type = str(major.get("type") or "")

        # 文字提取
        content_parts: list = []
        for node in desc.get("rich_text_nodes") or []:
            t = node.get("orig_text") or node.get("text") or ""
            if t:
                content_parts.append(t)
        dt = desc.get("text") or ""
        if dt and dt not in "".join(content_parts):
            content_parts.append(dt)
        if "OPUS" in major_type:
            opus_data = major.get("opus") or {}
            title = opus_data.get("title") or ""
            summary_text = (opus_data.get("summary") or {}).get("text") or ""
            if title and title not in "".join(content_parts):
                content_parts.insert(0, title)
            if summary_text and summary_text not in "".join(content_parts):
                content_parts.append(summary_text)

        content = "\n".join(c for c in content_parts if c)

        # 专栏类动态转 Article 获取全文
        if not content.strip() and try_article:
            try:
                dyn = Dynamic(dynamic_id=int(opus_id), credential=cred)
                if await dyn.is_article():
                    art = await dyn.turn_to_article()
                    await art.fetch_content()
                    md = art.markdown() or ""
                    md = re.sub(r'^---\s*\n.*?\n---\s*\n', '', md, count=1, flags=re.DOTALL)
                    content = md
            except Exception:
                pass

        # 图片提取
        images: list = []
        for src_key in ("draw", "opus"):
            obj = major.get(src_key) or {}
            for d in (obj.get("items") or obj.get("pics") or []):
                src = d.get("src") or d.get("url") or ""
                if src and src not in images:
                    images.append(src)

        # 统计
        stat_info = modules.get("module_stat") or {}
        like_count = (stat_info.get("like") or {}).get("count", 0) or 0
        comment_count = (stat_info.get("comment") or {}).get("count", 0) or 0
        forward_count = (stat_info.get("forward") or {}).get("count", 0) or 0

        return OpusCard(
            opus_id=opus_id,
            author=author,
            author_face=author_face,
            content=content,
            images=images,
            like_count=like_count,
            comment_count=comment_count,
            forward_count=forward_count,
            pub_ts=pub_ts,
            url=f"https://www.bilibili.com/opus/{opus_id}",
        )

    # ── 短链解析 ───────────────────────────────────────

    async def resolve_short(self, url: str) -> str:
        """解析 b23.tv / bili2233.cn 短链，返回重定向后的 URL 或提取的 BV/AV 号。"""
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
            return final
        except Exception:
            pass
        return url

    # ── 图片下载 & Base64 ──────────────────────────────

    async def download_b64(self, url: str) -> str:
        """下载图片并转为 base64 data URI，失败返回空字符串。"""
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

    # ── 评论 ───────────────────────────────────────────

    async def fetch_comments(self, oid: int, count: int = 3) -> list[dict]:
        """获取视频热门评论（最多 count 条）。"""
        count = safe_int(count, 3, 0, 20)
        cred = await self._cred_mgr.get()
        try:
            c = await get_comments(
                oid=oid,
                type_=CommentResourceType.VIDEO,
                order=OrderType.LIKE,
                credential=cred,
            )
            result = []
            for cmt in c.get("replies", [])[:count]:
                if cmt and isinstance(cmt, dict) and cmt.get("member") and cmt.get("content"):
                    text = cmt["content"].get("message", "")
                    text = re.sub(r"\[.*?\]", "", text).strip()
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

    # ── 视频下载（内部）────────────────────────────────

    async def _download_from_plan(self, plan: DownloadPlan) -> Path | None:
        """根据下载计划下载视频并合并音轨（需要 FFmpeg）。"""
        stem = plan.stem
        output = self._cache_dir / f"{stem}.mp4"
        if output.exists() and output.stat().st_size > 0:
            return output

        headers = {"Referer": "https://www.bilibili.com/"}
        cred = await self._cred_mgr.get()
        if cred:
            cookie = "; ".join(f"{k}={v}" for k, v in cred.get_cookies().items() if v)
            if cookie:
                headers["Cookie"] = cookie

        if plan.audio_url:
            v_temp = self._cache_dir / f"{stem}.video.m4s"
            a_temp = self._cache_dir / f"{stem}.audio.m4s"
            try:
                await asyncio.gather(
                    self._download(plan.video_url, v_temp, headers),
                    self._download(plan.audio_url, a_temp, headers),
                )
                await self._ffmpeg_merge(v_temp, a_temp, output)
            finally:
                v_temp.unlink(missing_ok=True)
                a_temp.unlink(missing_ok=True)
        else:
            await self._download(plan.video_url, output, headers)

        return output if (output.exists() and output.stat().st_size > 0) else None

    async def _download(self, url: str, path: Path, headers: dict):
        """流式下载文件到指定路径。"""
        async with self._client.stream(
            "GET", url, headers=headers, timeout=300, follow_redirects=True
        ) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                async for chunk in resp.aiter_bytes(1024 * 1024):
                    f.write(chunk)

    async def _ffmpeg_merge(self, video: Path, audio: Path, output: Path):
        """调用 FFmpeg 合并视频和音频轨道。"""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(audio),
            "-c", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            str(output),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg 合并失败: {stderr.decode(errors='ignore')[:200]}")
