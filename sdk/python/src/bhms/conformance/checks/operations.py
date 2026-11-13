"""Chapter 6: operations, idempotency, states, cancellation, waiting, deadlines, unknown outcomes and restart.

These checks drive the conformance device (documented in ``bhms.testing.conformance_device``): ``axis-1`` actions
``move_to`` (measured), ``pulse`` (relative, 1 ms), ``slow_move`` (cancellable, duration chosen by the caller), ``fault``
(always DEVICE_FAULT); the device-side ``counter`` property proves "no effect" and "exactly one effect".
"""

from __future__ import annotations

import asyncio
import time

from bhms.conformance.context import SETTLED, TERMINAL, Context
from bhms.conformance.core import CheckFailed, check


@check("operations.completion-evidence", ["BHMS-OPS-006", "BHMS-OPS-008", "BHMS-OPS-001", "BHMS-OPS-002", "BHMS-OPS-053", "BHMS-LIF-046"])
async def completion_evidence(c: Context) -> None:
    """Measured completion is verified, reported completion unverified; result matches output; terminal never changes."""
    axis = c.axis()
    moved = await c.run(axis, "move_to", {"position": 12.5})
    c.expect(moved["state"] == "completed", f"move_to ended {moved['state']}: {moved.get('error')}")
    c.expect((moved["effect"], (moved.get("evidence") or {}).get("kind")) == ("verified", "measured"),
             f"a measured, agreeing move_to must be verified with measured evidence, was {moved['effect']}/{moved.get('evidence')}")
    c.expect(moved["result"] == {"position": 12.5}, f"move_to result {moved['result']}")
    pulsed = await c.run(axis, "pulse", {"count": 2})
    c.expect(pulsed["state"] == "completed" and pulsed["effect"] == "unverified",
             f"a reported completion is unverified, was {pulsed['state']}/{pulsed['effect']}")
    got = await c.get_op(moved["operationId"])
    c.expect(got["state"] == "completed" and got["history"], "operations/get returns the durable record with history")
    cancelled = (await c.ok("operations/cancel", {"operationId": moved["operationId"]}))["operation"]
    c.expect(cancelled["state"] == "completed" and cancelled["effect"] == got["effect"] and cancelled.get("result") == got.get("result"),
             "cancelling a settled operation must return it unchanged (BHMS-OPS-053)")
    again = await c.get_op(moved["operationId"])
    c.expect([h["seq"] for h in again["history"]][: len(got["history"])] == [h["seq"] for h in got["history"]],
             "history must be append-only")
    c.expect(again["state"] == got["state"] and again.get("result") == got.get("result") and again["effect"] == got["effect"],
             "a terminal operation changed")


