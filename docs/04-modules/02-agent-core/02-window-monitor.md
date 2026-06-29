> **对应代码**：`tracker-core/src/agent.rs` (`run_window_monitor`, `spawn_window_monitor`)
> **维护提示**：修改轮询间隔、去重逻辑或富化触发条件时同步更新本文档。

# 十、窗口监控

## 1、主循环

`run_window_monitor()` 是 AppTracker 的核心循环，以 250ms 间隔轮询前台窗口：

```rust
async fn run_window_monitor(state: TrackerState, poll_interval_ms: u64) {
    let mut ticker = tokio::time::interval(Duration::from_millis(poll_interval_ms.max(100)));
    ticker.set_missed_tick_behavior(MissedTickBehavior::Skip);
    // ...
    loop {
        ticker.tick().await;
        if state.is_paused() { continue; }
        match active_window().await {
            Ok(mut info) => { /* 处理窗口信息 */ }
            Err(exc) => { /* 记录错误 */ }
        }
    }
}
```

## 2、去重策略

主循环使用两层去重避免不必要的状态更新和富化调用：

### fast_window_identity（快速身份）

```rust
fn fast_window_identity(info: &WindowInfo) -> String {
    format!("{}|{:?}|{:?}",
        info.identity_key(),
        info.file_manager_state,
        info.terminal_context
    )
}
```

包含应用名、窗口 ID、标题、几何信息、文档路径、文件管理器状态、终端上下文。只有当这个值变化时才调用 `state.update_window()`。

### foreground_match_key（富化触发键）

```rust
fn foreground_match_key(info: &WindowInfo) -> String {
    format!("{}|{}|{}",
        info.window_id, pid, info.window_title
    )
}
```

用于判断是否需要重新触发富化。额外考虑 900ms 时间衰减（同一窗口超过 900ms 也会重新富化）。

### window_identity_key（窗口身份键）

```rust
fn window_identity_key(info: &WindowInfo) -> String {
    format!("{}|{}|{}",
        info.window_id, pid, info.app_name
    )
}
```

不含 `window_title`，用于"富化结果是否仍属于同一窗口"的判断。避免 WPS/Office 打字时标题抖动导致富化结果被错判为过期。

## 3、富化触发条件

富化（enrichment）在以下条件之一满足时触发：

1. `foreground_match_key` 变化（窗口切换或标题变化）
2. 距上次富化超过 900ms（周期性刷新）

触发方式：通过 `tokio::sync::watch::channel` 发送给 enrichment worker。

## 4、carry_enrich_only_docs

当窗口标题闪动（WPS 脏标记、页码变化等）导致 `fast_window_identity` 变化时，主循环会从先前的富化结果中"搬运"仅来自富化的文档源（file_manager、terminal、office、uia 等），避免基础轮询覆盖掉富化数据。

```rust
fn is_enrich_only_source(source: &str) -> bool {
    source == "file_manager"
        || source.starts_with("terminal:")
        || source.starts_with("office:")
        || source.starts_with("uia:")
        // ...
}
```

## 5、Enrichment Worker

富化工作在独立的 supervised 任务中运行：

```rust
async fn run_window_enrichment_worker(state, document_memory, mut rx) {
    while rx.changed().await.is_ok() {
        let info = rx.borrow_and_update().clone();
        let mut enriched = enrich_window(info).await;
        apply_document_memory(&document_memory, &mut enriched);
        if should_publish_enriched(&state, &expected_key, &enriched).await {
            state.update_window(enriched).await;
        }
    }
}
```

`should_publish_enriched()` 确保：
- 富化结果仍属于同一窗口（`window_identity_key` 匹配）
- 富化结果确实有变化（`fast_window_identity` 不同）

## 6、supervised 容错

窗口监控和富化 worker 均通过 `supervised()` 包装：

```rust
async fn supervised<F, Fut>(name: &'static str, mut make_fut: F) {
    loop {
        match tokio::spawn(make_fut()).await {
            Ok(()) => return,                    // 正常退出，不重启
            Err(e) if e.is_panic() => {
                // panic → 等 2 秒后重启
                tokio::time::sleep(Duration::from_secs(2)).await;
            }
            Err(_) => return,                    // 取消，不重启
        }
    }
}
```

---

- 上一篇：[01-overview.md](./01-overview.md)
- 下一篇：[03-document-memory.md](./03-document-memory.md)
- 返回索引：[docs/README.md](../../README.md)
