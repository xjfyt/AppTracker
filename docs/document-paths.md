# 文档路径来源与分类

`WindowInfo.document_paths` 是 AppTracker 最容易出现"噪声"的字段——同一帧里可能既有用户真正打开的文档，又有进程的 cwd、启动目录、命令行参数里偶然命中的安装文件。本文记录现在的分类规则。

## 数据结构

```rust
pub struct DocumentSource {
    pub path: String,
    pub kind: String,       // "file" | "folder" | "unknown"
    pub source: String,     // 见下表
    pub confidence: f32,    // 0.0 - 1.0
    pub category: DocumentCategory, // User | Process
}
```

## 各 `source` 的分类

| source | 来源 | category | 备注 |
| --- | --- | --- | --- |
| `cwd` | 进程当前工作目录 | **Process** | 大多数 Windows GUI 程序的 cwd 是 `C:/Windows/System32` 之类，纯噪声 |
| `cmdline` | 命令行参数里能落地到磁盘的 token | User | 多数情况下就是"用 notepad 打开的那个 doc" |
| `title` | 解析窗口标题中的路径片段 | User | |
| `title_filename` | 标题里像文件名的部分 + 候选目录 | User | 置信度 0.55 |
| `title_memory` | `DocumentMemory` 用历史绝对路径补回 | User | 置信度 0.88 |
| `file_manager` | Explorer / Finder / 文件管理器当前目录 | User | 0.95 / 0.7 |
| `file_manager_selection` | Explorer 选中项 | User | 0.95 / 0.7 |
| `terminal:<shell>` | 终端 shell cwd | User | 0.9（shell hook） / 0.8（proc） |
| `office:word` / `office:excel` / `office:powerpoint` | COM 直接读取 Office/WPS 打开的文档 | User | 当前活动文档 0.99，其它 0.95 |
| `uia:value` / `uia:name` | UIA 抓 ValuePattern / Name | User | 0.75 |

## 默认行为

- API/UI 始终返回完整 `document_paths`（含 category 标签）。
- UI 默认只渲染 `category=user`，可通过开关「显示进程上下文」切换显示 process 类。
- 此外，无论 category，凡是落在 **当前前台进程可执行文件所在目录**（含子目录）里的路径都会在后端被丢弃。这条规则的目的是把"C:/Program Files/<App>/resources/locale.json"之类的纯安装包内文件全部过滤掉，但不会影响用户在 Explorer 里浏览 Program Files 的场景。

## 切换与持久化

- 开关字段：`TrackerState::show_process_paths`（默认 false）。
- API：`GET/POST /api/v1/show_process_paths`。
- 事件：`show_process_paths_changed`，UI 多端实时同步。
- 当前实现没有把状态持久化到磁盘——重启后会回到默认（即默认隐藏）。如果未来需要持久化，可以在 `state.rs` 加 JSON 文件落盘。

## 后续可扩展

- 用户自定义的"额外排除前缀"列表：再加一个 `Vec<String>`，按前缀屏蔽。
- 把 `category=process` 进一步细化为 `cwd` / `cmdline` / `launch_dir`，UI 提供分组。
