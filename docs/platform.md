# 平台采集层

`platform/` 给上层一个统一接口：

```rust
pub async fn active_window() -> anyhow::Result<WindowInfo>;
pub async fn enrich_platform_window_documents(WindowInfo) -> WindowInfo;
```

具体实现按 `cfg(target_os=…)` 切分到 `windows.rs`、`macos.rs`、`linux.rs`。

## Windows

[`platform/windows.rs`](../tracker-core/src/platform/windows.rs)：

- `GetForegroundWindow` 拿 HWND → 标题、类名、矩形、PID/TID。
- `process_info(pid)` 复用 `sysinfo` 一次性 refresh，避免每帧重建 System。
- `collect_title_and_cwd_documents` 在 [`platform/mod.rs`](../tracker-core/src/platform/mod.rs)：
  - 把命令行参数当 candidate 检查是否真实存在；
  - 用 `extract_paths_from_title` 解析标题里的可疑路径；
  - 把 cwd 加进 document_paths（低置信度 0.3）。
- **Office / WPS 走 COM**：`enrich_platform_window_documents` 异步在 spawn_blocking 里跑：
  - 判定窗口是 Office/WPS 类时，走 `office_documents()`（COM Automation：`Word.Application.Documents`, `Excel.Application.Workbooks`，包括 WPS 的 `KWPS.Application` / `KET.Application` 等）。
  - 其他文档型应用走 UIA（`UIAutomation` 抓 `ValuePattern`/`UIA_AutomationIdPropertyId` 等），便于 IDE、记事本等也能拿到打开的文件。
- 通过 `dedupe_documents` 合并相同路径，最高置信度优先。

## macOS

[`platform/macos.rs`](../tracker-core/src/platform/macos.rs)：

- 走 Accessibility API + NSWorkspace：拿前台 App、bundle id、窗口几何。
- AppleScript 桥用于浏览器/Office 的 doc 探测。
- Bundle id 用来识别终端、Finder（见 [integrations.md](./integrations.md)）。

## Linux

[`platform/linux.rs`](../tracker-core/src/platform/linux.rs)：

- 用 X11/Wayland 工具拿前台窗口（依赖运行环境）。
- 文件管理器主要走 D-Bus / `xdotool`，覆盖度比 macOS/Windows 弱。

## 通用辅助 — `tools.rs`

- `extract_paths_from_title`：兼容 Windows 反斜杠 / Unix 斜杠 / 引号。
- `classify_path` / `is_interesting_path`：基于扩展名 + 存在性，把候选标成 `file` / `folder` / `unknown`。
- `dedupe_documents`：按 normalize 后的 path 去重，保留 confidence 最高的来源。
- `likely_document_name_from_title`：仅返回标题里像"文件名"的那段，用于配合 `DocumentMemory` 把基础名补回绝对路径。
