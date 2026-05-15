# Active Tracker

> 实时检测当前焦点应用、窗口、文档路径、URL、键鼠活动，并通过 PySide6 桌面 GUI 展示。
> 跨平台（Windows / macOS / Linux X11），事件驱动，本地优先，隐私可控。

<!-- screenshot here -->

## 目录

- [特性](#特性)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [架构与数据流](#架构与数据流)
- [平台权限](#平台权限)
- [命令行选项](#命令行选项)
- [浏览器扩展](#浏览器扩展)
- [隐私清单](#隐私清单)
- [开发与测试](#开发与测试)
- [已知限制](#已知限制)
- [后续路线](#后续路线)

## 特性

- **跨平台**：Windows 10/11 · macOS 13+ · Linux X11
- **事件驱动**：NSWorkspace 通知 / SetWinEventHook / X PropertyNotify — 切换应用 < 200 ms 内更新
- **多策略文档路径**：辅助功能 API → AppleScript → 标题正则 → 进程句柄扫描，自动去重保留最高置信度
- **文件管理器深度集成**：Finder / Explorer 拿所有窗口的当前目录 + 选中项；Linux 文件管理器尽力而为
- **终端深度集成**：列出每个终端进程下的所有 shell（含真实 pwd）和正在运行的子进程，cmdline 自动脱敏
- **浏览器扩展**：Chrome / Edge / Brave / Arc / Firefox 同一份 MV3 扩展，通过 WebSocket + token 推送当前 tab
- **活动聚合**：每秒输出按键 / 点击 / 滚动 / 鼠标距离 / 空闲时间，60 s 滑动窗口；**不记录任何按键值**
- **焦点窗口截图**：mss 抓取 + 缩略图，密码管理器自动屏蔽，不写盘
- **全局暂停**：顶栏一键停止所有采集和 UI 更新
- **错误友好**：单字段失败不影响其他字段，所有非致命错误聚合到 UI 底部错误面板和 `~/.active_tracker/tracker.log`

## 快速开始

需要 **Python 3.12** + [uv](https://docs.astral.sh/uv/)。

```bash
# 1) 同步依赖（首次会自动创建 .venv）
uv sync

# 2) 启动
uv run main.py
```

加 `--debug` 把日志同步打到 stderr：

```bash
uv run main.py --debug
```

## 项目结构

```
.
├── main.py                      # 程序入口（uv run main.py）
├── pyproject.toml               # uv 管理（package = false，仅作依赖项目）
├── core/
│   ├── models.py                # WindowInfo / DocumentSource / ActivityStats 等数据类
│   ├── signals.py               # 全局 SignalBus（window_changed / activity_updated / ...）
│   └── utils.py                 # 路径白名单、文档去重、URL/标题解析
├── monitors/
│   ├── base.py                  # 抽象基类 + 2 s 兜底定时器
│   ├── macos_monitor.py         # NSWorkspace + AX + AppleScript
│   ├── windows_monitor.py       # SetWinEventHook + UIA（线程池硬性超时）
│   └── linux_x11_monitor.py     # Xlib PropertyChange + EWMH
├── activity/
│   └── activity_monitor.py      # pynput 聚合统计（隐私敏感：不读键值）
├── capture/
│   └── screen_capture.py        # mss → Pillow → QImage，黑名单过滤
├── browser/
│   └── bridge.py                # WebSocket 服务端 + token 鉴权
├── integrations/                # 深度集成：异步、二段 emit、可独立测试
│   ├── coordinator.py           # 监听 window_changed → 异步 enrich → 再次 emit
│   ├── redaction.py             # 命令行脱敏
│   ├── file_managers/           # Finder · Explorer · Nautilus · Dolphin
│   └── terminals/               # 通用 process_tree + shell 集成脚本读取
├── ui/
│   ├── main_window.py           # MainWindow：顶栏 / 双栏 splitter / 错误日志
│   ├── widgets/                 # 8 个卡片 widget（含 FileManagerCard + TerminalCard）
│   └── style.qss                # 深色主题
├── browser_extension/           # Chromium / Firefox MV3 扩展
├── shell_integration/           # 可选 Tier 2：bash / zsh / fish / pwsh 集成脚本
└── tests/                       # 单元测试
```

## 深度集成（文件管理器 / 终端）

`integrations/` 模块在窗口监视器之上做异步丰富，命中后再次 emit `window_changed`，
UI 会在主信息出现后约 100–500 ms 内补充展示对应卡片。

### 文件管理器

| 平台    | 实现                                  | 拿得到 |
|---------|-------------------------------------|--------|
| macOS   | AppleScript 一次枚举所有 Finder 窗口 | 每个窗口的目录 + active 窗口的选中项 |
| Windows | Shell COM (`Shell.Application.Windows()`) | 所有 Explorer 窗口的目录 + 选中项（Win11 tab 仅 active 可见） |
| Linux   | psutil cwd + 标题解析（best-effort） | 单个窗口的目录；选中项基本拿不到 |

macOS 首次使用会触发系统 "允许 Active Tracker 控制 Finder" 对话框（**自动化权限**，
和辅助功能权限是两个开关，分别授权）。

### 终端

通用 `process_tree` 方案：递归遍历终端进程子孙，分两组列出 —

- **Shells**：bash / zsh / fish / pwsh / cmd 等，附带真实 `pwd`
- **Running**：当前被 shell 启动的非 shell 进程（编辑器、构建命令、脚本…），cmdline 自动脱敏

#### Shell 集成脚本（可选 Tier 2）

裸方案的 cwd 来自 `psutil.Process.cwd()`，在 tmux / screen / 嵌套 shell 下会不准。
可选安装 [`shell_integration/`](shell_integration/) 下的脚本（bash / zsh / fish / pwsh），
每次 prompt 把 `$PWD` 写入 `~/.active_tracker/shells/PID.cwd` 文件（权限 0600，
只写当前目录，不写命令）。主程序检测到后会优先用文件里的 cwd，UI 会显示 `shell-file` chip。

主窗口顶栏 **Shell 脚本目录** 按钮一键复制路径，方便在 rc 文件里 source。

### Cmdline 脱敏

所有终端的 cmdline 都经过 [`integrations/redaction.py`](integrations/redaction.py) 后才显示，
识别并 redact：

- `--password=xxx` / `--token xxx` / `--api-key xxx` 等敏感 flag 的值
- 值本身像 AWS access key（`AKIA*`）、GitHub PAT（`ghp_*`）、Anthropic/OpenAI key（`sk-*`）、长 hex / 长 base64

被 redact 过的行右侧显示 ⚠ redacted chip。

## 架构与数据流

事件驱动，所有跨模块通信走 [`core/signals.py`](core/signals.py) 的单例 `bus`：

```
┌─────────────────┐  NSWorkspace / SetWinEventHook / Xlib
│ WindowMonitor   │ ─────────────────────────────────────────► bus.window_changed
└─────────────────┘  (event + 2s fallback)                       │
                                                                 ▼
┌─────────────────┐                                       ┌─────────────────┐
│ ActivityMonitor │ ──── pynput ────► bus.activity_updated│   MainWindow    │
└─────────────────┘                                       │  ┌───────────┐  │
                                                          │  │ App/Win    │ │
┌─────────────────┐                                       │  │ Documents  │ │
│ ScreenCapture   │ ── mss ─► bus.screenshot_ready ──────►│  │ Browser    │ │
└─────────────────┘                                       │  │ Activity   │ │
                                                          │  │ Screenshot │ │
┌─────────────────┐                                       │  │ Errors     │ │
│ BrowserBridge   │◄─ ws://127.0.0.1:5006 ─┐              │  └───────────┘ │
└────────┬────────┘                       │              └─────────────────┘
         │                                 │                       ▲
         └─► bus.browser_tab_updated ──────┘                       │
                                                                   │
                              ┌──────────┐    chrome.tabs API     │
                              │ Browser  │─────────────────────────┘
                              │Extension │
                              └──────────┘
```

- **WindowMonitor**：平台事件触发 `emit_current()`，调 `query_now()` 拿 `WindowInfo` 并做 identity 去重
- **ActivityMonitor**：pynput 后台线程 → QTimer 每秒聚合 → `ActivityStats`
- **ScreenCapture**：监听 `window_changed`，依靠 `geometry` 字段抓焦点窗口，按 `max_fps=0.5` 节流
- **BrowserBridge**：与浏览器扩展握手认证后接收 `tab_update` JSON 消息，转成 `BrowserTab` 发到 bus
- **MainWindow** 仅订阅信号，不主动拉数据 — 保证可测试性

## 平台权限

| 平台    | 权限                | 用途                          | 缺失时降级                     |
|---------|---------------------|-------------------------------|--------------------------------|
| macOS   | 辅助功能 (Accessibility) | 窗口标题/几何/AXDocument | 仅 NSWorkspace 数据（应用名/PID） |
| macOS   | 输入监控 (Input Monitoring) | pynput 键鼠聚合         | 活动卡片显示 0                 |
| macOS   | 自动化 (Automation) | Finder / Chrome / Safari AppleScript 取 URL | 退化到 AXURL 或标题解析  |
| Windows | （默认即可）         | UIA 树需要进程对等           | 部分 UWP 应用拒绝读取           |
| Linux   | X11 会话             | XLib PropertyChange         | Wayland 仅能看到 XWayland 应用 |

**授权步骤（macOS）**：

1. 启动 `uv run main.py`，UI 顶部会出现黄色横幅 → 点 **打开系统设置**
2. *系统设置 → 隐私与安全性 → 辅助功能* 中勾选运行 Python 的终端
3. *输入监控* 同样勾选一次
4. 重启 `uv run main.py`

## 命令行选项

| 选项                    | 作用                                         |
|-------------------------|----------------------------------------------|
| `--debug`               | 日志同步打到 stderr（默认仅写日志文件）       |
| `--no-activity`         | 不启动 pynput 键鼠监视器                      |
| `--no-capture`          | 不截图                                        |
| `--no-browser-bridge`   | 不开 WebSocket 桥                             |
| `--check`               | 冒烟模式：构造完所有组件 2 s 后退出           |

日志位置：`~/.active_tracker/tracker.log`（10 MB × 3 滚动）

## 浏览器扩展

主程序内置 WebSocket 服务，端口 `127.0.0.1:5006`，token 鉴权。
扩展安装步骤见 [`browser_extension/README.md`](browser_extension/README.md)。

简版：

1. 启动主程序，UI 顶栏点 **复制 Token**
2. Chrome → `chrome://extensions` → 开发者模式 → 加载已解压扩展程序 → 选 `browser_extension/`
3. 点扩展图标 → 粘贴 token → 保存

主界面 **Browser** 卡片就会显示当前 tab 的 URL/标题。

## 隐私清单

- [x] **不记录任何按键值** — `ActivityMonitor._on_key` 仅累加计数，不读 `key.char` / `key.vk` / `key.name`
- [x] **截图仅在内存中** — 不落盘；密码管理器默认黑名单（`~/.active_tracker/blacklist.json`，可改）
- [x] **WebSocket 桥本机限定** — 仅 `127.0.0.1`，token 鉴权
- [x] **Token 文件权限 0600** — 存 `~/.active_tracker/token`，删了重启就重新生成
- [x] **全局暂停** — 一键停掉所有 monitor emit 和 screen capture
- [x] **错误面板透明** — UI 底部能看到所有非致命错误的来源和消息

## 开发与测试

```bash
# 运行单元测试
uv run pytest

# 仅装运行依赖（无 dev）
uv sync --no-dev

# 调试模式
uv run main.py --debug

# 离线检查能否启动（不弹 GUI 持久运行）
uv run main.py --check
```

代码结构原则：

- **跨线程信号**：Qt 自动用 `QueuedConnection`，工作线程**不直接操作 widget**
- **超时**：所有可能阻塞的调用（lsof、osascript、UIA 遍历）都带超时
- **不崩**：宁可某字段为空也别让整个 emit 失败 — 用 try/except 包到 `errors` 字段

## 已知限制

- 浏览器当前 URL 必须靠扩展，主程序自己无法读取
- 沙盒应用（Mac App Store / UWP）的文档路径常拿不到
- DRM / 反作弊应用拒绝被读取
- 远程桌面 / 虚拟机内部进程对宿主不可见
- Wayland 会话仅能看到 XWayland 兼容应用

## 后续路线

- macOS 用 AXObserver 替代 250 ms 快轮询，做到真·零延迟事件驱动
- 历史记录持久化到本地 SQLite，做时间轴/聚焦时长统计
- 截图脱敏（OCR 后再模糊敏感词）
- 打包：Windows PyInstaller / macOS briefcase（签名 + 公证）/ Linux AppImage
- macOS 系统托盘常驻 + 全局快捷键暂停
