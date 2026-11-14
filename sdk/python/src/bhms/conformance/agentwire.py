"""A minimal MCP client over stdio for the agent profile.

The runner speaks MCP itself (``initialize``, ``tools/list``, ``tools/call``: newline-delimited JSON-RPC) so that it needs no
MCP SDK and tests any bridge, whatever it is written in. A function-tool adapter is tested through the same calls by wrapping it
in an MCP shim; the definitions it publishes must equal the bridge's (BHMS-AGT-050).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

from bhms.transport.stdio import release_process

MCP_VERSION = "2025-06-18"


@dataclass
class ToolOutcome:
    """The result of one ``tools/call``."""

    is_error: bool
    text: str
    structured: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """The first line of the text content (BHMS-AGT-010)."""
        return self.text.split("\n", 1)[0]


class AgentWire:
    """One MCP session with a bridge process."""

    def __init__(self, command: list[str], *, env: dict[str, str] | None = None, cwd: str | None = None) -> None:
        self.command, self.env, self.cwd = command, env, cwd
        self.process: asyncio.subprocess.Process | None = None
        self._ids = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader: asyncio.Task[None] | None = None
        self.server_info: dict[str, Any] = {}
        self.instructions = ""

    async def start(self) -> AgentWire:
        self.process = await asyncio.create_subprocess_exec(
            *self.command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **(self.env or {})}, cwd=self.cwd, limit=16 * 1024 * 1024)
        self._reader = asyncio.ensure_future(self._read())
        init = await self.request("initialize", {"protocolVersion": MCP_VERSION, "capabilities": {},
                                                 "clientInfo": {"name": "bhms-conformance", "version": "0.1.0"}}, timeout=30)
        self.server_info = init.get("serverInfo", {})
        self.instructions = init.get("instructions", "")
        await self.notify("notifications/initialized")
        return self

    async def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                future = self._pending.pop(message.get("id"), None) if "method" not in message else None
                if future is not None and not future.done():
                    future.set_result(message)
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("the bridge closed its output"))

    async def _send(self, message: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 60.0) -> dict[str, Any]:
        self._ids += 1
        ident = self._ids
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        await self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})
        reply = await asyncio.wait_for(future, timeout)
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply.get("result", {})

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor = None
        while True:
            result = await self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    async def call(self, name: str, arguments: dict[str, Any] | None = None, *, timeout: float = 90.0) -> ToolOutcome:
        result = await self.request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        text = "\n".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
        return ToolOutcome(bool(result.get("isError")), text, result.get("structuredContent") or {}, result)

    async def close(self) -> None:
        if self.process is None:
            return
        with contextlib.suppress(Exception):
            self.process.stdin.close()  # type: ignore[union-attr]
        try:
            await asyncio.wait_for(self.process.wait(), 5)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        release_process(self.process)
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
