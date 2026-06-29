> **对应代码**：`tracker-core/src/integrations/mod.rs`, `tracker-core/src/platform/mod.rs`
> **维护提示**：新增富化源或修改富化顺序时同步更新本文档。

# 十二、富化管线

## 1、概述

富化管线（enrichment pipeline）将基础的前台窗口信息（仅含应用名、标题、PID）扩展为包含文档路径、文件管理器状态、终端上下文的完整 WindowInfo。

## 2、入口函数

```rust
pub async fn enrich_window(mut info: WindowInfo) -> WindowInfo {
    info = enrich_platform_window_documents(info).await;  // 平台特定文档
    let fm = file_manager::query(&info).await;            // 文件管理器
    let term = terminal::query(&info).await;              // 终端上下文
    info.file_manager_state = fm;
    info.terminal_context = term;
    merge_into_document_paths(&mut info);                  // 合并到 document_paths
    drop_paths_inside_install_dir(&mut info);              // 过滤安装目录噪声
    info
}
```

## 3、富化阶段

### 阶段一：平台文档富化

`platform::enrich_platform_window_documents()` 根据平台分发：

| 平台 | 实现 | 来源 |
|------|------|------|
| Windows | `windows.rs` | Office COM（Word/Excel/PPT + WPS）、UIA 树扫描 |
| macOS | `macos.rs` | AX 属性（AXDocument/AXURL）、per-bundle AppleScript、lsof 回退 |
| Linux | `linux.rs` | /proc/PID/fd、LibreOffice argv、AT-SPI Document 接口 |

### 阶段二：文件管理器检测

`file_manager::query()` 检测当前窗口是否为文件管理器：

| 平台 | 实现 | 检测方式 |
|------|------|---------|
| Windows | Explorer COM via PowerShell | `Shell.Application.Windows()` + `SelectedItems()` |
| macOS | Finder AppleScript | `tell application "Finder"` + selection + windows |
| Linux | D-Bus (AT-SPI) + cwd/title 回退 | `org.a11y.atspi` 遍历 + `/proc/PID/cwd` |

### 阶段三：终端上下文检测

`terminal::query()` 检测当前窗口是否为终端：

1. 通过 `detect_terminal()` 匹配 35+ 种终端可执行文件名/bundle ID
2. 遍历进程树，识别 18 种 Shell（bash/zsh/fish/pwsh/cmd/nu 等）
3. 读取 shell hook `.cwd` 文件获取真实 cwd
4. 区分 shell 进程和运行中的子命令

### 阶段四：通用文档提取

`platform::collect_title_and_cwd_documents()` 在所有平台上执行：

1. **命令行路径提取**：遍历 `process.cmdline`，尝试解析为文件路径
2. **标题路径提取**：用正则从窗口标题中提取 Windows/POSIX 路径
3. **标题文件名搜索**：从标题提取文件名，在常见目录（cwd、Desktop、Documents、Downloads）中搜索
4. **cwd 记录**：将进程 cwd 作为 `source: "cwd"`, `confidence: 0.3` 的文档

## 4、合并与过滤

### merge_into_document_paths

将文件管理器和终端的结果合并到 `document_paths`：

- 文件管理器文件夹 → `source: "file_manager"`, confidence: 0.95（活跃窗口）/ 0.7
- 文件管理器选中项 → `source: "file_manager_selection"`, confidence: 0.95/0.7
- 终端 shell cwd → `source: "terminal:{shell_name}"`, confidence: 0.9（shell_file）/ 0.8

### drop_paths_inside_install_dir

移除落在进程可执行文件所在目录（及其子目录）内的文档路径，过滤安装目录噪声。

## 5、置信度体系

| 置信度 | 来源 | 说明 |
|--------|------|------|
| 0.99 | `office:word:active` | Office 当前活动文档 |
| 0.95 | `file_manager`（活跃）、`ax:doc`、`atspi:document` | 高确信来源 |
| 0.92 | `lsof:title_match`、`fd:title_match` | FD 扫描 + 标题匹配 |
| 0.90 | `terminal:shell_file`、`browser:*` | Shell hook 文件、浏览器 AppleScript |
| 0.85 | `cmdline`、`libreoffice:argv` | 命令行参数 |
| 0.80 | `terminal:process`、`cmdline`（相对路径） | 进程 cwd 解析 |
| 0.75 | `uia:*` | UIA 树扫描 |
| 0.55 | `title_filename` | 标题文件名搜索 |
| 0.45 | `lsof`、`fd` | FD 扫描无标题匹配 |
| 0.30 | `cwd` | 进程 cwd（通常为噪声） |

## 6、文档分类（DocumentCategory）

| 类别 | 说明 |
|------|------|
| `User` | 来自用户真实操作（文件管理器、终端 cwd、Office 打开等） |
| `Process` | 来自进程自身上下文（cwd、启动目录），通常为噪声 |

UI 默认隐藏 `Process` 类别的路径，用户可通过 `show_process_paths` 开关显示。

---

- 上一篇：[03-document-memory.md](./03-document-memory.md)
- 下一篇：[05-activity-capture.md](./05-activity-capture.md)
- 返回索引：[docs/README.md](../../README.md)
