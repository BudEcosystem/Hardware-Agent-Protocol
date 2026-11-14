"""Regression tests for task review round 1 (queued dispatch vs stop, stop ordering, unjournalable results,
reconciliation invariants, program crash window, worker-thread journal access, small declaration/liveness fixes)."""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import threading
import time

import pytest

import bhms.runtime.store as store_module
from bhms import DeviceServer
from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import InvalidTransition, Journal
from bhms.runtime.store import Store, StoreError
from bhms.server.context import Reconciled
from bhms.server.decorators import DescriptionError
from helpers.devices import connect, serve


async def _open(tmp_path, name, setup, **kw):
    srv = DeviceServer(name, state_dir=tmp_path / name, **kw)
    state = setup(srv)
    url, listener = await serve(srv, tmp_path, name=f"{name}.sock")
    client = await connect(url)
    return srv, listener, client, state


async def _close(srv, listener, client):
    await client.close()
    await listener.close()
    await srv.close()


def _gated_device(srv):
    """ax with a gated action ``a``, a lease-requiring ``b`` guarded by a blockable freshness read, and on_stop."""
    st = {"b_ran": 0, "block": False, "stopped": 0}
    st["read_started"], st["read_go"], st["agate"] = asyncio.Event(), asyncio.Event(), asyncio.Event()
    dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
    dev.report_alive()

    @dev.property(unit="kPa", evidence="measured")
    async def pressure() -> float:
        if st["block"]:
            st["read_started"].set()
            await st["read_go"].wait()
        return 1.0

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000)
    async def a(ctx) -> None:
        await st["agate"].wait()

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000, requires_lease=True,
                requires_fresh={"pressure": 60})
    async def b(ctx) -> None:
        st["b_ran"] += 1

    @dev.on_stop(evidence="reported")
    def halt(ctx):
        st["stopped"] += 1

    return st


async def _park_b_in_freshness_read(client, st):
    lease = (await client.leases_acquire(["ax"], 5000)).lease
    await client.actions_invoke("ax", "a", {}, lease_id=lease.lease_id, operation_key="a")  # ax is leased (BHMS-LSE-014)
    rb = await client.actions_invoke("ax", "b", {}, lease_id=lease.lease_id, operation_key="b")
    assert rb.operation.state == "accepted"
    await asyncio.sleep(0.15)
    st["block"] = True
    st["agate"].set()  # a completes -> b leaves the queue -> its pre-dispatch freshness read blocks
    await asyncio.wait_for(st["read_started"].wait(), 2)
    return rb.operation.operation_id


async def test_stop_cancels_an_operation_in_its_predispatch_checks(tmp_path):  # finding 1; BHMS-AUTH-021, OPS-041
    srv, listener, client, st = await _open(tmp_path, "r1a", _gated_device)
    try:
        op_id = await _park_b_in_freshness_read(client, st)
        stop = (await client.stop("probe", device_ids=["ax"])).stops[0]
        assert op_id in stop.canceled_operations and stop.revoked_leases
        st["read_go"].set()
        await asyncio.sleep(0.2)
        op = (await client.operations_get(op_id)).operation
        assert st["b_ran"] == 0 and op.state == "canceled" and op.effect == "none"
        assert [h.state for h in op.history if h.kind == "state"] == ["accepted", "canceled"]
    finally:
        await _close(srv, listener, client)


async def test_cancel_during_predispatch_checks_is_clean(tmp_path):  # finding 1 (cancel race)
    srv, listener, client, st = await _open(tmp_path, "r1b", _gated_device)
    try:
        op_id = await _park_b_in_freshness_read(client, st)
        await client.operations_cancel(op_id, reason="changed my mind")
        st["read_go"].set()
        await asyncio.sleep(0.2)
        op = (await client.operations_get(op_id)).operation
        assert st["b_ran"] == 0 and op.state == "canceled"
        assert not srv.executor._busy and not srv.executor._pending  # the reservation was released
    finally:
        await _close(srv, listener, client)


