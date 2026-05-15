"""集中维护"最新状态" — 订阅 bus，缓存供 REST 端点查询，并广播给 SSE/WS。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Optional

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

from common.models import ActivityStats, BrowserTab, WindowInfo
from common.signals import bus

log = logging.getLogger(__name__)


class APIState:
    """单例：缓存最新状态 + 提供 asyncio 订阅队列给 SSE/WS 推流用。"""

    def __init__(self) -> None:
        self._window: Optional[WindowInfo] = None
        self._activity: Optional[ActivityStats] = None
        self._browser_tab: Optional[BrowserTab] = None
        self._latest_screenshot_png: Optional[bytes] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._dropped_count = 0

        bus.window_changed.connect(self._on_window)
        bus.activity_updated.connect(self._on_activity)
        bus.browser_tab_updated.connect(self._on_browser_tab)
        bus.screenshot_ready.connect(self._on_screenshot)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """API server 启动时调用，告诉 state 用哪个 asyncio loop 派发。"""
        self._loop = loop

    # ---- snapshot for REST ----

    def snapshot(self) -> dict:
        return {
            "window": asdict(self._window) if self._window else None,
            "activity": asdict(self._activity) if self._activity else None,
            "browser_tab": asdict(self._browser_tab) if self._browser_tab else None,
            "has_screenshot": self._latest_screenshot_png is not None,
        }

    def latest_screenshot(self) -> Optional[bytes]:
        return self._latest_screenshot_png

    # ---- subscription for SSE / WS ----

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    # ---- bus handlers (Qt thread → push to asyncio loop) ----

    def _broadcast(self, event: dict) -> None:
        """从 Qt 线程把事件丢回 asyncio loop，再 fanout 给所有订阅者。"""
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def _fanout() -> None:
            for q in list(self._subscribers):
                if q.full():
                    try:
                        q.get_nowait()   # 丢最旧的一条防止背压
                        self._dropped_count += 1
                        if self._dropped_count == 1 or self._dropped_count % 100 == 0:
                            log.warning(
                                "API subscriber queue full, dropping events "
                                "(dropped=%d, consider faster consumer)",
                                self._dropped_count,
                            )
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

        try:
            loop.call_soon_threadsafe(_fanout)
        except RuntimeError:
            pass

    def _on_window(self, info: WindowInfo) -> None:
        self._window = info
        self._broadcast({"type": "window_changed", "data": asdict(info)})

    def _on_activity(self, stats: ActivityStats) -> None:
        self._activity = stats
        self._broadcast({"type": "activity_updated", "data": asdict(stats)})

    def _on_browser_tab(self, tab: BrowserTab) -> None:
        self._browser_tab = tab
        self._broadcast({"type": "browser_tab_updated", "data": asdict(tab)})

    def _on_screenshot(self, qimg: QImage) -> None:
        try:
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            if qimg.save(buf, "PNG"):
                self._latest_screenshot_png = bytes(ba)
            buf.close()
        except Exception as exc:
            log.debug("screenshot to PNG failed: %s", exc)
            return
        # 不在事件流里包大图，发"有更新"通知，客户端再拉 /screenshot
        self._broadcast({"type": "screenshot_ready"})


# 单例
api_state = APIState()
