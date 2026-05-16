# tracker-core 内部结构

## 入口：`start_agent`

[`tracker-core/src/agent.rs`](../tracker-core/src/agent.rs) 内 `start_agent(config)` 拉起所有后台任务：

```rust
let state = TrackerState::new();
let (token_path, token) = bridge::load_or_create_token().await?;
spawn_api(state.clone(), host, api_port, Arc::new(token), token_path); // REST/WS + browser
if !config.no_activity { spawn_activity_monitor(...); }
if !config.no_capture {
    state.set_capture_enabled(config.capture_default_on); // 默认 false
    spawn_screen_capture(state.clone());
}
spawn_window_monitor(state.clone(), config.poll_interval_ms);
```

`AgentConfig` 默认值见 `agent.rs::AgentConfig::default`：API 5007（同时承载浏览器桥），poll 250 ms，`capture_default_on=false`。整个 agent 只暴露一个端口，浏览器扩展、UI、第三方共用。

## 窗口轮询

`spawn_window_monitor` 是一个 `tokio::time::interval`：

1. 跳过 `is_paused()` 状态。
2. 调 `active_window().await` 拿到当前前台窗口（平台分支详见 [platform.md](./platform.md)）。
3. 用 `apply_document_memory` 把"标题里的纯文件名"回填为绝对路径。
4. `fast_window_identity` 做轻量去重 key，识别变化才写 `state.update_window`。
5. 写入前调 `carry_enrich_only_docs`：如果新一帧和上一帧是「同一个窗口」（window_id + pid + app_name 相同），就把先前富化得到的 `office:*` / `uia:*` / `file_manager*` / `terminal:*` 数据原样带过来。这样 WPS / Notepad 打字、翻页造成的标题闪动不会把已经探测好的文档路径冲掉。
6. 富化任务通过 `tokio::sync::watch` 单坑队列异步触发——只关心"最新的一帧"。
7. 富化 worker 调 `enrich_window` 拉文件管理器/终端/平台扩展。`should_publish_enriched` 只检查"窗口身份"（不含 title），避免 COM/UIA 还在跑的 ~1s 内 title 改了就被错判为过期。

## 文档记忆 `DocumentMemory`

为了让"用 Office 看一个文件之后，切到另一个标题只剩文件名的窗口也能找回路径"，`DocumentMemory` 保存：

- 按进程键存：`<pid>:<exe>` → `{ normalized_basename → absolute_path }`
- 全局：`normalized_basename → absolute_path`

`apply` 流程：
1. `remember`：把当前窗口里所有"绝对路径 + 文件存在 + kind=file"的文档登记。
2. `resolve_title_filename`：如果 `window_title` 看起来只是个文件名，就尝试用进程记忆/全局记忆补回路径，置信度 0.88，source `title_memory`。
3. 最后 `dedupe_documents` 去重。

## 状态与事件 `TrackerState`

[`state.rs`](../tracker-core/src/state.rs) 是所有共享状态的 owner：

- `Arc<RwLock<InnerState>>`：当前 window / activity / browser_tab / 最新截图 PNG。
- `broadcast::Sender<TrackerEvent>`：事件总线，所有写操作都会发一条事件。
- `paused: AtomicBool`、`capture_enabled: AtomicBool`：原子开关。
- 关键方法：
  - `update_window` → `window_changed`
  - `update_activity` → `activity_updated`
  - `update_browser_tab` → `browser_tab_updated`
  - `update_screenshot` → `screenshot_ready`
  - `set_paused` / `set_capture_enabled` → `paused_changed` / `capture_changed`
  - `clear_screenshot`：关闭截图时立即丢掉缓存的 PNG，避免遗留旧图。

## 活动统计

`activity.rs`（feature `activity`）用 60s 窗口聚合：按键、点击、滚动次数；累计鼠标距离；空闲秒数。每秒/事件触发都会通过 `state.update_activity` 推送。
