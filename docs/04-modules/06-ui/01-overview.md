> **对应代码**：`desktop/ui/index.html`, `desktop/ui/main.js`, `desktop/ui/styles.css`
> **维护提示**：修改 UI 组件或渲染逻辑时同步更新本文档。

# 二十六、桌面 UI

## 1、概述

桌面 UI 位于 `desktop/ui/`，是纯静态的 HTML/CSS/JS 应用，由 Tauri WebView 直接加载，无构建步骤。

## 2、页面结构

```
┌─────────────────────────────────────────────────┐
│  顶栏 (topbar)                                   │
│  [Logo] AppTracker  [截图开关] [暂停] [API地址] [状态] │
├──────────┬──────────────────────────────────────┤
│ 侧边栏    │ 主视图 (view-stack)                   │
│ (side-tabs)│                                      │
│           │ ┌─ 当前状态 (overview) ──────────────┐ │
│ 当前状态   │ │ 左: 窗口信息 + 文档路径             │ │
│           │ │ 中: 浏览器Key + Tab + 终端 + 文件管理│ │
│ 诊断      │ │ 右: 活动统计 + 截图                 │ │
│           │ └────────────────────────────────────┘ │
│           │ ┌─ 诊断 (diagnostics) ───────────────┐ │
│           │ │ 连接状态 / 能力状态 / 错误提示       │ │
│           │ └────────────────────────────────────┘ │
└──────────┴──────────────────────────────────────┘
```

## 3、三个开关

| 开关 | 元素 | API | 说明 |
|------|------|-----|------|
| 截图 | `#captureToggle` | `POST /api/v1/capture` | 截图采集开关 |
| 暂停 | `#pauseBtn` | `POST /api/v1/pause` | 暂停/恢复所有采集 |
| 进程路径 | `#showProcessPaths` | `POST /api/v1/show_process_paths` | 显示/隐藏进程上下文路径 |

## 4、WebSocket 连接

`main.js` 通过 WebSocket 连接接收实时事件：

```javascript
const wsUrl = apiBase.replace(/^http/, "ws") + "/api/v1/ws";
const socket = new WebSocket(wsUrl);
socket.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") renderSnapshot(msg.data);
    if (msg.type === "window_changed") renderWindow(msg.data);
    if (msg.type === "activity_updated") renderActivity(msg.data);
    // ...
};
```

连接断开后每秒自动重连。

## 5、端口发现

```javascript
function candidateApiBases(preferred) {
    // 优先使用用户配置的地址
    // 回退扫描 5007-5012
}
async function discoverApiBase() {
    for (const base of candidateApiBases()) {
        const res = await fetch(`${base}/api/v1/health`);
        if (data.service === "apptracker") return base;
    }
}
```

## 6、诊断面板

诊断面板（`view-diagnostics`）显示：

| 区域 | 内容 |
|------|------|
| 连接 | API 地址、连接状态、插件 Key、暂停/截图/进程路径状态 |
| 能力状态 | API、浏览器插件、前台窗口、文档路径、文件管理器、终端、活动统计、平台错误 |
| 错误/提示 | Wayland 限制、macOS 权限、浏览器插件未连接等 |

## 7、灯箱（Lightbox）

双击截图图片打开灯箱放大查看，点击背景或按 Escape 关闭。

## 8、HTML 缓存

`main.js` 使用 `htmlCache` Map 避免重复设置 `innerHTML`，减少 DOM 操作。

---

- 上一篇：[04-browser-protocol.md](../05-api/04-browser-protocol.md)
- 下一篇：[01-overview.md](../07-state/01-overview.md)
- 返回索引：[docs/README.md](../../README.md)
