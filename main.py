"""Active Tracker — 程序入口。

启动:
    uv run main.py
    uv run main.py --debug
    uv run main.py --no-activity --no-capture --no-browser-bridge
    uv run main.py --check          # 冒烟模式：构造完所有组件 2s 后退出

日志写到 ~/.active_tracker/tracker.log (10MB × 3 滚动)。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import qasync

from api import APIServer
from common.signals import bus
from controllers.activity_monitor import ActivityMonitor
from controllers.browser_bridge import BrowserBridge
from controllers.integration_coordinator import IntegrationCoordinator
from controllers.screen_capture import ScreenCapture
from controllers.window_monitor import create_monitor
from ui.main_window import MainWindow

LOG_DIR = Path.home() / ".active_tracker"
LOG_FILE = LOG_DIR / "tracker.log"


def setup_logging(debug: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)

    fh = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3)
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    root.addHandler(fh)

    if debug:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh.setLevel(logging.DEBUG)
        root.addHandler(sh)

    # bus 上的错误事件也走 logging
    bus.error_occurred.connect(
        lambda src, msg: logging.getLogger(src).warning("%s", msg)
    )


def load_style(app: QApplication) -> None:
    qss_path = Path(__file__).resolve().parent / "ui" / "style.qss"
    try:
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Failed to load stylesheet: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Active Tracker")
    parser.add_argument("--debug", action="store_true", help="把日志同步打到 stderr")
    parser.add_argument("--no-activity", action="store_true", help="不启动键鼠监视器")
    parser.add_argument("--no-capture", action="store_true", help="不截图")
    parser.add_argument("--no-browser-bridge", action="store_true", help="不开浏览器扩展 WebSocket 桥")
    parser.add_argument("--no-api", action="store_true", help="不启动 HTTP/SSE/WS API 服务")
    parser.add_argument("--api-host", default="127.0.0.1", help="API 服务监听地址")
    parser.add_argument("--api-port", type=int, default=5007, help="API 服务监听端口（默认 5007）")
    parser.add_argument("--check", action="store_true",
                        help="冒烟模式：构造完所有组件后 2 秒退出")
    args = parser.parse_args()

    setup_logging(args.debug)
    log = logging.getLogger("main")
    log.info("Active Tracker starting (platform=%s)", sys.platform)

    app = QApplication(sys.argv)
    app.setApplicationName("Active Tracker")
    load_style(app)

    # qasync 让 websockets 与 Qt 共用同一个事件循环
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 1. 焦点窗口监视器（平台派发）
    monitor = None
    try:
        monitor = create_monitor(bus)
    except Exception as exc:
        log.exception("Monitor init failed")
        bus.error_occurred.emit("main", f"Monitor init: {exc}")

    # 2. 键鼠活动（可关闭）
    activity: Optional[ActivityMonitor] = None
    if not args.no_activity:
        activity = ActivityMonitor()

    # 3. 截图（可关闭）
    capture: Optional[ScreenCapture] = None
    if not args.no_capture:
        capture = ScreenCapture()

    # 4. 浏览器扩展 WebSocket 桥（可关闭）
    bridge: Optional[BrowserBridge] = None
    bridge_task: Optional[asyncio.Task] = None
    if not args.no_browser_bridge:
        bridge = BrowserBridge()

    # 5. 集成调度器（文件管理器 + 终端）
    coordinator = IntegrationCoordinator()

    # 6. HTTP/SSE/WS API（可关闭）
    api: Optional[APIServer] = None
    api_task: Optional[asyncio.Task] = None
    if not args.no_api:
        api = APIServer(host=args.api_host, port=args.api_port)

    # 7. 主窗口
    window = MainWindow(monitor=monitor)
    window.show()

    # 暂停联动
    if monitor is not None:
        bus.paused_changed.connect(monitor.set_paused)
    if activity is not None:
        bus.paused_changed.connect(activity.set_paused)

    def _start_all() -> None:
        if monitor is not None:
            monitor.start()
        if activity is not None:
            activity.start()
        nonlocal bridge_task, api_task
        if bridge is not None:
            bridge_task = bridge.start_in_loop(loop)
        if api is not None:
            api_task = loop.create_task(api.start())

    QTimer.singleShot(0, _start_all)

    # 关闭前清理（loop 此时还活着）
    def _shutdown() -> None:
        log.info("Active Tracker shutting down")
        if monitor is not None:
            monitor.stop()
        if activity is not None:
            activity.stop()
        if bridge_task is not None and not bridge_task.done():
            bridge_task.cancel()
        if api is not None:
            loop.create_task(api.stop())
        if api_task is not None and not api_task.done():
            api_task.cancel()

    app.aboutToQuit.connect(_shutdown)

    if args.check:
        QTimer.singleShot(2000, app.quit)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
