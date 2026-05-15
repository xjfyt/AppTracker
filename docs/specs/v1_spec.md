# Active App & Document Tracker — 实施规格

## 1. 项目目标

构建一个 Python 跨平台桌面工具，实时检测当前用户焦点所在的应用程序，并尽可能多地获取相关元数据（窗口标题、进程信息、打开的文件/文件夹路径等）。检测结果通过本地 Flask 服务展示在一个自动刷新的网页上。

**核心原则：能拿多少信息就显示多少，拿不到的字段显示 "—" 或 null，不要因为单个字段失败就让整个检测崩溃。**

## 2. 目标平台

| 平台 | 优先级 |
|------|--------|
| Windows 10/11 | P0 |
| macOS 12+ | P0 |
| Linux X11 | P0 |
| Linux Wayland | P2（best-effort，先不做） |

## 3. 技术栈

- **Python 3.10+**
- **Web UI**：Flask + 原生 HTML/JS（不用任何前端框架，单文件 `index.html` 通过 `fetch` 每秒轮询）
- **进程信息**：`psutil`（跨平台基础）
- **平台特定**：
  - Windows：`pywin32`、`uiautomation`
  - macOS：`pyobjc-framework-Cocoa`、`pyobjc-framework-Quartz`、`pyobjc-framework-ApplicationServices`
  - Linux：`python-xlib`、`ewmh`

依赖按平台分组写在 `requirements.txt`，用 `; sys_platform == 'win32'` 这种 PEP 508 标记区分，让安装时只装当前平台需要的。

## 4. 项目结构

```
active_tracker/
├── requirements.txt
├── README.md
├── run.py                       # 入口：启动 Flask 服务
├── core/
│   ├── __init__.py
│   ├── models.py                # WindowInfo / DocumentSource 数据类
│   ├── detector.py              # 根据 sys.platform 派发到对应 backend
│   └── utils.py                 # 路径白名单、扩展名过滤等通用工具
├── backends/
│   ├── __init__.py
│   ├── base.py                  # Backend 抽象基类
│   ├── windows.py
│   ├── macos.py
│   └── linux_x11.py
├── web/
│   ├── app.py                   # Flask 应用
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── style.css
└── tests/
    └── test_detector.py
```

## 5. 数据模型

`core/models.py`：

```python
from dataclasses import dataclass, field, asdict
from typing import Optional
import time

@dataclass
class DocumentSource:
    path: str                  # 文件路径 / 文件夹路径 / URL
    kind: str                  # "file" | "folder" | "url" | "unknown"
    source: str                # "accessibility" | "title" | "fd_scan" | "cwd" | "extension"
    confidence: float          # 0.0 - 1.0

@dataclass
class WindowInfo:
    timestamp: float = field(default_factory=time.time)
    platform: str = ""
    app_name: str = ""
    app_executable: Optional[str] = None
    pid: Optional[int] = None
    window_title: str = ""
    window_id: Optional[str] = None
    document_paths: list[DocumentSource] = field(default_factory=list)
    extra: dict = field(default_factory=dict)   # 平台特定的额外字段
    errors: list[str] = field(default_factory=list)  # 非致命错误信息

    def to_dict(self) -> dict:
        return asdict(self)
```

`backends/base.py`：

```python
from abc import ABC, abstractmethod
from core.models import WindowInfo

class Backend(ABC):
    @abstractmethod
    def get_active_window(self) -> WindowInfo:
        ...
```

## 6. Phase 1 — 骨架与派发器

1. 建好上面的目录结构，所有文件先放空类/空函数。
2. `core/detector.py`：

   ```python
   import sys

   def get_backend():
       if sys.platform.startswith("win"):
           from backends.windows import WindowsBackend
           return WindowsBackend()
       if sys.platform == "darwin":
           from backends.macos import MacOSBackend
           return MacOSBackend()
       if sys.platform.startswith("linux"):
           from backends.linux_x11 import LinuxX11Backend
           return LinuxX11Backend()
       raise RuntimeError(f"Unsupported platform: {sys.platform}")
   ```

