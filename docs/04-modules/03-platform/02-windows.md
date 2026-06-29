> **对应代码**：`tracker-core/src/platform/windows.rs`
> **维护提示**：修改 Win32 API 调用或 PowerShell 脚本时同步更新本文档。

# 十五、Windows 平台实现

## 1、前台窗口查询

### active_window()

通过 `tokio::task::spawn_blocking` 在阻塞线程中调用 Win32 API：

```
GetForegroundWindow()           → HWND
GetWindowTextW(hwnd)            → window_title
GetClassNameW(hwnd)             → window_class
GetWindowThreadProcessId(hwnd)  → pid
GetWindowRect(hwnd)             → geometry (x, y, width, height)
sysinfo::process_info(pid)      → ProcessInfo
```

### 输出

```rust
WindowInfo {
    platform: "win32",
    window_id: Some(hwnd_as_string),     // HWND 地址转字符串
    window_title: "...",
    window_class: Some("CabinetWClass"), // Explorer 等
    geometry: Some(WindowGeometry { x, y, width, height }),
    process: Some(ProcessInfo { pid, name, executable, cmdline, cwd, ... }),
    extra: {"hwnd_hex": "0x1234", "thread_id": 1234},
}
```

## 2、文档富化

### enrich_platform_window_documents()

通过 HWND 判断是否需要富化：

1. **Office COM 检测**（`is_office_like`）：
   - 匹配 `winword`, `excel`, `powerpnt`, `wps`, `kwps`, `ket`, `wpp` 等
   - 运行 PowerShell 脚本通过 `Marshal::GetActiveObject` 获取 COM 对象
   - 遍历 Word.Documents / Excel.Workbooks / PowerPoint.Presentations
   - 活动文档 confidence: 0.99，其他文档 0.95

2. **UIA 树扫描**（`should_scan_uia`）：
   - 匹配 Typora、Notepad++、VS Code、Obsidian、Acrobat、WPS 等
   - 运行 PowerShell 脚本通过 `UIAutomationClient` 遍历 UIA 树
   - 提取 `Name` 和 `ValuePattern.Value` 属性
   - 扫描上限 260 个节点，confidence: 0.75

### PowerShell 脚本执行

```rust
fn run_powershell_utf8(script: &str, timeout: Duration) -> Option<String>
```

- 参数：`-NoLogo -NoProfile -ExecutionPolicy Bypass -Command`
- 超时：Office COM 900ms，UIA 扫描 1200ms
- 编码处理：自动检测 UTF-16LE BOM、UTF-16BE、UTF-8

## 3、支持的 Office 应用

| ProgId | 应用 | 文档集合 |
|--------|------|---------|
| `Word.Application` | Microsoft Word | Documents |
| `KWPS.Application` | WPS 文字 | Documents |
| `Excel.Application` | Microsoft Excel | Workbooks |
| `KET.Application` | WPS 表格 | Workbooks |
| `PowerPoint.Application` | Microsoft PowerPoint | Presentations |
| `KWPP.Application` | WPS 演示 | Presentations |

## 4、UIA 扫描目标

| 应用 | 匹配关键词 |
|------|-----------|
| Typora | typora |
| Notepad / Notepad++ | notepad, notepad++ |
| VS Code | code.exe, visual studio code |
| Obsidian | obsidian |
| Adobe Acrobat | acrobat, acrord |
| Foxit Reader | foxit |
| SumatraPDF | sumatrapdf |
| WPS 全家桶 | wps, kwps, ket, wpp |

---

- 上一篇：[01-overview.md](./01-overview.md)
- 下一篇：[03-macos.md](./03-macos.md)
- 返回索引：[docs/README.md](../../README.md)
