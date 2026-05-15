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
    find_shell_cwd,
    is_interesting_path,
    looks_like_terminal,
)

log = logging.getLogger(__name__)


class _X11Thread(QThread):
    """读 X 事件的工作线程：订阅 root._NET_ACTIVE_WINDOW + 活动窗口标题/几何。

    用 pending() + 短 sleep 替代阻塞 next_event()，让 stop() 能在 ~50ms 内退出。
    """

    fired = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._stop = False
        self._disp = None

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        import time
        try:
            from Xlib import display, X
            self._disp = display.Display()
            root = self._disp.screen().root
            root.change_attributes(event_mask=X.PropertyChangeMask)

            atom_active = self._disp.intern_atom("_NET_ACTIVE_WINDOW")
            atom_name = self._disp.intern_atom("_NET_WM_NAME")
            atom_wm_name = self._disp.intern_atom("WM_NAME")

            current_active = None

            def _subscribe_active() -> None:
                nonlocal current_active
                try:
                    prop = root.get_full_property(atom_active, X.AnyPropertyType)
                    if not prop or not prop.value:
                        return
                    new_active = int(prop.value[0])
                    if new_active and new_active != current_active:
                        try:
                            win = self._disp.create_resource_object("window", new_active)
                            win.change_attributes(
                                event_mask=X.PropertyChangeMask | X.StructureNotifyMask
                            )
                        except Exception:
                            pass
                        current_active = new_active
                except Exception:
                    pass

            _subscribe_active()

            while not self._stop:
                if self._disp.pending() > 0:
                    ev = self._disp.next_event()
                    if ev.type == X.PropertyNotify:
                        if ev.atom == atom_active:
                            _subscribe_active()
                            self.fired.emit()
                        elif ev.atom in (atom_name, atom_wm_name):
                            self.fired.emit()
                    elif ev.type in (X.ConfigureNotify, X.MapNotify):
                        self.fired.emit()
                else:
                    time.sleep(0.03)
        except Exception as exc:
            log.exception("X11 thread crashed: %s", exc)
        finally:
            try:
                if self._disp is not None:
                    self._disp.close()
            except Exception:
                pass


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

        # 几何 — translate_coords(root, 0, 0) 返回 win 原点在 root 坐标系中的位置
        try:
            geom = win.get_geometry()
            root = win.query_tree().root
            coords = root.translate_coords(win, 0, 0)
            info.geometry = WindowGeometry(
                x=int(coords.x), y=int(coords.y),
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

        # 终端 → 找真实 shell pwd
        exe_hint = info.process.executable if info.process else None
        if pid and looks_like_terminal(exe_hint, info.app_name):
            shell_cwd = find_shell_cwd(pid)
            if shell_cwd:
                info.document_paths.append(
                    DocumentSource(
                        path=shell_cwd, kind="folder",
                        source="shell_pwd", confidence=0.8,
                    )
                )
                info.extra["shell_cwd"] = shell_cwd

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
