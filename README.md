## 一、项目介绍

AppTracker 是一个 Tauri 桌面应用，集成了窗口/文档/终端/浏览器 Tab/键鼠活动/可选截图等本地采集能力。整个进程只暴露一个端口（默认 5007），同时承载 UI、采集核与浏览器扩展桥。

## 二、一键命令

以下命令都在项目根目录执行。

```powershell
# 启动 AppTracker 桌面端（带 UI；采集核内嵌运行）
npm run dev

# 打包 release 版应用
npm run package

# 格式检查、编译检查和 Rust 测试
npm run check
```

第一次执行 `npm run dev` 或 `npm run package` 时，会自动在 `desktop/` 下安装 Tauri 的 npm 依赖。

## 三、构建产物

Windows 下产物位于：

```text
target/release/active-tracker-tauri.exe
```

macOS / Linux 下文件名没有 `.exe` 后缀。该二进制即 AppTracker 桌面端，启动后同时托管 UI、采集核与浏览器扩展桥，仅占用一个端口（默认 5007）。

## 四、API 说明

### 1、默认监听

- 唯一端口：默认 `http://127.0.0.1:5007`（HTTP/WebSocket/SSE 共享）。如果被占用，核心会尝试顺延到 `5008`-`5012`；桌面 UI 和浏览器扩展会自动探测这一段端口。

### 2、主要路由

- `GET /api/v1/health`
- `GET /api/v1/snapshot`
- `GET /api/v1/screenshot`
- `GET /api/v1/events` (SSE)
- `GET /api/v1/ws`
- `GET /api/v1/browser` (浏览器扩展 WebSocket)
- `GET /api/v1/bridge_token`
- `GET/POST /api/v1/pause`
- `GET/POST /api/v1/capture`（截图开关，默认关闭）
- `GET/POST /api/v1/show_process_paths`（是否展示进程上下文路径，默认关闭）

完整列表见 [docs/api.md](docs/api.md)。

### 3、鉴权

浏览器扩展通过 `~/.apptracker/token`（旧版 `~/.active_tracker/token` 会自动迁移）。AppTracker 首次启动时会自动生成该 token，并通过 `/api/v1/bridge_token` 让扩展一键拉取。

## 五、浏览器扩展安装

浏览器扩展用于把当前活动标签页的 URL 和标题发送给本机 AppTracker。主程序无法稳定、合规地直接读取所有浏览器 URL，所以浏览器信息建议始终通过扩展获取。

1. 启动 AppTracker 桌面端（`npm run dev` 或打包后的二进制）。
2. 在 Chromium 系浏览器打开 `chrome://extensions`（或 Firefox `about:debugging`），加载 `browser_extension/` 目录。
3. 点击扩展图标 → **Sync**。如果 AppTracker 正在运行，扩展会自动通过 `/api/v1/bridge_token` 拉到 token 并连接。

如果自动同步失败，桌面端 UI 的「浏览器插件 Key」区域会显示同一个 token，可直接复制到扩展的 Token 输入框。

如需自定义端口或者手动粘贴 token，详见 [browser_extension/README.md](browser_extension/README.md)。

## 六、终端扩展安装

终端扩展是可选的。没有它时，agent 会尽量通过进程信息读取终端 cwd；安装后，在 tmux、screen、嵌套 shell、Windows CMD 等场景下可以更准确地识别当前目录。

脚本会在每次 shell prompt 显示时写入：

```text
~/.active_tracker/shells/<PID>.cwd
```

只写当前目录，不写环境变量。部分脚本也会写 `<PID>.cmd` 供后续能力使用，但 cwd 检测只依赖 `.cwd`。

### 1、Windows 一键安装

Windows 推荐直接双击：

```text
shell_integration/install_windows.cmd
```

该脚本会自动安装 PowerShell 和 CMD 集成：PowerShell 会写入当前用户的 `$PROFILE`，CMD 会写入当前用户注册表 `HKCU\Software\Microsoft\Command Processor\AutoRun`。安装完成后，重启 PowerShell、CMD 或 Windows Terminal 即可生效。

也可以在 PowerShell 中执行：

```powershell
.\shell_integration\install_windows.ps1
```

### 2、bash

```bash
echo "source /path/to/active_tracker/shell_integration/bash.sh" >> ~/.bashrc
exec bash
```

### 3、zsh

```zsh
echo "source /path/to/active_tracker/shell_integration/zsh.sh" >> ~/.zshrc
exec zsh
```

### 4、fish

```fish
echo "source /path/to/active_tracker/shell_integration/fish.fish" >> ~/.config/fish/config.fish
exec fish
```

### 5、PowerShell 手动安装

先查看 profile 路径：

```powershell
$PROFILE
```

如果 profile 文件不存在，先创建：

```powershell
New-Item -ItemType File -Path $PROFILE -Force
```

然后追加 source 命令：

```powershell
Add-Content -Path $PROFILE -Value ". 'C:\path\to\active_tracker\shell_integration\powershell.ps1'"
```

重启终端后生效。

### 6、CMD 手动安装

如不使用一键脚本，可以把下面命令中的路径替换为项目实际路径后执行：

```powershell
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Command Processor" -Name AutoRun -Value 'if exist "C:\path\to\active_tracker\shell_integration\cmd.cmd" call "C:\path\to\active_tracker\shell_integration\cmd.cmd"'
```

CMD 集成会在启动时写入一次 cwd，并通过 `doskey` 包装 `cd`、`pushd`、`popd`、`exit` 等命令来更新当前目录。CMD 本身没有通用的 prompt hook，因此通过第三方程序改变父 CMD cwd 的极端场景无法保证捕获。

### 7、验证终端扩展

启动一个新的 shell 后执行：

```bash
ls ~/.active_tracker/shells/
cat ~/.active_tracker/shells/$$.cwd
```

应该能看到当前 shell PID 对应的 `.cwd` 文件，文件内容是当前目录。

PowerShell 可用：

```powershell
Get-ChildItem "$HOME\.active_tracker\shells"
Get-Content "$HOME\.active_tracker\shells\$PID.cwd"
```

CMD 可用：

```cmd
dir "%USERPROFILE%\.active_tracker\shells"
type "%USERPROFILE%\.active_tracker\shells\%ACTIVE_TRACKER_CMD_PID%.cwd"
```

## 七、平台能力

- Windows：Win32 前台窗口、进程信息、cmdline/cwd 文档探测、Office/WPS COM 文档探测、UI Automation 文档探测、Explorer COM、终端进程树、PowerShell/CMD shell cwd 文件、截图、键鼠活动。
- macOS：System Events / AppleScript 前台窗口、Finder AppleScript、进程树、shell cwd 文件、截图、键鼠活动。需要 Accessibility / Input Monitoring / Automation 权限。
- Linux：X11 下使用 `xdotool` / `xprop` / `xwininfo` 获取窗口信息；文件管理器为 cwd/title best-effort。Wayland 受桌面安全模型限制，能力会少一些。

## 八、接入建议

如果要接入到其他软件，把 AppTracker 桌面端常驻启动即可，然后通过 HTTP/SSE/WebSocket 端口 5007 读取状态。这样采集权限、平台差异和异常崩溃都和主程序隔离。