@check("operations.idempotency", ["BHMS-OPS-030", "BHMS-OPS-031", "BHMS-OPS-035", "BHMS-OPS-037", "BHMS-OPS-040"])
async def idempotency(c: Context) -> None:
    """Same key and intent: one operation, one device effect, replayed true; different intent: KEY_CONFLICT with the
    existing operationId; no key: server key, new operation each time; d- keys are reserved."""
    axis = c.axis()
    key = c.unique("idem")
    base = await c.counter(axis)
    first = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 3}, "operationKey": key, "waitMs": 2000})
    c.expect(first["replayed"] is False and first["operation"]["keyOrigin"] == "client", "the first invoke is not a replay", ("BHMS-OPS-030",))
    for _ in range(2):
        again = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 3}, "operationKey": key, "waitMs": 2000})
        c.expect(again["replayed"] is True, "a repeated key must return replayed true", ("BHMS-OPS-030",))
        c.expect(again["operation"]["operationId"] == first["operation"]["operationId"], "a repeated key must return the same operation",
                 ("BHMS-OPS-030",))
    c.expect(await c.counter(axis) == base + 1, f"three identical keyed invokes must have exactly one device effect (counter {base} -> {await c.counter(axis)})",
             ("BHMS-OPS-030",))
    ops = await c.operations_count(deviceId=axis)
    conflict = await c.invoke(axis, "pulse", {"count": 4}, operationKey=key)
    try:
        data = c.refused(conflict, "KEY_CONFLICT", may_have_acted=None)
    except CheckFailed as exc:
        raise CheckFailed(str(exc), ("BHMS-OPS-031",)) from None
    c.expect(data.get("operationId") == first["operation"]["operationId"], f"KEY_CONFLICT must carry the existing operationId, carries {data.get('operationId')!r}")
    c.expect(data.get("mayHaveActed") is True, "KEY_CONFLICT on a dispatched operation carries mayHaveActed true", ("BHMS-OPS-031", "BHMS-OPS-040"))
    other = await c.invoke(axis, "slow_move", {"duration_ms": 5}, operationKey=key)
    c.refused(other, "KEY_CONFLICT", may_have_acted=None, what="same key, other action")
    c.expect(await c.operations_count(deviceId=axis) == ops, "KEY_CONFLICT created an operation", ("BHMS-OPS-031", "BHMS-OPS-040"))
    c.expect(await c.counter(axis) == base + 1, "KEY_CONFLICT reached the device", ("BHMS-OPS-031",))
    one = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "waitMs": 2000})
    two = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "waitMs": 2000})
    c.expect(one["operation"]["keyOrigin"] == two["operation"]["keyOrigin"] == "server", "without a key the server must mint one (keyOrigin server)",
             ("BHMS-OPS-035",))
    c.expect(one["operation"]["operationId"] != two["operation"]["operationId"] and not two["replayed"],
             "a re-sent request without a key is a new operation", ("BHMS-OPS-035",))
    c.expect(one["operation"]["operationKey"] != two["operation"]["operationKey"], "server-minted keys must be unique", ("BHMS-OPS-035",))
    reserved = await c.invoke(axis, "pulse", {"count": 1}, operationKey="d-reserved")
    try:
        c.refused(reserved, "INVALID_ARGUMENT", field="operationKey", what="a d- operation key")
    except CheckFailed as exc:
        raise CheckFailed(str(exc), ("BHMS-OPS-037",)) from None


@check("operations.concurrent-same-key", ["BHMS-OPS-032"])
async def concurrent_same_key(c: Context) -> None:
    """Twenty concurrent identical keyed invokes produce one operation and one device effect."""
    axis = c.axis()
    base = await c.counter(axis)
    key = c.unique("race")
    params = {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "operationKey": key, "waitMs": 2000}
    responses = await asyncio.gather(*(c.call("actions/invoke", params) for _ in range(20)))
    ids = {c.result(r)["operation"]["operationId"] for r in responses}
    c.expect(len(ids) == 1, f"20 concurrent identical invokes produced {len(ids)} operations")
    c.expect(sum(1 for r in responses if r.result["replayed"] is False) == 1, "exactly one response may be the original (replayed false)")
    c.expect(await c.counter(axis) == base + 1, "20 concurrent identical invokes must have exactly one device effect")


@check("operations.cancel-queued", ["BHMS-OPS-050", "BHMS-OPS-006", "BHMS-OPS-001"], needs=("direct",))
async def cancel_queued(c: Context) -> None:
    """Cancelling an accepted operation: canceled, confirmed, effect none, never dispatched."""
    axis = c.axis()
    base = await c.counter(axis)
    running = await c.invoke_op(axis, "slow_move", {"duration_ms": 3000})
    queued = await c.invoke_op(axis, "move_to", {"position": 7})
    c.expect(queued["state"] == "accepted", f"an operation behind a busy resource must wait in accepted, is {queued['state']}")
    cancelled = (await c.ok("operations/cancel", {"operationId": queued["operationId"], "reason": "conformance"}))["operation"]
    c.expect(cancelled["state"] == "canceled" and cancelled["cancel"]["state"] == "confirmed" and cancelled["effect"] == "none",
             f"cancelling an accepted operation: {cancelled['state']}/{cancelled['cancel']}/{cancelled['effect']}")
    await c.ok("operations/cancel", {"operationId": running["operationId"]})
    await c.settle(running["operationId"], 5)
    c.expect(await c.counter(axis) == base + 1, "the cancelled queued operation must not have reached the device")