3. 每个 backend 先返回一个写死的 `WindowInfo`（比如 `app_name="stub"`），保证 Phase 2 的 UI 能跑通。

**验收**：`python -c "from core.detector import get_backend; print(get_backend().get_active_window())"` 在三个平台上都不报错。

## 7. Phase 2 — Web UI

### 7.1 Flask 应用 (`web/app.py`)

```python
from flask import Flask, jsonify, render_template
from core.detector import get_backend

app = Flask(__name__)
backend = get_backend()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/active")
def api_active():
    try:
        info = backend.get_active_window()
        return jsonify(info.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### 7.2 入口 `run.py`

```python
from web.app import app
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005, debug=False)
```

### 7.3 页面 (`web/templates/index.html`)

要求：
- 顶部：当前时间 + 平台徽标
- 主卡片：应用名称（大字）、可执行文件路径、PID、窗口标题
- 文档列表：每条显示 path / kind / source / confidence，按 confidence 倒序
- "Extra info" 折叠面板，展示原始 JSON
- 底部：errors 列表（红色）
- 每 1 秒 fetch 一次 `/api/active`，无刷新更新
- 简洁的 CSS：等宽字体显示路径，深色背景，圆角卡片

页面骨架示例（让 Claude Code 自由发挥样式，但结构按这个来）：

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Active Tracker</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <span id="platform-badge"></span>
    <span id="timestamp"></span>
  </header>
  <main>
    <section class="app-card">
      <h1 id="app-name">—</h1>
      <div id="app-exe" class="mono"></div>
      <div>PID: <span id="pid"></span></div>
      <h2 id="title">—</h2>
    </section>
    <section class="docs">
      <h3>Documents / Paths</h3>
      <ul id="doc-list"></ul>
    </section>
    <section class="extra">
      <h3>Extra</h3>
      <pre id="extra"></pre>
    </section>
    <section class="errors" id="errors-section" hidden>
      <h3>Errors</h3>
      <ul id="errors"></ul>
    </section>
  </main>
  <script>
    async function tick() {
      try {
        const r = await fetch("/api/active");
        const data = await r.json();
        render(data);
      } catch (e) { /* show connection error */ }
    }
    function render(d) { /* 填充各个字段 */ }
    setInterval(tick, 1000);
    tick();
  </script>
</body>
</html>
```

**验收**：访问 `http://127.0.0.1:5005`，看到 stub 数据每秒刷新。

## 8. Phase 3 — Windows 后端

`backends/windows.py` 需要拿到的字段：

| 字段 | 方法 |
|------|------|
| `pid` | `win32process.GetWindowThreadProcessId(hwnd)` |
| `window_title` | `win32gui.GetWindowText(hwnd)` |
| `window_id` | `str(hwnd)` |
| `app_executable` | `psutil.Process(pid).exe()` |
| `app_name` | 从 exe 的 version info 取 `FileDescription`，失败则用 `proc.name()` |
| `document_paths` | 见下面三条策略 |
| `extra` | 包含 `class_name`（`win32gui.GetClassName`）、`cmdline`、`cwd`、`username` |

**文档路径提取（按可靠性高到低，结果都加入 `document_paths`）：**

