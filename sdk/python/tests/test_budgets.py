"""Cumulative budgets of grants (spec/bhms/07-leases-and-authority.md 7.4.1, BHMS-AUTH-030..035; Ruling R50).

Evidence that caused them: Task 14 live run, gpt-5.4-mini asked for 600 uL against a 500 uL per-call bound dispensed 500 uL
and then 100 uL: each call honest and in bounds, the total over what the task allowed.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError
from bhms.protocol.version import V0_1
from bhms.runtime.authority import Policy
from bhms.runtime.budgets import Budget, proves_no_effect
from bhms.server import DeviceFault, DeviceServer, Range

UID = os.getuid()


class Pump:
    def __init__(self) -> None:
        self.dispensed = 0.0
        self.calls = 0
        self.mode = "ok"  # ok | refuse (provably nothing) | crash (outcome unknown)


def pump_server(state_dir, budgets: list[dict], *, scopes=None, extra_devices: bool = False) -> tuple[DeviceServer, Pump]:
    pump = Pump()
    policy = Policy({"agent": {"uids": [UID], "scopes": scopes or ["read", "lease", "invoke:*/*", "programs:run"],
                               "budgets": budgets}}, trust_same_uid=False)
    srv = DeviceServer("budget-test", state_dir=state_dir, policy=policy)
    names = ("pump-1", "pump-2") if extra_devices else ("pump-1",)
    for name in names:
        dev = srv.device(name, name=name, description="Syringe pump.", capabilities=["bhms.liquid.dispense"],
                         resources=[f"{name}/plunger"])
        dev.report_alive()

        @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=5000)
        async def dispense(ctx, volume: Range(1, 500, unit="uL", step=0.1)) -> {"dispensed": "uL"}:  # noqa: F821
            """Dispense a volume."""
            pump.calls += 1
            if pump.mode == "refuse":
                raise DeviceFault("syringe empty", proof="the pump refused before moving", effect="none")
            if pump.mode == "crash":
                raise ValueError("driver crashed after the plunger moved")
            pump.dispensed += volume
            return {"dispensed": volume}

    return srv, pump


@pytest.fixture
async def served(tmp_path):
    made = []

    async def make(budgets, *, state=None, **kw):
        srv, pump = pump_server(state or tmp_path / "state", budgets, **kw)
        path = tmp_path / f"s{len(made)}.sock"
        listener = await srv.listen(f"unix:{path}")
        client = await Client.connect(f"unix:{path}")
        made.append((srv, listener, client))
        return srv, pump, client, f"unix:{path}"

    yield make
    for srv, listener, client in made:
        await client.close()
        await listener.close()
        await srv.close()


VOLUME = {"id": "pump-volume", "action": "pump-*/dispense", "quantity": "/volume", "unit": "uL", "total": 500}


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_a_total_is_never_exceeded_and_the_refusal_says_what_remains(served):  # BHMS-AUTH-032
    srv, pump, client, _ = await served([VOLUME])
    first = (await client.actions_invoke("pump-1", "dispense", {"volume": 400}, operation_key="ok-1",
                                         wait_ms=2000)).operation
    assert first.state == "completed"
    exc = await refused(client.actions_invoke("pump-1", "dispense", {"volume": 200}, operation_key="b-2", wait_ms=2000))
    assert exc.bhms_code == "OUT_OF_RANGE" and exc.field == "arguments.volume" and exc.may_have_acted is False
    assert exc.bound["maximum"] == 100 and exc.bound["budget"]["id"] == "pump-volume"
    assert exc.bound["budget"]["remaining"] == 100 and exc.bound["budget"]["total"] == 500
    assert "100" in exc.hint and "pump-volume" in exc.message
    assert pump.calls == 1 and pump.dispensed == 400  # never a partial dispatch
    assert srv.journal.lookup_key("agent", "b-2") is None  # a refusal creates no operation (BHMS-OPS-040)
    last = (await client.actions_invoke("pump-1", "dispense", {"volume": 100}, operation_key="b-3", wait_ms=2000)).operation
    assert last.state == "completed" and pump.dispensed == 500
    assert (await refused(client.actions_invoke("pump-1", "dispense", {"volume": 1}, operation_key="b-4"))).bound[
        "maximum"] == 0


async def test_a_replay_is_not_charged_twice(served):  # BHMS-OPS-030 before BHMS-AUTH-032
    _, pump, client, _ = await served([VOLUME])
    for _ in range(3):
        await client.actions_invoke("pump-1", "dispense", {"volume": 300}, operation_key="same", wait_ms=2000)
    assert pump.calls == 1
    assert (await client.discover()).principal.budgets[0].remaining == 200


async def test_concurrent_admissions_never_spend_the_same_remainder(served):  # BHMS-AUTH-031 (atomic with admission)
    _, pump, client, _ = await served([VOLUME])
    results = await asyncio.gather(*(client.actions_invoke("pump-1", "dispense", {"volume": 100}, operation_key=f"c-{i}",
                                                           wait_ms=2000) for i in range(12)), return_exceptions=True)
    ok = [r for r in results if not isinstance(r, BaseException)]
    bad = [r for r in results if isinstance(r, BhmsError)]
    assert len(ok) == 5 and len(bad) == 7 and all(e.bhms_code == "OUT_OF_RANGE" for e in bad)
    assert pump.calls == 5 and pump.dispensed == 500


async def test_only_proof_of_no_effect_gives_a_reservation_back(served):  # BHMS-AUTH-033
    srv, pump, client, _ = await served([VOLUME])
    pump.mode = "refuse"  # failed, mayHaveActed false: released
    op = (await client.actions_invoke("pump-1", "dispense", {"volume": 300}, operation_key="r-1", wait_ms=2000)).operation
    assert op.state == "failed" and op.error.may_have_acted is False
    assert (await client.discover()).principal.budgets[0].remaining == 500
    pump.mode = "crash"  # unknown: consumed
    op = (await client.actions_invoke("pump-1", "dispense", {"volume": 300}, operation_key="r-2", wait_ms=2000)).operation
    assert op.state == "unknown"
    assert (await client.discover()).principal.budgets[0].remaining == 200
    srv.executor.lift_inhibition(srv.journal.get(op.operation_id))  # (the unknown op would also inhibit the plunger)
    pump.mode = "ok"
    exc = await refused(client.actions_invoke("pump-1", "dispense", {"volume": 250}, operation_key="r-3"))
    assert exc.bound["maximum"] == 200


async def test_budgets_survive_a_restart(served, tmp_path):  # BHMS-AUTH-034
    srv, _, client, _ = await served([VOLUME], state=tmp_path / "durable")
    await client.actions_invoke("pump-1", "dispense", {"volume": 450}, operation_key="k-1", wait_ms=2000)
    await client.close()
    await srv.close()
    srv2, pump2, client2, _ = await served([VOLUME], state=tmp_path / "durable")
    assert (await client2.discover()).principal.budgets[0].remaining == 50
    exc = await refused(client2.actions_invoke("pump-1", "dispense", {"volume": 60}, operation_key="k-2"))
    assert exc.bound["maximum"] == 50 and pump2.calls == 0


async def test_a_window_frees_what_left_it(served):  # BHMS-AUTH-030 (windowMs)
    windowed = {**VOLUME, "total": 100, "windowMs": 1000}
    _, _, client, _ = await served([windowed])
    await client.actions_invoke("pump-1", "dispense", {"volume": 100}, operation_key="w-1", wait_ms=2000)
    exc = await refused(client.actions_invoke("pump-1", "dispense", {"volume": 10}, operation_key="w-2"))
    assert exc.bound["budget"]["remaining"] == 0 and "resetsAt" in exc.bound["budget"]
    await asyncio.sleep(1.1)
    assert (await client.actions_invoke("pump-1", "dispense", {"volume": 10}, operation_key="w-3",
                                        wait_ms=2000)).operation.state == "completed"


async def test_the_budget_unit_converts_and_one_pattern_spans_devices(served):  # BHMS-AUTH-030
    millilitres = {**VOLUME, "unit": "mL", "total": 0.5}
    _, pump, client, _ = await served([millilitres], extra_devices=True)
    await client.actions_invoke("pump-1", "dispense", {"volume": 300}, operation_key="m-1", wait_ms=2000)
    exc = await refused(client.actions_invoke("pump-2", "dispense", {"volume": 300}, operation_key="m-2"))
    assert exc.bound["maximum"] == 200 and exc.bound["budget"]["remaining"] == 0.2
    await client.actions_invoke("pump-2", "dispense", {"volume": 200}, operation_key="m-3", wait_ms=2000)
    assert pump.dispensed == 500


async def test_discover_shows_budgets_to_v0_2_requests_only(served):  # BHMS-AUTH-035, BHMS-LIF-026
    _, _, client, url = await served([VOLUME])
    found = await client.discover()
    assert found.capabilities.authority.budgets is True and found.principal.budgets[0].remaining == 500
    old = await Client.connect(url)
    old.version = V0_1
    try:
        legacy = await old.discover()
        assert legacy.principal.budgets is None and legacy.capabilities.authority.budgets is None
        assert legacy.capabilities.programs.grants is None
        await old.actions_invoke("pump-1", "dispense", {"volume": 400}, operation_key="v-1", wait_ms=2000)
        exc = await refused(old.actions_invoke("pump-1", "dispense", {"volume": 200}, operation_key="v-2"))
        assert exc.bhms_code == "OUT_OF_RANGE"  # a v0.1 peer is held to the same budget (only what it is shown differs)
    finally:
        await old.close()


async def test_a_budget_that_cannot_measure_its_action_is_refused_at_start(tmp_path):  # BHMS-AUTH-031
    for bad in ({**VOLUME, "quantity": "/rate"}, {**VOLUME, "unit": "s"}):
        srv, _ = pump_server(tmp_path / bad["unit"], [bad])
        with pytest.raises(ValueError, match="BHMS-AUTH-031"):
            await srv.start()


async def test_program_steps_are_charged(served):  # BHMS-AUTH-032 inside programs (BHMS-PRG-005)
    srv, pump, client, _ = await served([VOLUME])
    program = {"bhmsProgram": "2026-11-15", "name": "two_doses", "description": "Two doses.", "maxDurationMs": 20_000,
               "input": {"type": "object", "additionalProperties": False, "properties": {}},
               "steps": [{"kind": "invoke", "deviceId": "pump-1", "action": "dispense", "arguments": {"volume": 300}},
                         {"kind": "invoke", "deviceId": "pump-1", "action": "dispense", "arguments": {"volume": 300}}]}
    op = (await client.programs_run(program=program, arguments={}, operation_key="p-1", wait_ms=5000)).operation
    assert op.state == "failed" and op.error.bhms_code == "OUT_OF_RANGE" and "budget" in op.error.message
    assert pump.calls == 1 and pump.dispensed == 300


def test_what_proves_no_effect():
    assert proves_no_effect({"state": "rejected"})
    assert proves_no_effect({"state": "failed", "error": {"mayHaveActed": False}})
    assert not proves_no_effect({"state": "failed", "error": {"mayHaveActed": True}})
    assert proves_no_effect({"state": "canceled", "effect": "none"})
    assert not proves_no_effect({"state": "canceled", "effect": "unverified"})
    assert not proves_no_effect({"state": "unknown", "error": {"mayHaveActed": True}})
    assert not proves_no_effect({"state": "completed"})


def test_budget_wire_round_trip_and_pattern():
    budget = Budget.from_wire({**VOLUME, "windowMs": 3_600_000})
    assert budget.wire() == {**VOLUME, "total": 500.0, "windowMs": 3_600_000}
    assert budget.matches("pump-7", "dispense") and not budget.matches("pump-7", "aspirate")
    assert budget.field() == "arguments.volume"
    with pytest.raises(ValueError):
        Budget.from_wire({**VOLUME, "unit": "rpm"})
