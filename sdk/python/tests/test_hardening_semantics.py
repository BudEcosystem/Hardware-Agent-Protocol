"""Task 7b group A: semantics found wanting by Tasks 10 and 11 (hazardous leases, reconcile on return, operator resolution)."""

from __future__ import annotations

import pytest

from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.server.decorators import DescriptionError
from bhms.server.device import Device

# ---------------------------------------------------------------------------- A5: hazardous actions require a lease


def _hazardous(**options):
    dev = Device(None, "oven-1", resources=["oven-1/heater"])

    @dev.action(effect="hazardous", idempotency="absolute", max_duration_ms=1000, **options)
    def heat(ctx) -> None:
        """Heat."""

    return dev


def test_a_hazardous_action_must_require_a_lease():  # BHMS-DEV-033 (Task 10 gap 8: the centrifuge spin ran without one)
    with pytest.raises(DescriptionError) as exc:
        _hazardous()
    assert "BHMS-DEV-033" in str(exc.value) and "requires_lease=True" in str(exc.value) and "heat" in str(exc.value)
    description = _hazardous(requires_lease=True).description()
    assert description["actions"]["heat"]["requiresLease"] is True


def test_the_schema_rejects_a_hazardous_action_without_a_lease():
    action = _hazardous(requires_lease=True).description()["actions"]["heat"]
    schema.validate("ActionDescription", action)
    with pytest.raises(BhmsError) as exc:
        schema.validate("ActionDescription", {**action, "requiresLease": False})
    assert exc.value.bhms_code == "INVALID_ARGUMENT" and "requiresLease" in (exc.value.field or "")


# ---------------------------------------------------------------------------- A3: reconcile when a device returns; B9: liveness probe

import asyncio  # noqa: E402

from bhms.client.client import Client  # noqa: E402
from bhms.server import DeviceLost, Range, Reconciled  # noqa: E402
from bhms.server.server import DeviceServer  # noqa: E402


class _Instrument:
    """A device whose power can be cut: a command in flight is lost, and after power returns it can say what happened."""

    def __init__(self) -> None:
        self.powered = True
        self.done: dict[str, float] = {}
        self.reconcile_calls: list[str] = []
        self.knows = True
        self.probe_calls = 0


async def _instrument_server(tmp_path, **server_kw):
    inst = _Instrument()
    srv = DeviceServer("returns", state_dir=str(tmp_path), **server_kw)
    dev = srv.device("spin-1", name="Centrifuge", resources=["spin-1/rotor"])
    dev.report_alive()

    @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=2000)
    async def spin(ctx, speed: Range(0, 100, unit="{rev}/s")) -> {"speed": Range(0, 100, unit="{rev}/s")}:  # noqa: F821
        inst.done[ctx.operation_id] = speed  # the instrument acted ...
        if not inst.powered:
            raise DeviceLost("power lost during spin")  # ... but its reply never arrived
        return {"speed": speed}

    @dev.property(unit="{rev}/s", evidence="measured")
    def speed() -> float:
        """Tachometer."""
        return max(inst.done.values(), default=0.0)

    @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=2000, completion_evidence="measured",
                verified_by=["speed"])
    async def checked_spin(ctx, speed: Range(0, 100, unit="{rev}/s")) -> {"speed": Range(0, 100, unit="{rev}/s")}:  # noqa: F821
        inst.done[ctx.operation_id] = speed
        if not inst.powered:
            raise DeviceLost("power lost during spin")
        await ctx.verify("speed", lambda v: v == speed)
        return {"speed": speed}

    @dev.reconcile
    async def reconcile(op):
        inst.reconcile_calls.append(op["operationId"])
        if not inst.powered:
            raise DeviceLost("still without power")
        if not inst.knows:
            return None
        if op["operationId"] in inst.done:
            return Reconciled("completed", evidence="the instrument's run log lists the command as finished",
                              result={"speed": inst.done[op["operationId"]]})
        return Reconciled("failed", evidence="the run log has no such command", may_have_acted=False, effect="none")

    await srv.listen(f"unix:{tmp_path}/s.sock")
    return srv, dev, inst, await Client.connect(f"unix:{tmp_path}/s.sock")