1. **UI Automation**（confidence 0.9）：
   ```python
   import uiautomation as auto
   win = auto.ControlFromHandle(hwnd)
   # 遍历 win 的子控件，查找 ValuePattern 中包含路径的元素
   # 对 Office、Notepad++、记事本等大多数应用有效
   ```
   把找到的疑似路径（包含 `:\` 或 `\\` 且文件存在）加入结果。

2. **标题解析**（confidence 0.4）：
   - 去掉常见后缀：` - Microsoft Word`、` - Notepad`、` - Visual Studio Code` 等
   - 用正则匹配 `[A-Z]:\\[^<>:"|?*]+` 这种 Windows 路径模式
   - 检查解析出的字符串是否对应真实文件，存在的话 confidence 提到 0.7

3. **进程文件句柄扫描**（confidence 0.3）：
   - 用 `psutil.Process(pid).open_files()` 拿打开的文件
   - 用 `core/utils.py` 中的过滤器筛掉系统库、字体、临时文件
   - 保留扩展名在白名单中的（见第 11 节）

**错误处理**：每一步用 try/except 包起来，失败就 append 到 `info.errors`，继续下一步。

## 9. Phase 4 — macOS 后端

`backends/macos.py`：

```python
from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    kAXFocusedWindowAttribute,
    kAXTitleAttribute,
    kAXDocumentAttribute,
    kAXURLAttribute,
)
```

字段获取：

| 字段 | 方法 |
|------|------|
| 应用 | `NSWorkspace.sharedWorkspace().frontmostApplication()` |
| `app_name` | `app.localizedName()` |
| `app_executable` | `app.bundleURL().path()` |
| `pid` | `app.processIdentifier()` |
| `window_title` | AX 焦点窗口的 `kAXTitleAttribute` |
| `document_paths` | 见下 |

**文档路径提取：**

1. **AXDocument**（confidence 0.95）：
   ```python
   ax_app = AXUIElementCreateApplication(pid)
   err, focused = AXUIElementCopyAttributeValue(ax_app, kAXFocusedWindowAttribute, None)
   err, doc = AXUIElementCopyAttributeValue(focused, kAXDocumentAttribute, None)
   # doc 通常是 "file:///Users/..." 形式的 URL
   ```
   对 TextEdit、Pages、Preview、Word、Finder 大多数生效。

2. **标题解析**（confidence 0.4）：
   - 标题里如果包含 `~/...` 或 `/Users/...` 直接抓
   - 检查文件是否存在

3. **lsof 兜底**（confidence 0.3）：
   - `psutil.Process(pid).open_files()`
   - 同样用扩展名白名单过滤

**extra 字段**：`bundle_identifier`（`app.bundleIdentifier()`）、`launch_date`、所有 AX 属性名列表（调试用）

**权限提示**：在 README 和首次启动日志中明确告知用户需要在 *系统设置 → 隐私与安全性 → 辅助功能* 中允许运行 Python 的终端。如果 AX 调用返回 `kAXErrorAPIDisabled`，把 `"Accessibility permission not granted"` 加入 errors。

## 10. Phase 5 — Linux X11 后端

`backends/linux_x11.py`：

```python
from Xlib import display, X
from ewmh import EWMH

ewmh = EWMH()
win = ewmh.getActiveWindow()
pid = ewmh.getWmPid(win)
title = ewmh.getWmName(win).decode("utf-8", errors="replace")
```

字段获取：

| 字段 | 方法 |
|------|------|
| `window_id` | `hex(win.id)` |
| `window_title` | `_NET_WM_NAME` |
| `pid` | `_NET_WM_PID` |
| `app_executable` | `psutil.Process(pid).exe()` |
| `app_name` | `WM_CLASS`（第二个元素），失败则用进程名 |
| `document_paths` | 见下 |

**文档路径提取：**

1. **cwd**（confidence 0.3）：
   `psutil.Process(pid).cwd()` 加为 `kind="folder"`，用于像终端、编辑器这种"打开了某个工作目录"的场景。

2. **/proc/<pid>/fd 扫描**（confidence 0.3-0.5）：
   - 遍历 `psutil.Process(pid).open_files()`
   - 用白名单过滤
   - 在用户家目录下的提到 0.5

3. **标题解析**（confidence 0.4）：
   - 匹配 `/[^ ]+` 路径模式
   - 检查文件存在性

**extra 字段**：`wm_class`、`window_geometry`、`display`、`cmdline`

**Wayland 检测**：如果 `os.environ.get("XDG_SESSION_TYPE") == "wayland"`，往 errors 里写一条 `"Running under Wayland; X11 backend may only see XWayland apps"`。

## 11. Phase 6 — 文件过滤工具

`core/utils.py`：

```python
import os
from pathlib import Path

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
    # 压缩/数据
    ".zip", ".tar", ".gz", ".7z", ".epub",
}

BORING_PATH_FRAGMENTS = [
    "/site-packages/", "/dist-packages/", "/.cache/", "/Library/Caches/",
    "AppData\\Local\\", "AppData\\Roaming\\", "/proc/", "/dev/",
    "/System/", "/usr/lib/", "/usr/share/fonts/",
]

def is_interesting_path(path: str) -> bool:
    if not path:
        return False
    if any(frag in path for frag in BORING_PATH_FRAGMENTS):
        return False
    ext = Path(path).suffix.lower()
    if ext and ext in INTERESTING_EXTENSIONS:
        return True
    # 没扩展名的，如果在家目录下且不是隐藏文件，也保留
    home = str(Path.home())
    if path.startswith(home) and "/." not in path[len(home):]:
        return True
    return False
```

## 12. Phase 7 — 错误处理与日志

- 所有 backend 方法不能抛异常，必须返回带 `errors` 字段的 `WindowInfo`
- 用 Python `logging` 模块，日志写到 `./tracker.log`
- 关键事件 INFO 级别，异常 WARNING 级别（带 traceback）
- 加一个 `--debug` 命令行参数让 `run.py` 把日志同步打到 stderr

## 13. README 内容大纲

`README.md` 需要包含：
1. 一句话简介
2. 截图占位（写 `<!-- screenshot here -->`）
3. 安装步骤：
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python run.py
   # 打开 http://127.0.0.1:5005
   ```
4. 每个平台的权限说明
   - macOS: 辅助功能权限授予步骤（带菜单路径）
   - Windows: 一般无需特殊权限，但部分应用需要"以相同用户身份"才能读到
   - Linux: Wayland 限制说明
5. 已知限制清单：
   - 浏览器无法获取当前 URL（需要扩展）
   - 沙盒应用文档路径可能拿不到
   - DRM/反作弊应用拒绝读取
   - 远程桌面/虚拟机内部不可见
6. 后续可扩展方向（先不实现）：
   - 浏览器扩展通过 native messaging 接入
   - 历史记录持久化
   - 切换事件订阅取代轮询

## 14. 全局验收标准

按下述顺序在 **至少一个目标平台** 上验证：

1. `pip install -r requirements.txt` 不报错
2. `python run.py` 启动后控制台打印监听地址
3. 浏览器打开页面，主卡片显示当前焦点应用（手动切换应用后 1-2 秒内更新）
4. 用记事本/TextEdit/gedit 打开一个文件，`document_paths` 列表里出现该文件路径
5. 用浏览器打开任意网页，窗口标题正确显示，errors 列表可以为空（即便文档路径拿不到）
6. 故意杀掉一个进程后切回它，页面不能崩溃，只在 errors 中显示问题
7. 关掉所有窗口（焦点回到桌面），页面仍能正常返回数据（app_name 显示桌面或空）

## 15. 执行顺序建议

按 Phase 1 → 2 → 当前平台的 backend → 其他平台 backend → Phase 6 → Phase 7 推进。每个 Phase 完成后提交一次 git commit，commit message 写明 phase 编号和验收点。

---

**给 Claude Code 的额外提示**：
- 优先让端到端 demo 跑通（stub backend + UI 也算），再逐个填实各平台
- 任何拿不到的字段宁可留空也不要伪造
- 三个 backend 的 `extra` 字段越丰富越好，方便后续调试
- 不要使用任何需要联网的服务
- 端口 5005 被占用时自动 +1 尝试，最多试到 5010
