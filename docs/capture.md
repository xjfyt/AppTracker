# 截图功能

实现：[`tracker-core/src/capture.rs`](../tracker-core/src/capture.rs)。

## 设计要点

- **默认关闭**。`AgentConfig::default()` 里 `capture_default_on=false`；`spawn_screen_capture` 始终在 agent 启动时被拉起（除非 `--no-capture`），但只有 `state.is_capture_enabled() && !state.is_paused()` 时才真正截屏。
- **2 秒 tick**：`tokio::time::interval(Duration::from_secs(2))`，错过 tick 直接跳过。
- **范围**：优先按当前窗口的 geometry 截，落到 4096 内防极端值；拿不到 geometry 时退回主屏全屏。
- **降采样**：`MAX_THUMB_SIZE=480`，超过时用 `image::DynamicImage::thumbnail`，控制传输体积。
- **编码**：转 PNG，存到 `InnerState.latest_screenshot_png`，发 `screenshot_ready` 事件让 UI 主动拉。

## 切换流程

```
UI 勾选「截图」┐
              ▼
POST /api/v1/capture {"enabled": true}
              ▼
state.set_capture_enabled(true)
              ▼
broadcast "capture_changed: true"
              ▼
capture loop 下一个 tick 触发抓图
              ▼
broadcast "screenshot_ready" → UI 拉 /api/v1/screenshot
```

关闭时：`state.set_capture_enabled(false)` + `state.clear_screenshot()`，确保下一帧前已经没有残留图。

## UI 端交互

- 顶栏开关绑定 `change` 事件，发 POST 后立即调用 `applyCaptureState` 同步 UI；同时监听 `capture_changed` 事件，保证其它客户端切换时这边也跟着改。
- 关闭时清掉 `<img src>` + 增加 `hidden` class，避免长尾旧图。
- 双击 `<img>` 触发 lightbox：复制 `src` 到全屏覆盖层，按 `Esc` 或点击背景关闭。
