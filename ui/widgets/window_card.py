from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from core.models import WindowInfo


class WindowCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        head = QLabel("窗口")
        head.setObjectName("CardLabel")
        layout.addWidget(head)

        self.title_lbl = QLabel("—")
        self.title_lbl.setObjectName("WindowTitle")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.title_lbl)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        self.class_lbl = self._v()
        self.id_lbl = self._v()
        self.geom_lbl = self._v()
        self.screen_lbl = self._v()
        for row, (k, v) in enumerate([
            ("Class", self.class_lbl),
            ("Window ID", self.id_lbl),
            ("Geometry", self.geom_lbl),
            ("Screen", self.screen_lbl),
        ]):
            grid.addWidget(self._k(k), row, 0)
            grid.addWidget(v, row, 1)
        layout.addLayout(grid)
        layout.addStretch()

    @staticmethod
    def _k(s: str) -> QLabel:
        l = QLabel(s)
        l.setObjectName("FieldKey")
        return l

    @staticmethod
    def _v() -> QLabel:
        l = QLabel("—")
        l.setObjectName("Mono")
        l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        l.setWordWrap(True)
        return l

    def update_from(self, info: WindowInfo) -> None:
        self.title_lbl.setText(info.window_title or "—")
        self.class_lbl.setText(info.window_class or "—")
        self.id_lbl.setText(info.window_id or "—")
        if info.geometry:
            g = info.geometry
            self.geom_lbl.setText(f"{g.x}, {g.y}  {g.width}×{g.height}")
            self.screen_lbl.setText(str(g.screen_index))
        else:
            self.geom_lbl.setText("—")
            self.screen_lbl.setText("—")
