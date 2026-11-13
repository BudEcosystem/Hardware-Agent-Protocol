"""DeviceServer: actions/invoke, operations/get|wait|list|cancel over a real Unix socket with the typed Client.

Requirement IDs: BHMS-OPS-0xx, DEV-030, LIF-050.
"""

from __future__ import annotations

import asyncio

import pytest

from bhms.protocol import schema, types
from bhms.protocol.errors import BhmsError
from bhms.server.context import Reconciled
from helpers.devices import build, connect, serve


@pytest.fixture
async def env(tmp_path):
    made = []

    async def make(**kw):
        srv, axis = build(tmp_path / f"state{len(made)}", **kw)
        url, listener = await serve(srv, tmp_path, name=f"s{len(made)}.sock")
        client = await connect(url)
        made.append((srv, listener, client))
        return srv, axis, client, url

    yield make
    for srv, listener, client in made:
        await client.close()
        await listener.close()
        await srv.close()


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_invoke_completes_with_measured_verification_and_full_history(env):  # BHMS-OPS-001, OPS-006
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "move_to", {"target": 12.5}, operation_key="m-1", wait_ms=2000)
    op = res.operation
    assert res.replayed is False and op.state == "completed" and op.result == {"position": 12.5}
    assert op.effect == "verified" and op.evidence.kind == "measured"
    assert op.evidence.observations["position"].value == 12.5
    full = (await client.operations_get(op.operation_id)).operation
    schema.validate("Operation", types.to_wire(full))
    states = [h.state for h in full.history if h.kind == "state"]
    assert states == ["accepted", "dispatching", "completed"] and axis.commands["move_to"] == 1


async def test_same_key_same_operation(env):  # BHMS-OPS-030, OPS-032 (plan Review Focus 2)
    srv, axis, client, _ = await env()
    results = await asyncio.gather(*(client.actions_invoke("axis-1", "move_to", {"target": 7}, operation_key="same",
                                                           wait_ms=2000) for _ in range(50)))
    ids = {r.operation.operation_id for r in results}
    assert len(ids) == 1 and axis.commands["move_to"] == 1
    assert sum(1 for r in results if not r.replayed) == 1
    again = await client.actions_invoke("axis-1", "move_to", {"target": 7}, operation_key="same")
    assert again.replayed and again.operation.state == "completed" and axis.commands["move_to"] == 1


async def test_key_conflict_creates_nothing(env):  # BHMS-OPS-031, OPS-040
    srv, axis, client, _ = await env()
    first = await client.actions_invoke("axis-1", "move_to", {"target": 7}, operation_key="k", wait_ms=2000)
    err = await refused(client.actions_invoke("axis-1", "move_to", {"target": 8}, operation_key="k"))
    assert err.code == "KEY_CONFLICT" and err.operation_id == first.operation.operation_id
    assert err.may_have_acted is True and "operations/get" in err.hint
    quantity = await refused(client.actions_invoke("axis-1", "move_to", {"target": {"value": 7, "unit": "mm"}},
                                                   operation_key="k"))
    assert quantity.code == "KEY_CONFLICT"  # same intent in a different form: the hint says to inspect first
    assert axis.commands["move_to"] == 1
    assert len((await client.operations_list()).operations) == 1


async def test_server_keys_are_not_retry_safe(env):  # BHMS-OPS-035
    srv, axis, client, _ = await env()
    a = await client.actions_invoke("axis-1", "move_to", {"target": 1}, wait_ms=2000)
    b = await client.actions_invoke("axis-1", "move_to", {"target": 1}, wait_ms=2000)
    assert a.operation.operation_id != b.operation.operation_id
    assert a.operation.key_origin == b.operation.key_origin == "server" and axis.commands["move_to"] == 2


