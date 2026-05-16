## 一、功能说明

浏览器扩展负责把当前活动标签页的 URL 和标题发送给本机 AppTracker：

```text
ws://127.0.0.1:5007/api/v1/browser
```

扩展只读取当前活动标签页的 URL / 标题，不读取网页正文、历史记录、Cookie 或表单内容。

## 二、安装方法

启动 AppTracker 桌面端（任何方式都可以，比如 `npm run dev` 或打包后的 .exe），它会在 `~/.apptracker/token` 自动生成鉴权 token，端口 5007 同时承载浏览器扩展的 WebSocket。

### 1、Chrome / Edge / Brave / Arc

1. 打开扩展管理页，例如 `chrome://extensions`、`edge://extensions`。
2. 打开"开发者模式"。
3. 点击"加载已解压的扩展程序"。
4. 选择项目里的 `browser_extension/` 目录。
5. 点击扩展图标 → **Sync**。如果 AppTracker 正在运行，扩展会自动从 `/api/v1/bridge_token` 拉到 token 并连接。

### 2、Firefox 临时安装

1. 打开 `about:debugging#/runtime/this-firefox`。
2. 点击"临时载入附加组件"。
3. 选择 `browser_extension/manifest.json`。
4. 点击扩展图标 → **Sync**，同上。

Firefox 临时扩展会在浏览器关闭后失效，长期使用需要正式签名安装。

## 三、手动粘贴（可选）

如果自动 Sync 不可用（防火墙、自定义端口等），可以手动粘贴：

- 文件位置：`~/.apptracker/token`（旧版的 `~/.active_tracker/token` 会被一次性迁移）。
- PowerShell：

```powershell
Get-Content "$HOME\.apptracker\token"
```

把内容粘贴到扩展 popup 的 Token 框，点击 Save。

## 四、验证

启动 AppTracker 与扩展后，切换浏览器 Tab，`/api/v1/snapshot` 中的 `browser_tab` 字段应实时更新为当前标签页；UI 上"浏览器 Tab"卡片也会显示对应的浏览器与 URL。
