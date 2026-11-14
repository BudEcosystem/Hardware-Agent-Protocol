"""A DeviceServer child process for the crash-window tests (tests/test_crash_recovery.py).

Usage: ``python crash_server.py <state_dir> <socket_path>`` with environment:

* ``CRASH_PAUSE`` — ``before-start`` (after the dispatch record is committed, before the handler can run),
  ``before-settle`` (after the handler returned, before its outcome is recorded) or ``in-batch`` (group commit: the first
  ``fdatasync`` of the WAL after start-up is slowed by 0.3 s so that later intents pile up behind it, and the second, the
  one that would cover that batch, never runs; the server behaves as a busy one, whose intents are synced in the store's
  sync thread). At that point the process writes ``<state_dir>/paused`` and stops itself
  with SIGSTOP so the test can SIGKILL it exactly there. ``in-batch`` also writes ``<state_dir>/durable_wal_size``: the
  WAL's size when the completed ``fdatasync`` began, i.e. what a power loss at the pause is guaranteed to keep (the
  background checkpointer is held off in this mode, so nothing else reaches stable storage).
* ``RECONCILE`` — ``1`` to answer reconciliation from the device log, ``0`` to leave unknown operations unknown.
* ``DEVICES`` — how many devices (``arm-1`` .. ``arm-N``, each its own resource; default 1).

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
from bhms.runtime import store as store_module
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

    def paused_start(self, rec, *args, **kwargs):  # the dispatch record is committed; the handler cannot run yet
        freeze("before-start")
        return original_start(self, rec, *args, **kwargs)

    executor_module.Executor._start = paused_start  # type: ignore[method-assign]
elif pause == "before-settle":
    original_settle = executor_module.Executor._settle

    def paused_settle(self, execution, outcome):  # the handler has returned; nothing recorded yet
        freeze("before-settle")
        return original_settle(self, execution, outcome)

    executor_module.Executor._settle = paused_settle  # type: ignore[method-assign]
elif pause == "in-batch":
    armed = False
    flush_sizes: list[int] = []
    syncs = 0
    original_start_flush = store_module.Store._start_flush
    original_fdatasync = os.fdatasync

    def recording_start_flush(self):  # on the event loop: no commit is half-written while it runs
        if armed:
            flush_sizes.append(os.path.getsize(f"{self.path}-wal"))
        return original_start_flush(self)

    def batching_fdatasync(fd: int) -> None:
        global syncs
        if not armed:
            return original_fdatasync(fd)
        syncs += 1
        if syncs == 1:
            import time

            time.sleep(0.3)  # the intents of the other requests arrive and wait for the next sync
            original_fdatasync(fd)
            (state_dir / "durable_wal_size").write_text(str(flush_sizes[0]))
            return None
        freeze("in-batch")  # the sync that would cover the batch: killed before it runs
        return None

    store_module.Store._start_flush = recording_start_flush  # type: ignore[method-assign]
    # as on a busy server: every intent is synced in the store's sync thread (a lone intent would be synced inline)
    original_wait_synced = store_module.Store.wait_synced
    store_module.Store.wait_synced = (  # type: ignore[method-assign]
        lambda self, ticket, inline=False: original_wait_synced(self, ticket))
    store_module.os.fdatasync = batching_fdatasync  # type: ignore[attr-defined]
    original_checkpointer = store_module._Checkpointer.__init__
    store_module._Checkpointer.__init__ = (  # type: ignore[method-assign]
        lambda self, path, *, every=10**9, interval_s=3600.0: original_checkpointer(self, path, every=every,
                                                                                    interval_s=interval_s))


def log_line(text: str) -> None:
    with open(device_log, "a") as handle:
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def device_entries() -> list[str]:
    return device_log.read_text().splitlines() if device_log.exists() else []


srv = DeviceServer("crash-server", state_dir=state_dir)


def declare(device_id: str) -> None:
    arm = srv.device(device_id, resources=[device_id])
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


for index in range(1, int(os.environ.get("DEVICES", "1")) + 1):
    declare(f"arm-{index}")


async def main() -> None:
    global armed
    await srv.listen(f"unix:{socket_path}")
    armed = True
    (state_dir / "ready").write_text(str(os.getpid()))
    await asyncio.Event().wait()


asyncio.run(main())
