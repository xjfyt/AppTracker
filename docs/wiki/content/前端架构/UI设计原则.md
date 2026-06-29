# UI 设计原则

<cite>
**本文档引用的文件**
- [desktop/ui/styles.css](file://desktop/ui/styles.css)
- [desktop/ui/index.html](file://desktop/ui/index.html)
</cite>

## 目录

1. [简介](#简介)
2. [设计令牌](#设计令牌)
3. [组件系统](#组件系统)
4. [布局系统](#布局系统)
5. [响应式设计](#响应式设计)

## 简介

AppTracker UI 采用简洁的现代设计风格，使用 CSS 自定义属性作为设计令牌，确保视觉一致性。

## 设计令牌

### 颜色系统

```css
:root {
  --accent: #2563eb;          /* 主色调（蓝色） */
  --accent-soft: #dbeafe;     /* 主色调浅色背景 */
  --teal: #0f766e;            /* 暂停状态色 */
  --border: #d8dee8;          /* 边框色 */
  --border-soft: #e5eaf2;     /* 软边框色 */
  --muted: #667085;           /* 次要文字色 */
  --bg-card: #ffffff;         /* 卡片背景 */
  --bg-soft: #f8fafc;         /* 柔和背景 */
}
```

### Chip 颜色

| 类名 | 背景 | 文字 | 用途 |
|------|------|------|------|
| `.chip-primary` | `--accent-soft` | `#1e3a8a` | 主要标识 |
| `.chip-muted` | `#f1f5f9` | `--muted` | 次要信息 |
| `.chip-success` | `#dcfce7` | `#166534` | 成功/活跃 |
| `.chip-warn` | `#fef3c7` | `#92400e` | 警告 |
| `.chip-kind` | `#ede9fe` | `#5b21b6` | 类型标识 |
| `.chip-source` | `#e0f2fe` | `#075985` | 来源标识 |

## 组件系统

### Badge（状态徽章）

```css
.badge {
  border-radius: 999px;
  padding: 5px 10px;
  background: #fee2e2;  /* 默认：错误色 */
  color: #991b1b;
}
.badge.ok { background: #dcfce7; color: #166534; }
```

用于连接状态指示：`connecting`（红）/ `connected`（绿）/ `disconnected`（红）。

### Card（卡片）

```css
.card {
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 10px;
  background: var(--bg-soft);
  display: grid;
  gap: 6px;
}
```

用于文档路径、终端进程、浏览器标签等列表项。

### Switch（开关）

自定义 CSS-only 开关组件：

```css
.switch .track {
  width: 36px; height: 20px;
  background: #cbd5e1;
  border-radius: 999px;
}
.switch input:checked + .track { background: var(--accent); }
.switch input:checked + .track .thumb { transform: translateX(16px); }
```

用于截图开关、进程路径显示开关。

### Panel（面板）

```css
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  min-height: 160px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
```

### Metric（指标卡）

```css
.metric strong {
  display: block;
  font-size: 22px;
}
.metric .metric-label {
  color: var(--muted);
  font-size: 12px;
}
```

用于活动统计的大数字显示。

## 布局系统

### 顶部栏

```css
.topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
}
```

包含品牌标识、工具栏（截图开关、暂停按钮、API 地址、状态徽章）。

### 应用壳

```css
.app-shell {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr);
}
```

左侧 128px 侧边栏 + 右侧内容区。

### 当前状态视图

```css
.layout {
  display: grid;
  grid-template-columns: minmax(420px, 1.25fr) minmax(320px, 0.9fr) minmax(300px, 0.8fr);
  gap: 14px;
}
```

三列网格：窗口信息 | 浏览器/终端/文件管理器 | 活动/截图。

### 诊断视图

```css
.diagnostics-layout {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr);
}
```

两列网格：连接信息 | 能力状态。

## 响应式设计

980px 以下切换为单列布局：

```css
@media (max-width: 980px) {
  .app-shell { grid-template-columns: 1fr; }
  .side-tabs {
    display: flex;
    gap: 8px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .layout { grid-template-columns: 1fr; }
  .diagnostics-layout { grid-template-columns: 1fr; }
}
```

侧边栏从垂直标签变为水平标签。

### 灯箱（截图放大）

```css
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.85);
  display: grid;
  place-items: center;
  z-index: 50;
}
.lightbox img {
  max-width: 92vw;
  max-height: 88vh;
}
```

双击截图图片触发全屏查看，Escape 或点击背景关闭。

**图表来源**
- [desktop/ui/styles.css:1-350](file://desktop/ui/styles.css#L1-L350)