async def _settled(client, op_id, state, timeout=3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        op = (await client.operations_get(op_id)).operation
        if op.state == state or asyncio.get_running_loop().time() > deadline:
            return op
        await asyncio.sleep(0.02)


async def _power_cut_operation(client, dev, inst):
    inst.powered = False
    op = (await client.actions_invoke("spin-1", "spin", {"speed": 50.0}, wait_ms=2000)).operation
    assert op.state == "unknown"
    dev.set_status("offline")
    return op


async def test_reconcile_runs_when_an_offline_device_returns(tmp_path):
    """Task 11 S11: 54 of 67 power-cut drills stayed unknown with power restored, because nothing asked the device."""
    srv, dev, inst, client = await _instrument_server(tmp_path)
    try:
        op = await _power_cut_operation(client, dev, inst)
        assert inst.reconcile_calls == []  # nothing is asked while the device is away
        inst.powered = True
        dev.set_status(None)  # the device is back (its last evidence of life is recent)
        dev.report_alive()
        resolved = await _settled(client, op.operation_id, "completed")
        assert resolved.state == "completed" and resolved.result == {"speed": 50.0} and resolved.effect == "unverified"
        assert inst.reconcile_calls == [op.operation_id]  # once per return, not once per sign of life
        kinds = [(h.kind, h.state) for h in resolved.history if h.kind in ("state", "reconciliation")]
        assert kinds[-2:] == [("state", "unknown"), ("reconciliation", "completed")]  # history is appended, never rewritten
        # the inhibition is lifted: the resource is usable again
        assert (await client.actions_invoke("spin-1", "spin", {"speed": 1.0}, wait_ms=2000)).operation.state == "completed"
    finally:
        await client.close()
        await srv.close()


async def test_reconcile_on_return_never_assumes_success(tmp_path):
    srv, dev, inst, client = await _instrument_server(tmp_path)
    try:
        op = await _power_cut_operation(client, dev, inst)
        inst.powered, inst.knows = True, False  # the device is back but cannot say what happened
        dev.set_status(None)
        dev.report_alive()
        await asyncio.sleep(0.2)
        assert inst.reconcile_calls == [op.operation_id]
        still = (await client.operations_get(op.operation_id)).operation
        assert still.state == "unknown" and still.effect == "unknown"
        with pytest.raises(BhmsError) as exc:  # and its resources stay inhibited (BHMS-OPS-042)
            await client.actions_invoke("spin-1", "spin", {"speed": 1.0})
        assert exc.value.bhms_code == "STALE" and exc.value.operation_id == op.operation_id
        # the next return asks again, once
        dev.set_status("offline")
        inst.knows = True
        dev.set_status(None)
        resolved = await _settled(client, op.operation_id, "completed")
        assert resolved.state == "completed" and inst.reconcile_calls == [op.operation_id] * 2
    finally:
        await client.close()
        await srv.close()


async def test_a_reconcile_hook_that_hangs_is_bounded_and_leaves_the_operation_unknown(tmp_path):
    srv, dev, inst, client = await _instrument_server(tmp_path, reconcile_timeout_s=0.1)
    try:
        op = await _power_cut_operation(client, dev, inst)
        release = asyncio.Event()

        @dev.reconcile
        async def hangs(op):
            inst.reconcile_calls.append("hung")
            await release.wait()

        dev.set_status(None)
        dev.report_alive()
        await asyncio.sleep(0.4)
        assert inst.reconcile_calls == ["hung"]
        assert (await client.operations_get(op.operation_id)).operation.state == "unknown"
        assert not [t for t in asyncio.all_tasks() if t.get_name().startswith("bhms-reconcile")]  # the bound ended it
    finally:
        await client.close()
        await srv.close()


async def test_a_periodic_liveness_probe_takes_a_dead_instrument_offline_and_brings_it_back(tmp_path):
    """Task 10 gap 6: liveness ran only at start, so a bridge whose instrument died kept reporting its last status."""
    srv, dev, inst, client = await _instrument_server(tmp_path)

    @dev.liveness(interval_s=0.05, timeout_s=0.5)
    async def alive() -> bool:
        inst.probe_calls += 1
        if not inst.powered:
            raise ConnectionRefusedError("instrument does not answer")
        return True

    srv.start_liveness(dev)  # declared after start: begin probing now
    try:
        async def status():
            return (await client.devices_list()).devices[0].status

        await asyncio.sleep(0.2)
        assert await status() == "online" and inst.probe_calls >= 2
        op = (await client.actions_invoke("spin-1", "spin", {"speed": 5.0}, wait_ms=1000)).operation
        assert op.state == "completed"
        inst.powered = False
        lost = (await client.actions_invoke("spin-1", "spin", {"speed": 6.0}, wait_ms=1000)).operation
        assert lost.state == "unknown"
        await asyncio.sleep(0.2)
        assert await status() == "offline"  # evidence of unreachability, not a stale "online"
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("spin-1", "spin", {"speed": 1.0})
        assert exc.value.bhms_code in ("DEVICE_UNAVAILABLE", "STALE")
        events = [e.type for e in (await client.events_read(types=["device.offline", "device.online"])).events]
        assert events == ["device.offline"]
        inst.powered = True  # the probe notices by itself: no set_status needed, and the lost operation is reconciled
        resolved = await _settled(client, lost.operation_id, "completed")
        assert resolved.state == "completed" and await status() == "online"
        events = [e.type for e in (await client.events_read(types=["device.offline", "device.online"])).events]
        assert events == ["device.offline", "device.online"]
    finally:
        await client.close()
        await srv.close()
    assert not [t for t in asyncio.all_tasks() if t.get_name().startswith("bhms-liveness")]


async def test_the_liveness_probe_is_off_by_default_and_a_server_wide_default_can_turn_it_on(tmp_path):
    srv, dev, inst, client = await _instrument_server(tmp_path)
    try:
        @dev.liveness
        def alive() -> bool:
            inst.probe_calls += 1
            return True

        srv.start_liveness(dev)
        await asyncio.sleep(0.15)
        assert inst.probe_calls == 0 and not [t for t in asyncio.all_tasks() if t.get_name().startswith("bhms-liveness")]
    finally:
        await client.close()
        await srv.close()
    srv2 = DeviceServer("probing", state_dir=str(tmp_path / "two"), liveness_interval_s=0.05)
    calls = []
    dev2 = srv2.device("d-1", name="D")

    @dev2.liveness
    def alive2() -> bool:
        calls.append(1)
        return True

    await srv2.start()
    try:
        await asyncio.sleep(0.2)
        assert len(calls) >= 3 and dev2.status == "online"
    finally:
        await srv2.close()
    with pytest.raises(ValueError):
        DeviceServer("bad", liveness_interval_s=0)


# ---------------------------------------------------------------------------- A4: operator resolution of an unprovable unknown

from bhms.runtime.authority import Policy, token_digest  # noqa: E402

RESOLVE_TOKENS = {"agent": "t-agent", "operator": "t-operator", "resolver": "t-resolver", "auditor": "t-auditor"}


def _resolve_policy() -> Policy:
    scopes = {"agent": ["read", "lease", "invoke:spin-1/*", "stop:spin-1"], "operator": ["admin"],
              "resolver": ["read", "operations:read", "operations:resolve"], "auditor": ["read", "operations:read"]}
    return Policy({name: {"tokens": [token_digest(RESOLVE_TOKENS[name])], "scopes": scopes[name]} for name in scopes})


async def _resolve_rig(tmp_path):
    srv, dev, inst, local = await _instrument_server(tmp_path, policy=_resolve_policy())
    await local.close()
    listener = await srv.listen("ws://127.0.0.1:0")
    url = f"ws://127.0.0.1:{listener.address[1]}"
    clients = {name: await Client.connect(url, token=token) for name, token in RESOLVE_TOKENS.items()}
    return srv, dev, inst, clients


async def _close(srv, clients):
    for client in clients.values():
        await client.close()
    await srv.close()


async def test_an_operator_resolves_an_unknown_the_device_cannot_prove(tmp_path):
    """Task 10 gap 5: a dead bridge left its operation unknown, and its resources inhibited, for ever."""
    srv, dev, inst, c = await _resolve_rig(tmp_path)
    try:
        assert c["operator"].server.capabilities.operations.resolve is True
        inst.powered = False
        op = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 50.0}, wait_ms=2000)).operation
        assert op.state == "unknown"
        inst.powered, inst.knows = True, False  # the device answers again but has no record of the command
        # 1. without a resolution the call only asks the device again; nothing is assumed
        asked = (await c["operator"].operations_resolve(op.operation_id)).operation
        assert asked.state == "unknown" and inst.reconcile_calls == [op.operation_id]
        # 2. the operator inspected the rotor and resolves it, stating the basis
        resolved = (await c["resolver"].operations_resolve(
            op.operation_id, state="failed", basis="rotor inspected at 14:02 by J. Doe: stationary, lid locked, run counter "
            "unchanged; treating the spin as not completed")).operation
        assert resolved.state == "failed" and resolved.effect == "unknown" and resolved.error.may_have_acted is True
        assert resolved.error.bhms_code == "DEVICE_FAULT" and "rotor inspected" in resolved.error.message
        entries = [h for h in resolved.history if h.kind in ("state", "reconciliation")]
        assert [(h.kind, h.state) for h in entries[-2:]] == [("state", "unknown"), ("reconciliation", "failed")]
        mark = entries[-1].operator
        assert mark.principal == "resolver" and mark.basis.startswith("rotor inspected at 14:02")
        assert "operator" in entries[-1].detail and all(h.operator is None for h in entries[:-1])
        # 3. the resource is usable again, and the resolution is an audited event
        again = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 1.0}, wait_ms=2000)).operation
        assert again.state == "completed"
        events = (await c["operator"].events_read(types=["operation.resolved"])).events
        assert len(events) == 1 and events[0].operation_id == op.operation_id and events[0].severity == "warning"
        assert events[0].data == {"state": "failed", "principal": "resolver", "source": "operator"}
        # 4. resolving again changes nothing and records nothing (it is no longer unknown)
        same = (await c["operator"].operations_resolve(op.operation_id, state="completed", basis="second opinion",
                                                       result={"speed": 50.0})).operation
        assert same.state == "failed" and len(same.history) == len(resolved.history)
    finally:
        await _close(srv, c)