async def test_lease_revoked_during_predispatch_checks_rejects(tmp_path):  # finding 1 (re-check after await)
    srv, listener, client, st = await _open(tmp_path, "r1c", _gated_device)
    try:
        op_id = await _park_b_in_freshness_read(client, st)
        for lease in list(srv.leases.active()):
            srv.leases.revoke_covering(["ax"], reason="test")
        st["read_go"].set()
        await asyncio.sleep(0.2)
        op = (await client.operations_get(op_id)).operation
        assert st["b_ran"] == 0 and op.state == "rejected" and op.error.may_have_acted is False
    finally:
        await _close(srv, listener, client)


async def test_stop_procedure_runs_before_any_journal_write(tmp_path):  # finding 2; BHMS-AUTH-020, AUTH-025
    seen: dict[str, int] = {}

    def setup(srv):
        dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
        dev.report_alive()

        @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000, cancel="supported")
        async def slow(ctx) -> None:
            await ctx.cancelled.wait()

        @dev.on_stop(evidence="reported")
        def halt(ctx):
            seen["sync"] = commits[0]

        dev2 = srv.device("ay", capabilities=["bhms.axis.linear"], resources=["ay"])
        dev2.report_alive()

        @dev2.on_stop(evidence="reported")
        async def halt2(ctx):
            seen["async"] = commits[0]
            await asyncio.sleep(0)

        return None

    commits = [0]
    srv, listener, client, _ = await _open(tmp_path, "r2", setup)
    try:
        for i in range(4):
            await client.actions_invoke("ax", "slow", {}, operation_key=f"k{i}")
        real = srv.store.transaction

        @contextlib.contextmanager
        def counting(**kw):
            commits[0] += 1
            with real(**kw):
                yield

        srv.store.transaction = counting
        res = await client.stop("go", device_ids=["ax", "ay"], wait_ms=500)
        assert seen == {"sync": 0, "async": 0}, "a stop procedure waited for journal writes"
        assert commits[0] > 0 and [s.outcome for s in res.stops] == ["confirmed", "confirmed"]
    finally:
        await _close(srv, listener, client)


async def test_stop_still_runs_when_the_journal_is_unwritable(tmp_path):  # finding 2; BHMS-AUTH-025
    ran = []

    def setup(srv):
        dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
        dev.report_alive()

        @dev.on_stop(evidence="reported")
        def halt(ctx):
            ran.append(1)

    srv, listener, client, _ = await _open(tmp_path, "r2b", setup)
    try:
        srv.store.set_writable(False)
        stop = (await client.stop("go", device_ids=["ax"], wait_ms=200)).stops[0]
        assert ran == [1] and stop.outcome == "confirmed" and stop.detail == "degraded-audit"
    finally:
        srv.store.set_writable(True)
        await _close(srv, listener, client)


def _result_device(srv):
    dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
    dev.report_alive()

    @dev.property(unit="mm", evidence="measured")
    def position() -> float:
        return 1.0

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def weird(ctx):
        return {"x": {1, 2}}

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def fine(ctx) -> None:
        return None

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000, completion_evidence="measured")
    async def mv(ctx) -> None:
        raise ValueError("handler bug after dispatch")

    answer: dict = {}

    @dev.reconcile
    async def rec(op):
        return answer.get("v")

    return answer


async def test_unjournalable_result_does_not_leave_the_operation_dispatching(tmp_path):  # finding 3
    srv, listener, client, _ = await _open(tmp_path, "r3", _result_device)
    try:
        op = (await client.actions_invoke("ax", "weird", {}, operation_key="w", wait_ms=1000)).operation
        assert op.state == "failed" and op.error.bhms_code == "INTERNAL" and op.error.may_have_acted is True
        assert "JSON" in op.error.message
        assert (await client.actions_invoke("ax", "fine", {}, operation_key="f", wait_ms=1000)).operation.state \
            == "completed"
    finally:
        await _close(srv, listener, client)


