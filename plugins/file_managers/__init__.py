"""文件管理器插件 — 自包含 package，按平台导出可用插件。

新增一个文件管理器集成：
  1. 在本目录建一个新模块（继承 FileManagerIntegration）
  2. 在 get_for_platform() 里按 sys.platform 添加
"""

from __future__ import annotations

import sys

from plugins.file_managers.base import FileManagerIntegration


def get_for_platform() -> list[FileManagerIntegration]:
    """返回当前平台可用的文件管理器集成实例。"""
    if sys.platform == "darwin":
        from plugins.file_managers.mac_finder import FinderIntegration
        return [FinderIntegration()]
    if sys.platform.startswith("win"):
        from plugins.file_managers.win_explorer import ExplorerIntegration
        return [ExplorerIntegration()]
    if sys.platform.startswith("linux"):
        from plugins.file_managers.linux_nautilus import NautilusIntegration
        from plugins.file_managers.linux_dolphin import DolphinIntegration
        return [NautilusIntegration(), DolphinIntegration()]
    return []


__all__ = ["FileManagerIntegration", "get_for_platform"]
