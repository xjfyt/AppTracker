> **对应代码**：`tracker-core/src/diagnostics.rs`, `tracker-core/src/platform/`, `tracker-core/src/api/mod.rs`
> **维护提示**：发现新问题模式时同步更新本文档。

# 二十九、故障排查

## 1、常见问题

### API 无法连接

**症状**：桌面 UI 显示 "disconnected"，浏览器扩展 Badge 为红色

**排查步骤**：

1. 确认 AppTracker 核心已启动（Tauri 窗口已打开）
2. 检查端口占用：`netstat -ano | findstr :5007`
3. 检查防火墙是否阻止本地连接
4. 查看日志中的绑定错误

**解决**：端口被占用时 AppTracker 自动回退到 5008-5012，UI 和扩展会自动扫描。

### 浏览器扩展不工作

**症状**：Badge 显示 `!`，UI 显示"等待浏览器扩展连接"

**排查步骤**：

1. 确认扩展已安装并启用
2. 点击扩展图标查看 popup 状态
3. 确认 token 已同步（popup 中显示 "connected"）
4. 检查浏览器控制台是否有 WebSocket 错误

**解决**：
- 手动复制 UI 中的"浏览器插件 Key"，粘贴到扩展 popup 的 Token 输入框
- 确认扩展有 `tabs` 和 `activeTab` 权限

### macOS 窗口识别失败

**症状**：`info.errors` 包含 "osascript unavailable" 或 "Automation permission"

**排查步骤**：

1. 打开 系统偏好设置 → 隐私与安全 → 辅助功能
2. 确认 AppTracker（或终端应用）已勾选
3. 打开 系统偏好设置 → 隐私与安全 → 自动化
4. 确认 AppTracker 有权控制 System Events

**解决**：首次运行时 macOS 会弹出权限请求对话框，点击"允许"。

### Linux Wayland 下功能受限

**症状**：`info.errors` 包含 "Running under Wayland"

**说明**：Wayland 安全模型限制了通用前台窗口捕获。X11 会话下功能完整。

**解决**：切换到 X11 会话，或等待 Wayland 原生支持。

### Windows Office 文档检测不到

**症状**：打开 Word/Excel 文件但 `document_paths` 为空

**排查步骤**：

1. 确认 Office 应用已启动（COM 对象需要运行中的实例）
2. 检查 PowerShell 执行策略：`Get-ExecutionPolicy`
3. 查看日志中是否有 COM 超时

**解决**：WPS Office 需要确认 ProgId 正确（KWPS.Application 等）。

## 2、崩溃日志

### 位置

`~/.active_tracker/crash.log`

### 格式

```
==== panic @ ts=<timestamp> thread=<thread_name> ====
<panic_info>
backtrace:
<backtrace>
```

### 分析

1. 查看 `thread` 字段确定哪个 worker 崩溃（`window_monitor` / `window_enrichment`）
2. 查看 backtrace 定位具体代码位置
3. `supervised()` 会自动重启崩溃的 worker，2 秒后恢复

## 3、性能问题

### CPU 占用高

**可能原因**：
- 轮询间隔过低（`poll_interval_ms` < 100）
- UIA 树扫描频繁（Windows 上某些应用触发）
- rdev 监听线程异常

**解决**：
- 增大 `poll_interval_ms`
- 检查 `should_scan_uia()` 的匹配列表

### 内存占用高

**可能原因**：
- 截图 PNG 未及时清理
- broadcast channel 积压

**解决**：
- 关闭截图功能（`POST /api/v1/capture {"enabled": false}`）
- 确认客户端及时消费 WebSocket/SSE 事件

## 4、日志调试

```bash
# 启用调试日志
RUST_LOG=tracker_core=debug npm run tauri dev

# 仅查看窗口轮询
RUST_LOG=tracker_core=debug 2>&1 | grep "window_monitor"

# 查看富化管线
RUST_LOG=tracker_core=debug 2>&1 | grep "enrich"
```

---

- 上一篇：[01-coding-standards.md](./01-coding-standards.md)
- 下一篇：[03-roadmap.md](./03-roadmap.md)
- 返回索引：[docs/README.md](../README.md)
