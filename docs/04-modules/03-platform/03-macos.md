> **对应代码**：`tracker-core/src/platform/macos.rs`
> **维护提示**：修改 AppleScript 脚本或 lsof 逻辑时同步更新本文档。

# 十六、macOS 平台实现

## 1、前台窗口查询

### active_window()

通过 AppleScript System Events 查询前台应用：

```applescript
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set pidVal to unix id of frontApp
    set bundleVal to bundle identifier of frontApp
    set titleVal to name of front window of frontApp
    set posVal to position of front window
    set sizeVal to size of front window
    return appName & tab & pidVal & tab & bundleVal & tab & titleVal & tab & x & tab & y & tab & w & tab & h
end tell
```

超时：900ms。若 osascript 不可用或超时，记录错误到 `info.errors`。

### 输出

```rust
WindowInfo {
    platform: "darwin",
    app_name: "Safari",
    app_bundle_id: Some("com.apple.Safari"),
    window_title: "Example Page",
    geometry: Some(WindowGeometry { x, y, width, height }),
    process: Some(ProcessInfo { ... }),
}
```

## 2、文档富化

### enrich_platform_window_documents()

三阶段富化：

#### 阶段一：AX 属性查询

通过 System Events 查询窗口的无障碍属性：

```applescript
tell application "System Events"
    set proc to first process whose unix id is {pid}
    set win to front window of proc
    set v to value of attribute "AXDocument" of win  -- 文档路径
    set v to value of attribute "AXURL" of win       -- 文档 URL
end tell
```

- `ax:doc` → confidence: 0.95
- `ax:url` → confidence: 0.9

#### 阶段二：Per-bundle AppleScript

根据 bundle ID 调用特定应用的 AppleScript 字典：

| Bundle ID | 应用 | 文档来源 |
|-----------|------|---------|
| `com.microsoft.Word` | Word | `full name of active document` |
| `com.microsoft.Excel` | Excel | `full name of active workbook` |
| `com.microsoft.Powerpoint` | PowerPoint | `full name of active presentation` |
| `com.google.Chrome` | Chrome | `URL of active tab of front window` |
| `company.thebrowser.Browser` | Arc | `URL of active tab of front window` |
| `com.brave.Browser` | Brave | `URL of active tab of front window` |
| `com.microsoft.edgemac` | Edge | `URL of active tab of front window` |
| `com.apple.Safari` | Safari | `URL of front document` |
| `com.sublimetext.4` | Sublime Text | `file name of active document` |
| `abnerworks.Typora` | Typora | 窗口名称（作为 lsof 标题提示） |

confidence: 0.99（Office 活动文档）/ 0.9（浏览器/编辑器）

#### 阶段三：lsof 回退

对于 Electron/Chromium 类应用（Typora 等），AX 和 AppleScript 可能无输出。通过 `lsof -p PID -F nt` 获取进程打开的文件列表：

1. 解析 lsof 输出（`f`=新文件条目，`t`=类型，`n`=路径名）
2. 仅保留 `REG`（常规文件）类型
3. 匹配标题中的文件名（`lsof:title_match`, confidence: 0.92）
4. 或匹配已知文档扩展名（`lsof`, confidence: 0.45）
5. 扫描上限 4000 条

## 3、超时处理

所有 osascript 调用均通过 `run_osascript()` 包装：

```rust
fn run_osascript(script: &str, timeout: Duration) -> Option<String>
```

- 超时后 kill 子进程
- 日志记录超时原因（通常是 Automation 权限弹窗阻塞）

## 4、权限要求

macOS 上 AppTracker 需要以下权限：

| 权限 | 用途 |
|------|------|
| Accessibility | System Events 窗口查询、AX 属性读取 |
| Automation (System Events) | AppleScript 执行 |
| Automation (各应用) | Per-bundle AppleScript（Office、浏览器等） |

---

- 上一篇：[02-windows.md](./02-windows.md)
- 下一篇：[04-linux.md](./04-linux.md)
- 返回索引：[docs/README.md](../../README.md)
