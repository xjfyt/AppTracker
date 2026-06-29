> **对应代码**：`tracker-core/src/platform/linux.rs`, `tracker-core/src/integrations/linux_dbus.rs`
> **维护提示**：修改 X11 命令或 D-Bus/AT-SPI 逻辑时同步更新本文档。

# 十七、Linux 平台实现

## 1、前台窗口查询

### active_window()

通过 xdotool/xprop 查询 X11 前台窗口：

```
xdotool getactivewindow                    → window_id
xprop -id <window_id> _NET_WM_NAME         → window_title
xprop -id <window_id> WM_CLASS             → window_class
xprop -id <window_id> _NET_WM_PID          → pid
xwininfo -id <window_id>                   → geometry
sysinfo::process_info(pid)                  → ProcessInfo
```

若 `xdotool` 不可用，回退到 `xprop -root _NET_ACTIVE_WINDOW`。

### Wayland 限制

检测 `XDG_SESSION_TYPE == "wayland"` 时，在 `info.errors` 中记录警告。Wayland 下通用前台窗口捕获受限。

### 超时

所有外部命令调用超时 700ms。

## 2、文档富化

### enrich_platform_window_documents()

两阶段富化：

#### 阶段一：/proc/PID/fd 扫描

读取 `/proc/PID/fd/<n>` 符号链接，获取进程打开的文件：

1. 遍历 `/proc/PID/fd/` 目录
2. `read_link` 获取目标路径
3. 过滤非文件 fd（socket、pipe、/dev/*、/proc/*、/sys/*）
4. 匹配标题中的文件名（`fd:title_match`, confidence: 0.92）
5. 或匹配已知文档扩展名（`fd`, confidence: 0.45）
6. 扫描上限 4000 条

#### 阶段二：AT-SPI Document 接口

通过 D-Bus AT-SPI 无障碍总线查询文档 URL：

```rust
pub async fn document_url_for(info: &WindowInfo) -> Vec<DocumentSource>
```

1. 连接 AT-SPI a11y bus（通过 `org.a11y.Bus` 获取地址）
2. 在注册表中查找匹配 PID 的应用
3. 查询 `org.a11y.atspi.Document` 接口的 `DocURL` 属性
4. `atspi:document`, confidence: 0.95

#### 阶段三：LibreOffice argv

检测 LibreOffice 进程（soffice/libreoffice/oosplash），从 `/proc/PID/cmdline` 提取文件参数：

- `libreoffice:argv`, confidence: 0.85

## 3、AT-SPI 详解（linux_dbus.rs）

### 架构

```
Session Bus (org.a11y.Bus)
  │ get_address()
  ▼
A11y Bus (独立总线)
  │
  ├─ Registry (org.a11y.atspi.Registry)
  │    │ get_children()
  │    ▼
  │  Application[] (按 PID 匹配)
  │    │ get_children()
  │    ▼
  │  Accessible 树 (遍历，上限 400 节点)
  │    ├─ Text 接口 → get_text() → 路径检测
  │    └─ Document 接口 → get_attribute_value("DocURL")
  │
  └─ file_manager_state()
       │ 遍历 Text 节点
       ▼
       FileManagerState { folder, selected_items }
```

### 防御性设计

- 每次 D-Bus 调用超时 200ms
- 整体连接超时 700ms
- 节点遍历上限 400
- AT-SPI bus 不可用时静默返回 None

## 4、xprop 解析

### 窗口标题

```rust
fn parse_xprop_string(text: &str, key: &str) -> Option<String>
```

优先 `_NET_WM_NAME`，回退 `WM_NAME`。

### WM_CLASS

取引号分隔的最后一个值（实例名）。

### 窗口几何

从 `xwininfo` 输出解析 `Absolute upper-left X/Y` 和 `Width/Height`。

---

- 上一篇：[03-macos.md](./03-macos.md)
- 下一篇：[01-overview.md](../04-integrations/01-overview.md)
- 返回索引：[docs/README.md](../../README.md)
