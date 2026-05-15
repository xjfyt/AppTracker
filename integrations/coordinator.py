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
import sys
from typing import Optional

from PySide6.QtCore import QObject

from core.models import WindowInfo
from core.signals import bus
from integrations.file_managers.base import FileManagerIntegration
from integrations.terminals.base import TerminalIntegration

log = logging.getLogger(__name__)


def _build_file_managers() -> list[FileManagerIntegration]:
    plat = sys.platform
    out: list[FileManagerIntegration] = []
    if plat == "darwin":
        from integrations.file_managers.mac_finder import FinderIntegration
        out.append(FinderIntegration())
    elif plat.startswith("win"):
        from integrations.file_managers.win_explorer import ExplorerIntegration
        out.append(ExplorerIntegration())
    elif plat.startswith("linux"):
        from integrations.file_managers.linux_nautilus import NautilusIntegration
        from integrations.file_managers.linux_dolphin import DolphinIntegration
        out.extend([NautilusIntegration(), DolphinIntegration()])
    return out


def _build_terminal() -> TerminalIntegration:
    from integrations.terminals.process_tree import ProcessTreeTerminal
    return ProcessTreeTerminal()


class IntegrationCoordinator(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.file_managers = _build_file_managers()
        self.terminal = _build_terminal()
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
                bus.window_changed.emit(info)
        except asyncio.CancelledError:
            return
