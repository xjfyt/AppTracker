"""集成模块的轻量单元测试。"""

import asyncio
import sys
from pathlib import Path

import pytest

from core.models import ProcessInfo, WindowInfo
from integrations.coordinator import IntegrationCoordinator
from integrations.terminals.base import detect_terminal
from integrations.terminals.shell_files import (
    SHELLS_DIR, read_shell_cwds, shell_integration_dir_path,
)


def _make_info(**kwargs) -> WindowInfo:
    return WindowInfo(
        app_name=kwargs.get("app_name", ""),
        app_bundle_id=kwargs.get("bundle"),
        window_class=kwargs.get("cls"),
        process=ProcessInfo(
            pid=kwargs.get("pid", 1),
            name=kwargs.get("proc_name", ""),
            executable=kwargs.get("exe"),
        ),
    )


def test_detect_terminal_macos_bundle():
    info = _make_info(bundle="com.googlecode.iterm2")
    assert detect_terminal(info) == "iterm2"


def test_detect_terminal_executable():
    info = _make_info(exe="/usr/bin/gnome-terminal-server")
    assert detect_terminal(info) == "gnome_terminal"


def test_detect_terminal_windows_exe():
    info = _make_info(exe="C:\\Program Files\\WindowsApps\\X\\WindowsTerminal.exe")
    assert detect_terminal(info) == "windows_terminal"


def test_detect_terminal_negative():
    info = _make_info(app_name="Code", exe="/Applications/VS Code.app/MacOS/Electron")
    assert detect_terminal(info) is None


def test_shell_integration_dir_exists():
    p = shell_integration_dir_path()
    assert p.is_dir()
    # 必须包含 4 个脚本
    expected = {"bash.sh", "zsh.sh", "fish.fish", "powershell.ps1"}
    found = {f.name for f in p.iterdir() if f.is_file()}
    assert expected.issubset(found)


def test_read_shell_cwds_handles_missing_dir(tmp_path, monkeypatch):
    fake = tmp_path / "no_such_dir"
    monkeypatch.setattr(
        "integrations.terminals.shell_files.SHELLS_DIR", fake,
    )
    assert read_shell_cwds() == {}


def test_read_shell_cwds_reads_valid(tmp_path, monkeypatch):
    import os
    fake = tmp_path / "shells"
    fake.mkdir()
    pid = os.getpid()  # 用本进程 PID 保证 pid_exists 返回 True
    f = fake / f"{pid}.cwd"
    f.write_text("/tmp/work")
    monkeypatch.setattr(
        "integrations.terminals.shell_files.SHELLS_DIR", fake,
    )
    out = read_shell_cwds()
    assert out.get(pid) == "/tmp/work"


def test_read_shell_cwds_cleans_dead_pid(tmp_path, monkeypatch):
    fake = tmp_path / "shells"
    fake.mkdir()
    dead_pid = 2**30   # 几乎肯定不存在
    f = fake / f"{dead_pid}.cwd"
    f.write_text("/tmp/dead")
    monkeypatch.setattr(
        "integrations.terminals.shell_files.SHELLS_DIR", fake,
    )
    out = read_shell_cwds()
    assert dead_pid not in out
    assert not f.exists()   # 顺手被清理


def test_coordinator_skips_already_enriched():
    """已带 file_manager_state 的 emit 不应触发再次 enrich（防循环）。"""
    from core.models import FileManagerState
    c = IntegrationCoordinator()
    info = _make_info()
    info.file_manager_state = FileManagerState(source="test")
    # 应该直接返回，不创建任务
    c.on_window_changed(info)
    assert c._inflight is None or c._inflight.cancelled() or c._inflight.done()
