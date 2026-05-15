# Shell 集成（可选 Tier 2）

主程序默认用 `psutil.Process.cwd()` 拿终端 shell 的 cwd，对大多数终端足够。
**tmux / screen / 嵌套 shell** 下不准——这里就是给那个场景准备的。

## 它做什么

源码在 [`/shell_integration/`](../shell_integration/)（bash / zsh / fish / powershell 各一份）。
每个脚本注册一个 prompt hook：每次 shell 显示 prompt 时把 `$PWD` 写到 `~/.active_tracker/shells/<PID>.cwd`。

主程序在终端卡片渲染时会读这些文件，**优先用文件里的 cwd**，UI 上对应行显示 `shell-file` chip。

## 安装

主程序顶栏 **Shell 脚本目录** 按钮一键复制路径，方便在 rc 文件里 source。

### bash

```bash
echo "source /path/to/active_tracker/shell_integration/bash.sh" >> ~/.bashrc
exec bash
```

### zsh

```zsh
echo "source /path/to/active_tracker/shell_integration/zsh.sh" >> ~/.zshrc
exec zsh
```

### fish

```fish
echo "source /path/to/active_tracker/shell_integration/fish.fish" >> ~/.config/fish/config.fish
exec fish
```

### PowerShell（Windows / cross-platform pwsh）

```powershell
# 找到 profile 位置
$PROFILE
# 末尾追加（替换路径）
Add-Content -Path $PROFILE -Value ". 'C:\path\to\active_tracker\shell_integration\powershell.ps1'"
# 重启终端
```

## 验证

启动一个新 shell：

```bash
ls ~/.active_tracker/shells/
# 应能看到 <PID>.cwd

cat ~/.active_tracker/shells/$$.cwd   # bash/zsh
# → 当前目录
```

主程序终端卡片里对应 shell 那行右上角应该出现 `shell-file` chip。

## 卸载

删 `source ...` 那行，重启 shell。`~/.active_tracker/shells/` 目录可以直接 `rm -rf`。

## 隐私

- 脚本只写 `$PWD`，**不写命令、历史、环境变量**
- 文件权限 `0600`（脚本里 `chmod 600` 强制设置）
- 退出 shell 时自动 `rm`（`trap EXIT` / `zshexit` / `fish_exit` / PowerShell engine exit）
- 主程序读 PID 文件时验证进程还活着，否则当场清理
