> **对应代码**：`tracker-core/src/platform/mod.rs`
> **维护提示**：新增平台适配或修改公共接口时同步更新本文档。

# 十四、平台抽象层 — 概述

## 1、职责

平台抽象层（`platform/`）提供跨平台的前台窗口查询和文档路径富化能力。每个平台实现两个核心函数：

```rust
pub async fn active_window() -> anyhow::Result<WindowInfo>;
pub async fn enrich_platform_window_documents(info: WindowInfo) -> WindowInfo;
```

## 2、平台分发

`platform/mod.rs` 通过 `#[cfg(target_os)]` 条件编译选择平台实现：

```rust
#[cfg(target_os = "windows")]
pub use self::windows::{active_window, enrich_platform_window_documents};

#[cfg(target_os = "macos")]
pub use self::macos::{active_window, enrich_platform_window_documents};

#[cfg(target_os = "linux")]
pub use self::linux::{active_window, enrich_platform_window_documents};
```

不支持的平台返回空 WindowInfo + 错误信息。

## 3、公共辅助函数

### process_info(pid)

跨平台进程信息采集，基于 sysinfo：

```rust
pub fn process_info(pid: u32) -> Option<ProcessInfo> {
    // sysinfo: refresh_processes_specifics
    // 返回 pid, name, executable, cmdline, cwd, create_time, cpu_percent, memory_rss
}
```

### collect_title_and_cwd_documents(info)

通用文档提取（所有平台共享）：

1. `collect_cmdline_documents` — 遍历 cmdline 参数，尝试解析为文件路径
2. `extract_paths_from_title` — 正则提取标题中的 Windows/POSIX 路径
3. `collect_title_name_documents` — 从标题提取文件名，在常见目录搜索
4. cwd 记录 — 进程 cwd 作为 `category: Process` 的低置信度文档

### candidate_search_dirs(info)

标题文件名搜索的候选目录列表：

- 进程 cwd
- `~/`
- `~/Desktop`
- `~/Documents`
- `~/Downloads`
- `~/OneDrive/Desktop`
- `~/OneDrive/Documents`

## 4、平台能力对比

| 能力 | Windows | macOS | Linux |
|------|---------|-------|-------|
| 前台窗口 | Win32 GetForegroundWindow | AppleScript System Events | xdotool/xprop |
| 窗口标题 | GetWindowTextW | AppleScript name of winRef | xprop _NET_WM_NAME |
| 窗口几何 | GetWindowRect | AppleScript position+size | xwininfo |
| 进程信息 | sysinfo | sysinfo | sysinfo |
| Office 文档 | COM (GetActiveObject) | AppleScript (tell application) | LibreOffice argv |
| UIA/AX 文档 | UIAutomationClient | AXDocument/AXURL 属性 | AT-SPI Document |
| 文件描述符 | — | lsof -p PID | /proc/PID/fd |
| 截图 | screenshots crate | screenshots crate | screenshots crate |

---

- 上一篇：[05-activity-capture.md](../02-agent-core/05-activity-capture.md)
- 下一篇：[02-windows.md](./02-windows.md)
- 返回索引：[docs/README.md](../../README.md)
