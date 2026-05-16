from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from common.models import ActivityStats, BrowserTab, WindowInfo
from common.signals import bus
from tools.shell_installer import install_powershell_integration
from ui.assets import app_icon
from ui.widgets.activity_card import ActivityCard
from ui.widgets.app_card import AppCard
from ui.widgets.browser_card import BrowserCard
from ui.widgets.document_list import DocumentList
from ui.widgets.error_log import ErrorLog
from ui.widgets.file_manager_card import FileManagerCard
from ui.widgets.screenshot_view import ScreenshotView
from ui.widgets.terminal_card import TerminalCard
from ui.widgets.window_card import WindowCard

log = logging.getLogger(__name__)


class TopBar(QFrame):
    """顶栏：标题 + 平台 + 时间 + 暂停按钮 + AX 权限横幅触发。"""

    def __init__(self):
        super().__init__()
        self.setObjectName("TopBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        self.pause_btn = QPushButton("⏸  暂停")
        self.pause_btn.setObjectName("PauseButton")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_toggle)
        layout.addWidget(self.pause_btn)

        title = QLabel("Active Tracker")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        layout.addStretch()

        self.platform_lbl = QLabel(sys.platform)
        self.platform_lbl.setObjectName("Badge")
        layout.addWidget(self.platform_lbl)

        self.time_lbl = QLabel("—")
        self.time_lbl.setObjectName("Mono")
        layout.addWidget(self.time_lbl)

        # 仅 Windows：PowerShell 的 cd 不更新 PEB，需要装 shell 集成才能追到
        if sys.platform == "win32":
            self.install_shell_btn = QPushButton("🛠 装 cd 追踪")
            self.install_shell_btn.setObjectName("MiniButton")
            self.install_shell_btn.setToolTip(
                "PowerShell 的 cd 只更新 $PWD，不更新进程 PEB，psutil 拿不到。\n"
                "点击会向你的 $PROFILE 追加一行 source；幂等，重复点不会重复写。"
            )
            self.install_shell_btn.clicked.connect(self._install_shell_integration)
            layout.addWidget(self.install_shell_btn)

        self.copy_token_btn = QPushButton("复制 Token")
        self.copy_token_btn.setObjectName("MiniButton")
        self.copy_token_btn.clicked.connect(self._copy_token)
        layout.addWidget(self.copy_token_btn)

    def _on_toggle(self, checked: bool) -> None:
        self.pause_btn.setText("▶  恢复" if checked else "⏸  暂停")
        bus.paused_changed.emit(checked)

    def set_time(self, ts: float) -> None:
        self.time_lbl.setText(time.strftime("%H:%M:%S", time.localtime(ts)))

    def _copy_token(self) -> None:
        path = Path.home() / ".active_tracker" / "token"
        if not path.exists():
            QMessageBox.information(self, "Token", "Token 尚未生成（启动 BrowserBridge 后会自动写入）。")
            return
        QGuiApplication.clipboard().setText(path.read_text().strip())
        self.copy_token_btn.setText("✓ 已复制")
        QTimer.singleShot(1500, lambda: self.copy_token_btn.setText("复制 Token"))

    def _install_shell_integration(self) -> None:
        result = install_powershell_integration()
        if result.ok:
            QMessageBox.information(self, "shell 集成", result.message)
            self.install_shell_btn.setText("✓ 已装 cd 追踪")
            QTimer.singleShot(3000, lambda: self.install_shell_btn.setText("🛠 装 cd 追踪"))
        else:
            QMessageBox.warning(self, "安装失败", result.message)


