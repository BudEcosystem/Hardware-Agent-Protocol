"""Gateway step 2: routing of invoke/read/get/wait/cancel/list through the forwarding journal.

Spec: BHMS-AUTH-014 (deterministic per-principal upstream keys, key lookup before policy), OPS-030/031/033/040/053/054/
060/062, LIF-018 (trace propagation).
"""

from __future__ import annotations

import asyncio
import re

import pytest

from bhms.gateway import upstream_key
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy
from helpers.gateway_rig import TOKENS, UID, principals, rig


async def test_invoke_is_forwarded_and_rewritten(tmp_path):
    async with rig(tmp_path) as r:
        client = await r.client()
        reply = await client.actions_invoke("a/axis-1", "move_to", {"target": 12.5}, operation_key="k1", wait_ms=2000)
        op = reply.operation
        assert reply.replayed is False and op.state == "completed" and op.result["position"] == 12.5
        assert op.device_id == "a/axis-1" and op.operation_key == "k1" and op.key_origin == "client"
        assert op.effect == "verified"
        rec = r.gateway.journal.get(op.operation_id)
        assert rec.principal == "agent" and rec.private["upstream"] == "a"
        assert op.operation_id != rec.private["upstreamOperationId"]  # the gateway mints its own ids (LIF-031)
        assert r.axes["a"].commands["move_to"] == 1 and r.axes["b"].commands["move_to"] == 0


async def test_upstream_key_is_the_pinned_formula(tmp_path):  # BHMS-AUTH-014
    key = upstream_key("gw-test", "agent", "k1")
    assert re.fullmatch(r"g-[a-z2-7]{26}", key) and len(key) == 28
    assert key == upstream_key("gw-test", "agent", "k1")  # deterministic
    assert len({key, upstream_key("other-gw", "agent", "k1"), upstream_key("gw-test", "agent-b", "k1"),
                upstream_key("gw-test", "agent", "k2"), upstream_key("gw-test", "agen", "tk1")}) == 5
    import base64
    import hashlib

    raw = hashlib.sha256(b"gw-test\nagent\nk1").digest()
    assert key == "g-" + base64.b32encode(raw).decode().rstrip("=").lower()[:26]
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="k1",
                                          wait_ms=2000)).operation
        assert r.gateway.journal.get(op.operation_id).private["upstreamKey"] == key
        # the upstream recorded exactly that key (as the gateway's principal)
        found = [row for row in r.servers["a"].store.list_operations(principal=None, limit=10) if row.record["operationKey"] == key]
        assert len(found) == 1 and found[0].record["keyOrigin"] == "client"


async def test_same_key_replays_without_a_second_effect(tmp_path):  # BHMS-OPS-030
    async with rig(tmp_path) as r:
        client = await r.client()
        first = await client.actions_invoke("a/axis-1", "move_to", {"target": 5}, operation_key="k", wait_ms=2000)
        again = await client.actions_invoke("a/axis-1", "move_to", {"target": 5}, operation_key="k", wait_ms=2000)
        assert again.replayed is True and again.operation.operation_id == first.operation.operation_id
        assert again.operation.state == "completed" and r.axes["a"].commands["move_to"] == 1


async def test_same_key_other_intent_is_key_conflict_naming_the_gateway_operation(tmp_path):  # BHMS-OPS-031
    async with rig(tmp_path) as r:
        client = await r.client()
        first = (await client.actions_invoke("a/axis-1", "move_to", {"target": 5}, operation_key="k")).operation
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 6}, operation_key="k")
        assert exc.value.code == "KEY_CONFLICT" and exc.value.operation_id == first.operation_id
        await asyncio.sleep(0.1)
        assert r.axes["a"].commands["move_to"] == 1


async def test_two_principals_with_one_key_get_two_operations(tmp_path):  # BHMS-AUTH-014
    async with rig(tmp_path) as r:
        one = await r.client()
        two = await r.client(token=TOKENS["agent-b"])
        a = (await one.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="same", wait_ms=2000)).operation
        b = (await two.actions_invoke("a/axis-1", "move_to", {"target": 2}, operation_key="same", wait_ms=2000)).operation
        assert a.operation_id != b.operation_id and a.result["position"] == 1 and b.result["position"] == 2
        assert r.axes["a"].commands["move_to"] == 2
        keys = {row.record["operationKey"] for row in r.servers["a"].store.list_operations(principal=None, limit=10)}
        assert keys == {upstream_key("gw-test", "agent", "same"), upstream_key("gw-test", "agent-b", "same")}


