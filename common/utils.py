"""通用工具：路径白名单、文档去重、URL/标题解析。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote, urlparse


INTERESTING_EXTENSIONS = {
    # 文档
    ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pdf",
    ".xls", ".xlsx", ".ods", ".csv", ".tsv",
    ".ppt", ".pptx", ".odp", ".key",
    # 代码
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp", ".rs", ".go",
    ".rb", ".php", ".sh", ".sql", ".yaml", ".yml", ".toml", ".json", ".xml",
    # 媒体
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".mp3", ".wav", ".flac", ".mp4", ".mov", ".mkv",
    # 设计
    ".psd", ".ai", ".sketch", ".fig", ".xd",
    # 数据
    ".zip", ".tar", ".gz", ".7z", ".epub",
}

BORING_PATH_FRAGMENTS = [
    "/site-packages/", "/dist-packages/", "/.cache/", "/Library/Caches/",
    "AppData\\Local\\", "AppData\\Roaming\\", "/proc/", "/dev/",
    "/System/", "/usr/lib/", "/usr/share/fonts/", "node_modules",
]


def is_interesting_path(path: str) -> bool:
    if not path:
        return False
    if any(frag in path for frag in BORING_PATH_FRAGMENTS):
        return False
    ext = Path(path).suffix.lower()
    if ext in INTERESTING_EXTENSIONS:
        return True
    home = str(Path.home())
    if path.startswith(home) and "/." not in path[len(home):]:
        return True
    return False


def dedupe_documents(docs: Iterable) -> list:
    """同 path 去重，保留 confidence 最高的；按 confidence 倒序输出。"""
    best: dict[str, object] = {}
    for d in docs:
        cur = best.get(d.path)
        if cur is None or d.confidence > cur.confidence:  # type: ignore[attr-defined]
            best[d.path] = d
    return sorted(best.values(), key=lambda x: -x.confidence)  # type: ignore[attr-defined]


def file_url_to_path(url: str) -> Optional[str]:
    """file:// → 本地路径；非 file scheme 返回 None。"""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme == "file":
        return unquote(parsed.path)
    return None


def classify_path(path: str) -> str:
    """根据真实文件系统状态分类成 file/folder/unknown。"""
    if not path:
        return "unknown"
    try:
        p = Path(path)
        if p.is_dir():
            return "folder"
        if p.is_file():
            return "file"
    except OSError:
        pass
    return "unknown"


_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^<>:\"|?*\r\n]+")
_POSIX_PATH_RE = re.compile(r"(?:~|/)[^\s\"'<>]+")


def extract_paths_from_title(title: str) -> list[str]:
    if not title:
        return []
    candidates: list[str] = []
    candidates.extend(_WIN_PATH_RE.findall(title))
    candidates.extend(_POSIX_PATH_RE.findall(title))
    return candidates


def expand_user(path: str) -> str:
    try:
        return os.path.expanduser(path)
    except Exception:
        return path


# 用于把浏览器进程归类，方便 UI 决定是否高亮 BrowserCard。
BROWSER_EXECUTABLE_HINTS = (
    "google chrome",
    "chrome.exe",
    "chrome",
    "microsoft edge",
    "msedge.exe",
    "firefox",
    "firefox.exe",
    "brave",
    "brave.exe",
    "arc",
    "safari",
)


def looks_like_browser(executable: Optional[str], app_name: Optional[str]) -> bool:
    haystacks = [s.lower() for s in (executable, app_name) if s]
    return any(any(h in s for h in BROWSER_EXECUTABLE_HINTS) for s in haystacks)


# --- 终端识别 + 真实 shell pwd 提取 ---------------------------------------

TERMINAL_EXECUTABLE_HINTS = (
    # macOS
    "Terminal", "iTerm", "Alacritty", "WezTerm", "kitty", "Ghostty",
    "Hyper", "Warp", "Tabby",
    # Windows
    "WindowsTerminal", "wt.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "conhost.exe", "ConEmu", "mintty", "putty.exe",
    # Linux
    "gnome-terminal", "konsole", "xterm", "tilix", "terminator",
    "wezterm-gui", "urxvt", "tmux",
)

# 进程名匹配（不含路径），全部小写比较
SHELL_PROCESS_NAMES = {
    "bash", "zsh", "fish", "ksh", "tcsh", "csh", "sh", "dash", "ash",
    "nu", "nush", "xonsh", "elvish",
    "pwsh", "powershell", "powershell.exe", "pwsh.exe",
    "cmd", "cmd.exe",
}


def looks_like_terminal(executable: Optional[str], app_name: Optional[str]) -> bool:
    haystacks = [s for s in (executable, app_name) if s]
    needles = [h.lower() for h in TERMINAL_EXECUTABLE_HINTS]
    for s in haystacks:
        sl = s.lower()
        if any(n in sl for n in needles):
            return True
    return False


def find_shell_cwd(pid: int) -> Optional[str]:
    """递归查找 pid 的 shell 后代进程，返回最新启动的那个的 cwd。

    覆盖大多数 "用户在终端里 cd 切目录" 的场景。多 tab/分屏时返回
    "最近启动的 shell"，对单 tab 场景准确；多 tab 时是近似值。

    任何异常都返回 None — 调用方据此降级使用 process.cwd()。
    """
    import psutil
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    shells = []
    for c in children:
        try:
            name = (c.name() or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name in SHELL_PROCESS_NAMES:
            try:
                shells.append((c.create_time(), c))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    if not shells:
        return None
    shells.sort(key=lambda t: t[0], reverse=True)
    for _, c in shells:
        try:
            cwd = c.cwd()
            if cwd:
                return cwd
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None
