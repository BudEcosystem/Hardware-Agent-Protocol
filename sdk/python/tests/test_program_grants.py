"""Program-scoped grants (spec/bhms/08-programs.md BHMS-PRG-023, amending BHMS-PRG-006; Ruling R51).

A grant ``programs:run:<digest>`` authorizes exactly the reviewed program's steps, without raw ``invoke`` scope on them,
so a program can be an agent's safety boundary (Ruling R46: in v0.1 running a program needed ``invoke`` on every step,
which let the agent call the action directly too). Leases, envelopes, budgets and hazard rules still apply to each step.
"""

from __future__ import annotations

import os

import pytest

from bhms.client.client import Client
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy
from bhms.runtime.programs import program_step_scopes
from bhms.server import DeviceServer, Range

UID = os.getuid()


def program(volume: float = 50, name: str = "dose") -> dict:
    return {"bhmsProgram": "2026-11-15", "name": name, "description": "One reviewed dose.", "maxDurationMs": 10_000,
            "input": {"type": "object", "additionalProperties": False, "properties": {}},
            "steps": [{"kind": "invoke", "deviceId": "pump-1", "action": "dispense", "arguments": {"volume": volume}},
                      {"kind": "read", "deviceId": "pump-1", "property": "dispensed", "saveAs": "d"}],
            "output": {"dispensed": "${d.value}"}}


SPIN = {"bhmsProgram": "2026-11-15", "name": "spin", "description": "A reviewed spin.", "maxDurationMs": 10_000,
        "input": {"type": "object", "additionalProperties": False, "properties": {}},
        "steps": [{"kind": "invoke", "deviceId": "pump-1", "action": "flush", "arguments": {}}]}


class Pump:
    calls = 0
    dispensed = 0.0
    flushes = 0


@pytest.fixture
async def env(tmp_path):
    pump = Pump()
    grants = [f"programs:run:{digest(program())}", f"programs:run:{digest(SPIN)}"]
    policy = Policy({
        "agent": {"uids": [UID], "scopes": ["read", "lease", *grants],
                  "bounds": {"pump-1/dispense": {"volume": {"maximum": 100}}},
                  "budgets": [{"id": "vol", "action": "pump-1/dispense", "quantity": "/volume", "unit": "uL",
                               "total": 120}]},
        "admin": {"tokens": ["sha256:" + "0" * 64], "scopes": ["admin"]}}, trust_same_uid=False)
    srv = DeviceServer("grants", state_dir=tmp_path / "state", policy=policy)
    dev = srv.device("pump-1", name="Pump", description="Syringe pump.", resources=["pump-1/plunger"])
    dev.report_alive()

    @dev.property(unit="uL", evidence="measured")
    def dispensed() -> float:
        return pump.dispensed

    @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=5000)
    async def dispense(ctx, volume: Range(1, 500, unit="uL")) -> None:  # noqa: F821
        """Dispense."""
        pump.calls += 1
        pump.dispensed += volume

    @dev.action(effect="hazardous", idempotency="relative", max_duration_ms=5000, requires_lease=True)
    async def flush(ctx) -> None:
        """Flush the line at full pressure."""
        pump.flushes += 1

    path = tmp_path / "s.sock"
    listener = await srv.listen(f"unix:{path}")
    client = await Client.connect(f"unix:{path}")
    yield srv, pump, client
    await client.close()
    await listener.close()
    await srv.close()


async def refused(coro) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        await coro
    return info.value


async def test_a_grant_runs_exactly_the_reviewed_program(env):  # BHMS-PRG-023
    srv, pump, client = env
    op = (await client.programs_run(program=program(), arguments={}, operation_key="grant-ok", wait_ms=5000)).operation
    assert op.state == "completed" and op.result == {"dispensed": 50} and pump.calls == 1
    # by digest, once registered by someone allowed to register (registration grants nothing, BHMS-PRG-021)
    admin = next(p for p in srv.policy.principals if p.id == "admin")
    await srv.programs.register(admin, program())
    op = (await client.programs_run(digest=digest(program()), arguments={}, operation_key="by-digest",
                                    wait_ms=5000)).operation
    assert op.state == "completed" and pump.calls == 2


