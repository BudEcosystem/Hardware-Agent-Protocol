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
from bhms.protocol.errors import BhmsError
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


async def test_an_intent_is_not_observable_before_its_sync_has_completed(rig, tmp_path, monkeypatch):  # R47, OPS-003
    """No observer (a subscriber, operations/list, operations/get) learns of an operation whose dispatching record is
    written but not yet durable: after a power loss it would vanish. Once the sync completes, the subscriber hears
    accepted then dispatching, in order, and list/get show it."""
    srv, client, spy, calls = rig
    shared = srv.store.wait_synced  # a busy server: the intent's sync runs in the sync thread, where it is held
    monkeypatch.setattr(srv.store, "wait_synced", lambda ticket, inline=False: shared(ticket))
    spy.gate = threading.Event()
    watcher = await connect(f"unix:{tmp_path}/s.sock")
    sub = await watcher.subscribe(operations={"deviceIds": ["dev-5"]})
    try:
        invoke = asyncio.ensure_future(client.actions_invoke("dev-5", "set_point", {"value": 7}, wait_ms=0))
        rec = None
        for _ in range(400):
            rec = next((r for r in srv.journal.live() if r.op.get("deviceId") == "dev-5"), None)
            if rec is not None:
                break
            await asyncio.sleep(0.005)
        assert rec is not None and srv.store.synced_seq < rec.sync_ticket  # committed, not durable
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.__anext__(), 0.2)
        listed = (await watcher.operations_list(device_id="dev-5")).operations
        assert listed == []
        with pytest.raises(BhmsError) as info:
            await watcher.operations_get(rec.id)
        assert info.value.bhms_code == "INVALID_ARGUMENT"
        assert not invoke.done()
        spy.gate.set()
        op = (await invoke).operation
        states = []
        while len(states) < 2:
            item = await asyncio.wait_for(sub.__anext__(), 2)
            states.append(item.params.operation.state)
        assert states == ["accepted", "dispatching"]
        assert [o.operation_id for o in (await watcher.operations_list(device_id="dev-5")).operations] == [op.operation_id]
        assert (await watcher.operations_get(op.operation_id)).operation.operation_id == op.operation_id
    finally:
        spy.gate.set()
        await sub.cancel()
        await watcher.close()


async def test_a_failed_intent_sync_is_reported_settled_even_with_wait_ms_0(rig):  # Task 12b fix round 1
    srv, client, spy, calls = rig
    spy.fail = True
    op = (await client.actions_invoke("dev-6", "set_point", {"value": 1}, wait_ms=0)).operation
    assert op.state == "failed" and op.error.may_have_acted is False and op.effect == "none"
    assert calls == []


async def test_after_a_failed_sync_later_operations_are_never_held(rig, tmp_path):  # fix round 2, N1
    """The store refuses every barrier after a failed sync; each operation that waits on one is released at once with its
    settled outcome (here: failed, nothing sent), never left invisible."""
    srv, client, spy, calls = rig
    spy.fail = True
    first = (await client.actions_invoke("dev-6", "set_point", {"value": 1}, wait_ms=2000)).operation
    assert first.state == "failed"
    assert srv.store.probe_writable()  # a non-barrier write still works: the degraded audit is lifted (BHMS-AUTH-025)
    srv._journal_ok = True
    watcher = await connect(f"unix:{tmp_path}/s.sock")
    sub = await watcher.subscribe(operations={"deviceIds": ["dev-7"]})
    try:
        second = (await client.actions_invoke("dev-7", "set_point", {"value": 1}, wait_ms=2000)).operation
        assert second.state == "failed" and second.error.may_have_acted is False
        assert srv.journal._held == {}
        assert (await watcher.operations_get(second.operation_id)).operation.state == "failed"
        assert [o.operation_id for o in (await watcher.operations_list(device_id="dev-7")).operations] == [second.operation_id]
        states = []
        while "failed" not in states:
            states.append((await asyncio.wait_for(sub.__anext__(), 2)).params.operation.state)
        assert states[0] == "accepted" and states[-1] == "failed"
    finally:
        await sub.cancel()
        await watcher.close()


async def test_a_listed_page_keeps_its_cursor_when_a_held_record_falls_in_it(rig, monkeypatch):  # fix round 2, N3
    srv, client, spy, calls = rig
    older = [(await client.actions_invoke("dev-1", "set_point", {"value": i}, wait_ms=2000)).operation.operation_id
             for i in range(3)]
    shared = srv.store.wait_synced  # a busy server: the new intent's sync runs in the thread, where it is held
    monkeypatch.setattr(srv.store, "wait_synced", lambda ticket, inline=False: shared(ticket))
    spy.gate = threading.Event()
    invoke = asyncio.ensure_future(client.actions_invoke("dev-2", "set_point", {"value": 7}, wait_ms=0))
    try:
        for _ in range(400):
            if srv.journal._held:
                break
            await asyncio.sleep(0.005)
        assert srv.journal._held
        seen, cursor = [], None
        while True:
            page = await client.operations_list(limit=2, cursor=cursor)
            seen += [o.operation_id for o in page.operations]
            cursor = page.next_cursor
            if cursor is None:
                break
        assert sorted(seen) == sorted(older)  # every older operation reachable; the held one not shown
    finally:
        spy.gate.set()
    await invoke


