> **对应代码**：`Cargo.toml`, `desktop/package.json`
> **维护提示**：修改构建流程或依赖时同步更新本文档。

# 四、构建指南

## 1、前置条件

| 依赖 | 版本 | 说明 |
|------|------|------|
| Rust | 2021 edition（1.70+） | 通过 `rustup` 安装 |
| Node.js | 18+ | Tauri 开发模式需要 |
| npm | 9+ | 随 Node.js 安装 |

### 平台额外要求

| 平台 | 要求 |
|------|------|
| Windows | Windows SDK（Win32 API 头文件）、PowerShell 5.1+ |
| macOS | Xcode Command Line Tools、Accessibility 权限 |
| Linux | xdotool、xprop、X11 会话（Wayland 功能受限） |

## 2、克隆与构建

```bash
# 克隆仓库
git clone <repo-url> AppTracker
cd AppTracker

# 构建核心库（验证编译）
cargo build -p tracker-core

# 构建完整 Tauri 应用
cd desktop
npm install
npm run tauri build
```

## 3、开发模式

```bash
cd desktop
npm run tauri dev
```

Tauri 开发模式会同时启动 Vite 前端热重载和 Rust 后端编译。桌面窗口自动打开。

## 4、仅构建核心库

```bash
# 在 workspace 根目录
cargo build -p tracker-core

# 运行测试
cargo test -p tracker-core

# 禁用可选 features（最小构建）
cargo build -p tracker-core --no-default-features
```

## 5、Feature 开关

| Feature | 默认 | 说明 |
|---------|------|------|
| `activity` | 开启 | 键鼠全局监听（rdev） |
| `capture` | 开启 | 截图采集（screenshots + image） |

禁用 `activity` 和 `capture` 后，对应的 `spawn_activity_monitor` 和 `spawn_screen_capture` 会变为空操作（no-op）。

## 6、浏览器扩展构建

浏览器扩展无需构建步骤，直接加载源码：

1. 打开 `chrome://extensions/`（Chrome）或 `about:debugging#/runtime/this-firefox`（Firefox）
2. 启用"开发者模式"
3. 点击"加载已解压的扩展程序"，选择 `browser_extension/` 目录

## 7、Shell 集成安装

详见各 shell 脚本顶部注释：

```bash
# bash — 添加到 ~/.bashrc
source /path/to/AppTracker/shell_integration/bash.sh

# zsh — 添加到 ~/.zshrc
source /path/to/AppTracker/shell_integration/zsh.sh

# fish — 添加到 ~/.config/fish/config.fish
source /path/to/AppTracker/shell_integration/fish.fish

# PowerShell — 添加到 $PROFILE
. 'C:\path\to\AppTracker\shell_integration\powershell.ps1'

# cmd — 运行安装脚本
install_windows.cmd
```

---

- 上一篇：[03-tech-stack.md](../01-overview/03-tech-stack.md)
- 下一篇：[02-run-and-deploy.md](./02-run-and-deploy.md)
- 返回索引：[docs/README.md](../README.md)
