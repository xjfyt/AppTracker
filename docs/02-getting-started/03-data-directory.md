> **对应代码**：`tracker-core/src/bridge.rs`, `tracker-core/src/diagnostics.rs`, `tracker-core/src/integrations/shell_files.rs`
> **维护提示**：新增文件存储路径时同步更新本文档。

# 六、数据目录

## 1、目录结构

```
~/.apptracker/
└── token                    # 浏览器扩展鉴权 token（Base64 URL-safe，32 字节随机）

~/.active_tracker/
├── crash.log                # Panic 崩溃日志（追加写入，含 backtrace）
└── shells/
    ├── 12345.cwd            # PID 12345 的 shell 当前工作目录
    ├── 12345.cmd            # PID 12345 的最近一条命令
    ├── 67890.cwd
    └── 67890.cmd
```

## 2、Token 文件

`~/.apptracker/token` 是浏览器扩展与 AppTracker API 之间的共享鉴权凭证。

- 首次启动时由 `bridge::load_or_create_token()` 生成（32 字节随机 → Base64 URL-safe 编码）
- 若检测到旧路径 `~/.active_tracker/token`，自动迁移至新路径
- Unix 系统上文件权限设为 `0o600`（仅所有者可读写）
- 浏览器扩展通过 `GET /api/v1/bridge_token` 获取 token

## 3、Shell 钩子文件

Shell 集成脚本在每次提示符显示时写入 `.cwd` 文件：

| 文件 | 内容 | 写入时机 |
|------|------|---------|
| `<PID>.cwd` | 当前工作目录绝对路径 | 每次 PROMPT_COMMAND / precmd / fish_prompt |
| `<PID>.cmd` | 最近一条命令（仅 bash/pwsh） | 每次 PROMPT_COMMAND |

读取逻辑在 `integrations/shell_files.rs::read_shell_cwds()`：

1. 扫描 `~/.active_tracker/shells/` 目录
2. 解析文件名为 PID
3. 检查 PID 是否仍存活（sysinfo），已死亡的自动删除 `.cwd` 文件
4. 返回 `HashMap<u32, String>`（PID → cwd 路径）

## 4、崩溃日志

`~/.active_tracker/crash.log` 由 `diagnostics::install_panic_hook()` 管理：

- 追加写入（不覆盖历史记录）
- 每条记录包含：时间戳、线程名、panic 信息、完整 backtrace
- 同时输出到 stderr（方便 `npm run dev` 终端查看）

示例条目：
```
==== panic @ ts=1719600000 thread=window_monitor ====
panicked at 'explicit panic', tracker-core/src/agent.rs:100:5
backtrace:
   0: ...
```

## 5、临时数据

截图数据仅保存在内存中（`TrackerState.inner.latest_screenshot_png`），不写入磁盘。进程退出后自动释放。

---

- 上一篇：[02-run-and-deploy.md](./02-run-and-deploy.md)
- 下一篇：[01-config-file.md](../03-config/01-config-file.md)
- 返回索引：[docs/README.md](../README.md)
