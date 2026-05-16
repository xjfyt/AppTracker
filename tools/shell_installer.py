"""一键把 shell 集成脚本 source 进用户的 PowerShell $PROFILE。

PowerShell 的 cd（Set-Location）不更新进程 PEB.CurrentDirectory，
psutil.Process.cwd() 永远返回 PowerShell 启动时的目录。要追 cd，
唯一办法是在 $PROFILE 里 source 我们的 powershell.ps1，让它在每次
prompt 时把 $PWD 写到 ~/.active_tracker/shells/<PID>.cwd。

幂等：如果已经 source 过，再点按钮也不会重复追加。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class InstallResult:
    ok: bool
    message: str
    profile_path: Optional[Path] = None


def _shell_integration_root() -> Path:
    """指向仓库内的 shell_integration/ 目录。"""
    return Path(__file__).resolve().parent.parent / "shell_integration"


def _powershell_exe() -> Optional[str]:
    """优先 pwsh（PowerShell 7+），fallback 到 Windows PowerShell 5.1。"""
    for name in ("pwsh", "powershell"):
        path = shutil.which(name)
        if path:
            return path
    return None


def detect_powershell_profile_path() -> Optional[Path]:
    """问 PowerShell 自己 $PROFILE 是啥；比硬编码靠谱（受 PSScriptRoot 等影响）。"""
    exe = _powershell_exe()
    if not exe:
        return None
    try:
        # -NoProfile 避免用户自己的 profile 干扰输出
        result = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", "$PROFILE"],
            capture_output=True, timeout=5, text=True,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.debug("query $PROFILE failed: %s", exc)
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip().splitlines()
    if not out:
        return None
    return Path(out[-1].strip())


def _source_line(script_path: Path) -> str:
    """生成 source 行；PowerShell 用 . 操作符 + 单引号路径。"""
    return f". '{script_path}'"


def _is_already_installed(profile_path: Path, script_path: Path) -> bool:
    if not profile_path.exists():
        return False
    try:
        content = profile_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    needle = str(script_path)
    return needle in content


def install_powershell_integration() -> InstallResult:
    """把 source 行追加到 $PROFILE；返回结构化结果给 UI 用。"""
    if sys.platform != "win32":
        return InstallResult(False, "仅 Windows 下需要本按钮（macOS / Linux 手动 source）")

    script = _shell_integration_root() / "powershell.ps1"
    if not script.exists():
        return InstallResult(False, f"未找到 {script}")

    profile = detect_powershell_profile_path()
    if profile is None:
        return InstallResult(False, "找不到 PowerShell 可执行文件或 $PROFILE")

    if _is_already_installed(profile, script):
        return InstallResult(
            True,
            f"已安装过（{profile} 已包含本脚本）。重启 PowerShell 即可生效。",
            profile_path=profile,
        )

    try:
        profile.parent.mkdir(parents=True, exist_ok=True)
        line = _source_line(script)
        existing = ""
        if profile.exists():
            existing = profile.read_text(encoding="utf-8", errors="replace")
        # 保证前面有换行，避免拼到原 profile 最后一行末尾
        sep = "" if (not existing or existing.endswith(os.linesep) or existing.endswith("\n")) else os.linesep
        addition = f"{sep}# Active Tracker shell integration — 追踪 cd{os.linesep}{line}{os.linesep}"
        with profile.open("a", encoding="utf-8") as fh:
            fh.write(addition)
    except OSError as exc:
        return InstallResult(False, f"写入 {profile} 失败: {exc}")

    return InstallResult(
        True,
        f"已写入 {profile}。新开 PowerShell 窗口即可生效（旧窗口不会回滚）。",
        profile_path=profile,
    )
