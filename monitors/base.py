"""所有平台 WindowMonitor 的抽象基类。"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer

from common.models import WindowInfo

log = logging.getLogger(__name__)

FALLBACK_INTERVAL_MS = 2000   # 2s 兜底轮询


class WindowMonitor(QObject):
    """子类实现 _start_native / _stop_native / query_now 三个方法。"""

    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self._running = False
        self._paused = False
        self._last_identity = None
        # 兜底定时器：每 2s 主动查一次，发现差异就 emit
        self._fallback_timer = QTimer(self)
        self._fallback_timer.setInterval(FALLBACK_INTERVAL_MS)
        self._fallback_timer.timeout.connect(self._on_fallback_tick)

    # ----- 子类需实现 -----

    def _start_native(self) -> None:
        raise NotImplementedError

    def _stop_native(self) -> None:
        raise NotImplementedError

    def query_now(self) -> WindowInfo:
        raise NotImplementedError

    # ----- 通用流程 -----

    def start(self) -> None:
        if self._running:
            return
        try:
            self._start_native()
        except Exception as exc:
            log.exception("native start failed")
            self.bus.error_occurred.emit(self.__class__.__name__, f"start failed: {exc}")
        self._fallback_timer.start()
        self._running = True
        self.emit_current("initial")

    def stop(self) -> None:
        if not self._running:
            return
        self._fallback_timer.stop()
        try:
            self._stop_native()
        except Exception as exc:
            log.exception("native stop failed")
        self._running = False

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def emit_current(self, reason: str = "event") -> None:
        """子类的事件回调应调用这个；自动做指纹去重并 emit。"""
        if self._paused:
            return
        try:
            info = self.query_now()
        except Exception as exc:
            log.exception("query_now failed (%s)", reason)
            self.bus.error_occurred.emit(self.__class__.__name__, str(exc))
            return
        key = info.identity_key()
        if key == self._last_identity and reason != "initial":
            return
        self._last_identity = key
        self.bus.window_changed.emit(info)

    def _on_fallback_tick(self) -> None:
        self.emit_current("fallback")
