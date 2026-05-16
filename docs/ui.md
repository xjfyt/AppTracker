# 桌面 UI

UI 是纯静态资产（`desktop/ui/`），由 Tauri 加载本地 HTTP/WS 数据。

## 文件

- [`index.html`](../desktop/ui/index.html)：顶栏 + 三列面板 + lightbox。
- [`styles.css`](../desktop/ui/styles.css)：CSS 变量主题、组件化的 chip/card/switch/lightbox。
- [`main.js`](../desktop/ui/main.js)：与 agent API 的 WS + 渲染逻辑。

## 设计原则

1. **组件化展示**：原来一行行 `key·value·decimal` 的文本被换成 chip + card 组合。
   - 文档列表里 kind / source / 置信度都是 chip，置信度根据数值切换 `chip-success/warn/muted`。
   - 终端、文件管理器同样以 card + chip 呈现「shell / running」、「当前 / 后台」等状态。
2. **百分比表示置信度**：`formatPercent(value)` 把 `[0, 1]` 数值乘 100 并 `Math.round`。文件 / 文件夹处不再出现 0.x 小数。
3. **去 Rust 化**：`<title>`、`<h1>`、Tauri `productName` 全部改成 AppTracker，副标题只描述功能。
4. **截图开关**：顶栏 toggle，默认关闭，状态由 `/api/v1/capture` 和 `capture_changed` 事件双向同步。
5. **双击放大**：截图 `<img>` 监听 `dblclick`，把 `src` 复制到 `#lightbox` 内的 `<img>`；点背景或 `Esc` 关闭。

## 数据流

```
loadSnapshot ──► applyCaptureState / renderSnapshot
       │
       └──► WS connect ──► 增量事件
                              ├─ window_changed → renderWindow
                              ├─ activity_updated → renderActivity
                              ├─ browser_tab_updated → renderBrowser
                              ├─ screenshot_ready → refreshScreenshot
                              ├─ paused_changed → renderPaused
                              └─ capture_changed → applyCaptureState
```

`setHtml` 用 `htmlCache` 做"同字符串不重渲染"的小优化，避免高频事件导致 DOM 抖动。

## 状态管理

页面只有几个可变量：`apiBase / paused / captureEnabled / ws / reconnectTimer / lastScreenshotRefresh`。  
没有引入框架——保持依赖为零，方便 Tauri 直接加载。