async def test_device_evidence_wins_over_the_operator(tmp_path):
    srv, dev, inst, c = await _resolve_rig(tmp_path)
    try:
        inst.powered = False
        op = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 50.0}, wait_ms=2000)).operation
        inst.powered = True  # the device now knows: it finished the command
        resolved = (await c["operator"].operations_resolve(op.operation_id, state="failed", basis="I think it did not run")).operation
        assert resolved.state == "completed" and resolved.result == {"speed": 50.0}
        last = [h for h in resolved.history if h.kind == "reconciliation"][-1]
        assert last.operator is None and "device evidence" in last.detail
        assert (await c["operator"].events_read(types=["operation.resolved"])).events[0].data["source"] == "device"
    finally:
        await _close(srv, c)


async def test_who_may_resolve_and_what_a_resolution_must_say(tmp_path):
    srv, dev, inst, c = await _resolve_rig(tmp_path)
    try:
        inst.powered = False
        op = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 50.0}, wait_ms=2000)).operation
        inst.powered, inst.knows = True, False

        async def refused(client, code, **kw):
            with pytest.raises(BhmsError) as exc:
                await c[client].operations_resolve(op.operation_id, **kw)
            assert exc.value.bhms_code == code and exc.value.may_have_acted is False, exc.value
            return exc.value

        basis = {"basis": "inspected"}
        assert "operations:resolve" in (await refused("agent", "UNAUTHORIZED", state="failed", **basis)).hint   # the owner
        assert "operations:resolve" in (await refused("auditor", "UNAUTHORIZED")).hint                           # read-only
        assert (await refused("resolver", "INVALID_ARGUMENT", state="failed")).field == "resolution.basis"       # no basis
        assert (await refused("resolver", "INVALID_ARGUMENT", state="running", **basis)).field == "resolution.state"
        # completed needs a result the action's output accepts; verified needs measured, valid observations
        assert (await refused("resolver", "INVALID_ARGUMENT", state="completed", **basis)).field == "resolution.result"
        assert (await refused("resolver", "OUT_OF_RANGE", state="completed", result={"speed": 500.0}, **basis)).field \
            == "resolution.result.speed"
        # an operator cannot attest a verified effect (R38): refused by the schema, nothing recorded
        assert (await refused("resolver", "INVALID_ARGUMENT", state="completed", result={"speed": 50.0}, effect="verified",
                              **basis)).field == "resolution.effect"
        # "nothing happened" is a claim of proof: it must come with effect none
        claim = await refused("resolver", "INVALID_ARGUMENT", state="failed", may_have_acted=False, effect="unverified", **basis)
        assert claim.field == "resolution.effect" and "effect none" in claim.message
        # Ruling R45: the most specific member wins (the member at fault, not the resolution object)
        assert (await refused("resolver", "INVALID_ARGUMENT", state="failed", may_have_acted=False, **basis)).field \
            == "resolution.effect"
        assert (await refused("resolver", "INVALID_ARGUMENT", state="failed", effect="none", **basis)).field \
            == "resolution.mayHaveActed"
        assert (await refused("resolver", "INVALID_ARGUMENT", state="failed", result={"speed": 50.0}, **basis)).field \
            == "resolution.result"
        assert (await refused("resolver", "INVALID_ARGUMENT", state="completed", may_have_acted=True, result={"speed": 50.0},
                              **basis)).field == "resolution.mayHaveActed"
        with pytest.raises(BhmsError) as exc:
            await c["resolver"].operations_resolve("op-does-not-exist", state="failed", **basis)
        assert exc.value.bhms_code == "INVALID_ARGUMENT" and exc.value.field == "operationId"
        still = (await c["operator"].operations_get(op.operation_id)).operation
        assert still.state == "unknown" and not [h for h in still.history if h.kind == "reconciliation"]
        # a completed resolution with a valid result; the effect is unverified (an operator's report is not a measurement)
        done = (await c["resolver"].operations_resolve(op.operation_id, state="completed", result={"speed": 50.0},
                                                       basis="run log of the instrument's own display shows run 118 at 50 rev/s")).operation
        assert done.state == "completed" and done.effect == "unverified" and done.result == {"speed": 50.0}
        assert done.evidence.kind == "reported" and done.evidence.observations is None  # a report, never a measurement
        # a proven non-execution: effect none, mayHaveActed false
        inst.powered = False
        second = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 7.0}, wait_ms=2000)).operation
        inst.powered = True
        never = (await c["operator"].operations_resolve(second.operation_id, state="failed", may_have_acted=False, effect="none",
                                                        basis="the instrument was unplugged the whole time (photo in ticket 4411)")).operation
        assert never.state == "failed" and never.effect == "none" and never.error.may_have_acted is False
    finally:
        await _close(srv, c)


