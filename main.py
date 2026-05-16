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
import os
import signal
import sys
import threading
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
from ui.assets import app_icon
from ui.main_window import MainWindow

APP_USER_MODEL_ID = "wxj.active-tracker"

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


def _set_windows_app_user_model_id(app_id: str) -> None:
    """Windows 上必须在创建第一个窗口前调一次 SetCurrentProcessExplicitAppUserModelID，
    否则 Python 解释器进程会和 python.exe 共用任务栏 icon / 分组，我们的 setWindowIcon
    在任务栏上看不到。无该 API 的旧系统静默忽略。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as exc:
        logging.debug("SetCurrentProcessExplicitAppUserModelID failed: %s", exc)


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

    _set_windows_app_user_model_id(APP_USER_MODEL_ID)
    app = QApplication(sys.argv)
    app.setApplicationName("Active Tracker")
    app.setWindowIcon(app_icon())
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

    # Ctrl+C 处理：Qt 的 C++ 事件循环阻塞 Python 的信号派发，光装 signal
    # handler 没用。配一个 200ms 无操作的 QTimer 周期性把控制权交回 Python
    # 解释器，handler 才能跑。装 SIGINT 后转成 app.quit() 走正常关闭流程。
    def _on_sigint(*_args) -> None:
        log.info("Received SIGINT, requesting quit")
        app.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    if hasattr(signal, "SIGBREAK"):   # Windows: Ctrl+Break
        signal.signal(signal.SIGBREAK, _on_sigint)
    _signal_pump = QTimer()
    _signal_pump.timeout.connect(lambda: None)
    _signal_pump.start(200)

    def _hard_exit() -> None:
        """优雅关闭的兜底：pynput / qasync IOCP proactor / aiohttp runner
        在 Windows 上偶尔不肯彻底退出，让 Python 主线程返回也没用——
        非守护线程会让 uv run 一直挂着。给 3s 优雅期，到点强退。"""
        log.warning("Active Tracker hard-exit after grace period")
        logging.shutdown()
        os._exit(0)

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
        _signal_pump.stop()
        # threading.Timer 不依赖 Qt 事件循环——app.quit() 之后 Qt loop
        # 就退出了，QTimer.singleShot 永远不会 fire。daemon 让 Python
        # 真能优雅退时不被它挡住。
        t = threading.Timer(3.0, _hard_exit)
        t.daemon = True
        t.start()

    app.aboutToQuit.connect(_shutdown)

    if args.check:
        QTimer.singleShot(2000, app.quit)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
