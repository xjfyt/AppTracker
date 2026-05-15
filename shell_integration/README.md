# Active Tracker — Shell 集成（可选 Tier 2）

> **可选**。不装，主程序也能用 `psutil.Process.cwd()` 拿到大多数终端的 cwd。
> 装了之后，**tmux / screen / 嵌套 shell** 下也能拿到准确的 cwd。

## 它做什么

每次 shell 显示 prompt 时，把当前目录写到 `~/.active_tracker/shells/<PID>.cwd`，
主程序读这个文件比 `psutil.Process.cwd()` 在多层进程嵌套下更准。

**只写当前目录**：不写命令、不写历史、不写环境变量。
文件权限 0600，只有当前用户能读。

## 安装

主程序 UI 顶栏点 **Shell 脚本目录** 按钮 → 复制路径，方便 source。

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
# 看 $PROFILE 位置
$PROFILE
# 在末尾追加（替换路径）
Add-Content -Path $PROFILE -Value ". 'C:\path\to\active_tracker\shell_integration\powershell.ps1'"
# 重启终端
```

## 卸载

删掉 `source ...` 那行，重启 shell。`~/.active_tracker/shells/` 目录可以直接 `rm -rf`。

## 验证生效

启动一个新 shell，应在 0.5 秒内看到一个新文件：

```bash
ls ~/.active_tracker/shells/
# 应能看到 当前PID.cwd
cat ~/.active_tracker/shells/$$.cwd     # bash/zsh
# → 当前目录
```

在主程序 UI 的终端卡里，对应 shell 行右上角会出现 `shell-file` chip，
表示 cwd 来自集成脚本。

## 隐私清单

- [x] 只写 `$PWD`，不写其他变量
- [x] 文件权限 0600
- [x] 退出 shell 时自动 `rm`（trap EXIT / zshexit / fish_exit / Engine Exit）
- [x] 主程序读时验证 PID 还活着，否则当场清理
