> **对应代码**：`tracker-core/src/lib.rs`
> **维护提示**：新增或移除模块时同步更新本文档。

# 八、模块总览

## 1、模块依赖关系

```
lib.rs（公开 API）
  ├── agent.rs          ← 入口：start_agent(), AgentConfig, AgentHandle
  ├── state.rs          ← TrackerState（核心状态容器）
  ├── models.rs         ← 所有数据结构定义
  ├── api/              ← Axum HTTP/WS/SSE 服务
  │   └── mod.rs
  ├── platform/         ← 平台抽象层
  │   ├── mod.rs        ← process_info(), collect_title_and_cwd_documents()
  │   ├── windows.rs    ← Win32 GetForegroundWindow + Office COM + UIA
  │   ├── macos.rs      ← AppleScript + AX + lsof
  │   └── linux.rs      ← xdotool/xprop + /proc/fd + AT-SPI
  ├── integrations/     ← 外部集成
  │   ├── mod.rs        ← enrich_window() 编排
  │   ├── file_manager.rs ← Explorer COM / Finder AS / D-Bus
  │   ├── terminal.rs   ← 进程树遍历 + 18 种 Shell
  │   ├── shell_files.rs ← 读取 .cwd 文件
  │   └── linux_dbus.rs ← AT-SPI 无障碍总线
  ├── activity.rs       ← 键鼠监控（rdev）
  ├── capture.rs        ← 截图采集（screenshots + image）
  ├── tools.rs          ← 路径工具（提取/分类/去重/脱敏）
  ├── bridge.rs         ← 浏览器扩展 token 管理
  └── diagnostics.rs    ← panic hook → crash.log
```

## 2、Feature 控制

`lib.rs` 使用条件编译控制可选模块：

```rust
#[cfg(feature = "activity")]
pub mod activity;

#[cfg(feature = "capture")]
pub mod capture;

// 禁用时提供空实现
#[cfg(not(feature = "activity"))]
pub mod activity { pub fn spawn_activity_monitor(...) {} }

#[cfg(not(feature = "capture"))]
pub mod capture { pub fn spawn_screen_capture(...) {} }
```

## 3、公开 API

`lib.rs` 导出的核心类型：

| 类型 | 来源 | 说明 |
|------|------|------|
| `AgentConfig` | agent.rs | 启动配置 |
| `AgentHandle` | agent.rs | 运行时句柄（state + api + window_task） |
| `TrackerState` | state.rs | 状态容器 |
| `start_agent()` | agent.rs | 启动入口函数 |

## 4、模块职责速查

| 模块 | 核心职责 | 关键函数 |
|------|---------|---------|
| `agent` | 窗口轮询主循环、DocumentMemory、supervised 重启 | `start_agent()`, `run_window_monitor()` |
| `state` | 线程安全状态存储 + 事件广播 | `TrackerState::update_window()`, `subscribe()` |
| `models` | 数据结构定义 | `WindowInfo`, `ActivityStats`, `Snapshot` |
| `api` | HTTP/WS/SSE 端点 | `spawn_api()`, `router()` |
| `platform` | 前台窗口查询 + 平台文档富化 | `active_window()`, `enrich_platform_window_documents()` |
| `integrations` | 文件管理器/终端/shell 文件集成 | `enrich_window()`, `file_manager::query()` |
| `activity` | 键鼠活动统计 | `spawn_activity_monitor()` |
| `capture` | 窗口截图采集 | `spawn_screen_capture()` |
| `tools` | 路径提取/分类/去重/脱敏 | `extract_paths_from_title()`, `redact_cmdline()` |
| `bridge` | 浏览器扩展 token | `load_or_create_token()` |
| `diagnostics` | panic 崩溃日志 | `install_panic_hook()` |

---

- 上一篇：[01-config-file.md](../03-config/01-config-file.md)
- 下一篇：[01-overview.md](./02-agent-core/01-overview.md)
- 返回索引：[docs/README.md](../README.md)
