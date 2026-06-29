> **对应代码**：`tracker-core/src/api/mod.rs`
> **维护提示**：修改 WebSocket/SSE 协议或事件格式时同步更新本文档。

# 二十四、WebSocket 与 SSE

## 1、WebSocket（/api/v1/ws）

### 连接

```
ws://127.0.0.1:5007/api/v1/ws
```

### 服务端推送事件

连接后自动接收所有 TrackerEvent：

```json
{"type": "window_changed", "data": {...WindowInfo...}}
{"type": "activity_updated", "data": {...ActivityStats...}}
{"type": "browser_tab_updated", "data": {...BrowserTab...}}
{"type": "screenshot_ready", "data": null}
{"type": "paused_changed", "data": true}
```

### 客户端命令

| 命令 | 说明 |
|------|------|
| `"snapshot"` | 请求完整状态快照（响应 `snapshot` 事件） |
| `"pause"` | 暂停采集 |
| `"resume"` | 恢复采集 |
| 其他文本 | 回显为 `ack` 事件 |

### 错误处理

- `Lagged` → 跳过（不推送给客户端）
- `Closed` → 断开连接

## 2、SSE（/api/v1/events）

### 连接

```
GET /api/v1/events
Accept: text/event-stream
```

### 事件格式

```
event: window_changed
data: {"type":"window_changed","data":{...}}

event: activity_updated
data: {"type":"activity_updated","data":{...}}

: keepalive
```

### Keepalive

每 25 秒发送 `: keepalive` 注释行，防止代理/负载均衡器断开空闲连接。

## 3、事件结构

```rust
pub struct TrackerEvent {
    pub event_type: String,           // "window_changed" 等
    pub data: Option<serde_json::Value>, // 事件数据（信号事件为 null）
}
```

### 信号事件

`screenshot_ready` 等信号事件不含数据，客户端收到后应主动请求 `/api/v1/screenshot`。

## 4、客户端选择

| 方式 | 适用场景 | 方向 |
|------|---------|------|
| WebSocket | 桌面 UI、需要双向通信 | 双向 |
| SSE | 只需接收事件的轻量客户端 | 单向（服务端→客户端） |
| REST | 一次性查询、开关控制 | 请求-响应 |

---

- 上一篇：[02-rest.md](./02-rest.md)
- 下一篇：[04-browser-protocol.md](./04-browser-protocol.md)
- 返回索引：[docs/README.md](../../README.md)
