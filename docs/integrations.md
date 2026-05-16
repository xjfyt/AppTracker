# 集成层

`integrations/` 把"窗口之外"的上下文塞回 `WindowInfo`：

```rust
pub async fn enrich_window(info: WindowInfo) -> WindowInfo {
    info = enrich_platform_window_documents(info).await;
    info.file_manager_state = file_manager::query(&info).await;
    info.terminal_context = terminal::query(&info).await;
    merge_into_document_paths(&mut info);
    info
}
```

`merge_into_document_paths` 会把每个 source 重新拼回 `document_paths`，给文件管理器路径、终端 cwd 加置信度（活跃窗口 0.95，否则 0.7；shell_file 来源 0.9）。

## 文件管理器（file_manager.rs）

- Windows：枚举 Explorer COM 对象，读取 `LocationURL` + `SelectedItems`。
- macOS：AppleScript 抓 Finder `target of front window` 和 `selection`。
- Linux：尝试 Nautilus/Dolphin 的 D-Bus 接口；不可用时退而求其次。

输出 `FileManagerState { source, windows: [{folder, selected_items, is_active}] }`，UI 渲染为卡片。

## 终端（terminal.rs）

- 找前台进程的子进程树，匹配 `SHELL_NAMES`（bash/pwsh/cmd/zsh/...）和 `TERMINAL_EXECUTABLES`。
- 每个 shell 进程都尝试两条路径拿到 cwd：
  1. `sysinfo` 直接读 cwd（`cwd_source="proc"`）。
  2. 失败时回退 `shell_files::read_shell_cwds` 读取由 shell hook 写下的 cwd 文件（`cwd_source="shell_file"`，置信度 0.9）。
- `running` 列出 shell 下当前运行的非黑名单子进程，命令行经 `redact_cmdline` 脱敏后展示。

## shell cd 集成（shell_integration/）

- 提供 PowerShell（`profile.ps1`）和 CMD（`cmd.cmd` + `install_windows.cmd`）的 cd hook：
  - 把当前 cwd 写到 `%LOCALAPPDATA%/AppTracker/cwd/<pid>.txt`（含原子写）。
  - `shell_files::read_shell_cwds` 在采集时按 pid 反查这些文件。
- `install_windows.ps1` 注入 profile，`install_windows.cmd` 注册 AutoRun。卸载就是反向删除。

## 浏览器扩展（同端口的 `/api/v1/browser`）

- agent 启动时 `bridge::load_or_create_token` 读取（或生成）`~/.apptracker/token`；如果用户来自老版本，会自动从 `~/.active_tracker/token` 迁移过来。
- 扩展首次启动会调 `GET /api/v1/bridge_token` 自动同步 token，用户也可以在 popup 里手动「Sync」一次；不再需要手工粘贴文件内容。
- WS 连上 `/api/v1/browser` 后第一帧必须是 `{"token": "<bridge_token>"}`，校验失败立即断开。
- 协议：扩展每次 active tab 变化发 `{"type":"tab_update", "browser":"...", "windowId":..., "tabId":..., "url":"...", "title":"...", ...}`，桥转写 `state.update_browser_tab` → 触发 `browser_tab_updated` 事件。
