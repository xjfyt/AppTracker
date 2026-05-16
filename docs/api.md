# 本地 API

AppTracker 只对外暴露 **一个端口**（默认 `127.0.0.1:5007`，被占用时向后顺延 5 个端口）。HTTP / WebSocket / SSE 全部走这里。

## REST

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 健康检查，返回 `{ok, service:"apptracker"}` |
| GET | `/api/v1/snapshot` | 一次性快照（见下） |
| GET | `/api/v1/screenshot` | 最新截图 PNG，无图返回 404 |
| GET | `/api/v1/bridge_token` | 浏览器扩展用的鉴权 token（明文返回） |
| GET / POST | `/api/v1/pause` | 暂停整套采集 |
| GET / POST | `/api/v1/capture` | 截图开关（默认关闭） |
| GET / POST | `/api/v1/show_process_paths` | 是否在 `document_paths` 中显示进程上下文（cwd/启动目录）路径，默认关闭 |

POST 体一律是单字段 JSON：`{"paused": bool}` / `{"enabled": bool}`。

## Snapshot

```jsonc
{
  "window": WindowInfo | null,
  "activity": ActivityStats | null,
  "browser_tab": BrowserTab | null,
  "has_screenshot": false,
  "paused": false,
  "capture_enabled": false,
  "show_process_paths": false
}
```

`WindowInfo.document_paths[*]` 字段：

```jsonc
{
  "path": "C:/Users/.../doc.docx",
  "kind": "file" | "folder" | "unknown",
  "source": "file_manager" | "title" | "cwd" | "cmdline" | "office:word" | "terminal:pwsh" | ...,
  "confidence": 0.0 - 1.0,
  "category": "user" | "process"
}
```

`category` 区分这条路径是用户行为捕获到的（Explorer 浏览、Office 当前打开、终端 cwd、Tab、UIA/COM 提取的文档等）还是进程自身上下文（`cwd` / `cmdline`）。UI 默认隐藏 `category=process`，可通过 `show_process_paths` 开关展示。

> 此外，任何落在「当前前台进程可执行文件所在目录」里的路径都会在后台直接丢弃（无论 category）——这一步专门干掉 `C:/Program Files/<App>` 这种纯安装目录噪声。

## WebSocket（UI / 第三方）

- 路径：`/api/v1/ws`
- 客户端 text 帧：`snapshot` / `pause` / `resume`
- 服务端事件：
  - `window_changed` — `WindowInfo`
  - `activity_updated` — `ActivityStats`
  - `browser_tab_updated` — `BrowserTab`
  - `screenshot_ready` — 信号事件
  - `paused_changed` — `bool`
  - `capture_changed` — `bool`
  - `show_process_paths_changed` — `bool`

## WebSocket（浏览器扩展）

- 路径：`/api/v1/browser`
- 第一帧必须发 `{"token": "<bridge_token>"}`，token 来自 `~/.apptracker/token` 或 `GET /api/v1/bridge_token`。
- 后续帧：`{"type": "tab_update", "browser": "...", "url": "...", "title": "...", ...}`，由 `state.update_browser_tab` 触发 `browser_tab_updated`。

## SSE

`/api/v1/events`：把 `/api/v1/ws` 的事件按 `event:` + `data:` 推送，25s keep-alive。
