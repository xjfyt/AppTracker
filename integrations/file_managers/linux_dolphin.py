"""Linux Dolphin 集成 — best-effort。

Dolphin 在不同版本下 D-Bus 接口有差异，且 dbus-next 不是默认依赖。
当前实现只做最稳的 fallback：psutil.cwd + 标题解析。
正式 D-Bus 调用留作后续增强（写在 spec §5.5 里）。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import psutil

from core.models import FileManagerState, FileManagerWindow, WindowInfo
from integrations.file_managers.base import FileManagerIntegration

log = logging.getLogger(__name__)


class DolphinIntegration(FileManagerIntegration):
    def matches(self, info: WindowInfo) -> bool:
        exe = (info.process.executable or "").lower() if info.process else ""
        cls = (info.window_class or "").lower()
        return "dolphin" in exe or cls == "dolphin"

    async def query(self, info: WindowInfo) -> Optional[FileManagerState]:
        if not info.process:
            return None
        cwd = None
        try:
            cwd = psutil.Process(info.process.pid).cwd()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        title = info.window_title or ""
        candidate = title.split(" — ")[0].strip().split(" – ")[0].strip()
        if candidate.startswith("~"):
            candidate = os.path.expanduser(candidate)

        folder = None
        if candidate and os.path.isdir(candidate):
            folder = candidate
        elif cwd and os.path.isdir(cwd):
            folder = cwd

        if not folder:
            return None
        return FileManagerState(
            source="title_parse" if folder == candidate else "dolphin_cwd",
            windows=[FileManagerWindow(folder=folder, is_active=True)],
        )
