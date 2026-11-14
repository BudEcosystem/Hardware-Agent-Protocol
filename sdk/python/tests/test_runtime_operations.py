"""Operation store (real SQLite files), state machine transitions, idempotency and restart recovery.

Requirement IDs: BHMS-OPS-001..009, OPS-030..035, OPS-034 (epoch), OPS-080, PRG-017.
"""

from __future__ import annotations

import asyncio
import itertools
import sqlite3

import pytest

from bhms.protocol import types
from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import (TRANSITIONS, InvalidTransition, Journal, derived_key, intent_digest,
                                     key_conflict_error)
from bhms.runtime.store import Store, StoreError, StoreLocked

ALL_STATES = ("accepted", "dispatching", "running", "completed", "failed", "canceled", "rejected", "unknown")
SPEC_TABLE = {
    "accepted": {"dispatching", "rejected", "canceled"},
    "dispatching": {"running", "completed", "failed", "canceled", "unknown"},
    "running": {"completed", "failed", "canceled", "unknown"},
    "unknown": {"running", "completed", "failed", "canceled"},
    "completed": set(), "failed": set(), "canceled": set(), "rejected": set(),
}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "ops.sqlite3")
    yield s
    s.close()


def new_op(journal: Journal, key: str = "k1", principal: str = "alice", **kw):
    params = {"deviceId": "dev-1", "action": "move_to", "arguments": {"target": 5}}
    kw.setdefault("arguments", params["arguments"])
    return journal.create(principal=principal, key=key, key_origin="client", kind="action", device_id="dev-1",
                          action="move_to", request_digest=intent_digest("actions/invoke", params),
                          private={"resources": ["stage"], "effectClass": "reversible"}, **kw)


def error(code="DEVICE_FAULT", acted=True):
    return BhmsError(code, "boom", may_have_acted=acted, hint="look at the device").to_operation_error()


def drive(journal, rec, state):
    kw = {}
    if state == "completed":
        kw["result"] = {"ok": True}
        kw["effect"] = "unverified"
    elif state in ("failed", "rejected"):
        kw["error"] = error(acted=state == "failed")
    elif state == "unknown":
        kw["error"] = BhmsError("DEADLINE_EXCEEDED", "lost", may_have_acted=True,
                                hint="reconcile").to_operation_error()
    if rec.state == "unknown":
        kw["kind"] = "reconciliation"
        kw["detail"] = "device query: position 5 um"
    journal.transition(rec, state, **kw)


def path_to(state):
    return {"accepted": [], "dispatching": ["dispatching"], "running": ["dispatching", "running"],
            "unknown": ["dispatching", "unknown"]}[state]


def test_transition_table_matches_spec():  # BHMS-OPS-001
    assert {k: set(v) for k, v in TRANSITIONS.items()} == SPEC_TABLE


@pytest.mark.parametrize("source, target", list(itertools.product(("accepted", "dispatching", "running", "unknown"),
                                                                  ALL_STATES)))
def test_every_transition_is_allowed_or_refused_per_the_table(store, source, target):  # BHMS-OPS-001, OPS-002
    journal = Journal(store)
    rec = new_op(journal)
    for step in path_to(source):
        drive(journal, rec, step)
    before = len(journal.history(rec))
    if target in SPEC_TABLE[source]:
        drive(journal, rec, target)
        assert rec.state == target
        history = journal.history(rec)
        assert len(history) == before + 1 and history[-1]["state"] == target
        types.Operation.model_validate(rec.wire(history=True))  # schema rules: result/error/effect per state
    else:
        with pytest.raises(InvalidTransition):
            drive(journal, rec, target)
        assert rec.state == source and len(journal.history(rec)) == before


@pytest.mark.parametrize("terminal", ["completed", "failed", "canceled"])
def test_terminal_states_never_change_and_corrections_append(store, terminal):  # BHMS-OPS-002
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    drive(journal, rec, terminal)
    snapshot = dict(rec.op)
    for target in ALL_STATES:
        with pytest.raises(InvalidTransition):
            journal.transition(rec, target, error=error(), result=1)
    journal.annotate(rec, "correction", "scale later read 3 g, contradicting the reported result")
    assert rec.op["state"] == snapshot["state"] and rec.op.get("result") == snapshot.get("result")
    assert rec.op["effect"] == snapshot["effect"]
    assert journal.history(rec)[-1]["kind"] == "correction"


