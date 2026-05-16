# 本地 API

所有 HTTP 端口默认在 `127.0.0.1:5007`（被占用时向后顺延 5 个端口）。

## REST

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 健康检查，返回 `{ok, service:"apptracker"}` |
| GET | `/api/v1/snapshot` | 一次性快照 |
| GET | `/api/v1/screenshot` | 最新截图 PNG（无图时 404） |
| GET | `/api/v1/pause` | 查询暂停状态 |
| POST | `/api/v1/pause` | `{"paused": bool}` 切换暂停 |
| GET | `/api/v1/capture` | 查询截图开关 |
| POST | `/api/v1/capture` | `{"enabled": bool}` 切换截图（关闭会立即清空缓存图） |

## Snapshot 结构

```jsonc
{
  "window": WindowInfo | null,
  "activity": ActivityStats | null,
  "browser_tab": BrowserTab | null,
  "has_screenshot": false,
  "paused": false,
  "capture_enabled": false
}
```

`WindowInfo` 包含：基础元数据、`process`、`document_paths`（含 source + 置信度）、`file_manager_state`、`terminal_context`、`browser_tab`。完整字段见 [`models.rs`](../crates/tracker-core/src/models.rs)。

## WebSocket

- 路径：`/api/v1/ws`
- 客户端发送的 text 帧：
  - `snapshot`：服务端回一条 `{type:"snapshot", data: Snapshot}`
  - `pause` / `resume`：切换暂停（同 POST `/pause`）
- 服务端事件：
  - `window_changed` — `WindowInfo`
  - `activity_updated` — `ActivityStats`
  - `browser_tab_updated` — `BrowserTab`
  - `screenshot_ready` — 信号事件（无 data），UI 收到后请求 `/screenshot`
  - `paused_changed` — `bool`
  - `capture_changed` — `bool`

## SSE

`/api/v1/events`：把 WebSocket 上的事件以 `event:` + `data:` 格式推送。25s keep-alive。

## 浏览器桥

`spawn_browser_bridge` 默认监听 5006，使用 `bridge.token`（首次启动写入 `~/.config/apptracker/bridge.token`，仅 owner 可读）做 Bearer 鉴权。扩展握手成功后定时上报当前 Tab → `state.update_browser_tab`。
