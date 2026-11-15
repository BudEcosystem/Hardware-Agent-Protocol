"""A scripted compact endpoint: answers exactly what a test tells it to (the native C endpoint cannot be made to misbehave)."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.gateway.compact_bridge import CompactBridge
from bhms.transport import compact as cp
from helpers.compact_rig import FAST, LED, wait_served

Behaviour = Callable[["Scripted", Any], Awaitable[None] | None]


class Scripted:
    """The MCU side of a socket pair. ``on[MessageClass]`` is called with ``(self, message)``; it replies with
    :meth:`say`. Default behaviour: answer HELLO_REQ with a correct HELLO, QUERY of an unknown handle with HANDLE_UNKNOWN."""

    def __init__(self, digest8: bytes, *, epoch: int = 7, flags: int = cp.FLAG_PERSISTENT_EPOCH | cp.FLAG_FENCING,
                 max_args: int = 16, last_handle: int = 0, version: int = cp.COMPACT_VERSION) -> None:
        self.digest8, self.epoch, self.flags, self.max_args = digest8, epoch, flags, max_args
        self.last_handle, self.version = last_handle, version
        self.on: dict[type, Behaviour] = {}
        self.seen: list[Any] = []
        self.frames: list[cp.Incoming] = []  # every frame received, with its session
        self.link: cp.CompactLink | None = None
        self._task: asyncio.Task[None] | None = None

    async def open(self, port: str, baud: int) -> cp.ByteStream:
        a, b = socket.socketpair()
        self.link = cp.CompactLink(cp.FdStream(b.detach()), role="endpoint")
        self.link.start()
        self._task = asyncio.get_running_loop().create_task(self._serve())
        return cp.FdStream(a.detach())

    def say(self, message: Any, *, kind: int = cp.STATUS_KIND, session: int | None = None) -> None:
        assert self.link is not None
        self.link.send(message, session=self.epoch if session is None else session, kind=kind)

    async def _serve(self) -> None:
        assert self.link is not None
        try:
            while True:
                incoming = await self.link.receive()
                assert incoming is not None
                message = incoming.message
                self.seen.append(message)
                self.frames.append(incoming)
                handler = self.on.get(type(message))
                if handler is not None:
                    result = handler(self, message)
                    if asyncio.iscoroutine(result):
                        await result
                elif isinstance(message, cp.HelloReq):
                    self.say(cp.Hello(self.flags, self.digest8, self.epoch, message.nonce, self.last_handle, 4, 2,
                                      self.max_args, self.version))
                elif isinstance(message, cp.Query):
                    self.say(cp.Error(cp.QUERY, message.handle, cp.E_HANDLE_UNKNOWN))
        except (cp.LinkClosed, asyncio.CancelledError):
            return

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self.link is not None:
            await self.link.close()

    def of(self, kind: type) -> list[Any]:
        return [m for m in self.seen if isinstance(m, kind)]


@asynccontextmanager
async def scripted_rig(tmp: Path, *, sidecar: dict[str, Any] | None = None, scripted: Scripted | None = None,
                       served: bool = True) -> AsyncIterator[tuple[Client, CompactBridge, Scripted]]:
    sidecar = sidecar or LED
    script = scripted or Scripted(cp.digest8_of(sidecar))
    bridge = CompactBridge("script", "unix:/unused", sidecar, state_dir=tmp / "bridge", timing=FAST, opener=script.open)
    await bridge.start()
    client = await Client.from_transport(await bridge.connector(), client_info={"name": "bhms-gateway", "version": "t"})
    try:
        if served:
            await wait_served(bridge)
        yield client, bridge, script
    finally:
        await client.close()
        await bridge.close()
        await script.close()


__all__ = ["Scripted", "scripted_rig"]
