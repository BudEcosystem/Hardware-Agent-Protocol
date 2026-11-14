"""Group commit at dispatch (Ruling R12, Task 12b): concurrent intents share fsyncs, and no handler runs, and no invoke is
answered, before the fsync covering its own ``dispatching`` record has returned (BHMS-OPS-003).

The device server runs on a durable store in ``tmp_path``; ``os.fdatasync`` *as the store calls it* is replaced by a spy that
records which commits each call covers and can be slowed, held or failed.

Requirement IDs: BHMS-OPS-003, BHMS-OPS-009, BHMS-AUTH-021.
"""

from __future__ import annotations

import asyncio
import errno
import os
import threading
import time

import pytest

from bhms import DeviceServer, Range
from bhms.runtime import store as store_module
from helpers.devices import connect, serve

DEVICES = 24


class SyncSpy:
    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.store = None
        self.covered: list[int] = []  # for each completed fdatasync: the commits made before it started
        self.gate: threading.Event | None = None
        self.fail = False

    def __call__(self, fd: int) -> None:
        started = self.store.commit_seq if self.store is not None else 0  # (None: the store's own creation barrier)
        if self.gate is not None:
            self.gate.wait(10)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise OSError(errno.EIO, "Input/output error")
        os.fsync(fd)
        self.covered.append(started)


@pytest.fixture
async def rig(tmp_path, monkeypatch):
    spy = SyncSpy()
    monkeypatch.setattr(store_module.os, "fdatasync", spy)
    srv = DeviceServer("group-commit", state_dir=tmp_path / "state")
    calls: list[tuple[str, int]] = []  # (operation id, the store's synced commit when its handler started)
    for i in range(DEVICES):
        dev = srv.device(f"dev-{i}", resources=[f"dev-{i}"])
        dev.report_alive()

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000, cancel="supported")
        async def set_point(ctx, value: Range(0, 100, unit="1")) -> None:  # noqa: F821
            calls.append((ctx.operation_id, srv.store.synced_seq))

    url, listener = await serve(srv, tmp_path)
    spy.store = srv.store
    client = await connect(url)
    try:
        yield srv, client, spy, calls
    finally:
        spy.fail = False
        if spy.gate is not None:
            spy.gate.set()
        await client.close()
        await listener.close()
        await srv.close()


async def test_concurrent_intents_on_distinct_devices_share_fsyncs_and_no_handler_runs_early(rig):
    srv, client, spy, calls = rig
    spy.delay = 0.01  # a slow disk: intents arrive while a sync runs
    results = await asyncio.gather(*(client.actions_invoke(f"dev-{i % DEVICES}", "set_point", {"value": i % 100},
                                                           wait_ms=5000) for i in range(96)))
    assert {r.operation.state for r in results} == {"completed"}
    assert len(calls) == 96
    tickets = {op_id: srv.journal.get(op_id).sync_ticket for op_id, _ in calls}
    early = [(op_id, synced, tickets[op_id]) for op_id, synced in calls if synced < tickets[op_id]]
    assert early == []  # every handler started after the fsync covering its dispatching record had returned
    assert len(spy.covered) < 48, f"{len(spy.covered)} fsyncs for 96 intents: no group commit"


async def test_the_reply_is_not_sent_before_the_intent_is_durable(rig):
    srv, client, spy, calls = rig
    spy.delay = 0.02
    res = await client.actions_invoke("dev-0", "set_point", {"value": 1}, wait_ms=0)
    rec = srv.journal.get(res.operation.operation_id)
    assert res.operation.state in ("dispatching", "running", "completed")
    assert srv.store.synced_seq >= rec.sync_ticket > 0


async def test_a_failed_intent_sync_sends_nothing_and_says_so(rig):
    srv, client, spy, calls = rig
    spy.fail = True
    res = await client.actions_invoke("dev-1", "set_point", {"value": 5}, wait_ms=2000)
    op = res.operation
    assert calls == []  # the handler was never called
    assert op.state == "failed" and op.effect == "none"
    assert op.error.bhms_code == "INTERNAL" and op.error.may_have_acted is False
    assert "could not be made durable" in op.error.message and "nothing was sent" in op.error.message
    assert srv.journal_ok is False  # degraded (BHMS-AUTH-025): ordinary operations are refused from now on


async def test_a_stop_during_the_intent_sync_ends_the_operation_without_calling_the_handler(rig, monkeypatch):
    srv, client, spy, calls = rig
    shared = srv.store.wait_synced  # as on a busy server: the intent's sync runs in the sync thread, never inline
    monkeypatch.setattr(srv.store, "wait_synced", lambda ticket, inline=False: shared(ticket))
    spy.gate = threading.Event()  # the intent's fsync is held
    invoke = asyncio.ensure_future(client.actions_invoke("dev-2", "set_point", {"value": 9}, wait_ms=0))
    for _ in range(200):
        if any(r.op.get("deviceId") == "dev-2" for r in srv.journal.live()):
            break
        await asyncio.sleep(0.005)
    stop = await client.stop("test stop", device_ids=["dev-2"])
    assert stop.stops[0].cancel_requested_operations  # the operation was already dispatching: a cancel was requested
    spy.gate.set()
    op_id = (await invoke).operation.operation_id
    op = (await client.operations_wait(op_id, 2000)).operation
    assert calls == []
    assert op.state == "canceled" and op.effect == "none"
    assert "before the handler was called" in op.history[-1].detail


async def test_a_lone_client_pays_no_thread_hand_off_and_concurrent_clients_share_the_sync_thread(rig, monkeypatch):
    srv, client, spy, calls = rig
    threads: list[str] = []
    inner = spy.__call__

    def recording(fd: int) -> None:
        threads.append(threading.current_thread().name)
        inner(fd)

    monkeypatch.setattr(store_module.os, "fdatasync", recording)
    for i in range(5):  # one request at a time: nobody to share a sync with
        await client.actions_invoke("dev-3", "set_point", {"value": i}, wait_ms=2000)
    assert threads and set(threads) == {"MainThread"}
    threads.clear()
    spy.delay = 0.01
    await asyncio.gather(*(client.actions_invoke(f"dev-{i % DEVICES}", "set_point", {"value": 1}, wait_ms=5000)
                           for i in range(48)))
    assert any(name.startswith("bhms-store-sync") for name in threads) and len(threads) < 48


async def test_operations_queued_on_one_device_are_synced_inline(rig, monkeypatch):
    """Intents that cannot share a sync (one device runs one operation at a time) gain nothing from the sync thread:
    each is synced on the event loop, without the hand-off that a loaded host makes expensive."""
    srv, client, spy, calls = rig
    threads: list[str] = []
    inner = spy.__call__

    def recording(fd: int) -> None:
        threads.append(threading.current_thread().name)
        inner(fd)

    monkeypatch.setattr(store_module.os, "fdatasync", recording)
    results = await asyncio.gather(*(client.actions_invoke("dev-4", "set_point", {"value": i}, wait_ms=5000)
                                     for i in range(20)))
    assert {r.operation.state for r in results} == {"completed"}
    assert threads.count("MainThread") >= 18, threads  # (the first admissions may still find each other)
