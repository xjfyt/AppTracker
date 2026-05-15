"""Windows Explorer 集成 — Shell COM 枚举所有 Explorer 窗口 + 选中项。

注意：
  * COM 必须 CoInitialize/Uninitialize 配对，且最好在固定线程跑
  * Shell.Application.Windows() 同时返回 IE 实例，要过滤 FullName 含 "explorer.exe"
  * Windows 11 标签页式 Explorer 的非活动 tab COM 看不到（已知限制）
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import unquote, urlparse

from common.models import FileManagerState, FileManagerWindow, WindowInfo
from integrations.file_managers.base import FileManagerIntegration

log = logging.getLogger(__name__)

# COM 串行执行：避免多线程同时 CoInitialize 引发的不确定行为
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="explorer-com")


def _location_to_path(location_url: str) -> str:
    if not location_url:
        return ""
    if not location_url.startswith("file:"):
        return ""
    parsed = urlparse(location_url)
    raw = unquote(parsed.path).lstrip("/")
    if len(raw) >= 2 and raw[1] == ":":
        return raw.replace("/", "\\")
    return raw


def _query_blocking(active_hwnd: Optional[int]) -> Optional[FileManagerState]:
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:
        log.debug("pywin32 not available: %s", exc)
        return None
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        wins: list[FileManagerWindow] = []
        for w in shell.Windows():
            try:
                fullname = (getattr(w, "FullName", "") or "").lower()
                if "explorer.exe" not in fullname:
                    continue
                location_url = getattr(w, "LocationURL", "") or ""
                folder = _location_to_path(location_url)
                if not folder:
                    continue
                try:
                    hwnd = int(w.HWND)
                except Exception:
                    hwnd = 0
                selected: list[str] = []
                try:
                    for item in w.Document.SelectedItems():
                        try:
                            p = item.Path or ""
                        except Exception:
                            continue
                        if p:
                            selected.append(p)
                        if len(selected) >= 50:
                            break
                except Exception:
                    pass
                wins.append(FileManagerWindow(
                    folder=folder,
                    selected_items=selected,
                    hwnd_or_id=str(hwnd) if hwnd else None,
                    is_active=(active_hwnd is not None and hwnd == active_hwnd),
                ))
            except Exception:
                continue
        return FileManagerState(source="explorer_com", windows=wins)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


class ExplorerIntegration(FileManagerIntegration):
    def matches(self, info: WindowInfo) -> bool:
        if (info.window_class or "") == "CabinetWClass":
            return True
        exe = (info.process.executable or "").lower() if info.process else ""
        return exe.endswith("explorer.exe")

    async def query(self, info: WindowInfo) -> Optional[FileManagerState]:
        active_hwnd: Optional[int] = None
        if info.window_id and info.window_id.lstrip("-").isdigit():
            try:
                active_hwnd = int(info.window_id)
            except ValueError:
                active_hwnd = None
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_executor, _query_blocking, active_hwnd),
                timeout=1.5,
            )
        except asyncio.TimeoutError:
            log.debug("Explorer COM query timed out")
            return None
