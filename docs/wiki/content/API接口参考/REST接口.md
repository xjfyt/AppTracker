# REST 接口

<cite>
**本文档引用的文件**
- [tracker-core/src/api/mod.rs](file://tracker-core/src/api/mod.rs)
- [tracker-core/src/models.rs](file://tracker-core/src/models.rs)
</cite>

## 目录

1. [简介](#简介)
2. [健康检查](#健康检查)
3. [快照查询](#快照查询)
4. [截图获取](#截图获取)
5. [暂停控制](#暂停控制)
6. [截图开关](#截图开关)
7. [进程路径显示](#进程路径显示)
8. [桥接 Token](#桥接-token)

## 简介

REST 接口提供状态查询和控制功能，所有响应均为 JSON 格式（截图除外）。

## 健康检查

```
GET /api/v1/health
```

**响应**：

```json
{
  "ok": true,
  "service": "apptracker"
}
```

用于服务发现和端口回退检测。

## 快照查询

```
GET /api/v1/snapshot
```

**响应**（Snapshot）：

```json
{
  "window": {
    "timestamp": 1719532800.0,
    "platform": "win32",
    "app_name": "Code",
    "window_title": "main.rs - AppTracker",
    "window_id": "12345",
    "window_class": "Chrome_WidgetWin_1",
    "geometry": { "x": 100, "y": 200, "width": 1920, "height": 1080, "screen_index": 0 },
    "process": {
      "pid": 6789,
      "name": "Code",
      "executable": "C:\\...\\Code.exe",
      "cmdline": ["Code.exe"],
      "cwd": "C:\\Projects\\AppTracker"
    },
    "document_paths": [
      {
        "path": "C:\\Projects\\AppTracker\\main.rs",
        "kind": "file",
        "source": "uia:name",
        "confidence": 0.75,
        "category": "user"
      }
    ],
    "browser_tab": null,
    "file_manager_state": null,
    "terminal_context": null,
    "extra": {},
    "errors": []
  },
  "activity": {
    "timestamp": 1719532800.0,
    "window_seconds": 60,
    "keys_count": 342,
    "clicks_count": 28,
    "mouse_distance_px": 15234.5,
    "scrolls_count": 12,
    "idle_seconds": 3.2
  },
  "browser_tab": null,
  "has_screenshot": false,
  "paused": false,
  "capture_enabled": false,
  "show_process_paths": false
}
```

### Snapshot 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `window` | WindowInfo? | 当前窗口信息 |
| `activity` | ActivityStats? | 最近 60 秒活动统计 |
| `browser_tab` | BrowserTab? | 最新浏览器标签页 |
| `has_screenshot` | bool | 是否有可用截图 |
| `paused` | bool | 是否暂停 |
| `capture_enabled` | bool | 截图是否启用 |
| `show_process_paths` | bool | 是否显示进程上下文路径 |

## 截图获取

```
GET /api/v1/screenshot
```

**成功响应**：

- Content-Type: `image/png`
- Body: PNG 二进制数据

**失败响应**：

- Status: 404
- Body: `"no screenshot yet"`

前端通过 `<img src="/api/v1/screenshot?t={timestamp}">` 加载截图，时间戳用于缓存失效。

## 暂停控制

### 查询状态

```
GET /api/v1/pause
```

**响应**：

```json
{ "paused": false }
```

### 设置状态

```
POST /api/v1/pause
Content-Type: application/json

{ "paused": true }
```

**响应**：

```json
{ "paused": true }
```

暂停后所有采集任务（窗口监控、活动监听、截图）停止更新状态。

## 截图开关

### 查询状态

```
GET /api/v1/capture
```

**响应**：

```json
{ "enabled": false }
```

### 设置状态

```
POST /api/v1/capture
Content-Type: application/json

{ "enabled": true }
```

**响应**：

```json
{ "enabled": true }
```

关闭截图时会清除已存储的截图数据。

## 进程路径显示

### 查询状态

```
GET /api/v1/show_process_paths
```

**响应**：

```json
{ "enabled": false }
```

### 设置状态

```
POST /api/v1/show_process_paths
Content-Type: application/json

{ "enabled": true }
```

**响应**：

```json
{ "enabled": true }
```

控制前端是否显示 `category: "process"` 的文档路径（cwd、启动目录等）。

## 桥接 Token

```
GET /api/v1/bridge_token
```

**响应**：

```json
{ "token": "base64url_encoded_32_bytes" }
```

返回浏览器扩展鉴权所需的 Token。前端 UI 中显示此 Token 供用户复制到扩展。

**图表来源**
- [tracker-core/src/api/mod.rs:90-331](file://tracker-core/src/api/mod.rs#L90-L331)
- [tracker-core/src/models.rs:195-228](file://tracker-core/src/models.rs#L195-L228)