async def test_reserved_key_prefixes_are_refused(env):  # BHMS-OPS-037
    srv, axis, client, _ = await env()
    err = await refused(client.request("actions/invoke", {"deviceId": "axis-1", "action": "move_to",
                                                         "arguments": {"target": 1}, "operationKey": "d-123"}))
    assert err.code == "INVALID_ARGUMENT" and err.field == "operationKey"
    err = await refused(client.actions_invoke("axis-1", "move_to", {"target": 1}, operation_key="g-123"))
    assert err.code == "INVALID_ARGUMENT" and err.field == "operationKey"
    assert axis.commands["move_to"] == 0


@pytest.mark.parametrize("call, code, field", [
    (dict(device_id="nope", action="move_to", arguments={"target": 1}), "UNKNOWN_DEVICE", "deviceId"),
    (dict(device_id="axis-1", action="fly", arguments={}), "UNKNOWN_ACTION", "action"),
    (dict(device_id="axis-1", action="move_to", arguments={"target": 250}), "OUT_OF_RANGE", "arguments.target"),
    (dict(device_id="axis-1", action="move_to", arguments={"target": {"value": 1, "unit": "cm"}}), "UNIT_MISMATCH",
     "arguments.target"),
    (dict(device_id="axis-1", action="move_to", arguments={"target": 1, "force": True}), "INVALID_ARGUMENT",
     "arguments.force"),
    (dict(device_id="axis-1", action="slow", arguments={}, require={"effect": "verified"}), "UNSUPPORTED", "require"),
    (dict(device_id="axis-1", action="move_to", arguments={"target": 1}, description_digest="sha256:" + "0" * 64),
     "STALE", "descriptionDigest"),
])
async def test_admission_refusals_create_no_operation(env, call, code, field):  # BHMS-OPS-040, OPS-007, DEV-044
    srv, axis, client, _ = await env()
    err = await refused(client.actions_invoke(**call, operation_key="r-1"))
    assert (err.code, err.field, err.may_have_acted) == (code, field, False)
    assert err.hint
    assert sum(axis.commands.values()) == 0
    assert (await client.operations_list()).operations == []
    if code == "UNKNOWN_ACTION":
        assert "move_to" in err.hint  # names the available actions


async def test_short_wait_returns_unsettled_and_wait_settles_without_error(env):  # BHMS-OPS-060, OPS-061
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "slow", {"distance": 2}, operation_key="s-1", wait_ms=50)
    assert res.operation.state in ("dispatching", "running") and res.operation.progress is not None
    waited = await client.operations_wait(res.operation.operation_id, 50)
    assert waited.operation.state == "running"  # timeout elapsed: returned, not an error
    axis.gate.set()
    done = await client.operations_wait(res.operation.operation_id, 2000)
    assert done.operation.state == "completed" and done.operation.result == {"position": 2.0}
    err = await refused(client.operations_wait(res.operation.operation_id, 10 ** 7))
    assert err.code == "OUT_OF_RANGE" and err.field == "timeoutMs"


async def test_queued_operation_cancel_prevents_dispatch(env):  # BHMS-OPS-050
    srv, axis, client, _ = await env()
    first = await client.actions_invoke("axis-1", "slow", {}, operation_key="q-1")
    queued = await client.actions_invoke("axis-1", "move_to", {"target": 3}, operation_key="q-2")
    assert queued.operation.state == "accepted"  # same resource: waits in the queue
    canceled = (await client.operations_cancel(queued.operation.operation_id, reason="changed my mind")).operation
    assert (canceled.state, canceled.cancel.state, canceled.effect) == ("canceled", "confirmed", "none")
    axis.gate.set()
    await client.operations_wait(first.operation.operation_id, 2000)
    assert axis.commands["move_to"] == 0


async def test_cancel_running_supported_action_confirms_termination(env):  # BHMS-OPS-052
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "slow", {}, operation_key="c-1", wait_ms=30)
    op = (await client.operations_cancel(res.operation.operation_id, reason="stop it")).operation
    assert op.cancel.state in ("requested", "confirmed")
    done = (await client.operations_wait(op.operation_id, 2000)).operation
    assert (done.state, done.cancel.state, done.effect) == ("canceled", "confirmed", "unverified")
    kinds = [(h.kind, h.cancel) for h in done.history if h.kind == "cancel"]
    assert ("cancel", "requested") in kinds