async def test_unexpected_settle_failure_makes_the_operation_unknown_and_keeps_the_resource_inhibited(tmp_path):
    srv, listener, client, _ = await _open(tmp_path, "r3b", _result_device)
    try:
        real = srv.journal.transition
        calls = []

        def flaky(rec, state, **kw):
            if state == "completed" and not calls:
                calls.append(1)
                raise RuntimeError("boom while settling")
            return real(rec, state, **kw)

        srv.journal.transition = flaky
        op = (await client.actions_invoke("ax", "fine", {}, operation_key="f1", wait_ms=1000)).operation
        assert op.state == "unknown" and op.error.bhms_code == "DEADLINE_EXCEEDED" and op.error.may_have_acted is True
        with pytest.raises(BhmsError) as refused:
            await client.actions_invoke("ax", "fine", {}, operation_key="f2")
        assert refused.value.hint and "unknown" in str(refused.value).lower()
    finally:
        await _close(srv, listener, client)


async def test_reconciliation_cannot_bypass_a_required_verified_effect(tmp_path):  # finding 4; BHMS-OPS-005/006
    srv, listener, client, answer = await _open(tmp_path, "r4", _result_device)
    try:
        r = (await client.actions_invoke("ax", "mv", {}, operation_key="k", require={"effect": "verified"},
                                         wait_ms=1000)).operation
        assert r.state == "unknown"
        answer["v"] = Reconciled("completed", evidence="operator says it looks fine", result={})
        await srv.reconcile()
        op = (await client.operations_get(r.operation_id)).operation
        assert op.state == "failed" and op.error.bhms_code == "UNVERIFIED" and op.effect != "verified"
    finally:
        await _close(srv, listener, client)


def test_reconciled_verified_needs_measured_observations():  # finding 4
    with pytest.raises(ValueError, match="observations"):
        Reconciled("completed", evidence="x", effect="verified")
    with pytest.raises(ValueError, match="observations"):
        Reconciled("completed", evidence="x", effect="verified",
                   observations={"position": {"evidence": "reported", "quality": "valid"}})
    Reconciled("completed", evidence="x", effect="verified",
               observations={"position": {"evidence": "measured", "quality": "valid"}})


def test_journal_refuses_unverifiable_completions(tmp_path):  # finding 4: the single mutation point
    store = Store(tmp_path / "j.db")
    try:
        journal = Journal(store)

        def op(require=None):
            rec = journal.create(principal="p", key=f"k{time.monotonic_ns()}", key_origin="client", kind="action",
                                 request_digest="sha256:x", arguments={}, device_id="ax", action="mv",
                                 require=require, private={"resources": ["ax"], "effectClass": "reversible"},
                                 dispatch=True)
            return rec

        required = op({"effect": "verified"})
        with pytest.raises(InvalidTransition, match="verified"):
            journal.transition(required, "completed", result={}, effect="unverified")
        with pytest.raises(InvalidTransition, match="measured"):
            journal.transition(required, "completed", result={}, effect="verified",
                               evidence={"kind": "reported"})
        plain = op()
        with pytest.raises(InvalidTransition, match="JSON"):
            journal.transition(plain, "completed", result={"x": {1, 2}})
        with pytest.raises(InvalidTransition, match="measured"):
            journal.transition(plain, "canceled", effect="verified")
        journal.transition(required, "completed", result={}, effect="verified", evidence={
            "kind": "measured", "observations": {"position": {"evidence": "measured", "quality": "valid"}}})
        assert required.state == "completed"
    finally:
        store.close()


def _program_with_unknown_child(tmp_path, child_state):
    path = tmp_path / "pr.db"
    store = Store(path)
    j = Journal(store)
    prog = j.create(principal="p", key="pk", key_origin="client", kind="program", request_digest="sha256:x",
                    arguments={}, program_digest="sha256:y", private={"resources": ["ax"], "effectClass": "reversible"})
    if child_state == "reconciled-completed":
        j.transition(prog, "dispatching")
        j.transition(prog, "running", detail="first step started")
    child = j.create(principal="p", key="d-1", key_origin="derived", kind="action", request_digest="sha256:z",
                     arguments={}, device_id="ax", action="mv", parent_id=prog.id,
                     private={"resources": ["ax"], "effectClass": "reversible"}, dispatch=True)
    if child_state == "reconciled-completed":
        j.transition(child, "unknown", error=_unknown())
        j.transition(prog, "unknown", error=_unknown())
        j._settle_parent_after_reconcile = lambda parent_id: None  # the crash falls between the child's reconciliation commit and the program's settle
        j.transition(child, "completed", result={}, effect="unverified", kind="reconciliation", detail="measured")
    store.close()
    return path, prog.id, child.id


