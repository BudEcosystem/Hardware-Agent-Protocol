"""``actions/invoke`` round trip per transport (unix, websocket, stdio) and durability mode, one client, sequential.

Modes: ``full`` (synchronous=FULL everywhere), ``dispatch`` (the default: NORMAL plus an fsync barrier on the intent), ``process``
(NORMAL, no barriers), ``memory`` (no store at all: the non-durable server). ``waitMs=0`` returns after admission and the durable
dispatch record; ``waitMs=1000`` returns after the completion is recorded. A fresh server process and state directory per cell.
The unix cell is the number the budget is judged on (``budgets.py``): one process, one client, an action that returns at once.
"""

from __future__ import annotations

import secrets

from common import Context, device_server, invoke_stats, timed, token_for
from bhms.client.client import Client

NAME = "invoke"


async def cell(ctx: Context, transport: str, durability: str, wait_ms: int, n: int) -> dict:
    tag = secrets.token_hex(3)
    async with device_server(ctx, durability, transport) as (target, _):
        async with await Client.connect(target, token=token_for(target), timeout=60) as client:
            async def call(i: int) -> None:
                res = await client.actions_invoke("dev-1", "set_point", {"value": abs(i)}, operation_key=f"{tag}-{i}",
                                                  wait_ms=wait_ms)
                if wait_ms and res.operation.state != "completed":
                    raise RuntimeError(res.operation.state)

            row: dict = {}
            with timed(row):
                row.update(await invoke_stats(call, n, 1, warmup=ctx.n(30, 200)))
            return row


async def run(ctx: Context) -> dict:
    n = ctx.n(100, 1000)
    out: dict = {"n": n}
    matrix = [("unix", d) for d in ("full", "dispatch", "process", "memory")]
    matrix += [("ws", "dispatch"), ("ws", "memory"), ("stdio", "dispatch"), ("stdio", "memory")]
    if ctx.quick:
        matrix = [("unix", "dispatch"), ("unix", "process"), ("unix", "memory"), ("ws", "dispatch"), ("stdio", "dispatch")]
    for transport, durability in matrix:
        for wait_ms in (0, 1000):
            out[f"{transport}/{durability}/waitMs={wait_ms}"] = await cell(ctx, transport, durability, wait_ms, n)
    return out
