"""macOS Finder 集成 — AppleScript 拿所有窗口和选中项。

权限：首次调用 osascript 会触发系统 "允许 Active Tracker 控制 Finder" 对话框。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Optional

from common.models import FileManagerState, FileManagerWindow, WindowInfo
from plugins.file_managers.base import FileManagerIntegration

log = logging.getLogger(__name__)

# 输出格式：
#   S|<POSIX path>        ← 选中项（多行）
#   W|<id>|<path>         ← 非焦点窗口
#   W*|<id>|<path>        ← 焦点窗口（选中项归属之）
FINDER_SCRIPT = r'''
tell application "Finder"
    set outText to ""
    try
        repeat with itemRef in (get selection)
            try
                set outText to outText & "S|" & (POSIX path of (itemRef as alias)) & linefeed
            end try
        end repeat
    end try
    try
        set frontWinId to id of front window
    on error
        set frontWinId to -1
    end try
    try
        repeat with w in windows
            try
                set targetPath to POSIX path of (target of w as alias)
                set wid to id of w
                if wid is frontWinId then
                    set outText to outText & "W*|" & wid & "|" & targetPath & linefeed
                else
                    set outText to outText & "W|" & wid & "|" & targetPath & linefeed
                end if
            end try
        end repeat
    end try
    return outText
end tell
'''


def _parse(text: str) -> FileManagerState:
    selected: list[str] = []
    windows_by_id: dict[str, FileManagerWindow] = {}
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line:
            continue
        if line.startswith("S|"):
            p = line[2:].rstrip("/") or "/"
            if p:
                selected.append(p)
        elif line.startswith("W*|") or line.startswith("W|"):
            is_active = line.startswith("W*|")
            try:
                _, wid, path = line.split("|", 2)
            except ValueError:
                continue
            path = path.rstrip("/") or "/"
            w = windows_by_id.get(wid)
            if w is None:
                w = FileManagerWindow(folder=path, hwnd_or_id=wid, is_active=is_active)
                windows_by_id[wid] = w
            else:
                w.folder = path
                w.is_active = is_active or w.is_active

    # 选中项归到 active 窗口（Finder 里 selection 必属前窗口）
    for w in windows_by_id.values():
        if w.is_active:
            w.selected_items = list(selected)
            break

    return FileManagerState(source="finder_applescript", windows=list(windows_by_id.values()))


class FinderIntegration(FileManagerIntegration):
    def __init__(self) -> None:
        self._osascript = shutil.which("osascript")

    def matches(self, info: WindowInfo) -> bool:
        return info.app_bundle_id == "com.apple.finder"

    async def query(self, info: WindowInfo) -> Optional[FileManagerState]:
        if not self._osascript:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                self._osascript, "-e", FINDER_SCRIPT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            log.debug("osascript spawn failed: %s", exc)
            return None
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=1.5)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            log.debug("Finder AppleScript timed out")
            return None
        if proc.returncode != 0:
            err = (stderr_b or b"").decode("utf-8", errors="replace").strip()
            log.debug("Finder AppleScript exit=%s err=%s", proc.returncode, err)
            return None
        return _parse(stdout_b.decode("utf-8", errors="replace"))
