"""Windows 焦点监视器。

事件源：SetWinEventHook（OUTOFCONTEXT）+ 自己的 PumpMessages 线程。
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

import psutil
import win32api
import win32con
import win32gui
import win32process
from PySide6.QtCore import QThread, Signal

from monitors.base import WindowMonitor
from core.models import (
    DocumentSource,
    ProcessInfo,
    WindowGeometry,
    WindowInfo,
)
from core.utils import (
    classify_path,
    dedupe_documents,
    extract_paths_from_title,
    is_interesting_path,
)

log = logging.getLogger(__name__)

TITLE_SUFFIXES = [
    " - Microsoft Word", " - Word", " - Excel", " - PowerPoint",
    " - Notepad", " - 记事本",
    " - Visual Studio Code", " - Visual Studio",
    " - Notepad++", " - Sublime Text", " - File Explorer",
    " - Google Chrome", " - Microsoft Edge", " — Mozilla Firefox",
]

UIA_TIMEOUT_SEC = 2.0


def _file_description(exe: str) -> Optional[str]:
    if not exe:
        return None
    try:
        info = win32api.GetFileVersionInfo(exe, "\\VarFileInfo\\Translation")
        if not info:
            return None
        lang, codepage = info[0]
        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        return win32api.GetFileVersionInfo(exe, key)
    except Exception:
        return None


class _HookThread(QThread):
    """跑 PumpMessages 的工作线程，捕获前台切换 / 标题变化事件。"""

    fired = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._win_tid: int = 0   # 工作线程的 Win32 thread ID，stop 时用来 PostThreadMessage

    def run(self) -> None:
        import ctypes
        from ctypes import wintypes

        # 关键：这里拿到的是这个 QThread 真正运行的 Win32 线程 ID
        self._win_tid = int(ctypes.windll.kernel32.GetCurrentThreadId())

        EVENT_SYSTEM_FOREGROUND = 0x0003
        EVENT_OBJECT_NAMECHANGE = 0x800C
        EVENT_OBJECT_LOCATIONCHANGE = 0x800B
        WINEVENT_OUTOFCONTEXT = 0x0000

        WinEventProcType = ctypes.WINFUNCTYPE(
            None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
            wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
        )

        def _callback(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
            self.fired.emit()

        self._proc = WinEventProcType(_callback)  # keep ref alive
        user32 = ctypes.windll.user32

        hooks = []
        for ev in (EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_NAMECHANGE, EVENT_OBJECT_LOCATIONCHANGE):
            h = user32.SetWinEventHook(ev, ev, 0, self._proc, 0, 0, WINEVENT_OUTOFCONTEXT)
            if h:
                hooks.append(h)

        try:
            win32gui.PumpMessages()
        finally:
            for h in hooks:
                user32.UnhookWinEvent(h)

    def post_quit(self) -> None:
        """从其他线程调用，让 PumpMessages 退出。"""
        if not self._win_tid:
            return
        import ctypes
        WM_QUIT = 0x0012
        ctypes.windll.user32.PostThreadMessageW(self._win_tid, WM_QUIT, 0, 0)


class WindowsMonitor(WindowMonitor):
    def __init__(self, bus):
        super().__init__(bus)
        self._hook = _HookThread()
        self._hook.fired.connect(lambda: self.emit_current("winevent"))
        try:
            import uiautomation as _uia  # type: ignore
            self._uia = _uia
        except Exception as exc:
            self._uia = None
            log.warning("uiautomation unavailable: %s", exc)
        self._uia_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia")

    def _start_native(self) -> None:
        self._hook.start()

    def _stop_native(self) -> None:
        try:
            self._hook.post_quit()   # 给 hook 工作线程发 WM_QUIT
        except Exception:
            pass
        self._hook.wait(2000)
        self._uia_pool.shutdown(wait=False)

    def query_now(self) -> WindowInfo:
        info = WindowInfo(platform="win32")
        try:
            hwnd = win32gui.GetForegroundWindow()
        except Exception as exc:
            info.errors.append(f"GetForegroundWindow: {exc}")
            return info
        if not hwnd:
            info.errors.append("No foreground window")
            return info

        info.window_id = str(hwnd)
        info.extra["hwnd_hex"] = hex(hwnd)
        info.window_title = self._safe(lambda: win32gui.GetWindowText(hwnd) or "")
        info.window_class = self._safe(lambda: win32gui.GetClassName(hwnd))

        try:
            tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            info.extra["thread_id"] = int(tid)
        except Exception as exc:
            info.errors.append(f"GetWindowThreadProcessId: {exc}")
            pid = 0

        # 几何
        try:
            rect = win32gui.GetWindowRect(hwnd)   # (l, t, r, b)
            l, t, r, b = rect
            info.geometry = WindowGeometry(
                x=l, y=t, width=r - l, height=b - t,
                screen_index=self._screen_index(hwnd),
            )
        except Exception:
            pass

        # styles
        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            info.extra["window_styles"] = hex(style)
            info.extra["is_minimized"] = bool(style & win32con.WS_MINIMIZE)
            info.extra["is_maximized"] = bool(style & win32con.WS_MAXIMIZE)
        except Exception:
            pass

        # ProcessInfo
        if pid:
            info.process = self._build_proc(pid)

        # app_name
        if info.process:
            desc = _file_description(info.process.executable or "")
            info.app_name = desc or info.process.name or ""

        # AppUserModelID
        info.app_bundle_id = self._app_user_model_id(hwnd)

        # Explorer 当前文件夹 + 选中项已迁到 integrations.file_managers.win_explorer
        # 终端 shell pwd 已迁到 integrations.terminals.process_tree

        # 文档路径（编辑器/通用应用兜底）
        if self._uia and pid:
            self._collect_via_uia(info, hwnd)
        if info.window_title:
            self._collect_from_title(info)
        if pid:
            self._collect_open_files(info, pid)
        if info.process and info.process.cwd:
            info.document_paths.append(
                DocumentSource(
                    path=info.process.cwd, kind="folder",
                    source="cwd", confidence=0.3,
                )
            )

        info.document_paths = dedupe_documents(info.document_paths)
        return info

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _safe(fn, default=""):
        try:
            return fn()
        except Exception:
            return default

    @staticmethod
    def _screen_index(hwnd: int) -> int:
        try:
            mon = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            for i, (h, _hdc, _rect) in enumerate(win32api.EnumDisplayMonitors()):
                if int(h) == int(mon):
                    return i
        except Exception:
            pass
        return 0

    @staticmethod
    def _app_user_model_id(hwnd: int) -> Optional[str]:
        try:
            from win32com.propsys import propsys, pscon  # type: ignore
            store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
            val = store.GetValue(pscon.PKEY_AppUserModel_ID)
            return str(val.GetValue()) if val else None
        except Exception:
            return None

    def _build_proc(self, pid: int) -> ProcessInfo:
        name = ""
        exe = None
        cmdline: list[str] = []
        cwd = None
        username = None
        ctime = None
        cpu = None
        rss = None
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                name = self._safe(proc.name, "") or ""
                exe = self._safe(proc.exe)
                cmdline = self._safe(proc.cmdline, []) or []
                cwd = self._safe(proc.cwd)
                username = self._safe(proc.username)
                ctime = self._safe(proc.create_time)
                cpu = self._safe(lambda: proc.cpu_percent(interval=None))
                mem = self._safe(proc.memory_info)
                rss = int(mem.rss) if mem else None
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return ProcessInfo(
            pid=pid, name=name, executable=exe, cmdline=cmdline,
            cwd=cwd, username=username, create_time=ctime,
            cpu_percent=cpu, memory_rss=rss,
        )

    def _collect_via_uia(self, info: WindowInfo, hwnd: int) -> None:
        """UIA 树遍历放到线程池里跑，硬性 2s 超时。"""
        fut = self._uia_pool.submit(self._uia_walk, hwnd)
        try:
            paths = fut.result(timeout=UIA_TIMEOUT_SEC)
        except FuturesTimeout:
            info.errors.append("UIA walk timeout")
            fut.cancel()
            return
        except Exception as exc:
            info.errors.append(f"UIA walk: {exc}")
            return
        for path in paths:
            info.document_paths.append(
                DocumentSource(
                    path=path, kind=classify_path(path),
                    source="accessibility", confidence=0.9,
                )
            )

    def _uia_walk(self, hwnd: int) -> list[str]:
        auto = self._uia
        if auto is None:
            return []
        results: list[str] = []
        try:
            win = auto.ControlFromHandle(hwnd)
        except Exception:
            return results
        if win is None:
            return results

        # 优先找 DocumentControl
        def _walk(ctrl, depth: int):
            if depth > 3 or len(results) > 5:
                return
            try:
                if ctrl.ControlTypeName == "DocumentControl" and ctrl.IsValuePatternAvailable():
                    val = ctrl.GetValuePattern().Value or ""
                    if val and (":\\" in val or val.startswith("\\\\")) and os.path.exists(val):
                        results.append(val)
                children = ctrl.GetChildren()
            except Exception:
                return
            for child in children[:20]:
                _walk(child, depth + 1)

        _walk(win, 0)
        return results

    def _collect_from_title(self, info: WindowInfo) -> None:
        title = info.window_title or ""
        for suf in TITLE_SUFFIXES:
            if title.endswith(suf):
                title = title[: -len(suf)]
                break
        for cand in extract_paths_from_title(title):
            if not is_interesting_path(cand):
                continue
            exists = os.path.exists(cand)
            info.document_paths.append(
                DocumentSource(
                    path=cand,
                    kind=classify_path(cand) if exists else "unknown",
                    source="title",
                    confidence=0.7 if exists else 0.4,
                )
            )

    def _collect_open_files(self, info: WindowInfo, pid: int) -> None:
        try:
            opened = psutil.Process(pid).open_files()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        for f in opened:
            if not is_interesting_path(f.path):
                continue
            info.document_paths.append(
                DocumentSource(
                    path=f.path, kind=classify_path(f.path),
                    source="fd_scan", confidence=0.3,
                )
            )
