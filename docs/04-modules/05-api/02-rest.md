> **对应代码**：`tracker-core/src/api/mod.rs`
> **维护提示**：新增 REST 端点或修改请求/响应格式时同步更新本文档。

# 二十三、REST API

## 1、健康检查

### GET /api/v1/health

**响应**：
```json
{"ok": true, "service": "apptracker"}
```

用于浏览器扩展和桌面 UI 的端口发现。

## 2、状态快照

### GET /api/v1/snapshot

**响应**（Snapshot）：
```json
{
    "window": { "app_name": "...", "window_title": "...", ... },
    "activity": { "keys_count": 42, "clicks_count": 10, ... },
    "browser_tab": { "browser": "chrome", "url": "...", ... },
    "has_screenshot": true,
    "paused": false,
    "capture_enabled": false,
    "show_process_paths": false
}
```

一次性返回所有当前状态，适合初始加载。

## 3、截图

### GET /api/v1/screenshot

**成功响应**：`200 OK`，`Content-Type: image/png`，Body 为 PNG 二进制

**无截图响应**：`404 Not Found`，Body 为 `"no screenshot yet"`

## 4、暂停控制

### GET /api/v1/pause

**响应**：
```json
{"paused": false}
```

### POST /api/v1/pause

**请求体**：
```json
{"paused": true}
```

**响应**：
```json
{"paused": true}
```

## 5、截图开关

### GET /api/v1/capture

**响应**：
```json
{"enabled": false}
```

### POST /api/v1/capture

**请求体**：
```json
{"enabled": true}
```

**响应**：
```json
{"enabled": true}
```

关闭截图时自动清除内存中的最新截图。

## 6、进程路径显示

### GET /api/v1/show_process_paths

**响应**：
```json
{"enabled": false}
```

### POST /api/v1/show_process_paths

**请求体**：
```json
{"enabled": true}
```

**响应**：
```json
{"enabled": true}
```

## 7、浏览器扩展 Token

### GET /api/v1/bridge_token

**响应**：
```json
{"token": "base64url-encoded-token"}
```

---

- 上一篇：[01-overview.md](./01-overview.md)
- 下一篇：[03-websocket-sse.md](./03-websocket-sse.md)
- 返回索引：[docs/README.md](../../README.md)
