"""HTTP/SSE/WebSocket API — 让其他客户端读取 Active Tracker 的实时状态。

入口：APIServer。详见 docs/api.md。
"""

from api.server import APIServer

__all__ = ["APIServer"]
