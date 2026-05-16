# AppTracker 文档

本目录沉淀 AppTracker 的核心实现说明，方便回顾与协作。

| 文档 | 内容 |
| --- | --- |
| [architecture.md](./architecture.md) | 总体架构、进程拓扑、数据流 |
| [agent-core.md](./agent-core.md) | tracker-core 内部模块：窗口轮询、文档记忆、富化管线 |
| [api.md](./api.md) | REST / WebSocket / SSE 接口及事件格式 |
| [platform.md](./platform.md) | Windows / macOS / Linux 平台采集与 Office/WPS COM 路径 |
| [integrations.md](./integrations.md) | 浏览器扩展、文件管理器、终端、shell cd 集成 |
| [capture.md](./capture.md) | 截图开关、降采样与生命周期 |
| [ui.md](./ui.md) | 桌面 UI（Tauri）渲染策略与组件 |
