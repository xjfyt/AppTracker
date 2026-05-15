"""核心数据模型 — 全部用 dataclass，可序列化为 dict 便于日志/调试。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int
    screen_index: int = 0


@dataclass
class DocumentSource:
    path: str
    kind: str           # "file" | "folder" | "url" | "unknown"
    source: str         # "accessibility" | "title" | "fd_scan" | "cwd" | "browser_ext" | "applescript"
    confidence: float


@dataclass
class ProcessInfo:
    pid: int
    name: str
    executable: Optional[str] = None
    cmdline: list[str] = field(default_factory=list)
    cwd: Optional[str] = None
    username: Optional[str] = None
    create_time: Optional[float] = None
    cpu_percent: Optional[float] = None
    memory_rss: Optional[int] = None


@dataclass
class BrowserTab:
    browser: str           # "chrome" | "edge" | "firefox" | "brave" | "arc"
    pid: Optional[int]
    window_id: Optional[int]
    tab_id: Optional[int]
    url: str
    title: str
    favicon_url: Optional[str] = None
    is_active: bool = True


@dataclass
class FileManagerWindow:
    folder: str
    selected_items: list[str] = field(default_factory=list)
    hwnd_or_id: Optional[str] = None
    is_active: bool = False


@dataclass
class FileManagerState:
    source: str            # finder_applescript | explorer_com | nautilus_* | dolphin_dbus | title_parse
    windows: list[FileManagerWindow] = field(default_factory=list)


@dataclass
class TerminalProcess:
    pid: int
    name: str              # bash / zsh / python / node ...
    cwd: Optional[str] = None
    cmdline: list[str] = field(default_factory=list)   # 已脱敏
    cmdline_redacted: bool = False
    create_time: Optional[float] = None
    is_shell: bool = False
    cwd_source: str = "psutil"   # psutil | shell_file


@dataclass
class TerminalContext:
    source: str            # process_tree | iterm2_api
    shells: list[TerminalProcess] = field(default_factory=list)
    running: list[TerminalProcess] = field(default_factory=list)


@dataclass
class WindowInfo:
    timestamp: float = field(default_factory=time.time)
    platform: str = ""
    app_name: str = ""
    app_bundle_id: Optional[str] = None
    window_title: str = ""
    window_id: Optional[str] = None
    window_class: Optional[str] = None
    geometry: Optional[WindowGeometry] = None
    process: Optional[ProcessInfo] = None
    document_paths: list[DocumentSource] = field(default_factory=list)
    browser_tab: Optional[BrowserTab] = None
    file_manager_state: Optional[FileManagerState] = None
    terminal_context: Optional[TerminalContext] = None
    extra: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def identity_key(self) -> tuple:
        """用于检测 "实质性变化" 的指纹 — 给 2s 兜底定时器做去重。"""
        geom = (
            (self.geometry.x, self.geometry.y, self.geometry.width, self.geometry.height)
            if self.geometry else None
        )
        return (
            self.app_name,
            self.window_id,
            self.window_title,
            geom,
            tuple(d.path for d in self.document_paths),
        )


@dataclass
class ActivityStats:
    timestamp: float = field(default_factory=time.time)
    window_seconds: int = 60
    keys_count: int = 0
    clicks_count: int = 0
    mouse_distance_px: float = 0.0
    scrolls_count: int = 0
    idle_seconds: float = 0.0
