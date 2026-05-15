# Active App & Document Tracker — 实施规格 v2

## 0. 本文档变更说明（相对 v1）

- **GUI**：从 Flask + 网页改为 **PySide6 桌面应用**，不走 web
- **包管理**：从 pip 改为 **uv**，Python 锁定 **3.12**
- **更新机制**：从 1Hz 轮询改为**事件驱动 + 信号槽实时推送**
- **浏览器 URL**：新增**浏览器扩展**模块，通过 WebSocket 实时推送当前 tab
- **新增信号**：窗口位置/大小、应用完整路径、用户操作（键鼠聚合统计）、屏幕窗口截图

## 1. 项目目标

构建一个 Python 跨平台桌面工具，**实时**检测当前用户焦点所在的应用程序，并尽可能多地获取相关元数据。检测结果通过 PySide6 GUI 实时展示，前台应用切换、窗口标题变化、文件切换都应在用户感知不到延迟（< 200ms）的情况下更新到界面。

**核心原则**：
1. 能拿多少信息显示多少，单个字段失败不影响其他字段
2. 真·事件驱动，不要无脑轮询
3. 用户可看、可暂停、可清除——隐私是产品基础设施

## 2. 目标平台

| 平台 | 优先级 | 备注 |
|------|--------|------|
| Windows 10/11 | P0 | 主要测试平台 |
| macOS 13+ | P0 | 需辅助功能权限 |
| Linux X11 | P0 | |
| Linux Wayland | P2 | 不在本期范围 |

## 3. 技术栈

- **Python 3.12**（用 uv 锁定）
- **uv** 管理依赖与虚拟环境
- **PySide6**（≥ 6.6）GUI
- **psutil** 进程信息
- **pynput** 键鼠活动监听
- **mss** + **Pillow** 屏幕截图
- **websockets** + **qasync** 浏览器扩展通信
- **平台特定**：
  - Windows：`pywin32`、`uiautomation`
  - macOS：`pyobjc-framework-Cocoa`、`pyobjc-framework-Quartz`、`pyobjc-framework-ApplicationServices`
  - Linux：`python-xlib`、`ewmh`

## 4. 项目结构

```
active_tracker/
├── pyproject.toml
├── uv.lock
├── README.md
├── src/
│   └── active_tracker/
│       ├── __init__.py
│       ├── __main__.py              # python -m active_tracker
│       ├── app.py                   # QApplication 启动入口
│       ├── core/
│       │   ├── models.py            # 数据类
│       │   ├── signals.py           # 全局 SignalBus
│       │   └── utils.py
│       ├── monitors/
│       │   ├── base.py              # WindowMonitor 抽象基类
│       │   ├── windows_monitor.py
│       │   ├── macos_monitor.py
│       │   └── linux_x11_monitor.py
│       ├── activity/
│       │   └── activity_monitor.py  # 键鼠聚合统计
│       ├── capture/
│       │   └── screen_capture.py    # 截图
│       ├── browser/
│       │   └── bridge.py            # WebSocket 服务端
│       └── ui/
│           ├── main_window.py
│           ├── widgets/
│           │   ├── app_card.py
│           │   ├── window_card.py
│           │   ├── document_list.py
│           │   ├── browser_card.py
│           │   ├── activity_card.py
│           │   ├── screenshot_view.py
│           │   └── error_log.py
│           └── style.qss
├── browser_extension/
│   ├── manifest.json
│   ├── background.js
│   ├── popup.html
│   ├── popup.js
│   ├── icons/
│   │   ├── 16.png
│   │   ├── 48.png
│   │   └── 128.png
│   └── README.md
└── tests/
    ├── test_models.py
    └── test_filters.py
```

## 5. uv 初始化与依赖

```bash
# 初始化
uv init --python 3.12 active_tracker
cd active_tracker
```

`pyproject.toml`：

```toml
[project]
name = "active-tracker"
version = "0.1.0"
requires-python = "==3.12.*"
dependencies = [
    "PySide6>=6.6",
    "psutil>=5.9",
    "pynput>=1.7",
    "mss>=9.0",
    "pillow>=10.0",
    "websockets>=12.0",
    "qasync>=0.27",
    # platform-specific
    "pywin32>=306; sys_platform == 'win32'",
    "uiautomation>=2.0; sys_platform == 'win32'",
    "pyobjc-framework-Cocoa>=10.0; sys_platform == 'darwin'",
    "pyobjc-framework-Quartz>=10.0; sys_platform == 'darwin'",
    "pyobjc-framework-ApplicationServices>=10.0; sys_platform == 'darwin'",
    "python-xlib>=0.33; sys_platform == 'linux'",
    "ewmh>=0.1.6; sys_platform == 'linux'",
]

[project.scripts]
active-tracker = "active_tracker.app:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/active_tracker"]
```