async def test_cancel_unsupported_is_refused_and_terminal_is_unchanged(env):  # BHMS-OPS-051, OPS-053
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "stubborn", {}, operation_key="u-1", wait_ms=20)
    op = (await client.operations_cancel(res.operation.operation_id)).operation
    assert op.cancel.state == "refused" and op.state == res.operation.state
    done = await client.actions_invoke("axis-1", "info", {}, operation_key="i-1", wait_ms=2000)
    again = (await client.operations_cancel(done.operation.operation_id)).operation
    assert again.state == "completed" and again.cancel.state == "none"


async def test_max_duration_with_cancel_support_fails_deadline_exceeded(env):  # BHMS-DEV-030, OPS-071
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "slow", {}, operation_key="dl-ok", deadline_ms=100, wait_ms=3000)
    op = res.operation
    assert op.state == "failed" and op.error.bhms_code == "DEADLINE_EXCEEDED" and op.error.may_have_acted
    assert op.cancel.state == "confirmed"


async def test_max_duration_without_cancel_becomes_unknown_then_reconciled(env):  # BHMS-DEV-030, OPS-004/005
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "stubborn", {}, operation_key="st-1", wait_ms=1000)
    op = res.operation
    assert op.state == "unknown" and op.effect == "unknown"
    assert (op.error.bhms_code, op.error.may_have_acted, op.error.retry) == ("DEADLINE_EXCEEDED", True,
                                                                             "after-reconcile")
    late = (await client.operations_wait(op.operation_id, 2000)).operation
    # the handler finished after the bound: reconciled to failed, never completed
    for _ in range(50):
        late = (await client.operations_get(op.operation_id)).operation
        if late.state != "unknown":
            break
        await asyncio.sleep(0.02)
    assert late.state == "failed" and late.error.bhms_code == "DEADLINE_EXCEEDED"
    kinds = [(h.kind, h.state) for h in late.history]
    assert ("state", "unknown") in kinds and ("reconciliation", "failed") in kinds


async def test_deadline_passing_while_queued_rejects_without_dispatch(env):  # BHMS-OPS-070, OPS-041
    srv, axis, client, _ = await env()
    first = await client.actions_invoke("axis-1", "slow", {}, operation_key="b-1")
    queued = await client.actions_invoke("axis-1", "move_to", {"target": 4}, operation_key="b-2", deadline_ms=50)
    await asyncio.sleep(0.15)
    axis.gate.set()
    done = (await client.operations_wait(queued.operation.operation_id, 2000)).operation
    assert done.state == "rejected" and done.error.bhms_code == "DEADLINE_EXCEEDED"
    assert done.error.may_have_acted is False and done.effect == "none"
    await client.operations_wait(first.operation.operation_id, 2000)
    assert axis.commands["move_to"] == 0


async def test_handler_bug_is_unknown_and_inhibits_its_resources_until_reconciled(env):  # BHMS-OPS-004, OPS-042
    srv, axis, client, _ = await env()
    res = await client.actions_invoke("axis-1", "explode", {}, operation_key="x-1", wait_ms=2000)
    op = res.operation
    assert op.state == "unknown" and "driver crashed" in op.error.message
    err = await refused(client.actions_invoke("axis-1", "move_to", {"target": 1}, operation_key="x-2"))
    assert err.code == "STALE" and err.operation_id == op.operation_id and err.may_have_acted is False
    # reconciliation from device evidence lifts the inhibition (BHMS-OPS-005)
    axis.reconcile_answer = Reconciled("failed", evidence="driver log shows no motion", effect="none",
                                       may_have_acted=False, message="the driver crashed before moving")
    await srv.reconcile("axis-1")
    after = (await client.operations_get(op.operation_id)).operation
    assert after.state == "failed" and after.history[-1].kind == "reconciliation"
    ok = await client.actions_invoke("axis-1", "move_to", {"target": 1}, operation_key="x-3", wait_ms=2000)
    assert ok.operation.state == "completed"


