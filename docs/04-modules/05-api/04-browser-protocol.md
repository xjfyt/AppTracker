> **对应代码**：`tracker-core/src/api/mod.rs` (`browser_ws`, `browser_client`), `browser_extension/background.js`
> **维护提示**：修改浏览器扩展 WebSocket 协议时同步更新本文档。

# 二十五、浏览器扩展协议

## 1、WebSocket 端点

```
ws://127.0.0.1:5007/api/v1/browser
```

## 2、握手流程

```
扩展                              AppTracker API
 │                                    │
 │──── WebSocket 连接 ───────────────→│
 │                                    │
 │──── {"token": "base64..."} ──────→│  鉴权
 │                                    │  验证 token
 │                                    │
 │──── {"type":"tab_update",...} ───→│  Tab 更新
 │──── {"type":"tab_update",...} ───→│  Tab 更新
 │                                    │
 │◄─── 连接关闭（token 无效） ────────│  或保持连接
```

## 3、鉴权

连接后第一条消息必须为 JSON 格式的 token：

```json
{"token": "base64url-encoded-32-bytes"}
```

Token 不匹配时服务端立即关闭连接。

## 4、Tab 更新消息

```json
{
    "type": "tab_update",
    "browser": "chrome",
    "pid": 12345,
    "windowId": 1,
    "tabId": 42,
    "url": "https://example.com/page",
    "title": "Example Page",
    "favIconUrl": "https://example.com/favicon.ico",
    "active": true
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 必须为 `"tab_update"` |
| `browser` | string | 否 | 浏览器类型，默认 `"chrome"` |
| `pid` | number | 否 | 浏览器进程 PID |
| `windowId` | number | 否 | 浏览器窗口 ID |
| `tabId` | number | 否 | 标签页 ID |
| `url` | string | 否 | 标签页 URL |
| `title` | string | 否 | 标签页标题 |
| `favIconUrl` | string | 否 | 图标 URL |
| `active` | boolean | 否 | 是否为活跃标签，默认 true |

## 5、暂停行为

当 AppTracker 处于暂停状态时，浏览器扩展的消息会被静默忽略（`continue`）。

## 6、自动重连

浏览器扩展内置重连机制：

- 断开后指数退避（1s → 2s → 4s → ... → 30s）
- 每 30 秒 keepalive alarm 检查连接
- 端口回退扫描 5007-5012

---

- 上一篇：[03-websocket-sse.md](./03-websocket-sse.md)
- 下一篇：[01-overview.md](../06-ui/01-overview.md)
- 返回索引：[docs/README.md](../../README.md)
