from core.models import (
    ActivityStats, BrowserTab, DocumentSource, ProcessInfo,
    WindowGeometry, WindowInfo,
)


def test_window_info_defaults():
    info = WindowInfo()
    assert info.app_name == ""
    assert info.document_paths == []
    assert info.errors == []
    d = info.to_dict()
    assert "timestamp" in d
    assert d["document_paths"] == []


def test_identity_key_changes_with_title():
    a = WindowInfo(app_name="A", window_id="1", window_title="t1")
    b = WindowInfo(app_name="A", window_id="1", window_title="t2")
    assert a.identity_key() != b.identity_key()


def test_identity_key_includes_documents():
    a = WindowInfo(
        app_name="A", window_id="1",
        document_paths=[DocumentSource(path="/x", kind="file", source="title", confidence=0.5)],
    )
    b = WindowInfo(
        app_name="A", window_id="1",
        document_paths=[DocumentSource(path="/y", kind="file", source="title", confidence=0.5)],
    )
    assert a.identity_key() != b.identity_key()


def test_geometry_in_identity():
    a = WindowInfo(geometry=WindowGeometry(0, 0, 100, 100))
    b = WindowInfo(geometry=WindowGeometry(10, 0, 100, 100))
    assert a.identity_key() != b.identity_key()


def test_activity_stats_dataclass():
    s = ActivityStats(keys_count=5, clicks_count=3)
    assert s.keys_count == 5
    assert s.idle_seconds == 0.0


def test_browser_tab_dataclass():
    t = BrowserTab(browser="chrome", pid=1, window_id=2, tab_id=3,
                   url="https://x.com", title="X")
    assert t.is_active is True
    assert t.favicon_url is None


def test_process_info_optional_fields():
    p = ProcessInfo(pid=10, name="x")
    assert p.cmdline == []
    assert p.cwd is None
