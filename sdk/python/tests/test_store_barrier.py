"""Store barrier semantics and group commit (BHMS-OPS-003, BHMS-LSE-003; Ruling R12, Task 12b).

A barrier is a commit followed by an ``fdatasync`` of the WAL. Synchronous barriers are durable when ``transaction`` returns;
deferred barriers are durable when :meth:`Store.wait_synced` returns, and concurrent ones share their ``fdatasync``. The test
doubles below replace ``os.fdatasync`` *as the store calls it* and record which commits each call covers.
"""

from __future__ import annotations

import asyncio
import errno
import os
import threading
import time

import pytest

from bhms.runtime import store as store_module
from bhms.runtime.store import Store, StoreError


class SyncSpy:
    """Stands in for ``os.fdatasync`` inside the store: counts calls, checks they sync the WAL, can be slowed or failed."""

    def __init__(self, store: Store, *, delay: float = 0.0) -> None:
        self.store, self.delay = store, delay
        self.calls: list[tuple[int, int]] = []  # (commits made when the call started, when it returned)
        self.fail_next = 0
        self.gate: threading.Event | None = None
        self.paths: set[str] = set()

    def __call__(self, fd: int) -> None:
        started = self.store.commit_seq
        self.paths.add(os.readlink(f"/proc/self/fd/{fd}"))
        if self.gate is not None:
            self.gate.wait(10)
        if self.delay:
            time.sleep(self.delay)
        if self.fail_next:
            self.fail_next -= 1
            raise OSError(errno.EIO, "Input/output error")
        os.fsync(fd)
        self.calls.append((started, self.store.commit_seq))


@pytest.fixture
def dispatch_store(tmp_path):
    store = Store(tmp_path / "s.db", durability="dispatch")
    yield store
    store.close()


def spy_on(monkeypatch, store: Store, **kw) -> SyncSpy:
    spy = SyncSpy(store, **kw)
    monkeypatch.setattr(store_module.os, "fdatasync", spy)
    return spy


def test_a_barrier_syncs_the_wal_and_never_switches_the_safety_level(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store)
    statements: list[str] = []
    dispatch_store._db.set_trace_callback(statements.append)
    with dispatch_store.transaction(barrier=True):
        dispatch_store.meta_set("k", "v")
    dispatch_store._db.set_trace_callback(None)
    assert not [s for s in statements if s.startswith("PRAGMA")], statements  # no synchronous=FULL/NORMAL toggles
    assert len(spy.calls) == 1 and spy.paths == {str(dispatch_store.path) + "-wal"}
    assert dispatch_store.synced_seq == dispatch_store.commit_seq
    with dispatch_store.transaction():  # an ordinary commit is not synced
        dispatch_store.meta_set("k", "w")
    assert len(spy.calls) == 1 and dispatch_store.synced_seq == dispatch_store.commit_seq - 1


def test_nested_barrier_in_dispatch_mode_is_promoted_not_an_error(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store)
    with dispatch_store.transaction():  # NORMAL outer transaction
        dispatch_store.meta_set("a", "1")
        assert dispatch_store.next_counter("fence") == 1  # nested barrier: synced after the outer commit
        assert spy.calls == []
    assert len(spy.calls) == 1 and dispatch_store.synced_seq == dispatch_store.commit_seq
    assert dispatch_store.meta_get("a") == "1"
    assert dispatch_store.counter("fence") == 1
    with dispatch_store.transaction():  # still usable afterwards
        dispatch_store.meta_set("b", "2")
    assert dispatch_store.meta_get("b") == "2"


def test_nested_barrier_rolls_back_with_the_outer_transaction(dispatch_store):
    try:
        with dispatch_store.transaction():
            dispatch_store.next_counter("fence")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert dispatch_store.counter("fence") == 0
    with dispatch_store.transaction():
        dispatch_store.meta_set("c", "3")
    assert dispatch_store.meta_get("c") == "3"


