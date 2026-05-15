# 文件管理器 & 终端集成模块 — 实施规格

> **本文档与 `active_tracker_spec_v2.md` 配套使用**。它在 v2 的 Phase 10 完成后追加 Phase 11、12 两个模块，复用 v2 的 `SignalBus`、`WindowInfo`、PySide6 UI 架构。读本文前请先看完 v2 §6（数据模型）和 §7（信号总线）。

---

## 1. 模块目标

在已有的"前台窗口实时检测"之上，**深度采集用户在文件管理器和终端里的具体操作上下文**：

| 应用类型 | 想拿到的信息 |
|---------|------------|
| 文件管理器（Finder / Explorer / Nautilus / Dolphin） | 当前打开的所有窗口的目录、每个窗口的选中项 |
| 终端（Terminal / iTerm2 / Windows Terminal / GNOME Terminal 等） | 每个 shell 的当前工作目录、正在运行的子进程及其命令行（脱敏） |

**核心原则**：
1. **零配置可用** —— Tier 1 方案不要求用户改任何配置
2. **不录命令历史** —— 只看"此刻在哪、此刻在跑什么"，不持久化命令记录
3. **机密脱敏** —— 命令行里的 token / 密码必须 redact 后才显示

## 2. 项目结构追加

在 v2 的 `src/active_tracker/` 下新增：

```
src/active_tracker/
├── integrations/
│   ├── __init__.py
│   ├── base.py                       # Integration 抽象基类
│   ├── coordinator.py                # 调度：根据焦点应用选择对应集成
│   ├── redaction.py                  # 命令行/路径脱敏
│   ├── file_managers/
│   │   ├── __init__.py
│   │   ├── base.py                   # FileManagerIntegration
│   │   ├── mac_finder.py             # AppleScript
│   │   ├── win_explorer.py           # COM
│   │   ├── linux_nautilus.py         # D-Bus / 标题
│   │   └── linux_dolphin.py          # D-Bus
│   └── terminals/
│       ├── __init__.py
│       ├── base.py                   # TerminalIntegration
│       ├── process_tree.py           # 通用：进程子树
│       ├── shell_files.py            # 读 ~/.active_tracker/shells/*.cwd
│       └── iterm2_api.py             # 可选：iTerm2 官方 API
└── ui/widgets/
    ├── file_manager_card.py          # 新卡片
    └── terminal_card.py              # 新卡片
```

仓库根追加：

```
shell_integration/                    # 用户一次性配置的脚本
├── README.md
├── bash.sh
├── zsh.sh
├── fish.fish
└── powershell.ps1
```

## 3. 数据模型扩展

在 `src/active_tracker/core/models.py` 中追加：

```python
@dataclass
class FileManagerWindow:
    folder: str                         # 当前显示的目录绝对路径
    selected_items: list[str] = field(default_factory=list)
    hwnd_or_id: Optional[str] = None    # 用于和 WindowInfo.window_id 关联
    is_active: bool = False             # 是否是当前焦点窗口

@dataclass
class FileManagerState:
    source: str                         # "finder_applescript" | "explorer_com" | "nautilus_dbus" | "dolphin_dbus" | "title_parse"
    windows: list[FileManagerWindow] = field(default_factory=list)

@dataclass
class TerminalProcess:
    pid: int
    name: str                           # bash / zsh / python / node …
    cwd: Optional[str] = None
    cmdline: list[str] = field(default_factory=list)   # 已脱敏
    cmdline_redacted: bool = False                     # 是否经过脱敏
    create_time: Optional[float] = None
    is_shell: bool = False

@dataclass
class TerminalContext:
    source: str                         # "process_tree" | "iterm2_api" | "shell_files"
    shells: list[TerminalProcess] = field(default_factory=list)
    running: list[TerminalProcess] = field(default_factory=list)  # 非 shell 子进程
```

在 `WindowInfo` 中追加两个可选字段：