def _unknown():
    from bhms.runtime.operations import unknown_error
    return unknown_error("test")


def test_recovery_consults_children_of_a_program_still_accepted(tmp_path):  # finding 5; BHMS-PRG-017
    path, prog_id, child_id = _program_with_unknown_child(tmp_path, "dispatched")
    store = Store(path)
    try:
        j = Journal(store)
        j.recover()
        parent, child = j.get(prog_id), j.get(child_id)
        assert child.state == "unknown"
        assert parent.state == "unknown", "a dispatched child is unresolved: the program is unknown, not rejected"
    finally:
        store.close()


def test_recovery_resettles_a_program_whose_children_were_all_reconciled(tmp_path):  # finding 5 (minor)
    path, prog_id, _ = _program_with_unknown_child(tmp_path, "reconciled-completed")
    store = Store(path)
    try:
        j = Journal(store)
        j.recover()
        parent = j.get(prog_id)
        assert parent.state == "failed" and parent.op["error"]["mayHaveActed"] is True
    finally:
        store.close()


async def test_program_is_dispatching_before_its_first_child_exists(tmp_path):  # finding 5; BHMS-PRG-017
    observed = []

    def setup(srv):
        dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
        dev.report_alive()

        @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
        async def go(ctx) -> None:
            return None

    srv, listener, client, _ = await _open(tmp_path, "r5", setup, policy=None)
    real = srv.journal.create

    def create(**kw):
        if kw.get("parent_id"):
            observed.append(srv.journal.get(kw["parent_id"]).state)
        return real(**kw)

    srv.journal.create = create
    try:
        program = {"bhmsProgram": "2026-11-13", "name": "one_step", "description": "Invoke go once.",
                   "input": {"type": "object", "additionalProperties": False, "properties": {}},
                   "maxDurationMs": 5000,
                   "steps": [{"kind": "invoke", "deviceId": "ax", "action": "go", "arguments": {}}],
                   "output": {}}
        res = await client.programs_run(program=program, arguments={}, operation_key="pk", wait_ms=2000)
        assert res.operation.state == "completed"
        assert observed == ["running"]
    finally:
        await _close(srv, listener, client)


async def test_blocking_handler_emits_through_the_event_loop_thread(tmp_path):  # finding 6
    seen: dict = {}

    def setup(srv):
        dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
        dev.report_alive()

        @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000, blocking=True)
        def blk(ctx) -> None:
            seen["worker"] = threading.get_ident()
            ctx.emit("device.fault", {"why": "probe"}, message="from the worker thread")

    srv, listener, client, _ = await _open(tmp_path, "r6", setup)
    writers = []
    real_append = srv.events.append

    def recording(*a, **k):
        writers.append(threading.get_ident())
        return real_append(*a, **k)

    srv.events.append = recording
    try:
        op = (await client.actions_invoke("ax", "blk", {}, wait_ms=2000)).operation
        assert op.state == "completed" and seen["worker"] != threading.get_ident()
        assert writers and set(writers) == {threading.get_ident()}, "the journal was written from a worker thread"
        events, _cursor, _gap = srv.events.read(after=None, limit=50)
        assert [e for e in events if e["type"] == "device.fault"]
    finally:
        await _close(srv, listener, client)


def test_store_refuses_writes_from_another_thread(tmp_path):  # finding 6
    store = Store(tmp_path / "t.db")
    errors = []
    try:
        def other():
            try:
                with store.transaction(barrier=True):
                    pass
            except StoreError as exc:
                errors.append(exc)

        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
        assert len(errors) == 1 and "thread" in str(errors[0])
        with store.transaction():  # the owner is unaffected
            store.meta_set("k", "v")
    finally:
        store.close()