async def test_a_deferred_barrier_is_durable_only_when_wait_synced_returns(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store)
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("intent", "x")
    ticket = dispatch_store.commit_seq
    assert spy.calls == [] and dispatch_store.synced_seq < ticket  # the commit returned before any sync
    await dispatch_store.wait_synced(ticket)
    assert len(spy.calls) == 1 and spy.calls[0][0] >= ticket and dispatch_store.synced_seq >= ticket
    await dispatch_store.wait_synced(ticket)  # already durable: no second sync
    assert len(spy.calls) == 1


async def test_concurrent_deferred_barriers_share_fsyncs_and_none_returns_early(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store, delay=0.02)  # a slow disk: commits pile up while a sync runs
    violations: list[str] = []

    async def writer(i: int) -> None:
        await asyncio.sleep(0.001 * (i % 7))
        with dispatch_store.transaction(barrier=True, defer_sync=True):
            dispatch_store.meta_set(f"intent:{i}", str(i))
        ticket = dispatch_store.commit_seq
        await dispatch_store.wait_synced(ticket)
        # durable only after a sync that started once this commit was made has returned
        if not any(started >= ticket for started, _ in spy.calls):
            violations.append(f"writer {i} (ticket {ticket}) returned before a covering sync: {spy.calls}")

    await asyncio.gather(*(writer(i) for i in range(60)))
    assert violations == []
    assert 1 <= len(spy.calls) <= 6, spy.calls  # 60 barriers, a handful of fsyncs
    assert dispatch_store.synced_seq == dispatch_store.commit_seq


async def test_the_event_loop_keeps_serving_while_a_deferred_sync_runs(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store)
    spy.gate = threading.Event()
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("intent", "1")
    waiter = asyncio.ensure_future(dispatch_store.wait_synced(dispatch_store.commit_seq))
    await asyncio.sleep(0.01)
    with dispatch_store.transaction():  # the journal is writable while the sync is blocked in its thread
        dispatch_store.meta_set("other", "2")
    assert not waiter.done()
    spy.gate.set()
    await asyncio.wait_for(waiter, 5)


async def test_a_cancelled_waiter_does_not_cancel_the_shared_sync(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store)
    spy.gate = threading.Event()
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("intent", "1")
    ticket = dispatch_store.commit_seq
    first = asyncio.ensure_future(dispatch_store.wait_synced(ticket))
    second = asyncio.ensure_future(dispatch_store.wait_synced(ticket))
    await asyncio.sleep(0.01)
    first.cancel()
    spy.gate.set()
    await asyncio.wait_for(second, 5)
    assert dispatch_store.synced_seq >= ticket and len(spy.calls) == 1
    with pytest.raises(asyncio.CancelledError):
        await first


async def test_a_failed_fsync_fails_that_barrier_and_every_later_one(dispatch_store, monkeypatch):
    spy = spy_on(monkeypatch, dispatch_store)
    spy.fail_next = 1
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("intent", "1")
    with pytest.raises(StoreError, match="could not be synced"):
        await dispatch_store.wait_synced(dispatch_store.commit_seq)
    # the kernel may have dropped the dirty pages: a later successful fdatasync would prove nothing
    with pytest.raises(StoreError, match="could not be synced"):
        with dispatch_store.transaction(barrier=True):
            dispatch_store.meta_set("fence", "2")
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("intent", "3")
    with pytest.raises(StoreError):
        await dispatch_store.wait_synced(dispatch_store.commit_seq)
    with dispatch_store.transaction():  # ordinary writes still work (a degraded journal can still record outcomes)
        dispatch_store.meta_set("outcome", "4")


async def test_stores_without_barriers_never_sync(tmp_path, monkeypatch):
    for store in (Store(tmp_path / "p.db", durability="process"), Store(tmp_path / "f.db", durability="full"),
                  Store(None)):
        try:
            spy = spy_on(monkeypatch, store)
            with store.transaction(barrier=True, defer_sync=True):
                store.meta_set("k", "v")
            await store.wait_synced(store.commit_seq)
            with store.transaction(barrier=True):
                store.meta_set("k", "w")
            assert spy.calls == [] and store.synced_seq == store.commit_seq
            expected = 2 if store.durability == "full" else 1  # "full": SQLite syncs every commit itself
            assert store.execute_scalar("PRAGMA synchronous") == (expected if store.durable else 1)
        finally:
            store.close()