```python
@dataclass
class WindowInfo:
    # ... 已有字段
    file_manager_state: Optional[FileManagerState] = None
    terminal_context: Optional[TerminalContext] = None
```

## 4. 信号扩展

`SignalBus` 不新增信号——集成结果直接挂在 `WindowInfo` 上，复用现有的 `window_changed` 信号。

**关键时序**：

```
[窗口监视器] emit window_changed(WindowInfo)   ──┐
                                                  │
                                                  ├──► UI 立即更新基本信息（不阻塞）
                                                  │
[IntegrationCoordinator] 异步调用对应集成 ──────┤
                                                  │
[集成返回结果后] 再次 emit window_changed   ──┘   ──► UI 更新文件管理器/终端卡片
```

也就是说，**一个焦点事件可能触发两次 `window_changed`**：第一次是基础信息，第二次是含集成结果的富信息。UI 端要做幂等渲染。

## 5. Phase 11 — 文件管理器集成

### 5.1 抽象基类 `integrations/file_managers/base.py`

```python
from abc import ABC, abstractmethod
from ...core.models import FileManagerState, WindowInfo

class FileManagerIntegration(ABC):
    @abstractmethod
    def matches(self, info: WindowInfo) -> bool:
        """根据 WindowInfo.process.executable 或 bundle_id 判断是否归本集成处理。"""
        ...

    @abstractmethod
    async def query(self, info: WindowInfo) -> FileManagerState | None:
        """查询当前文件管理器状态。必须带超时（建议 1 秒），失败返回 None。"""
        ...
```

### 5.2 macOS Finder：`mac_finder.py`

```python
import asyncio
import subprocess
from ...core.models import FileManagerState, FileManagerWindow
from .base import FileManagerIntegration

FINDER_SCRIPT = '''
tell application "Finder"
    set out to ""
    try
        repeat with itemRef in selection
            try
                set out to out & "S|" & (POSIX path of (itemRef as alias)) & linefeed
            end try
        end repeat
    end try
    try
        set frontWinId to id of front window
    on error
        set frontWinId to -1
    end try
    repeat with w in windows
        try
            set targetPath to POSIX path of (target of w as alias)
            set wid to id of w
            if wid is frontWinId then
                set out to out & "W*|" & wid & "|" & targetPath & linefeed
            else
                set out to out & "W|" & wid & "|" & targetPath & linefeed
            end if
        end try
    end repeat
    return out
end tell
'''

class FinderIntegration(FileManagerIntegration):
    def matches(self, info):
        return info.app_bundle_id == "com.apple.finder"

    async def query(self, info):
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", FINDER_SCRIPT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1.0)
            return self._parse(stdout.decode("utf-8", errors="replace"))
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    def _parse(self, text: str) -> FileManagerState:
        selected = []
        windows_by_id: dict[str, FileManagerWindow] = {}
        for line in text.splitlines():
            if line.startswith("S|"):
                selected.append(line[2:])
            elif line.startswith("W*|") or line.startswith("W|"):
                is_active = line.startswith("W*|")
                _, wid, path = line.split("|", 2)
                w = windows_by_id.setdefault(wid, FileManagerWindow(folder=path, hwnd_or_id=wid))
                w.folder = path
                w.is_active = is_active
        # 把 selected 全部归到 active window（Finder 选中项天然属于前窗口）
        for w in windows_by_id.values():
            if w.is_active:
                w.selected_items = selected
                break
        return FileManagerState(source="finder_applescript", windows=list(windows_by_id.values()))
```

**权限提示**：首次调用会触发系统弹"允许 Active Tracker 控制 Finder"对话框（自动化权限，与辅助功能权限是两个不同的开关）。在 UI 顶部错误栏给出明确指引。

### 5.3 Windows Explorer：`win_explorer.py`

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, unquote
from ...core.models import FileManagerState, FileManagerWindow
from .base import FileManagerIntegration

