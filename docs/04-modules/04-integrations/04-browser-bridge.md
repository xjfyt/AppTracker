> **对应代码**：`browser_extension/background.js`, `browser_extension/manifest.json`, `tracker-core/src/bridge.rs`
> **维护提示**：修改浏览器扩展协议或 token 机制时同步更新本文档。

# 二十一、浏览器扩展桥接

## 1、概述

浏览器扩展通过 WebSocket 连接到 AppTracker API，实时上报当前活跃标签页的 URL、标题、favicon 等信息。

## 2、架构

```
┌──────────────────────┐     WebSocket      ┌──────────────────────┐
│  浏览器扩展           │ ──────────────────→ │  AppTracker API      │
│  background.js       │  token 鉴权         │  /api/v1/browser     │
│                      │  tab_update 消息     │                      │
│  chrome.tabs API     │ ←────────────────── │  bridge_token 管理   │
└──────────────────────┘                     └──────────────────────┘
```

## 3、连接流程

1. 扩展启动 → `loadState()` 从 `chrome.storage.local` 读取 token/apiBase
2. 若无 token → `fetchTokenFromHost()` 从 `/api/v1/bridge_token` 获取
3. `discoverApiBase()` 扫描 5007-5012 端口，找到健康的服务
4. 建立 WebSocket → 发送 `{"token": "..."}` 鉴权
5. 监听 `chrome.tabs.onActivated` / `onUpdated` / `onFocusChanged` → `pushActiveTab()`

## 4、消息协议

### 鉴权消息（扩展 → 服务端）

```json
{"token": "base64url-token"}
```

### Tab 更新消息（扩展 → 服务端）

```json
{
    "type": "tab_update",
    "browser": "chrome",
    "windowId": 123,
    "tabId": 456,
    "url": "https://example.com",
    "title": "Example Page",
    "favIconUrl": "https://example.com/favicon.ico",
    "active": true
}
```

### 浏览器类型检测

```javascript
function detectBrowser() {
    if (ua.includes("Edg/")) return "edge";
    if (ua.includes("Firefox/")) return "firefox";
    if (ua.includes("OPR/")) return "opera";
    return "chrome";
}
```

## 5、Token 管理

### 服务端（bridge.rs）

```rust
pub async fn load_or_create_token() -> anyhow::Result<(PathBuf, String)>
```

1. 读取 `~/.apptracker/token`
2. 若不存在，检查旧路径 `~/.active_tracker/token`（一次性迁移）
3. 若仍不存在，生成 32 字节随机 token（Base64 URL-safe 编码）
4. Unix 系统设置文件权限 `0o600`

### 扩展端

- 首次连接时自动从 `/api/v1/bridge_token` 获取 token
- 存储在 `chrome.storage.local`
- 支持手动粘贴 token（通过 popup UI）

## 6、重连策略

- 断开后指数退避重连（1s → 2s → 4s → ... → 30s 上限）
- 每 30 秒 keepalive alarm 检查连接状态
- 端口回退：扫描 5007-5012

## 7、Badge 状态

| 状态 | 颜色 | 文字 | 含义 |
|------|------|------|------|
| ok | 绿色 #22c55e | `*` | 已连接 |
| off | 灰色 #64748b | 空 | 用户暂停 |
| err | 红色 #ef4444 | `!` | 连接失败 |

## 8、支持的浏览器

| 浏览器 | manifest 配置 |
|--------|--------------|
| Chrome | 标准 MV3 |
| Edge | 同 Chrome（Chromium 内核） |
| Brave | 同 Chrome |
| Arc | 同 Chrome |
| Firefox | `gecko` 配置（`apptracker@localhost`） |

---

- 上一篇：[03-terminal.md](./03-terminal.md)
- 下一篇：[01-overview.md](../05-api/01-overview.md)
- 返回索引：[docs/README.md](../../README.md)
