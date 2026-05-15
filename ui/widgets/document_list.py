from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from common.models import DocumentSource, WindowInfo

KIND_ICON = {"file": "📄", "folder": "📁", "url": "🌐", "unknown": "❓"}


class DocumentList(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(8)

        head = QLabel("文档 / 路径")
        head.setObjectName("CardLabel")
        layout.addWidget(head)

        self.list = QListWidget()
        self.list.setObjectName("DocList")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.list, 1)

        self.empty_lbl = QLabel("（暂无）")
        self.empty_lbl.setProperty("dim", True)
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_lbl)

    def update_from(self, info: WindowInfo) -> None:
        self.list.clear()
        docs = info.document_paths
        self.empty_lbl.setVisible(not docs)
        self.list.setVisible(bool(docs))
        for d in docs:
            self._append_row(d)

    def _append_row(self, d: DocumentSource) -> None:
        widget = QWidget()
        v = QVBoxLayout(widget)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(2)

        icon = KIND_ICON.get(d.kind, "•")
        path_lbl = QLabel(f"{icon}  {d.path}")
        path_lbl.setObjectName("Mono")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_lbl.setWordWrap(True)
        v.addWidget(path_lbl)

        meta = QHBoxLayout()
        meta.setSpacing(8)

        kind = QLabel(d.kind)
        kind.setObjectName("Chip")
        kind.setProperty("kind", d.kind)
        src = QLabel(d.source)
        src.setObjectName("Chip")
        src.setProperty("kind", "src")
        conf_level = "high" if d.confidence >= 0.8 else ("mid" if d.confidence >= 0.5 else "low")
        conf = QLabel(f"{int(d.confidence * 100)}%")
        conf.setObjectName("Chip")
        conf.setProperty("kind", conf_level)

        for w in (kind, src, conf):
            meta.addWidget(w)
        meta.addStretch()
        meta_w = QWidget()
        meta_w.setLayout(meta)
        v.addWidget(meta_w)

        item = QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, widget)
