> **对应代码**：全项目
> **维护提示**：完成路线图项目或新增计划时同步更新本文档。

# 三十、路线图

## 1、已完成

- [x] 核心窗口监控（250ms 轮询 + 去重）
- [x] 跨平台支持（Windows/macOS/Linux）
- [x] Office/WPS COM 文档检测
- [x] UIA/AX 无障碍树扫描
- [x] 文件管理器集成（Explorer/Finder/D-Bus）
- [x] 终端上下文检测（18 种 Shell）
- [x] Shell 钩子集成（bash/zsh/fish/pwsh/cmd）
- [x] 浏览器扩展桥接（Chrome/Firefox MV3）
- [x] REST/WebSocket/SSE API
- [x] 键鼠活动统计
- [x] 窗口截图采集
- [x] DocumentMemory 标题→路径记忆
- [x] supervised 自动重启容错
- [x] 命令行脱敏
- [x] 桌面 UI（Tauri + 原生 HTML/CSS/JS）
- [x] 诊断面板

## 2、计划中

### P0 — 高优先级

- [ ] Wayland 原生支持（通过 `xdg-foreign` 或 `wlr-foreign-toplevel`）
- [ ] 持久化存储（SQLite 记录历史窗口/活动数据）
- [ ] 截图存储到磁盘（可选）

### P1 — 中优先级

- [ ] 多显示器支持（geometry.screen_index 实际使用）
- [ ] 浏览器扩展 Firefox MV3 完整测试
- [ ] 活动统计图表（前端可视化）
- [ ] 配置文件支持（TOML/YAML）

### P2 — 低优先级

- [ ] 多语言 UI
- [ ] 插件系统（自定义富化源）
- [ ] 远程 API 访问（认证机制）
- [ ] macOS 原生 Swift 替代 AppleScript

## 3、已知限制

| 限制 | 平台 | 说明 |
|------|------|------|
| Wayland 前台窗口 | Linux | 安全模型限制，需 X11 会话 |
| Electron 应用文档 | macOS | AX 属性不可用，依赖 lsof 回退 |
| sandboxed 应用 | macOS | lsof 可能受限 |
| cmd.exe cwd | Windows | 需要 doskey 劫持，不如 pwsh 可靠 |
| 截图权限 | macOS | 需要屏幕录制权限 |

---

- 上一篇：[02-troubleshooting.md](./02-troubleshooting.md)
- 下一篇：[01-doc-writing-rules.md](../06-conventions/01-doc-writing-rules.md)
- 返回索引：[docs/README.md](../README.md)
