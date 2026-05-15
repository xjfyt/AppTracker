# 各平台权限授予

## macOS（13+）

需要三个权限（按需）：

### 1. 辅助功能 (Accessibility) — 必需

用途：读窗口标题、几何、AXDocument。
路径：*系统设置 → 隐私与安全性 → 辅助功能*

未授予时主程序 UI 顶部会显示黄色横幅，点 **打开系统设置** 跳转。授权后重启主程序。

### 2. 输入监控 (Input Monitoring) — 用于活动卡片

用途：pynput 监听键鼠事件做聚合统计（不记录按键值）。
路径：*系统设置 → 隐私与安全性 → 输入监控*

未授予时活动卡片显示 0。**永不记录按键内容**，仅事件计数。

### 3. 自动化 (Automation) — 用于 Finder / Chrome / Safari / Arc

用途：通过 AppleScript 拿 Finder 当前文件夹+选中项、浏览器 URL。
首次调用 `osascript` 时系统自动弹"允许 Active Tracker 控制 X"对话框，点允许即可。

> 三个权限是**独立开关**，分别授权。

## Windows 10/11

通常无需特殊权限。例外：

- **以管理员启动的应用** — Active Tracker 必须也以管理员运行才能读其句柄信息和 UI Automation 树
- **UWP / 沙盒应用** — 可能拒绝 UI Automation 遍历，会被 2 s 超时兜住，errors 面板有提示
- **Shell COM 对 Explorer** — 不需要权限，但 Windows 11 标签页式 Explorer 的非活动 tab 拿不到

## Linux

- **X11 会话** — 默认即可工作
- **Wayland 会话** — 只能看到 XWayland 兼容应用（大多数 Chromium/Firefox 默认仍跑在 XWayland），原生 Wayland 应用看不到，会在 errors 面板提示
- **pynput** — 需要可访问的 X server；远程 SSH 无 X11 forwarding 会失败
