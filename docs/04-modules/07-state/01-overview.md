> **对应代码**：`tracker-core/src/state.rs`, `tracker-core/src/models.rs`
> **维护提示**：修改 TrackerState 或数据模型时同步更新本文档。

# 二十七、状态管理

## 1、TrackerState

`TrackerState` 是 AppTracker 的核心状态容器，线程安全，支持并发读写和事件广播。

```rust
pub struct TrackerState {
    inner: Arc<RwLock<InnerState>>,     // 读写锁保护的状态
    tx: broadcast::Sender<TrackerEvent>, // 事件广播发送端
    paused: Arc<AtomicBool>,            // 暂停标志
    capture_enabled: Arc<AtomicBool>,   // 截图开关
    show_process_paths: Arc<AtomicBool>, // 进程路径显示开关
}
```

## 2、InnerState

```rust
struct InnerState {
    window: Option<WindowInfo>,              // 当前窗口信息
    activity: Option<ActivityStats>,         // 活动统计
    browser_tab: Option<BrowserTab>,         // 浏览器标签页
    latest_screenshot_png: Option<Vec<u8>>,  // 最新截图 PNG
}
```

## 3、原子开关

三个开关使用 `AtomicBool`，读写无需加锁：

| 开关 | 默认值 | 事件 |
|------|--------|------|
| `paused` | false | `paused_changed` |
| `capture_enabled` | false | `capture_changed` |
| `show_process_paths` | false | `show_process_paths_changed` |

设置开关时自动广播对应事件。

## 4、事件广播

```rust
pub fn subscribe(&self) -> broadcast::Receiver<TrackerEvent>
```

- Channel 容量：256
- Lagged 时跳过（不阻塞）
- Closed 时断开

## 5、更新方法

| 方法 | 事件 | 说明 |
|------|------|------|
| `update_window(info)` | `window_changed` | 更新当前窗口信息 |
| `update_activity(stats)` | `activity_updated` | 更新活动统计 |
| `update_browser_tab(tab)` | `browser_tab_updated` | 更新浏览器标签（同时更新窗口内的 browser_tab） |
| `update_screenshot(png)` | `screenshot_ready` | 更新截图（信号事件） |
| `clear_screenshot()` | 无 | 清除截图（关闭截图开关时调用） |

## 6、快照

```rust
pub async fn snapshot(&self) -> Snapshot
```

一次性读取所有状态，返回 `Snapshot` 结构体：

```rust
pub struct Snapshot {
    pub window: Option<WindowInfo>,
    pub activity: Option<ActivityStats>,
    pub browser_tab: Option<BrowserTab>,
    pub has_screenshot: bool,         // 是否有截图（不返回 PNG 数据）
    pub paused: bool,
    pub capture_enabled: bool,
    pub show_process_paths: bool,
}
```

## 7、浏览器标签联动

`update_browser_tab()` 会同时检查当前窗口是否为浏览器，若是则同步更新 `window.browser_tab`：

```rust
if looks_like_browser(executable, Some(&window.app_name)) {
    window.browser_tab = Some(tab.clone());
}
```

## 8、数据模型

### WindowInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | f64 | 采集时间戳 |
| `platform` | String | 平台标识 |
| `app_name` | String | 应用名 |
| `app_bundle_id` | Option | macOS bundle ID |
| `window_title` | String | 窗口标题 |
| `window_id` | Option | 窗口标识（HWND/xprop ID） |
| `window_class` | Option | 窗口类名 |
| `geometry` | Option | 窗口位置和尺寸 |
| `process` | Option | 进程信息 |
| `document_paths` | Vec | 文档路径列表 |
| `browser_tab` | Option | 浏览器标签页 |
| `file_manager_state` | Option | 文件管理器状态 |
| `terminal_context` | Option | 终端上下文 |
| `extra` | Value | 扩展字段 |
| `errors` | Vec | 错误信息 |

### DocumentSource

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | String | 文件/目录路径 |
| `kind` | String | "file" / "folder" / "unknown" |
| `source` | String | 来源标识 |
| `confidence` | f32 | 置信度（0.0-1.0） |
| `category` | DocumentCategory | User / Process |

---

- 上一篇：[01-overview.md](../06-ui/01-overview.md)
- 下一篇：[01-coding-standards.md](../../05-maintenance/01-coding-standards.md)
- 返回索引：[docs/README.md](../../README.md)
