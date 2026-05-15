"""焦点窗口截图。mss 抓屏 → Pillow 缩放 → QImage 发到 UI。

隐私：
  * 截图仅经内存到 UI，绝不写盘
  * 暂停时停止接收 window_changed
  * 黑名单（bundle_id 前缀 / exe basename）命中时返回占位图
"""

from __future__ import annotations

import logging
import time
from io import BytesIO
from typing import Optional

import mss
from PIL import Image
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage

from common.models import WindowInfo
from common.signals import bus
from tools.blacklist import is_blacklisted, load_blacklist

log = logging.getLogger(__name__)


class ScreenCapture(QObject):
    def __init__(self, max_fps: float = 0.5, thumb_max_size: int = 480):
        super().__init__()
        self.min_interval = 1.0 / max_fps
        self.thumb_max_size = thumb_max_size
        self._last_capture_t = 0.0
        self._sct: Optional[mss.base.MSSBase] = None
        self._last_window: Optional[WindowInfo] = None
        self._paused = False
        self._blacklist = load_blacklist()

        bus.window_changed.connect(self.on_window_changed)
        bus.paused_changed.connect(self.set_paused)

        self._timer = QTimer(self)
        self._timer.setInterval(int(self.min_interval * 1000))
        self._timer.timeout.connect(self.capture_now)
        self._timer.start()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def on_window_changed(self, info: WindowInfo) -> None:
        """事件驱动的截图：绕过 min_interval 节流，并稍等 ~120 ms 让窗口
        切换动画结束、合成器把新窗口画好，否则常截到上一个 app。"""
        self._last_window = info
        QTimer.singleShot(120, lambda: self._capture(force=True))

    def capture_now(self) -> None:
        """定时器路径：按 min_interval 节流。"""
        self._capture(force=False)

    def _capture(self, force: bool) -> None:
        if self._paused:
            return
        now = time.time()
        if not force and now - self._last_capture_t < self.min_interval:
            return
        self._last_capture_t = now

        info = self._last_window
        if info and is_blacklisted(info, self._blacklist):
            qimg = self._placeholder("已屏蔽 — 敏感应用")
            bus.screenshot_ready.emit(qimg)
            return

        try:
            qimg = self._capture_active_window(info)
        except Exception as exc:
            log.exception("capture failed")
            bus.error_occurred.emit("screen_capture", str(exc))
            return
        if qimg is not None:
            bus.screenshot_ready.emit(qimg)

    def _ensure_sct(self) -> mss.base.MSSBase:
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def _capture_active_window(self, info: Optional[WindowInfo]) -> Optional[QImage]:
        sct = self._ensure_sct()
        if info and info.geometry and info.geometry.width >= 10 and info.geometry.height >= 10:
            g = info.geometry
            bbox = {"left": g.x, "top": g.y, "width": g.width, "height": g.height}
            try:
                shot = sct.grab(bbox)
            except Exception:
                # 退化到主屏
                shot = sct.grab(sct.monitors[1])
        else:
            shot = sct.grab(sct.monitors[1])

        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img.thumbnail((self.thumb_max_size, self.thumb_max_size))
        buf = BytesIO()
        img.save(buf, format="PNG")
        qimg = QImage.fromData(buf.getvalue(), "PNG")
        return qimg if not qimg.isNull() else None

    @staticmethod
    def _placeholder(text: str) -> QImage:
        from PySide6.QtGui import QColor, QPainter
        img = QImage(320, 200, QImage.Format.Format_RGB32)
        img.fill(QColor("#2a2f3a"))
        painter = QPainter(img)
        painter.setPen(QColor("#f1c97b"))
        painter.drawText(img.rect(), 0x84, text)  # AlignCenter
        painter.end()
        return img
