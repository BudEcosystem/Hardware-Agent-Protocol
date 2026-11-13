"""The microscope twin as a BHMS device server."""

import asyncio

import pytest

from contract import check_description, check_observations, check_replay_is_one_effect
from lab_helpers import turn
from serving import read, run, serving
from simlab.faults import At, Fault
from simlab.oracle import Claim, Oracle, Verdict
from simlab.scene import BENCH
from simlab.twins import microscope as scope_twin
from simlab.world import SceneParams, World

MEASURED = {"z_position", "xy_position"}


async def make(tmp_path, mode="stepped", **params):
    world = World(BENCH, seed=5, mode=mode, attach_arm=False, params=SceneParams(**params) if params else None)
    world.ledger.add_container("slide", "slide", {}, "microscope_stage", meta={"specimen_z_um": 40.0})
    srv, scope = scope_twin.build_server(world, state_dir=tmp_path / "scope")
    return world, srv, scope


@pytest.fixture
async def rig(tmp_path):
    world, srv, scope = await make(tmp_path)
    async with serving(srv, tmp_path) as client:
        yield client, srv, scope, world


async def test_contract(rig):
    client, srv, scope, world = rig
    desc = await check_description(client, "microscope-1", measured_ok=MEASURED)
    await check_observations(client, "microscope-1", desc)
    assert desc["actions"]["snap"]["effect"] == "none" and desc["actions"]["set_z"]["completionEvidence"] == "measured"
    await check_replay_is_one_effect(client, "microscope-1", "snap", {"exposure_ms": 20},
                                     lambda: len([e for e in world.effect_log() if e.kind == "image_captured"]))


async def test_set_z_is_verified_by_the_encoder_and_the_oracle_agrees(rig):
    client, srv, scope, world = rig
    op = await run(client, "microscope-1", "set_z", {"z": 40.0})
    assert op.state == "completed" and op.effect == "verified" and abs(op.result["z_um"] - 40.0) < 0.3
    claim = Claim(op.operation_id, "completed", "verified", lambda s: abs(scope.true_z_um() - 40.0) < 0.3)
    assert Oracle(world).judge(claim) is Verdict.CONSISTENT


async def test_snap_records_a_frame_and_reports_the_focus_score(rig):
    client, srv, scope, world = rig
    await run(client, "microscope-1", "set_z", {"z": 40.0})
    sharp = await run(client, "microscope-1", "snap", {"exposure_ms": 20})
    await run(client, "microscope-1", "set_z", {"z": 70.0})
    blurry = await run(client, "microscope-1", "snap", {"exposure_ms": 20})
    assert sharp.result["focus_score"] > 2 * blurry.result["focus_score"]
    assert sharp.result["captured_at_s"] == pytest.approx(sharp.result["device_time_s"], abs=0.05)
    assert scope.frames.get(sharp.result["frame_id"]).z_um == pytest.approx(40.0, abs=0.01)


async def test_a_knob_turn_is_visible_as_a_reading_with_no_operation_behind_it(rig):
    client, srv, scope, world = rig
    before = (await read(client, "microscope-1", "z_position")).value
    turn(world, "focus_fine", 2.0)  # a human at the knob (F9)
    after = (await read(client, "microscope-1", "z_position")).value
    assert abs((after - before) - 2.0 * 100.0 / 6.283185) < 1.0
    assert [o for o in (await client.operations_list(device_id="microscope-1")).operations] == []
    # a commanded move still lands on the requested z: the drive servos the true axis
    op = await run(client, "microscope-1", "set_z", {"z": 60.0})
    assert op.effect == "verified" and abs(scope.true_z_um() - 60.0) < 0.3


async def test_a_frozen_camera_is_betrayed_by_its_capture_time(rig):
    client, srv, scope, world = rig
    await run(client, "microscope-1", "snap", {})
    world.faults.inject(Fault("scope", "stale_camera", At(0.0)))
    world.step(0.01)
    await run(client, "microscope-1", "set_z", {"z": 90.0})
    frozen = await run(client, "microscope-1", "snap", {})
    assert frozen.state == "completed"
    assert frozen.result["device_time_s"] - frozen.result["captured_at_s"] > 0.25  # an old frame, honestly dated
    assert world.effect_log()[-1].detail["stale"] is True


async def test_a_disconnected_camera_fails_with_proof_of_no_effect(rig):
    client, srv, scope, world = rig
    world.faults.inject(Fault("scope", "sensor_disconnect", At(0.0)))
    world.step(0.01)
    op = await run(client, "microscope-1", "snap", {})
    assert op.state == "failed" and op.error.may_have_acted is False and op.effect == "none"
    assert [e for e in world.effect_log() if e.kind == "image_captured"] == []


async def test_power_loss_mid_move_is_unknown_and_reconciles_to_failed(rig):
    client, srv, scope, world = rig
    world.faults.inject(Fault("microscope-1", "power_loss", At(world.time_s + 0.3)))
    op = await run(client, "microscope-1", "set_z", {"z": 190.0})  # 850 ms of travel
    assert op.state == "unknown"
    world.faults.clear("fault-1")
    await srv.reconcile("microscope-1")
    settled = (await client.operations_get(op.operation_id)).operation
    assert settled.state == "failed" and settled.error.may_have_acted is True


async def test_cancel_freezes_the_axis_partway(tmp_path):
    world, srv, scope = await make(tmp_path, mode="realtime")
    async with serving(srv, tmp_path) as client:
        started = await client.actions_invoke("microscope-1", "set_z", {"z": 190.0}, wait_ms=0)
        await asyncio.sleep(0.3)
        await client.operations_cancel(started.operation.operation_id, reason="test")
        op = (await client.operations_wait(started.operation.operation_id, 5000)).operation
        assert op.state == "canceled"
