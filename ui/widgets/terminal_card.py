from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from common.models import TerminalContext, TerminalProcess
from plugins.terminals.shell_files import shell_integration_dir_path
from tools.shell_installer import install_powershell_integration


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
        if sys.platform == "win32":
            self.install_btn = QPushButton("一键装到 $PROFILE")
            self.install_btn.setObjectName("MiniButton")
            self.install_btn.setToolTip(
                "PowerShell 的 cd 不更新进程 PEB，psutil 拿不到。\n"
                "点击会向你的 $PROFILE 追加一行 source；幂等，重复点也不会重复写入。"
            )
            self.install_btn.clicked.connect(self._install_ps_integration)
            head.addWidget(self.install_btn)
        self.copy_btn = QPushButton("Shell 脚本目录")
        self.copy_btn.setObjectName("MiniButton")
        self.copy_btn.setToolTip("复制 shell 集成脚本所在目录路径，方便在 ~/.bashrc 等里 source")
        self.copy_btn.clicked.connect(self._copy_shell_dir)
        head.addWidget(self.copy_btn)
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
        if p.last_command:
            last_text = p.last_command
            if len(last_text) > 240:
                last_text = last_text[:237] + "…"
            last_lbl = QLabel(f"  ⏵ {last_text}")
            last_lbl.setObjectName("Mono")
            last_lbl.setProperty("dim", True)
            last_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            last_lbl.setWordWrap(True)
            last_lbl.setToolTip("最近一次执行的命令（来自 shell 集成脚本，已脱敏）")
            v.addWidget(last_lbl)
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

    def _copy_shell_dir(self) -> None:
        path = str(shell_integration_dir_path())
        QGuiApplication.clipboard().setText(path)
        self.copy_btn.setText("✓ 已复制")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("Shell 脚本目录"))

    def _install_ps_integration(self) -> None:
        result = install_powershell_integration()
        if result.ok:
            QMessageBox.information(self, "安装成功", result.message)
        else:
            QMessageBox.warning(self, "安装失败", result.message)
