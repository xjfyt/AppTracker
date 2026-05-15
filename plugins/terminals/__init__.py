"""终端插件 — 自包含 package。

当前仅提供通用 process_tree 实现（跨平台）。后续可以加：
  * iterm2/    — iTerm2 Python API（仅 macOS，需用户在偏好设置启用 Python API）
"""

from __future__ import annotations

from plugins.terminals.base import TerminalIntegration, detect_terminal


def get_default() -> TerminalIntegration:
    """返回平台无关的默认终端集成。"""
    from plugins.terminals.process_tree import ProcessTreeTerminal
    return ProcessTreeTerminal()


__all__ = ["TerminalIntegration", "detect_terminal", "get_default"]