def test_leaving_unknown_requires_a_reconciliation_entry_and_keeps_the_unknown_entry(store):  # BHMS-OPS-005
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    drive(journal, rec, "unknown")
    with pytest.raises(InvalidTransition, match="reconciliation"):
        journal.transition(rec, "completed", result={}, effect="unverified")
    journal.transition(rec, "completed", result={}, effect="unverified", kind="reconciliation",
                       detail="device query: at target")
    kinds = [(h["kind"], h.get("state")) for h in journal.history(rec)]
    assert ("state", "unknown") in kinds and kinds[-1] == ("reconciliation", "completed")


def test_unknown_requires_the_uniform_error(store):  # BHMS-OPS-004
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    with pytest.raises(InvalidTransition, match="DEADLINE_EXCEEDED"):
        journal.transition(rec, "unknown", error=error("INTERNAL"))
    journal.transition(rec, "unknown", error=journal.unknown_error("the reply was lost"))
    err = rec.op["error"]
    assert (err["bhmsCode"], err["mayHaveActed"], err["retry"]) == ("DEADLINE_EXCEEDED", True, "after-reconcile")
    assert rec.op["effect"] == "unknown"


def test_dispatched_failures_must_say_may_have_acted(store):  # BHMS-OPS-009
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    with pytest.raises(InvalidTransition, match="mayHaveActed"):
        journal.transition(rec, "failed", error=error(acted=False))


def test_rejected_and_canceled_from_accepted_have_effect_none(store):  # BHMS-OPS-006
    journal = Journal(store)
    a = new_op(journal, "a")
    journal.transition(a, "rejected", error=error("DEADLINE_EXCEEDED", acted=False))
    b = new_op(journal, "b")
    journal.transition(b, "canceled")
    assert a.op["effect"] == "none" and b.op["effect"] == "none"
    with pytest.raises(InvalidTransition):
        journal.transition(new_op(journal, "c"), "rejected", error=error("INTERNAL", acted=True))


def test_result_only_when_completed(store):  # BHMS-OPS-008
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    assert "result" not in rec.op
    drive(journal, rec, "completed")
    assert rec.op["result"] == {"ok": True}


def test_cancel_state_and_effect_changes_are_in_history(store):  # BHMS-OPS-001
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    journal.set_cancel(rec, "requested", reason="operator")
    journal.set_effect(rec, "unknown", detail="partial motion")
    kinds = [h["kind"] for h in journal.history(rec)]
    assert kinds[-2:] == ["cancel", "effect"]
    assert rec.op["cancel"]["state"] == "requested" and rec.op["cancel"]["reason"] == "operator"


def test_records_survive_reopen_with_same_epoch(tmp_path):  # BHMS-OPS-034, OPS-063
    path = tmp_path / "ops.sqlite3"
    s = Store(path)
    epoch = s.epoch
    journal = Journal(s)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    drive(journal, rec, "completed")
    s.close()
    s2 = Store(path)
    assert s2.epoch == epoch and s2.durable
    again = Journal(s2).get(rec.id)
    assert again.wire(history=True) == rec.wire(history=True)
    s2.close()
    path.unlink()
    s3 = Store(path)
    assert s3.epoch != epoch  # state lost -> new epoch
    s3.close()


def test_memory_store_is_not_durable_and_changes_epoch():  # BHMS-OPS-034
    a, b = Store(None), Store(None)
    assert not a.durable and a.epoch != b.epoch
    a.close()
    b.close()


def test_second_process_cannot_open_the_same_store(tmp_path):
    s = Store(tmp_path / "x.sqlite3")
    with pytest.raises(StoreLocked):
        Store(tmp_path / "x.sqlite3")
    s.close()
    Store(tmp_path / "x.sqlite3").close()


def test_store_uses_wal_and_durability_modes(tmp_path):
    for mode in ("full", "dispatch", "process"):
        s = Store(tmp_path / f"{mode}.sqlite3", durability=mode)
        assert s.durability == mode
        assert s.execute_scalar("PRAGMA journal_mode") == "wal"
        s.close()
    with pytest.raises(ValueError):
        Store(tmp_path / "bad.sqlite3", durability="maybe")


def test_query_only_store_refuses_writes(store):  # BHMS-OPS-003 groundwork
    journal = Journal(store)
    store.set_writable(False)
    with pytest.raises(StoreError):
        new_op(journal)
    store.set_writable(True)
    new_op(journal)


# --------------------------------------------------------------------------- idempotency


