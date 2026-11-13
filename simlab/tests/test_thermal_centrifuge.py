"""Thermal block and centrifuge twins: first-order physics, interlock and imbalance refusals, BHMS servers."""

import asyncio
import math

import pytest

from contract import check_description, check_observations
from serving import read, run, serving
from simlab.oracle import Claim, Oracle, Verdict
from simlab.scene import BENCH
from simlab.twins import centrifuge as fuge_twin
from simlab.twins import thermal as thermal_twin
from simlab.world import World


def world(seed=1):
    return World(BENCH, seed=seed, attach_arm=False)


# ------------------------------------------------------------------------------------------------ thermal


def test_first_order_response_matches_the_closed_form():
    w = world()
    block = thermal_twin.ThermalModel(w)
    block.command(60.0, True, cause="c")
    for seconds in (10.0, 40.0, 120.0):
        w2 = world()
        b2 = thermal_twin.ThermalModel(w2)
        b2.command(60.0, True, cause="c")
        w2.step(seconds)
        expected = 60.0 + (22.0 - 60.0) * math.exp(-seconds / thermal_twin.TAU_S)
        assert b2.temperature_c() == pytest.approx(expected, abs=0.01)
    w.step(40.0)
    assert w.time_s == pytest.approx(40.0)
    assert block.temperature_c() == pytest.approx(60.0 - 38.0 * math.exp(-1), abs=0.01)  # 63 % of the way in one tau


def test_cooling_to_ambient_and_the_setpoint_bound():
    w = world()
    block = thermal_twin.ThermalModel(w)
    block.command(80.0, True, cause="c")
    w.step(200.0)
    hot = block.temperature_c()
    block.command(None, False, cause="off")
    w.step(thermal_twin.TAU_S)
    assert 22.0 < block.temperature_c() < hot
    with pytest.raises(ValueError):
        block.command(120.0, True, cause="too hot")


@pytest.fixture
async def thermal(tmp_path):
    w = world()
    srv, model = thermal_twin.build_server(w, state_dir=tmp_path / "th")
    async with serving(srv, tmp_path) as client:
        yield client, srv, model, w


async def test_thermal_contract_and_set_temperature(thermal):
    client, srv, model, w = thermal
    desc = await check_description(client, "thermal-1", measured_ok={"temperature"})
    await check_observations(client, "thermal-1", desc)
    op = await run(client, "thermal-1", "set_temperature", {"target": 37.0, "tolerance": 0.5}, wait_ms=60_000)
    assert op.state == "completed" and op.effect == "verified" and abs(op.result["temperature"] - 37.0) <= 0.5
    assert abs(model.temperature_c() - 37.0) < 0.5
    claim = Claim(op.operation_id, "completed", "verified", lambda s: abs(model.temperature_c() - 37.0) <= 0.5)
    assert Oracle(w).judge(claim) is Verdict.CONSISTENT


async def test_thermal_bounds_are_enforced_before_the_device(thermal):
    client, srv, model, w = thermal
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as err:
        await client.actions_invoke("thermal-1", "set_temperature", {"target": 150.0})
    assert err.value.code == "OUT_OF_RANGE"
    assert not model.enabled


async def test_stop_switches_the_heater_off(thermal):
    client, srv, model, w = thermal
    await run(client, "thermal-1", "set_temperature", {"target": 50.0}, wait_ms=60_000)
    await client.stop("test", device_ids=["thermal-1"], wait_ms=2000)
    assert not model.enabled


# ------------------------------------------------------------------------------------------------ centrifuge


def load_tubes(w, positions, volume_ul=1000.0):
    for n in positions:
        w.ledger.add_container(f"tube{n}", "tube", {"a": (volume_ul, {})}, fuge_twin.rotor_site(n), max_volume_ul=2000.0)