@check("operations.cancel-states", ["BHMS-OPS-051", "BHMS-OPS-053", "BHMS-OPS-062", "BHMS-OPS-001"])
async def cancel_states(c: Context) -> None:
    """Running: cancel requested then confirmed. Unsupported: refused, state unchanged. Settled: unchanged. Unknown id:
    INVALID_ARGUMENT operationId."""
    axis = c.axis()
    running = await c.invoke_op(axis, "slow_move", {"duration_ms": 3000})
    asked = (await c.ok("operations/cancel", {"operationId": running["operationId"]}))["operation"]
    c.expect(asked["cancel"]["state"] in ("requested", "acknowledged", "confirmed"), f"cancel of a running operation: {asked['cancel']}")
    final = await c.settle(running["operationId"], 5)
    c.expect(final["state"] == "canceled" and final["cancel"]["state"] == "confirmed", f"a cancellable operation must end canceled/confirmed: {final['state']}/{final['cancel']}")
    again = (await c.ok("operations/cancel", {"operationId": running["operationId"]}))["operation"]
    c.expect(again["state"] == "canceled", "cancelling a canceled operation returns it unchanged", ("BHMS-OPS-053",))
    await c.inject("hang_next")
    stuck = await c.invoke_op(axis, "pulse", {"count": 1})
    refused = (await c.ok("operations/cancel", {"operationId": stuck["operationId"]}))["operation"]
    c.expect(refused["cancel"]["state"] == "refused" and refused["state"] not in TERMINAL,
             f"cancel of an action declaring cancel unsupported must be refused and leave the state: {refused['state']}/{refused['cancel']}", ("BHMS-OPS-051",))
    c.expect((await c.get_op(stuck["operationId"]))["state"] in ("dispatching", "running"), "the refused cancel changed the state", ("BHMS-OPS-051",))
    for method in ("operations/get", "operations/cancel"):
        response = await c.call(method, {"operationId": "op-" + "f" * 24})
        c.refused(response, "INVALID_ARGUMENT", field="operationId", what=f"{method} of an unknown operation")
    response = await c.call("operations/wait", {"operationId": "op-" + "f" * 24, "timeoutMs": 10})
    c.refused(response, "INVALID_ARGUMENT", field="operationId", what="operations/wait of an unknown operation")


@check("operations.wait-semantics", ["BHMS-OPS-060", "BHMS-OPS-061", "BHMS-OPS-063"])
async def wait_semantics(c: Context) -> None:
    """wait returns when settled or at timeoutMs without error; waitMs on invoke does not fail the operation; limits."""
    axis = c.axis()
    slow = await c.invoke_op(axis, "slow_move", {"duration_ms": 600})
    started = time.monotonic()
    waited = (await c.ok("operations/wait", {"operationId": slow["operationId"], "timeoutMs": 100}))["operation"]
    elapsed = time.monotonic() - started
    c.expect(waited["state"] not in SETTLED and 0.08 <= elapsed < 0.5, f"wait of 100 ms on a 600 ms action returned {waited['state']} after {elapsed:.2f}s")
    started = time.monotonic()
    done = (await c.ok("operations/wait", {"operationId": slow["operationId"], "timeoutMs": 10000}))["operation"]
    c.expect(done["state"] == "completed" and time.monotonic() - started < 2.0, "wait must return as soon as the operation settles")
    over = int(c.limits.get("maxWaitMs", 60000)) + 1
    refused = await c.call("operations/wait", {"operationId": slow["operationId"], "timeoutMs": over})
    c.refused(refused, "OUT_OF_RANGE", field="timeoutMs", what="wait above limits.maxWaitMs")
    refused = await c.invoke(axis, "pulse", {"count": 1}, waitMs=over)
    c.refused(refused, "OUT_OF_RANGE", field="waitMs", what="invoke waitMs above limits.maxWaitMs")
    started = time.monotonic()
    brief = (await c.ok("actions/invoke", {"deviceId": axis, "action": "slow_move", "arguments": {"duration_ms": 700}, "waitMs": 100}))["operation"]
    c.expect(brief["state"] not in TERMINAL, f"waitMs shorter than the action must return the unsettled operation, got {brief['state']}")
    final = await c.settle(brief["operationId"])
    c.expect(final["state"] == "completed", f"an admitted operation must not fail because the response window ended: {final['state']}")
    c.expect((await c.get_op(slow["operationId"]))["state"] == "completed", "a settled operation stays retrievable")


