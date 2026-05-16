"""IntegrationCoordinator — 监听 window_changed，异步跑文件管理器/终端集成。

时序：
  Monitor emit window_changed(info_basic)  ──► UI 立即渲染基本信息
                                              │
                                              ├──► coordinator.on_window_changed
                                              │      │
                                              │      ├─ cancel inflight task
                                              │      └─ create new task: _enrich(info)
                                              │
   <enrich done>                              ◄──── coordinator emit window_changed(info_full)
                                              │
                                              └──► UI 再次渲染（含 file_manager_state / terminal_context）

UI 需要做幂等渲染（同一 WindowInfo 被两次 emit 都不出错）。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from PySide6.QtCore import QObject

from common.models import (
    DocumentSource,
    FileManagerState,
    TerminalContext,
    WindowInfo,
)
from common.signals import bus
from plugins import file_managers, terminals
from tools.path_filter import classify_path, dedupe_documents

log = logging.getLogger(__name__)


class IntegrationCoordinator(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.file_managers = file_managers.get_for_platform()
        self.terminal = terminals.get_default()
        self._inflight: Optional[asyncio.Task] = None
        self._paused = False
        bus.window_changed.connect(self.on_window_changed)
        bus.paused_changed.connect(self._on_paused)

    def _on_paused(self, paused: bool) -> None:
        self._paused = paused

    def on_window_changed(self, info: WindowInfo) -> None:
        # 这条 emit 已经被本协调器丰富过了，跳过避免循环
        if info.file_manager_state is not None or info.terminal_context is not None:
            return
        if self._paused:
            return
        # 上一个查询还没完，扔掉
        if self._inflight is not None and not self._inflight.done():
            self._inflight.cancel()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            log.debug("no running event loop; skip enrich")
            return
        self._inflight = loop.create_task(self._enrich(info))

    async def _enrich(self, info: WindowInfo) -> None:
        try:
            # 文件管理器
            for fm in self.file_managers:
                try:
                    if not fm.matches(info):
                        continue
                    state = await fm.query(info)
                    if state is not None and state.windows:
                        info.file_manager_state = state
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.exception("file manager integration failed")
                    bus.error_occurred.emit(
                        fm.__class__.__name__, str(exc),
                    )

            # 终端
            try:
                if self.terminal.matches(info):
                    ctx = await self.terminal.query(info)
                    if ctx is not None:
                        info.terminal_context = ctx
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("terminal integration failed")
                bus.error_occurred.emit("terminal_integration", str(exc))

            if info.file_manager_state is not None or info.terminal_context is not None:
                _merge_into_document_paths(info)
                bus.window_changed.emit(info)
        except asyncio.CancelledError:
            return


def _merge_into_document_paths(info: WindowInfo) -> None:
    """把集成查询到的"文件管理器当前文件夹/选中项"和"终端 shell 的 cwd"
    并入 info.document_paths，左侧"文档 / 路径"卡片才能看到这些路径，
    否则它们只在右侧专属卡片里出现。"""
    extras: list[DocumentSource] = []

    state: Optional[FileManagerState] = info.file_manager_state
    if state is not None:
        for w in state.windows:
            if w.folder:
                extras.append(DocumentSource(
                    path=w.folder,
                    kind="folder",
                    source="file_manager",
                    confidence=0.95 if w.is_active else 0.7,
                ))
            for sel in w.selected_items:
                kind = classify_path(sel)
                if kind == "unknown":
                    # selected_items 来自 shell，路径多半真实存在
                    kind = "folder" if os.path.isdir(sel) else "file"
                extras.append(DocumentSource(
                    path=sel,
                    kind=kind,
                    source="file_manager_selection",
                    confidence=0.95 if w.is_active else 0.7,
                ))

    ctx: Optional[TerminalContext] = info.terminal_context
    if ctx is not None:
        # 同一 cwd 多个 shell（拆分窗格）只显示一条
        seen_cwds: set[str] = set()
        for sh in ctx.shells:
            if not sh.cwd or sh.cwd in seen_cwds:
                continue
            seen_cwds.add(sh.cwd)
            extras.append(DocumentSource(
                path=sh.cwd,
                kind="folder",
                source=f"terminal:{sh.name}",
                confidence=0.9 if sh.cwd_source == "shell_file" else 0.8,
            ))

    if not extras:
        return
    info.document_paths = dedupe_documents(extras + list(info.document_paths))