@pytest.fixture
async def blocking(tmp_path, monkeypatch):
    """A durable server with one device whose ``go(1)`` waits for ``release`` (so that later operations queue)."""
    spy = SyncSpy()
    monkeypatch.setattr(store_module.os, "fdatasync", spy)
    srv = DeviceServer("held-transition", state_dir=tmp_path / "state")
    dev = srv.device("d", resources=["d"])
    dev.report_alive()
    release = asyncio.Event()

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000, cancel="supported")
    async def go(ctx, value: Range(0, 100, unit="1")) -> None:  # noqa: F821
        if value == 1:
            await release.wait()

    url, listener = await serve(srv, tmp_path)
    spy.store = srv.store
    client = await connect(url)
    try:
        yield srv, client, spy, release, url
    finally:
        if spy.gate is not None:
            spy.gate.set()
        release.set()
        await client.close()
        await listener.close()
        await srv.close()


def thread_syncs(monkeypatch, srv) -> None:
    """As on a busy server: intents are synced in the sync thread (where the spy can hold them), never inline."""
    shared = srv.store.wait_synced
    monkeypatch.setattr(srv.store, "wait_synced", lambda ticket, inline=False: shared(ticket))


async def test_a_queued_accepted_is_durable_before_it_is_answered_or_observed(blocking, monkeypatch):  # R57
    srv, client, spy, release, url = blocking
    await client.actions_invoke("d", "go", {"value": 1}, wait_ms=0)  # holds the device
    thread_syncs(monkeypatch, srv)
    spy.gate = threading.Event()
    watcher = await connect(url)
    sub = await watcher.subscribe(operations={"deviceIds": ["d"]})
    try:
        queued = asyncio.ensure_future(client.actions_invoke("d", "go", {"value": 2}, wait_ms=0))
        rec = None
        for _ in range(400):
            rec = next((r for r in srv.journal.live() if r.state == "accepted"), None)
            if rec is not None:
                break
            await asyncio.sleep(0.005)
        assert rec is not None and srv.store.synced_seq < rec.sync_ticket
        await asyncio.sleep(0.1)
        assert not queued.done()  # not answered before its accepted record is durable
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.__anext__(), 0.2)
        assert (await watcher.operations_list(device_id="d")).operations[0].state != "accepted"
        spy.gate.set()
        op = (await queued).operation
        assert op.state == "accepted" and srv.store.synced_seq >= rec.sync_ticket
        assert (await asyncio.wait_for(sub.__anext__(), 2)).params.operation.state == "accepted"
    finally:
        spy.gate.set()
        await sub.cancel()
        await watcher.close()


async def test_a_queued_operation_stays_visible_while_its_dispatch_is_syncing(blocking, monkeypatch):  # R57, N2
    """Observability is monotonic: an operation already answered as accepted stays visible (as accepted) while its
    dispatching transition waits for its sync; the transition's own notification waits for the sync."""
    srv, client, spy, release, url = blocking
    await client.actions_invoke("d", "go", {"value": 1}, wait_ms=0)
    b = (await client.actions_invoke("d", "go", {"value": 2}, wait_ms=0)).operation
    assert b.state == "accepted"
    thread_syncs(monkeypatch, srv)
    spy.gate = threading.Event()
    sub = await client.subscribe(operations={"operationIds": [b.operation_id]})
    release.set()
    for _ in range(400):
        if b.operation_id in srv.journal._held:
            break
        await asyncio.sleep(0.005)
    assert srv.journal.get(b.operation_id).state == "dispatching"  # committed, its sync held
    assert (await client.operations_get(b.operation_id)).operation.state == "accepted"
    assert [o.state for o in (await client.operations_list(device_id="d")).operations
            if o.operation_id == b.operation_id] == ["accepted"]
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub.__anext__(), 0.2)
    spy.gate.set()
    done = (await client.operations_wait(b.operation_id, 2000)).operation
    assert done.state == "completed"
    states = []
    while "completed" not in states:
        states.append((await asyncio.wait_for(sub.__anext__(), 2)).params.operation.state)
    assert states[0] == "dispatching"
    await sub.cancel()


