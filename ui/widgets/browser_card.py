from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from common.models import BrowserTab

BROWSER_GLYPH = {
    "chrome": "🟢", "edge": "🔵", "firefox": "🦊", "brave": "🦁",
    "arc": "🌐", "opera": "🔴", "safari": "🧭",
}


class BrowserCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("cardKind", "browser")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        head = QLabel("浏览器")
        head.setObjectName("CardLabel")
        layout.addWidget(head)

        self.app_lbl = QLabel("— (未连接扩展)")
        self.app_lbl.setObjectName("AppName")
        layout.addWidget(self.app_lbl)

        self.title_lbl = QLabel("")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.title_lbl)

        self.url_lbl = QLabel("")
        self.url_lbl.setObjectName("Mono")
        self.url_lbl.setProperty("dim", True)
        self.url_lbl.setWordWrap(True)
        self.url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.url_lbl)

        meta = QGridLayout()
        meta.setColumnStretch(1, 1)
        meta.setHorizontalSpacing(12)
        self.status_lbl = QLabel("等待扩展连接…")
        self.status_lbl.setObjectName("FieldKey")
        meta.addWidget(self.status_lbl, 0, 0, 1, 2)
        layout.addLayout(meta)
        layout.addStretch()

    def set_connected(self, connected: bool) -> None:
        if connected:
            self.status_lbl.setText("● 已连接")
            self.status_lbl.setProperty("ok", True)
        else:
            self.status_lbl.setText("○ 未连接")
            self.status_lbl.setProperty("ok", False)
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def update_from(self, tab: BrowserTab) -> None:
        glyph = BROWSER_GLYPH.get(tab.browser, "🌐")
        self.app_lbl.setText(f"{glyph} {tab.browser.capitalize()}")
        self.title_lbl.setText(tab.title or "—")
        self.url_lbl.setText(tab.url or "—")
