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

周期刷新：terminal 用户 cd / Explorer 用户改选中项 → 这些都不会触发窗口
focus / title / 几何变化，monitor 的 identity 去重会吞掉。所以协调器
自己再起一个 1.5s 的 QTimer，在当前焦点窗口是 terminal/文件管理器时
周期重跑集成查询；只有真正变化才再 emit 一次 window_changed。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from PySide6.QtCore import QObject, QTimer

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

REFRESH_INTERVAL_MS = 1500


class IntegrationCoordinator(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.file_managers = file_managers.get_for_platform()
        self.terminal = terminals.get_default()
        self._inflight: Optional[asyncio.Task] = None
        self._paused = False
        # 周期刷新当前焦点窗口的 file_manager_state / terminal_context
        self._current_info: Optional[WindowInfo] = None
        self._last_state_key: tuple = ()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._refresh_timer.start()
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
        # 新窗口：记下来给周期 tick 用，state 指纹归零
        self._current_info = info
        self._last_state_key = ()
        # 上一个查询还没完，扔掉
        if self._inflight is not None and not self._inflight.done():
            self._inflight.cancel()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            log.debug("no running event loop; skip enrich")
            return
        self._inflight = loop.create_task(self._enrich(info, force_emit=True))

    def _on_refresh_tick(self) -> None:
        if self._paused or self._current_info is None:
            return
        if self._inflight is not None and not self._inflight.done():
            return   # 上次还没跑完，下次再说
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        self._inflight = loop.create_task(self._enrich(self._current_info, force_emit=False))

    async def _enrich(self, info: WindowInfo, force_emit: bool) -> None:
        """跑一次集成查询；force_emit=True 来自新窗口（首次必发），
        False 来自周期 tick（仅在状态变化时才 emit）。"""
        try:
            new_fm_state: Optional[FileManagerState] = None
            new_term_ctx: Optional[TerminalContext] = None

            for fm in self.file_managers:
                try:
                    if not fm.matches(info):
                        continue
                    state = await fm.query(info)
                    if state is not None and state.windows:
                        new_fm_state = state
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.exception("file manager integration failed")
                    bus.error_occurred.emit(fm.__class__.__name__, str(exc))

            try:
                if self.terminal.matches(info):
                    ctx = await self.terminal.query(info)
                    if ctx is not None:
                        new_term_ctx = ctx
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("terminal integration failed")
                bus.error_occurred.emit("terminal_integration", str(exc))

            if new_fm_state is None and new_term_ctx is None:
                return

            new_key = _state_key(new_fm_state, new_term_ctx)
            if not force_emit and new_key == self._last_state_key:
                return   # 周期 tick 但状态没变，不打扰 UI
            self._last_state_key = new_key

            # 周期刷新场景下，info 是上一次首次 enrich 用过的对象，
            # document_paths 里已经堆了上次的 file_manager_* / terminal:*
            # 条目；直接覆盖 file_manager_state / terminal_context，
            # _merge_into_document_paths 会先剥掉旧条目再加新的，不会累加。
            info.file_manager_state = new_fm_state
            info.terminal_context = new_term_ctx
            _merge_into_document_paths(info)
            bus.window_changed.emit(info)
        except asyncio.CancelledError:
            return


def _state_key(
    fm: Optional[FileManagerState], term: Optional[TerminalContext]
) -> tuple:
    """把当前集成查询结果折成一个可比较的指纹；变化判断用。"""
    fm_part: tuple = ()
    if fm is not None:
        fm_part = tuple(
            (w.folder, w.is_active, tuple(w.selected_items))
            for w in fm.windows
        )
    term_part: tuple = ()
    if term is not None:
        # 只比较 shells（用户 cd 体现在这里），cmdline 变化不打扰 UI
        term_part = tuple(
            (sh.pid, sh.cwd) for sh in term.shells
        )
    return (fm_part, term_part)


def _merge_into_document_paths(info: WindowInfo) -> None:
    """把集成查询到的"文件管理器当前文件夹/选中项"和"终端 shell 的 cwd"
    并入 info.document_paths，左侧"文档 / 路径"卡片才能看到这些路径，
    否则它们只在右侧专属卡片里出现。

    周期刷新会调多次：先把上次自己加的条目（按 source 标签）剥掉，
    再合并这次的，避免累加旧 cwd / 旧选中项。"""
    base_paths = [
        d for d in info.document_paths
        if not (
            d.source == "file_manager"
            or d.source == "file_manager_selection"
            or d.source.startswith("terminal:")
        )
    ]

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
                    kind = "folder" if os.path.isdir(sel) else "file"
                extras.append(DocumentSource(
                    path=sel,
                    kind=kind,
                    source="file_manager_selection",
                    confidence=0.95 if w.is_active else 0.7,
                ))

    ctx: Optional[TerminalContext] = info.terminal_context
    if ctx is not None:
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

    info.document_paths = dedupe_documents(extras + base_paths)
