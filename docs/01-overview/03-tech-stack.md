> **对应代码**：`Cargo.toml`, `tracker-core/Cargo.toml`, `browser_extension/manifest.json`
> **维护提示**：升级依赖版本或引入新 crate 时同步更新本文档。

# 三、技术栈

## 1、后端（Rust）

| 依赖 | 版本 | 用途 |
|------|------|------|
| axum | 0.8 | HTTP/WebSocket/SSE 框架（含 `ws` + `json` features） |
| tokio | 1 | 异步运行时（rt-multi-thread, macros, sync, time, net, process, signal, fs） |
| serde + serde_json | 1 | 序列化/反序列化 |
| sysinfo | 0.37 | 跨平台进程信息采集（PID、exe、cmd、cwd、内存） |
| tower-http | 0.6 | CORS 中间件 |
| tracing | 0.1 | 结构化日志 |
| regex | 1 | 路径提取正则 |
| anyhow | 1 | 错误处理 |
| async-stream | 0.3 | SSE 流构建 |
| futures-util | 0.3 | Stream/Sink 工具 |
| dirs | 6 | 跨平台 home 目录 |
| base64 | 0.22 | Token 编码 |
| rand | 0.8 | Token 随机生成 |

### 可选依赖（Feature 控制）

| Feature | 依赖 | 说明 |
|---------|------|------|
| `activity`（默认开启） | rdev 0.5 | 键盘/鼠标全局监听 |
| `capture`（默认开启） | screenshots 0.8 + image 0.24 | 截图采集 + PNG 编码 |

### 平台特定依赖

| 平台 | 依赖 | 用途 |
|------|------|------|
| Windows | windows 0.62 | Win32 API（GetForegroundWindow, GetWindowRect, GetClassNameW） |
| Linux | zbus 5 | D-Bus 通信（AT-SPI 无障碍总线） |

## 2、前端（原生 HTML/CSS/JS）

前端位于 `desktop/ui/`，无构建步骤，直接由 Tauri WebView 加载：

| 文件 | 用途 |
|------|------|
| `index.html` | 页面结构：顶栏、侧边栏、主视图、灯箱 |
| `main.js` | WebSocket 连接、事件渲染、API 交互、诊断面板 |
| `styles.css` | 样式（CSS 变量主题系统） |

## 3、浏览器扩展（MV3）

| 文件 | 用途 |
|------|------|
| `manifest.json` | Chrome/Firefox MV3 声明（permissions: tabs, activeTab, storage, alarms） |
| `background.js` | Service Worker：WebSocket 桥接、token 自动发现、Tab 事件监听 |
| `popup.html` + `popup.js` | 扩展弹窗 UI |

支持的浏览器：Chrome、Edge、Brave、Arc、Firefox（通过 `gecko` 配置）。

## 4、Shell 集成

| 文件 | Shell | 机制 |
|------|-------|------|
| `bash.sh` | bash | `PROMPT_COMMAND` 写 `~/.active_tracker/shells/$PID.cwd` |
| `zsh.sh` | zsh | `precmd` hook |
| `fish.fish` | fish | `fish_prompt` 事件 |
| `powershell.ps1` | PowerShell | `prompt` 函数重写 |
| `cmd.cmd` | cmd.exe | `doskey` 劫持 `cd/pushd/popd` |

## 5、构建工具链

| 工具 | 版本要求 |
|------|---------|
| Rust | 2021 edition |
| Node.js | 仅 Tauri 开发时需要 |
| npm | 仅 Tauri 开发时需要 |

---

- 上一篇：[02-architecture.md](./02-architecture.md)
- 下一篇：[01-build.md](../02-getting-started/01-build.md)
- 返回索引：[docs/README.md](../README.md)
