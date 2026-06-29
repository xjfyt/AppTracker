> **对应代码**：`tracker-core/src/agent.rs`, `tracker-core/src/state.rs`, `tracker-core/src/api/mod.rs`
> **维护提示**：修改模块交互关系或数据流时同步更新本文档。

# 二、架构设计

## 1、总体架构

AppTracker 采用 Rust workspace monorepo，分为四个子项目：

```
┌─────────────────────────────────────────────────────────────┐
│                    Tauri 桌面壳 (desktop/src-tauri)          │
│  main.rs → install_panic_hook → start_agent(AgentConfig)    │
│                       ┌─────────────────────┐                │
│                       │  desktop/ui/         │                │
│                       │  index.html          │                │
│                       │  main.js             │                │
│                       │  styles.css          │                │
│                       └─────────────────────┘                │
└───────────────────────────┬─────────────────────────────────┘
                            │ 依赖
┌───────────────────────────▼─────────────────────────────────┐
│                    tracker-core（核心库）                      │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  agent   │  │  state   │  │   api    │  │ platform │    │
│  │  窗口轮询 │  │  状态管理 │  │ HTTP/WS  │  │ 平台抽象  │    │
│  └────┬─────┘  └──────────┘  └──────────┘  └──────────┘    │
│       │                                                      │
│  ┌────▼──────────────┐  ┌──────────┐  ┌──────────┐         │
│  │  integrations     │  │ activity │  │ capture  │         │
│  │  文件管理器/终端   │  │ 键鼠监控 │  │ 截图采集  │         │
│  └───────────────────┘  └──────────┘  └──────────┘         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  tools   │  │  bridge  │  │diagnostics│                  │
│  │ 路径工具  │  │ 浏览器token│ │ panic hook│                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  browser_extension/     shell_integration/                   │
│  Chrome/Firefox MV3     bash/zsh/fish/pwsh/cmd              │
│  WebSocket → localhost  PROMPT_COMMAND → .cwd 文件           │
└─────────────────────────────────────────────────────────────┘
```

## 2、数据流

```
                    ┌──────────────┐
                    │  OS 前台窗口  │
                    └──────┬───────┘
                           │ 250ms 轮询
                    ┌──────▼───────┐
                    │ active_window│
                    │ (platform/)  │
                    └──────┬───────┘
                           │ WindowInfo (基础)
                    ┌──────▼───────┐
                    │  agent.rs    │
                    │ DocumentMemory│ ← 标题→路径记忆
                    │ fast_identity │
                    └──────┬───────┘
                           │ watch channel
                    ┌──────▼───────┐
                    │ enrich_window│
                    │ integrations │
                    │ ┌──────────┐ │
                    │ │platform/ │ │ → Office COM / UIA / AX / lsof / /proc/fd
                    │ │file_mgr  │ │ → Explorer COM / Finder AS / D-Bus
                    │ │terminal  │ │ → 进程树遍历 + shell hook 文件
                    │ └──────────┘ │
                    └──────┬───────┘
                           │ WindowInfo (富化)
                    ┌──────▼───────┐
                    │ TrackerState │ ← Arc<RwLock<InnerState>>
                    │  broadcast   │ ← broadcast::channel(256)
                    └──┬───┬───┬──┘
                       │   │   │
          ┌────────────┘   │   └────────────┐
          ▼                ▼                 ▼
   ┌────────────┐  ┌────────────┐  ┌──────────────┐
   │ REST API   │  │ WebSocket  │  │ SSE Stream   │
   │ /snapshot  │  │ /ws        │  │ /events      │
   └────────────┘  └────────────┘  └──────────────┘
```

## 3、进程拓扑

Tauri 桌面应用启动后，核心在 `tauri::async_runtime::spawn` 中调用 `start_agent()`：

```
Tauri 主进程
  └─ async_runtime
       ├─ start_agent()
       │    ├─ spawn_api()              → TcpListener (Axum)
       │    ├─ spawn_activity_monitor() → rdev::listen (独立 OS 线程) + tokio 统计任务
       │    ├─ spawn_screen_capture()   → tokio 截图任务
       │    └─ spawn_window_monitor()   → supervised("window_monitor")
       │         ├─ run_window_monitor()        → 250ms 轮询 + fast_identity 去重
       │         └─ spawn_window_enrichment_worker() → supervised("window_enrichment")
       │              └─ run_window_enrichment_worker() → enrich_window() 富化
       └─ tauri 窗口管理
```

## 4、supervised 自动重启

`supervised()` 是 agent.rs 中的关键容错机制：当内部任务 panic 时自动重启，日志记录到 `~/.active_tracker/crash.log`。

```rust
async fn supervised<F, Fut>(name: &'static str, mut make_fut: F)
```

- 正常退出 → 不重启（worker 已完成）
- panic → 等待 2 秒后重启，attempt 计数递增
- 取消 → 不重启

## 5、端口回退

API 服务绑定时从配置端口（默认 5007）开始尝试，最多回退 5 个端口（5007-5012）。浏览器扩展和桌面 UI 均内置相同的回退扫描逻辑。

---

- 上一篇：[01-introduction.md](./01-introduction.md)
- 下一篇：[03-tech-stack.md](./03-tech-stack.md)
- 返回索引：[docs/README.md](../README.md)