安装与运行：

```bash
uv sync
uv run active-tracker
# 或
uv run python -m active_tracker
```

## 6. 数据模型

`src/active_tracker/core/models.py`：

```python
from dataclasses import dataclass, field, asdict
from typing import Optional
import time

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
    browser: str        # "chrome" | "edge" | "firefox" | "brave" | "arc"
    pid: Optional[int]
    window_id: Optional[int]
    tab_id: Optional[int]
    url: str
    title: str
    favicon_url: Optional[str] = None
    is_active: bool = True

@dataclass
class WindowInfo:
    timestamp: float = field(default_factory=time.time)
    platform: str = ""
    app_name: str = ""
    app_bundle_id: Optional[str] = None     # macOS: bundle identifier; Windows: AppUserModelID
    window_title: str = ""
    window_id: Optional[str] = None
    window_class: Optional[str] = None      # Win32 class / macOS subrole / X11 WM_CLASS
    geometry: Optional[WindowGeometry] = None
    process: Optional[ProcessInfo] = None
    document_paths: list[DocumentSource] = field(default_factory=list)
    browser_tab: Optional[BrowserTab] = None  # 当前焦点是浏览器时填充
    extra: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ActivityStats:
    timestamp: float = field(default_factory=time.time)
    window_seconds: int = 60        # 统计窗口长度（秒）
    keys_count: int = 0
    clicks_count: int = 0
    mouse_distance_px: float = 0.0
    scrolls_count: int = 0
    idle_seconds: float = 0.0
    # 不存储任何按键内容
```

## 7. 信号总线架构

`src/active_tracker/core/signals.py`：

```python
from PySide6.QtCore import QObject, Signal
from .models import WindowInfo, ActivityStats, BrowserTab
from PySide6.QtGui import QImage

class SignalBus(QObject):
    """全局信号总线，各模块通过它解耦通信。"""
    window_changed = Signal(WindowInfo)        # 焦点窗口变化（包含切换 + 标题变化）
    activity_updated = Signal(ActivityStats)   # 每秒一次活动统计
    browser_tab_updated = Signal(BrowserTab)   # 浏览器扩展推送
    screenshot_ready = Signal(QImage)          # 新截图就绪
    error_occurred = Signal(str, str)          # (source, message)
    paused_changed = Signal(bool)              # 暂停状态切换

bus = SignalBus()   # 单例
```

**所有模块向 `bus` 发信号**，UI 订阅，相互不直接调用——保证可测试性和模块化。

## 8. Phase 1 — 项目骨架 + PySide6 主窗口外壳

1. 用上面的 `pyproject.toml` 初始化 uv 项目
2. 建好目录结构，所有文件先放空类/空函数
3. `src/active_tracker/app.py`：

   ```python
   import sys
   import asyncio
   from PySide6.QtWidgets import QApplication
   import qasync
   from .ui.main_window import MainWindow

   def main():
       app = QApplication(sys.argv)
       loop = qasync.QEventLoop(app)
       asyncio.set_event_loop(loop)
       window = MainWindow()
       window.show()
       with loop:
           loop.run_forever()

   if __name__ == "__main__":
       main()
   ```

4. `MainWindow` 先布局好 6 个卡片占位（应用卡 / 窗口卡 / 文档列表 / 浏览器卡 / 活动卡 / 截图预览），数据先写死
5. 顶栏放：暂停按钮、平台标签、最后更新时间

**布局建议**（不强制）：
- 左侧主栏：应用卡（大）→ 窗口卡 → 文档列表
- 右侧副栏：浏览器卡 → 活动卡 → 截图预览
- 底部：可折叠错误日志

**验收**：`uv run active-tracker` 能弹出窗口，所有卡片显示占位数据。

## 9. Phase 2 — 跨平台事件驱动窗口监视器

### 9.1 抽象基类 `monitors/base.py`

```python
from PySide6.QtCore import QObject, QThread
from ..core.models import WindowInfo

class WindowMonitor(QObject):
    """所有平台监视器必须发出 bus.window_changed 信号。"""
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self._running = False

    def start(self):
        """启动监听（通常会起一个 QThread 跑原生事件循环）。"""
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def query_now(self) -> WindowInfo:
        """主动查询当前状态（用于启动时初始化和定时兜底）。"""
        raise NotImplementedError
```

### 9.2 派发

`monitors/__init__.py`：

