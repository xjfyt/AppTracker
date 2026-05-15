# API 参考

Active Tracker 启动时默认在 `http://127.0.0.1:5007` 暴露 HTTP/SSE/WebSocket 服务，让其他客户端读取实时状态。

> 三种协议并存，看场景挑：
> - **REST** — 一次性查 snapshot/screenshot
> - **SSE** — 浏览器原生 EventSource 一行代码消费，单向推送
> - **WebSocket** — 长连场景（IDE 守护进程、桌面助手等），自带 30 s 心跳，中间代理静默不易切断

启动参数：

```bash
uv run main.py                              # 默认 5007
uv run main.py --api-port 8080              # 改端口
uv run main.py --api-host 0.0.0.0           # 监听所有网卡（谨慎，没鉴权）
uv run main.py --no-api                     # 完全关掉
```

## 路由速查

| 方法 | 路径 | 用途 | Content-Type |
|------|------|------|----------------|
| GET | `/api/v1/health` | 健康检查 | application/json |
| GET | `/api/v1/snapshot` | 当前所有状态 | application/json |
| GET | `/api/v1/screenshot` | 最新焦点窗口截图 | image/png |
| GET | `/api/v1/events` | SSE 事件流 | text/event-stream |
| WS  | `/api/v1/ws` | WebSocket 事件流 | - |

## REST

### `GET /api/v1/health`

```json
{ "ok": true, "service": "active-tracker" }
```

### `GET /api/v1/snapshot`

```json
{
  "window": {
    "timestamp": 1747345678.12,
    "platform": "darwin",
    "app_name": "Visual Studio Code",
    "app_bundle_id": "com.microsoft.VSCode",
    "window_title": "main.py — active_tracker",
    "window_id": null,
    "window_class": "AXStandardWindow",
    "geometry": { "x": 120, "y": 80, "width": 1200, "height": 800, "screen_index": 0 },
    "process": { "pid": 84421, "name": "Code Helper", "executable": "...", "cmdline": [...], "cwd": "..." },
    "document_paths": [ { "path": "...", "kind": "file", "source": "accessibility", "confidence": 0.95 } ],
    "browser_tab": null,
    "file_manager_state": null,
    "terminal_context": null,
    "extra": { "..." : "..." },
    "errors": []
  },
  "activity": { "timestamp": 1747345678.12, "window_seconds": 60, "keys_count": 42, "clicks_count": 5, "scrolls_count": 3, "mouse_distance_px": 1234.5, "idle_seconds": 0.4 },
  "browser_tab": null,
  "has_screenshot": true
}
```

字段任意可能为 `null`。当你刚启动还没切过窗口时 `window` 也是 `null`。

### `GET /api/v1/screenshot`

返回最近一次焦点窗口截图的 PNG 二进制。还没截到时返回 `404`。

```bash
curl -o latest.png http://127.0.0.1:5007/api/v1/screenshot
```

## SSE

`Content-Type: text/event-stream`，每条事件格式：

```
event: <type>
data: { "type": "<type>", "data": { ... } }

```

事件类型与 `data` 内容：

| `event` | `data.data` 内容 |
|---------|------------------|
| `window_changed`     | 完整 `WindowInfo` |
| `activity_updated`   | `ActivityStats` |
| `browser_tab_updated`| `BrowserTab` |
| `screenshot_ready`   | （无 `data`，提示客户端拉 `/screenshot`） |

25 s 没有事件时服务端发一个 SSE 注释行 `: keepalive` 保活——这不是 message，浏览器/客户端不会作为事件派发。

### 浏览器 EventSource 客户端

```javascript
const es = new EventSource("http://127.0.0.1:5007/api/v1/events");
es.addEventListener("window_changed", (ev) => {
  const { data } = JSON.parse(ev.data);
  console.log("App switched to:", data.app_name);
});
es.addEventListener("activity_updated", (ev) => { /* ... */ });
```

### httpx 流式客户端

```python
import httpx

with httpx.stream("GET", "http://127.0.0.1:5007/api/v1/events") as r:
    for line in r.iter_lines():
        if line.startswith("data: "):
            print(line[6:])
```

## WebSocket

`ws://127.0.0.1:5007/api/v1/ws`

- 服务端 **30 s 心跳**：aiohttp 自动发 ping 帧，客户端无需写代码
- 服务端推送的每条消息是一个 JSON：`{ "type": "...", "data": {...} }`，type 同 SSE
- 客户端可发文本指令：
  - `"snapshot"` → 服务端回 `{ "type": "snapshot", "data": <full snapshot> }`
  - 其他文本 → echo（用于连通性测试）

### websockets 库示例

```python
import asyncio, json, websockets

async def listen():
    async with websockets.connect("ws://127.0.0.1:5007/api/v1/ws") as ws:
        await ws.send("snapshot")
        async for msg in ws:
            event = json.loads(msg)
            print(event["type"], event.get("data"))

asyncio.run(listen())
```

### 节点 / 浏览器 WebSocket

```javascript
const ws = new WebSocket("ws://127.0.0.1:5007/api/v1/ws");
ws.onmessage = (ev) => {
  const e = JSON.parse(ev.data);
  if (e.type === "window_changed") { /* ... */ }
};
ws.onopen = () => ws.send("snapshot");
```

## 数据模型字段说明

详见 [`common/models.py`](../common/models.py)。要点：

- `document_paths[]`: 每条带 `source` 标签和 `confidence`（0-1）；按 confidence 倒序
- `file_manager_state.windows[]`: 每个文件管理器窗口的 `folder` + `selected_items[]`
- `terminal_context.shells[]` / `running[]`: 终端进程子树。`cmdline` 已脱敏，`cmdline_redacted=true` 表示有 token/密码被替换
- `extra`: 平台特定调试字段（AX 属性名 / 窗口 styles / display 等）
- `errors[]`: 非致命错误聚合（如 AX 权限未授予）

## 鉴权

**当前没有鉴权**。监听 `127.0.0.1` 即仅本机可访问。如果你 `--api-host 0.0.0.0` 把服务暴露到局域网，自己加 nginx + auth 或在网络层限制。

## 背压

服务端为每个 SSE/WS 客户端维护一个 `asyncio.Queue(maxsize=64)`。**消费太慢时丢最旧消息**，不会把服务端拖死。所以"长时间没看后又来看"会看到最新的几十条，不会看到所有历史。
