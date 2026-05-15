"""浏览器扩展 ↔ Python 主程序的 WebSocket 桥。"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from pathlib import Path

import websockets
from PySide6.QtCore import QObject

from common.models import BrowserTab
from common.signals import bus
from tools.port import find_free_port

log = logging.getLogger(__name__)

TOKEN_DIR = Path.home() / ".active_tracker"
TOKEN_PATH = TOKEN_DIR / "token"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5006
PORT_FALLBACK_RANGE = 5    # 占用时往后再试 N 个端口


class BrowserBridge(QObject):
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        super().__init__()
        self.host = host
        try:
            self.port = find_free_port(host, port, port + PORT_FALLBACK_RANGE)
            if self.port != port:
                log.warning(
                    "BrowserBridge: port %d busy, using %d (扩展端的端口也要相应改)",
                    port, self.port,
                )
        except RuntimeError:
            self.port = port   # 退化到首选端口，让 serve() 抛错给上层
            log.error("BrowserBridge: no free port near %d, will likely fail", port)
        self.token = self._load_or_create_token()
        self.clients: set = set()
        self._server = None
        self._paused = False
        bus.paused_changed.connect(self.set_paused)

    @staticmethod
    def _load_or_create_token() -> str:
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        if TOKEN_PATH.exists():
            return TOKEN_PATH.read_text().strip()
        t = secrets.token_urlsafe(32)
        TOKEN_PATH.write_text(t)
        try:
            TOKEN_PATH.chmod(0o600)
        except OSError:
            pass
        return t

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    async def _handler(self, ws):
        # 5s 内必须发送 {"token": "..."}
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            auth = json.loads(raw)
            if auth.get("token") != self.token:
                await ws.close(code=4001, reason="bad token")
                return
        except Exception as exc:
            log.debug("auth failed: %s", exc)
            return

        self.clients.add(ws)
        bus.browser_connected.emit(True)
        log.info("Browser extension connected from %s", getattr(ws, "remote_address", "?"))

        try:
            async for raw in ws:
                if self._paused:
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "tab_update":
                    tab = BrowserTab(
                        browser=str(msg.get("browser", "chrome")),
                        pid=msg.get("pid"),
                        window_id=msg.get("windowId"),
                        tab_id=msg.get("tabId"),
                        url=str(msg.get("url", "")),
                        title=str(msg.get("title", "")),
                        favicon_url=msg.get("favIconUrl"),
                        is_active=bool(msg.get("active", True)),
                    )
                    bus.browser_tab_updated.emit(tab)
        except websockets.ConnectionClosed:
            pass
        except Exception as exc:
            log.exception("ws handler error: %s", exc)
            bus.error_occurred.emit("browser_bridge", str(exc))
        finally:
            self.clients.discard(ws)
            if not self.clients:
                bus.browser_connected.emit(False)
                log.info("Browser extension disconnected")

    async def serve(self) -> None:
        log.info("BrowserBridge listening on ws://%s:%s", self.host, self.port)
        async with websockets.serve(self._handler, self.host, self.port):
            await asyncio.Future()  # run forever

    def start_in_loop(self, loop: asyncio.AbstractEventLoop) -> asyncio.Task:
        return loop.create_task(self.serve())