```python
import sys

def create_monitor(bus):
    if sys.platform.startswith("win"):
        from .windows_monitor import WindowsMonitor
        return WindowsMonitor(bus)
    if sys.platform == "darwin":
        from .macos_monitor import MacOSMonitor
        return MacOSMonitor(bus)
    if sys.platform.startswith("linux"):
        from .linux_x11_monitor import LinuxX11Monitor
        return LinuxX11Monitor(bus)
    raise RuntimeError(f"Unsupported: {sys.platform}")
```

### 9.3 工作模式（所有平台共用）

- **启动时**：`query_now()` 拿一次状态，立刻 `emit window_changed`
- **事件驱动**：在工作线程跑平台原生事件循环，捕获焦点切换 / 窗口标题改变事件，每次事件触发 `query_now()` 并 emit
- **兜底**：在主线程跑一个 QTimer，每 2 秒 `query_now()` 一次，对比上次结果有变化才 emit（防止事件漏掉）

## 10. Phase 3 — Windows 监视器

`monitors/windows_monitor.py`：

**事件 hook**：使用 `SetWinEventHook` 监听以下事件：
- `EVENT_SYSTEM_FOREGROUND`：前台窗口切换
- `EVENT_OBJECT_NAMECHANGE`：窗口标题变化（带 `WINEVENT_OUTOFCONTEXT`）
- `EVENT_OBJECT_LOCATIONCHANGE`：窗口移动/缩放（按需，可能太吵）

hook 必须跑在带消息泵的线程，用 `QThread` + `win32gui.PumpMessages()`。

**字段获取**：

| 字段 | API |
|------|-----|
| `pid` | `win32process.GetWindowThreadProcessId(hwnd)` |
| `window_title` | `win32gui.GetWindowText(hwnd)` |
| `window_id` | `str(hwnd)` |
| `window_class` | `win32gui.GetClassName(hwnd)` |
| `geometry` | `win32gui.GetWindowRect(hwnd)` → 转为 `WindowGeometry` |
| `process.executable` | `psutil.Process(pid).exe()` |
| `process.cmdline` | `psutil.Process(pid).cmdline()` |
| `process.cwd` | `psutil.Process(pid).cwd()` |
| `app_name` | exe 的 version info 中 `FileDescription`，失败则 `proc.name()` |
| `app_bundle_id` | 从 hwnd 拿 AppUserModelID（`win32com.shell.shell.SHGetPropertyStoreForWindow` → `PKEY_AppUserModel_ID`），失败 None |

**多屏 geometry**：用 `win32api.MonitorFromWindow(hwnd)` 拿到显示器，再用 `EnumDisplayMonitors` 拿到所有显示器的索引和坐标，算出 `screen_index`。

**document_paths**（三策略合并，去重）：

1. **UI Automation**（confidence 0.9）：
   ```python
   import uiautomation as auto
   win = auto.ControlFromHandle(hwnd)
   # 优先找 DocumentControl
   for ctrl in win.GetChildren():
       try:
           if ctrl.ControlTypeName == "DocumentControl":
               val = ctrl.GetValuePattern().Value
               if val and (":\\" in val or val.startswith("\\\\")):
                   # 加入 document_paths
   ```
   遍历深度限制 3 层避免卡死。给整个调用加 2 秒超时（用 `concurrent.futures`）。

2. **标题解析**（confidence 0.4-0.7）：
   - 去掉常见后缀：` - Microsoft Word`, ` - Notepad`, ` — VSCode`, ` - File Explorer` 等
   - 正则 `[A-Z]:\\[^<>:"|?*\r\n]+`
   - 如果对应路径存在 → confidence 0.7，否则 0.4

3. **fd 扫描**（confidence 0.3）：
   - `psutil.Process(pid).open_files()`
   - 过滤白名单扩展名（见 §13）

**extra 字段**：`hwnd_hex`、`thread_id`、`window_styles`（GetWindowLong）、`is_maximized`、`is_minimized`

## 11. Phase 4 — macOS 监视器

`monitors/macos_monitor.py`：

**事件 hook**：用 `NSWorkspace` 通知中心订阅：
- `NSWorkspaceDidActivateApplicationNotification`：应用切换
- 配合 `AXObserverAddNotification` 订阅每个应用的 `kAXFocusedWindowChangedNotification`、`kAXTitleChangedNotification`、`kAXWindowMovedNotification`、`kAXWindowResizedNotification`

PyObjC 的通知回调在主线程触发——直接用 Qt 的 QTimer.singleShot 把工作转到处理函数即可。

**字段获取**：

```python
from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCreateApplication, AXUIElementCopyAttributeValue,
    kAXFocusedWindowAttribute, kAXTitleAttribute, kAXDocumentAttribute,
    kAXPositionAttribute, kAXSizeAttribute, kAXRoleAttribute, kAXSubroleAttribute,
)
```

