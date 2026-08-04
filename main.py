"""AstrBot B站内容解析插件 — 入口模块。

功能:
1. 被动解析：自动识别消息中的 B站链接，发送文本卡片 + 封面图
2. 手动下载：/bili 下载 <链接> 下载并发送视频文件
3. 自动下载：管理员控制群内自动下载
4. 扫码登录：/bili 登录
5. 状态查询：/bili 状态

本文件仅负责插件的组装与生命周期管理，业务逻辑已拆分至:
- constants.py   — 正则模式、HTML 模板、默认配置
- models.py      — 数据模型（VideoCard / ArticleCard / OpusCard）
- utils.py       — 纯工具函数
- credential.py  — B站凭证管理
- resolver.py    — 链接解析
- service.py     — B站 API 调用与视频下载
- card_builder.py — HTML 卡片渲染
"""

import asyncio
import time
from pathlib import Path

import httpx
from bilibili_api.dynamic import Dynamic

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Image, Video as MessageVideo
from astrbot.api.star import Context, Star, StarTools

from .core import (
    AV_PATTERN,
    BV_PATTERN,
    CV_PATTERN,
    OPUS_PATTERN,
    PLUGIN_NAME,
    BilibiliService,
    CardBuilder,
    CredentialManager,
    LinkResolver,
    quality_display,
    resolve_quality,
    safe_int,
)

# ═════════════════════════════════════════════════════════
# 插件主类
# ═════════════════════════════════════════════════════════