async def test_the_grant_is_not_a_scope_on_the_steps(env):  # BHMS-PRG-023 (no bypass)
    srv, pump, client = env
    exc = await refused(client.actions_invoke("pump-1", "dispense", {"volume": 10}, operation_key="raw"))
    assert exc.bhms_code == "UNAUTHORIZED" and "invoke:pump-1/dispense" in exc.hint
    changed = program(volume=60)
    exc = await refused(client.programs_run(program=changed, arguments={}, operation_key="changed"))
    assert exc.bhms_code == "UNAUTHORIZED" and f"programs:run:{digest(changed)}" in exc.hint
    renamed = program(name="dose_again")  # the same steps under another name: another digest, not reviewed
    assert (await refused(client.programs_run(program=renamed, arguments={}, operation_key="renamed"))).bhms_code == \
        "UNAUTHORIZED"
    assert pump.calls == 0 and srv.journal.lookup_key("agent", "changed") is None


async def test_leases_bounds_and_budgets_still_apply(env):  # BHMS-PRG-023 with PRG-005/006, AUTH-010, AUTH-032, DEV-033
    srv, pump, client = env
    exc = await refused(client.programs_run(program=SPIN, arguments={}, operation_key="spin-1"))
    assert exc.bhms_code == "LEASE_REQUIRED"  # a hazardous step still needs its lease
    lease = (await client.leases_acquire(["pump-1/plunger"], 10_000)).lease
    op = (await client.programs_run(program=SPIN, arguments={}, operation_key="spin-2", lease_id=lease.lease_id,
                                    wait_ms=5000)).operation
    assert op.state == "completed" and pump.flushes == 1  # the literal step name satisfies BHMS-AUTH-003
    await client.leases_release(lease.lease_id)
    await client.programs_run(program=program(), arguments={}, operation_key="b-1", wait_ms=5000)
    await client.programs_run(program=program(), arguments={}, operation_key="b-2", wait_ms=5000)
    third = (await client.programs_run(program=program(), arguments={}, operation_key="b-3", wait_ms=5000)).operation
    assert third.state == "failed" and third.error.bhms_code == "OUT_OF_RANGE" and pump.calls == 2  # 120 uL budget


async def test_policy_bounds_narrow_a_granted_program(tmp_path):  # BHMS-AUTH-010 inside a granted run
    big = program(volume=200)  # inside the device's 500 uL, outside the agent's 100 uL policy bound
    policy = Policy({"agent": {"uids": [UID], "scopes": ["read", f"programs:run:{digest(big)}"],
                               "bounds": {"pump-1/dispense": {"volume": {"maximum": 100}}}}}, trust_same_uid=False)
    srv = DeviceServer("grants-bounds", state_dir=tmp_path / "state", policy=policy)
    dev = srv.device("pump-1", name="Pump", description="Syringe pump.", resources=["pump-1/plunger"])
    dev.report_alive()

    @dev.property(unit="uL", evidence="measured")
    def dispensed() -> float:
        return 0.0

    @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=5000)
    async def dispense(ctx, volume: Range(1, 500, unit="uL")) -> None:  # noqa: F821
        """Dispense."""

    path = tmp_path / "b.sock"
    listener = await srv.listen(f"unix:{path}")
    client = await Client.connect(f"unix:{path}")
    try:
        exc = await refused(client.programs_run(program=big, arguments={}, operation_key="big"))
        assert exc.bhms_code == "OUT_OF_RANGE" and exc.field.startswith("program.steps[0].arguments")
    finally:
        await client.close()
        await listener.close()
        await srv.close()


def test_the_grant_names_exactly_the_literal_steps():
    nested = {"steps": [{"kind": "repeat", "times": 2, "steps": [
        {"kind": "invoke", "deviceId": "a", "action": "go", "arguments": {}},
        {"kind": "waitUntil", "deviceId": "b", "property": "level", "predicate": {}, "timeoutMs": 10}]},
        {"kind": "sleep", "durationMs": 1}, {"kind": "invoke", "deviceId": "a", "action": "go", "arguments": {}}]}
    assert program_step_scopes(nested) == ("invoke:a/go", "invoke:b/level")
