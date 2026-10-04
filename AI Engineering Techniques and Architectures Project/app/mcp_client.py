"""MCP client used by the agent.

A single supervisor task owns the transport + ClientSession for the life of the app (so anyio cancel scopes are
entered/exited by the same task), and request handlers just call `call_tool`. If the server dies the client
reconnects once on the next call. Two transports:
  * stdio            - default; spawns `python -m mcp_server.server` (single-service free-tier deployment)
  * streamable HTTP  - when MCP_SERVER_URL is set (separate MCP service)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

import settings


class MCPClient:
    def __init__(self, url: str | None = None, env: dict[str, str] | None = None):
        self.url = (url if url is not None else settings.MCP_SERVER_URL) or ""
        self.extra_env = env or {}
        self.session: ClientSession | None = None
        self.tools: list[dict] = []
        self.last_error: str | None = None
        self.connected_at: float | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def transport(self) -> str:
        return "streamable-http" if self.url else "stdio"

    # ------------------------------------------------------------------ lifecycle
    @contextlib.asynccontextmanager
    async def _open(self):
        if self.url:
            async with streamablehttp_client(self.url) as (r, w, _get_id):
                yield r, w
        else:
            params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(settings.ROOT),
                                           env={**os.environ, **self.extra_env})
            async with stdio_client(params) as (r, w):
                yield r, w

    async def _run(self) -> None:
        try:
            async with self._open() as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    listed = await session.list_tools()  # tool DISCOVERY: the agent only knows what the server advertises
                    self.tools = [{"name": t.name, "description": t.description, "input_schema": t.inputSchema} for t in listed.tools]
                    self.session, self.last_error, self.connected_at = session, None, time.time()
                    self._ready.set()
                    await self._stop.wait()
        except Exception as e:  # noqa: BLE001 - surfaced through /health and traces
            self.last_error = f"{type(e).__name__}: {e}"
        finally:
            self.session = None
            self._ready.set()

    async def start(self, timeout: float = 45.0) -> bool:
        async with self._lock:
            if self._task and not self._task.done() and self.session:
                return True
            self._stop, self._ready = asyncio.Event(), asyncio.Event()
            self._task = asyncio.create_task(self._run())
            try:
                await asyncio.wait_for(self._ready.wait(), timeout)
            except asyncio.TimeoutError:
                self.last_error = "timeout while starting MCP server"
            return self.session is not None

    async def close(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, 10)
            except Exception:  # noqa: BLE001
                self._task.cancel()
        self.session = None

    # ------------------------------------------------------------------ calls
    @property
    def tool_names(self) -> list[str]:
        return [t["name"] for t in self.tools]

    @staticmethod
    def _parse(result) -> tuple[bool, Any]:
        if result.structuredContent is not None:
            data = result.structuredContent
        else:
            text = "".join(getattr(c, "text", "") for c in result.content)
            try:
                data = json.loads(text)
            except ValueError:
                data = {"text": text}
        if result.isError:
            return False, data
        if isinstance(data, dict) and data.get("ok") is False:
            return False, data
        return True, data

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        """Returns {ok, data, error, latency_ms}; never raises."""
        t0 = time.perf_counter()
        for attempt in (1, 2):
            if self.session is None and not await self.start():
                return {"ok": False, "data": None, "error": f"MCP server unavailable: {self.last_error}", "latency_ms": _ms(t0), "unavailable": True}
            try:
                res = await asyncio.wait_for(self.session.call_tool(name, arguments), settings.MCP_CALL_TIMEOUT_S)
                ok, data = self._parse(res)
                err = None if ok else (data.get("error", {}).get("message") if isinstance(data, dict) and isinstance(data.get("error"), dict) else json.dumps(data)[:300])
                return {"ok": ok, "data": data, "error": err, "latency_ms": _ms(t0)}
            except asyncio.TimeoutError:
                return {"ok": False, "data": None, "error": f"tool call '{name}' timed out after {settings.MCP_CALL_TIMEOUT_S:g}s", "latency_ms": _ms(t0)}
            except Exception as e:  # noqa: BLE001 - broken pipe / server crash -> reconnect once
                self.last_error = f"{type(e).__name__}: {e}"
                self.session = None
                if attempt == 2:
                    return {"ok": False, "data": None, "error": f"MCP call failed: {self.last_error}", "latency_ms": _ms(t0), "unavailable": True}
        return {"ok": False, "data": None, "error": "unreachable", "latency_ms": _ms(t0)}

    async def health(self) -> dict:
        connected = False
        if self.session is not None:
            try:
                await asyncio.wait_for(self.session.send_ping(), 5)
                connected = True
            except Exception as e:  # noqa: BLE001
                self.last_error = f"{type(e).__name__}: {e}"
        return {"connected": connected, "transport": self.transport, "url": self.url or None, "tool_count": len(self.tools),
                "tools": self.tool_names, "last_error": self.last_error}


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)
