from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class ScreenshotView(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(8)

        head = QLabel("窗口截图")
        head.setObjectName("CardLabel")
        layout.addWidget(head)

        self.image_lbl = QLabel("（等待截图）")
        self.image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_lbl.setMinimumHeight(220)
        self.image_lbl.setObjectName("Screenshot")
        layout.addWidget(self.image_lbl, 1)

        self.caption = QLabel("")
        self.caption.setObjectName("Caption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.caption)

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