_executor = ThreadPoolExecutor(max_workers=1)  # COM 必须串行

def _query_blocking(active_hwnd: int | None) -> FileManagerState | None:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        wins = []
        for w in shell.Windows():
            try:
                # 过滤：只要资源管理器，不要 IE
                fullname = (w.FullName or "").lower()
                if "explorer.exe" not in fullname:
                    continue
                location_url = w.LocationURL or ""
                if not location_url.startswith("file:"):
                    continue
                parsed = urlparse(location_url)
                folder = unquote(parsed.path).lstrip("/")
                # Windows 路径修正
                if len(folder) >= 2 and folder[1] == ":":
                    folder = folder.replace("/", "\\")
                hwnd = int(w.HWND)
                selected = []
                try:
                    for item in w.Document.SelectedItems():
                        selected.append(item.Path)
                except Exception:
                    pass
                wins.append(FileManagerWindow(
                    folder=folder,
                    selected_items=selected,
                    hwnd_or_id=str(hwnd),
                    is_active=(hwnd == active_hwnd),
                ))
            except Exception:
                continue
        return FileManagerState(source="explorer_com", windows=wins)
    finally:
        pythoncom.CoUninitialize()

class ExplorerIntegration(FileManagerIntegration):
    EXES = {"explorer.exe"}

    def matches(self, info):
        exe = (info.process.executable or "").lower() if info.process else ""
        return any(exe.endswith(e) for e in self.EXES)

    async def query(self, info):
        active_hwnd = int(info.window_id) if info.window_id and info.window_id.isdigit() else None
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_executor, _query_blocking, active_hwnd),
                timeout=1.5,
            )
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None
```

**已知坑**（写进 README）：
- Windows 11 标签页式 Explorer：COM 只能看到当前活动 tab，其他 tab 不可见
- 桌面 (Program Manager) 不会出现在 `shell.Windows()` 中——这是正常的
- 网络驱动器路径以 UNC 形式返回（`\\server\share\...`），不要尝试解析为本地路径

### 5.4 Linux Nautilus：`linux_nautilus.py`

Nautilus 的 D-Bus 接口非常简陋（`org.gnome.Nautilus` 主要是 `OpenLocations`），**取不到当前路径或选中项**。只能用三个 fallback：

1. **窗口标题解析**（confidence 0.5）：Nautilus 标题通常是 `文件夹名` 或 `文件夹名 — Files`，结合 `psutil.Process(pid).open_files()` 反查
2. **AT-SPI**（confidence 0.7，但需要 GNOME a11y bus 开启）：遍历到 location entry 控件取 value
3. **/proc/PID/cwd**（confidence 0.2）：很多情况下错的

```python
class NautilusIntegration(FileManagerIntegration):
    def matches(self, info):
        exe = (info.process.executable or "") if info.process else ""
        return "nautilus" in exe.lower() or info.window_class == "Nautilus"

    async def query(self, info):
        # 优先 AT-SPI，失败 fallback 标题解析
        result = await self._try_atspi(info)
        if result and result.windows:
            return result
        return self._fallback_title(info)

    async def _try_atspi(self, info):
        # 用 pyatspi 在 worker 线程执行，遍历 Nautilus 应用的 a11y 树
        # 找 EditableText role 且 name 含 "Location"/"位置" 的节点
        # （具体实现略，标记为 best-effort）
        return None

    def _fallback_title(self, info):
        title = info.window_title or ""
        # Nautilus 标题模式：清理后看是否是绝对路径或家目录子目录
        candidate = title.split(" — ")[0].strip()
        # ...解析逻辑
        return None  # 不可靠就返回 None
