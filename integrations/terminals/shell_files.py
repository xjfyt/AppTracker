"""读取 shell 集成脚本写到 ~/.active_tracker/shells/PID.cwd 的当前目录。

这是 Tier 2 路径：用户在 ~/.bashrc 等里 source 我们的 shell 脚本后，
每次 prompt 都会把 $PWD 写入一个以 PID 命名的小文件。我们读这个比
psutil.Process.cwd() 在 tmux/screen/嵌套 shell 下更准。
"""

from __future__ import annotations

import logging
from pathlib import Path

import psutil

log = logging.getLogger(__name__)

SHELLS_DIR = Path.home() / ".active_tracker" / "shells"


def shell_integration_dir_path() -> Path:
    """供 UI 上 "复制脚本路径" 按钮使用。"""
    return Path(__file__).resolve().parent.parent.parent / "shell_integration"


def read_shell_cwds() -> dict[int, str]:
    """返回 {pid: cwd}；不存在的 PID 文件顺手清掉。"""
    out: dict[int, str] = {}
    if not SHELLS_DIR.exists():
        return out
    for f in SHELLS_DIR.glob("*.cwd"):
        try:
            pid = int(f.stem)
        except ValueError:
            continue
        try:
            if not psutil.pid_exists(pid):
                try:
                    f.unlink()
                except OSError:
                    pass
                continue
            cwd = f.read_text(encoding="utf-8", errors="replace").strip()
            if cwd:
                out[pid] = cwd
        except OSError as exc:
            log.debug("read %s failed: %s", f, exc)
            continue
    return out
