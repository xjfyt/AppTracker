> **对应代码**：全项目
> **维护提示**：修改编码规范时同步更新本文档。

# 二十八、编码规范

## 1、Rust 规范

### 命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | snake_case | `file_manager.rs`, `shell_files.rs` |
| 结构体 | PascalCase | `WindowInfo`, `TrackerState` |
| 函数 | snake_case | `active_window()`, `enrich_window()` |
| 常量 | SCREAMING_SNAKE_CASE | `MAX_THUMB_SIZE`, `SHELL_NAMES` |
| Feature | snake_case | `activity`, `capture` |

### 错误处理

- 使用 `anyhow::Result` 作为函数返回类型
- 使用 `?` 操作符传播错误
- 外部命令调用始终设置超时
- 平台 API 失败记录到 `info.errors` 而非 panic

### 异步

- 平台特定的阻塞调用通过 `tokio::task::spawn_blocking` 包装
- 外部命令通过 `std::process::Command` 在阻塞线程中执行
- `TrackerState` 的读写使用 `tokio::sync::RwLock`

### 平台条件编译

```rust
#[cfg(target_os = "windows")]
mod windows;

#[cfg(target_os = "macos")]
pub use self::macos::active_window;
```

### 测试

- 单元测试放在模块底部 `#[cfg(test)] mod tests`
- 测试使用临时目录，结束时清理
- 测试不依赖外部服务或特定桌面环境

## 2、前端规范

### JavaScript

- 原生 ES Modules（`type="module"`）
- 无框架（React/Vue），无构建步骤
- DOM 操作使用 `querySelector` / `innerHTML`
- 使用 `htmlCache` Map 避免重复设置 innerHTML
- 事件处理使用 `addEventListener`

### CSS

- CSS 变量主题系统
- BEM-like 命名（`.panel-head`, `.card-row`）

## 3、浏览器扩展规范

- MV3 Service Worker（`background.js`）
- `chrome.storage.local` 持久化配置
- 指数退避重连（1s → 30s）
- Badge 状态指示

## 4、Shell 集成规范

- 每个 shell 一个文件
- 写入 `~/.active_tracker/shells/<PID>.cwd`
- EXIT trap 清理文件
- 幂等加载（检查是否已集成）

## 5、提交规范

```
type(scope): 描述

body（可选）：原因与改动

Co-Authored-By: Claude
```

类型：`feat`, `fix`, `refactor`, `docs`, `test`, `chore`

---

- 上一篇：[01-overview.md](../04-modules/07-state/01-overview.md)
- 下一篇：[02-troubleshooting.md](./02-troubleshooting.md)
- 返回索引：[docs/README.md](../README.md)
