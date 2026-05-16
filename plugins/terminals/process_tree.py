"""跨平台通用：从终端进程往下走找 shell / 运行中的子进程。"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import psutil

from common.models import TerminalContext, TerminalProcess, WindowInfo
from tools.redaction import redact_cmdline
from plugins.terminals.base import TerminalIntegration, detect_terminal
from plugins.terminals.shell_files import ShellInfo, read_shell_infos

log = logging.getLogger(__name__)

SHELL_NAMES = {
    "bash", "zsh", "fish", "sh", "dash", "ash", "ksh", "tcsh", "csh",
    "pwsh", "pwsh.exe", "powershell", "powershell.exe", "cmd.exe",
    "nu", "elvish", "xonsh",
}

# 这些子进程不展示在 running 里（系统/wrapper 噪声）
RUNNING_BLACKLIST_NAMES = {
    "login", "tmux", "screen", "less", "more", "tail",
}


def _proc_to_terminal_process(
    child: psutil.Process,
    shell_infos: dict[int, ShellInfo],
) -> Optional[TerminalProcess]:
    try:
        name = child.name() or ""
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    name_lc = name.lower()
    is_shell = name_lc in SHELL_NAMES

    info = shell_infos.get(child.pid)

    cwd: Optional[str] = None
    cwd_source = "psutil"
    if info is not None and info.cwd:
        cwd = info.cwd
        cwd_source = "shell_file"
    else:
        try:
            cwd = child.cwd()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            cwd = None

    try:
        raw_cmdline = child.cmdline() or []
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        raw_cmdline = []
    redacted, was = redact_cmdline(raw_cmdline)

    # 最近一次命令（来自 shell 集成脚本）；按空白切再走 redact_cmdline，
    # 命中 token / --password 等同样脱敏。tokenize 不严格但够用于打码。
    last_cmd: Optional[str] = None
    last_cmd_redacted = False
    if info is not None and info.last_command:
        tokens = info.last_command.split()
        red_tokens, last_cmd_redacted = redact_cmdline(tokens)
        last_cmd = " ".join(red_tokens) if red_tokens else info.last_command

    try:
        ctime = child.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        ctime = None

    return TerminalProcess(
        pid=child.pid, name=name, cwd=cwd,
        cmdline=redacted, cmdline_redacted=was,
        create_time=ctime, is_shell=is_shell, cwd_source=cwd_source,
        last_command=last_cmd, last_command_redacted=last_cmd_redacted,
    )


def _walk(term_pid: int, shell_infos: dict[int, ShellInfo]) -> Optional[TerminalContext]:
    try:
        term = psutil.Process(term_pid)
        children = term.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    shells: list[TerminalProcess] = []
    running: list[TerminalProcess] = []
    for c in children:
        tp = _proc_to_terminal_process(c, shell_infos)
        if tp is None:
            continue
        if tp.is_shell:
            shells.append(tp)
        else:
            if tp.name.lower() in RUNNING_BLACKLIST_NAMES:
                continue
            running.append(tp)

    # 按创建时间倒序，让最近活跃的排前面
    shells.sort(key=lambda t: t.create_time or 0, reverse=True)
    running.sort(key=lambda t: t.create_time or 0, reverse=True)

    if not shells and not running:
        return None
    return TerminalContext(source="process_tree", shells=shells, running=running)


class ProcessTreeTerminal(TerminalIntegration):
    def matches(self, info: WindowInfo) -> bool:
        return detect_terminal(info) is not None

    async def query(self, info: WindowInfo) -> Optional[TerminalContext]:
        if not info.process:
            return None
        # shell 集成脚本写的 PID→(cwd, last_cmd) 映射，先读一次
        shell_infos = read_shell_infos()
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _walk, info.process.pid, shell_infos),
                timeout=1.5,
            )
        except asyncio.TimeoutError:
            log.debug("ProcessTreeTerminal query timed out for pid=%s", info.process.pid)
            return None