class ParseBilibiliPlugin(Star):
    """B站内容解析插件。

    通过 Star 基类接入 AstrBot 生命周期，将业务逻辑委托给各服务模块。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config

        # ── 数据目录 ──
        self._data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self._media_dir = self._data_dir / "media_cache"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._media_dir.mkdir(parents=True, exist_ok=True)

        # ── HTTP 客户端 ──
        self._client = httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )

        # ── 服务层 ──
        self._cred_mgr = CredentialManager(self._data_dir, config, self._client)
        self._service = BilibiliService(self._client, self._cred_mgr, self._media_dir)
        self._card_builder = CardBuilder(
            config,
            self.html_render,
            self._service,
        )

        # ── 去重状态 ──
        self._debounce: dict[str, dict[str, float]] = {}

        # ── 已启用被动解析的群组 ──
        self._init_enabled_groups()

    # ── 生命周期 ──────────────────────────────────────

    async def initialize(self):
        """插件加载完成后调用。"""
        self._init_enabled_groups()
        asyncio.create_task(self._cleanup_loop())
        logger.info(f"{PLUGIN_NAME} 已加载")

    async def terminate(self):
        """插件卸载/停用时调用。"""
        await self._client.aclose()
        logger.info(f"{PLUGIN_NAME} 已卸载")

    async def _cleanup_loop(self):
        """每天清理一次媒体缓存。"""
        while True:
            await asyncio.sleep(86400)
            try:
                for f in self._media_dir.rglob("*"):
                    if f.is_file():
                        f.unlink(missing_ok=True)
            except Exception:
                pass

    # ── 局部模式群组配置 ──────────────────────────────

    def _init_enabled_groups(self):
        """确保 enabled_groups 是合法列表。"""
        groups = self.config.get("enabled_groups", [])
        if not isinstance(groups, list):
            self.config["enabled_groups"] = []

    @property
    def _enabled_groups(self) -> set[str]:
        return {str(g) for g in self.config.get("enabled_groups", [])}

    # ── 去重 ──────────────────────────────────────────

    def _is_debounced(self, umo: str, key: str) -> bool:
        """检查是否在去重冷却期内。"""
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
        # 清理过期条目
        expired = [k for k, v in entry.items() if v <= now]
        for k in expired:
            del entry[k]
        return False

    # ═══════════════════════════════════════════════════
    # 下载限制检查
    # ═══════════════════════════════════════════════════

    def _check_download_restrictions(
        self, duration_seconds: int, size_info: dict | None
    ) -> tuple[bool, list[str]]:
        """根据配置的限制模式判断是否可以下载。

        Returns:
            (can_download, reasons): reasons 为阻止下载的原因列表（空=通过）。
            仅包含与当前模式相关的失败原因。
        """
        mode = self.config.get("download_restriction_mode", "both")
        max_dur = safe_int(self.config.get("auto_download_max_duration", 10), 10)
        max_size = safe_int(self.config.get("max_video_size_mb", 100), 100)

        # ── 时长检查 ──
        dur_ok = True
        dur_reason = ""
        if duration_seconds > max_dur * 60:
            dur_ok = False
            dur_min = duration_seconds // 60
            dur_sec = duration_seconds % 60
            dur_reason = f"视频时长 {dur_min}分{dur_sec}秒 超过限制 ({max_dur}分)"

        # ── 大小检查 ──
        size_ok = True
        size_reason = ""
        if size_info is None:
            size_ok = False
            size_reason = "无法获取视频大小信息，已阻止下载"
        elif size_info["total_mb"] > max_size:
            size_ok = False
            size_reason = (
                f"预估大小 {size_info['total_mb']}MB 超过限制 ({max_size}MB)"
            )

        # ── 模式判定：只收集与当前模式相关的失败原因 ──
        if mode == "none":
            return True, []
        elif mode == "duration_only":
            return dur_ok, [dur_reason] if dur_reason else []
        elif mode == "size_only":
            return size_ok, [size_reason] if size_reason else []
        elif mode == "both":
            reasons = [r for r in (dur_reason, size_reason) if r]
            return not reasons, reasons
        elif mode == "either":
            ok = dur_ok or size_ok
            if ok:
                return True, []
            reasons = [r for r in (dur_reason, size_reason) if r]
            return False, reasons
        # 默认按时长限制
        return dur_ok, [dur_reason] if dur_reason else []

    def _format_size_prompt(
        self, card, size_info: dict | None, retract: bool = False,
        requested_quality: str = "",
    ) -> str:
        """生成下载提示文本。

        Args:
            card: VideoCard 实例。
            size_info: estimate_download_size 返回的字典或 None。
            retract: 是否附加撤回提示文字。
            requested_quality: 用户配置的期望清晰度（如 '720P'），用于与实际对比。
        """
        lines = [f"📥 即将下载视频"]
        if card.title:
            lines.append(f"📺 {card.title}")
        lines.append(f"⏱️ 时长: {card.duration_text}")
        if size_info:
            lines.append(
                f"📦 预估大小: {size_info['total_mb']}MB "
                f"(视频 {size_info['video_mb']}MB + 音频 {size_info['audio_mb']}MB)"
            )
            # 实际画质 vs 期望画质
            actual_enum = size_info.get("actual_quality", "")
            if actual_enum and requested_quality:
                actual_display = quality_display(actual_enum)
                if actual_display != requested_quality:
                    lines.append(
                        f"⚠️ 实际画质: {actual_display}（请求: {requested_quality}），"
                        f"登录后可获取更高质量"
                    )
        if retract:
            lines.append("（该消息一分钟后撤回）")
        return "\n".join(lines)

    async def _send_prompt_and_maybe_retract(
        self, event: AstrMessageEvent, text: str
    ) -> None:
        """发送下载提示消息。若开启撤回则通过 OneBot API 直发以捕获 message_id。"""
        retract = self.config.get("retract_download_prompt", False)

        if retract:
            sent, msg_id = await self._send_via_onebot(event, text)
            if sent:
                # 消息已通过 OneBot 发出，不再回退到 event.send()
                if msg_id:
                    asyncio.create_task(self._retract_onebot(event, msg_id, 60))
                else:
                    logger.debug("OneBot 消息已发送但未能提取 message_id，跳过撤回")
                return
            # OneBot 发送失败 → 回退普通发送（无法撤回）
            logger.debug("OneBot 直发失败，回退普通发送")

        # 普通发送
        try:
            await event.send(event.make_result().message(text))
        except Exception as e:
            logger.debug(f"发送下载提示失败: {e}")

    async def _send_via_onebot(
        self, event: AstrMessageEvent, text: str
    ) -> tuple[bool, int | None]:
        """通过 OneBot API 直接发送消息。

        Returns:
            (sent_successfully, message_id): sent_successfully 表示 API 调用是否成功
            （消息已发出）。message_id 可能为 None（发出但无法解析 ID）。
        """
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )
            if not isinstance(event, AiocqhttpMessageEvent):
                return False, None

            gid = event.get_group_id()
            if gid:
                result = await event.bot.api.call_action(
                    "send_group_msg", group_id=int(gid), message=text
                )
            else:
                result = await event.bot.api.call_action(
                    "send_private_msg",
                    user_id=int(event.get_sender_id()),
                    message=text,
                )

            msg_id = self._extract_msg_id(result)
            logger.debug(f"OneBot 发送结果: msg_id={msg_id}, result_type={type(result).__name__}")
            return True, msg_id
        except Exception as e:
            logger.debug(f"_send_via_onebot 异常: {e}")
            return False, None

    @staticmethod
    def _extract_msg_id(result) -> int | None:
        """从 OneBot API 返回值中提取 message_id，兼容多种格式。"""
        if isinstance(result, dict):
            # 格式1: {"data": {"message_id": 12345}}
            data = result.get("data", {})
            if isinstance(data, dict):
                mid = data.get("message_id")
                if mid is not None:
                    return int(mid)
            # 格式2: {"message_id": 12345}
            mid = result.get("message_id")
            if mid is not None:
                return int(mid)
        # 格式3: 对象属性
        if hasattr(result, "message_id"):
            return int(getattr(result, "message_id"))
        return None

    async def _retract_onebot(
        self, event: AstrMessageEvent, msg_id: int, delay: int
    ) -> None:
        """延迟 delay 秒后通过 OneBot API 撤回消息。"""
        await asyncio.sleep(delay)
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )
            if isinstance(event, AiocqhttpMessageEvent):
                await event.bot.api.call_action("delete_msg", message_id=msg_id)
                logger.debug(f"已撤回下载提示消息: {msg_id}")
        except Exception as e:
            logger.debug(f"撤回下载提示失败 (msg_id={msg_id}): {e}")

    # ═══════════════════════════════════════════════════
    # 被动解析
    # ═══════════════════════════════════════════════════

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """被动解析：识别消息中的 B站内容并回复信息卡片。"""
        # ── 模式检查 ──
        mode = self.config.get("passive_parse_mode", "global")
        gid = event.get_group_id()
        if mode == "local":
            if gid and str(gid) not in self._enabled_groups:
                return

        # 忽略自身消息
        if str(event.get_sender_id()) == str(event.get_self_id()):
            return

        # 忽略 @他人的消息
        messages = event.get_messages() or []
        if messages:
            first = messages[0]
            if isinstance(first, At) and str(first.qq) != str(event.get_self_id()):
                return

        # ── 链接提取 ──
        bvid_or_url, source_kind, page = LinkResolver.extract_target(
            messages, event.message_str or ""
        )
        if not bvid_or_url:
            return

        # ── 去重 ──
        umo = event.unified_msg_origin
        key = f"{source_kind}:{bvid_or_url}"
        if self._is_debounced(umo, key):
            return

        # ── 短链解析 ──
        bvid = bvid_or_url
        if source_kind == "short":
            bvid = await self._service.resolve_short(bvid_or_url)
            # 重新判断短链跳转后的目标类型
            if CV_PATTERN.search(bvid):
                source_kind = "article"
                bvid_or_url = CV_PATTERN.search(bvid).group(1)
            elif OPUS_PATTERN.search(bvid):
                source_kind = "opus"
                bvid_or_url = OPUS_PATTERN.search(bvid).group(1)

        # ── 专栏解析 ──
        if source_kind == "article":
            try:
                ac = await self._service.fetch_article_info(bvid_or_url)
                chains = await self._card_builder.build_article_chains(ac)
                for chain in chains:
                    yield event.chain_result(chain.chain)
                event.stop_event()
            except Exception as e:
                logger.error(f"专栏解析失败: {e}")
            return

        # ── 图文动态解析 ──
        if source_kind == "opus":
            try:
                # 专栏类动态 → 尝试转 Article
                if self.config.get("opus_try_article", True):
                    try:
                        cred = await self._cred_mgr.get()
                        dyn = Dynamic(dynamic_id=int(bvid_or_url), credential=cred)
                        if await dyn.is_article():
                            art = await dyn.turn_to_article()
                            ac = await self._service.fetch_article_info(
                                f"cv{art.get_cvid()}"
                            )
                            chains = await self._card_builder.build_article_chains(ac)
                            for chain in chains:
                                yield event.chain_result(chain.chain)
                            event.stop_event()
                            return
                    except Exception:
                        pass

                oc = await self._service.fetch_opus_info(bvid_or_url)
                chains = await self._card_builder.build_opus_chains(oc)
                for chain in chains:
                    yield event.chain_result(chain.chain)
                event.stop_event()
            except Exception as e:
                logger.error(f"动态解析失败: {e}")
                yield event.plain_result(
                    f"图文动态链接: https://www.bilibili.com/opus/{bvid_or_url}"
                )
            return

        # ── 视频解析 ──
        if not BV_PATTERN.fullmatch(bvid) and not AV_PATTERN.fullmatch(bvid):
            return

        # 1. 获取视频信息（先不下载）
        try:
            requested_quality = self.config.get("video_quality", "480P")
            quality = resolve_quality(requested_quality)
            if AV_PATTERN.fullmatch(bvid):
                aid_val = int(bvid.lstrip("avAV"))
                card = await self._service.fetch_video_card(
                    aid=aid_val, page=page, quality=quality, download=False
                )
                bvid_or_aid_kw = {"aid": aid_val}
            else:
                card = await self._service.fetch_video_card(
                    bvid=bvid, page=page, quality=quality, download=False
                )
                bvid_or_aid_kw = {"bvid": bvid}
        except Exception as e:
            logger.error(f"被动解析失败: {e}")
            return

        # 2. 预估大小 & 检查限制
        size_info = None
        restriction_mode = self.config.get("download_restriction_mode", "duration_only")
        if restriction_mode != "none":
            try:
                size_info = await self._service.estimate_download_size(
                    page=page, quality=quality, **bvid_or_aid_kw
                )
            except Exception as e:
                logger.debug(f"预估视频大小失败: {e}")

        can_download, reasons = self._check_download_restrictions(
            card.duration_seconds, size_info
        )

        # 3. 执行下载（如允许）
        if can_download and self.config.get("send_video", True):
            try:
                card.video_path = await self._service.download_video(
                    page=page, quality=quality, **bvid_or_aid_kw
                )
                # 下载提示
                if self.config.get("show_download_prompt", True) and card.video_path:
                    retract = self.config.get("retract_download_prompt", False)
                    prompt = self._format_size_prompt(
                        card, size_info, retract=retract,
                        requested_quality=requested_quality,
                    )
                    await self._send_prompt_and_maybe_retract(event, prompt)
            except Exception as e:
                logger.debug(f"视频下载失败: {e}")
        elif not can_download and reasons:
            # 无法下载时可选告知原因
            if self.config.get("show_download_fail_reason", True):
                reason_text = "；".join(reasons)
                yield event.plain_result(f"⚠️ 未下载视频: {reason_text}")
            card.video_path = None
        elif not can_download:
            card.video_path = None

        # 4. 发送卡片
        chains = await self._card_builder.build_video_chains(card)
        for chain in chains:
            if len(chain.chain) == 1 and isinstance(chain.chain[0], MessageVideo):
                try:
                    await self.context.send_message(umo, chain)
                except Exception as e:
                    logger.warning(f"视频发送失败: {e}")
            else:
                yield event.chain_result(chain.chain)

        event.stop_event()

    # ═══════════════════════════════════════════════════
    # 内部: 下载逻辑（由 /bili 下载 调用）
    # ═══════════════════════════════════════════════════

    async def _do_download(self, event: AstrMessageEvent, link: str = ""):
        """执行视频下载的完整流程：解析链接 → 检查限制 → 下载 → 发送卡片。"""
        if not link:
            link = event.message_str or ""
        if not link:
            yield event.plain_result(
                "请提供B站链接或视频ID，例如: /bili 下载 BV1xx411c7mD"
            )
            return

        messages = event.get_messages() or []
        bvid_or_url, source_kind, page = LinkResolver.extract_target(messages, link)
        if not bvid_or_url:
            bvid_or_url, source_kind, page = LinkResolver.extract_target(
                messages, event.message_str or ""
            )

        if not bvid_or_url:
            yield event.plain_result("未识别到有效的B站链接或BV/AV号")
            return

        if source_kind == "short":
            bvid_or_url = await self._service.resolve_short(bvid_or_url)

        # 非视频类型 → 提示使用被动解析
        if source_kind in ("article", "opus"):
            yield event.plain_result("⚠️ 该链接为专栏/动态，非视频，请直接发送链接以被动解析")
            return

        yield event.plain_result("⏳ 正在获取视频信息...")

        # 1. 获取视频信息（先不下载）
        requested_quality = self.config.get("video_quality", "480P")
        quality = resolve_quality(requested_quality)
        try:
            if AV_PATTERN.fullmatch(bvid_or_url):
                aid_val = int(bvid_or_url.lstrip("avAV"))
                card = await self._service.fetch_video_card(
                    aid=aid_val, page=page, quality=quality, download=False
                )
                bvid_or_aid_kw = {"aid": aid_val}
            else:
                card = await self._service.fetch_video_card(
                    bvid=bvid_or_url, page=page, quality=quality, download=False
                )
                bvid_or_aid_kw = {"bvid": bvid_or_url}
        except Exception as e:
            yield event.plain_result(f"获取视频失败: {e}")
            return

        # 2. 预估大小 & 检查限制
        size_info = None
        restriction_mode = self.config.get("download_restriction_mode", "duration_only")
        if restriction_mode != "none":
            try:
                size_info = await self._service.estimate_download_size(
                    page=page, quality=quality, **bvid_or_aid_kw
                )
            except Exception as e:
                logger.debug(f"预估视频大小失败: {e}")

        can_download, reasons = self._check_download_restrictions(
            card.duration_seconds, size_info
        )

        # 3. 执行下载或告知原因
        if not can_download and reasons:
            if self.config.get("show_download_fail_reason", True):
                reason_text = "；".join(reasons)
                yield event.plain_result(f"⚠️ 无法下载: {reason_text}")
            else:
                yield event.plain_result("⚠️ 无法下载该视频")
            card.video_path = None
        elif not can_download:
            card.video_path = None
        else:
            # 下载提示
            if self.config.get("show_download_prompt", True):
                retract = self.config.get("retract_download_prompt", False)
                prompt = self._format_size_prompt(
                    card, size_info, retract=retract,
                    requested_quality=requested_quality,
                )
                await self._send_prompt_and_maybe_retract(event, prompt)
            yield event.plain_result("⏳ 正在下载视频...")
            try:
                card.video_path = await self._service.download_video(
                    page=page, quality=quality, **bvid_or_aid_kw
                )
                if card.video_path:
                    yield event.plain_result(f"✅ 下载完成: {card.title} ({card.duration_text})")
            except Exception as e:
                yield event.plain_result(f"视频下载失败: {e}")

        # 4. 发送卡片
        chains = await self._card_builder.build_video_chains(card)
        for chain in chains:
            yield event.chain_result(chain.chain)

    # ═══════════════════════════════════════════════════
    # 指令组: /bili ...
    # ═══════════════════════════════════════════════════

    @filter.command_group("bili")
    def bili(self):
        pass

    @bili.command("下载")
    async def _cmd_dl(self, event: AstrMessageEvent, link: str = ""):
        """手动下载 B站视频。用法: /bili 下载 <链接/BV号/AV号>"""
        async for r in self._do_download(event, link):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bili.command("自动下载")
    async def cmd_auto(self, event: AstrMessageEvent, action: str = ""):
        """管理员开关群内自动下载。"""
        mode = self.config.get("passive_parse_mode", "global")
        if mode == "global":
            yield event.plain_result(
                "当前为全局被动解析模式，所有群聊均已启用。"
                "如需局部控制，请在插件配置中将被动解析模式改为 local。"
            )
            return

        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("仅限群聊使用")
            return

        gs = str(gid)
        groups: list = self.config.get("enabled_groups", [])

        if action == "on":
            if gs in self._enabled_groups:
                yield event.plain_result("已开启")
            else:
                groups.append(gs)
                self.config["enabled_groups"] = groups
                self.config.save_config()
                yield event.plain_result("✅ 已在本群开启被动解析")
        elif action == "off":
            if gs not in self._enabled_groups:
                yield event.plain_result("本群未开启被动解析")
            else:
                groups = [g for g in groups if str(g) != gs]
                self.config["enabled_groups"] = groups
                self.config.save_config()
                yield event.plain_result("✅ 已在本群关闭被动解析")
        else:
            yield event.plain_result("用法: /bili 自动下载 on|off")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bili.command("登录")
    async def cmd_login(self, event: AstrMessageEvent):
        """管理员扫码登录 B站。"""
        try:
            qr_bytes = await self._cred_mgr.login_qrcode()
        except Exception as e:
            yield event.plain_result(f"生成二维码失败: {e}")
            return
        yield event.chain_result([Image.fromBytes(qr_bytes)])
        yield event.plain_result("请用哔哩哔哩客户端扫码（3分钟内）")
        async for msg in self._cred_mgr.poll_qr():
            yield event.plain_result(msg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bili.command("状态")
    async def cmd_status(self, event: AstrMessageEvent):
        """查看插件状态。"""
        mode = self.config.get("passive_parse_mode", "global")
        mode_text = "全局" if mode == "global" else "局部"
        lines = [f"被动解析模式：{mode_text}"]

        gid = event.get_group_id()
        if mode == "global":
            lines.append("本群被动解析：已开启（全局模式）")
        elif gid:
            enabled = "已开启" if str(gid) in self._enabled_groups else "未开启"
            lines.append(f"本群被动解析：{enabled}")

        login_status = await self._cred_mgr.status()
        lines.append(login_status)

        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @bili.command("登出")
    async def cmd_logout(self, event: AstrMessageEvent):
        """管理员登出 B站账号。"""
        await self._cred_mgr.clear()
        yield event.plain_result("✅ 已登出")
