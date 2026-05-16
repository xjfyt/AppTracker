## 一、功能说明

终端集成是可选增强，用于更准确地识别终端当前目录。没有安装脚本时，agent 会尽量通过进程信息读取 cwd；安装脚本后，在 tmux、screen、嵌套 shell、Windows CMD 等场景下也能更稳定地拿到真实 cwd。

脚本会在每次 prompt 显示时写入：

```text
~/.active_tracker/shells/<PID>.cwd
```

只写当前目录。部分脚本也会写 `<PID>.cmd`，但 cwd 检测只依赖 `.cwd`。

## 二、安装方法

### 1、Windows 一键安装

Windows 推荐直接双击：

```text
shell_integration/install_windows.cmd
```

该脚本会自动安装 PowerShell 和 CMD 集成。PowerShell 会写入当前用户的 `$PROFILE`，CMD 会写入当前用户注册表 `HKCU\Software\Microsoft\Command Processor\AutoRun`。安装完成后，重启 PowerShell、CMD 或 Windows Terminal 即可生效。

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

查看 profile 路径：

```powershell
$PROFILE
```

如果 profile 不存在，先创建：

```powershell
New-Item -ItemType File -Path $PROFILE -Force
```

追加集成脚本：

```powershell
Add-Content -Path $PROFILE -Value ". 'C:\path\to\active_tracker\shell_integration\powershell.ps1'"
```

重启终端后生效。

### 6、CMD 手动安装

如果不使用一键脚本，可以把下面命令中的路径替换为项目实际路径后执行：

```powershell
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Command Processor" -Name AutoRun -Value 'if exist "C:\path\to\active_tracker\shell_integration\cmd.cmd" call "C:\path\to\active_tracker\shell_integration\cmd.cmd"'
```

CMD 集成会在启动时写入一次 cwd，并通过 `doskey` 包装 `cd`、`pushd`、`popd`、`exit` 等命令来更新当前目录。CMD 本身没有通用的 prompt hook，因此通过第三方程序改变父 CMD cwd 的极端场景无法保证捕获。

## 三、验证方法

### 1、bash / zsh

```bash
ls ~/.active_tracker/shells/
cat ~/.active_tracker/shells/$$.cwd
```

### 2、fish

```fish
ls ~/.active_tracker/shells/
cat ~/.active_tracker/shells/$fish_pid.cwd
```

### 3、PowerShell

```powershell
Get-ChildItem "$HOME\.active_tracker\shells"
Get-Content "$HOME\.active_tracker\shells\$PID.cwd"
```

### 4、CMD

```cmd
dir "%USERPROFILE%\.active_tracker\shells"
type "%USERPROFILE%\.active_tracker\shells\%ACTIVE_TRACKER_CMD_PID%.cwd"
```

文件内容应该是当前目录。

## 四、卸载方法

删除 shell 配置文件中 `source .../shell_integration/...`、PowerShell profile 中对应的 `. '...\powershell.ps1'` 行，或 CMD 的 `HKCU\Software\Microsoft\Command Processor\AutoRun` 中对应的 `cmd.cmd` 调用，然后重启终端。

如需清理缓存文件：

```bash
rm -rf ~/.active_tracker/shells
```