def test_spin_profile_ramps_holds_and_brakes():
    w = world()
    load_tubes(w, (1, 5))
    fuge = fuge_twin.CentrifugeModel(w)
    total = fuge.start(100.0, 20.0, cause="s")
    assert total == pytest.approx(10.0 + 20.0 + 12.5)
    w.step(5.0)
    assert fuge.speed_hz() == pytest.approx(50.0)
    w.step(20.0)
    assert fuge.speed_hz() == pytest.approx(100.0)
    w.step(10.0)
    assert 0 < fuge.speed_hz() < 100.0 and fuge.lid_locked()
    w.step(10.0)
    assert fuge.speed_hz() == 0.0 and not fuge.lid_locked()


def test_unbalanced_rotor_is_refused_and_balanced_is_accepted():
    w = world()
    load_tubes(w, (1,))
    fuge = fuge_twin.CentrifugeModel(w)
    with pytest.raises(ValueError, match="imbalance"):
        fuge.start(50.0, 5.0, cause="bad")
    load_tubes(w, (5,), volume_ul=1500.0)  # 0.5 g heavier: inside the 1 g limit
    fuge.start(50.0, 5.0, cause="ok")
    assert [e.kind for e in w.effect_log() if e.device == "centrifuge-1"] == ["spin_started"]


def test_lid_is_locked_while_spinning_and_a_spin_needs_a_closed_lid():
    w = world()
    load_tubes(w, (1, 5))
    fuge = fuge_twin.CentrifugeModel(w)
    fuge.set_lid(True, cause="o")
    with pytest.raises(PermissionError):
        fuge.start(50.0, 5.0, cause="lid open")
    fuge.set_lid(False, cause="c")
    fuge.start(50.0, 5.0, cause="go")
    w.step(1.0)
    with pytest.raises(PermissionError, match="locked"):
        fuge.set_lid(True, cause="too early")


@pytest.fixture
async def fuge(tmp_path):
    w = world()
    load_tubes(w, (1, 5, 2, 6))
    srv, model = fuge_twin.build_server(w, state_dir=tmp_path / "cf")
    async with serving(srv, tmp_path) as client:
        yield client, srv, model, w


async def test_centrifuge_contract_and_a_full_run(fuge):
    client, srv, model, w = fuge
    desc = await check_description(client, "centrifuge-1", measured_ok={"speed", "lid_open"})
    await check_observations(client, "centrifuge-1", desc)
    assert desc["actions"]["spin"]["effect"] == "hazardous"
    spin = await run(client, "centrifuge-1", "spin", {"speed": 60.0, "duration": 30}, wait_ms=60_000)
    assert spin.state == "completed" and spin.effect == "verified" and abs(spin.result["peak_speed"] - 60.0) < 0.6
    assert model.speed_hz() < 60.0  # braking after the hold
    w.step(10.0)
    assert (await run(client, "centrifuge-1", "open_lid")).state == "completed"
    assert (await read(client, "centrifuge-1", "lid_open")).value is True


async def test_open_lid_during_a_spin_is_refused_with_proof(fuge):
    client, srv, model, w = fuge
    started = await client.actions_invoke("centrifuge-1", "spin", {"speed": 60.0, "duration": 600}, wait_ms=0)
    await asyncio.sleep(0.2)
    refused = await run(client, "centrifuge-1", "open_lid")
    assert refused.state == "failed" and refused.effect == "none" and refused.error.may_have_acted is False
    assert Oracle(w).judge(Claim(refused.operation_id, "failed", "failed", lambda s: False)) is Verdict.CONSISTENT
    await client.operations_cancel(started.operation.operation_id, reason="end of test")
    done = (await client.operations_wait(started.operation.operation_id, 20_000)).operation
    assert done.state == "canceled"
    assert model.speed_hz() < 60.0


async def test_imbalance_refusal_through_bhms(tmp_path):
    w = world()
    load_tubes(w, (1,))
    srv, model = fuge_twin.build_server(w, state_dir=tmp_path / "cf2")
    async with serving(srv, tmp_path) as client:
        op = await run(client, "centrifuge-1", "spin", {"speed": 60.0, "duration": 30})
        assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False
        assert model.speed_hz() == 0.0 and not any(e.kind == "spin_started" for e in w.effect_log())