class PermissionBanner(QFrame):
    """macOS 未授予辅助功能权限时显示的黄色横幅。"""

    def __init__(self, on_open):
        super().__init__()
        self.setObjectName("PermissionBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        msg = QLabel("⚠ macOS 辅助功能权限未授予 — 标题/几何/文档字段不可用。")
        msg.setObjectName("BannerText")
        layout.addWidget(msg)
        layout.addStretch()
        btn = QPushButton("打开系统设置")
        btn.setObjectName("MiniButton")
        btn.clicked.connect(on_open)
        layout.addWidget(btn)


class MainWindow(QMainWindow):
    def __init__(self, monitor=None):
        super().__init__()
        self.setWindowTitle("Active Tracker")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        # 显式给一个 ≤ 常见笔记本可用区域（1366×768 去掉任务栏 ~728px）的下限，
        # 否则 layout 的隐式最小高度（>950px）在小屏上触发
        # "QWindowsWindow::setGeometry: Unable to set geometry..." 警告
        self.setMinimumSize(900, 560)
        self.monitor = monitor   # 可选：用于触发授权弹窗

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.topbar = TopBar()
        outer.addWidget(self.topbar)

        # macOS 权限横幅（默认隐藏，需要时显示）
        self.banner = PermissionBanner(self._on_open_settings)
        self.banner.setVisible(False)
        outer.addWidget(self.banner)

        # 主体 splitter
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setObjectName("BodySplitter")
        body.setHandleWidth(8)

        # 左列
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(14, 14, 7, 14)
        left_lay.setSpacing(14)
        self.app_card = AppCard()
        self.window_card = WindowCard()
        self.doc_list = DocumentList()
        left_lay.addWidget(self.app_card)
        left_lay.addWidget(self.window_card)
        left_lay.addWidget(self.doc_list, 1)

        # 右列
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(7, 14, 14, 14)
        right_lay.setSpacing(14)
        self.browser_card = BrowserCard()
        self.file_manager_card = FileManagerCard()
        self.file_manager_card.setVisible(False)
        self.terminal_card = TerminalCard()
        self.terminal_card.setVisible(False)
        self.activity_card = ActivityCard()
        self.screenshot = ScreenshotView()
        right_lay.addWidget(self.browser_card)
        right_lay.addWidget(self.file_manager_card)
        right_lay.addWidget(self.terminal_card)
        right_lay.addWidget(self.activity_card)
        right_lay.addWidget(self.screenshot, 1)

        body.addWidget(left)
        body.addWidget(right)
        body.setStretchFactor(0, 5)
        body.setStretchFactor(1, 4)
        outer.addWidget(body, 1)

        # 底部错误日志
        self.error_log = ErrorLog()
        bottom = QWidget()
        bot_lay = QHBoxLayout(bottom)
        bot_lay.setContentsMargins(14, 0, 14, 14)
        bot_lay.addWidget(self.error_log)
        outer.addWidget(bottom)

        self.setCentralWidget(central)

        # 接到信号
        bus.window_changed.connect(self._on_window_changed)
        bus.activity_updated.connect(self._on_activity)
        bus.browser_tab_updated.connect(self._on_browser_tab)
        bus.browser_connected.connect(self.browser_card.set_connected)
        bus.screenshot_ready.connect(self.screenshot.update_image)
        bus.error_occurred.connect(self._on_error)
        bus.paused_changed.connect(self._on_paused)

    # ---- bus handlers ----

    def _on_window_changed(self, info: WindowInfo) -> None:
        self.topbar.set_time(info.timestamp)
        self.app_card.update_from(info)
        self.window_card.update_from(info)
        self.doc_list.update_from(info)

        # 集成结果：非空才显示对应卡片
        if info.file_manager_state and info.file_manager_state.windows:
            self.file_manager_card.update_from(info.file_manager_state)
            self.file_manager_card.setVisible(True)
        else:
            self.file_manager_card.clear()
            self.file_manager_card.setVisible(False)
        if info.terminal_context and (info.terminal_context.shells or info.terminal_context.running):
            self.terminal_card.update_from(info.terminal_context)
            self.terminal_card.setVisible(True)
        else:
            self.terminal_card.clear()
            self.terminal_card.setVisible(False)

    def _on_activity(self, stats: ActivityStats) -> None:
        self.activity_card.update_from(stats)

    def _on_browser_tab(self, tab: BrowserTab) -> None:
        self.browser_card.update_from(tab)

    def _on_error(self, source: str, message: str) -> None:
        self.error_log.append(source, message)
        if "Accessibility permission" in message and sys.platform == "darwin":
            self.banner.setVisible(True)

    def _on_paused(self, paused: bool) -> None:
        self.setWindowOpacity(0.85 if paused else 1.0)

    # ---- AX permission banner ----

    def _on_open_settings(self) -> None:
        if self.monitor is None:
            return
        opener = getattr(self.monitor, "prompt_ax_permission", None)
        if callable(opener):
            opener()
        opener2 = getattr(self.monitor, "open_accessibility_settings", None)
        if callable(opener2):
            opener2()

    def show_ax_banner(self, show: bool = True) -> None:
        self.banner.setVisible(show)
