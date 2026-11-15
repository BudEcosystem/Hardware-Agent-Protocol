"""``connect(server)``: start a device server and hand back a connected client, with no sockets or subprocesses.

Example (a pytest test for your device)::

    async def test_move():
        async with connect(build()) as client:  # build() returns a DeviceServer, e.g. DeviceServer("demo", store=None)
            op = (await client.actions_invoke("stage", "move_to", {"target": 10}, wait_ms=1000)).operation
            assert op.state == "completed"

Thread-safety: one event loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from bhms.client.client import Client
from bhms.server.server import DeviceServer
from bhms.testing.memory import connect_in_process


@asynccontextmanager
async def connect(server: DeviceServer, *, strict: bool = True) -> AsyncIterator[Client]:
    """Start ``server``, connect an in-process :class:`Client` (``strict``: every message is schema-validated) and close both."""
    await server.start()
    client = None
    try:
        client = await Client.from_transport(await connect_in_process(server.rpc), strict=strict)
        yield client
    finally:
        if client is not None:
            await client.close()
        await server.close()
