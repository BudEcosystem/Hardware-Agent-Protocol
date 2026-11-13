"""The arm twin as a BHMS device server: contract, evidence honesty, faults, and oracle verdicts on its operations."""

import asyncio

import pytest

from bhms.protocol.errors import BhmsError
from contract import check_description, check_observations, check_replay_is_one_effect
from lab_helpers import inject_drop_during_next_carry
from serving import read, run, serving
from simlab.faults import At, Fault
from simlab.oracle import Claim, Oracle, Verdict
from simlab.scene import BENCH
from simlab.twins import arm as arm_twin
from simlab.world import World

MEASURED = {"tcp_position", "gripper_width"}


@pytest.fixture(params=["stepped"])
async def arm(request, tmp_path):
    world = World(BENCH, seed=11, mode=request.param)
    srv, twin = arm_twin.build_server(world, state_dir=tmp_path / "arm")
    async with serving(srv, tmp_path) as client:
        yield client, srv, twin, world


@pytest.fixture
async def slow_arm(tmp_path):
    """A realtime world: a 3 s move takes 3 s of wall time, so there is time to cancel or stop it."""
    world = World(BENCH, seed=11, mode="realtime")
    srv, twin = arm_twin.build_server(world, state_dir=tmp_path / "arm")
    async with serving(srv, tmp_path) as client:
        yield client, srv, twin, world


async def test_contract(arm):
    client, srv, twin, world = arm
    desc = await check_description(client, "arm-1", measured_ok=MEASURED)
    await check_observations(client, "arm-1", desc)
    assert desc["safety"]["stop"] == "supported"
    await check_replay_is_one_effect(client, "arm-1", "move_to_site", {"site": "reader"},
                                     lambda: len([e for e in world.effect_log() if e.kind == "move_started"]))


async def test_pick_and_place_through_bhms_is_verified_and_the_oracle_agrees(arm):
    client, srv, twin, world = arm
    ops = {}
    for label, action, args in (("go_hotel", "move_to_site", {"site": "hotel"}), ("grab", "close_gripper", {}),
                                ("go_reader", "move_to_site", {"site": "reader"}), ("release", "open_gripper", {})):
        ops[label] = await run(client, "arm-1", action, args)
        assert ops[label].state == "completed", (label, ops[label].error)
    assert ops["go_reader"].effect == "verified" and ops["grab"].result["holding"] is True
    assert world.ledger.location("plate") == "reader"
    oracle = Oracle(world)
    for label, expect in (("go_reader", lambda s: True), ("release", lambda s: s["ledger"]["plate"] == "reader")):
        claim = Claim(ops[label].operation_id, "completed", "verified", expect)
        assert oracle.judge(claim) is Verdict.CONSISTENT
    # the device's own evidence matches the world: the jaw reads open
    assert (await read(client, "arm-1", "gripper_width")).value > 95


async def test_a_grasp_on_nothing_is_reported_honestly(arm):
    client, srv, twin, world = arm
    await run(client, "arm-1", "move_to_site", {"site": "reader"})
    grab = await run(client, "arm-1", "close_gripper", {})
    assert grab.state == "completed" and grab.result["holding"] is False and grab.result["width_mm"] < 2.0


async def test_a_dropped_plate_is_visible_in_the_gripper_width_before_release(arm):
    client, srv, twin, world = arm
    inject_drop_during_next_carry(world)
    for action, args in (("move_to_site", {"site": "hotel"}), ("close_gripper", {}),
                         ("move_to_site", {"site": "reader"})):
        op = await run(client, "arm-1", action, args)
        assert op.state == "completed"
    assert world.ledger.location("plate") == "lost"
    width = (await read(client, "arm-1", "gripper_width")).value
    assert width < 2.0  # an agent that checks the jaw sees the plate is gone (F14)
    # the move claim is still true (the arm arrived); the oracle has no complaint about it
    move = op
    assert Oracle(world).judge(Claim(move.operation_id, "completed", "verified", lambda s: True)) is Verdict.CONSISTENT


async def test_a_stalled_joint_makes_the_move_fail_with_a_device_fault(arm):
    client, srv, twin, world = arm
    world.faults.inject(Fault("Pitch", "joint_stall", At(0.0)))
    op = await run(client, "arm-1", "move_to_site", {"site": "reader"})
    assert op.state == "failed" and op.error.bhms_code == "DEVICE_FAULT" and op.effect != "verified"
    claim = Claim(op.operation_id, "failed", "unverified", lambda s: False)
    assert Oracle(world).judge(claim) is Verdict.HONEST_UNKNOWN


async def test_disconnected_encoders_leave_the_move_unverified(arm):
    client, srv, twin, world = arm
    world.faults.inject(Fault("arm-1", "sensor_disconnect", At(0.0)))
    world.step(0.01)
    obs = await read(client, "arm-1", "tcp_position")
    assert obs.quality == "invalid" and obs.value is None
    op = await run(client, "arm-1", "move_to_site", {"site": "hotel"})
    assert op.state == "completed" and op.effect == "unverified"  # it moved; nothing can confirm it
    assert Oracle(world).judge(Claim(op.operation_id, "completed", op.effect,
                                     lambda s: True)) is Verdict.CONSISTENT


async def test_power_loss_mid_move_is_unknown_then_reconciled_from_the_device_log(arm):
    client, srv, twin, world = arm
    world.faults.inject(Fault("arm-1", "power_loss", At(world.time_s + 0.5)))
    op = await run(client, "arm-1", "move_to_site", {"site": "reader"})
    assert op.state == "unknown" and op.effect == "unknown"
    summary = next(d for d in (await client.devices_list()).devices if d.device_id == "arm-1")
    assert summary.status == "offline"
    with pytest.raises(BhmsError) as refused:
        await client.actions_invoke("arm-1", "move_to_site", {"site": "hotel"})
    assert refused.value.code == "DEVICE_UNAVAILABLE" and refused.value.may_have_acted is False
    world.faults.clear("fault-1")
    (await srv.reconcile("arm-1"))
    settled = (await client.operations_get(op.operation_id)).operation
    assert settled.state == "failed" and settled.error.may_have_acted is True
    verdict = Oracle(world).judge(Claim(op.operation_id, "failed", "unverified", lambda s: False))
    assert verdict is Verdict.HONEST_UNKNOWN
    # and the arm works again once powered
    assert (await run(client, "arm-1", "move_to_site", {"site": "hotel"})).state == "completed"


async def test_cancel_stops_the_arm_and_the_effect_is_unverified(slow_arm):
    client, srv, twin, world = slow_arm
    started = await client.actions_invoke("arm-1", "move_to_site", {"site": "reader"}, wait_ms=0)
    await asyncio.sleep(0.4)
    await client.operations_cancel(started.operation.operation_id, reason="test")
    op = (await client.operations_wait(started.operation.operation_id, 5000)).operation
    assert op.state == "canceled" and op.effect == "unverified"
    assert not twin.busy


async def test_stop_holds_the_arm_where_it_is(slow_arm):
    client, srv, twin, world = slow_arm
    started = await client.actions_invoke("arm-1", "move_to_site", {"site": "reader"}, wait_ms=0)
    await asyncio.sleep(0.4)
    stopped = await client.stop("test stop", device_ids=["arm-1"], wait_ms=2000)
    op = (await client.operations_wait(started.operation.operation_id, 5000)).operation
    assert op.state in ("canceled", "unknown") and stopped is not None
    assert any(e.kind == "move_aborted" for e in world.effect_log())
