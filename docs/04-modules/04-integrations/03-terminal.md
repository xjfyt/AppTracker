> **对应代码**：`tracker-core/src/integrations/terminal.rs`, `tracker-core/src/integrations/shell_files.rs`
> **维护提示**：新增终端类型或 Shell 类型时同步更新本文档。

# 二十、终端集成

## 1、概述

终端集成检测当前窗口是否为终端应用，若是则遍历进程树识别 Shell 和运行中的子命令，提取工作目录。

## 2、终端检测

### detect_terminal()

通过以下属性匹配 35+ 种终端：

| 属性 | 示例 |
|------|------|
| Bundle ID | `com.apple.Terminal`, `com.googlecode.iterm2`, `io.alacritty` |
| 应用名 | `Terminal`, `iTerm2`, `Alacritty`, `kitty` |
| 可执行文件 | `WindowsTerminal.exe`, `wt.exe`, `gnome-terminal-server` |
| 进程名 | `konsole`, `xterm`, `tilix`, `terminator` |

支持的终端：macOS Terminal、iTerm2、Alacritty、Kitty、WezTerm、Warp、Hyper、Ghostty、Tabby、Windows Terminal、conhost、cmd、PowerShell、mintty、GNOME Terminal、Konsole、xterm、tilix、Terminator、XFCE Terminal、urxvt。

## 3、进程树遍历

### query_blocking(root_pid)

1. `System::new_all()` 刷新所有进程信息
2. `descendants_of(root_pid)` 递归收集子进程
3. 遍历候选进程：
   - **Shell 进程**：匹配 18 种 Shell 名称（bash、zsh、fish、sh、dash、ash、ksh、tcsh、csh、pwsh、powershell、cmd.exe、nu、elvish、xonsh 等）
   - **运行中命令**：非 Shell 且非黑名单（login、tmux、screen、less、more、tail）
4. 按 create_time 降序排序（最新的在前）

### Shell cwd 来源

| 来源 | 优先级 | confidence | 说明 |
|------|--------|-----------|------|
| Shell 钩子文件 | 高 | 0.9 | `~/.active_tracker/shells/<PID>.cwd` |
| 进程 cwd | 低 | 0.8 | sysinfo `proc_.cwd()` |

## 4、Shell 钩子文件

### shell_files.rs

读取 `~/.active_tracker/shells/` 目录下的 `.cwd` 文件：

```rust
pub fn read_shell_cwds() -> HashMap<u32, String>
```

1. 扫描目录中的 `*.cwd` 文件
2. 解析文件名为 PID
3. 检查 PID 是否存活（sysinfo），已死亡的删除文件
4. 读取文件内容（去除 BOM 和空白）

## 5、数据结构

```rust
pub struct TerminalContext {
    pub source: String,                  // "process_tree"
    pub shells: Vec<TerminalProcess>,    // Shell 进程列表
    pub running: Vec<TerminalProcess>,   // 运行中的子命令
}

pub struct TerminalProcess {
    pub pid: u32,
    pub name: String,                    // 进程名
    pub cwd: Option<String>,             // 工作目录
    pub cmdline: Vec<String>,            // 命令行（已脱敏）
    pub cmdline_redacted: bool,          // 是否有脱敏
    pub create_time: Option<f64>,
    pub is_shell: bool,                  // 是否为 Shell
    pub cwd_source: String,              // "shell_file" / "process"
}
```

## 6、命令行脱敏

`tools::redact_cmdline()` 对敏感信息进行脱敏：

| 模式 | 示例 | 脱敏结果 |
|------|------|---------|
| `--password=value` | `--password=secret123` | `--password=***` |
| `--token value` | `--token sk-abc...xyz` | `--token sk-***yz` |
| AWS Key | `AKIA1234567890ABCDEF` | `AKI***EF` |
| GitHub Token | `ghp_xxxx...` | `ghp***xx` |
| Hex 密钥 | 40+ 字符十六进制 | 前3+后2 |

---

- 上一篇：[02-file-manager.md](./02-file-manager.md)
- 下一篇：[04-browser-bridge.md](./04-browser-bridge.md)
- 返回索引：[docs/README.md](../../README.md)
