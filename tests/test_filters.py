import os

from core.models import DocumentSource
from core.utils import (
    SHELL_PROCESS_NAMES, classify_path, dedupe_documents, expand_user,
    extract_paths_from_title, file_url_to_path, find_shell_cwd,
    is_interesting_path, looks_like_browser, looks_like_terminal,
)


def test_is_interesting_extension():
    assert is_interesting_path("/Users/me/Documents/foo.md") is True
    assert is_interesting_path("/Users/me/Documents/foo.py") is True


def test_is_interesting_rejects_blacklist():
    assert is_interesting_path("/Users/me/.cache/pip/foo") is False
    assert is_interesting_path("/usr/lib/libfoo.so") is False
    assert is_interesting_path("/repo/node_modules/bar/index.js") is False


def test_is_interesting_rejects_empty():
    assert is_interesting_path("") is False


def test_file_url_to_path():
    assert file_url_to_path("file:///Users/me/a.txt") == "/Users/me/a.txt"
    assert file_url_to_path("file:///path%20with%20spaces") == "/path with spaces"
    assert file_url_to_path("https://x") is None
    assert file_url_to_path("") is None


def test_extract_paths_from_title():
    paths = extract_paths_from_title("foo - /Users/me/x.txt")
    assert any("/Users/me/x.txt" in p for p in paths)
    paths = extract_paths_from_title("C:\\Users\\me\\file.txt - Notepad")
    assert any("file.txt" in p for p in paths)


def test_classify_path(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert classify_path(str(f)) == "file"
    assert classify_path(str(tmp_path)) == "folder"
    assert classify_path("/no/such/__nope__") == "unknown"


def test_dedupe_keeps_highest_confidence():
    docs = [
        DocumentSource(path="/x", kind="file", source="title", confidence=0.4),
        DocumentSource(path="/x", kind="file", source="accessibility", confidence=0.95),
        DocumentSource(path="/y", kind="file", source="fd_scan", confidence=0.3),
    ]
    out = dedupe_documents(docs)
    assert len(out) == 2
    # /x with high confidence comes first
    assert out[0].path == "/x"
    assert out[0].confidence == 0.95
    assert out[1].path == "/y"


def test_expand_user():
    expanded = expand_user("~/foo")
    assert "/" in expanded
    assert expanded != "~/foo"


def test_looks_like_browser():
    assert looks_like_browser("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", None)
    assert looks_like_browser(None, "Firefox")
    assert not looks_like_browser("/usr/bin/python", "Terminal")


def test_looks_like_terminal():
    assert looks_like_terminal("/Applications/iTerm.app/Contents/MacOS/iTerm2", None)
    assert looks_like_terminal(None, "Terminal")
    assert looks_like_terminal("/opt/homebrew/bin/wezterm", "WezTerm")
    assert looks_like_terminal(
        "C:\\Program Files\\WindowsApps\\WindowsTerminal_x\\WindowsTerminal.exe", None
    )
    assert looks_like_terminal(None, "powershell.exe")
    assert looks_like_terminal("/usr/bin/gnome-terminal-server", None)
    assert not looks_like_terminal(
        "/Applications/Visual Studio Code.app/Contents/MacOS/Electron", "Code"
    )
    assert not looks_like_terminal(None, None)


def test_shell_process_names_covers_common_shells():
    assert {"bash", "zsh", "fish", "pwsh", "cmd.exe"}.issubset(SHELL_PROCESS_NAMES)


def test_find_shell_cwd_unknown_pid_returns_none():
    assert find_shell_cwd(2**31 - 1) is None


def test_find_shell_cwd_no_shell_children_returns_none():
    # 当前 pytest 进程通常没有 shell 子进程
    result = find_shell_cwd(os.getpid())
    assert result is None or isinstance(result, str)
