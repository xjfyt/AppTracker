"""Linux Nautilus 集成 — best-effort。

Nautilus 的 D-Bus 接口几乎没暴露当前目录/选中项；这里做两件可靠的事：
  1) 用 psutil.Process(pid).cwd() 作为粗略的当前目录
  2) 标题里如果像路径就解析
拿不到选中项是已知限制（spec §5.4 写明）。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import psutil

from common.models import FileManagerState, FileManagerWindow, WindowInfo
from plugins.file_managers.base import FileManagerIntegration

log = logging.getLogger(__name__)


class NautilusIntegration(FileManagerIntegration):
    def matches(self, info: WindowInfo) -> bool:
        exe = (info.process.executable or "") if info.process else ""
        cls = info.window_class or ""
        return "nautilus" in exe.lower() or cls.lower() == "nautilus" or "files" in (info.app_name or "").lower() and "nautilus" in (info.process.name or "").lower() if info.process else False

    async def query(self, info: WindowInfo) -> Optional[FileManagerState]:
        if not info.process:
            return None
        cwd = None
        try:
            cwd = psutil.Process(info.process.pid).cwd()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # 尝试标题
        title = info.window_title or ""
        title_path = title.split(" — ")[0].strip().split(" – ")[0].strip()
        if title_path.startswith("~"):
            title_path = os.path.expanduser(title_path)

        folder = None
        if title_path and os.path.isdir(title_path):
            folder = title_path
        elif cwd and os.path.isdir(cwd):
            folder = cwd

        if not folder:
            return None
        return FileManagerState(
            source="title_parse" if folder == title_path else "nautilus_cwd",
            windows=[FileManagerWindow(folder=folder, is_active=True)],
        )
