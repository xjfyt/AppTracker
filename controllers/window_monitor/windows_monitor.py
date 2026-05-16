"""Windows 焦点监视器。

事件源：SetWinEventHook（OUTOFCONTEXT）+ 自己的 PumpMessages 线程。
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import psutil
import win32api
import win32con
import win32gui
import win32process
from PySide6.QtCore import QThread, QTimer, Signal

from controllers.window_monitor.base import WindowMonitor
from common.models import (
    DocumentSource,
    ProcessInfo,
    WindowGeometry,
    WindowInfo,
)
from tools.path_filter import (
    classify_path,
    dedupe_documents,
    extract_filename_from_title,
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

# Hook 触发后等多久才查询：把瞬时的事件流合成一次 query_now。
# 浏览器切 tab / 缩放窗口会瞬时发几十个 NAMECHANGE，必须合并，否则主线程被打爆。
HOOK_DEBOUNCE_MS = 80

# 这些进程的 open_files() 永远是几百条 cache/cookies/扩展，对文档定位
# 没意义，而且 NtQuerySystemInformation 在巨型进程上 300ms+，直接拉黑。
OPEN_FILES_BLACKLIST = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "vivaldi.exe", "opera.exe", "arc.exe", "iexplore.exe",
    # Electron 大户：VS Code / Discord / Slack 等也常 100+ 句柄
    "code.exe", "discord.exe", "slack.exe", "teams.exe",
    "explorer.exe",   # Explorer 走专用 COM 集成
}

# Office / WPS 走 COM 自动化拿 ActiveDocument.FullName —— 这是最权威的来源，
# open_files() 有时拿不到（Office 用 MMF / 短句柄），UIA 也看不到 Word 的
# 文档属性。WPS 安装后会注册同名 ProgID，所以一套表覆盖两家。
# value = (ProgID, Documents collection 属性名)
OFFICE_COM_PROGIDS: dict[str, tuple[str, str]] = {
    # Microsoft Office
    "winword.exe": ("Word.Application", "Documents"),
    "excel.exe": ("Excel.Application", "Workbooks"),
    "powerpnt.exe": ("PowerPoint.Application", "Presentations"),
    # WPS Office（中文 / 国际版）
    "wps.exe": ("Word.Application", "Documents"),
    "et.exe": ("Excel.Application", "Workbooks"),
    "wpp.exe": ("PowerPoint.Application", "Presentations"),
}


def _office_active_paths(progid: str, collection_attr: str) -> list[str]:
    """Worker 线程里跑：拿 Office/WPS 当前 application 实例所有打开文档的完整路径。

    GetActiveObject 只能在有运行实例时拿到，否则抛 com_error。每次调用都
    独立 CoInitialize / CoUninitialize，避免污染其他线程的 COM 状态。
    返回 ["C:\\path\\to\\doc.docx", ...]；未保存的新建文档（FullName 返回
    "Document1" 之类没有路径分隔符的值）直接丢弃。"""
    try:
        import pythoncom    # type: ignore
        import win32com.client    # type: ignore
    except ImportError:
        return []
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    paths: list[str] = []
    try:
        app = win32com.client.GetActiveObject(progid)
        collection = getattr(app, collection_attr, None)
        if collection is not None:
            # COM collection 没法用 enumerate，靠 Count + Item(idx) 走（idx 从 1 起）
            try:
                count = int(collection.Count)
            except Exception:
                count = 0
            for idx in range(1, count + 1):
                try:
                    doc = collection.Item(idx)
                    full = str(doc.FullName or "")
                except Exception:
                    continue
                # FullName 在未保存时是 "Document1" / "Workbook1" 这种短名；
                # 真实路径要么 "C:\..." 要么 UNC "\\server\share\..."
                if not full:
                    continue
                is_real_path = (
                    (len(full) >= 3 and full[1] == ":" and full[2] in ("\\", "/"))
                    or full.startswith("\\\\")
                )
                if is_real_path:
                    paths.append(full)
    except Exception as exc:
        log.debug("office COM lookup failed for %s: %s", progid, exc)
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass
    return paths


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
        # 不订阅 EVENT_OBJECT_LOCATIONCHANGE：它对每个 accessible 对象的位置变化都触发
        # （包括鼠标光标、菜单、状态栏、滚动条……），全局打开会洪泛主线程；
        # 焦点窗口的位置变化由 base.py 里 2s 的 fallback_timer 兜底足够了。
        WINEVENT_OUTOFCONTEXT = 0x0000
        OBJID_WINDOW = 0   # 仅过滤"窗口本身"，丢弃所有子控件/菜单/光标等噪声

        WinEventProcType = ctypes.WINFUNCTYPE(
            None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
            wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
        )

        def _callback(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
            # 仅关心 top-level 窗口本身的事件；子元素 (status bar、time、tooltip、
            # 浏览器内的 a11y tree 节点) 的 NAMECHANGE 直接丢弃
            if idObject != OBJID_WINDOW or idChild != 0 or not hwnd:
                return
            self.fired.emit()

        self._proc = WinEventProcType(_callback)  # keep ref alive
        user32 = ctypes.windll.user32

        hooks = []
        for ev in (EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_NAMECHANGE):
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
        # 用单触发 QTimer 把瞬时事件流合并：第一次 fired 启动 timer，期间所有 fired
        # 都被吞掉，timer 到点才真正 query 一次。query_now 本身可能阻塞 ~1s（UIA）
        # 所以一定要节流，否则主线程被事件队列淹没。
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(HOOK_DEBOUNCE_MS)
        self._debounce.timeout.connect(lambda: self.emit_current("winevent"))
        self._hook.fired.connect(self._on_hook_fired)
        try:
            import uiautomation as _uia  # type: ignore
            self._uia = _uia
        except Exception as exc:
            self._uia = None
            log.warning("uiautomation unavailable: %s", exc)
        self._uia_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia")
        # UIA 不再同步阻塞主线程：每次 query_now 用上一次 walk 的结果，
        # 同时后台再起一次 walk 刷新缓存。hwnd 切换/重用都自动 invalidate。
        self._uia_cache_hwnd: Optional[int] = None
        self._uia_cache_paths: list[str] = []
        self._uia_inflight = False
        # open_files() 用同样的"缓存 + fire-and-forget"模式：Typora / WPS /
        # Office 这类编辑器把文件 hold 在句柄表里，是定位文档完整路径最直接
        # 的办法（UIA 通常拿不到，title 只有 basename）。
        self._files_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="open-files")
        self._files_cache_hwnd: Optional[int] = None
        self._files_cache_paths: list[str] = []
        self._files_inflight = False
        # Office / WPS COM 查询同一套缓存模型；同一个 pool 串行跑没问题，
        # COM 调用通常 <100ms，open_files 通常 <300ms
        self._office_cache_hwnd: Optional[int] = None
        self._office_cache_paths: list[str] = []
        self._office_inflight = False

    def _on_hook_fired(self) -> None:
        if not self._debounce.isActive():
            self._debounce.start()

    def _start_native(self) -> None:
        self._hook.start()

    def _stop_native(self) -> None:
        try:
            self._hook.post_quit()   # 给 hook 工作线程发 WM_QUIT
        except Exception:
            pass
        self._hook.wait(2000)
        self._debounce.stop()
        self._uia_pool.shutdown(wait=False)
        self._files_pool.shutdown(wait=False)

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
        # Office / WPS 走 COM —— 这俩家用 MMF / 短句柄持有文档，
        # open_files 偶尔抓不到；ActiveDocument.FullName 是最权威的来源
        if pid:
            self._collect_office_com_async(info, hwnd)
        # Typora 等编辑器把当前文档作为句柄 hold 住，open_files() 是
        # 定位完整路径最直接的方式。同 UIA 一样后台跑、缓存复用，绝不
        # 在主线程等。浏览器 / Electron 大户拉黑跳过。
        if pid:
            self._collect_open_files_async(info, hwnd, pid)
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
        """UIA 树遍历完全异步：用上一次 walk 的缓存填充当前结果，
        再后台启一个新的 walk 刷新缓存。绝不让主线程等 UIA。"""
        if self._uia_cache_hwnd == hwnd:
            for path in self._uia_cache_paths:
                info.document_paths.append(
                    DocumentSource(
                        path=path, kind=classify_path(path),
                        source="accessibility", confidence=0.9,
                    )
                )
        else:
            # 焦点切到新窗口，旧缓存对当前窗口无效，清掉
            self._uia_cache_hwnd = hwnd
            self._uia_cache_paths = []

        if self._uia_inflight:
            return
        self._uia_inflight = True
        fut = self._uia_pool.submit(self._uia_walk, hwnd)

        def _store(f, hwnd=hwnd) -> None:
            try:
                paths = f.result()
            except Exception:
                paths = []
            # 回调在 worker 线程；GIL 让单次赋值原子，无需锁
            if self._uia_cache_hwnd == hwnd:
                self._uia_cache_paths = paths
            self._uia_inflight = False

        fut.add_done_callback(_store)

    def _collect_open_files_async(self, info: WindowInfo, hwnd: int, pid: int) -> None:
        """psutil.Process.open_files() 在 Windows 上靠 NtQuerySystemInformation
        遍历全系统句柄表，慢。所以：浏览器/Electron 大户直接跳过；其他进程
        用单线程池跑、缓存、fire-and-forget，绝不阻塞主线程。

        若 window_title 里能抽出 basename（"doc.md - Typora"），
        优先匹配同名句柄给 0.85 高置信度；其他句柄按 fd_scan 0.3 低置信度。"""
        title_basename = extract_filename_from_title(info.window_title or "")

        if self._files_cache_hwnd == hwnd:
            for path in self._files_cache_paths:
                conf = 0.3
                if title_basename and os.path.basename(path).lower() == title_basename.lower():
                    conf = 0.85
                info.document_paths.append(
                    DocumentSource(
                        path=path, kind=classify_path(path),
                        source="fd_scan", confidence=conf,
                    )
                )
        else:
            self._files_cache_hwnd = hwnd
            self._files_cache_paths = []

        # 黑名单进程跳过（仍然每次都查 process name —— 便宜）
        proc_name_lc = (info.process.name or "").lower() if info.process else ""
        if proc_name_lc in OPEN_FILES_BLACKLIST:
            return

        if self._files_inflight:
            return
        self._files_inflight = True
        fut = self._files_pool.submit(self._open_files_walk, pid)

        def _store(f, hwnd=hwnd) -> None:
            try:
                paths = f.result()
            except Exception:
                paths = []
            if self._files_cache_hwnd == hwnd:
                self._files_cache_paths = paths
            self._files_inflight = False

        fut.add_done_callback(_store)

    def _collect_office_com_async(self, info: WindowInfo, hwnd: int) -> None:
        """Office / WPS：用 COM GetActiveObject 拿 ActiveDocument.FullName。
        同 open_files / UIA 一样异步缓存，主线程 0 阻塞。"""
        proc_name_lc = (info.process.name or "").lower() if info.process else ""
        if proc_name_lc not in OFFICE_COM_PROGIDS:
            return

        if self._office_cache_hwnd == hwnd:
            for path in self._office_cache_paths:
                info.document_paths.append(
                    DocumentSource(
                        path=path, kind=classify_path(path),
                        source="office_com", confidence=0.95,
                    )
                )
        else:
            self._office_cache_hwnd = hwnd
            self._office_cache_paths = []

        if self._office_inflight:
            return
        self._office_inflight = True
        progid, attr = OFFICE_COM_PROGIDS[proc_name_lc]
        fut = self._files_pool.submit(_office_active_paths, progid, attr)

        def _store(f, hwnd=hwnd) -> None:
            try:
                paths = f.result()
            except Exception:
                paths = []
            if self._office_cache_hwnd == hwnd:
                self._office_cache_paths = paths
            self._office_inflight = False

        fut.add_done_callback(_store)

    @staticmethod
    def _open_files_walk(pid: int) -> list[str]:
        """worker 线程里跑的实际查询；保留过滤后"有意思"的路径。"""
        try:
            opened = psutil.Process(pid).open_files()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for f in opened:
            path = f.path
            if not path or path in seen:
                continue
            if not is_interesting_path(path):
                continue
            seen.add(path)
            results.append(path)
            if len(results) >= 20:
                break
        return results

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