def test_intent_digest_covers_exactly_the_intent():  # §6.4
    base = {"deviceId": "d", "action": "a", "arguments": {"x": 1}}
    digest = intent_digest("actions/invoke", base)
    ignored = {**base, "leaseId": "l", "waitMs": 5, "operationKey": "k", "_meta": {"bhms/protocolVersion": "x"}}
    assert intent_digest("actions/invoke", ignored) == digest
    for change in ({"arguments": {"x": 2}}, {"deadlineMs": 10}, {"require": {"effect": "verified"}},
                   {"descriptionDigest": "sha256:" + "0" * 64}, {"action": "b"}):
        assert intent_digest("actions/invoke", {**base, **change}) != digest
    # a quantity object is a different intent from the bare number (arguments as sent)
    assert intent_digest("actions/invoke", {**base, "arguments": {"x": {"value": 1, "unit": "mm"}}}) != digest
    prog = {"digest": "sha256:" + "1" * 64, "arguments": {}, "leaseId": "l"}
    assert intent_digest("programs/run", prog) == intent_digest("programs/run", {**prog, "waitMs": 3})


def test_same_key_lookup_is_per_principal(store):  # BHMS-OPS-030
    journal = Journal(store)
    rec = new_op(journal, "k1", "alice")
    assert journal.lookup_key("alice", "k1").id == rec.id
    assert journal.lookup_key("bob", "k1") is None
    other = new_op(journal, "k1", "bob")
    assert other.id != rec.id


def test_key_conflict_names_the_operation_and_its_may_have_acted(store):  # BHMS-OPS-031, OPS-040
    journal = Journal(store)
    rec = new_op(journal)
    err = key_conflict_error(rec, "k1")
    assert (err.bhms_code, err.operation_id, err.may_have_acted, err.field) == ("KEY_CONFLICT", rec.id, False,
                                                                         "operationKey")
    assert "operations/get" in err.hint and "different form" in err.hint
    drive(journal, rec, "dispatching")
    assert key_conflict_error(rec, "k1").may_have_acted is True
    drive(journal, rec, "failed")
    assert key_conflict_error(rec, "k1").may_have_acted is True


def test_unique_key_is_enforced_by_the_database(store):  # BHMS-OPS-032 backstop
    journal = Journal(store)
    new_op(journal, "dup")
    with pytest.raises(StoreError):
        new_op(journal, "dup")


async def test_single_flight_admission_lock(store):  # BHMS-OPS-032
    journal = Journal(store)
    created = []

    async def admit():
        async with journal.admission("alice", "same"):
            existing = journal.lookup_key("alice", "same")
            if existing is not None:
                return existing.id
            await asyncio.sleep(0.001)  # admission work that yields
            rec = new_op(journal, "same")
            created.append(rec.id)
            return rec.id

    ids = await asyncio.gather(*(admit() for _ in range(50)))
    assert len(set(ids)) == 1 and len(created) == 1
    assert not journal._admissions  # locks are released


def test_derived_key_formula():  # BHMS-PRG-010
    import hashlib
    expected = "d-" + hashlib.sha256(b"op-1/1/3/0").hexdigest()[:40]
    assert derived_key("op-1", "1/3/0") == expected


# --------------------------------------------------------------------------- waiting


async def test_wait_returns_on_settle_without_polling(store):  # BHMS-OPS-060
    journal = Journal(store)
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, drive, journal, rec, "completed")
    start = loop.time()
    got = await journal.wait(rec, 5.0)
    assert got.state == "completed" and loop.time() - start < 1.0
    rec2 = new_op(journal, "k2")
    got2 = await journal.wait(rec2, 0.05)  # timeout: returned unsettled, no error
    assert got2.state == "accepted"


def test_listeners_see_every_state_cancel_and_effect_change_in_order(store):  # BHMS-OPS-090
    journal = Journal(store)
    seen = []
    journal.listeners.append(lambda rec, op: seen.append((op["state"], op["cancel"]["state"], op["effect"])))
    rec = new_op(journal)
    drive(journal, rec, "dispatching")
    journal.set_cancel(rec, "requested")
    drive(journal, rec, "completed")
    # entering dispatching makes the effect of an effectful action unknown until evidence arrives
    assert seen == [("accepted", "none", "none"), ("dispatching", "none", "unknown"),
                    ("dispatching", "requested", "unknown"), ("completed", "requested", "unverified")]


# --------------------------------------------------------------------------- recovery