@check("operations.require-verified", ["BHMS-OPS-007"])
async def require_verified(c: Context) -> None:
    """require.effect verified: UNSUPPORTED on reported evidence; failed UNVERIFIED when the measurement fails."""
    axis = c.axis()
    refused = await c.invoke(axis, "pulse", {"count": 1}, require={"effect": "verified"})
    c.refused(refused, "UNSUPPORTED", what="require verified on a reported action")
    ok = await c.run(axis, "move_to", {"position": 20}, require={"effect": "verified"})
    c.expect(ok["state"] == "completed" and ok["effect"] == "verified", f"verified move_to: {ok['state']}/{ok['effect']}")
    await c.inject("sensor_invalid")
    op = await c.run(axis, "move_to", {"position": 21}, require={"effect": "verified"})
    c.expect(op["state"] == "failed" and (op.get("error") or {}).get("bhmsCode") == "UNVERIFIED" and op["error"]["mayHaveActed"] is True,
             f"an unverifiable effect must end failed/UNVERIFIED with mayHaveActed true, ended {op['state']} {op.get('error')}")
    await c.inject("none")
    await c.inject("encoder_disagrees")
    op = await c.run(axis, "move_to", {"position": 22})
    c.expect(op["state"] != "completed" or op["effect"] != "verified", "an encoder that disagrees must never give a verified effect")


@check("operations.device-fault", ["BHMS-ERR-012", "BHMS-OPS-009", "BHMS-ERR-004"])
async def device_fault(c: Context) -> None:
    """DEVICE_FAULT appears only inside the failed operation with mayHaveActed true."""
    axis = c.axis()
    base = await c.counter(axis)
    op = await c.run(axis, "fault", {})
    err = op.get("error") or {}
    c.expect(op["state"] == "failed" and err.get("bhmsCode") == "DEVICE_FAULT" and err.get("mayHaveActed") is True,
             f"fault action: {op['state']} {err}")
    c.expect(err.get("hint") and err.get("retry") == "after-reconcile", "DEVICE_FAULT carries a hint and retry after-reconcile")
    c.expect(await c.counter(axis) == base + 1, "the fault action acted once")


@check("operations.deadline-before-dispatch", ["BHMS-OPS-070"], needs=("direct",))
async def deadline_before_dispatch(c: Context) -> None:
    """A deadline that passes before dispatch rejects the operation: DEADLINE_EXCEEDED, mayHaveActed false, effect none."""
    axis = c.axis()
    base = await c.counter(axis)
    busy = await c.invoke_op(axis, "slow_move", {"duration_ms": 900})
    waiting = await c.invoke_op(axis, "pulse", {"count": 1}, deadlineMs=150)
    c.expect(waiting["state"] == "accepted", f"the second operation must queue behind the busy resource, is {waiting['state']}")
    op = await c.settle(waiting["operationId"], 5)
    err = op.get("error") or {}
    c.expect(op["state"] == "rejected" and err.get("bhmsCode") == "DEADLINE_EXCEEDED" and err.get("mayHaveActed") is False and op["effect"] == "none",
             f"a deadline passing before dispatch: {op['state']} {err} effect {op['effect']}")
    await c.settle(busy["operationId"], 5)
    c.expect(await c.counter(axis) == base + 1, "the rejected operation must not have reached the device")


@check("operations.deadline-while-running", ["BHMS-OPS-071"])
async def deadline_while_running(c: Context) -> None:
    """A deadline that passes during execution requests cancellation: failed DEADLINE_EXCEEDED, mayHaveActed true."""
    long = await c.run(c.axis(), "slow_move", {"duration_ms": 5000}, deadlineMs=200)
    err = long.get("error") or {}
    c.expect(long["state"] in ("failed", "unknown") and err.get("bhmsCode") == "DEADLINE_EXCEEDED" and err.get("mayHaveActed") is True,
             f"a deadline passing while running: {long['state']} {err}")
    c.expect(long["cancel"]["state"] in ("requested", "acknowledged", "confirmed"), "the server must request cancellation when the deadline passes")


