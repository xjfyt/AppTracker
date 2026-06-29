# API 接口参考

<cite>
**本文档引用的文件**
- [tracker-core/src/api/mod.rs](file://tracker-core/src/api/mod.rs)
</cite>

## 目录

1. [简介](#简介)
2. [文档导航](#文档导航)
3. [API 总览](#api-总览)
4. [基础信息](#基础信息)

## 简介

AppTracker 在单个端口（默认 5007）上提供 REST、WebSocket 和 SSE 三种 API 接口，供前端 UI、浏览器扩展和外部客户端使用。

## 文档导航

| 文档 | 内容 |
|------|------|
| [REST接口](REST接口.md) | 快照、截图、暂停、截图开关等 |
| [WebSocket与SSE](WebSocket与SSE.md) | 实时事件推送、双向控制 |
| [浏览器扩展协议](浏览器扩展协议.md) | Token 鉴权、tab_update 消息 |

## API 总览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/snapshot` | GET | 获取当前快照 |
| `/api/v1/screenshot` | GET | 获取最新截图 PNG |
| `/api/v1/events` | GET | SSE 事件流 |
| `/api/v1/ws` | GET | WebSocket 事件推送 |
| `/api/v1/browser` | GET | 浏览器扩展 WebSocket |
| `/api/v1/bridge_token` | GET | 获取浏览器桥接 Token |
| `/api/v1/pause` | GET/POST | 查询/设置暂停状态 |
| `/api/v1/capture` | GET/POST | 查询/设置截图开关 |
| `/api/v1/show_process_paths` | GET/POST | 查询/设置进程路径显示 |

## 基础信息

### 绑定地址

默认 `127.0.0.1:5007`，可通过 `AgentConfig` 修改：

```rust
pub struct AgentConfig {
    pub host: String,      // 默认 "127.0.0.1"
    pub api_port: u16,     // 默认 5007
}
```

### 端口回退

端口被占用时自动尝试 5008-5012：

```rust
const PORT_FALLBACK_RANGE: u16 = 5;

async fn bind_with_fallback(host: &str, port: u16) -> anyhow::Result<SocketAddr> {
    for candidate in port..=port.saturating_add(PORT_FALLBACK_RANGE) {
        if TcpListener::bind(addr).await.is_ok() {
            return Ok(addr);
        }
    }
    Err(anyhow!("no free port"))
}
```

### CORS

启用宽松 CORS 策略：

```rust
.layer(CorsLayer::permissive())
```

### 事件类型

所有事件通过 `TrackerEvent` 结构体封装：

```rust
pub struct TrackerEvent {
    pub event_type: String,           // 事件类型
    pub data: Option<serde_json::Value>, // 事件数据
}
```

| 事件类型 | 触发时机 | 数据 |
|---------|---------|------|
| `window_changed` | 前台窗口变化或富化完成 | WindowInfo |
| `activity_updated` | 活动统计更新（每秒） | ActivityStats |
| `browser_tab_updated` | 浏览器标签页更新 | BrowserTab |
| `screenshot_ready` | 新截图就绪 | 无（signal） |
| `paused_changed` | 暂停状态变化 | bool |
| `capture_changed` | 截图开关变化 | bool |
| `show_process_paths_changed` | 进程路径显示变化 | bool |
| `snapshot` | 完整快照（WS 请求触发） | Snapshot |

**图表来源**
- [tracker-core/src/api/mod.rs:71-88](file://tracker-core/src/api/mod.rs#L71-L88)