async def test_concurrent_identical_requests_make_one_operation(tmp_path):  # BHMS-OPS-032
    async with rig(tmp_path) as r:
        client = await r.client()
        replies = await asyncio.gather(*(client.actions_invoke("a/axis-1", "move_to", {"target": 9}, operation_key="c",
                                                               wait_ms=2000) for _ in range(20)))
        assert len({x.operation.operation_id for x in replies}) == 1 and sum(not x.replayed for x in replies) == 1
        assert r.axes["a"].commands["move_to"] == 1


async def test_key_lookup_precedes_policy(tmp_path):  # BHMS-AUTH-014 + OPS-033
    async with rig(tmp_path) as r:
        client = await r.client()
        first = (await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k", wait_ms=2000)).operation
        r.gateway.set_policy(Policy(principals(agent_scopes=["read"])))  # the scope is revoked
        again = await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k")
        assert again.replayed is True and again.operation.operation_id == first.operation_id
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="new")
        assert exc.value.code == "UNAUTHORIZED" and "scope:invoke" in exc.value.hint
        assert r.axes["a"].commands["move_to"] == 1


async def test_refusals_create_no_operation(tmp_path):  # BHMS-OPS-040
    async with rig(tmp_path) as r:
        client = await r.client()
        for call, code in [(("a/axis-1", "move_to", {"target": 500}), "OUT_OF_RANGE"),
                           (("a/axis-1", "nope", {}), "UNKNOWN_ACTION"),
                           (("z/axis-1", "move_to", {"target": 1}), "UNKNOWN_DEVICE"),
                           (("a/axis-1", "move_to", {"target": 1, "extra": 1}), "INVALID_ARGUMENT")]:
            with pytest.raises(BhmsError) as exc:
                await client.actions_invoke(*call, operation_key="r")
            assert exc.value.code == code and exc.value.may_have_acted is False
        assert [op async for op in client.iter_operations()] == []
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="d-reserved")
        assert exc.value.code == "INVALID_ARGUMENT"


async def test_read_is_forwarded(tmp_path):
    async with rig(tmp_path) as r:
        client = await r.client()
        r.axes["a"].position = 33.0
        obs = (await client.properties_read("a/axis-1", "position", fresh=True)).observation
        assert obs.value == 33.0 and obs.quality == "valid" and obs.evidence == "measured"
        with pytest.raises(BhmsError) as exc:
            await client.properties_read("a/axis-1", "nope")
        assert exc.value.code == "INVALID_ARGUMENT"


async def test_get_wait_cancel_list_are_routed(tmp_path):  # BHMS-OPS-050, 053, 060
    async with rig(tmp_path) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "slow", {"distance": 2}, operation_key="s")).operation
        assert op.state in ("dispatching", "running")
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state == "running" and got.history and got.operation_id == op.operation_id
        waited = (await client.operations_wait(op.operation_id, 200)).operation
        assert waited.state == "running"  # the timeout is not an error (BHMS-OPS-060)
        listing = [x async for x in client.iter_operations(device_id="a/axis-1")]
        assert [x.operation_id for x in listing] == [op.operation_id]
        cancelled = (await client.operations_cancel(op.operation_id, reason="test")).operation
        assert cancelled.cancel.state in ("requested", "acknowledged", "confirmed")
        settled = (await client.operations_wait(op.operation_id, 3000)).operation
        assert settled.state == "canceled" and settled.cancel.state == "confirmed"
        assert (await client.operations_cancel(op.operation_id)).operation.state == "canceled"  # unchanged (OPS-053)
        r.axes["a"].gate.set()
        done = (await client.actions_invoke("a/axis-1", "slow", {"distance": 1}, operation_key="s2", wait_ms=3000)).operation
        assert done.state == "completed"
        assert [x.state async for x in client.iter_operations(state="completed")] == ["completed"]


async def test_wait_ms_returns_when_the_operation_settles(tmp_path):  # BHMS-OPS-061
    async with rig(tmp_path) as r:
        client = await r.client()
        r.axes["a"].gate.clear()
        task = asyncio.create_task(client.actions_invoke("a/axis-1", "slow", {"distance": 1}, operation_key="w",
                                                        wait_ms=5000))
        await asyncio.sleep(0.3)
        assert not task.done()
        r.axes["a"].gate.set()
        assert (await asyncio.wait_for(task, 3)).operation.state == "completed"


async def test_operations_are_visible_to_their_owner_and_admin_only(tmp_path):  # BHMS-OPS-054, 062
    async with rig(tmp_path) as r:
        owner = await r.client()
        other = await r.client(token=TOKENS["agent-b"])
        admin = await r.client(token=TOKENS["admin"])
        op = (await owner.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="o", wait_ms=2000)).operation
        with pytest.raises(BhmsError) as exc:
            await other.operations_get(op.operation_id)
        assert exc.value.code == "INVALID_ARGUMENT" and exc.value.field == "operationId"
        assert [x async for x in other.iter_operations()] == []
        assert (await admin.operations_get(op.operation_id)).operation.operation_id == op.operation_id
        assert len([x async for x in admin.iter_operations()]) == 1


