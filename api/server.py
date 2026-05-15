"""API 服务器 — aiohttp 跑 HTTP/SSE/WebSocket。

路由：
  GET  /api/v1/health                  健康检查（不走 state，永远 200）
  GET  /api/v1/snapshot                当前所有状态的 JSON 快照
  GET  /api/v1/screenshot              最新焦点窗口截图（image/png）
  GET  /api/v1/events                  SSE 事件流（断线后浏览器自动重连）
  WS   /api/v1/ws                      WebSocket 事件流（带 30s 心跳，适合长连）
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from aiohttp import WSCloseCode, WSMsgType, web

from api.state import api_state

log = logging.getLogger(__name__)

WS_HEARTBEAT_SEC = 30.0
SSE_HEARTBEAT_SEC = 25.0


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "active-tracker"})


async def snapshot(_request: web.Request) -> web.Response:
    return web.json_response(api_state.snapshot())


async def screenshot(_request: web.Request) -> web.Response:
    png = api_state.latest_screenshot()
    if png is None:
        return web.Response(status=404, text="no screenshot yet")
    return web.Response(body=png, content_type="image/png")


async def events_sse(request: web.Request) -> web.StreamResponse:
    """SSE 事件流。

    SSE 优点：纯 HTTP，浏览器原生 EventSource 自动重连，客户端代码 3 行。
    缺点：单向；长时间无消息可能被中间代理切断。我们每 25s 发一个 `: keepalive` 注释
    （SSE 协议保留行）保活，对客户端透明，不当 message 派发。
    """
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)
    queue = api_state.subscribe()
    log.info("SSE client connected: %s", request.remote)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SEC)
            except asyncio.TimeoutError:
                # SSE 注释行保活
                await response.write(b": keepalive\n\n")
                continue
            payload = json.dumps(event, default=str).encode("utf-8")
            await response.write(b"event: " + event["type"].encode("ascii") + b"\n")
            await response.write(b"data: " + payload + b"\n\n")
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    except Exception as exc:
        log.exception("SSE stream error: %s", exc)
    finally:
        api_state.unsubscribe(queue)
        log.info("SSE client gone: %s", request.remote)
    return response


async def events_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket 事件流，30 s 心跳。

    aiohttp 的 `heartbeat` 参数会自动发 ping 帧并等 pong，断连时抛 ConnectionResetError。
    适合 IDE/守护进程类客户端长时间连着。
    """
    ws = web.WebSocketResponse(heartbeat=WS_HEARTBEAT_SEC, autoping=True)
    await ws.prepare(request)
    queue = api_state.subscribe()
    log.info("WS client connected: %s", request.remote)

    # 推送循环
    push_task = asyncio.create_task(_ws_push_loop(ws, queue))
    try:
        # 客户端也可以发简单文本指令，方便调试；我们只回 echo + ack
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if msg.data == "snapshot":
                    await ws.send_json({"type": "snapshot", "data": api_state.snapshot()})
                else:
                    await ws.send_json({"type": "ack", "echo": msg.data})
            elif msg.type == WSMsgType.ERROR:
                log.warning("WS error: %s", ws.exception())
                break
    finally:
        push_task.cancel()
        try:
            await push_task
        except (asyncio.CancelledError, Exception):
            pass
        api_state.unsubscribe(queue)
        log.info("WS client gone: %s", request.remote)
    return ws


async def _ws_push_loop(ws: web.WebSocketResponse, queue: asyncio.Queue) -> None:
    try:
        while True:
            event = await queue.get()
            if ws.closed:
                break
            try:
                await ws.send_json(event)
            except (ConnectionResetError, RuntimeError):
                break
    except asyncio.CancelledError:
        return


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/v1/health", health)
    app.router.add_get("/api/v1/snapshot", snapshot)
    app.router.add_get("/api/v1/screenshot", screenshot)
    app.router.add_get("/api/v1/events", events_sse)
    app.router.add_get("/api/v1/ws", events_ws)
    return app


class APIServer:
    """启动 aiohttp 服务器并接入 qasync 共享的 asyncio loop。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5007) -> None:
        self.host = host
        self.port = port
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        api_state.bind_loop(loop)
        app = make_app()
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        log.info("APIServer listening on http://%s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        log.info("APIServer stopped")
