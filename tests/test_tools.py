"""tools/ 模块单元测试（path_filter 在 test_filters.py，redaction 在 test_redaction.py）。"""

import socket

import pytest

from common.models import ProcessInfo, WindowInfo
from tools.blacklist import is_blacklisted, load_blacklist
from tools.port import find_free_port


# --- blacklist ---

def _info(bundle=None, exe=None, app_name=""):
    return WindowInfo(
        app_name=app_name,
        app_bundle_id=bundle,
        process=ProcessInfo(pid=1, name="", executable=exe) if exe else None,
    )


def test_blacklist_matches_bundle_prefix():
    bl = {"bundle_ids": ["com.1password."], "executables": []}
    assert is_blacklisted(_info(bundle="com.1password.macos"), bl)
    assert not is_blacklisted(_info(bundle="com.example.other"), bl)


def test_blacklist_matches_exe_substring():
    bl = {"bundle_ids": [], "executables": ["KeePassXC"]}
    assert is_blacklisted(_info(exe="/Applications/KeePassXC.app/Contents/MacOS/KeePassXC"), bl)
    assert not is_blacklisted(_info(exe="/usr/bin/code"), bl)


def test_blacklist_matches_app_name():
    bl = {"bundle_ids": [], "executables": ["Bitwarden"]}
    assert is_blacklisted(_info(app_name="Bitwarden"), bl)


def test_blacklist_case_insensitive():
    bl = {"bundle_ids": ["COM.1PASSWORD."], "executables": []}
    assert is_blacklisted(_info(bundle="com.1password.macos"), bl)


def test_blacklist_empty_info_safe():
    assert not is_blacklisted(WindowInfo(), {"bundle_ids": [], "executables": []})


def test_load_blacklist_returns_dict(tmp_path, monkeypatch):
    fake = tmp_path / "blacklist.json"
    monkeypatch.setattr("tools.blacklist.BLACKLIST_PATH", fake)
    bl = load_blacklist()
    assert isinstance(bl, dict)
    assert "bundle_ids" in bl
    assert fake.exists()   # 第一次调用应该把默认配置写出


# --- port ---

def test_find_free_port_returns_free():
    port = find_free_port("127.0.0.1", 49000, 49100)
    # 应该真能 bind 这个端口
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_find_free_port_skips_occupied():
    # 占用 49200，再让 find_free_port 从 49200 开始找，应得 49201+
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupier:
        occupier.bind(("127.0.0.1", 49200))
        occupier.listen(1)
        port = find_free_port("127.0.0.1", 49200, 49210)
        assert port != 49200


def test_find_free_port_exhausted_raises():
    # 占用 49250 — 49252，范围 [49250, 49252] 都占满 → 抛
    socks = []
    try:
        for p in range(49250, 49253):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", p))
            s.listen(1)
            socks.append(s)
        with pytest.raises(RuntimeError):
            find_free_port("127.0.0.1", 49250, 49252)
    finally:
        for s in socks:
            s.close()
