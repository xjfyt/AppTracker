from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from common.models import ActivityStats


class Sparkline(QWidget):
    """简易折线图，显示最近 60 个采样点的"键+点击+滚动"总和。"""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(48)
        self.history: deque[int] = deque([0] * 60, maxlen=60)

    def push(self, value: int) -> None:
        self.history.append(value)
        self.update()

    def paintEvent(self, _ev) -> None:
        if not self.history:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        peak = max(self.history) or 1
        pen = QPen(QColor("#6ee7a8"), 2)
        painter.setPen(pen)
        n = len(self.history)
        step = w / max(1, n - 1)
        points = []
        for i, v in enumerate(self.history):
            x = i * step
            y = h - (v / peak) * (h - 4) - 2
            points.append((x, y))
        for i in range(1, len(points)):
            painter.drawLine(int(points[i - 1][0]), int(points[i - 1][1]),
                             int(points[i][0]), int(points[i][1]))


class ActivityCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        head = QLabel("活动（过去 1 分钟）")
        head.setObjectName("CardLabel")
        layout.addWidget(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        self.keys_lbl = self._big("0")
        self.clicks_lbl = self._big("0")
        self.scrolls_lbl = self._big("0")
        self.mouse_lbl = self._big("0 px")
        self.idle_lbl = self._big("0.0 s")

        for col, (k, v) in enumerate([
            ("⌨ 按键", self.keys_lbl),
            ("🖱 点击", self.clicks_lbl),
            ("↕ 滚动", self.scrolls_lbl),
        ]):
            grid.addWidget(self._k(k), 0, col, alignment=Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(v, 1, col, alignment=Qt.AlignmentFlag.AlignHCenter)

        for col, (k, v) in enumerate([
            ("🐭 鼠标距离", self.mouse_lbl),
            ("💤 空闲", self.idle_lbl),
        ]):
            grid.addWidget(self._k(k), 2, col, alignment=Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(v, 3, col, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(grid)

        self.sparkline = Sparkline()
        layout.addWidget(self.sparkline)

    @staticmethod
    def _k(s: str) -> QLabel:
        l = QLabel(s)
        l.setObjectName("FieldKey")
        return l

    @staticmethod
    def _big(s: str) -> QLabel:
        l = QLabel(s)
        l.setObjectName("BigNumber")
        return l

    def update_from(self, stats: ActivityStats) -> None:
        self.keys_lbl.setText(str(stats.keys_count))
        self.clicks_lbl.setText(str(stats.clicks_count))
        self.scrolls_lbl.setText(str(stats.scrolls_count))
        self.mouse_lbl.setText(f"{int(stats.mouse_distance_px)} px")
        self.idle_lbl.setText(f"{stats.idle_seconds:.1f} s")
        self.sparkline.push(stats.keys_count + stats.clicks_count + stats.scrolls_count)
