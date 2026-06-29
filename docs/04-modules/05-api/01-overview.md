> **对应代码**：`tracker-core/src/api/mod.rs`
> **维护提示**：新增或修改 API 端点时同步更新本文档。

# 二十二、API 总览

## 1、概述

AppTracker 通过 Axum 框架提供统一的 HTTP/WebSocket/SSE API，默认监听 `127.0.0.1:5007`。

## 2、端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/snapshot` | 完整状态快照 |
| GET | `/api/v1/screenshot` | 最新截图（PNG） |
| GET | `/api/v1/events` | SSE 事件流 |
| GET | `/api/v1/ws` | WebSocket 事件流 |
| GET | `/api/v1/browser` | 浏览器扩展 WebSocket 桥接 |
| GET | `/api/v1/bridge_token` | 获取浏览器扩展 token |
| GET | `/api/v1/pause` | 查询暂停状态 |
| POST | `/api/v1/pause` | 设置暂停状态 |
| GET | `/api/v1/capture` | 查询截图开关 |
| POST | `/api/v1/capture` | 设置截图开关 |
| GET | `/api/v1/show_process_paths` | 查询进程路径显示开关 |
| POST | `/api/v1/show_process_paths` | 设置进程路径显示开关 |

## 3、中间件

- **CORS**：`CorsLayer::permissive()`（允许所有跨域请求）
- **Keepalive**：SSE 端点每 25 秒发送 `keepalive` 文本

## 4、端口回退

```rust
const PORT_FALLBACK_RANGE: u16 = 5;
```

从配置端口开始尝试，最多回退 5 个端口。浏览器扩展和桌面 UI 均内置相同的回退扫描逻辑。

## 5、事件类型

通过 WebSocket/SSE 推送的事件类型：

| 事件类型 | 触发时机 | 数据 |
|---------|---------|------|
| `window_changed` | 前台窗口变化或富化完成 | WindowInfo |
| `activity_updated` | 键鼠活动统计更新（每秒） | ActivityStats |
| `browser_tab_updated` | 浏览器扩展上报标签页 | BrowserTab |
| `screenshot_ready` | 新截图可用 | 无（信号事件） |
| `paused_changed` | 暂停状态变化 | bool |
| `capture_changed` | 截图开关变化 | bool |
| `show_process_paths_changed` | 进程路径开关变化 | bool |
| `snapshot` | 客户端请求快照 | Snapshot |
| `ack` | WebSocket 回显 | {"echo": "..."}` |

---

- 上一篇：[04-browser-bridge.md](../04-integrations/04-browser-bridge.md)
- 下一篇：[02-rest.md](./02-rest.md)
- 返回索引：[docs/README.md](../../README.md)