| 字段 | 方法 |
|------|------|
| `app_name` | `app.localizedName()` |
| `app_bundle_id` | `app.bundleIdentifier()` |
| `process.executable` | `app.bundleURL().path()` |
| `pid` | `app.processIdentifier()` |
| `window_title` | AX 焦点窗口 `kAXTitleAttribute` |
| `window_class` | AX `kAXSubroleAttribute` |
| `geometry` | AX `kAXPositionAttribute` + `kAXSizeAttribute`，结合 `NSScreen.screens()` 算 `screen_index` |

**document_paths**：

1. **AXDocument**（confidence 0.95）：
   ```python
   err, doc = AXUIElementCopyAttributeValue(focused_window, kAXDocumentAttribute, None)
   # doc 是 "file:///..." URL，转成本地路径
   ```

2. **AppleScript 兜底**（confidence 0.85，仅对支持的应用）：
   - 对 Finder：`tell application "Finder" to get POSIX path of (target of front window as alias)`
   - 对 Chrome：见 §12 浏览器章节
   - 用 `osascript` 子进程，加 1 秒超时
   - 维护一个白名单 `{bundle_id: applescript}` 字典

3. **标题解析**（confidence 0.4）

4. **lsof / open_files**（confidence 0.3）

**extra 字段**：所有可读的 AX 属性名列表（调试用）、`activation_policy`、`launch_date`

**权限处理**：第一次启动时检测 AX 可用性：

```python
from ApplicationServices import AXIsProcessTrustedWithOptions
from CoreFoundation import CFDictionaryCreate
# 弹出系统授权对话框：
trusted = AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
```

未授权时 UI 顶部显示醒目提示，并给一个"打开系统设置"按钮（用 `subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])`）。

## 12. Phase 5 — Linux X11 监视器

`monitors/linux_x11_monitor.py`：

**事件 hook**：
- 订阅根窗口的 `PropertyChangeMask`
- 监听属性 `_NET_ACTIVE_WINDOW`（焦点切换）和当前活动窗口的 `_NET_WM_NAME`、`WM_NAME`（标题变化）、`_NET_WM_STATE`、几何变化用 `ConfigureNotify`
- 用 QThread 跑 `display.next_event()` 阻塞循环

**字段获取**：

| 字段 | 方法 |
|------|------|
| `window_id` | `hex(win.id)` |
| `window_title` | `_NET_WM_NAME` 优先，fallback `WM_NAME` |
| `pid` | `_NET_WM_PID` 属性 |
| `app_executable` | `psutil.Process(pid).exe()` |
| `app_name` | `WM_CLASS[1]`（instance name），fallback 进程名 |
| `window_class` | `WM_CLASS[0]`（class name） |
| `geometry` | `win.get_geometry()` + 用 `win.translate_coords(root, 0, 0)` 算绝对坐标 |

**document_paths**：

1. **AT-SPI2**（confidence 0.6，覆盖率有限）：
   - 用 `pyatspi` 拿焦点应用的 document 接口
   - 失败概率高，写好兜底

2. **cwd**（confidence 0.3）：作为 `kind="folder"` 加入

3. **/proc/<pid>/fd 扫描**（confidence 0.3-0.5）

4. **标题解析**（confidence 0.4-0.7）

**Wayland 检测**：

```python
import os
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    self.bus.error_occurred.emit("linux_monitor",
        "Running under Wayland; X11 backend only sees XWayland apps")
```

**extra 字段**：`wm_class`、`is_xwayland`、`window_role`、`startup_id`

## 13. Phase 6 — 文件过滤工具

`src/active_tracker/core/utils.py`：

```python
from pathlib import Path

INTERESTING_EXTENSIONS = {
    ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pdf",
    ".xls", ".xlsx", ".ods", ".csv", ".tsv",
    ".ppt", ".pptx", ".odp", ".key",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".rs", ".go",
    ".rb", ".php", ".sh", ".sql", ".yaml", ".yml", ".toml", ".json", ".xml",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".mp3", ".wav", ".flac", ".mp4", ".mov", ".mkv",
    ".psd", ".ai", ".sketch", ".fig", ".xd",
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

def dedupe_documents(docs: list) -> list:
    """同 path 去重，保留 confidence 最高的那条。"""
    seen = {}
    for d in docs:
        if d.path not in seen or d.confidence > seen[d.path].confidence:
            seen[d.path] = d
    return sorted(seen.values(), key=lambda x: -x.confidence)
```

## 14. Phase 7 — 浏览器扩展 + WebSocket 桥

### 14.1 架构