async def test_trace_context_reaches_the_upstream(tmp_path):  # BHMS-LIF-018
    async with rig(tmp_path, names=("a",)) as r:
        seen = []
        original = r.servers["a"].rpc._handlers["actions/invoke"]

        async def spy(params, ctx):
            seen.append(ctx.params["_meta"])
            return await original(params, ctx)

        r.servers["a"].rpc.register("actions/invoke", spy)
        client = await r.client()
        trace = {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01", "tracestate": "a=b"}
        await client.request("actions/invoke", {"_meta": {"bhms/protocolVersion": client.version, **trace},
                                                "deviceId": "a/axis-1", "action": "move_to",
                                                "arguments": {"target": 4}, "operationKey": "t"})
        assert seen[0]["traceparent"] == trace["traceparent"] and seen[0]["tracestate"] == "a=b"


async def test_a_lost_forward_reply_is_reconciled_by_resending_the_same_key(tmp_path, monkeypatch):  # BHMS-OPS-004, 030
    from bhms.gateway.upstreams import Upstream

    original = Upstream.call
    lose = {"on": True}

    async def lossy(self, method, params, **kw):
        result = await original(self, method, params, **kw)
        if method == "actions/invoke" and lose["on"]:
            raise asyncio.TimeoutError()  # the upstream acted; the answer never reached the gateway
        return result

    monkeypatch.setattr(Upstream, "call", lossy)
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        reply = await client.actions_invoke("a/axis-1", "move_to", {"target": 7}, operation_key="lost")
        assert reply.operation.state == "unknown" and reply.operation.error.bhms_code == "DEADLINE_EXCEEDED"
        assert reply.operation.error.may_have_acted is True
        lose["on"] = False
        rec = r.gateway.journal.get(reply.operation.operation_id)
        assert rec.private.get("upstreamOperationId") is None  # the forward was in doubt
        for _ in range(100):  # the reconciler asks again until the upstream reports progress
            settled = (await client.operations_get(reply.operation.operation_id)).operation
            if settled.state != "unknown":
                break
            await asyncio.sleep(0.05)
        assert settled.state == "completed" and settled.result["position"] == 7
        assert [h.kind for h in settled.history if h.state == "completed"] == ["reconciliation"]
        assert r.axes["a"].commands["move_to"] == 1  # the same upstream key: deduplicated, not executed twice


async def test_gateway_restart_resends_the_same_upstream_key(tmp_path, monkeypatch):  # the Task 5 brief, journal row
    from bhms.client.client import Client
    from bhms.gateway import Gateway
    from bhms.gateway.upstreams import Upstream

    original = Upstream.call

    async def lossy(self, method, params, **kw):
        result = await original(self, method, params, **kw)
        if method == "actions/invoke":
            raise asyncio.TimeoutError()
        return result

    monkeypatch.setattr(Upstream, "call", lossy)
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 8}, operation_key="rs")).operation
        assert op.state == "unknown"
        await client.close()
        await r.gateway.close()
        monkeypatch.setattr(Upstream, "call", original)
        again = Gateway(r.gateway.config)
        await again.start()
        try:
            listener = await again.listen(r.socket)
            async with await Client.connect(r.socket) as fresh:
                for _ in range(100):
                    got = (await fresh.operations_get(op.operation_id)).operation
                    if got.state == "completed":
                        break
                    await asyncio.sleep(0.05)
                assert got.state == "completed" and got.result["position"] == 8
                replay = await fresh.actions_invoke("a/axis-1", "move_to", {"target": 8}, operation_key="rs")
                assert replay.replayed is True and replay.operation.operation_id == op.operation_id
            await listener.close()
        finally:
            await again.close()
        assert r.axes["a"].commands["move_to"] == 1 and UID >= 0


async def test_cancelling_an_in_doubt_operation_is_recorded_and_not_resent(tmp_path, monkeypatch):  # OPS-053
    from bhms.gateway.upstreams import Upstream

    original = Upstream.call

    async def lossy(self, method, params, **kw):
        result = await original(self, method, params, **kw)
        if method == "actions/invoke":
            raise asyncio.TimeoutError()  # the upstream acted; the answer was lost
        return result

    monkeypatch.setattr(Upstream, "call", lossy)
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "slow", {"distance": 1}, operation_key="dq")).operation
        assert op.state == "unknown"
        asked = (await client.operations_cancel(op.operation_id, reason="changed my mind")).operation
        assert asked.cancel.state == "requested"  # recorded although it cannot be forwarded yet
        await asyncio.sleep(1.2)
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state == "unknown" and got.cancel.state == "requested"  # never re-sent after a cancel (fix round 1)
        assert r.axes["a"].commands["slow"] == 1