def test_recovery_moves_in_flight_actions_to_unknown_and_rejects_accepted(tmp_path):  # BHMS-OPS-080
    path = tmp_path / "ops.sqlite3"
    s = Store(path)
    journal = Journal(s)
    accepted = new_op(journal, "a")
    dispatching = new_op(journal, "b")
    drive(journal, dispatching, "dispatching")
    running = new_op(journal, "c")
    drive(journal, running, "dispatching")
    drive(journal, running, "running")
    done = new_op(journal, "d")
    drive(journal, done, "dispatching")
    drive(journal, done, "completed")
    s.close()
    s2 = Store(path)
    j2 = Journal(s2)
    changed = j2.recover()
    assert {r.id for r in changed} == {accepted.id, dispatching.id, running.id}
    assert j2.get(accepted.id).state == "rejected"
    assert j2.get(accepted.id).op["error"]["mayHaveActed"] is False
    for rec in (dispatching, running):
        again = j2.get(rec.id)
        assert again.state == "unknown"
        assert again.op["error"]["bhmsCode"] == "DEADLINE_EXCEEDED" and again.op["error"]["mayHaveActed"]
        assert "restart" in again.op["error"]["message"]
    assert j2.get(done.id).state == "completed"
    s2.close()


def test_recovery_settles_programs_from_step_history(tmp_path):  # BHMS-PRG-017
    path = tmp_path / "ops.sqlite3"
    s = Store(path)
    journal = Journal(s)

    def program(key):
        return journal.create(principal="alice", key=key, key_origin="client", kind="program",
                              program_digest="sha256:" + "2" * 64, arguments={},
                              request_digest=intent_digest("programs/run", {"digest": "sha256:" + "2" * 64,
                                                                             "arguments": {key: 1}}),
                              private={"resources": ["stage"], "effectClass": "reversible"})

    def child(parent, key, effect_class="reversible"):
        return journal.create(principal="alice", key=key, key_origin="derived", kind="action", device_id="dev-1",
                              action="move_to", parent_id=parent.id, arguments={},
                              request_digest=intent_digest("actions/invoke", {"deviceId": "dev-1",
                                                                               "action": "move_to",
                                                                               "arguments": {"k": key}}),
                              private={"resources": ["stage"], "effectClass": effect_class})

    never_started = program("p0")
    between = program("p1")
    journal.transition(between, "dispatching")
    journal.transition(between, "running")
    c1 = child(between, "c1")
    journal.annotate(between, "step", "step 0 started", step_index=0, child_operation_id=c1.id)
    drive(journal, c1, "dispatching")
    drive(journal, c1, "completed")
    in_step = program("p2")
    journal.transition(in_step, "dispatching")
    journal.transition(in_step, "running")
    c2 = child(in_step, "c2")
    journal.annotate(in_step, "step", "step 0 started", step_index=0, child_operation_id=c2.id)
    drive(journal, c2, "dispatching")
    s.close()

    s2 = Store(path)
    j2 = Journal(s2)
    j2.recover()
    assert j2.get(never_started.id).state == "rejected"
    assert j2.get(never_started.id).op["error"]["bhmsCode"] == "INTERNAL"
    p1 = j2.get(between.id)
    assert p1.state == "failed" and p1.op["error"]["mayHaveActed"] is True
    assert p1.op["error"]["message"] == "server restarted during the program"
    assert "stepIndex 0" in p1.op["error"]["hint"]
    assert j2.get(c2.id).state == "unknown"
    p2 = j2.get(in_step.id)
    assert p2.state == "unknown" and p2.op["error"]["bhmsCode"] == "DEADLINE_EXCEEDED"
    # once the unknown child is reconciled the program settles too (failed INTERNAL)
    j2.transition(j2.get(c2.id), "failed", error=error(), kind="reconciliation", detail="device query: idle")
    assert j2.get(in_step.id).state == "failed"
    assert j2.history(j2.get(in_step.id))[-1]["kind"] == "reconciliation"
    s2.close()


def test_list_orders_by_created_desc_then_id_and_pages(store):  # BHMS-LIF-062
    journal = Journal(store)
    recs = [new_op(journal, f"k{i}") for i in range(5)]
    page, cursor = journal.list(principal="alice", limit=2)
    assert [r["operationId"] for r in page] == [recs[4].id, recs[3].id] and cursor
    rest, cursor2 = journal.list(principal="alice", limit=10, after=cursor)
    assert [r["operationId"] for r in rest] == [r.id for r in reversed(recs[:3])] and cursor2 is None
    assert journal.list(principal="bob", limit=10) == ([], None)  # BHMS-OPS-062 visibility
    assert len(journal.list(principal=None, limit=10)[0]) == 5  # admin sees all
    with pytest.raises(BhmsError) as info:
        journal.list(principal="alice", limit=2, after="garbage")
    assert info.value.field == "cursor"


def test_store_file_is_a_real_wal_database(tmp_path):
    path = tmp_path / "ops.sqlite3"
    s = Store(path)
    new_op(Journal(s))
    con = sqlite3.connect(path)
    assert con.execute("select count(*) from operations").fetchone()[0] == 1
    con.close()
    s.close()
