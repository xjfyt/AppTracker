> **对应代码**：`tracker-core/src/activity.rs`, `tracker-core/src/capture.rs`
> **维护提示**：修改活动统计窗口大小或截图参数时同步更新本文档。

# 十三、活动监控与截图采集

## 1、活动监控（activity.rs）

### 概述

活动监控通过 `rdev::listen` 全局监听键盘和鼠标事件，维护 60 秒滑动窗口统计。

### 架构

```
OS 全局事件
     │
     ▼
rdev::listen (独立 OS 线程)
     │ callback
     ▼
ActivityCounters (Arc<Mutex>)
     │ events: VecDeque<(Instant, &str)>
     │ mouse_moves: VecDeque<(Instant, f64)>
     │ last_input: Instant
     │
     ▼ 每 1 秒聚合
tokio 统计任务
     │
     ▼
ActivityStats → TrackerState
```

### 事件类型

| rdev 事件 | 统计字段 | 说明 |
|-----------|---------|------|
| `KeyPress` | `keys_count` | 按键次数 |
| `ButtonPress` | `clicks_count` | 鼠标点击次数 |
| `Wheel` | `scrolls_count` | 滚动次数 |
| `MouseMove` | `mouse_distance_px` | 鼠标移动距离（欧几里得距离累积） |

### ActivityStats 结构

```rust
pub struct ActivityStats {
    pub timestamp: f64,           // 采集时间戳
    pub window_seconds: u64,      // 统计窗口大小（默认 60 秒）
    pub keys_count: u64,          // 按键次数
    pub clicks_count: u64,        // 点击次数
    pub mouse_distance_px: f64,   // 鼠标移动距离（像素）
    pub scrolls_count: u64,       // 滚动次数
    pub idle_seconds: f64,        // 距上次输入的空闲秒数
}
```

### 滑动窗口

统计任务每秒执行一次：

1. 清除超过 `window_seconds`（60s）的旧事件
2. 分类统计各事件类型
3. 计算鼠标移动总距离
4. 计算空闲时长（`last_input.elapsed()`）
5. 发送到 TrackerState（除非 paused）

### Feature 控制

`activity` feature 禁用时，`spawn_activity_monitor()` 变为空操作。

## 2、截图采集（capture.rs）

### 概述

截图采集每 2 秒截取前台窗口，下采样至 480px，编码为 PNG 存入内存。

### 流程

```
每 2 秒
  │
  ├─ 检查 paused / capture_enabled
  │
  ├─ 获取当前窗口 geometry
  │
  ├─ spawn_blocking (阻塞线程):
  │    ├─ 有 geometry → Screen::from_point(x,y).capture_area(x,y,w,h)
  │    └─ 无 geometry → Screen::all().first().capture()
  │
  ├─ image::DynamicImage::thumbnail(480, 480)  // 下采样
  │
  ├─ PngEncoder 编码
  │
  └─ state.update_screenshot(png)              // 存入内存 + 广播事件
```

### 截图参数

| 参数 | 值 | 说明 |
|------|------|------|
| 采集间隔 | 2 秒 | `tokio::time::interval(Duration::from_secs(2))` |
| 最大缩略图尺寸 | 480px | `MAX_THUMB_SIZE` 常量 |
| 最大窗口尺寸 | 4096px | 防止异常窗口尺寸 |
| 编码格式 | PNG | `image::codecs::png::PngEncoder` |
| 存储位置 | 内存 | `TrackerState.inner.latest_screenshot_png` |

### 截图 API

截图通过 `GET /api/v1/screenshot` 获取，返回 PNG 二进制流。前端通过 `screenshot_ready` 事件通知刷新。

### Feature 控制

`capture` feature 禁用时，`spawn_screen_capture()` 变为空操作。

---

- 上一篇：[04-enrichment-pipeline.md](./04-enrichment-pipeline.md)
- 下一篇：[01-overview.md](../03-platform/01-overview.md)
- 返回索引：[docs/README.md](../../README.md)
