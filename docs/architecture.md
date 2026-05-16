# 总体架构

AppTracker 由一个 Rust 采集核 + 多个轻量前端组成。核心运行在本地，前端只消费 API。

## 进程拓扑

```
┌────────────────────────┐        ┌──────────────────────┐
│ AppTracker Desktop     │  HTTP  │ tracker-core (Rust)  │
│ (Tauri shell + UI)     │◀──────▶│ ─ 窗口轮询           │
└────────────────────────┘   WS   │ ─ 文档记忆 / 富化     │
                                  │ ─ 活动统计           │
┌────────────────────────┐  WS    │ ─ 截图（可关）       │
│ Browser Extension      │◀──────▶│ ─ 集成（FM/终端）    │
└────────────────────────┘   /api │ ─ 浏览器桥           │
                                  └──────────┬───────────┘
┌────────────────────────┐                   │
│ Shell hook (cd 追踪)   │ 写本地 cwd 文件 ───┘
└────────────────────────┘
```

- `tracker-core`：库 crate，所有核心逻辑都在这里。
- `tracker-agent`：可独立运行的 headless CLI，包一层 `clap`。
- `desktop/src-tauri`：把 `tracker-core` 作为 in-process 嵌入，UI 走本地 HTTP/WS（端口 5007）。
- `browser_extension/`：MV3 扩展，通过 WS（端口 5006）发活动 Tab。
- `shell_integration/`：把 PowerShell/CMD 的 `cd` 写入本地 cwd 文件，供 `terminal` 集成回读。

## 关键 crate / 目录

```
crates/tracker-core/src
├── activity.rs        全局键鼠 / 滚动 / idle 统计
├── agent.rs           启动入口、窗口轮询、文档记忆
├── api/mod.rs         axum 路由（REST/WS/SSE）
├── bridge.rs          浏览器扩展 WS 桥（鉴权 token）
├── capture.rs         截图任务（受开关 + pause 双重控制）
├── integrations/      文件管理器、终端、shell cwd
├── platform/          Windows / macOS / Linux 采集
├── models.rs          线序列化结构
└── state.rs           共享状态 + 事件广播
```

## 数据流

1. `spawn_window_monitor` 250ms 轮询前台窗口，落到 `state.window`。
2. 同样的 info 推到 `enrich_window`：补 file manager、终端上下文、Office/WPS 文档路径。
3. 富化结果对比 `should_publish_enriched`，确认仍是同一窗口才再次写状态。
4. `state` 的每次写都通过 `broadcast::Sender<TrackerEvent>` 发出，被 SSE/WS 客户端转发。
5. UI 收到事件后做局部渲染（带 HTML 缓存避免重绘抖动）。

## 暂停与截图开关的关系

- **暂停（pause）**：全局闸门，会让窗口轮询、活动统计、截图全部停下。
- **截图开关（capture）**：只控制 `capture.rs`。默认关闭，可由 UI / `POST /api/v1/capture` 切换。关闭时立即清空 `latest_screenshot_png`，UI 端隐藏图像。
