"""Modbus TCP adapter against a real pymodbus 3.8.6 slave serving the thermal block's registers."""

import pymodbus
import pytest
from bhms.protocol.errors import BhmsError

from contract import check_description, check_observations
from serving import read, run, serving
from simlab.adapters import modbus as modbus_adapter
from simlab.faults import At, Fault
from simlab.instruments.modbus_thermal import ModbusThermalInstrument
from simlab.oracle import Claim, Oracle, Verdict
from simlab.profiles import THERMAL_MODBUS
from simlab.scene import BENCH
from simlab.twins.thermal import ThermalModel
from simlab.world import World


@pytest.fixture
async def rig(tmp_path):
    w = World(BENCH, seed=2, attach_arm=False)
    model = ThermalModel(w, device="thermal-m1")
    instrument = ModbusThermalInstrument(w, model, device="thermal-m1")
    port = await instrument.start()
    srv, link = modbus_adapter.build_server(w, THERMAL_MODBUS, "127.0.0.1", port, state_dir=tmp_path / "mb")
    try:
        async with serving(srv, tmp_path) as client:
            yield client, srv, model, w, instrument
    finally:
        await link.close()
        await instrument.stop()


def test_pymodbus_is_pinned():
    assert pymodbus.__version__ == "3.8.6"


async def test_contract(rig):
    client, srv, model, w, instrument = rig
    desc = await check_description(client, "thermal-m1", measured_ok={"temperature"})
    await check_observations(client, "thermal-m1", desc)
    assert desc["properties"]["setpoint"]["evidence"] == "reported"
    assert all(a["completionEvidence"] == "reported" for a in desc["actions"].values())  # no measured read-back exists
    assert desc["actions"]["set_setpoint"]["input"]["properties"]["value"]["x-bhms-unit"] == "Cel"


async def test_set_and_heat_through_modbus(rig):
    client, srv, model, w, instrument = rig
    op = await run(client, "thermal-m1", "set_setpoint", {"value": 45.0})
    assert op.state == "completed", op.error
    assert op.effect == "unverified" and op.result["value"] == 45.0
    assert model.setpoint_c == 45.0  # the instrument really received it
    assert (await run(client, "thermal-m1", "set_enabled", {"value": True})).state == "completed"
    w.step(250.0)
    temp = await read(client, "thermal-m1", "temperature")
    assert temp.evidence == "measured" and abs(temp.value - 45.0) < 0.5
    status = (await read(client, "thermal-m1", "status")).value
    assert int(status) & 1 and int(status) & 2


async def test_same_key_twice_is_one_register_write(rig):
    client, srv, model, w, instrument = rig
    first = await run(client, "thermal-m1", "set_setpoint", {"value": 30.0}, key="k1")
    model.command(31.0, False, None)  # something else changes the setpoint meanwhile
    second = await run(client, "thermal-m1", "set_setpoint", {"value": 30.0}, key="k1")
    assert first.operation_id == second.operation_id and model.setpoint_c == 31.0  # not written again


async def test_sdk_bounds_stop_an_unsafe_setpoint_before_any_modbus_traffic(rig):
    client, srv, model, w, instrument = rig
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as err:
        await client.actions_invoke("thermal-m1", "set_setpoint", {"value": 150.0})
    assert err.value.bhms_code == "OUT_OF_RANGE"
    assert not [e for e in w.effect_log() if e.kind == "thermal_command"]


async def test_a_disconnected_thermistor_reads_invalid_not_a_number(rig):
    client, srv, model, w, instrument = rig
    w.faults.inject(Fault("thermal-m1", "sensor_disconnect", At(0.0)))
    w.step(0.01)
    obs = await read(client, "thermal-m1", "temperature")
    assert obs.quality == "invalid" and obs.value is None


async def test_power_loss_is_unknown_and_reconciles_only_on_evidence(rig):
    client, srv, model, w, instrument = rig
    fault = w.faults.inject(Fault("thermal-m1", "power_loss", At(0.0)))
    w.step(0.01)
    assert (await read(client, "thermal-m1", "temperature")).quality == "invalid"
    op = await run(client, "thermal-m1", "set_setpoint", {"value": 50.0})
    assert op.state == "unknown"  # the unit answered with a device failure: it may or may not have acted
    w.faults.clear(fault)
    await srv.reconcile("thermal-m1")
    settled = (await client.operations_get(op.operation_id)).operation
    # the setpoint never reached the model, so read-back cannot prove completion: it stays unknown, honestly
    assert settled.state == "unknown" and model.setpoint_c != 50.0
    verdict = Oracle(w).judge(Claim(op.operation_id, "outcome_unknown", "unverified", lambda s: True))
    assert verdict is Verdict.HONEST_UNKNOWN
    # the unresolved operation keeps the registers inhibited: new work is refused, not queued behind a guess
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as refused:
        await client.actions_invoke("thermal-m1", "set_setpoint", {"value": 50.0})
    assert refused.value.bhms_code == "STALE"


async def test_unreachable_instrument_fails_with_proof_of_no_effect(tmp_path):
    w = World(BENCH, seed=2, attach_arm=False)
    srv, link = modbus_adapter.build_server(w, THERMAL_MODBUS, "127.0.0.1", 1, state_dir=tmp_path / "x", timeout_s=0.3)
    async with serving(srv, tmp_path) as client:
        # the liveness probe failed when the server started: the device is offline and nothing is sent (BHMS-DEV-012)
        assert (await client.devices_list()).devices[0].status == "offline"
        with pytest.raises(BhmsError) as refused:
            await run(client, "thermal-m1", "set_setpoint", {"value": 40.0})
        assert refused.value.bhms_code == "DEVICE_UNAVAILABLE" and refused.value.may_have_acted is False
        # the adapter's own proof, for a link that drops between the probe and the command
        srv.devices["thermal-m1"].report_alive()
        op = await run(client, "thermal-m1", "set_setpoint", {"value": 40.0})
        assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False
        assert (await read(client, "thermal-m1", "temperature")).quality == "invalid"
    await link.close()
