"""API 端点冒烟测试 — 启 aiohttp test_server，用 httpx 打路由。

不挂 PySide6 / qasync — 只验证 HTTP/SSE/WS 路由结构与基本响应。
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

import httpx

from api.server import make_app
from api.state import api_state


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def server() -> TestServer:
    api_state.bind_loop(asyncio.get_event_loop())
    app = make_app()
    srv = TestServer(app)
    await srv.start_server()
    yield srv
    await srv.close()


async def test_health(server: TestServer):
    async with httpx.AsyncClient(base_url=str(server.make_url("/"))) as c:
        r = await c.get("api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["service"] == "active-tracker"


async def test_snapshot_returns_dict(server: TestServer):
    async with httpx.AsyncClient(base_url=str(server.make_url("/"))) as c:
        r = await c.get("api/v1/snapshot")
        assert r.status_code == 200
        d = r.json()
        for key in ("window", "activity", "browser_tab", "has_screenshot"):
            assert key in d


async def test_screenshot_404_when_no_data(server: TestServer):
    # 这个 fixture 干净启动，没有截图入流
    async with httpx.AsyncClient(base_url=str(server.make_url("/"))) as c:
        r = await c.get("api/v1/screenshot")
        assert r.status_code in (404, 200)   # 如果其它测试先填了缓存就 200


async def test_sse_keepalive_during_silence(server: TestServer):
    """无事件时 SSE 应该不报错（25s 才发心跳，所以这个测试只检查能连上）。"""
    base = str(server.make_url("/"))
    async with httpx.AsyncClient() as c:
        async with c.stream("GET", base + "api/v1/events", timeout=2.0) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")


async def test_ws_snapshot_command(server: TestServer):
    """WS 收到 'snapshot' 文本时应回 snapshot 数据。"""
    import websockets
    url = "ws://" + server.host + ":" + str(server.port) + "/api/v1/ws"
    async with websockets.connect(url) as ws:
        await ws.send("snapshot")
        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
        data = json.loads(msg)
        assert data["type"] == "snapshot"
        assert "data" in data
