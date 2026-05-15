from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from common.models import FileManagerState, FileManagerWindow


class FileManagerCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("cardKind", "file_manager")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("文件管理器")
        title.setObjectName("CardLabel")
        head.addWidget(title)
        head.addStretch()
        self.source_lbl = QLabel("")
        self.source_lbl.setObjectName("Chip")
        head.addWidget(self.source_lbl)
        layout.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("FmList")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.list, 1)

        self.empty_lbl = QLabel("（未识别到打开的文件管理器）")
        self.empty_lbl.setProperty("dim", True)
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_lbl)

    def clear(self) -> None:
        self.list.clear()
        self.source_lbl.setText("")
        self.empty_lbl.setVisible(True)
        self.list.setVisible(False)

    def update_from(self, state: FileManagerState) -> None:
        self.list.clear()
        self.source_lbl.setText(state.source)
        if not state.windows:
            self.empty_lbl.setVisible(True)
            self.list.setVisible(False)
            return
        self.empty_lbl.setVisible(False)
        self.list.setVisible(True)
        # active window 在前
        ordered = sorted(state.windows, key=lambda w: 0 if w.is_active else 1)
        for w in ordered:
            self._append_window(w)

    def _append_window(self, w: FileManagerWindow) -> None:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(6)
        marker = QLabel("●" if w.is_active else "○")
        marker.setObjectName("FmMarker")
        marker.setProperty("active", w.is_active)
        header.addWidget(marker)
        folder_lbl = QLabel(w.folder or "—")
        folder_lbl.setObjectName("Mono")
        folder_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_lbl.setWordWrap(True)
        header.addWidget(folder_lbl, 1)
        v.addLayout(header)

        if w.selected_items:
            sel_head = QLabel(f"已选 {len(w.selected_items)} 项")
            sel_head.setObjectName("FieldKey")
            v.addWidget(sel_head)
            for path in w.selected_items[:20]:
                item_lbl = QLabel(f"  • {path}")
                item_lbl.setObjectName("Mono")
                item_lbl.setProperty("dim", True)
                item_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                item_lbl.setWordWrap(True)
                v.addWidget(item_lbl)
            if len(w.selected_items) > 20:
                more = QLabel(f"  …还有 {len(w.selected_items) - 20} 项未显示")
                more.setProperty("dim", True)
                v.addWidget(more)

        item = QListWidgetItem()
        item.setSizeHint(container.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, container)
