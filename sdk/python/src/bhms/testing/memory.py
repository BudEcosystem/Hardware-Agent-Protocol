"""In-memory transports: connect a client session to a server in the same process without sockets.

``memory_pair()`` returns two connected :class:`~bhms.transport.base.Transport` ends (what one sends the other receives,
whole messages, in order). :func:`connect_in_process` serves a :class:`~bhms.jsonrpc.dispatcher.Server` on one end and
returns the client end, so a gateway can have thousands of upstreams in one process
(:mod:`bhms.testing.gateway_fleet`) and unit tests need no ports or paths.

The principal of the server end is the in-process creator: ``Peer("unix", uid=os.getuid())``, which the default policies
treat as the same-uid administrator (use ``peer=`` to present another identity).

Example::

    transport = await connect_in_process(device_server.rpc)
    client = await Client.from_transport(transport)

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import os

from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.transport.base import DEFAULT_MAX_MESSAGE_BYTES, Peer, Transport, TransportClosed


class MemoryTransport(Transport):
    """One end of a :func:`memory_pair`."""

    def __init__(self, peer: Peer, max_message_bytes: int) -> None:
        self.peer = peer
        self.max_message_bytes = max_message_bytes
        self._inbox: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._other: MemoryTransport | None = None
        self._closed = False

    async def send(self, data: bytes) -> None:
        if self._closed or self._other is None or self._other._closed:
            raise TransportClosed("memory transport is closed")
        self._other._inbox.put_nowait(data)

    async def receive(self) -> bytes:
        item = await self._inbox.get()
        if item is None:
            self._inbox.put_nowait(None)
            raise TransportClosed("memory transport is closed")
        return item

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbox.put_nowait(None)
        if self._other is not None and not self._other._closed:
            self._other._inbox.put_nowait(None)


def memory_pair(*, peer: Peer | None = None, max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES
                ) -> tuple[MemoryTransport, MemoryTransport]:
    """Two connected ends; ``peer`` is who the *server* end sees (default: this process's uid on a Unix peer)."""
    client = MemoryTransport(Peer("memory", address="in-process"), max_message_bytes)
    server = MemoryTransport(peer or Peer("unix", address="in-process", uid=os.getuid(), gid=os.getgid(),
                                          pid=os.getpid()), max_message_bytes)
    client._other, server._other = server, client
    return client, server


async def connect_in_process(rpc: RpcServer, *, peer: Peer | None = None,
                             max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> MemoryTransport:
    """Serve ``rpc`` on a new connection and return the client end."""
    client, server = memory_pair(peer=peer, max_message_bytes=max_message_bytes)
    task = asyncio.get_running_loop().create_task(rpc.handle_connection(server), name="bhms-memory-connection")
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
    return client


__all__ = ["MemoryTransport", "connect_in_process", "memory_pair"]
