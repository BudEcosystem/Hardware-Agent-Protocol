"""Crash-recovery time: SIGKILL a durable server holding N running operations, restart it, time until it serves.

The server has ``D`` devices (so the cost of declaring devices is a constant, measured with N=0) and N of them hold a ``hang``
operation that is running (``dispatching``/``running`` in the journal) when the process is killed. On restart the runtime must
settle every such operation to ``unknown`` (BHMS-OPS recovery: the SDK cannot know whether the effect happened). Reported:

* ``to_ready_s``: spawn -> the listener accepts (``ready`` line; includes interpreter start, imports, device declaration,
  store open with WAL replay and recovery);
* ``to_first_response_s``: spawn -> first successful ``server/discover`` over a new connection;
* ``unknown_after``: how many operations ``operations/list state=unknown`` reports (must equal N: nothing lost, nothing invented).

``N=0`` is the control for the constant part.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from common import DEVICE_SERVER, Context, ServerProc, spawn_server, timed
from bhms.client.client import Client

NAME = "recovery"


async def cell(ctx: Context, devices: int, unknown: int) -> dict:
    with tempfile.TemporaryDirectory(dir=ctx.state_root) as tmp:
        sock = Path(tmp) / "b.sock"
        url = f"unix:{sock}"
        args = ["--listen", url, "--durability", "dispatch", "--state-dir", tmp, "--devices", str(devices), "--queue-limit", "1024"]
        server = spawn_server(DEVICE_SERVER, args, url=url)
        try:
            if unknown:
                async with await Client.connect(url, timeout=120) as client:
                    await asyncio.gather(*(client.actions_invoke(f"dev-{i}", "hang", {}, operation_key=f"hang-{i}", wait_ms=0)
                                           for i in range(1, unknown + 1)))
        finally:
            server.kill()
        sock.unlink(missing_ok=True)
        row: dict = {"devices": devices, "unknown_expected": unknown, "journal_bytes": sum(f.stat().st_size for f in Path(tmp).glob("*")
                                                                                         if f.is_file())}
        with timed(row):
            started = time.perf_counter()
            server2: ServerProc = spawn_server(DEVICE_SERVER, args, url=url)
            row["to_ready_s"] = round(time.perf_counter() - started, 3)
            try:
                async with await Client.connect(url, timeout=120) as client:
                    row["to_first_response_s"] = round(time.perf_counter() - started, 3)
                    seen = 0
                    async for _ in client.iter_operations(state="unknown"):
                        seen += 1
                row["unknown_after"] = seen
            finally:
                server2.stop()
    return row


async def run(ctx: Context) -> dict:
    sizes = [(10, 0), (10, 10), (100, 100)] if ctx.quick else [(1000, 0), (10, 10), (100, 100), (1000, 1000)]
    out: dict = {}
    for devices, unknown in sizes:
        out[f"devices={devices} unknown={unknown}"] = await cell(ctx, devices, unknown)
    return out