```

**实事求是的态度**：Linux 这块拿不到就如实返回 `None`，不要硬塞假数据。文档里告诉用户："在 Linux 下文件管理器集成是 best-effort，建议结合终端集成获得更准确的上下文。"

### 5.5 Linux Dolphin：`linux_dolphin.py`

Dolphin 的 D-Bus 比 Nautilus 强：

```python
# Dolphin 暴露 org.kde.dolphin.MainWindow 接口
# bus name: org.kde.dolphin-<pid>
# 方法：viewItems()、currentPath() （视版本而定）
```

实现：用 `dbus-next`（已在 v2 依赖里？没有的话加上）异步调用，超时 500ms。Dolphin 版本差异较多，做好兼容并 fallback 到标题解析。

### 5.6 调度器 `integrations/coordinator.py`

```python
import asyncio
from PySide6.QtCore import QObject
from ..core.models import WindowInfo
from ..core.signals import bus
from .file_managers.mac_finder import FinderIntegration
from .file_managers.win_explorer import ExplorerIntegration
# ... 其他

class IntegrationCoordinator(QObject):
    def __init__(self):
        super().__init__()
        self.file_managers = self._build_fm_list()
        self.terminal = self._build_terminal()
        self._inflight: asyncio.Task | None = None
        bus.window_changed.connect(self.on_window_changed)

    def _build_fm_list(self):
        import sys
        if sys.platform == "darwin":
            return [FinderIntegration()]
        if sys.platform.startswith("win"):
            return [ExplorerIntegration()]
        if sys.platform.startswith("linux"):
            from .file_managers.linux_nautilus import NautilusIntegration
            from .file_managers.linux_dolphin import DolphinIntegration
            return [NautilusIntegration(), DolphinIntegration()]
        return []

    def _build_terminal(self):
        from .terminals.process_tree import ProcessTreeTerminal
        return ProcessTreeTerminal()  # 跨平台通用

    def on_window_changed(self, info: WindowInfo):
        # 取消之前 inflight 的查询（窗口已经切了，旧结果没用）
        if self._inflight and not self._inflight.done():
            self._inflight.cancel()
        self._inflight = asyncio.create_task(self._enrich(info))

    async def _enrich(self, info: WindowInfo):
        # 文件管理器
        for fm in self.file_managers:
            if fm.matches(info):
                state = await fm.query(info)
                if state:
                    info.file_manager_state = state
                break
        # 终端
        if self.terminal.matches(info):
            ctx = await self.terminal.query(info)
            if ctx:
                info.terminal_context = ctx
        # 再 emit 一次，让 UI 更新富信息
        bus.window_changed.emit(info)
```

## 6. Phase 12 — 终端集成

### 6.1 终端识别表

`integrations/terminals/base.py`：

```python
TERMINAL_EXECUTABLES = {
    # macOS
    "Terminal": "macos_terminal",
    "iTerm2": "iterm2",
    "iTerm": "iterm2",
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
    "kitty": "kitty",
    "tilix": "tilix",
    "terminator": "terminator",
    "xfce4-terminal": "xfce4_terminal",
    "wezterm-gui": "wezterm",
}

def detect_terminal(info) -> str | None:
    exe = info.process.executable if info.process else None
    name = info.process.name if info.process else None
    bundle = info.app_bundle_id or ""
    # ... 匹配逻辑返回 terminal key 或 None
```

### 6.2 通用方案：进程子树 `terminals/process_tree.py`

```python
import asyncio
import psutil
from ...core.models import TerminalContext, TerminalProcess
from ..redaction import redact_cmdline
from .base import TerminalIntegration, detect_terminal

SHELL_NAMES = {
    "bash", "zsh", "fish", "sh", "dash", "ksh", "tcsh",
    "pwsh", "powershell", "powershell.exe", "pwsh.exe", "cmd.exe",
    "nu", "elvish", "xonsh",
}

