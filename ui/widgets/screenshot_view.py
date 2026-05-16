from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from common.signals import bus


class ScreenshotView(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("窗口截图")
        title.setObjectName("CardLabel")
        head.addWidget(title)
        head.addStretch()
        # 默认关闭，需用户点击启用。bus.screenshot_enabled_changed 也可以
        # 由 API 端点远程切换，UI 这边订阅信号保持同步
        self.toggle_btn = QPushButton("启用")
        self.toggle_btn.setObjectName("MiniButton")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(False)
        self.toggle_btn.setToolTip(
            "实时截图默认关闭以省 CPU；点击启用后会监听焦点切换 + 每 2s 抓一帧。\n"
            "API: GET/POST /api/v1/screenshot/enabled"
        )
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        head.addWidget(self.toggle_btn)
        layout.addLayout(head)

        self.image_lbl = QLabel("（截图已关闭 — 点上方「启用」按钮）")
        self.image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_lbl.setMinimumHeight(140)
        self.image_lbl.setObjectName("Screenshot")
        layout.addWidget(self.image_lbl, 1)

        self.caption = QLabel("")
        self.caption.setObjectName("Caption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.caption)

        # 接 API / 其他来源对开关的设置，保持 UI 同步
        bus.screenshot_enabled_changed.connect(self._on_enabled_changed)

    def _on_toggle_clicked(self, checked: bool) -> None:
        bus.screenshot_enabled_changed.emit(checked)

    def _on_enabled_changed(self, enabled: bool) -> None:
        # 防止信号 → 槽 → emit 循环：先 block
        was = self.toggle_btn.blockSignals(True)
        try:
            self.toggle_btn.setChecked(enabled)
            self.toggle_btn.setText("已启用" if enabled else "启用")
        finally:
            self.toggle_btn.blockSignals(was)
        if not enabled:
            self.image_lbl.setText("（截图已关闭 — 点上方「启用」按钮）")
            self.image_lbl.setPixmap(QPixmap())
            self.caption.setText("")

    def update_image(self, qimg: QImage) -> None:
        if qimg.isNull():
            return
        pix = QPixmap.fromImage(qimg)
        target = self.image_lbl.size()
        scaled = pix.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_lbl.setPixmap(scaled)
        self.caption.setText(time.strftime("Captured %H:%M:%S"))
