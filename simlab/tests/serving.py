"""Serve SimLab device servers in-process and talk to them with the real BHMS client (no mocks)."""

from __future__ import annotations

import contextlib
import itertools
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from bhms.client.client import Client
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.server.server import DeviceServer

_counter = itertools.count()


@contextlib.asynccontextmanager
async def serving(server: DeviceServer, directory: Path) -> AsyncIterator[Client]:
    """``async with serving(srv, tmp_path) as client``: listen on a Unix socket, connect a strict client."""
    path = f"unix:{directory}/s{next(_counter)}.sock"
    listener = await server.listen(path)
    client = await Client.connect(path, strict=True)
    try:
        yield client
    finally:
        await client.close()
        await listener.close()
        await server.close()


async def run(client: Client, device: str, action: str, arguments: dict[str, Any] | None = None, *,
              key: str | None = None, wait_ms: int = 20_000):
    """Invoke and wait for a settled operation; returns the ``Operation``. An action that requires a lease (every hazardous
    one, BHMS-DEV-033) gets one for the resources the refusal names, held until the operation has settled."""
    try:
        result = await client.actions_invoke(device, action, arguments or {}, operation_key=key, wait_ms=wait_ms)
    except BhmsError as exc:
        if exc.bhms_code != "LEASE_REQUIRED":
            raise
        async with leased(client, exc.bound) as lease_id:
            result = await client.actions_invoke(device, action, arguments or {}, operation_key=key, wait_ms=wait_ms,
                                                 lease_id=lease_id)
            if not result.operation.settled:
                result = await client.operations_wait(result.operation.operation_id, 60_000)
    return result.operation


@contextlib.asynccontextmanager
async def leased(client: Client, resources: list[str], ttl_ms: int = 120_000) -> AsyncIterator[str]:
    """Hold a lease on ``resources`` for the block; yields the lease id."""
    lease = (await client.leases_acquire(list(resources), ttl_ms)).lease
    try:
        yield lease.lease_id
    finally:
        with contextlib.suppress(BhmsError):
            await client.leases_release(lease.lease_id)


async def read(client: Client, device: str, prop: str, *, fresh: bool = True):
    return (await client.properties_read(device, prop, fresh=fresh)).observation


async def described(client: Client, device: str) -> dict[str, Any]:
    desc = (await client.devices_describe(device)).description.model_dump(by_alias=True, exclude_unset=True)
    schema.validate("DeviceDescription", desc)
    return desc
