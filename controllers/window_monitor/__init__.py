"""平台派发：根据 sys.platform 选择对应的 WindowMonitor。"""

import sys


def create_monitor(bus):
    if sys.platform.startswith("win"):
        from .windows_monitor import WindowsMonitor
        return WindowsMonitor(bus)
    if sys.platform == "darwin":
        from .macos_monitor import MacOSMonitor
        return MacOSMonitor(bus)
    if sys.platform.startswith("linux"):
        from .linux_x11_monitor import LinuxX11Monitor
        return LinuxX11Monitor(bus)
    raise RuntimeError(f"Unsupported platform: {sys.platform}")