class ProcessTreeTerminal(TerminalIntegration):
    def matches(self, info):
        return detect_terminal(info) is not None

    async def query(self, info):
        if not info.process:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._walk, info.process.pid)

    def _walk(self, term_pid: int) -> TerminalContext | None:
        try:
            term = psutil.Process(term_pid)
        except psutil.NoSuchProcess:
            return None
        shells: list[TerminalProcess] = []
        running: list[TerminalProcess] = []
        for child in term.children(recursive=True):
            try:
                name = child.name()
                cwd = None
                try:
                    cwd = child.cwd()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
                cmdline = child.cmdline()
                redacted_cmd, was_redacted = redact_cmdline(cmdline)
                proc = TerminalProcess(
                    pid=child.pid,
                    name=name,
                    cwd=cwd,
                    cmdline=redacted_cmd,
                    cmdline_redacted=was_redacted,
                    create_time=child.create_time(),
                    is_shell=name.lower() in SHELL_NAMES,
                )
                (shells if proc.is_shell else running).append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return TerminalContext(source="process_tree", shells=shells, running=running)
```

**特殊情况处理**：

- **Windows Terminal (wt.exe)**：实际 shell 进程在 `OpenConsole.exe` 的子进程下，需要走 `children(recursive=True)`（已用）
- **macOS Terminal.app**：每个 tab 一个 `login` → `zsh` 进程链
- **tmux / screen**：tmux server 是独立进程，不是终端的子进程。当前架构看不到 tmux 内部 pane 的 cwd——这是已知限制，写进 README

### 6.3 shell 集成脚本（Tier 2，可选）

仓库根目录 `shell_integration/`：

**`bash.sh`**：
```bash
# Add the following to ~/.bashrc:
#   source /path/to/active_tracker/shell_integration/bash.sh
_active_tracker_dir="$HOME/.active_tracker/shells"
_active_tracker_update() {
    mkdir -p "$_active_tracker_dir"
    printf '%s\n' "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
}
case "$PROMPT_COMMAND" in
    *_active_tracker_update*) ;;
    *) PROMPT_COMMAND="_active_tracker_update;${PROMPT_COMMAND}" ;;