async def test_device_fault_fails_with_may_have_acted(env):  # BHMS-ERR-012
    srv, axis, client, _ = await env()
    op = (await client.actions_invoke("axis-1", "fault", {}, operation_key="f-1", wait_ms=2000)).operation
    assert op.state == "failed" and op.error.bhms_code == "DEVICE_FAULT" and op.error.may_have_acted
    full = (await client.operations_get(op.operation_id)).operation
    assert any("moved 2.5 mm" in (h.detail or "") for h in full.history)


async def test_require_verified_with_failing_sensor_fails_unverified(env):  # BHMS-OPS-007
    srv, axis, client, _ = await env()
    axis.sensor_ok = False
    op = (await client.actions_invoke("axis-1", "move_to", {"target": 5}, operation_key="v-1",
                                      require={"effect": "verified"}, wait_ms=2000)).operation
    assert op.state == "failed" and op.error.bhms_code == "UNVERIFIED" and op.error.may_have_acted
    axis.sensor_ok = True
    op2 = (await client.actions_invoke("axis-1", "move_to", {"target": 6}, operation_key="v-2",
                                       require={"effect": "verified"}, wait_ms=2000)).operation
    assert op2.state == "completed" and op2.effect == "verified"


async def test_effect_none_action_completes_with_effect_none(env):  # BHMS-OPS-006
    srv, axis, client, _ = await env()
    op = (await client.actions_invoke("axis-1", "info", {}, wait_ms=2000)).operation
    assert op.state == "completed" and op.effect == "none" and op.result == {"commands": 0}


async def test_get_unknown_operation_is_invalid_argument(env):  # BHMS-OPS-062
    srv, axis, client, _ = await env()
    err = await refused(client.operations_get("op-nope"))
    assert err.code == "INVALID_ARGUMENT" and err.field == "operationId"


async def test_list_filters_and_pages_newest_first(env):  # BHMS-LIF-061/062
    srv, axis, client, _ = await env()
    ids = [(await client.actions_invoke("axis-1", "info", {}, wait_ms=2000)).operation.operation_id
           for _ in range(4)]
    page = await client.operations_list(limit=3)
    assert [o.operation_id for o in page.operations] == ids[::-1][:3] and page.next_cursor
    assert all(o.history is None for o in page.operations)
    rest = await client.operations_list(limit=3, cursor=page.next_cursor)
    assert [o.operation_id for o in rest.operations] == [ids[0]] and rest.next_cursor is None
    assert len((await client.operations_list(state="completed")).operations) == 4
    assert (await client.operations_list(device_id="other")).operations == []


async def test_client_disconnect_does_not_cancel_physical_work(env, tmp_path):  # BHMS-LIF-050 (Ruling R10)
    srv, axis, client, url = await env()
    other = await connect(url)
    task = asyncio.ensure_future(other.actions_invoke("axis-1", "slow", {}, operation_key="dc-1", wait_ms=5000))
    await asyncio.sleep(0.1)
    await other.close()
    with pytest.raises(Exception):
        await task
    axis.gate.set()
    found = None
    for _ in range(100):
        ops = (await client.operations_list()).operations
        if ops and ops[0].state == "completed":
            found = ops[0]
            break
        await asyncio.sleep(0.02)
    assert found is not None and axis.commands["slow"] == 1


async def test_discover_reports_durable_operations_and_epoch(env):  # BHMS-OPS-034, LIF-023
    srv, axis, client, _ = await env()
    d = await client.discover()
    assert d.capabilities.operations.durable is True and d.capabilities.operations.key_retention_s >= 86400
    assert d.epoch == srv.store.epoch and d.principal is not None and "admin" in d.principal.scopes
