> **对应代码**：`tracker-core/src/integrations/mod.rs`
> **维护提示**：新增集成源或修改合并逻辑时同步更新本文档。

# 十八、集成层 — 概述

## 1、职责

集成层（`integrations/`）负责从外部系统采集窗口上下文信息，包括：

- 文件管理器当前目录和选中文件
- 终端 Shell 类型和工作目录
- Shell 钩子文件（`.cwd`）
- Linux D-Bus / AT-SPI 无障碍总线

## 2、入口函数

```rust
pub async fn enrich_window(mut info: WindowInfo) -> WindowInfo {
    info = enrich_platform_window_documents(info).await;  // 平台文档
    let fm = file_manager::query(&info).await;            // 文件管理器
    let term = terminal::query(&info).await;              // 终端
    info.file_manager_state = fm;
    info.terminal_context = term;
    merge_into_document_paths(&mut info);                  // 合并文档路径
    drop_paths_inside_install_dir(&mut info);              // 过滤安装目录
    info
}
```

## 3、模块结构

```
integrations/
├── mod.rs            ← enrich_window() 编排 + merge + 过滤
├── file_manager.rs   ← 文件管理器检测（Explorer/Finder/D-Bus）
├── terminal.rs       ← 终端检测（35+ 终端，18 种 Shell）
├── shell_files.rs    ← Shell 钩子 .cwd 文件读取
└── linux_dbus.rs     ← AT-SPI D-Bus 集成（仅 Linux）
```

## 4、合并策略

`merge_into_document_paths()` 将文件管理器和终端的结果合并到 `document_paths`：

1. 保留已有的非文件管理器/非终端来源的文档
2. 添加文件管理器文件夹（`source: "file_manager"`）
3. 添加文件管理器选中项（`source: "file_manager_selection"`）
4. 添加终端 shell cwd（`source: "terminal:{shell_name}"`）
5. 按 confidence 排序去重

## 5、安装目录过滤

`drop_paths_inside_install_dir()` 移除落在进程可执行文件所在目录内的文档路径。这过滤了应用安装目录中的噪声文件（如 Electron 应用的 `resources/app/` 下的文件）。

---

- 上一篇：[04-linux.md](../03-platform/04-linux.md)
- 下一篇：[02-file-manager.md](./02-file-manager.md)
- 返回索引：[docs/README.md](../../README.md)
