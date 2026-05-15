from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout,
)


class ErrorLog(QFrame):
    MAX = 50

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("cardKind", "errors")

        self.entries: deque[str] = deque(maxlen=self.MAX)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.title = QLabel("▶ 错误日志 (0)")
        self.title.setObjectName("CardLabel")
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title.mousePressEvent = self._toggle  # type: ignore[assignment]
        header.addWidget(self.title)
        header.addStretch()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("MiniButton")
        self.clear_btn.clicked.connect(self.clear)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.setObjectName("ErrorList")
        self.list.setVisible(False)
        layout.addWidget(self.list)

    def _toggle(self, _ev) -> None:
        self.list.setVisible(not self.list.isVisible())
        self._refresh_title()

    def append(self, source: str, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} [{source}] {message}"
        self.entries.append(line)
        self.list.addItem(line)
        while self.list.count() > self.MAX:
            self.list.takeItem(0)
        self._refresh_title()

    def clear(self) -> None:
        self.entries.clear()
        self.list.clear()
        self._refresh_title()

    def _refresh_title(self) -> None:
        marker = "▼" if self.list.isVisible() else "▶"
        self.title.setText(f"{marker} 错误日志 ({len(self.entries)})")
