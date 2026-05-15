"""终端集成抽象基类 + 终端识别表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.models import TerminalContext, WindowInfo


# bundle_id / exe basename / window_class → 终端类型 key
TERMINAL_EXECUTABLES: dict[str, str] = {
    # macOS bundle ids or app names
    "com.apple.Terminal": "macos_terminal",
    "com.googlecode.iterm2": "iterm2",
    "io.alacritty": "alacritty",
    "net.kovidgoyal.kitty": "kitty",
    "com.github.wez.wezterm": "wezterm",
    "dev.warp.Warp-Stable": "warp",
    "co.zeit.hyper": "hyper",
    "com.mitchellh.ghostty": "ghostty",
    "org.tabby": "tabby",
    "Terminal": "macos_terminal",
    "iTerm": "iterm2",
    "iTerm2": "iterm2",
    "Alacritty": "alacritty",
    "kitty": "kitty",
    "WezTerm": "wezterm",
    "Warp": "warp",
    "Hyper": "hyper",
    "Ghostty": "ghostty",
    "Tabby": "tabby",
    # Windows
    "WindowsTerminal.exe": "windows_terminal",
    "wt.exe": "windows_terminal",
    "conhost.exe": "conhost",
    "cmd.exe": "cmd",
    "powershell.exe": "powershell",
    "pwsh.exe": "pwsh",
    "mintty.exe": "mintty",
    # Linux
    "gnome-terminal-server": "gnome_terminal",
    "konsole": "konsole",
    "xterm": "xterm",
    "alacritty": "alacritty",
    "tilix": "tilix",
    "terminator": "terminator",
    "xfce4-terminal": "xfce4_terminal",
    "wezterm-gui": "wezterm",
    "urxvt": "urxvt",
}


def _basename_cross_platform(path: str) -> str:
    """同时处理 / 和 \\ 分隔（os.path.basename 在 macOS 上不认 Windows 路径）。"""
    base = path
    for sep in ("/", "\\"):
        idx = base.rfind(sep)
        if idx >= 0:
            base = base[idx + 1:]
    return base


def detect_terminal(info: WindowInfo) -> Optional[str]:
    """根据 WindowInfo 判断是不是终端，返回终端 key 或 None。"""
    exe = (info.process.executable or "") if info.process else ""
    name = (info.process.name or "") if info.process else ""
    bundle = info.app_bundle_id or ""
    app_name = info.app_name or ""

    # 1) bundle id 精确匹配
    if bundle and bundle in TERMINAL_EXECUTABLES:
        return TERMINAL_EXECUTABLES[bundle]
    # 2) executable basename (跨平台拆分)
    if exe:
        base = _basename_cross_platform(exe)
        if base in TERMINAL_EXECUTABLES:
            return TERMINAL_EXECUTABLES[base]
        # 也匹配不含扩展名的
        if "." in base:
            no_ext = base.rsplit(".", 1)[0]
            if no_ext in TERMINAL_EXECUTABLES:
                return TERMINAL_EXECUTABLES[no_ext]
    # 3) proc name
    if name and name in TERMINAL_EXECUTABLES:
        return TERMINAL_EXECUTABLES[name]
    # 4) app name (macOS)
    if app_name and app_name in TERMINAL_EXECUTABLES:
        return TERMINAL_EXECUTABLES[app_name]
    return None


class TerminalIntegration(ABC):
    @abstractmethod
    def matches(self, info: WindowInfo) -> bool: ...

    @abstractmethod
    async def query(self, info: WindowInfo) -> Optional[TerminalContext]: ...