def test_cancel_on_lease_loss_needs_a_cancellable_action():  # minor
    srv = DeviceServer("decl", state_dir=None)
    dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
    with pytest.raises(DescriptionError, match="on_lease_loss='cancel'"):
        @dev.action(effect="reversible", idempotency="relative", max_duration_ms=100, on_lease_loss="cancel")
        async def move(ctx) -> None: ...


def test_checkpointer_is_restarted_when_its_thread_dies(tmp_path, monkeypatch):  # minor
    path = tmp_path / "cp.db"
    sqlite3.connect(path).close()
    real = sqlite3.connect
    monkeypatch.setattr(store_module.sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(
        sqlite3.OperationalError("boom")))
    with pytest.MonkeyPatch.context() as quiet:
        quiet.setattr(threading, "excepthook", lambda args: None)
        cp = store_module._Checkpointer(path)
        cp._thread.join(2)
    assert not cp._thread.is_alive()
    monkeypatch.setattr(store_module.sqlite3, "connect", real)
    cp.committed()
    assert cp._thread.is_alive()
    cp.stop()


# --------------------------------------------------------------------------- fix round 2


def _round2_device(srv):
    from bhms.server.context import DeviceFault

    st = {"ran": 0, "effect": "unknown", "fresh_error": False, "remaining": None}
    dev = srv.device("ax", capabilities=["bhms.axis.linear"], resources=["ax"])
    dev.report_alive()

    @dev.property(unit="mm", evidence="measured")
    def position() -> float:
        if st["fresh_error"]:
            raise MemoryError("sensor driver blew up")
        return 1.0

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def fine(ctx) -> None:
        st["ran"] += 1

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def fault(ctx) -> None:
        raise DeviceFault("jam", effect=st["effect"])

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def big(ctx):
        return {"ns": 2 ** 60}

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=5000, blocking=True)
    def timed(ctx) -> None:
        st["remaining"] = ctx.remaining_ms

    return st


async def test_store_error_while_settling_keeps_the_resource_inhibited_until_unknown_is_durable(tmp_path):  # finding 3
    srv, listener, client, st = await _open(tmp_path, "r7", _round2_device)
    try:
        real = srv.journal.transition
        fail = {"on": True}

        def flaky(rec, state, **kw):
            if fail["on"] and state in ("completed", "unknown"):
                raise StoreError("disk full")
            return real(rec, state, **kw)

        srv.journal.transition = flaky
        op = (await client.actions_invoke("ax", "fine", {}, operation_key="f1", wait_ms=500)).operation
        assert op.state == "dispatching" and st["ran"] == 1
        assert srv.executor.inhibiting(("ax",)) == op.operation_id
        with pytest.raises(BhmsError):  # journal not writable: refused, handler not run again
            await client.actions_invoke("ax", "fine", {}, operation_key="f2")
        fail["on"] = False  # the journal is writable again
        with pytest.raises(BhmsError) as refused:
            await client.actions_invoke("ax", "fine", {}, operation_key="f3")
        assert refused.value.bhms_code == "STALE" and st["ran"] == 1, "the resource must stay inhibited"
        again = (await client.operations_get(op.operation_id)).operation
        assert again.state == "unknown" and again.error.bhms_code == "DEADLINE_EXCEEDED"
        assert again.error.may_have_acted is True
    finally:
        await _close(srv, listener, client)


async def test_background_retry_records_unknown_without_new_traffic(tmp_path):  # finding 3
    srv, listener, client, st = await _open(tmp_path, "r7b", _round2_device)
    try:
        real = srv.journal.transition
        fail = {"on": True}

        def flaky(rec, state, **kw):
            if fail["on"] and state in ("completed", "unknown"):
                raise StoreError("disk full")
            return real(rec, state, **kw)

        srv.journal.transition = flaky
        op = (await client.actions_invoke("ax", "fine", {}, operation_key="f1", wait_ms=500)).operation
        fail["on"] = False
        srv.executor._retry.cancel()
        srv.executor._retry = None
        srv.executor._retry_unsettled()
        assert srv.journal.get(op.operation_id).state == "unknown" and not srv.executor._unsettled
    finally:
        await _close(srv, listener, client)


