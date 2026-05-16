## 一、功能说明

浏览器扩展负责把当前活动标签页的 URL 和标题发送给本机 Rust agent：

```text
ws://127.0.0.1:5006
```

扩展只读取当前活动标签页的 URL / 标题，不读取网页正文、历史记录、Cookie 或表单内容。

## 二、获取 Token

先启动 agent：

```powershell
npm run agent
```

读取 token：

```bash
cat ~/.active_tracker/token
```

Windows PowerShell：

```powershell
Get-Content "$HOME\.active_tracker\token"
```

把 token 粘贴到扩展 popup 中并保存。

## 三、安装方法

### 1、Chrome / Edge / Brave / Arc

1. 打开扩展管理页，例如 `chrome://extensions`、`edge://extensions`。
2. 打开“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择项目里的 `browser_extension/` 目录。
5. 点击扩展图标，粘贴 token，点击保存并重连。

### 2、Firefox 临时安装

1. 打开 `about:debugging#/runtime/this-firefox`。
2. 点击“临时载入附加组件”。
3. 选择 `browser_extension/manifest.json`。
4. 点击扩展图标，粘贴 token，点击保存并重连。

Firefox 临时扩展会在浏览器关闭后失效，长期使用需要正式签名安装。

## 四、验证方法

启动 agent 和扩展后，切换浏览器 tab，`/api/v1/snapshot` 中的 `browser_tab` 字段应更新为当前标签页。