```
[Browser Extension Service Worker]
        │  WebSocket
        ▼
[Python: BrowserBridge]  (ws://127.0.0.1:5006)
        │  Qt Signal
        ▼
[bus.browser_tab_updated]
        │
        ▼
[BrowserCard UI 更新]
```

扩展和 Python 在同一台机器，用 WebSocket 而非 Native Messaging——Native Messaging 部署太烦（每个 OS 一个 manifest 路径），WebSocket 一行配置搞定。代价是要做一次握手认证防止其他本地进程乱连。

### 14.2 Python 端 `browser/bridge.py`

```python
import asyncio
import json
import secrets
from pathlib import Path
import websockets
from PySide6.QtCore import QObject
from ..core.models import BrowserTab
from ..core.signals import bus

# 启动时生成 token，写入 ~/.active_tracker/token
TOKEN_PATH = Path.home() / ".active_tracker" / "token"

class BrowserBridge(QObject):
    def __init__(self):
        super().__init__()
        self.token = self._load_or_create_token()
        self.clients = set()

    def _load_or_create_token(self) -> str:
        TOKEN_PATH.parent.mkdir(exist_ok=True)
        if TOKEN_PATH.exists():
            return TOKEN_PATH.read_text().strip()
        t = secrets.token_urlsafe(32)
        TOKEN_PATH.write_text(t)
        TOKEN_PATH.chmod(0o600)
        return t

    async def handler(self, ws):
        # 握手：第一条消息必须是 {"token": "..."}
        try:
            auth = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if auth.get("token") != self.token:
                await ws.close(code=4001, reason="bad token")
                return
        except Exception:
            return
        self.clients.add(ws)
        try:
            async for msg in ws:
                data = json.loads(msg)
                if data.get("type") == "tab_update":
                    tab = BrowserTab(
                        browser=data["browser"],
                        pid=data.get("pid"),
                        window_id=data.get("windowId"),
                        tab_id=data.get("tabId"),
                        url=data["url"],
                        title=data["title"],
                        favicon_url=data.get("favIconUrl"),
                        is_active=data.get("active", True),
                    )
                    bus.browser_tab_updated.emit(tab)
        finally:
            self.clients.discard(ws)

    async def serve(self):
        async with websockets.serve(self.handler, "127.0.0.1", 5006):
            await asyncio.Future()  # run forever
```

用 qasync 在 Qt 主事件循环里 `asyncio.create_task(bridge.serve())`。

### 14.3 浏览器扩展

放在 `browser_extension/` 目录，**同一份代码同时适配 Chrome / Edge / Brave / Arc / Firefox**。

**`manifest.json`** (Manifest V3)：

```json
{
  "manifest_version": 3,
  "name": "Active Tracker Bridge",
  "version": "0.1.0",
  "description": "Streams active tab info to the local Active Tracker app.",
  "permissions": ["tabs", "activeTab", "storage"],
  "host_permissions": ["<all_urls>"],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "popup.html",
    "default_icon": "icons/48.png"
  },
  "icons": {
    "16": "icons/16.png",
    "48": "icons/48.png",
    "128": "icons/128.png"
  },
  "browser_specific_settings": {
    "gecko": {
      "id": "active-tracker@localhost",
      "strict_min_version": "115.0"
    }
  }
}
```

**`background.js`** 关键逻辑：

```javascript
const WS_URL = "ws://127.0.0.1:5006";
let ws = null;
let token = null;
let reconnectDelay = 1000;

async function loadToken() {
  const stored = await chrome.storage.local.get("token");
  return stored.token || null;
}

function connect() {
  if (!token) {
    console.warn("[ActiveTracker] No token set. Open popup to configure.");
    return;
  }
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    ws.send(JSON.stringify({ token }));
    reconnectDelay = 1000;
    pushActiveTab();
  };
  ws.onclose = () => {
    ws = null;
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
  };
  ws.onerror = (e) => console.warn("[ActiveTracker] ws error", e);
}

function send(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

async function pushActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tabs.length) return;
  const t = tabs[0];
  send({
    type: "tab_update",
    browser: detectBrowser(),
    windowId: t.windowId,
    tabId: t.id,
    url: t.url,
    title: t.title,
    favIconUrl: t.favIconUrl,
    active: true,
  });
}

function detectBrowser() {
  const ua = navigator.userAgent;
  if (ua.includes("Edg/")) return "edge";
  if (ua.includes("Firefox/")) return "firefox";
  if (ua.includes("Brave/")) return "brave";
  return "chrome";
}

chrome.tabs.onActivated.addListener(pushActiveTab);
chrome.tabs.onUpdated.addListener((id, change, tab) => {
  if (change.status === "complete" || change.url || change.title) pushActiveTab();
});
chrome.windows.onFocusChanged.addListener((wid) => {
  if (wid !== chrome.windows.WINDOW_ID_NONE) pushActiveTab();
});

// Manifest V3 service worker keepalive
chrome.alarms.create("keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN) connect();
});

(async () => {
  token = await loadToken();
  connect();
})();
```