async def test_typed_in_observations_cannot_make_an_operator_resolution_verified(tmp_path):
    """Fix round 1 (R38): an admin resolve with effect "verified" and invented observations stamped the operation
    verified with measured evidence. An operator resolution is at most unverified, with evidence kind reported."""
    srv, dev, inst, c = await _resolve_rig(tmp_path)
    try:
        inst.powered = False
        op = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 50.0}, wait_ms=2000)).operation
        inst.powered, inst.knows = True, False
        invented = {"speed": {"value": 50.0, "unit": "{rev}/s", "quality": "valid", "evidence": "measured", "sequence": 7,
                              "epoch": "made-up", "acquiredAt": "2026-11-14T10:00:00.000Z", "ageMs": 0}}
        for extra in ({"effect": "verified"}, {"observations": invented}, {"effect": "verified", "observations": invented}):
            with pytest.raises(BhmsError) as exc:
                await c["operator"].request("operations/resolve", {"operationId": op.operation_id, "resolution": {
                    "state": "completed", "basis": "typed in", "result": {"speed": 50.0}, **extra}})
            assert exc.value.bhms_code == "INVALID_ARGUMENT"
        still = (await c["operator"].operations_get(op.operation_id)).operation
        assert still.state == "unknown" and still.effect == "unknown" and still.evidence is None
        done = (await c["operator"].operations_resolve(op.operation_id, state="completed", basis="display shows run 118",
                                                       result={"speed": 50.0}, effect="unverified")).operation
        assert (done.state, done.effect, done.evidence.kind, done.evidence.observations) == ("completed", "unverified",
                                                                                             "reported", None)
        # an operation that required a verified effect cannot be completed by an operator at all
        inst.powered = False
        strict = (await c["agent"].request("actions/invoke", {"deviceId": "spin-1", "action": "checked_spin",
                                                              "arguments": {"speed": 5.0}, "require": {"effect": "verified"},
                                                              "waitMs": 2000}))["operation"]
        inst.powered = True
        with pytest.raises(BhmsError) as exc:
            await c["operator"].operations_resolve(strict["operationId"], state="completed", basis="x", result={"speed": 5.0})
        assert exc.value.field == "resolution.state" and "verified" in exc.value.message
    finally:
        await _close(srv, c)


