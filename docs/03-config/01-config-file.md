> **对应代码**：`tracker-core/src/agent.rs` (`AgentConfig`)
> **维护提示**：新增配置项时同步更新本文档。

# 七、配置文件

## 1、AgentConfig 结构体

AppTracker 的运行时配置通过 `AgentConfig` 结构体传递：

```rust
pub struct AgentConfig {
    pub host: String,           // API 绑定地址，默认 "127.0.0.1"
    pub api_port: u16,          // API 端口，默认 5007
    pub no_activity: bool,      // 禁用键鼠监控，默认 false
    pub no_capture: bool,       // 禁用截图采集，默认 false
    pub capture_default_on: bool, // 截图默认开启，默认 false
    pub poll_interval_ms: u64,  // 窗口轮询间隔（毫秒），默认 250
}
```

## 2、配置项说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `host` | String | `"127.0.0.1"` | API 服务器绑定的 IP 地址。设为 `"0.0.0.0"` 可允许局域网访问（不推荐） |
| `api_port` | u16 | `5007` | API 服务器端口。被占用时自动回退到 5008-5012 |
| `no_activity` | bool | `false` | 设为 `true` 禁用键鼠活动监控（rdev 监听线程不启动） |
| `no_capture` | bool | `false` | 设为 `true` 禁用截图采集功能 |
| `capture_default_on` | bool | `false` | 设为 `true` 时截图功能启动即开启（否则需通过 API 手动开启） |
| `poll_interval_ms` | u64 | `250` | 前台窗口轮询间隔。最小值 100ms，过低会增加 CPU 开销 |

## 3、运行时开关

除 `AgentConfig` 外，AppTracker 提供三个运行时可切换的开关，通过 REST API 控制：

| 开关 | API 端点 | 说明 |
|------|---------|------|
| `paused` | `POST /api/v1/pause` | 暂停所有采集（窗口、活动、截图） |
| `capture_enabled` | `POST /api/v1/capture` | 截图采集开关 |
| `show_process_paths` | `POST /api/v1/show_process_paths` | 是否显示进程上下文路径（cwd/启动目录） |

这三个开关的状态存储在 `TrackerState` 的原子标志中，进程重启后重置为默认值。

## 4、日志配置

日志通过 `RUST_LOG` 环境变量控制：

```bash
# 默认级别
RUST_LOG=tracker_core=info,apptracker=info

# 调试模式（查看窗口轮询细节）
RUST_LOG=tracker_core=debug

# 仅错误
RUST_LOG=tracker_core=error
```

## 5、Tauri 配置

Tauri 相关配置在 `desktop/src-tauri/tauri.conf.json` 中（由 Tauri CLI 管理），不在 `AgentConfig` 范围内。

---

- 上一篇：[03-data-directory.md](../02-getting-started/03-data-directory.md)
- 下一篇：[01-overview.md](../04-modules/01-overview.md)
- 返回索引：[docs/README.md](../README.md)
