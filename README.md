## 一、项目介绍

Active Tracker 是一个 Rust/Tauri 版本地活动追踪器。底层核心是无界面的 Rust agent，负责采集当前窗口、进程、终端、文件管理器、浏览器标签页、截图和键鼠活动，并通过本机 API 对外提供状态；Tauri 只是一个读取本机 API 的页面。

## 二、一键命令

以下命令都在项目根目录执行。

```powershell
# 启动 Tauri 界面；内嵌 Rust agent 会一起启动
npm run dev

# 只启动无界面 agent，适合作为你们软件的 sidecar
npm run agent

# 一键打包 release 版 agent 和 Tauri 应用
npm run package

# 格式检查、编译检查和 Rust 测试
npm run check
```

第一次执行 `npm run dev` 或 `npm run package` 时，会自动在 `desktop/` 下安装 Tauri 的 npm 依赖。

## 三、构建产物

Windows 下产物位于：

```text
target/release/active-tracker-agent.exe
target/release/active-tracker-tauri.exe
```

macOS / Linux 下文件名没有 `.exe` 后缀，但命令相同。

## 四、API 说明

### 1、默认监听

- API：`http://127.0.0.1:5007`
- 浏览器扩展桥：`ws://127.0.0.1:5006`

### 2、路由

- `GET /api/v1/health`
- `GET /api/v1/snapshot`
- `GET /api/v1/screenshot`
- `GET /api/v1/events`
- `GET /api/v1/ws`
- `GET/POST /api/v1/pause`

### 3、鉴权

浏览器扩展使用 `~/.active_tracker/token` 鉴权。agent 首次启动时会自动生成该 token。

## 五、浏览器扩展安装

浏览器扩展用于把当前活动标签页的 URL 和标题发送给本机 agent。主程序无法稳定、合规地直接读取所有浏览器 URL，所以浏览器信息建议始终通过扩展获取。

### 1、安装前准备

先启动 agent：

```powershell
npm run agent
```

然后读取 token：

```bash
cat ~/.active_tracker/token
```

Windows PowerShell 可以用：

```powershell
Get-Content "$HOME\.active_tracker\token"
```

### 2、Chrome / Edge / Brave / Arc

1. 打开浏览器扩展管理页，例如 `chrome://extensions` 或 `edge://extensions`。
2. 打开“开发者模式”。
3. 选择“加载已解压的扩展程序”。
4. 选择项目里的 `browser_extension/` 目录。
5. 点击扩展图标，粘贴 `~/.active_tracker/token` 内容并保存。
6. 图标状态变为已连接后，agent 的 `browser_tab` 字段会开始更新。

### 3、Firefox 临时安装

1. 打开 `about:debugging#/runtime/this-firefox`。
2. 选择“临时载入附加组件”。
3. 选择 `browser_extension/manifest.json`。
4. 点击扩展图标，粘贴 token 并保存。

Firefox 的临时扩展会在浏览器关闭后失效，长期使用需要正式签名安装。

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

如果要接入到其他软件，推荐把 `tracker-agent` 作为 sidecar 进程启动，然后通过 HTTP/SSE/WebSocket 读取状态。这样采集权限、平台差异和异常崩溃都能和主程序隔离。