async def test_a_finished_sync_whose_callback_has_not_run_yet_is_accounted_for_not_spun_on(dispatch_store):
    """The interleaving the AMD benchmark hit: the shared sync has finished (its future is done) but its done-callback is
    still queued when a waiter looks at it. Awaiting a finished future never yields, so a waiter that only awaited it
    would spin the event loop forever; it must account for the finished sync itself."""
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("intent", "1")
    ticket = dispatch_store.commit_seq
    finished: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    finished.set_result(None)  # done, and no callback has accounted for it
    dispatch_store._flight, dispatch_store._flight_target = finished, ticket
    await asyncio.wait_for(dispatch_store.wait_synced(ticket), 2)
    assert dispatch_store.synced_seq >= ticket and dispatch_store._flight is None


async def test_an_inline_wait_syncs_on_the_calling_thread_unless_a_shared_sync_is_running(dispatch_store, monkeypatch):
    threads: list[str] = []
    gate = threading.Event()

    def spy(fd: int) -> None:
        threads.append(threading.current_thread().name)
        if threading.current_thread() is not threading.main_thread():
            gate.wait(10)
        os.fsync(fd)

    monkeypatch.setattr(store_module.os, "fdatasync", spy)
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("a", "1")
    await dispatch_store.wait_synced(dispatch_store.commit_seq, inline=True)  # nothing running: no hand-off
    assert threads == ["MainThread"]
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("b", "2")
    shared = asyncio.ensure_future(dispatch_store.wait_synced(dispatch_store.commit_seq))
    await asyncio.sleep(0.01)
    with dispatch_store.transaction(barrier=True, defer_sync=True):
        dispatch_store.meta_set("c", "3")
    inline = asyncio.ensure_future(dispatch_store.wait_synced(dispatch_store.commit_seq, inline=True))
    await asyncio.sleep(0.01)
    assert not inline.done()  # a sync is running in the thread: the inline caller waits for it, then shares the next
    gate.set()
    await asyncio.wait_for(asyncio.gather(shared, inline), 5)
    assert threads[0] == "MainThread" and threads[1].startswith("bhms-store-sync")
    assert dispatch_store.synced_seq == dispatch_store.commit_seq


async def test_inline_callers_with_other_commits_waiting_share_one_sync_in_the_thread(dispatch_store, monkeypatch):
    threads: list[str] = []

    def spy(fd: int) -> None:
        threads.append(threading.current_thread().name)
        os.fsync(fd)

    monkeypatch.setattr(store_module.os, "fdatasync", spy)

    async def intent(key: str) -> None:
        with dispatch_store.transaction(barrier=True, defer_sync=True):
            dispatch_store.meta_set(key, "1")
        ticket = dispatch_store.commit_seq
        # an operation's admission and its execution wait on the same ticket: that is still one caller
        await asyncio.gather(dispatch_store.wait_synced(ticket, inline=True), dispatch_store.wait_synced(ticket, inline=True))

    await intent("lone")
    assert threads == ["MainThread"]
    threads.clear()
    await asyncio.gather(*(intent(f"k{i}") for i in range(8)))  # eight intents at once: nobody syncs alone
    assert threads and all(name.startswith("bhms-store-sync") for name in threads) and len(threads) < 8
    assert dispatch_store.synced_seq == dispatch_store.commit_seq


def test_a_deferred_barrier_cannot_join_an_outer_transaction(dispatch_store):  # fix round 1: tickets are own commits
    from bhms.runtime.operations import Journal

    journal = Journal(dispatch_store)
    with pytest.raises(RuntimeError, match="outer transaction"):
        with dispatch_store.transaction():
            journal.create(principal="p", key="k", key_origin="client", kind="action", request_digest="d",
                           arguments={}, private={}, device_id="d1", dispatch=True, defer_sync=True)
    with dispatch_store.transaction():  # a synchronous barrier may join: its ticket is the outer commit
        rec = journal.create(principal="p", key="k2", key_origin="client", kind="action", request_digest="d",
                             arguments={}, private={}, device_id="d1", dispatch=True)
        assert rec.sync_ticket == dispatch_store.commit_seq + 1
    assert dispatch_store.synced_seq >= rec.sync_ticket
