from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QGridLayout

from common.models import WindowInfo


class AppCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("cardKind", "app")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title = QLabel("应用")
        title.setObjectName("CardLabel")
        layout.addWidget(title)

        self.name_lbl = QLabel("—")
        self.name_lbl.setObjectName("AppName")
        self.name_lbl.setWordWrap(True)
        layout.addWidget(self.name_lbl)

        self.exe_lbl = QLabel("")
        self.exe_lbl.setObjectName("Mono")
        self.exe_lbl.setProperty("dim", True)
        self.exe_lbl.setWordWrap(True)
        layout.addWidget(self.exe_lbl)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        self.pid_lbl = self._mono_value()
        self.bundle_lbl = self._mono_value()
        self.user_lbl = self._mono_value()

        grid.addWidget(self._k("PID"), 0, 0)
        grid.addWidget(self.pid_lbl, 0, 1)
        grid.addWidget(self._k("Bundle / AUMID"), 1, 0)
        grid.addWidget(self.bundle_lbl, 1, 1)
        grid.addWidget(self._k("User"), 2, 0)
        grid.addWidget(self.user_lbl, 2, 1)

        layout.addLayout(grid)
        layout.addStretch()

    @staticmethod
    def _k(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FieldKey")
        return lbl

    @staticmethod
    def _mono_value() -> QLabel:
        lbl = QLabel("—")
        lbl.setObjectName("Mono")
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setWordWrap(True)
        return lbl

    def update_from(self, info: WindowInfo) -> None:
        self.name_lbl.setText(info.app_name or "—")
        exe = info.process.executable if info.process else None
        self.exe_lbl.setText(exe or "")
        self.pid_lbl.setText(str(info.process.pid) if info.process else "—")
        self.bundle_lbl.setText(info.app_bundle_id or "—")
        user = info.process.username if info.process else None
        self.user_lbl.setText(user or "—")