**`popup.html`** + **`popup.js`**：

- 显示连接状态（已连接 / 未连接 / 等待 token）
- 一个输入框让用户粘贴 token，保存到 `chrome.storage.local`
- 一个"暂停推送"开关

**`browser_extension/README.md`** 需要包含：

1. **如何拿到 token**：
   - 启动 Python 主程序
   - 复制 `~/.active_tracker/token` 内的字符串
   - 或主程序 UI 提供"复制 token"按钮

2. **Chrome / Edge / Brave 安装**：
   - 打开 `chrome://extensions`
   - 开启"开发者模式"
   - "加载已解压的扩展程序" → 选择 `browser_extension/` 目录
   - 点扩展图标 → 粘贴 token → 保存

3. **Firefox 安装**（临时加载，关闭浏览器会消失；要永久需签名）：
   - 打开 `about:debugging#/runtime/this-firefox`
   - "临时载入附加组件" → 选 `manifest.json`

4. **验证**：连接成功后扩展图标显示绿点 / 失败显示红点

### 14.4 主程序 UI 集成

`BrowserCard` 在收到 `bus.browser_tab_updated` 后显示：
- 浏览器图标 + 名称
- URL（可点击复制）
- 页面标题
- favicon

**关键交互**：当 `WindowMonitor` 上报的当前焦点 app 是浏览器（按可执行文件名匹配 `chrome.exe`、`firefox.exe`、`Google Chrome`、`Brave Browser` 等），主 UI 显示浏览器卡片高亮，并把 `browser_tab.url` 作为 `DocumentSource(kind="url", source="browser_ext", confidence=1.0)` 加入文档列表。

### 14.5 macOS AppleScript 备选

对于不愿装扩展的 macOS 用户，监视器在检测到 Chrome/Safari 焦点时自动调 AppleScript 拿 URL：

```python
def get_chrome_url_via_applescript() -> tuple[str, str] | None:
    script = 'tell application "Google Chrome" to return (URL of active tab of front window) & "||" & (title of active tab of front window)'
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, timeout=1, text=True)
        if out.returncode == 0:
            url, title = out.stdout.strip().split("||", 1)
            return url, title
    except Exception:
        pass
    return None
```

第一次调用会触发系统弹"允许自动化"权限对话框。Firefox 不支持，跳过。

## 15. Phase 8 — 活动监视器（键鼠聚合）

`src/active_tracker/activity/activity_monitor.py`：

```python
from collections import deque
import time
from PySide6.QtCore import QObject, QTimer
from pynput import keyboard, mouse
from ..core.models import ActivityStats
from ..core.signals import bus

class ActivityMonitor(QObject):
    def __init__(self, window_seconds=60):
        super().__init__()
        self.window_seconds = window_seconds
        self.events = deque()   # (timestamp, kind, payload)
        self.last_mouse_pos = None
        self.mouse_distance = 0.0
        self.last_input_time = time.time()

        self.kb_listener = keyboard.Listener(on_press=self._on_key)
        self.mouse_listener = mouse.Listener(
            on_click=self._on_click, on_move=self._on_move, on_scroll=self._on_scroll)
        self.kb_listener.start()
        self.mouse_listener.start()

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start()

    def _on_key(self, key):
        # 仅记录事件发生，不存按键值
        self.events.append((time.time(), "key", None))
        self.last_input_time = time.time()

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self.events.append((time.time(), "click", None))
            self.last_input_time = time.time()

    def _on_move(self, x, y):
        now = time.time()
        if self.last_mouse_pos:
            dx = x - self.last_mouse_pos[0]
            dy = y - self.last_mouse_pos[1]
            self.mouse_distance += (dx * dx + dy * dy) ** 0.5
        self.last_mouse_pos = (x, y)
        self.last_input_time = now

    def _on_scroll(self, x, y, dx, dy):
        self.events.append((time.time(), "scroll", None))
        self.last_input_time = time.time()

    def _tick(self):
        now = time.time()
        cutoff = now - self.window_seconds
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
        stats = ActivityStats(
            timestamp=now,
            window_seconds=self.window_seconds,
            keys_count=sum(1 for e in self.events if e[1] == "key"),
            clicks_count=sum(1 for e in self.events if e[1] == "click"),
            scrolls_count=sum(1 for e in self.events if e[1] == "scroll"),
            mouse_distance_px=self.mouse_distance,
            idle_seconds=now - self.last_input_time,
        )
        bus.activity_updated.emit(stats)
        # mouse_distance 不重置（持续累积当前窗口距离需要按 deque 算，简化为单调累加显示）
```

