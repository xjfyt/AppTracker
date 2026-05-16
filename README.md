# Active Tracker

Rust/Tauri 版 Active Tracker。底层核心是 headless Rust agent，负责窗口、进程、终端、文件管理器、浏览器桥、截图、键鼠活动聚合与本机 API；Tauri 只是一个读取 API 的页面。

## 运行

```powershell
# headless agent，适合被你的软件作为 sidecar 启动
cargo run -p tracker-agent -- --api-port 5007

# Tauri 页面
cd desktop
npm install
npm run dev
```

构建：

```powershell
cargo build -p tracker-agent
cd desktop
npm run build
```

## API

默认监听：

- API: `http://127.0.0.1:5007`
- Browser bridge: `ws://127.0.0.1:5006`

路由：

- `GET /api/v1/health`
- `GET /api/v1/snapshot`
- `GET /api/v1/screenshot`
- `GET /api/v1/events`
- `GET /api/v1/ws`
- `GET/POST /api/v1/pause`

浏览器扩展仍使用 `~/.active_tracker/token` 鉴权；现有 `browser_extension/` 可继续连接。

## 平台能力

- Windows: Win32 前台窗口、进程信息、cmdline/cwd 文档探测、Office/WPS COM 文档探测、UI Automation 文档探测、Explorer COM、终端进程树、shell cwd 文件、截图、键鼠活动。
- macOS: System Events / AppleScript 前台窗口、Finder AppleScript、进程树、shell cwd 文件、截图、键鼠活动。仍需要 Accessibility / Input Monitoring / Automation 权限。
- Linux: X11 下使用 `xdotool` / `xprop` / `xwininfo` 获取窗口信息；文件管理器为 cwd/title best-effort；Wayland 会返回受限提示。

## 接入建议

上层软件优先把 `tracker-agent` 作为 sidecar 进程，通过 HTTP/SSE/WebSocket 消费状态。这样采集权限、平台差异和异常隔离都更容易处理。

