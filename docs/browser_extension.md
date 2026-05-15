# 浏览器扩展

源码在 [`/browser_extension/`](../browser_extension/) — Manifest V3，**同一份代码同时适配 Chrome / Edge / Brave / Arc / Firefox**。

## 它做什么

把当前浏览器标签页的 **URL / 标题 / favicon** 通过 WebSocket 实时推给本机的 Active Tracker 主程序（`ws://127.0.0.1:5006`），主程序的 BrowserCard 立即显示。

**不读页面内容**，不读历史，不读 cookies。

## 安装

### 1. 拿 token

启动主程序后：

```bash
cat ~/.active_tracker/token
```

或者点主窗口顶栏 **复制 Token** 按钮。

### 2. Chrome / Edge / Brave / Arc

1. 打开扩展页（`chrome://extensions` / `edge://extensions` / `brave://extensions`，Arc 在设置里）
2. 右上角开 **开发者模式**
3. **加载已解压的扩展程序** → 选 `browser_extension/` 目录
4. 点扩展图标 → 粘贴 token → **保存并重连**
5. 扩展图标右下角出现绿点 = 已连接

### 3. Firefox（临时载入）

1. 打开 `about:debugging#/runtime/this-firefox`
2. **临时载入附加组件** → 选 `manifest.json`
3. 同上配置 token

> 关闭浏览器后临时扩展失效。永久安装需要 Mozilla 签名。

## 验证

- 扩展图标徽标：绿色 = 已连接、红色 = 未连接
- 主程序的 BrowserCard 出现 URL + 标题
- 切换 tab 应立即更新

## 鉴权

扩展启动时先发 `{ "token": "..." }`，服务端比对 `~/.active_tracker/token`。token 不对就 4001 close。

```
~/.active_tracker/token   权限 0600，首次启动自动生成
```

删除 token 后下次启动主程序会重新生成；扩展里的旧 token 失效，要重新粘贴。

## 隐私

- 扩展 `host_permissions: <all_urls>` 是为了 `chrome.tabs` API 能拿到 URL，**不会读取页面内容**
- 数据只发到 `127.0.0.1:5006`，永不离开本机
- popup 里有"暂停推送"开关，关后即停
