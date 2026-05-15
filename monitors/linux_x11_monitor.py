"""Linux X11 焦点监视器。

事件源：监听根窗口 PropertyChange + 当前活动窗口的属性变化。
Wayland 下只能看到 XWayland 应用。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import psutil
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


class _X11Thread(QThread):
    """阻塞读 X 事件的工作线程。"""

    fired = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._stop = False
        self._disp = None

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            from Xlib import display, X
            self._disp = display.Display()
            root = self._disp.screen().root
            root.change_attributes(event_mask=X.PropertyChangeMask | X.SubstructureNotifyMask)
            while not self._stop:
                ev = self._disp.next_event()
                # 任何属性变化都触发一次重新查询；上层会做指纹去重
                if ev.type in (X.PropertyNotify, X.ConfigureNotify):
                    self.fired.emit()
        except Exception as exc:
            log.exception("X11 thread crashed: %s", exc)


class LinuxX11Monitor(WindowMonitor):
    def __init__(self, bus):
        super().__init__(bus)
        self._ewmh = None
        try:
            from ewmh import EWMH  # type: ignore
            self._ewmh = EWMH()
        except Exception as exc:
            log.warning("EWMH init failed: %s", exc)
            self.bus.error_occurred.emit("linux_monitor", f"EWMH init: {exc}")

        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            self.bus.error_occurred.emit(
                "linux_monitor",
                "Running under Wayland; X11 backend only sees XWayland apps",
            )

        self._thread = _X11Thread()
        self._thread.fired.connect(lambda: self.emit_current("x11"))

    def _start_native(self) -> None:
        self._thread.start()

    def _stop_native(self) -> None:
        self._thread.stop()
        self._thread.wait(2000)

    def query_now(self) -> WindowInfo:
        info = WindowInfo(platform="linux")
        if self._ewmh is None:
            info.errors.append("EWMH not available")
            return info

        try:
            win = self._ewmh.getActiveWindow()
        except Exception as exc:
            info.errors.append(f"getActiveWindow: {exc}")
            return info
        if win is None:
            info.errors.append("No active window")
            return info

        try:
            info.window_id = hex(win.id)
        except Exception:
            pass

        try:
            raw = self._ewmh.getWmName(win)
            if raw is not None:
                info.window_title = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            info.errors.append(f"getWmName: {exc}")

        pid: Optional[int] = None
        try:
            pid_val = self._ewmh.getWmPid(win)
            if pid_val:
                pid = int(pid_val)
        except Exception as exc:
            info.errors.append(f"getWmPid: {exc}")

        # WM_CLASS
        try:
            cls = win.get_wm_class()
            if cls:
                info.window_class = str(cls[0])
                info.extra["wm_class"] = list(cls)
                if not info.app_name:
                    info.app_name = str(cls[1])
        except Exception:
            pass

        # 几何
        try:
            geom = win.get_geometry()
            root = win.query_tree().root
            coords = win.translate_coords(root, 0, 0)
            info.geometry = WindowGeometry(
                x=int(-coords.x), y=int(-coords.y),
                width=int(geom.width), height=int(geom.height),
                screen_index=0,
            )
        except Exception:
            pass

        info.extra["display"] = os.environ.get("DISPLAY", "")
        info.extra["is_xwayland"] = os.environ.get("XDG_SESSION_TYPE") == "wayland"

        if pid:
            info.process = self._build_proc(pid)
            if not info.app_name and info.process.name:
                info.app_name = info.process.name

        # 文档路径
        if pid:
            self._collect_open_files(info, pid)
        if info.window_title:
            self._collect_from_title(info)
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
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    def _build_proc(self, pid: int) -> ProcessInfo:
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
                return ProcessInfo(
                    pid=pid, name=name, executable=exe, cmdline=cmdline,
                    cwd=cwd, username=username, create_time=ctime,
                    cpu_percent=cpu, memory_rss=rss,
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return ProcessInfo(pid=pid, name="")

    def _collect_open_files(self, info: WindowInfo, pid: int) -> None:
        try:
            opened = psutil.Process(pid).open_files()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        home = str(Path.home())
        for f in opened:
            if not is_interesting_path(f.path):
                continue
            conf = 0.5 if f.path.startswith(home) else 0.3
            info.document_paths.append(
                DocumentSource(
                    path=f.path, kind=classify_path(f.path),
                    source="fd_scan", confidence=conf,
                )
            )

    def _collect_from_title(self, info: WindowInfo) -> None:
        for cand in extract_paths_from_title(info.window_title):
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
