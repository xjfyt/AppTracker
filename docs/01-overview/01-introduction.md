> **对应代码**：`tracker-core/src/agent.rs`, `tracker-core/src/models.rs`
> **维护提示**：修改项目定位或核心功能时同步更新本文档。

# 一、项目简介

## 1、概述

AppTracker 是一款跨平台桌面活动追踪器，持续监控前台窗口、打开的文档、终端工作目录、浏览器标签页、键盘/鼠标活动，以及可选的窗口截图。所有采集的状态通过单一本地 HTTP/WebSocket/SSE 端口（默认 5007）对外暴露。

项目采用 Rust + Tauri v2 + 原生 HTML/CSS/JS 构建，核心逻辑封装在 `tracker-core` 库中，桌面壳层由 Tauri 提供。

## 2、核心能力

| 能力 | 说明 |
|------|------|
| 前台窗口追踪 | 250ms 轮询当前活动窗口，采集应用名、标题、PID、几何信息 |
| 文档路径识别 | 从窗口标题、命令行、Office COM、UIA 树、文件管理器、终端 cwd 等多源提取文档路径 |
| 终端上下文 | 进程树遍历识别 18 种 Shell，读取 shell hook 文件获取真实 cwd |
| 浏览器标签页 | 通过浏览器扩展 WebSocket 桥接上报当前标签 URL/标题 |
| 键鼠活动统计 | 60 秒滑动窗口统计按键、点击、滚动、鼠标距离、空闲时长 |
| 窗口截图 | 2 秒间隔采集前台窗口截图，下采样至 480px PNG |
| 实时事件推送 | REST 快照 + WebSocket 双向 + SSE 单向三种 API |
| 跨平台支持 | Windows（Win32 + COM + UIA）、macOS（AppleScript + AX + lsof）、Linux（X11 + /proc + AT-SPI） |

## 3、工作空间结构

```
AppTracker/
├── Cargo.toml              # Workspace 根
├── tracker-core/           # 核心库（平台无关逻辑 + 平台适配）
│   └── src/
│       ├── agent.rs        # 入口：start_agent()、窗口轮询、DocumentMemory
│       ├── models.rs       # 所有数据结构
│       ├── state.rs        # TrackerState（Arc<RwLock> + broadcast 事件总线）
│       ├── api/            # Axum HTTP/WS/SSE 服务
│       ├── platform/       # 平台抽象层（win32/macos/linux）
│       ├── integrations/   # 文件管理器/终端/shell 文件集成
│       ├── activity.rs     # 键鼠监控
│       ├── capture.rs      # 截图采集
│       ├── tools.rs        # 路径提取/分类/去重/命令行脱敏
│       ├── bridge.rs       # 浏览器扩展鉴权 token
│       └── diagnostics.rs  # panic hook → crash.log
├── desktop/
│   ├── src-tauri/          # Tauri 桌面壳
│   └── ui/                 # 静态前端（index.html + main.js + styles.css）
├── browser_extension/      # Chrome/Firefox MV3 浏览器扩展
└── shell_integration/      # bash/zsh/fish/pwsh/cmd shell 钩子
```

## 4、典型使用场景

- **开发效率分析**：追踪开发者在不同应用、文档间的切换模式
- **自动化上下文采集**：为 AI 助手提供当前工作上下文（前台应用、打开的文件、终端目录）
- **时间追踪**：统计各类活动的停留时间
- **工作流审计**：记录并回溯工作过程

---

- 上一篇：（无，这是首篇）
- 下一篇：[02-architecture.md](./02-architecture.md)
- 返回索引：[docs/README.md](../README.md)
