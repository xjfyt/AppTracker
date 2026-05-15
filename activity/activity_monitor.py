"""键鼠活动聚合统计。

隐私：_on_key 回调中不读取 key 的任何属性，只记录事件计数。
"""

from __future__ import annotations

import logging
import time
from collections import deque

from PySide6.QtCore import QObject, QTimer

from common.models import ActivityStats
from common.signals import bus

log = logging.getLogger(__name__)


def _patch_pynput_for_pyobjc12() -> None:
    """pynput 1.8.x 在 pyobjc 12 上找不到 HIServices.AXIsProcessTrusted，手动补上。"""
    import sys
    if sys.platform != "darwin":
        return
    try:
        import HIServices  # type: ignore[import-not-found]
    except Exception:
        return
    if hasattr(HIServices, "AXIsProcessTrusted"):
        try:
            HIServices.AXIsProcessTrusted  # 触发实际查找
            return
        except (KeyError, AttributeError):
            pass
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore[import-not-found]
        HIServices.AXIsProcessTrusted = AXIsProcessTrusted
    except Exception as exc:
        log.debug("Failed to patch HIServices.AXIsProcessTrusted: %s", exc)


class ActivityMonitor(QObject):
    def __init__(self, window_seconds: int = 60):
        super().__init__()
        self.window_seconds = window_seconds
        self.events: deque[tuple[float, str]] = deque()
        self.last_mouse_pos: tuple[int, int] | None = None
        self.mouse_distance: float = 0.0
        self.last_input_time: float = time.time()
        self._paused: bool = False

        self.kb_listener = None
        self.mouse_listener = None

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._tick)

    # ---- public API ----

    def start(self) -> None:
        try:
            _patch_pynput_for_pyobjc12()
            from pynput import keyboard, mouse  # 延迟引入，权限失败时不至于卡进程
            self.kb_listener = keyboard.Listener(on_press=self._on_key)
            self.mouse_listener = mouse.Listener(
                on_click=self._on_click,
                on_move=self._on_move,
                on_scroll=self._on_scroll,
            )
            self.kb_listener.start()
            self.mouse_listener.start()
        except Exception as exc:
            log.exception("pynput failed to start")
            bus.error_occurred.emit(
                "activity_monitor",
                f"pynput failed: {exc} (macOS 需在 输入监控 中授权)",
            )
        self.tick_timer.start()

    def stop(self) -> None:
        for listener in (self.kb_listener, self.mouse_listener):
            try:
                if listener is not None:
                    listener.stop()
            except Exception:
                pass
        self.tick_timer.stop()

    def set_paused(self, paused: bool) -> None:
        # 暂停时只停止 emit 信号，listener 仍在跑（防止恢复时计数错乱）
        self._paused = paused

    # ---- callbacks (隐私敏感)----

    def _on_key(self, _key) -> None:
        # 不读取 _key 任何属性
        self.events.append((time.time(), "key"))
        self.last_input_time = time.time()

    def _on_click(self, _x, _y, _button, pressed) -> None:
        if pressed:
            self.events.append((time.time(), "click"))
            self.last_input_time = time.time()

    def _on_move(self, x, y) -> None:
        now = time.time()
        if self.last_mouse_pos is not None:
            dx = x - self.last_mouse_pos[0]
            dy = y - self.last_mouse_pos[1]
            self.mouse_distance += (dx * dx + dy * dy) ** 0.5
        self.last_mouse_pos = (x, y)
        self.last_input_time = now

    def _on_scroll(self, _x, _y, _dx, _dy) -> None:
        self.events.append((time.time(), "scroll"))
        self.last_input_time = time.time()

    # ---- timer ----

    def _tick(self) -> None:
        now = time.time()
        cutoff = now - self.window_seconds
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
        if self._paused:
            return
        keys = sum(1 for _, k in self.events if k == "key")
        clicks = sum(1 for _, k in self.events if k == "click")
        scrolls = sum(1 for _, k in self.events if k == "scroll")
        stats = ActivityStats(
            timestamp=now,
            window_seconds=self.window_seconds,
            keys_count=keys,
            clicks_count=clicks,
            scrolls_count=scrolls,
            mouse_distance_px=self.mouse_distance,
            idle_seconds=now - self.last_input_time,
        )
        bus.activity_updated.emit(stats)