**ActivityCard UI** 显示：
- "过去 1 分钟"：按键 X 次 / 点击 Y 次 / 滚动 Z 次 / 鼠标移动 W px
- 当前空闲 N 秒
- 一条 60s 滚动迷你图（QPainter 自绘）显示活跃度趋势

**隐私**：
- `_on_key` 函数体内**绝对不能**出现 `key` 参数的任何属性访问（除存在性外）
- README 明确告知"不记录任何键值"

## 16. Phase 9 — 屏幕窗口捕获

`src/active_tracker/capture/screen_capture.py`：

```python
import mss
from PIL import Image
from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QImage
from io import BytesIO
from ..core.signals import bus
from ..core.models import WindowInfo

class ScreenCapture(QObject):
    def __init__(self, max_fps: float = 0.5, thumb_max_size=480):
        """默认每 2 秒最多截一次（max_fps=0.5），且在窗口变化时立即截一次。"""
        super().__init__()
        self.min_interval = 1.0 / max_fps
        self.thumb_max_size = thumb_max_size
        self._last_capture_t = 0.0
        self._sct = mss.mss()
        bus.window_changed.connect(self.on_window_changed)
        # 定时兜底
        self._timer = QTimer(self)
        self._timer.setInterval(int(self.min_interval * 1000))
        self._timer.timeout.connect(self.capture_now)
        self._timer.start()
        self._last_window = None

    def on_window_changed(self, info: WindowInfo):
        self._last_window = info
        self.capture_now()

    def capture_now(self):
        import time
        now = time.time()
        if now - self._last_capture_t < self.min_interval:
            return
        self._last_capture_t = now
        try:
            qimg = self._capture_active_window()
            if qimg:
                bus.screenshot_ready.emit(qimg)
        except Exception as e:
            bus.error_occurred.emit("screen_capture", str(e))

    def _capture_active_window(self) -> QImage | None:
        info = self._last_window
        if not info or not info.geometry:
            # 退化为主屏全屏
            mon = self._sct.monitors[1]
            shot = self._sct.grab(mon)
        else:
            g = info.geometry
            # mss 用绝对坐标
            bbox = {"left": g.x, "top": g.y, "width": g.width, "height": g.height}
            # 防御性裁切：宽高至少 10
            if g.width < 10 or g.height < 10:
                return None
            shot = self._sct.grab(bbox)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img.thumbnail((self.thumb_max_size, self.thumb_max_size))
        # PIL -> QImage
        buf = BytesIO()
        img.save(buf, format="PNG")
        qimg = QImage.fromData(buf.getvalue(), "PNG")
        return qimg
```

**ScreenshotView 控件**：QLabel + setPixmap，显示最新 QImage 缩略图，下方显示捕获时间。

**隐私设计**：
- 截图**仅显示在 UI 中，不写入磁盘**（v1 阶段）
- 顶栏暂停按钮按下时，停止接收 `window_changed` 信号 → 不再截图
- 维护"敏感应用黑名单"：bundle_id/exe 在黑名单时不截图，UI 显示"已屏蔽"占位图
  - 默认黑名单：1Password、KeePass、银行类应用（按 bundle_id 前缀），用户可配置
  - 黑名单存 `~/.active_tracker/blacklist.json`

## 17. Phase 10 — 暂停、错误日志、打包

### 17.1 全局暂停

- 主窗口顶部一个大开关按钮（QPushButton checkable）
- 暂停时：所有 monitor 停止 emit，所有 listener 也调用 stop()（活动监视器除外，否则恢复时计数会乱——改为仅停止 UI 更新）
- 状态写 `bus.paused_changed`，所有卡片订阅，暂停时变灰

### 17.2 错误日志

- 所有 `bus.error_occurred` 写入 `~/.active_tracker/tracker.log`（用 `logging.handlers.RotatingFileHandler`，10MB × 3）
- UI 底部可折叠面板，显示最近 50 条
- 加 `--debug` 参数同步打到 stderr

### 17.3 打包

不在本期范围，但 `README.md` 标注后续可用：
- Windows：`pyinstaller` 或 `briefcase`
- macOS：`briefcase`（处理签名 + 公证）
- Linux：AppImage 或直接 `uv run`

## 18. UI 总览

主窗口最小 1100 × 720，可调大小。建议布局（grid 2 列）：

