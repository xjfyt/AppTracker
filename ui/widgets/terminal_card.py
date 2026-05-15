from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from common.models import TerminalContext, TerminalProcess
from integrations.terminals.shell_files import shell_integration_dir_path


class TerminalCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("cardKind", "terminal")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("终端")
        title.setObjectName("CardLabel")
        head.addWidget(title)
        head.addStretch()
        self.source_lbl = QLabel("")
        self.source_lbl.setObjectName("Chip")
        head.addWidget(self.source_lbl)
        copy_btn = QPushButton("Shell 脚本目录")
        copy_btn.setObjectName("MiniButton")
        copy_btn.setToolTip("复制 shell 集成脚本所在目录路径，方便在 ~/.bashrc 等里 source")
        copy_btn.clicked.connect(self._copy_shell_dir)
        head.addWidget(copy_btn)
        layout.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("TermList")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.list, 1)

        self.empty_lbl = QLabel("（未识别到打开的终端 / 没有子进程）")
        self.empty_lbl.setProperty("dim", True)
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_lbl)

    def clear(self) -> None:
        self.list.clear()
        self.source_lbl.setText("")
        self.empty_lbl.setVisible(True)
        self.list.setVisible(False)

    def update_from(self, ctx: TerminalContext) -> None:
        self.list.clear()
        self.source_lbl.setText(ctx.source)
        if not ctx.shells and not ctx.running:
            self.empty_lbl.setVisible(True)
            self.list.setVisible(False)
            return
        self.empty_lbl.setVisible(False)
        self.list.setVisible(True)
        if ctx.shells:
            self._add_section("Shells")
            for p in ctx.shells:
                self._add_row(p)
        if ctx.running:
            self._add_section("Running")
            for p in ctx.running:
                self._add_row(p)

    def _add_section(self, title: str) -> None:
        lbl = QLabel(title)
        lbl.setObjectName("FieldKey")
        item = QListWidgetItem()
        item.setSizeHint(lbl.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, lbl)

    def _add_row(self, p: TerminalProcess) -> None:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(8, 4, 8, 4)
        v.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(8)
        glyph = "▸" if p.is_shell else "•"
        name_lbl = QLabel(f"{glyph} {p.name}  ({p.pid})")
        name_lbl.setObjectName("Mono")
        head.addWidget(name_lbl)
        head.addStretch()
        if p.cwd_source == "shell_file":
            src_chip = QLabel("shell-file")
            src_chip.setObjectName("Chip")
            src_chip.setToolTip("cwd 来自 shell 集成脚本 — tmux/screen 下更准确")
            head.addWidget(src_chip)
        if p.cmdline_redacted:
            chip = QLabel("⚠ redacted")
            chip.setObjectName("Chip")
            chip.setProperty("kind", "mid")
            chip.setToolTip("命令行含可能的敏感参数，已脱敏后显示")
            head.addWidget(chip)
        v.addLayout(head)

        if p.cwd:
            cwd_lbl = QLabel(f"  cwd: {p.cwd}")
            cwd_lbl.setObjectName("Mono")
            cwd_lbl.setProperty("dim", True)
            cwd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cwd_lbl.setWordWrap(True)
            v.addWidget(cwd_lbl)
        if p.cmdline:
            cmd_text = " ".join(p.cmdline)
            if len(cmd_text) > 240:
                cmd_text = cmd_text[:237] + "…"
            cmd_lbl = QLabel(f"  $ {cmd_text}")
            cmd_lbl.setObjectName("Mono")
            cmd_lbl.setProperty("dim", True)
            cmd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cmd_lbl.setWordWrap(True)
            v.addWidget(cmd_lbl)

        item = QListWidgetItem()
        item.setSizeHint(container.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, container)

    @staticmethod
    def _copy_shell_dir() -> None:
        path = str(shell_integration_dir_path())
        QGuiApplication.clipboard().setText(path)
