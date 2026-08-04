"""凭证管理：B站账号的加载、扫码登录、状态查询、登出。

Credentials 持久化到插件 data 目录下的 credential.json，
同时同步到 WebUI 配置的 bilibili_cookies 字段。
"""

import asyncio
import json
from pathlib import Path

import httpx
from bilibili_api import Credential
from bilibili_api.user import get_self_info

from astrbot.api import AstrBotConfig, logger

from .constants import PLUGIN_NAME


class CredentialManager:
    """管理 B站 Credential 的生命周期。

    参数:
        data_dir: 插件数据目录（凭证文件存储于此）。
        config:   AstrBotConfig 实例（读写 bilibili_cookies）。
        client:   httpx.AsyncClient（用于二维码 API 调用）。
    """

    QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
    QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

    def __init__(self, data_dir: Path, config: AstrBotConfig, client: httpx.AsyncClient):
        self._file = data_dir / "credential.json"
        self._config = config
        self._client = client
        self._credential: Credential | None = None
        self._qr_key: str = ""
        self._load()

    # ── 持久化 ─────────────────────────────────────────

    def _load(self):
        """从磁盘文件加载凭证。"""
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                self._credential = Credential.from_cookies(data)
            except Exception as e:
                logger.error(f"加载凭证失败: {e}")

    def _save(self):
        """将凭证保存到磁盘并同步到 WebUI 配置。"""
        if self._credential:
            self._file.write_text(
                json.dumps(self._credential.get_cookies(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # 同步到 WebUI 可见的 bilibili_cookies 配置
            cookie_parts = []
            for k, v in self._credential.get_cookies().items():
                if v:
                    cookie_parts.append(f"{k}={v}")
            self._config["bilibili_cookies"] = "; ".join(cookie_parts)
            self._config.save_config()

    # ── 获取有效凭证 ───────────────────────────────────

    async def get(self) -> Credential | None:
        """返回一个有效的 Credential 或 None。

        优先级：WebUI 配置 > 本地文件。会自动校验和刷新。
        """
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

        # 回退到本地文件凭证
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

    # ── 扫码登录 ───────────────────────────────────────

    async def login_qrcode(self) -> bytes:
        """生成登录二维码图片（PNG 字节），调用方负责发送给用户。"""
        import qrcode
        from io import BytesIO

        resp = await self._client.get(self.QR_GENERATE)
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"生成二维码失败: {data.get('message', '未知错误')}")
        self._qr_key = data["data"]["qrcode_key"]
        qr_url = data["data"]["url"]
        img = qrcode.make(qr_url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def poll_qr(self):
        """轮询扫码状态（最多 90 次 × 2 秒 = 3 分钟）。

        这是一个异步生成器，每次 yield 一条状态消息。
        """
        if not self._qr_key:
            yield "二维码未生成"
            return
        for _ in range(90):
            try:
                resp = await self._client.get(
                    self.QR_POLL, params={"qrcode_key": self._qr_key}
                )
                resp_data = resp.json()
            except Exception as e:
                yield f"检查失败: {e}"
                return

            code = resp_data.get("data", {}).get("code") if resp_data.get("code") == 0 else resp_data.get("code")
            if code == 0:
                # 登录成功，从 Set-Cookie 提取凭证
                cookies: dict = {}
                for key in resp.cookies:
                    cookies[key] = resp.cookies[key]
                logger.info(f"Login cookies: {list(cookies.keys())}, SESSDATA={'有' if cookies.get('SESSDATA') else '无'}")
                if cookies.get("SESSDATA"):
                    self._credential = Credential.from_cookies(cookies)
                    self._save()
                    try:
                        profile = await get_self_info(self._credential)
                        uname = profile.get("name", "未知")
                        yield f"✅ 登录成功！账号: {uname}"
                    except Exception:
                        yield "✅ 登录成功！"
                else:
                    yield "✅ 登录成功！（但未能提取凭证，请手动填写 Cookie）"
                return
            elif code in (86090, 86101):
                if code == 86090:
                    yield "📱 已扫描，请在手机上确认..."
            elif code == 86038:
                yield "⏰ 二维码已过期"
                return
            else:
                msg = resp_data.get("data", {}).get("message", "") or resp_data.get("message", "")
                yield f"状态异常(code={code}): {msg}"
                return
            await asyncio.sleep(2)
        yield "⏰ 登录超时"

    # ── 状态 & 登出 ────────────────────────────────────

    async def status(self) -> str:
        """返回当前登录状态的人类可读描述。"""
        cred = await self.get()
        if not cred:
            return "❌ 未登录"
        try:
            profile = await get_self_info(cred)
            return f"✅ 已登录: {profile.get('name', '未知')} (UID: {profile.get('mid', '?')})"
        except Exception as e:
            return f"⚠️ 凭证可能无效: {e}"

    async def clear(self):
        """登出：清除内存、磁盘和 WebUI 配置中的凭证。"""
        self._credential = None
        self._file.unlink(missing_ok=True)
        self._config["bilibili_cookies"] = ""
        self._config.save_config()
