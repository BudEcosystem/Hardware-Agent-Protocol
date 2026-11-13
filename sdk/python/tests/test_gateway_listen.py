"""Gateway step 7: subscriptions/listen fan-in (operations, events with the gateway's cursors, observation relays).

Spec: BHMS-LIF-040..046, EVT-001/010/011/020, OPS-090.
"""

from __future__ import annotations

import asyncio

import pytest

from bhms.runtime.authority import Policy
from helpers.gateway_rig import TOKENS, principals, rig


async def take(sub, count, timeout=5.0):
    out = []
    for _ in range(count):
        out.append(await asyncio.wait_for(sub.__anext__(), timeout))
    return out


async def test_operation_notifications_carry_gateway_ids_in_change_order(tmp_path):  # OPS-090
    async with rig(tmp_path) as r:
        owner, other = await r.client(), await r.client(token=TOKENS["agent-b"])
        admin = await r.client(token=TOKENS["admin"])
        async with await owner.subscribe(operations={"all": True}) as mine, \
                await other.subscribe(operations={"all": True}) as theirs, \
                await admin.subscribe(operations={"all": True}) as everything:
            assert mine.acknowledged.notifications.operations is not None
            op = (await owner.actions_invoke("a/axis-1", "slow", {"distance": 1}, operation_key="n")).operation
            r.axes["a"].gate.set()
            seen = []
            while not seen or seen[-1].params.operation.state != "completed":
                seen += await take(mine, 1)
            states = [n.params.operation.state for n in seen]
            assert states[-1] == "completed" and "running" in states
            assert {n.params.operation.operation_id for n in seen} == {op.operation_id}
            assert {n.params.operation.device_id for n in seen} == {"a/axis-1"}
            assert all(n.method == "notifications/operation" for n in seen)
            ids = []
            while len(ids) < len(seen):
                ids.append((await take(everything, 1))[0].params.operation.operation_id)
            assert set(ids) == {op.operation_id}
            with pytest.raises(asyncio.TimeoutError):  # another principal's operations are not delivered
                await asyncio.wait_for(theirs.__anext__(), 0.3)


async def test_events_are_fanned_in_with_gateway_cursors_and_ids(tmp_path):  # EVT-001, 010, 020
    async with rig(tmp_path) as r:
        client = await r.client()
        r.servers["a"].events.append("device.fault", severity="error", device_id="axis-1", message="a stalled",
                                     data={"code": "E1"})
        r.servers["b"].events.append("device.fault", severity="error", device_id="axis-1", message="b stalled")
        for _ in range(100):
            page = await client.events_read(types=["device.fault"])
            if len(page.events) == 2:
                break
            await asyncio.sleep(0.05)
        assert sorted(e.device_id for e in page.events) == ["a/axis-1", "b/axis-1"]
        assert page.gap is False and len({e.cursor for e in page.events}) == 2
        first = page.events[0]
        again = (await client.events_read(types=["device.fault"])).events[0]
        assert again.cursor == first.cursor and again.message == first.message  # an event read twice is the same
        # replay then live, no duplicate and no omission at the seam
        async with await client.subscribe(events={"after": first.cursor, "types": ["device.fault"]}) as sub:
            assert sub.acknowledged.events_gap is False
            replayed = (await take(sub, 1))[0].params.event
            assert replayed.cursor == page.events[1].cursor
            r.servers["a"].events.append("device.fault", severity="error", device_id="axis-1", message="again")
            live = (await take(sub, 1))[0].params.event
            assert live.message == "again" and live.device_id == "a/axis-1"
        old = (await client.events_read(after="e.00000000.1")).gap  # a cursor of another log: explicit gap (EVT-011)
        assert old is True


async def test_operation_events_use_the_gateways_operation_ids(tmp_path):  # EVT-002
    from bhms.client.client import Client

    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        direct = await Client.connect(f"unix:{tmp_path}/a.sock")
        try:
            await direct.request("x-conformance/inject", {"fault": "crash_next"})  # the next command ends unknown
            op = (await client.actions_invoke("a/axis-1", "pulse", {"count": 1}, operation_key="u", wait_ms=2000)).operation
            assert op.state in ("unknown", "running", "dispatching")
            for _ in range(100):
                events = [e for e in (await client.events_read(types=["operation.state"])).events]
                if events:
                    break
                await asyncio.sleep(0.05)
            assert events and all(e.operation_id == op.operation_id for e in events)
            assert all(e.device_id == "a/axis-1" for e in events)
            everything = (await client.events_read()).events
            assert all(e.device_id is None or "/" in e.device_id for e in everything)  # no un-namespaced id leaks
        finally:
            await direct.close()


async def test_observations_are_relayed_shared_and_closed(tmp_path):
    async with rig(tmp_path, names=("a",), gateway_kw={"observation_min_interval_ms": 20}) as r:
        one, two = await r.client(), await r.client(token=TOKENS["agent-b"])
        r.axes["a"].position = 12.0
        watch = [{"deviceId": "a/axis-1", "property": "position", "minIntervalMs": 50}]
        async with await one.subscribe(observations=watch) as first, await two.subscribe(observations=watch) as second:
            assert first.acknowledged.notifications.observations
            n1, n2 = (await take(first, 1))[0], (await take(second, 1))[0]
            for n in (n1, n2):
                assert n.method == "notifications/observation" and n.params.device_id == "a/axis-1"
                assert n.params.property == "position" and n.params.observation.value == 12.0
            assert len(r.gateway.observations._relays) == 1  # one upstream stream for both subscribers
        for _ in range(50):
            if not r.gateway.observations._relays:
                break
            await asyncio.sleep(0.05)
        assert r.gateway.observations._relays == {}  # the last subscriber closed it


async def test_refused_parts_are_reported_in_the_acknowledgement(tmp_path):  # LIF-040
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        async with await client.subscribe(observations=[{"deviceId": "a/none", "property": "position"},
                                                         {"deviceId": "a/axis-1", "property": "nope"}]) as sub:
            refused = {x.path: x.bhms_code for x in sub.acknowledged.refused}
            assert refused == {"notifications.observations[0]": "UNKNOWN_DEVICE",
                               "notifications.observations[1]": "INVALID_ARGUMENT"}


async def test_listen_ends_with_unauthorized_when_read_is_revoked(tmp_path):  # LIF-042, 044
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        async with await client.subscribe(devices_list_changed=True) as sub:
            r.gateway.set_policy(Policy(principals(agent_scopes=["lease"])))
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(sub.__anext__(), 5)
            assert sub.end_reason == "unauthorized"


async def test_listen_ends_with_shutdown_when_the_gateway_closes(tmp_path):  # LIF-044
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        sub = await client.subscribe(devices_list_changed=True)
        await r.gateway.close()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(sub.__anext__(), 5)
        assert sub.end_reason == "shutdown"
