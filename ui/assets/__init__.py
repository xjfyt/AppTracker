"""静态资源（图标 / 字体等）。访问入口：

    from ui.assets import APP_ICON_PATH, app_icon
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS_DIR = Path(__file__).resolve().parent

APP_ICON_PATH: Path = ASSETS_DIR / "icon.png"


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """返回应用主图标。缓存一次，多处复用同一个 QIcon 实例。"""
    return QIcon(str(APP_ICON_PATH))


__all__ = ["APP_ICON_PATH", "app_icon"]
