# 总体架构

AppTracker 由一个 Rust 采集核 + 多个轻量前端组成。核心运行在本地，前端只消费 API。**整个 app 只暴露一个端口**（默认 5007），浏览器扩展、Tauri UI、第三方调用方都走它。

## 进程拓扑

```
┌────────────────────────┐        ┌──────────────────────┐
│ AppTracker Desktop     │  HTTP  │ tracker-core (Rust)  │
│ (Tauri shell + UI)     │◀──────▶│ ─ 窗口轮询           │
└────────────────────────┘   WS   │ ─ 文档记忆 / 富化     │
                                  │ ─ 活动统计           │
┌────────────────────────┐  WS    │ ─ 截图（可关）       │
│ Browser Extension      │◀──────▶│ ─ 集成（FM/终端）    │
└────────────────────────┘ /api/* │ ─ 单端口 API/WS/SSE   │
                                  └──────────┬───────────┘
┌────────────────────────┐                   │
│ Shell hook (cd 追踪)   │ 写本地 cwd 文件 ───┘
└────────────────────────┘
```

只有一个二进制 (`apptracker.exe`，Tauri 进程) 在跑，里面同时托管：
- 窗口轮询 / 文档富化 / 活动统计 / 可选截图
- API（HTTP/WS/SSE）
- 浏览器扩展鉴权 + WS 端点 `/api/v1/browser`

## 关键 crate / 目录

```
crates/tracker-core/src
├── activity.rs        全局键鼠 / 滚动 / idle 统计
├── agent.rs           启动入口、窗口轮询、文档记忆
├── api/mod.rs         axum 路由（REST/WS/SSE，含 browser 桥）
├── bridge.rs          浏览器扩展 token 的读取 / 生成 / 迁移
├── capture.rs         截图任务（受开关 + pause 双重控制）
├── integrations/      文件管理器、终端、shell cwd
├── platform/          Windows / macOS / Linux 采集
├── models.rs          DocumentSource/Category 等线序列化结构
└── state.rs           共享状态 + 事件广播
```

`crates/tracker-agent` 已被移除——所有运行入口收敛到 Tauri 桌面端。

## 数据流

1. `spawn_window_monitor` 250 ms 轮询前台窗口，落到 `state.window`。
2. 同一帧推到 `enrich_window`：补 file manager、终端上下文、Office/WPS 文档路径。
3. 富化后的 `document_paths` 经两步过滤：
   - 给每条记录打上 `category: user|process`；
   - 整体丢掉落在「当前进程可执行文件所在目录」里的路径——专治"C:/Program Files/X"这种安装目录噪声。
4. 富化结果对比 `should_publish_enriched`，确认仍是同一窗口才再次写状态。
5. `state` 的每次写都通过 `broadcast::Sender<TrackerEvent>` 发出，UI / SSE / WS 都拿得到。
6. UI 默认只展示 `category=user`，通过 toggle 可同时显示 `category=process`。

## 三个独立开关

- **paused**：全局闸门，会让窗口轮询、活动统计、截图全部停下。
- **capture_enabled**：截图任务受不受控；默认关闭，关闭时立刻丢弃缓存图。
- **show_process_paths**：cwd / 启动目录类路径是否在 UI 上可见；默认关闭。