@check("operations.max-duration", ["BHMS-DEV-030"], timeout=40)
async def max_duration(c: Context) -> None:
    """A command that hangs past maxDurationMs never completes: failed DEADLINE_EXCEEDED (or unknown)."""
    axis = c.axis()
    limit = (await c.describe(axis))["actions"]["move_to"]["maxDurationMs"]
    c.expect(limit == 5000, f"the conformance device documents maxDurationMs 5000 for move_to, describes {limit}")
    await c.inject("hang_next")
    op = await c.invoke_op(axis, "move_to", {"position": 30})
    final = await c.settle(op["operationId"], 12, states=frozenset({"completed", "failed", "canceled", "rejected", "unknown"}))
    err = final.get("error") or {}
    c.expect(final["state"] != "completed", "a hung command was reported completed")
    c.expect(err.get("bhmsCode") == "DEADLINE_EXCEEDED" or final["state"] == "canceled", f"ended {final['state']} {err}")


@check("operations.lost-reply-becomes-unknown", ["BHMS-OPS-004", "BHMS-OPS-042", "BHMS-OPS-002"], needs=("faults",))
async def unknown_outcome(c: Context) -> None:
    """After dispatch an adapter failure leaves the operation unknown (DEADLINE_EXCEEDED, mayHaveActed true,
    after-reconcile); new operations on its resources are STALE naming it until a confirmed stop."""
    axis = c.axis()
    base = await c.counter(axis)
    await c.inject("crash_next")
    op = await c.run(axis, "pulse", {"count": 1})
    err = op.get("error") or {}
    c.expect(op["state"] == "unknown" and (err.get("bhmsCode"), err.get("mayHaveActed"), err.get("retry")) == ("DEADLINE_EXCEEDED", True, "after-reconcile"),
             f"a crash after dispatch must leave the operation unknown: {op['state']} {err}")
    c.expect(await c.counter(axis) == base + 1, "the device acted once")
    blocked = await c.invoke(axis, "pulse", {"count": 1})
    c.refused(blocked, "STALE", may_have_acted=False, what="an invoke while an operation is unknown")
    c.expect(op["operationId"] in str(blocked.error), f"STALE must name the unknown operation {op['operationId']}: {blocked.error}")
    stopped = (await c.ok("stop", {"reason": "conformance: lift the inhibition", "deviceIds": [axis]}))["stops"][0]
    c.expect(stopped["outcome"] == "confirmed", f"stop outcome {stopped['outcome']}")
    after = await c.run(axis, "pulse", {"count": 1})
    c.expect(after["state"] == "completed", f"a confirmed stop must lift the inhibition, but the next invoke ended {after['state']}")
    still = await c.get_op(op["operationId"])
    c.expect(still["state"] in ("unknown", "failed", "canceled", "completed"), "the unknown operation vanished")


@check("operations.journal-unwritable", ["BHMS-OPS-003", "BHMS-AUTH-025", "BHMS-SEC-041"], needs=("faults",))
async def journal_unwritable(c: Context) -> None:
    """Without a writable journal nothing is dispatched, but stop still executes, marked degraded-audit."""
    axis = c.axis()
    base = await c.counter(axis)
    await c.inject("journal_readonly")
    try:
        refused = await c.invoke(axis, "pulse", {"count": 1})
        if refused.ok:
            op = refused.result["operation"]
            c.expect(op["state"] in ("accepted", "rejected"), f"with an unwritable journal the operation may only be accepted or rejected, is {op['state']}")
        else:
            c.expect(refused.error is not None, "no answer")
        c.expect(await c.counter(axis) == base, "a command was dispatched although the journal was not writable (BHMS-OPS-003)")
        stop = (await c.ok("stop", {"reason": "conformance: degraded audit", "deviceIds": [axis]}))["stops"][0]
        c.expect(stop["outcome"] in ("confirmed", "initiated"), f"stop with an unwritable journal: {stop['outcome']}")
        c.expect(stop.get("detail") == "degraded-audit", f"stop with an unwritable journal must say detail degraded-audit, says {stop.get('detail')!r}")
        again = await c.invoke(axis, "pulse", {"count": 1})
        if again.ok:
            c.expect(again.result["operation"]["state"] in ("accepted", "rejected"), "an ordinary operation ran while the journal was unwritable")
    finally:
        await c.inject("journal_writable")
    c.expect((await c.run(axis, "pulse", {"count": 1}))["state"] == "completed", "ordinary operations must resume when the journal is writable again")


@check("operations.restart-recovery", ["BHMS-OPS-034", "BHMS-OPS-063", "BHMS-OPS-080", "BHMS-OPS-081", "BHMS-OPS-005", "BHMS-LSE-003",
                                       "BHMS-OBS-004", "BHMS-DEV-001", "BHMS-EVT-011", "BHMS-LIF-045"],
       needs=("restart", "durable"), timeout=90)
