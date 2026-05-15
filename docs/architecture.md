# 架构

Active Tracker 由几组明确分工的模块组成，全部通过 `common.signals.bus`（一个 PySide6 `QObject` 单例）解耦通信。

## 模块布局

```
common/        领域类型与全局信号总线（最稳定，被所有模块依赖）
tools/         无状态工具函数（path_filter / redaction / blacklist / port）
controllers/   有状态、订阅/发布 bus 的协调器
plugins/       可插拔的「特定应用 / 特定平台」实现
api/           HTTP/SSE/WebSocket 服务，把内部状态暴露给外部客户端
ui/            PySide6 主窗口与卡片 widgets
```

依赖方向（从上到下，单向）：

```
ui    api
  \  /
controllers ─── plugins
      │           │
      ▼           ▼
            tools / common
```

`controllers/` 和 `plugins/` 可以依赖 `tools/` 和 `common/`，但反向不行。`ui/` 和 `api/` 是消费者，只订阅 bus、不直接驱动业务。

## 信号总线

[`common/signals.py`](../common/signals.py) 定义了一个 `SignalBus(QObject)` 单例，6 个跨模块信号：

| 信号 | 发布方 | 订阅方 |
|------|--------|--------|
| `window_changed(WindowInfo)` | `controllers/window_monitor/*` | UI、`integration_coordinator`、`screen_capture`、`api/state` |
| `activity_updated(ActivityStats)` | `controllers/activity_monitor` | UI、`api/state` |
| `browser_tab_updated(BrowserTab)` | `controllers/browser_bridge` | UI、`api/state` |
| `browser_connected(bool)` | `controllers/browser_bridge` | UI |
| `screenshot_ready(QImage)` | `controllers/screen_capture` | UI、`api/state` |
| `error_occurred(str, str)` | 任意模块 | UI（错误面板）+ logging |
| `paused_changed(bool)` | UI（暂停按钮） | 所有 controllers |

## 数据流：一次焦点切换

```
[NSWorkspace 通知 / SetWinEventHook / X PropertyNotify]
        │
        ▼
controllers.window_monitor.MacOSMonitor.emit_current("workspace")
        │   query_now() 拿基础窗口信息（app / pid / title / geometry / process / docs）
        ▼
bus.window_changed(info_basic)   ──┬───► ui.MainWindow            （即时渲染：应用卡/窗口卡/文档列表）
                                    ├───► controllers.screen_capture （触发节流后的延迟截图）
                                    ├───► api.state.APIState        （更新 REST 快照 + 推到 SSE/WS 订阅者）
                                    └───► controllers.integration_coordinator
                                              │
                                              │ async enrich(info)  ←──── 取消上一次 inflight 任务
                                              │   • 文件管理器插件 query
                                              │   • 终端插件 query
                                              ▼
                                          bus.window_changed(info_full)
                                              │   含 file_manager_state / terminal_context
                                              ▼
                                          ui / api 再次渲染
```

Coordinator 通过检查 `file_manager_state` 或 `terminal_context` 是否已填来防自循环（已 enrich 过的 emit 直接跳过）。

## 插件机制

`plugins/file_managers/` 和 `plugins/terminals/` 是两个自包含 package。它们的 `__init__.py` 提供平台无关的发现入口：

```python
from plugins import file_managers, terminals

fm_list = file_managers.get_for_platform()   # [FinderIntegration()]（macOS 上）
term = terminals.get_default()               # ProcessTreeTerminal()
```

`IntegrationCoordinator` 不知道具体有哪些插件，只调入口；新增一个文件管理器集成只需：

1. 在 `plugins/file_managers/` 下建一个新模块，继承 `FileManagerIntegration`
2. 在 `plugins/file_managers/__init__.py` 的 `get_for_platform()` 里按 `sys.platform` 添加

终端插件同理。

## 控制器生命周期

每个 controller 都有 `start()` / `stop()`。`main.py` 在 `_start_all()` 里集中启动，在 `aboutToQuit` 钩子里集中停止——保证 asyncio loop 关闭前所有后台任务被 `cancel()`。

`bus.paused_changed` 被所有 controllers 订阅，暂停时停止 emit 但不停止内部累积（活动监视器除外，保留计数器一致性）。

## 跨线程

- `controllers/window_monitor/*` 在工作线程 (`QThread`) 跑原生事件循环（PumpMessages / Xlib next_event / NSWorkspace 通知）
- `controllers/activity_monitor` 用 pynput 起两个 daemon 线程
- aiohttp / websockets / qasync 共用 Qt 的 asyncio loop（主线程）
- `api/state.APIState` 的 bus 回调在 Qt 线程触发，通过 `loop.call_soon_threadsafe(...)` 投回 asyncio loop 再 fanout

Qt 的 `QueuedConnection` 在跨线程 emit 时自动启用；signal 处理函数始终在 receiver 所在线程执行。

## 日志

- 文件：`~/.active_tracker/tracker.log`（`RotatingFileHandler`，10 MB × 3）
- `bus.error_occurred` 自动接到 logging（每个 source 用独立 logger 名字）
- `--debug` 把同样的格式也打到 stderr

## 测试金字塔

- `tests/test_models.py` · 数据类与 identity_key 行为
- `tests/test_filters.py` · `tools/path_filter` 的纯函数
- `tests/test_tools.py` · `tools/blacklist` + `tools/port`
- `tests/test_redaction.py` · `tools/redaction` 11 种敏感参数模式
- `tests/test_integrations.py` · 插件入口 + Coordinator 反循环
- `tests/test_api.py` · 通过 aiohttp TestServer + httpx 端到端打路由（含 WS）

50 用例总耗时 < 0.3s（不需 GUI 环境）。
