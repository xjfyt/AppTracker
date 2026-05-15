"""焦点窗口截图。mss 抓屏 → 直接构造 QImage 发到 UI。

隐私：
  * 截图仅经内存到 UI，绝不写盘
  * 暂停时停止接收 window_changed
  * 黑名单（bundle_id 前缀 / exe basename）命中时返回占位图
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import mss
from PySide6.QtCore import QObject, Qt, QTimer
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
        # mss.monitors[0] 是 "virtual all-screens"，monitors[1..] 是各物理屏；
        # 多屏睡眠 / 单屏 / 锁屏下可能 monitors[1] 缺或 monitors[0] 尺寸为 0
        fallback_monitor = None
        for m in sct.monitors[1:] + [sct.monitors[0]]:
            if m.get("width", 0) > 0 and m.get("height", 0) > 0:
                fallback_monitor = m
                break
        if fallback_monitor is None:
            return None   # 没显示器可抓（合盖、锁屏等），静默跳过

        if info and info.geometry and info.geometry.width >= 10 and info.geometry.height >= 10:
            g = info.geometry
            bbox = {"left": g.x, "top": g.y, "width": g.width, "height": g.height}
            try:
                shot = sct.grab(bbox)
            except Exception:
                shot = sct.grab(fallback_monitor)
        else:
            shot = sct.grab(fallback_monitor)

        # 直接从 BGRA 字节构造 QImage：mss 给的 bgra 在小端机器上字节序为
        # B-G-R-A，正好和 Qt 的 ARGB32（小端 uint32 = 0xAARRGGBB）一致，
        # 不需要 rgbSwapped。.copy() 让 QImage 脱离 mss 的原始 buffer
        width, height = shot.size
        qimg = QImage(
            bytes(shot.bgra), width, height, width * 4,
            QImage.Format.Format_ARGB32,
        ).copy()
        if qimg.isNull():
            return None
        # 按长边缩放到 thumb_max_size
        if qimg.width() > self.thumb_max_size or qimg.height() > self.thumb_max_size:
            qimg = qimg.scaled(
                self.thumb_max_size, self.thumb_max_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return qimg

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
