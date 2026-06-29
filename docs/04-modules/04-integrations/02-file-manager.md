> **对应代码**：`tracker-core/src/integrations/file_manager.rs`
> **维护提示**：修改文件管理器检测逻辑或 COM/AppleScript 脚本时同步更新本文档。

# 十九、文件管理器集成

## 1、概述

文件管理器集成检测当前窗口是否为文件管理器，若是则提取当前目录和选中的文件/文件夹。

## 2、平台实现

### Windows — Explorer COM

检测条件：`window_class == "CabinetWClass"` 或 `executable ends_with "explorer.exe"`

通过 PowerShell 调用 Shell COM 对象：

```powershell
$shell = New-Object -ComObject Shell.Application
foreach ($w in $shell.Windows()) {
    # 遍历所有 Explorer 窗口
    $folder = $w.LocationURL          # file:///C:/Users/...
    $selected = $w.Document.SelectedItems()  # 选中项
}
```

输出格式：
```
W*|12345|C:\Users\demo\Documents     # 活跃窗口（W*=活跃，W=后台）
W|67890|C:\Users\demo\Downloads
S|12345|C:\Users\demo\Documents\report.docx  # 选中项
```

超时：1500ms

### macOS — Finder AppleScript

检测条件：`app_bundle_id == "com.apple.finder"` 或 `app_name == "Finder"`

```applescript
tell application "Finder"
    set sList to (get selection)           -- 选中项
    set wList to Finder windows            -- 所有窗口
    -- Desktop 回退：无窗口时返回 ~/Desktop
end tell
```

Desktop 回退：当没有 Finder 窗口但用户在桌面交互时，返回 `~/Desktop` 作为活跃文件夹。

超时：1200ms

### Linux — D-Bus + cwd/title 回退

检测方式：匹配 16 种文件管理器可执行文件名（nautilus、dolphin、nemo、thunar 等）

1. **D-Bus (AT-SPI)**：通过 `linux_dbus::file_manager_state()` 遍历 AT-SPI 无障碍树，提取路径文本
2. **cwd 回退**：读取进程 cwd
3. **标题回退**：从窗口标题解析文件夹名（"Documents — Files" → 搜索 ~/Documents）

## 3、数据结构

```rust
pub struct FileManagerState {
    pub source: String,                    // "explorer_com_powershell" / "finder_applescript" / ...
    pub windows: Vec<FileManagerWindow>,
}

pub struct FileManagerWindow {
    pub folder: String,                    // 当前目录路径
    pub selected_items: Vec<String>,       // 选中的文件/文件夹路径
    pub hwnd_or_id: Option<String>,        // 窗口标识
    pub is_active: bool,                   // 是否为活跃窗口
}
```

## 4、置信度

| 场景 | confidence | 来源 |
|------|-----------|------|
| 活跃文件管理器窗口 | 0.95 | `file_manager` / `file_manager_selection` |
| 后台文件管理器窗口 | 0.70 | `file_manager` / `file_manager_selection` |

---

- 上一篇：[01-overview.md](./01-overview.md)
- 下一篇：[03-terminal.md](./03-terminal.md)
- 返回索引：[docs/README.md](../../README.md)
