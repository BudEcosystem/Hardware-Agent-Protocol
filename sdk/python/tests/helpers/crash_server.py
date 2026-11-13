"""A DeviceServer child process for the crash-window tests (tests/test_crash_recovery.py).

Usage: ``python crash_server.py <state_dir> <socket_path>`` with environment:

* ``CRASH_PAUSE`` — ``before-start`` (after the dispatch record is durable, before the handler runs) or
  ``before-settle`` (after the handler returned, before its outcome is recorded). At that point the process writes
  ``<state_dir>/paused`` and stops itself with SIGSTOP so the test can SIGKILL it exactly there.
* ``RECONCILE`` — ``1`` to answer reconciliation from the device log, ``0`` to leave unknown operations unknown.

The "device" is ``<state_dir>/device.log``: the physical side records ``start <operationId>`` before acting and
``done <operationId>`` after, and fsyncs each line, like a device-side command journal. The reconcile hook answers from
it: ``done`` -> completed, ``start`` only -> failed (interrupted, may have acted), nothing -> failed with proof that no
command executed.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from bhms import DeviceServer, Range, Reconciled
from bhms.server import executor as executor_module

state_dir = Path(sys.argv[1])
socket_path = sys.argv[2]
pause = os.environ.get("CRASH_PAUSE", "")
reconcile_enabled = os.environ.get("RECONCILE", "1") == "1"
device_log = state_dir / "device.log"


def freeze(where: str) -> None:
    (state_dir / "paused").write_text(where)
    os.kill(os.getpid(), signal.SIGSTOP)


if pause == "before-start":
    original_start = executor_module.Executor._start

    def paused_start(self, rec, *args, **kwargs):  # the dispatch record is already committed (barrier)
        freeze("before-start")
        return original_start(self, rec, *args, **kwargs)

    executor_module.Executor._start = paused_start  # type: ignore[method-assign]
elif pause == "before-settle":
    original_settle = executor_module.Executor._settle

    def paused_settle(self, execution, outcome):  # the handler has returned; nothing recorded yet
        freeze("before-settle")
        return original_settle(self, execution, outcome)

    executor_module.Executor._settle = paused_settle  # type: ignore[method-assign]


def log_line(text: str) -> None:
    with open(device_log, "a") as handle:
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def device_entries() -> list[str]:
    return device_log.read_text().splitlines() if device_log.exists() else []


srv = DeviceServer("crash-server", state_dir=state_dir)
arm = srv.device("arm-1", resources=["arm-1"])
arm.report_alive()


@arm.action(effect="reversible", idempotency="absolute", max_duration_ms=60_000)
async def move(ctx, x: Range(0, 100, unit="mm")) -> {"x": "mm"}:  # noqa: F821
    log_line(f"start {ctx.operation_id}")
    if os.environ.get("HANG") == "1":
        (state_dir / "running").write_text(ctx.operation_id)
        await asyncio.sleep(3600)
    log_line(f"done {ctx.operation_id}")
    return {"x": x}


@arm.reconcile
async def reconcile(op):
    if not reconcile_enabled:
        return None
    entries = device_entries()
    if f"done {op['operationId']}" in entries:
        return Reconciled("completed", evidence="device log records the command as done",
                          result={"x": op["arguments"]["x"]})
    if f"start {op['operationId']}" in entries:
        return Reconciled("failed", evidence="device log records the command as started but not finished",
                          message="interrupted by a server crash", may_have_acted=True)
    return Reconciled("failed", evidence="device log has no record of the command", effect="none",
                      message="the command never reached the device", may_have_acted=False)


async def main() -> None:
    await srv.listen(f"unix:{socket_path}")
    (state_dir / "ready").write_text(str(os.getpid()))
    await asyncio.Event().wait()


asyncio.run(main())