```
┌────────────────────────────────────────────────────────────────┐
│ [⏸ Paused] Active Tracker      Platform: macOS  ⟳ 12:34:56  │
├──────────────────────────────┬─────────────────────────────────┤
│  APP CARD                    │  BROWSER CARD                   │
│  ━━━━━━━━━━━━━━━            │  ━━━━━━━━━━━━━━━━              │
│  Visual Studio Code          │  🌐 Chrome                       │
│  /Applications/VSCode.app    │  github.com/anthropics/...      │
│  PID 84421                   │  Anthropic · GitHub             │
├──────────────────────────────┤                                 │
│  WINDOW CARD                 ├─────────────────────────────────┤
│  Title: spec.md — tracker    │  ACTIVITY CARD                  │
│  Class: AXWindow             │  ⌨ 142 keys/min                │
│  Geometry: 120,80 1200×800   │  🖱 38 clicks/min               │
│  Screen: 0 (main)            │  idle: 0.4s                     │
├──────────────────────────────┤  [▁▂▃▅▆▇▇▆▅▃▂▁]                │
│  DOCUMENTS                   ├─────────────────────────────────┤
│  📄 spec.md (AX, 0.95)       │  SCREENSHOT                     │
│  📁 ~/projects/tracker (cwd) │  ┌─────────────────────┐        │
│  📄 README.md (title, 0.7)   │  │  [窗口缩略图]       │        │
│                              │  │                     │        │
│                              │  └─────────────────────┘        │
│                              │  Captured 12:34:55              │
├──────────────────────────────┴─────────────────────────────────┤
│  ▼ Errors (2)                                                  │
└────────────────────────────────────────────────────────────────┘
```

样式用 `style.qss` 控制，深色主题，等宽字体显示路径。

## 19. 全局验收标准

按下述顺序验证，**至少一个目标平台**全过：

1. `uv sync && uv run active-tracker` 启动后看到主窗口
2. 切换应用 → 主窗口在 **200ms 内**更新顶部 app name
3. 在编辑器里打开新文件 → documents 列表新增条目
4. 拖动窗口 → window card 的 geometry 实时变化
5. 打字 30 秒 → activity card 的 keys/min 上升
6. 静置 10 秒 → idle_seconds 上升到 ~10
7. 启动浏览器扩展并完成 token 配置 → browser card 出现 URL，切换 tab 实时更新
8. 截图区显示当前焦点窗口的缩略图，不超过 2 秒延迟
9. 按暂停按钮 → 所有信号停止，再次按下恢复
10. 杀掉一个被监视的进程 → 主窗口不崩溃，错误面板显示警告
11. macOS 未授予辅助功能权限 → 顶部黄色横幅 + "打开系统设置"按钮可用
12. 浏览器扩展断开 → BrowserBridge 自动重连，UI 显示"未连接"
13. 检查 `~/.active_tracker/tracker.log` 内容合理

## 20. 隐私清单（提交前必看）

- [ ] 活动监视器只记录事件计数和距离，**绝不**记录按键内容
- [ ] 截图只在内存中流转，不落盘
- [ ] 敏感应用黑名单默认包含密码管理器
- [ ] WebSocket 桥用 token 鉴权
- [ ] token 文件权限 0600
- [ ] 暂停按钮按下后所有采集真的停止（测试一遍）
- [ ] README 隐私章节说明每种数据采集了什么、存哪里

## 21. 执行顺序

| 顺序 | Phase | 关键产出 |
|------|-------|----------|
| 1 | Phase 1 | uv 项目跑起来，主窗口空壳 |
| 2 | Phase 2 + 当前开发平台对应的 Phase 3/4/5 | 应用切换实时同步 |
| 3 | Phase 6 | 文档路径列表能填充 |
| 4 | Phase 8 | 活动卡能动 |
| 5 | Phase 9 | 截图能显示 |
| 6 | Phase 7 | 浏览器扩展 + WebSocket |
| 7 | Phase 3/4/5 其他平台 | 跨平台 |
| 8 | Phase 10 | 暂停、日志、README |

每 Phase 完成 `git commit`，commit message 标 Phase 编号。

---

**给 Claude Code 的执行提示**：
- 用 `uv add` 加依赖，不要手改 pyproject 后再 sync
- 跨线程信号传递依赖 Qt 的 `Qt.QueuedConnection`，PySide6 默认会处理，但工作线程里**不要**直接操作 widget
- pynput 在 macOS 上需要输入监控权限；首启时需要引导
- 浏览器扩展开发期间用 `chrome://extensions` 的"重新加载"按钮快速迭代
- 任何可能阻塞的调用（lsof、osascript、AX 大树遍历）必须带超时
- 写代码时优先保证不崩，宁可一个字段为空也别让整个 emit 失败
