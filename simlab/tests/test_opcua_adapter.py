"""OPC UA adapter against a real asyncua server serving the centrifuge's state."""

import pytest

from contract import check_description, check_observations
from serving import read, run, serving
from simlab.adapters import opcua as opcua_adapter
from simlab.faults import At, Fault
from simlab.instruments.opcua_centrifuge import OpcUaCentrifugeInstrument
from simlab.oracle import Claim, Oracle, Verdict
from simlab.profiles import CENTRIFUGE_OPCUA
from simlab.scene import BENCH
from simlab.twins.centrifuge import CentrifugeModel, rotor_site
from simlab.world import World


def load(w, positions):
    for n in positions:
        w.ledger.add_container(f"tube{n}", "tube", {"a": (1000.0, {})}, rotor_site(n), max_volume_ul=2000.0)


@pytest.fixture
async def rig(tmp_path):
    w = World(BENCH, seed=4, attach_arm=False)
    load(w, (1, 5))
    model = CentrifugeModel(w, device="centrifuge-u1")
    instrument = OpcUaCentrifugeInstrument(w, model, device="centrifuge-u1")
    endpoint = await instrument.start()
    srv, link = opcua_adapter.build_server(w, CENTRIFUGE_OPCUA, endpoint, state_dir=tmp_path / "ua")
    try:
        async with serving(srv, tmp_path) as client:
            yield client, srv, model, w
    finally:
        await link.close()
        await instrument.stop()


async def test_contract(rig):
    client, srv, model, w = rig
    desc = await check_description(client, "centrifuge-u1", measured_ok={"speed", "lid_open"})
    await check_observations(client, "centrifuge-u1", desc)
    assert desc["actions"]["start_program"]["effect"] == "hazardous" and desc["actions"]["start_program"]["requiresLease"] is True
    assert all(a["completionEvidence"] == "reported" for a in desc["actions"].values())


async def test_spin_through_opc_ua(rig):
    client, srv, model, w = rig
    op = await run(client, "centrifuge-u1", "start_program", {"speed_hz": 50.0, "hold_seconds": 20.0})
    assert op.state == "completed" and op.effect != "verified", op.error  # accepted; not evidence of the spin itself
    w.step(6.0)
    speed = await read(client, "centrifuge-u1", "speed")
    assert speed.evidence == "measured" and speed.value == pytest.approx(50.0, abs=0.5)
    assert (await read(client, "centrifuge-u1", "state")).value == "spinning"
    assert (await read(client, "centrifuge-u1", "lid_locked")).value is True
    claim = Claim(op.operation_id, "completed", op.effect, lambda s: model.running())
    assert Oracle(w).judge(claim) is Verdict.CONSISTENT


async def test_the_unit_refuses_an_unsafe_command_and_the_adapter_says_nothing_happened(rig):
    client, srv, model, w = rig
    await run(client, "centrifuge-u1", "start_program", {"speed_hz": 50.0, "hold_seconds": 20.0})
    w.step(2.0)
    refused = await run(client, "centrifuge-u1", "open_lid")  # the interlock: the lid is locked
    assert refused.state == "failed" and refused.effect == "none" and refused.error.may_have_acted is False
    assert "locked" in refused.error.message and model.lid_open is False
    assert Oracle(w).judge(Claim(refused.operation_id, "failed", "failed", lambda s: False)) is Verdict.CONSISTENT


async def test_an_unbalanced_rotor_is_refused_by_the_unit(tmp_path):
    w = World(BENCH, seed=4, attach_arm=False)
    load(w, (1,))
    model = CentrifugeModel(w, device="centrifuge-u1")
    instrument = OpcUaCentrifugeInstrument(w, model, device="centrifuge-u1")
    endpoint = await instrument.start()
    srv, link = opcua_adapter.build_server(w, CENTRIFUGE_OPCUA, endpoint, state_dir=tmp_path / "ua2")
    try:
        async with serving(srv, tmp_path) as client:
            op = await run(client, "centrifuge-u1", "start_program", {"speed_hz": 50.0, "hold_seconds": 20.0})
            assert op.state == "failed" and op.effect == "none" and "imbalance" in op.error.message
            assert not model.running()
    finally:
        await link.close()
        await instrument.stop()


async def test_lid_round_trip_is_idempotent_and_confirmable(rig):
    client, srv, model, w = rig
    assert (await run(client, "centrifuge-u1", "open_lid")).state == "completed"
    assert (await read(client, "centrifuge-u1", "lid_open")).value is True
    assert (await run(client, "centrifuge-u1", "close_lid")).state == "completed"
    assert (await read(client, "centrifuge-u1", "lid_open")).value is False


async def test_sdk_bounds_apply_to_method_arguments(rig):
    client, srv, model, w = rig
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as err:
        await client.actions_invoke("centrifuge-u1", "start_program", {"speed_hz": 900.0, "hold_seconds": 5.0})
    assert err.value.bhms_code == "OUT_OF_RANGE" and not model.running()


async def test_power_loss_makes_reads_invalid_and_a_call_unknown(rig):
    client, srv, model, w = rig
    fault = w.faults.inject(Fault("centrifuge-u1", "power_loss", At(0.0)))
    w.step(0.01)
    assert (await read(client, "centrifuge-u1", "speed")).quality == "invalid"
    op = await run(client, "centrifuge-u1", "open_lid")
    assert op.state == "unknown" and op.effect == "unknown"
    w.faults.clear(fault)
    await srv.reconcile("centrifuge-u1")
    settled = (await client.operations_get(op.operation_id)).operation
    # the lid never opened, so the read-back cannot confirm it: the operation stays unknown
    assert settled.state == "unknown" and model.lid_open is False
    assert Oracle(w).judge(Claim(op.operation_id, "outcome_unknown", "unverified", lambda s: True)) \
        is Verdict.HONEST_UNKNOWN
