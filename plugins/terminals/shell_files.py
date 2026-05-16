"""读取 shell 集成脚本写到 ~/.active_tracker/shells/<PID>.cwd / .cmd 的数据。

这是 Tier 2 路径：用户在 ~/.bashrc / $PROFILE 等里 source 我们的 shell
脚本后，每次 prompt 会把 $PWD 写入 <PID>.cwd，把最近一次执行的命令写入
<PID>.cmd。PowerShell 的 cd 不更新 PEB，必须靠这个；bash/zsh 在
tmux/screen/嵌套 shell 下也比 psutil.Process.cwd() 更准。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

log = logging.getLogger(__name__)

SHELLS_DIR = Path.home() / ".active_tracker" / "shells"


@dataclass
class ShellInfo:
    cwd: Optional[str] = None
    last_command: Optional[str] = None


def shell_integration_dir_path() -> Path:
    """供 UI 上 "复制脚本路径" 按钮使用。"""
    return Path(__file__).resolve().parent.parent.parent / "shell_integration"


def _read_text(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        log.debug("read %s failed: %s", path, exc)
        return None
    return text or None


def read_shell_infos() -> dict[int, ShellInfo]:
    """扫描 SHELLS_DIR，返回 {pid: ShellInfo}；已死 PID 的文件顺手清掉。"""
    out: dict[int, ShellInfo] = {}
    if not SHELLS_DIR.exists():
        return out
    # 按 stem(pid) 聚合 .cwd / .cmd
    by_pid: dict[int, dict[str, Path]] = {}
    for f in SHELLS_DIR.iterdir():
        if f.suffix not in (".cwd", ".cmd"):
            continue
        try:
            pid = int(f.stem)
        except ValueError:
            continue
        by_pid.setdefault(pid, {})[f.suffix] = f

    for pid, files in by_pid.items():
        if not psutil.pid_exists(pid):
            for f in files.values():
                try:
                    f.unlink()
                except OSError:
                    pass
            continue
        info = ShellInfo()
        if ".cwd" in files:
            info.cwd = _read_text(files[".cwd"])
        if ".cmd" in files:
            info.last_command = _read_text(files[".cmd"])
        if info.cwd or info.last_command:
            out[pid] = info
    return out


def read_shell_cwds() -> dict[int, str]:
    """兼容旧调用方：只关心 cwd 的话用这个。"""
    return {pid: info.cwd for pid, info in read_shell_infos().items() if info.cwd}
