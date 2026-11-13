"""Observations, subscriptions and events of DeviceServer over real sockets (Unix and WebSocket with tokens).

Requirement IDs: BHMS-OBS-0xx, LIF-040..045, OPS-090, EVT-0xx, AUTH-012.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from bhms import DeviceServer, Policy, Range, Reading, token_digest
from bhms.client.client import Client
from bhms.protocol.errors import BhmsError

TOKENS = {"admin": "admin-token", "reader": "reader-token", "operator": "operator-token"}


def build(tmp_path, **kw):
    policy = Policy({
        "admin": {"tokens": [token_digest(TOKENS["admin"])], "scopes": ["admin"]},
        "reader": {"tokens": [token_digest(TOKENS["reader"])], "scopes": ["read"]},
        "operator": {"tokens": [token_digest(TOKENS["operator"])],
                     "scopes": ["read", "lease", "invoke:pump-1/*"]},
    })
    srv = DeviceServer("obs-server", state_dir=tmp_path, policy=policy, observation_min_interval_ms=50, **kw)
    state = {"pressure": 101.0, "pressure_ok": True, "fifo_reads": 0, "latency": 0.0, "dispensed": 0,
             "gate": asyncio.Event()}
    pump = srv.device("pump-1", resources=["pump-1/plunger"], capabilities=["bhms.liquid.dispense"])
    pump.report_alive()

    @pump.property(unit="kPa", evidence="measured", validity_ms=500)
    async def pressure() -> float:
        if not state["pressure_ok"]:
            raise RuntimeError("sensor unplugged")
        return Reading(state["pressure"], latency_ms=state["latency"])

    @pump.property(unit="1", evidence="reported", read_effect="transaction", requires_lease=True,
                   resources=["pump-1/plunger"])
    def fifo() -> Range(0, 1000, unit="1", integer=True):
        state["fifo_reads"] += 1
        return state["fifo_reads"]

    @pump.property(evidence="reported", observable=False)
    def firmware() -> str:
        return "1.4.2"

    pump.property(name="temperature", schema=Range(0, 100, unit="Cel"), evidence="measured")

    pump.event("pump.primed", data={"volume": "uL"}, description="the line was primed")

    @pump.action(effect="irreversible", idempotency="relative", max_duration_ms=2000,
                 requires_fresh={"pressure": 1000})
    async def dispense(ctx, volume: Range(1, 100, unit="uL")) -> {"dispensed": "uL"}:  # noqa: F821
        state["dispensed"] += 1
        return {"dispensed": volume}

    @pump.action(effect="reversible", idempotency="idempotent", max_duration_ms=5000)
    async def prime(ctx) -> None:
        await state["gate"].wait()

    return srv, state


@pytest.fixture
async def env(tmp_path):
    made = []

    async def make(**kw):
        srv, state = build(tmp_path / f"st{len(made)}", **kw)
        listener = await srv.listen("ws://127.0.0.1:0")
        url = f"ws://127.0.0.1:{listener.address[1]}"
        clients = {}
        for name, token in TOKENS.items():
            clients[name] = await Client.connect(url, token=token)
        made.append((srv, listener, clients))
        return srv, state, clients

    yield make
    for srv, listener, clients in made:
        for c in clients.values():
            await c.close()
        await listener.close()
        await srv.close()


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


# --------------------------------------------------------------------------- reads


async def test_read_retained_fresh_and_units(env):  # BHMS-OBS-001..005, OBS-010
    srv, state, c = await env()
    first = (await c["reader"].properties_read("pump-1", "pressure")).observation
    assert (first.value, first.unit, first.quality, first.evidence) == (101.0, "kPa", "valid", "measured")
    again = (await c["reader"].properties_read("pump-1", "pressure")).observation
    assert again.sequence == first.sequence and again.acquired_at == first.acquired_at  # retained, not refreshed
    state["pressure"] = 102.0
    fresh = (await c["reader"].properties_read("pump-1", "pressure", fresh=True)).observation
    assert fresh.value == 102.0 and fresh.sequence == first.sequence + 1 and fresh.epoch == first.epoch


async def test_failed_measurement_is_invalid_null_never_substituted(env):  # BHMS-OBS-001
    srv, state, c = await env()
    await c["reader"].properties_read("pump-1", "pressure", fresh=True)
    state["pressure_ok"] = False
    obs = (await c["reader"].properties_read("pump-1", "pressure", fresh=True)).observation
    assert obs.quality == "invalid" and obs.value is None


async def test_age_is_conservative_and_validity_makes_stale(env):  # BHMS-OBS-003
    srv, state, c = await env()
    state["latency"] = 300.0
    obs = (await c["reader"].properties_read("pump-1", "pressure", fresh=True)).observation
    assert obs.age_ms >= 300
    err = await refused(c["reader"].properties_read("pump-1", "pressure", max_age_ms=100))
    assert (err.code, err.field, err.bound) == ("STALE", "maxAgeMs", 100)
    state["latency"] = 0.0
    await c["reader"].properties_read("pump-1", "pressure", fresh=True)
    await asyncio.sleep(0.6)
    stale = (await c["reader"].properties_read("pump-1", "pressure")).observation
    assert stale.quality == "stale" and stale.age_ms > 500


async def test_unbounded_latency_has_null_age_and_fails_max_age(env):  # BHMS-OBS-003
    srv, state, c = await env()
    await srv.devices["pump-1"].publish("temperature", 21.5, latency_ms=None)
    obs = (await c["reader"].properties_read("pump-1", "temperature")).observation
    assert obs.age_ms is None and obs.acquired_at is None and obs.value == 21.5
    err = await refused(c["reader"].properties_read("pump-1", "temperature", max_age_ms=10_000))
    assert err.code == "STALE" and err.field == "maxAgeMs"


async def test_push_only_property_without_value_is_unknown_and_fresh_is_stale(env):  # BHMS-OBS-010
    srv, state, c = await env()
    obs = (await c["reader"].properties_read("pump-1", "temperature")).observation
    assert obs.quality == "unknown" and obs.value is None
    await srv.devices["pump-1"].publish("temperature", 22.0)
    err = await refused(c["reader"].properties_read("pump-1", "temperature", fresh=True))
    assert (err.code, err.field) == ("STALE", "fresh")


async def test_unknown_property_lists_the_properties(env):  # BHMS-OBS-012
    srv, state, c = await env()
    err = await refused(c["reader"].properties_read("pump-1", "flow"))
    assert (err.code, err.field) == ("INVALID_ARGUMENT", "property")
    assert "pressure" in err.hint and "fifo" in err.hint


async def test_transaction_property_needs_invoke_scope_and_lease(env):  # BHMS-OBS-011, AUTH-012
    srv, state, c = await env()
    err = await refused(c["reader"].properties_read("pump-1", "fifo", fresh=True))
    assert err.code == "UNAUTHORIZED" and "invoke:pump-1/fifo" in err.hint
    err = await refused(c["operator"].properties_read("pump-1", "fifo", fresh=True))
    assert err.code == "LEASE_REQUIRED"
    assert state["fifo_reads"] == 0
    lease = (await c["operator"].leases_acquire(["pump-1/plunger"], 5000)).lease
    obs = (await c["operator"].properties_read("pump-1", "fifo", fresh=True)).observation
    assert obs.value == 1 and state["fifo_reads"] == 1
    retained = (await c["reader"].properties_read("pump-1", "fifo")).observation  # retained read needs only read
    assert retained.value == 1 and state["fifo_reads"] == 1
    await c["operator"].leases_release(lease.lease_id)


async def test_requires_fresh_refuses_stale_at_admission(env):  # BHMS-OBS-030
    srv, state, c = await env()
    state["pressure_ok"] = False
    err = await refused(c["operator"].actions_invoke("pump-1", "dispense", {"volume": 5}, operation_key="f-1"))
    assert (err.code, err.field, err.bound) == ("STALE", "requiresFresh[0]",
                                                 {"property": "pressure", "maxAgeMs": 1000})
    assert "invalid" in err.hint and state["dispensed"] == 0
    state["pressure_ok"] = True
    op = (await c["operator"].actions_invoke("pump-1", "dispense", {"volume": 5}, operation_key="f-2",
                                             wait_ms=2000)).operation
    assert op.state == "completed" and state["dispensed"] == 1


async def test_requires_fresh_is_rechecked_before_dispatch(env):  # BHMS-OBS-030, OPS-041
    srv, state, c = await env()
    prime = (await c["admin"].actions_invoke("pump-1", "prime", {}, operation_key="p-1")).operation
    queued = (await c["admin"].actions_invoke("pump-1", "dispense", {"volume": 5}, operation_key="p-2")).operation
    assert queued.state == "accepted"
    state["pressure_ok"] = False
    await asyncio.sleep(1.05)  # the retained sample ages past maxAgeMs 1000; re-acquisition fails
    state["gate"].set()
    done = (await c["admin"].operations_wait(queued.operation_id, 2000)).operation
    assert done.state == "rejected" and done.error.bhms_code == "STALE" and done.effect == "none"
    assert done.error.may_have_acted is False and state["dispensed"] == 0
    assert (await c["admin"].operations_wait(prime.operation_id, 2000)).operation.state == "completed"


# --------------------------------------------------------------------------- subscriptions


async def test_ack_first_with_refusals(env):  # BHMS-LIF-040, OBS-020
    srv, state, c = await env()
    sub = await c["reader"].subscribe(observations=[
        {"deviceId": "pump-1", "property": "pressure"}, {"deviceId": "pump-1", "property": "firmware"},
        {"deviceId": "pump-1", "property": "nope"}, {"deviceId": "ghost", "property": "x"}])
    ack = sub.acknowledged
    assert [o.property for o in ack.notifications.observations] == ["pressure"]
    codes = {r.path: r.bhms_code for r in ack.refused}
    assert codes == {"notifications.observations[1]": "UNSUPPORTED", "notifications.observations[2]":
                     "INVALID_ARGUMENT", "notifications.observations[3]": "UNKNOWN_DEVICE"}
    await sub.cancel()


async def test_observation_rate_floor_and_quality_change(env):  # BHMS-LIF-043, OBS-021
    srv, state, c = await env()
    dev = srv.devices["pump-1"]
    sub = await c["reader"].subscribe(observations=[{"deviceId": "pump-1", "property": "temperature",
                                                     "minIntervalMs": 200}])
    received: list[tuple[float, object]] = []

    async def collect():
        async for item in sub:
            received.append((time.monotonic(), item.params.observation))

    task = asyncio.ensure_future(collect())
    start = time.monotonic()
    for i in range(40):  # 40 acquisitions in ~400 ms
        await dev.publish("temperature", 20.0 + i * 0.1)
        await asyncio.sleep(0.01)
    await dev.publish("temperature", None, quality="invalid")  # quality change inside the floor: delivered now
    await asyncio.sleep(0.05)
    elapsed = time.monotonic() - start
    valid = [o for _, o in received if o.quality == "valid"]
    assert 1 <= len(valid) <= int(elapsed / 0.2) + 2
    assert received[-1][1].quality == "invalid" and received[-1][1].value is None
    await sub.cancel()
    task.cancel()


async def test_subscription_polls_getter_properties(env):  # BHMS-OBS-021
    srv, state, c = await env()
    sub = await c["reader"].subscribe(observations=[{"deviceId": "pump-1", "property": "pressure",
                                                     "minIntervalMs": 50}])
    seen = []
    async for item in sub:
        seen.append(item.params.observation.sequence)
        if len(seen) == 3:
            break
    assert seen == sorted(seen) and len(set(seen)) == 3
    await sub.cancel()


async def test_transaction_property_is_never_polled_by_a_subscription(env):  # BHMS-OBS-022
    srv, state, c = await env()
    sub = await c["reader"].subscribe(observations=[{"deviceId": "pump-1", "property": "fifo"}])
    await asyncio.sleep(0.3)
    assert state["fifo_reads"] == 0
    await sub.cancel()


async def test_operation_notifications_for_every_change_in_order(env):  # BHMS-OPS-090
    srv, state, c = await env()
    sub = await c["operator"].subscribe(operations={"deviceIds": ["pump-1"]})
    op = (await c["operator"].actions_invoke("pump-1", "dispense", {"volume": 3}, operation_key="n-1",
                                             wait_ms=2000)).operation
    states = []
    async for item in sub:
        assert item.method == "notifications/operation" and item.params.operation.history is None
        states.append((item.params.operation.state, item.params.operation.effect))
        if item.params.operation.state == "completed":
            break
    assert states == [("accepted", "none"), ("dispatching", "unknown"), ("completed", "unverified")]
    assert op.operation_id
    other = await c["reader"].subscribe(operations={"all": True})  # another principal sees none of them
    await c["operator"].actions_invoke("pump-1", "dispense", {"volume": 3}, operation_key="n-2", wait_ms=2000)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(other.__anext__(), 0.2)
    await sub.cancel()
    await other.cancel()


async def test_devices_list_changed_and_shutdown_end_reason(env):  # BHMS-DEV-023, LIF-044
    srv, state, c = await env()
    sub = await c["reader"].subscribe(devices_list_changed=True)
    dev = srv.devices["pump-1"]

    @dev.action(effect="none", idempotency="idempotent")
    def ping(ctx) -> None: ...

    item = await asyncio.wait_for(sub.__anext__(), 2)
    assert item.method == "notifications/devices/listChanged"
    await srv.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(sub.__anext__(), 5)
    assert sub.end_reason == "shutdown"


async def test_policy_change_ends_subscription_unauthorized(env):  # BHMS-LIF-042, SEC-012
    srv, state, c = await env()
    sub = await c["reader"].subscribe(devices_list_changed=True)
    srv.set_policy(Policy({"admin": {"tokens": [token_digest(TOKENS["admin"])], "scopes": ["admin"]},
                           "reader": {"tokens": [token_digest(TOKENS["reader"])], "scopes": ["stop"]}}))
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(sub.__anext__(), 2)
    assert sub.end_reason == "unauthorized"
    events = (await c["admin"].events_read(types=["policy.changed"])).events
    assert len(events) == 1


# --------------------------------------------------------------------------- events


async def test_events_cursor_order_stability_and_gap(env):  # BHMS-EVT-001, EVT-010, EVT-011, LIF-060
    srv, state, c = await env()
    dev = srv.devices["pump-1"]
    for v in (1, 2, 3):
        dev.emit("pump.primed", {"volume": v})
    page = await c["reader"].events_read(types=["pump.primed"])
    assert [e.data["volume"] for e in page.events] == [1, 2, 3] and page.gap is False
    again = await c["reader"].events_read(types=["pump.primed"])
    assert [e.model_dump() for e in again.events] == [e.model_dump() for e in page.events]
    after_first = await c["reader"].events_read(after=page.events[0].cursor, types=["pump.primed"])
    assert [e.data["volume"] for e in after_first.events] == [2, 3]
    empty = await c["reader"].events_read(after=page.cursor)
    assert empty.events == [] and empty.cursor == page.cursor
    # a cursor from a reset log (another epoch) reads with gap true; a malformed cursor is INVALID_ARGUMENT
    foreign = "e.00000000." + page.events[0].cursor.rsplit(".", 1)[1]
    assert (await c["reader"].events_read(after=foreign)).gap is True
    err = await refused(c["reader"].events_read(after="garbage"))
    assert (err.code, err.field) == ("INVALID_ARGUMENT", "after")
    srv.store.prune_events(2 ** 62)  # retention expired for everything
    assert (await c["reader"].events_read(after=page.events[0].cursor)).gap is True


async def test_device_events_are_declared_and_validated(env):  # BHMS-EVT-003
    srv, state, c = await env()
    dev = srv.devices["pump-1"]
    with pytest.raises(ValueError):
        dev.emit("pump.primed", {"volume": "lots"})
    with pytest.raises(ValueError):
        dev.emit("pump.exploded", {})
    desc = (await c["reader"].devices_describe("pump-1")).description
    assert desc.events["pump.primed"].data["properties"]["volume"]["x-bhms-unit"] == "uL"


async def test_unknown_operation_produces_an_event(env):  # BHMS-EVT-002
    srv, state, c = await env()
    dev = srv.devices["pump-1"]

    @dev.action(effect="reversible", idempotency="relative", max_duration_ms=1000)
    async def bad(ctx) -> None:
        raise RuntimeError("bus error")

    op = (await c["admin"].actions_invoke("pump-1", "bad", {}, wait_ms=2000)).operation
    assert op.state == "unknown"
    events = (await c["admin"].events_read(types=["operation.state"])).events
    assert events[-1].operation_id == op.operation_id and events[-1].data == {"state": "unknown",
                                                                              "previousState": "dispatching"}


async def test_listen_replays_then_goes_live_without_seam(env):  # BHMS-EVT-020
    srv, state, c = await env()
    dev = srv.devices["pump-1"]
    first = dev.emit("pump.primed", {"volume": 0})
    for v in range(1, 20):
        dev.emit("pump.primed", {"volume": v})
    producing = True

    async def produce():
        v = 100
        while producing:
            dev.emit("pump.primed", {"volume": v})
            v += 1
            await asyncio.sleep(0)

    task = asyncio.ensure_future(produce())
    await asyncio.sleep(0.01)
    sub = await c["reader"].subscribe(events={"after": first["cursor"], "types": ["pump.primed"]})
    assert sub.acknowledged.events_gap is False
    got = []
    async for item in sub:
        got.append(item.params.event.data["volume"])
        if len(got) >= 60:
            break
    producing = False
    await task
    await sub.cancel()
    assert got[:19] == list(range(1, 20))
    assert got[19:] == list(range(100, 100 + len(got) - 19))  # no duplicate, no omission at the seam
