# WebSocket 与 SSE

<cite>
**本文档引用的文件**
- [tracker-core/src/api/mod.rs](file://tracker-core/src/api/mod.rs)
</cite>

## 目录

1. [简介](#简介)
2. [WebSocket 接口](#websocket-接口)
3. [SSE 接口](#sse-接口)
4. [事件格式](#事件格式)
5. [客户端实现示例](#客户端实现示例)

## 简介

AppTracker 提供 WebSocket 和 SSE 两种实时事件推送机制。WebSocket 支持双向通信（可发送控制命令），SSE 仅支持服务器到客户端的单向推送。

## WebSocket 接口

### 连接端点

```
ws://127.0.0.1:5007/api/v1/ws
```

### 服务器推送事件

连接建立后，服务器自动推送所有状态变更事件：

```json
{"type": "window_changed", "data": {...}}
{"type": "activity_updated", "data": {...}}
{"type": "browser_tab_updated", "data": {...}}
{"type": "screenshot_ready"}
{"type": "paused_changed", "data": true}
{"type": "capture_changed", "data": false}
```

### 客户端命令

客户端可发送文本消息控制 AppTracker：

| 命令 | 响应 |
|------|------|
| `"snapshot"` | 返回 `{"type": "snapshot", "data": {...}}` |
| `"pause"` | 设置暂停，返回 `paused_changed` 事件 |
| `"resume"` | 恢复运行，返回 `paused_changed` 事件 |
| 其他文本 | 返回 `{"type": "ack", "data": {"echo": "..."}}` |

### 实现细节

```rust
async fn ws_client(mut socket: WebSocket, state: TrackerState) {
    let mut rx = state.subscribe();
    loop {
        tokio::select! {
            event = rx.recv() => {
                // 推送事件到客户端
                send_json(&mut socket, &event).await;
            }
            incoming = socket.next() => {
                match incoming {
                    Some(Ok(Message::Text(text))) => {
                        match text.as_str() {
                            "snapshot" => { /* 发送快照 */ }
                            "pause" => { state.set_paused(true); }
                            "resume" => { state.set_paused(false); }
                            _ => { /* 返回 ack */ }
                        }
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
        }
    }
}
```

### Lagged 处理

当客户端处理速度跟不上事件产生速度时，broadcast channel 会产生 `Lagged` 错误。WebSocket 客户端跳过 lagged 事件继续接收：

```rust
Err(broadcast::error::RecvError::Lagged(_)) => continue,
```

## SSE 接口

### 连接端点

```
GET /api/v1/events
```

**响应头**：

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

### 事件格式

```
event: window_changed
data: {"type":"window_changed","data":{...}}

event: activity_updated
data: {"type":"activity_updated","data":{...}}

event: keepalive
data:
```

### Keep-Alive

SSE 连接每 25 秒发送一次 keepalive 消息，防止代理/防火墙超时断开：

```rust
Sse::new(events).keep_alive(
    KeepAlive::new()
        .interval(Duration::from_secs(25))
        .text("keepalive"),
)
```

### 实现细节

```rust
async fn events_sse(State(state): State<ApiState>)
    -> Sse<impl Stream<Item = Result<Event, Infallible>>>
{
    let mut rx = state.tracker.subscribe();
    let events = stream! {
        loop {
            match rx.recv().await {
                Ok(event) => {
                    let sse = Event::default()
                        .event(event.event_type.clone())
                        .data(serde_json::to_string(&event)?);
                    yield Ok(sse);
                }
                Err(RecvError::Lagged(skipped)) => {
                    tracing::warn!(skipped, "SSE client lagged behind");
                }
                Err(RecvError::Closed) => break,
            }
        }
    };
    Sse::new(events).keep_alive(...)
}
```

## 事件格式

### TrackerEvent 结构

```json
{
  "type": "window_changed",
  "data": { ... }
}
```

### 各事件数据类型

| 事件 | data 类型 | 说明 |
|------|----------|------|
| `window_changed` | WindowInfo | 窗口信息（含文档、终端、文件管理器） |
| `activity_updated` | ActivityStats | 活动统计 |
| `browser_tab_updated` | BrowserTab | 浏览器标签页 |
| `screenshot_ready` | null | 信号事件，无数据 |
| `paused_changed` | boolean | 暂停状态 |
| `capture_changed` | boolean | 截图开关 |
| `show_process_paths_changed` | boolean | 进程路径显示 |
| `snapshot` | Snapshot | 完整快照 |

## 客户端实现示例

### JavaScript WebSocket

```javascript
const ws = new WebSocket('ws://127.0.0.1:5007/api/v1/ws');

ws.onopen = () => {
    console.log('Connected');
    ws.send('snapshot'); // 请求初始快照
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    switch (msg.type) {
        case 'window_changed':
            console.log('Window:', msg.data.app_name, msg.data.window_title);
            break;
        case 'activity_updated':
            console.log('Keys:', msg.data.keys_count, 'Clicks:', msg.data.clicks_count);
            break;
        case 'screenshot_ready':
            document.getElementById('screenshot').src =
                `/api/v1/screenshot?t=${Date.now()}`;
            break;
    }
};

ws.onclose = () => {
    console.log('Disconnected, reconnecting...');
    setTimeout(() => { /* 重连逻辑 */ }, 1000);
};
```

### JavaScript SSE

```javascript
const source = new EventSource('http://127.0.0.1:5007/api/v1/events');

source.addEventListener('window_changed', (e) => {
    const data = JSON.parse(e.data);
    console.log('Window changed:', data.data.app_name);
});

source.addEventListener('activity_updated', (e) => {
    const data = JSON.parse(e.data);
    console.log('Activity:', data.data.keys_count, 'keys');
});

source.onerror = () => {
    console.log('SSE error, browser will auto-reconnect');
};
```

### 选择建议

| 场景 | 推荐 |
|------|------|
| 需要发送控制命令 | WebSocket |
| 仅接收事件 | SSE（更简单，自动重连） |
| 浏览器扩展 | WebSocket（专用端点） |

**图表来源**
- [tracker-core/src/api/mod.rs:109-191](file://tracker-core/src/api/mod.rs#L109-L191)
