"""端口工具：找一个能 bind 的空闲端口。"""

from __future__ import annotations

import socket


def find_free_port(host: str, start: int, end: int) -> int:
    """从 [start, end] 内顺序尝试，返回第一个能 bind 的端口。"""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in range {start}-{end}")
