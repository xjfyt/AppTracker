"""macOS 焦点监视器。

事件源：
  * NSWorkspaceDidActivateApplicationNotification — 应用切换（瞬时）
  * QTimer 250ms 轮询 — 抓窗口标题/位置变化（AXObserver 太脆弱，留作后续优化）

权限：
  * 辅助功能（Accessibility）— 缺失时退化为仅 NSWorkspace 数据
  * 自动化（Automation）— 仅在跑 AppleScript 时按需触发
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

import objc
import psutil
from PySide6.QtCore import QTimer
from AppKit import NSWorkspace, NSWorkspaceDidActivateApplicationNotification
from Foundation import NSObject
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementCopyAttributeNames,
    AXValueGetValue,
    kAXFocusedWindowAttribute,
    kAXTitleAttribute,
    kAXDocumentAttribute,
    kAXURLAttribute,
    kAXPositionAttribute,
    kAXSizeAttribute,
    kAXRoleAttribute,
    kAXSubroleAttribute,
    kAXErrorSuccess,
    kAXErrorAPIDisabled,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

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
    expand_user,
    extract_paths_from_title,
    file_url_to_path,
    is_interesting_path,
)

log = logging.getLogger(__name__)

# 应用切换后内部窗口/标题变化的快轮询间隔
FAST_POLL_INTERVAL_MS = 250

# bundle_id → AppleScript（拿 URL 或路径用）
APPLESCRIPT_BY_BUNDLE: dict[str, str] = {
    "com.apple.finder": (
        'tell application "Finder" to '
        'try\n'
        '  return POSIX path of (target of front window as alias)\n'
        'on error\n'
        '  return ""\n'
        'end try'
    ),
    "com.google.Chrome": (
        'tell application "Google Chrome"\n'
        '  if (count of windows) = 0 then return ""\n'
        '  return (URL of active tab of front window) & "\t" & (title of active tab of front window)\n'
        'end tell'
    ),
    "com.apple.Safari": (
        'tell application "Safari"\n'
        '  if (count of windows) = 0 then return ""\n'
        '  return (URL of front document) & "\t" & (name of front document)\n'
        'end tell'
    ),
    "company.thebrowser.Browser": (   # Arc
        'tell application "Arc"\n'
        '  if (count of windows) = 0 then return ""\n'
        '  return (URL of active tab of front window) & "\t" & (title of active tab of front window)\n'
        'end tell'
    ),
}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


class _WorkspaceObserver(NSObject):
    """Cocoa 通知必须由 NSObject 子类的方法接收。"""

    def initWithCallback_(self, cb):
        self = objc.super(_WorkspaceObserver, self).init()
        if self is None:
            return None
        self._cb = cb
        return self

    def appActivated_(self, _notification):
        try:
            self._cb()
        except Exception:
            log.exception("workspace callback failed")


class MacOSMonitor(WindowMonitor):
    def __init__(self, bus):
        super().__init__(bus)
        self._observer: Optional[_WorkspaceObserver] = None
        self._osascript = shutil.which("osascript")
        self._ax_ok = self._check_ax_permission()
        if not self._ax_ok:
            self.bus.error_occurred.emit(
                "macos_monitor",
                "Accessibility permission not granted — title/document fields unavailable",
            )

        # 应用切换后用快定时器抓内部变化（AXObserver 留作后续优化）
        self._fast_timer = QTimer(self)
        self._fast_timer.setInterval(FAST_POLL_INTERVAL_MS)
        self._fast_timer.timeout.connect(lambda: self.emit_current("fast"))

    # ------------------------------------------------------------ base impls

    def _start_native(self) -> None:
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        self._observer = _WorkspaceObserver.alloc().initWithCallback_(
            lambda: QTimer.singleShot(0, lambda: self.emit_current("workspace"))
        )
        center.addObserver_selector_name_object_(
            self._observer,
            "appActivated:",
            NSWorkspaceDidActivateApplicationNotification,
            None,
        )
        self._fast_timer.start()

    def _stop_native(self) -> None:
        if self._observer is not None:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(
                self._observer
            )
            self._observer = None
        self._fast_timer.stop()

    def query_now(self) -> WindowInfo:
        info = WindowInfo(platform="darwin")
        ws = NSWorkspace.sharedWorkspace()
        try:
            app = ws.frontmostApplication()
        except Exception as exc:
            info.errors.append(f"frontmostApplication failed: {exc}")
            return info
        if app is None:
            info.errors.append("No frontmost application")
            return info

        info.app_name = _safe(lambda: str(app.localizedName() or "")) or ""
        info.app_bundle_id = _safe(lambda: str(app.bundleIdentifier() or "")) or None

        bundle_url = _safe(app.bundleURL)
        exe_path = _safe(lambda: str(bundle_url.path())) if bundle_url else None
        pid = int(_safe(app.processIdentifier, 0) or 0) or None
        info.window_id = None

        # ProcessInfo
        if pid:
            info.process = self._build_process_info(pid, exe_path or "")

        # AX 部分
        if self._ax_ok and pid:
            self._fill_from_ax(info, pid)

        # AppleScript 兜底（仅当 AX 没拿到 document/URL 时再调用，节省成本）
        if pid and info.app_bundle_id:
            self._maybe_run_applescript(info)

        # 标题解析兜底
        if info.window_title:
            self._collect_from_title(info)

        # 进程打开文件
        if pid:
            self._collect_from_open_files(info, pid)

        # 当前工作目录
        if info.process and info.process.cwd:
            info.document_paths.append(
                DocumentSource(
                    path=info.process.cwd, kind="folder",
                    source="cwd", confidence=0.3,
                )
            )

        info.document_paths = dedupe_documents(info.document_paths)
        return info

    # ------------------------------------------------------------- internals

    @staticmethod
    def _check_ax_permission() -> bool:
        try:
            options = {"AXTrustedCheckOptionPrompt": False}
            return bool(AXIsProcessTrustedWithOptions(options))
        except Exception:
            return False

    def prompt_ax_permission(self) -> bool:
        """UI 可调，弹出系统授权对话框；返回当前授权状态。"""
        try:
            options = {"AXTrustedCheckOptionPrompt": True}
            self._ax_ok = bool(AXIsProcessTrustedWithOptions(options))
        except Exception:
            self._ax_ok = False
        return self._ax_ok

    @staticmethod
    def open_accessibility_settings() -> None:
        url = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        try:
            subprocess.Popen(["open", url])
        except Exception:
            pass

    def _build_process_info(self, pid: int, exe_hint: str) -> ProcessInfo:
        name = ""
        executable = exe_hint or None
        cmdline: list[str] = []
        cwd: Optional[str] = None
        username: Optional[str] = None
        ctime: Optional[float] = None
        cpu: Optional[float] = None
        rss: Optional[int] = None
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                name = _safe(proc.name, "") or ""
                executable = executable or _safe(proc.exe)
                cmdline = _safe(proc.cmdline, []) or []
                cwd = _safe(proc.cwd)
                username = _safe(proc.username)
                ctime = _safe(proc.create_time)
                cpu = _safe(lambda: proc.cpu_percent(interval=None))
                mem = _safe(proc.memory_info)
                rss = int(mem.rss) if mem else None
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            log.debug("psutil pid=%s failed: %s", pid, exc)
        return ProcessInfo(
            pid=pid, name=name, executable=executable, cmdline=cmdline,
            cwd=cwd, username=username, create_time=ctime,
            cpu_percent=cpu, memory_rss=rss,
        )

    def _fill_from_ax(self, info: WindowInfo, pid: int) -> None:
        try:
            ax_app = AXUIElementCreateApplication(pid)
        except Exception as exc:
            info.errors.append(f"AXUIElementCreateApplication: {exc}")
            return

        err, focused = self._ax_copy(ax_app, kAXFocusedWindowAttribute)
        if err == kAXErrorAPIDisabled:
            self._ax_ok = False
            info.errors.append("Accessibility permission revoked")
            return
        if err != kAXErrorSuccess or focused is None:
            return

        # 标题
        err, title = self._ax_copy(focused, kAXTitleAttribute)
        if err == kAXErrorSuccess and title:
            info.window_title = str(title)

        # 子角色作 window_class
        err, subrole = self._ax_copy(focused, kAXSubroleAttribute)
        if err == kAXErrorSuccess and subrole:
            info.window_class = str(subrole)
        err, role = self._ax_copy(focused, kAXRoleAttribute)
        if err == kAXErrorSuccess and role:
            info.extra["ax_role"] = str(role)

        # 几何
        geom = self._ax_geometry(focused)
        if geom:
            info.geometry = geom

        # AXDocument — 通常 "file:///..." 或纯路径
        err, doc = self._ax_copy(focused, kAXDocumentAttribute)
        if err == kAXErrorSuccess and doc:
            doc_str = str(doc)
            path = file_url_to_path(doc_str) or doc_str
            if path:
                info.document_paths.append(
                    DocumentSource(
                        path=path, kind=classify_path(path),
                        source="accessibility", confidence=0.95,
                    )
                )

        # AXURL — Finder/浏览器有时给 URL
        err, url = self._ax_copy(focused, kAXURLAttribute)
        if err == kAXErrorSuccess and url is not None:
            url_str = str(url)
            path = file_url_to_path(url_str)
            if path:
                info.document_paths.append(
                    DocumentSource(
                        path=path, kind=classify_path(path),
                        source="accessibility", confidence=0.95,
                    )
                )
            elif url_str.startswith(("http://", "https://")):
                info.document_paths.append(
                    DocumentSource(
                        path=url_str, kind="url",
                        source="accessibility", confidence=0.9,
                    )
                )

        # 调试：可读属性列表
        try:
            err, names = AXUIElementCopyAttributeNames(focused, None)
            if err == kAXErrorSuccess and names is not None:
                info.extra["ax_attributes"] = [str(n) for n in names]
        except Exception:
            pass

    @staticmethod
    def _ax_copy(element, attr: str):
        try:
            err, value = AXUIElementCopyAttributeValue(element, attr, None)
            return err, value
        except Exception:
            return -1, None

    def _ax_geometry(self, window) -> Optional[WindowGeometry]:
        pos = size = None
        try:
            err, pos_v = AXUIElementCopyAttributeValue(window, kAXPositionAttribute, None)
            if err == kAXErrorSuccess and pos_v is not None:
                ok, point = AXValueGetValue(pos_v, kAXValueCGPointType, None)
                if ok:
                    pos = (int(point.x), int(point.y))
            err, size_v = AXUIElementCopyAttributeValue(window, kAXSizeAttribute, None)
            if err == kAXErrorSuccess and size_v is not None:
                ok, sz = AXValueGetValue(size_v, kAXValueCGSizeType, None)
                if ok:
                    size = (int(sz.width), int(sz.height))
        except Exception as exc:
            log.debug("ax_geometry failed: %s", exc)
            return None
        if pos is None or size is None:
            return None
        x, y = pos
        w, h = size
        return WindowGeometry(
            x=x, y=y, width=w, height=h,
            screen_index=self._screen_index_for(x, y),
        )

    @staticmethod
    def _screen_index_for(x: int, y: int) -> int:
        try:
            from AppKit import NSScreen
            screens = NSScreen.screens()
            for i, scr in enumerate(screens):
                f = scr.frame()
                if (f.origin.x <= x < f.origin.x + f.size.width
                        and f.origin.y <= y < f.origin.y + f.size.height):
                    return i
        except Exception:
            pass
        return 0

    def _maybe_run_applescript(self, info: WindowInfo) -> None:
        if not self._osascript:
            return
        script = APPLESCRIPT_BY_BUNDLE.get(info.app_bundle_id or "")
        if not script:
            return
        try:
            res = subprocess.run(
                [self._osascript, "-e", script],
                capture_output=True, timeout=1.0, text=True,
            )
        except subprocess.TimeoutExpired:
            info.errors.append(f"AppleScript timeout: {info.app_bundle_id}")
            return
        except Exception as exc:
            info.errors.append(f"AppleScript run failed: {exc}")
            return
        if res.returncode != 0:
            err = (res.stderr or "").strip().splitlines()[-1:] or [""]
            info.errors.append(f"AppleScript {info.app_bundle_id}: {err[0]}")
            return
        out = res.stdout.strip()
        if not out:
            return
        # Finder 返回单行路径；浏览器返回 "url\ttitle"
        if "\t" in out:
            url, _title = out.split("\t", 1)
            if url.startswith(("http://", "https://")):
                info.document_paths.append(
                    DocumentSource(
                        path=url, kind="url",
                        source="applescript", confidence=0.85,
                    )
                )
        else:
            path = expand_user(out)
            if os.path.exists(path):
                info.document_paths.append(
                    DocumentSource(
                        path=path, kind=classify_path(path),
                        source="applescript", confidence=0.85,
                    )
                )

    def _collect_from_title(self, info: WindowInfo) -> None:
        for cand in extract_paths_from_title(info.window_title):
            path = expand_user(cand)
            if not is_interesting_path(path):
                continue
            kind = classify_path(path)
            conf = 0.7 if kind in ("file", "folder") else 0.4
            info.document_paths.append(
                DocumentSource(
                    path=path, kind=kind,
                    source="title", confidence=conf,
                )
            )

    def _collect_from_open_files(self, info: WindowInfo, pid: int) -> None:
        try:
            proc = psutil.Process(pid)
            opened = proc.open_files()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        for f in opened:
            path = f.path
            if not is_interesting_path(path):
                continue
            info.document_paths.append(
                DocumentSource(
                    path=path, kind=classify_path(path),
                    source="fd_scan", confidence=0.3,
                )
            )
