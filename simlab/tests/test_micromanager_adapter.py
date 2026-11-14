"""Micro-Manager adapter: BHMS -> pymmcore-plus core API -> Python devices -> microscope twin -> shared world."""

import numpy as np
import pytest

from contract import check_description, check_observations
from lab_helpers import scope_lab
from serving import read, run, serving
from simlab import mmbackend
from simlab.adapters import micromanager


@pytest.fixture
async def rig(tmp_path):
    w, scope = scope_lab(specimen_z_um=40.0)
    core = mmbackend.load_core(scope)
    srv = micromanager.build_server(w, core, state_dir=tmp_path / "mm", frames_dir=tmp_path / "mmframes")
    async with serving(srv, tmp_path) as client:
        yield client, srv, scope, w, tmp_path


async def test_contract(rig):
    client, srv, scope, w, tmp_path = rig
    desc = await check_description(client, "microscope-mm", measured_ok=set())
    await check_observations(client, "microscope-mm", desc)
    assert all(p["evidence"] == "reported" for p in desc["properties"].values())  # Micro-Manager reports, it does not measure
    assert all(a["completionEvidence"] == "reported" for a in desc["actions"].values())


async def test_bhms_drives_the_world_through_the_micromanager_api(rig):
    client, srv, scope, w, tmp_path = rig
    z = await run(client, "microscope-mm", "set_z", {"z": 40.0})
    assert z.state == "completed" and z.effect == "unverified" and abs(scope.true_z_um() - 40.0) < 1e-6
    assert (await run(client, "microscope-mm", "move_stage", {"x": 900.0, "y": 1100.0})).state == "completed"
    assert np.allclose(scope.true_xy_um(), (900.0, 1100.0))
    sharp = await run(client, "microscope-mm", "snap")
    await run(client, "microscope-mm", "set_z", {"z": 75.0})
    blurry = await run(client, "microscope-mm", "snap")
    assert sharp.result["focus_score"] > 2 * blurry.result["focus_score"]
    assert (tmp_path / "mmframes" / f"{sharp.result['frame_id']}.npy").exists()
    assert (await read(client, "microscope-mm", "z_position")).value == pytest.approx(75.0, abs=1e-6)
    # the world's effects carry the bridge's own cause: the core API has no way to pass a BHMS operation id through
    assert {e.cause for e in w.effect_log() if e.kind in ("z_move", "xy_move", "image_captured")} == {"micro-manager"}


async def test_out_of_range_never_reaches_the_core(rig):
    client, srv, scope, w, tmp_path = rig
    from bhms.protocol.errors import BhmsError
    with pytest.raises(BhmsError) as err:
        await client.actions_invoke("microscope-mm", "set_z", {"z": 500.0})
    assert err.value.bhms_code == "OUT_OF_RANGE" and not [e for e in w.effect_log() if e.kind == "z_move"]