async def restart_recovery(c: Context) -> None:
    """Kill the server with work in flight and restart it on the same state: epoch unchanged, records and keys kept,
    in-flight work unknown and never re-sent, fences keep increasing, observation epoch changes; a wiped store gets a new
    epoch and a gap."""
    axis = c.axis()
    keyed_key = c.unique("durable")
    done = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "operationKey": keyed_key, "waitMs": 2000})
    running = await c.invoke_op(axis, "slow_move", {"duration_ms": 20000})
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 60000}))["lease"]
    before = await c.read(axis, "position", fresh=True)
    obs_before = c.result(before)["observation"]
    digest_before = (await c.describe(axis))["digest"]
    cursor = (await c.ok("events/read", {"limit": 500}))["cursor"]
    epoch_before = c.discover_result["epoch"]
    await c.reconnect_base(await c.target.restart(kill=True))
    await c.locate()
    c.expect(c.discover_result["epoch"] == epoch_before, f"a durable server must keep its epoch across a restart: {epoch_before} -> {c.discover_result['epoch']}")
    c.expect(c.axis() == axis, "deviceId must survive a restart (BHMS-DEV-001)")
    c.expect((await c.describe(axis))["digest"] == digest_before, "the description changed across a restart")
    again = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "operationKey": keyed_key})
    c.expect(again["replayed"] is True and again["operation"]["operationId"] == done["operation"]["operationId"],
             "a key must survive a restart (replayed true, same operation)")
    c.expect((await c.get_op(done["operation"]["operationId"]))["state"] == "completed", "a settled operation must survive a restart")
    interrupted = await c.get_op(running["operationId"])
    kinds = [(h.get("kind"), h.get("state")) for h in interrupted.get("history", [])]
    c.expect(("state", "unknown") in kinds,
             f"work in flight at a kill must pass through unknown after restart (BHMS-OPS-080); history is {kinds}")
    if interrupted["state"] == "unknown":
        err = interrupted.get("error") or {}
        c.expect((err.get("bhmsCode"), err.get("mayHaveActed")) == ("DEADLINE_EXCEEDED", True), f"unknown after restart carries {err}")
    else:
        c.expect(any(k == "reconciliation" for k, _ in kinds),
                 f"an operation may leave unknown only through a reconciliation entry (BHMS-OPS-005); history is {kinds}")
    c.expect(await c.counter(axis) == 0, "the restarted server re-sent a command to the device (BHMS-OPS-081)")
    new_lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 60000}))["lease"]
    c.expect(new_lease["fence"] > lease["fence"], f"fences must increase across restarts: {lease['fence']} -> {new_lease['fence']}")
    obs_after = c.result(await c.read(axis, "position", fresh=True))["observation"]
    c.expect(obs_after["epoch"] != obs_before["epoch"] or obs_after["sequence"] > obs_before["sequence"],
             "sequence restarted without a new epoch (BHMS-OBS-004)")
    events = await c.ok("events/read", {"after": cursor})
    c.expect(events["gap"] is False, "events must continue after a restart of a durable server without a gap")
    await c.ok("stop", {"reason": "conformance: lift the inhibition", "deviceIds": [axis]})
    await c.ok("leases/release", {"leaseId": new_lease["leaseId"]})
    # a wiped store is a new epoch and the old cursor is a gap
    await c.target.stop_base(kill=False)
    await c.target.wipe_state()
    await c.reconnect_base(await c.target.open_base())
    await c.locate()
    c.expect(c.discover_result["epoch"] != epoch_before, "a wiped store must start a new epoch")
    response = await c.call("events/read", {"after": cursor})
    if response.ok:
        c.expect(response.result["gap"] is True, "reading from a cursor of an earlier epoch must report gap true")
    else:
        c.expect(response.code == "INVALID_ARGUMENT", f"a cursor of an earlier epoch is a gap or INVALID_ARGUMENT, got {response.describe()}")
    c.expect((await c.ok("leases/acquire", {"resources": [f"{c.axis()}/clamp"], "ttlMs": 60000}))["lease"]["fence"] >= 1, "lease after wipe")