@pytest.mark.parametrize("effect", ["verified", "bogus"])
def test_device_fault_validates_its_effect(effect):  # finding 4
    from bhms.server.context import DeviceFault
    with pytest.raises(ValueError, match="effect"):
        DeviceFault("jam", effect=effect)
    with pytest.raises(ValueError, match="measured"):
        DeviceFault("jam", effect="verified", observations={"p": {"evidence": "reported", "quality": "valid"}})
    DeviceFault("jam", effect="verified", observations={"p": {"evidence": "measured", "quality": "valid"}})


def test_journal_rejects_an_effect_outside_the_schema_enum(tmp_path):  # finding 4
    store = Store(tmp_path / "e.db")
    try:
        journal = Journal(store)
        rec = journal.create(principal="p", key="k", key_origin="client", kind="action", request_digest="sha256:x",
                             arguments={}, device_id="ax", action="mv",
                             private={"resources": ["ax"], "effectClass": "reversible"}, dispatch=True)
        with pytest.raises(InvalidTransition, match="EffectCertainty"):
            journal.transition(rec, "canceled", effect="bogus")
        assert rec.state == "dispatching"
    finally:
        store.close()


async def test_integer_beyond_2_53_is_refused_with_a_precise_message(tmp_path):  # fix (a)
    srv, listener, client, _ = await _open(tmp_path, "r8", _round2_device)
    try:
        op = (await client.actions_invoke("ax", "big", {}, operation_key="b", wait_ms=1000)).operation
        assert op.state == "failed" and op.error.may_have_acted is True
        assert "result.ns" in op.error.message and "2^53" in op.error.message and "I-JSON" in op.error.message
        assert "output schema" not in op.error.message
    finally:
        await _close(srv, listener, client)


def test_recover_lists_each_program_once(tmp_path):  # fix (b)
    path, prog_id, _ = _program_with_unknown_child(tmp_path, "reconciled-completed")
    store = Store(path)
    try:
        changed = Journal(store).recover()
        assert [r.id for r in changed].count(prog_id) == 1
    finally:
        store.close()


def test_reconciled_observations_are_validated_whenever_present():  # fix (d)
    with pytest.raises(ValueError, match="measured"):
        Reconciled("completed", evidence="x", effect="unverified",
                   observations={"p": {"evidence": "reported", "quality": "valid"}})


async def test_unexpected_freshness_error_rejects_the_queued_operation(tmp_path):  # fix (e)
    srv, listener, client, st = await _open(tmp_path, "r9", _gated_device)
    try:
        lease = (await client.leases_acquire(["ax"], 5000)).lease
        await client.actions_invoke("ax", "a", {}, lease_id=lease.lease_id, operation_key="a")
        rb = await client.actions_invoke("ax", "b", {}, lease_id=lease.lease_id, operation_key="b")
        real = srv.observations.require_fresh

        async def boom(*a, **k):
            raise MemoryError("driver blew up")

        srv.observations.require_fresh = boom
        st["agate"].set()
        await asyncio.sleep(0.3)
        op = (await client.operations_get(rb.operation.operation_id)).operation
        assert op.state == "rejected" and op.error.bhms_code == "INTERNAL" and op.error.may_have_acted is False
        assert not srv.executor._busy and not srv.executor._pending
        srv.observations.require_fresh = real
    finally:
        await _close(srv, listener, client)


async def test_remaining_ms_works_from_a_blocking_handlers_thread(tmp_path):  # fix (f)
    srv, listener, client, st = await _open(tmp_path, "r10", _round2_device)
    try:
        op = (await client.actions_invoke("ax", "timed", {}, wait_ms=2000)).operation
        assert op.state == "completed" and 0 < st["remaining"] <= 5000
    finally:
        await _close(srv, listener, client)
