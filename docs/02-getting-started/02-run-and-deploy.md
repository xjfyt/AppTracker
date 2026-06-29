> **对应代码**：`desktop/src-tauri/src/main.rs`, `tracker-core/src/agent.rs`
> **维护提示**：修改启动流程或部署方式时同步更新本文档。

# 五、运行与部署

## 1、启动流程

Tauri 桌面应用的启动入口在 `desktop/src-tauri/src/main.rs`：

```
main()
  → diagnostics::install_panic_hook()    // 安装全局 panic hook
  → tracing_subscriber::fmt()            // 初始化日志（RUST_LOG 环境变量控制级别）
  → tauri::Builder::default()
      .setup(|app| {
          tauri::async_runtime::spawn(
              start_agent(AgentConfig::default())
          )
      })
      .run()
```

`start_agent()` 内部依次：

1. 创建 `TrackerState`（RwLock + broadcast channel）
2. 加载或创建浏览器扩展鉴权 token（`~/.apptracker/token`）
3. 启动 API 服务器（Axum，端口 5007-5012 回退）
4. 启动键鼠活动监控（除非 `--no-activity`）
5. 启动截图采集（除非 `--no-capture`）
6. 启动窗口监控主循环（250ms 轮询）

## 2、环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RUST_LOG` | `tracker_core=info,apptracker=info` | 日志级别过滤 |

## 3、数据目录

AppTracker 使用 `~/.apptracker/` 和 `~/.active_tracker/` 两个目录：

| 路径 | 内容 |
|------|------|
| `~/.apptracker/token` | 浏览器扩展鉴权 token |
| `~/.active_tracker/shells/` | Shell 钩子写入的 `.cwd` 文件（按 PID 命名） |
| `~/.active_tracker/crash.log` | Panic 崩溃日志（带 backtrace） |

## 4、API 端口

默认监听 `127.0.0.1:5007`，端口被占用时自动尝试 5008-5012。浏览器扩展和桌面 UI 均内置相同的端口回退扫描。

## 5、Release 构建

Release 构建使用 Windows GUI subsystem（`#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]`），双击 `.exe` 不会弹出控制台窗口。Debug 构建保留 console subsystem 以便查看日志。

## 6、后台运行

AppTracker 设计为常驻后台服务：

- Tauri 桌面壳提供系统托盘窗口
- API 服务持续监听，浏览器扩展和外部客户端可随时连接
- 窗口监控主循环由 `supervised()` 保护，panic 自动重启

---

- 上一篇：[01-build.md](./01-build.md)
- 下一篇：[03-data-directory.md](./03-data-directory.md)
- 返回索引：[docs/README.md](../README.md)