async def test_closing_the_store_releases_held_records(tmp_path):  # fix round 2, N1 (shutdown)
    from bhms.runtime.operations import Journal
    from bhms.runtime.store import Store

    store = Store(tmp_path / "s.db")
    journal = Journal(store)
    heard: list[str] = []
    journal.listeners.append(lambda rec, wire: heard.append(wire["state"]))
    rec = journal.create(principal="p", key="k", key_origin="client", kind="action", request_digest="d", arguments={},
                         private={}, device_id="d1", dispatch=True, defer_sync=True)
    assert not journal.observable(rec) and heard == []
    store.close()
    assert journal.observable(rec) and journal._held == {} and heard == ["accepted", "dispatching"]


async def test_a_queued_op_dispatched_during_its_accepted_sync_is_answered_only_when_durable(blocking, monkeypatch):
    """Fix round 3: the device frees up while the queued operation's accepted sync runs, so it is dispatched (a second
    barrier, a later ticket) before that sync completes. The invoker is answered only once what it is told is durable,
    and get/list show the operation, in that state, right after the answer (R57)."""
    srv, client, spy, release, url = blocking
    await client.actions_invoke("d", "go", {"value": 1}, wait_ms=0)  # holds the device
    thread_syncs(monkeypatch, srv)
    g1, g2 = threading.Event(), threading.Event()
    spy.gate = g1  # the accepted record's sync
    queued = asyncio.ensure_future(client.actions_invoke("d", "go", {"value": 2}, wait_ms=0))
    rec = None
    for _ in range(400):
        rec = next((r for r in srv.journal.live() if r.state == "accepted"), None)
        if rec is not None:
            break
        await asyncio.sleep(0.005)
    assert rec is not None
    accepted_ticket = rec.sync_ticket
    release.set()  # the first operation completes: the queued one is dispatched while its accepted sync is held
    for _ in range(400):
        if rec.state != "accepted":
            break
        await asyncio.sleep(0.005)
    assert rec.state in ("dispatching", "running", "completed") and rec.sync_ticket > accepted_ticket
    spy.gate = g2  # the dispatching record's sync
    g1.set()
    await asyncio.sleep(0.1)
    assert not queued.done()  # its accepted record is durable now, but what it would be told (dispatching) is not
    g2.set()
    op = (await asyncio.wait_for(queued, 5)).operation
    assert srv.store.synced_seq >= rec.sync_ticket
    got = (await client.operations_get(op.operation_id)).operation
    listed = [o for o in (await client.operations_list(device_id="d")).operations if o.operation_id == op.operation_id]
    assert len(listed) == 1
    order = ["accepted", "dispatching", "running", "completed"]
    assert order.index(got.state) >= order.index(op.state) and order.index(listed[0].state) >= order.index(op.state)


async def test_a_state_filtered_list_uses_the_state_clients_see(blocking, monkeypatch):  # fix round 3
    srv, client, spy, release, url = blocking
    await client.actions_invoke("d", "go", {"value": 1}, wait_ms=0)
    b = (await client.actions_invoke("d", "go", {"value": 2}, wait_ms=0)).operation
    thread_syncs(monkeypatch, srv)
    spy.gate = threading.Event()
    release.set()
    for _ in range(400):
        if b.operation_id in srv.journal._held:
            break
        await asyncio.sleep(0.005)
    assert srv.journal.get(b.operation_id).state == "dispatching"  # stored; its sync held, clients still see accepted
    accepted = [o.operation_id for o in (await client.operations_list(state="accepted")).operations]
    dispatching = [o.operation_id for o in (await client.operations_list(state="dispatching")).operations]
    assert b.operation_id in accepted and b.operation_id not in dispatching
    spy.gate.set()


async def test_a_queued_op_whose_dispatch_sync_fails_is_answered_with_its_outcome(blocking, monkeypatch):  # 12b carried
    """Task 12b review (deferred to 15a): a queued operation dispatched while its accepted sync runs, whose syncs then fail,
    was answered ``dispatching`` (a state that is not durable and that it never keeps). Like an immediate dispatch, the
    invoker waits for the execution, which settles it ``failed`` with ``mayHaveActed: false`` without calling the handler."""
    srv, client, spy, release, url = blocking
    await client.actions_invoke("d", "go", {"value": 1}, wait_ms=0)  # holds the device
    thread_syncs(monkeypatch, srv)
    gate = threading.Event()
    spy.gate = gate  # the accepted record's sync
    queued = asyncio.ensure_future(client.actions_invoke("d", "go", {"value": 2}, wait_ms=0))
    rec = None
    for _ in range(400):
        rec = next((r for r in srv.journal.live() if r.state == "accepted"), None)
        if rec is not None:
            break
        await asyncio.sleep(0.005)
    assert rec is not None
    release.set()  # dispatched while its accepted sync is held
    for _ in range(400):
        if rec.state != "accepted":
            break
        await asyncio.sleep(0.005)
    assert rec.state == "dispatching"
    spy.fail = True
    gate.set()
    op = (await asyncio.wait_for(queued, 5)).operation
    assert op.state == "failed" and op.error.may_have_acted is False and op.effect == "none", op
