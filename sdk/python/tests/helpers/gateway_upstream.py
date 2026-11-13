"""A durable device server on stdio: the real upstream process of the gateway's crash and isolation tests.

``python gateway_upstream.py <state_dir>``; environment: ``MEMORY=1`` (non-durable: a new epoch every start),
``RECONCILE=0`` (leave unknown operations unknown). The "device" is ``<state_dir>/device.log``: the physical side records
``start <operationId>`` before acting and ``done <operationId>`` after (fsynced), and the reconcile hook answers from it.
Device ``axis-1`` has ``move`` (fast), ``hold`` (runs until ``<state_dir>/release`` exists, up to 60 s; cancellable) and
a stop procedure. ``<state_dir>/pid`` holds the process id.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from bhms import DeviceServer, Range, Reconciled
from bhms.server.context import Canceled

state_dir = Path(sys.argv[1])
state_dir.mkdir(parents=True, exist_ok=True)
(state_dir / "pid").write_text(str(os.getpid()))
device_log = state_dir / "device.log"
memory = os.environ.get("MEMORY") == "1"
reconcile_enabled = os.environ.get("RECONCILE", "1") == "1"


def log_line(text: str) -> None:
    with open(device_log, "a") as handle:
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def entries() -> list[str]:
    return device_log.read_text().splitlines() if device_log.exists() else []


srv = DeviceServer("gw-upstream", state_dir=state_dir, **({"store": None} if memory else {}))
axis = srv.device("axis-1", name="Axis", description="A durable stdio test axis.", capabilities=["bhms.axis.linear"],
                  resources=["axis-1"])
axis.report_alive()


@axis.action(effect="reversible", idempotency="absolute", max_duration_ms=60_000)
async def move(ctx, x: Range(0, 100, unit="mm")) -> {"x": "mm"}:  # noqa: F821
    """Move to x."""
    log_line(f"start {ctx.operation_id}")
    log_line(f"done {ctx.operation_id}")
    return {"x": x}


@axis.action(effect="reversible", idempotency="relative", max_duration_ms=60_000, cancel="supported")
async def hold(ctx) -> None:
    """Run until released (or cancelled)."""
    log_line(f"start {ctx.operation_id}")
    for _ in range(1200):
        if (state_dir / "release").exists():
            log_line(f"done {ctx.operation_id}")
            return
        if await ctx.wait_cancelled(0.05):
            raise Canceled(effect="unverified", detail="cancelled")
    log_line(f"done {ctx.operation_id}")


@axis.on_stop(evidence="reported", max_duration_ms=100)
async def halt(ctx) -> None:
    log_line("stop")


@axis.reconcile
async def reconcile(op):
    if not reconcile_enabled:
        return None
    seen = entries()
    if f"done {op['operationId']}" in seen:
        return Reconciled("completed", evidence="device log: done", result={})
    if f"start {op['operationId']}" in seen:
        return Reconciled("failed", evidence="device log: started, not finished", message="interrupted",
                          may_have_acted=True)
    return Reconciled("failed", evidence="device log: no record", effect="none", message="never reached the device",
                      may_have_acted=False)


if __name__ == "__main__":
    srv.run()
