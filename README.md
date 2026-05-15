# Active Tracker

> 实时检测当前焦点应用、窗口、文档路径、URL、键鼠活动，并通过 PySide6 桌面 GUI 展示。
> 跨平台（Windows / macOS / Linux X11），事件驱动，本地优先，隐私可控。
> 同时提供 HTTP / SSE / WebSocket API 给外部客户端消费。

## 特性

- **跨平台**：Windows 10/11 · macOS 13+ · Linux X11
- **事件驱动**：NSWorkspace 通知 / SetWinEventHook / X PropertyNotify — 切换应用 < 200 ms 内更新
- **多策略文档路径**：辅助功能 API → AppleScript → 标题正则 → 进程句柄扫描，自动去重保留最高置信度
- **文件管理器深度集成**：Finder / Explorer 拿所有窗口的当前目录 + 选中项
- **终端深度集成**：列出每个终端进程下的所有 shell（含真实 pwd）和正在运行的子进程，cmdline 自动脱敏
- **浏览器扩展**：Chrome / Edge / Brave / Arc / Firefox 同一份 MV3 扩展，WebSocket + token 推送当前 tab
- **活动聚合**：每秒输出按键 / 点击 / 滚动 / 鼠标距离 / 空闲，60 s 滑动窗口；**不记录任何按键值**
- **焦点窗口截图**：mss 抓取 + 缩略图，密码管理器自动屏蔽，不写盘
- **API 服务**：REST 快照 + SSE 事件流 + WebSocket 长连（含 30s 心跳），任选一种消费
- **全局暂停**：顶栏一键停止所有采集和 UI 更新

## 快速开始

需要 **Python 3.12** + [uv](https://docs.astral.sh/uv/)。

```bash
# 同步依赖（首次会自动创建 .venv）
uv sync

# 启动
uv run main.py            # 默认监听 API: 127.0.0.1:5007
uv run main.py --debug    # 同步打日志到 stderr
```

常用开关：

| 开关 | 作用 |
|------|------|
| `--debug` | 把日志同步打到 stderr（默认仅写日志文件） |
| `--no-activity` | 不启动 pynput 键鼠监视器 |
| `--no-capture` | 不截图 |
| `--no-browser-bridge` | 不开浏览器扩展 WebSocket 桥（5006） |
| `--no-api` | 不开 API 服务（5007） |
| `--api-port N` | 改 API 端口 |
| `--check` | 冒烟模式：构造完所有组件 2 秒后退出 |

日志：`~/.active_tracker/tracker.log`（10 MB × 3 滚动）

## 模块布局

```
common/        领域类型 + 全局信号总线
tools/         无状态工具（path_filter / redaction / blacklist / port）
controllers/   有状态协调器（窗口监视 / 活动 / 截图 / 浏览器桥 / 集成调度器）
plugins/       可插拔实现（文件管理器各家 / 终端各家）
api/           HTTP/SSE/WS 服务
ui/            PySide6 主窗口与卡片
docs/          所有文档
tests/         单测（50 用例 / pytest）
browser_extension/   MV3 浏览器扩展（同适配 Chrome/Firefox/...）
shell_integration/   bash/zsh/fish/pwsh 集成脚本（Tier 2，可选）
main.py        入口
```

依赖方向：ui/api → controllers/plugins → tools/common。反向不允许。

## 详细文档

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 架构 / 信号总线 / 数据流 / 跨线程 / 插件机制 |
| [docs/api.md](docs/api.md) | API 参考 + httpx / EventSource / WebSocket 客户端示例 |
| [docs/permissions.md](docs/permissions.md) | 各平台权限授予步骤 |
| [docs/shell_integration.md](docs/shell_integration.md) | shell 集成脚本（Tier 2） |
| [docs/browser_extension.md](docs/browser_extension.md) | 浏览器扩展安装与使用 |
| [docs/specs/](docs/specs/) | 历史 spec 归档 |

## 隐私清单

- [x] **不记录任何按键值** — `activity_monitor._on_key` 仅累加计数
- [x] **截图仅在内存中** — 不落盘；默认黑名单含密码管理器
- [x] **WebSocket 桥本机限定** — `127.0.0.1` + token 鉴权
- [x] **Token 文件 0600**，删除可重新生成
- [x] **终端 cmdline 脱敏**：`--password=` / `--token` / AKIA*/sk-*/ghp_* 等模式自动 redact
- [x] **API 不开鉴权**，但默认监听 `127.0.0.1`；若要 `0.0.0.0` 暴露需自己加 nginx/auth

## 开发与测试

```bash
uv run pytest             # 50/50 (含 API 端到端)
uv run main.py --check    # 端到端冒烟：构造完所有组件 2s 后退出
```

## 已知限制

- macOS Finder 桌面选中文件不算 window，AppleScript 拿不到
- Windows 11 标签页式 Explorer 仅 active tab 可见
- Linux 文件管理器选中项基本拿不到（D-Bus/AT-SPI 太脆弱）
- 多 tab 终端的 active tab 当前是"最近启动的 shell"近似
- 浏览器 URL 必须靠扩展，主程序无法直读

## License

MIT