async def test_verified_comes_only_from_the_device_during_a_resolve(tmp_path):
    """The device-first path: when the device itself supplies measured evidence, the resolve records verified/measured,
    and the operator's statement (given in the same call) is not used."""
    srv, dev, inst, c = await _resolve_rig(tmp_path)
    try:
        inst.powered = False
        op = (await c["agent"].actions_invoke("spin-1", "spin", {"speed": 50.0}, wait_ms=2000)).operation
        inst.powered = True

        @dev.reconcile
        async def measured(found):
            reading = await srv.observations.read(dev, "speed", fresh=True, internal=True)
            return Reconciled("completed", evidence="tachometer read back", result={"speed": reading["value"]},
                              effect="verified", observations={"speed": reading})

        done = (await c["operator"].operations_resolve(op.operation_id, state="failed", basis="I think it did not run")).operation
        assert (done.state, done.effect, done.evidence.kind) == ("completed", "verified", "measured")
        assert done.evidence.observations["speed"].evidence == "measured" and done.result == {"speed": 50.0}
        assert [h for h in done.history if h.kind == "reconciliation"][-1].operator is None
    finally:
        await _close(srv, c)


async def test_resolve_is_not_on_the_agent_surface():
    from bhms.bridges import tool_definitions
    from bhms.protocol import schema

    text = str([(t.name, t.description, t.input_schema) for t in tool_definitions()])
    assert "resolve" not in text.replace("resolved", "")
    assert not [name for name in schema.load_schema()["x-bhms-agent-tools"] if "resolve" in name]
