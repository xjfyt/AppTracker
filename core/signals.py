"""全局信号总线 — 各模块通过它发布事件，UI 订阅消费。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from core.models import ActivityStats, BrowserTab, WindowInfo


class SignalBus(QObject):
    """所有跨模块通信走这里，避免直接依赖。"""

    window_changed = Signal(WindowInfo)         # 焦点窗口变化（含切换 + 标题/位置变化）
    activity_updated = Signal(ActivityStats)    # 每秒键鼠聚合统计
    browser_tab_updated = Signal(BrowserTab)    # 浏览器扩展推送
    browser_connected = Signal(bool)            # 扩展连接状态变化
    screenshot_ready = Signal(QImage)           # 新截图就绪
    error_occurred = Signal(str, str)           # (source, message)
    paused_changed = Signal(bool)               # 全局暂停


bus = SignalBus()
