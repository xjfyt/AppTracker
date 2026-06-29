> **对应代码**：`tracker-core/src/agent.rs`
> **维护提示**：修改 Agent 启动流程或整体架构时同步更新本文档。

# 九、Agent 核心 — 概述

## 1、职责

Agent 核心（`agent.rs`）是 AppTracker 的启动入口和主循环协调器，负责：

1. 初始化所有子系统（API、活动监控、截图采集）
2. 运行 250ms 窗口轮询主循环
3. 管理 DocumentMemory（标题→路径记忆）
4. 编排富化管线（enrichment worker）
5. 提供 supervised 自动重启容错

## 2、关键类型

### AgentConfig

```rust
pub struct AgentConfig {
    pub host: String,              // API 绑定地址
    pub api_port: u16,             // API 端口
    pub no_activity: bool,         // 禁用键鼠监控
    pub no_capture: bool,          // 禁用截图
    pub capture_default_on: bool,  // 截图默认开启
    pub poll_interval_ms: u64,     // 轮询间隔
}
```

### AgentHandle

```rust
pub struct AgentHandle {
    pub state: TrackerState,       // 状态容器
    pub api: ServerHandle,         // API 服务句柄
    pub window_task: JoinHandle<()>, // 窗口监控任务句柄
}
```

## 3、启动流程

```
start_agent(config)
  │
  ├─ TrackerState::new()                    // 创建状态容器
  ├─ load_or_create_token()                 // 浏览器扩展 token
  ├─ spawn_api(state, host, port, token)    // 启动 Axum 服务
  │
  ├─ if !no_activity:
  │    spawn_activity_monitor(state, 60)    // 键鼠监控（60s 窗口）
  │
  ├─ if !no_capture:
  │    state.set_capture_enabled(default)   // 设置截图默认状态
  │    spawn_screen_capture(state)          // 截图采集
  │
  └─ spawn_window_monitor(state, poll_ms)   // 窗口监控主循环
       └─ supervised("window_monitor", ...)
            └─ run_window_monitor()
```

## 4、子系统协作

```
                    start_agent()
                        │
          ┌─────────────┼─────────────┐
          │             │             │
    ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
    │ API Server│ │Activity │ │  Capture  │
    │ (Axum)    │ │ (rdev)  │ │(screenshots)
    └───────────┘ └─────────┘ └───────────┘
                        │
                ┌───────▼───────┐
                │Window Monitor │
                │  250ms 轮询   │
                └───────┬───────┘
                        │ watch channel
                ┌───────▼───────┐
                │Enrichment Wkr │
                │  enrich_window│
                └───────────────┘
```

所有子系统共享同一个 `TrackerState` 实例，通过 `broadcast::channel` 事件总线通信。

---

- 上一篇：[01-overview.md](../01-overview.md)
- 下一篇：[02-window-monitor.md](./02-window-monitor.md)
- 返回索引：[docs/README.md](../../README.md)