esac
# Clean up on shell exit
trap 'rm -f "$_active_tracker_dir/$$.cwd"' EXIT
```

**`zsh.sh`**：
```zsh
_active_tracker_dir="$HOME/.active_tracker/shells"
_active_tracker_update() {
    mkdir -p "$_active_tracker_dir"
    print -r -- "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd _active_tracker_update
add-zsh-hook zshexit '_at_pid=$$; rm -f "$_active_tracker_dir/$_at_pid.cwd"'
```

**`fish.fish`**：
```fish
set -g _active_tracker_dir "$HOME/.active_tracker/shells"
function _active_tracker_update --on-event fish_prompt
    mkdir -p $_active_tracker_dir
    echo $PWD > "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
end
function _active_tracker_cleanup --on-event fish_exit
    rm -f "$_active_tracker_dir/$fish_pid.cwd"
end
```

**`powershell.ps1`**：
```powershell
$ActiveTrackerDir = Join-Path $HOME ".active_tracker\shells"
if (-not (Test-Path $ActiveTrackerDir)) {
    New-Item -ItemType Directory -Path $ActiveTrackerDir -Force | Out-Null
}
# Wrap existing prompt instead of replacing it
$global:_OriginalPrompt = $function:prompt
function global:prompt {
    $cwdFile = Join-Path $ActiveTrackerDir "$PID.cwd"
    try {
        $PWD.Path | Out-File -FilePath $cwdFile -Encoding utf8 -Force -ErrorAction SilentlyContinue
    } catch {}
    & $global:_OriginalPrompt
}
# Cleanup on exit
Register-EngineEvent PowerShell.Exiting -Action {
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cwd") -ErrorAction SilentlyContinue
} | Out-Null
```

**`shell_integration/README.md`** 要写：
1. 这一步可选，目的：让终端集成在 tmux / screen / 嵌套 shell 等场景下仍准确
2. 每种 shell 的一行安装指令
3. 卸载方法（删 source 那行）
4. 隐私说明：脚本只写当前目录，不写命令、不写历史

### 6.4 shell 文件读取 `terminals/shell_files.py`

```python
from pathlib import Path
import os
import psutil
from ...core.models import TerminalContext, TerminalProcess

SHELLS_DIR = Path.home() / ".active_tracker" / "shells"

def read_shell_cwds() -> dict[int, str]:
    """读取所有 ~/.active_tracker/shells/PID.cwd，返回 {pid: cwd}。"""
    out = {}
    if not SHELLS_DIR.exists():
        return out
    for f in SHELLS_DIR.glob("*.cwd"):
        try:
            pid = int(f.stem)
            # 校验进程还活着
            if not psutil.pid_exists(pid):
                f.unlink(missing_ok=True)
                continue
            cwd = f.read_text(encoding="utf-8").strip()
            if cwd:
                out[pid] = cwd
        except (ValueError, OSError):
            continue
    return out
```

`ProcessTreeTerminal._walk` 改造：如果某个 shell 进程在 `read_shell_cwds()` 里有记录，**优先用文件里的 cwd**（脚本写的是 `$PWD`，比 `/proc/PID/cwd` 在 tmux/screen 下准确）。

### 6.5 iTerm2 官方 API（可选增强）

iTerm2 提供独立 Python 库，能订阅 session 级别事件：

```python
# 仅 macOS + iTerm2 启用了 Python API
# pip install iterm2

import iterm2

async def iterm2_watcher(emit_callback):
    async with iterm2.Connection.async_create() as connection:
        app = await iterm2.async_get_app(connection)
        async for _ in iterm2.SessionTerminationMonitor(connection):
            # 重新枚举所有 session
            for window in app.terminal_windows:
                for tab in window.tabs:
                    for session in tab.sessions:
                        variables = await session.async_get_variables(
                            ["session.path", "session.jobName", "session.jobPid"]
                        )
                        emit_callback(variables)
```

**门槛**：用户要在 iTerm2 偏好设置里 `Magic → Enable Python API`。如果没开就跳过，回落到通用进程子树方案。

实现优先级：先把通用方案做好，iTerm2 API 放最后做。

## 7. 脱敏模块 `integrations/redaction.py`

终端 cmdline 经常包含敏感信息，必须在显示前 redact。

```python
import re

# 这些参数后面的值会被替换成 ***
SENSITIVE_FLAG_PATTERNS = [
    re.compile(r"^(--?password|--?passwd|--?pass)=(.*)$", re.IGNORECASE),
    re.compile(r"^(--?token|--?api-?key|--?apikey|--?secret|--?auth)=(.*)$", re.IGNORECASE),
]
SENSITIVE_FLAG_NAMES = {
    "--password", "-p", "--passwd", "--pass",
    "--token", "--api-key", "--apikey", "--secret",
    "--auth", "--authorization", "--bearer",
}

# 值本身像 token 也直接 redact（高熵长串、AKIA 开头等）
VALUE_PATTERNS = [
    re.compile(r"^[A-Za-z0-9+/=]{40,}$"),                # 长 base64
    re.compile(r"^AKIA[0-9A-Z]{16}$"),                   # AWS access key
    re.compile(r"^sk-[A-Za-z0-9]{20,}$"),                # OpenAI / Anthropic-style
    re.compile(r"^ghp_[A-Za-z0-9]{30,}$"),               # GitHub PAT
    re.compile(r"^[A-Fa-f0-9]{32,}$"),                   # long hex
]

def _redact_value(v: str) -> str:
    if not v:
        return v
    # 太短不脱敏
    if len(v) < 8:
        return v
    return v[:3] + "***" + v[-2:] if len(v) > 12 else "***"

def redact_cmdline(cmdline: list[str]) -> tuple[list[str], bool]:
    out = []
    was_redacted = False
    i = 0
    while i < len(cmdline):
        token = cmdline[i]
        # --key=value 模式
        replaced = False
        for pat in SENSITIVE_FLAG_PATTERNS:
            m = pat.match(token)
            if m:
                out.append(f"{m.group(1)}={_redact_value(m.group(2))}")
                was_redacted = True
                replaced = True
                break
        if replaced:
            i += 1
            continue
        # --key value 模式
        if token in SENSITIVE_FLAG_NAMES and i + 1 < len(cmdline):
            out.append(token)
            out.append(_redact_value(cmdline[i + 1]))
            was_redacted = True
            i += 2
            continue
        # 值本身像 token
        if any(p.match(token) for p in VALUE_PATTERNS):
            out.append(_redact_value(token))
            was_redacted = True
            i += 1
            continue
        out.append(token)
        i += 1
    return out, was_redacted
```

写单元测试 `tests/test_redaction.py`，至少覆盖：

```python
def test_redact_password_flag():
    cmd = ["mysql", "-u", "root", "--password=hunter2", "db"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "hunter2" not in " ".join(out)

def test_redact_space_separated_token():
    cmd = ["curl", "--token", "sk-1234567890abcdef1234567890", "https://api"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "sk-1234567890abcdef1234567890" not in out

def test_keep_short_values():
    cmd = ["echo", "hi"]
    out, r = redact_cmdline(cmd)
    assert r is False
    assert out == cmd

def test_aws_key_pattern():
    cmd = ["aws", "--access-key", "AKIAIOSFODNN7EXAMPLE"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "AKIAIOSFODNN7EXAMPLE" not in out
```

## 8. UI 卡片

### 8.1 FileManagerCard `ui/widgets/file_manager_card.py`

仅当 `WindowInfo.file_manager_state` 非空时显示。布局：

```
┌─ FILE MANAGER (finder_applescript) ──────────┐
│ ▸ /Users/alice/Documents/projects  (active)  │
│   selected:                                   │
│     • report.pdf                              │
│     • notes.md                                │
│     • data/                                   │
│ ▸ /Users/alice/Downloads                      │
└──────────────────────────────────────────────┘
```

- active 的窗口高亮（左侧绿色边）
- 选中项点击复制路径
- 每个窗口可折叠

### 8.2 TerminalCard `ui/widgets/terminal_card.py`

仅当 `WindowInfo.terminal_context` 非空时显示。布局：

```
┌─ TERMINAL (process_tree) ───────────────────────┐
│ Shells:                                          │
│   ▸ zsh (84231)  ~/projects/active-tracker      │
│   ▸ bash (84532) /tmp                           │
│ Running:                                         │
│   • node (84301)  src/server.js                 │
│   • python (84410)  scripts/ingest.py --batch=… │
│     ⚠ cmdline redacted                          │
└─────────────────────────────────────────────────┘
```

被 redact 过的 cmdline 末尾显示 ⚠ 角标，鼠标 hover 提示"包含可能的敏感参数，已脱敏"。

### 8.3 集成进主窗口

`ui/main_window.py` 在右侧副栏中（v2 §18 布局图）插入两张卡：浏览器卡之下、活动卡之上。隐藏规则：`info.file_manager_state` / `info.terminal_context` 为 None 时整张卡 `setVisible(False)`。

## 9. 隐私清单

- [ ] cmdline 100% 经过 `redact_cmdline` 后再放进 `TerminalProcess.cmdline`
- [ ] shell 集成脚本只写当前目录，不写命令
- [ ] shell 集成的 `.cwd` 文件权限设为 0600（写文件时显式 `chmod`）
- [ ] 进程被检测到后，**不读取它的环境变量**（`psutil.Process.environ()` 是禁用的）
- [ ] 文件管理器查询不递归列目录（只看用户显式选中的）
- [ ] 文档/UI 明确说明："终端集成只反映此刻的状态，不记录命令历史"
- [ ] 用户可在配置中加入"绝不集成"的可执行文件列表（如 password manager 启动的 shell）

## 10. 验收标准

按平台分别验证：

### macOS
1. 打开 Finder，cd 到 `~/Documents`，选中 3 个文件 → UI 文件管理器卡 500ms 内显示该目录 + 3 个选中项
2. 在 Finder 打开第二个窗口（cmd+N）切到 `~/Downloads` → 卡片显示两个窗口，active 标记正确
3. 切到 Terminal.app，在某 tab 里 `cd ~/projects && python -m http.server` → 终端卡显示 zsh@~/projects 和 python 进程
4. 在 zsh 里跑 `curl -H "Authorization: Bearer sk-1234abcd..." https://api.example.com` → UI cmdline 显示中 `sk-1234abcd...` 被 redact

### Windows
5. 打开 Explorer，进入 `C:\Users\X\Documents`，选中 2 个文件 → 卡片正确显示
6. 同时开两个 Explorer 窗口在不同路径 → 都能显示，焦点标记正确
7. 打开 Windows Terminal，新建 PowerShell tab，`cd C:\temp` → 终端卡显示
8. PowerShell 跑 `Invoke-RestMethod -Headers @{Authorization='Bearer xyz12345abc'}` → 显示中敏感值被脱敏（这条偏宽容，主要看主程序不崩）

### Linux
9. Nautilus 进入 `~/Documents` → 卡片至少显示 folder 字段（可能拿不到选中项，可接受）
10. Dolphin 进入 `~/Documents` → 卡片显示 folder 字段
11. GNOME Terminal 中 `cd /tmp` → 终端卡显示
12. 完成 `shell_integration/bash.sh` 安装后，在 tmux 内嵌套 bash → cwd 仍准确

### 通用
13. 切换焦点应用时，文件管理器卡和终端卡按需出现/消失，不残留
14. 杀掉 Finder/Explorer 进程，主程序不崩，卡片消失
15. `redact_cmdline` 单元测试 100% 通过

## 11. 执行顺序

| 顺序 | 内容 | 备注 |
|------|------|------|
| 1 | 数据模型扩展（§3） + Coordinator 骨架（§5.6） | 不写具体集成，先打通"两次 emit"的链路 |
| 2 | 通用终端方案 `process_tree.py` + 脱敏模块 + 单元测试 | 跨平台都能用，先把终端做了 |
| 3 | TerminalCard UI | 把终端结果显示出来 |
| 4 | 当前开发平台的文件管理器集成 | macOS 选 Finder / Windows 选 Explorer |
| 5 | FileManagerCard UI | |
| 6 | 其他两个平台的文件管理器集成 | |
| 7 | shell 集成脚本 + `shell_files.py` 读取 + 整合到 process_tree | Tier 2 |
| 8 | iTerm2 官方 API（可选） | 仅 macOS |
| 9 | Linux 的 Nautilus AT-SPI 尝试 | 失败就保留 fallback |

每步独立 commit。

## 12. 给 Claude Code 的执行提示

- **AppleScript / COM 必须用 worker 线程异步调用**，主线程是 Qt 事件循环，不能阻塞
- **AppleScript 通过 `osascript` 子进程调用，每次启动有 50-100ms 开销**——这没办法避免，所以本模块本身就不可能做到 <50ms 响应；UI 端做好"先显示基本信息、500ms 后补集成结果"的体验
- **COM 调用必须在每个线程内 `CoInitialize()` / `CoUninitialize()`**，否则会随机崩。建议固定用 `ThreadPoolExecutor(max_workers=1)`，串行执行所有 COM 任务
- **`psutil` 的 `cwd()`、`cmdline()`、`environ()` 在某些进程上会抛 `AccessDenied`**——全部 try/except
- **绝不要调 `psutil.Process.environ()`**——环境变量含大量敏感信息且无法可靠脱敏
- **shell 集成脚本路径需要可发现**——主程序 UI 提供"复制脚本路径到剪贴板"按钮，方便用户配置
- **测试时记得：第一次调用 AppleScript 会触发系统授权弹窗，授权后才能拿到数据；CI 环境跑不了这部分**
