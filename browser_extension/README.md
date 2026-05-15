# Active Tracker — Browser Bridge

把当前浏览器标签页的 URL/标题实时推给本机的 Active Tracker 主程序。
不联网。仅 `ws://127.0.0.1:5006`，token 鉴权。

## 拿 Token

启动 Python 主程序后：

```bash
cat ~/.active_tracker/token
```

或在主程序顶栏点 **复制 Token** 按钮。

## 安装 — Chrome / Edge / Brave / Arc

1. 浏览器地址栏打开 `chrome://extensions`（Edge 用 `edge://extensions`，Brave 用 `brave://extensions`，Arc 见设置 → 扩展）
2. 右上角打开 **开发者模式**
3. 点 **加载已解压的扩展程序**，选这个 `browser_extension/` 目录
4. 点扩展图标 → 粘贴 token → **保存并重连**
5. 图标徽标变成绿点 = 已连接

## 安装 — Firefox（临时载入）

1. 打开 `about:debugging#/runtime/this-firefox`
2. **临时载入附加组件** → 选 `manifest.json`
3. 同上，点扩展图标配置 token

> ⚠️ 临时载入关闭浏览器即失效。永久安装需要在 Mozilla 签名后才能用。

## 验证

- 主程序 UI 的 **Browser** 卡片显示当前 URL/标题
- 切换 tab 应该立即更新
- 扩展图标显示绿点表示 WebSocket 已连接，红色/感叹号表示未连接

## 隐私

- 扩展只读取**当前激活 tab 的 URL 和标题**（不读页面内容、不读历史、不读 cookie）
- 数据只发到 `127.0.0.1`，永不离开本机
- 暂停开关一关，所有推送立即停止
- Token 任何时候都可重新生成：删 `~/.active_tracker/token` 后重启主程序

## 图标

`icons/16.png`、`icons/48.png`、`icons/128.png` 是占位透明 PNG。
你可以替换成自己的图标。
