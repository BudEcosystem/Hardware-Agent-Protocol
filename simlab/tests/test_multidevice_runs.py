"""The scripted multi-device runs through BHMS, with the oracle judging every operation (acceptance: all CONSISTENT)."""

import json

import numpy as np
import pytest

from simlab.faults import Fault, OnEvent
from simlab.oracle import Verdict
from simlab.runs import multidevice


async def test_uc4_arm_loads_slide_microscope_autofocuses_images_recorded(tmp_path):
    result = await multidevice.run_uc4(tmp_path / "uc4", seed=3, specimen_z_um=52.0)
    assert result.status == "ok", result.detail
    assert result.all_consistent, result.verdict_counts
    assert len(result.operations) >= 20  # moves, grips, a focus sweep, images
    assert {o["verdict"] for o in result.operations} == {"consistent"}
    # the images really exist, are in focus, and the slide is back where it started
    extra = result.extra
    assert extra["slide_location"] == "slide_rack" and len(extra["frames"]) == 2
    assert all(abs(z - 52.0) <= 2.0 for z in extra["frame_z_um"]) and abs(extra["focus_um"] - 52.0) <= 2.0
    files = list((tmp_path / "uc4" / "frames").glob("*.npy"))
    assert len(files) >= 20 and np.load(files[0]).shape == (256, 256)
    # most operations of the run are verified by a device measurement; the rest are honestly unverified or effect-free
    effects = {o["effect"] for o in result.operations}
    assert "verified" in effects and "unknown" not in effects


async def test_uc4_is_deterministic_for_one_seed(tmp_path):
    a = await multidevice.run_uc4(tmp_path / "a", seed=9)
    b = await multidevice.run_uc4(tmp_path / "b", seed=9)
    c = await multidevice.run_uc4(tmp_path / "c", seed=10)
    assert a.digest == b.digest and a.digest != c.digest
    assert a.sim_s == b.sim_s


async def test_assay_crosses_four_devices_and_the_numbers_follow_the_ledger(tmp_path):
    result = await multidevice.run_assay(tmp_path / "assay", seed=4)
    assert result.status == "ok", result.detail
    assert result.all_consistent, result.verdict_counts
    extra = result.extra
    assert all(abs(c - 2.0) < 0.15 for c in extra["estimated_dye_mM"].values())
    assert extra["absorbance"]["A3"] == pytest.approx(0.04, abs=0.02)  # the empty well reads the blank
    assert extra["mass_g"] == pytest.approx(40.15, abs=0.02)


async def test_a_nearly_dry_reservoir_is_an_air_aspiration_the_handler_reports_and_the_oracle_confirms(tmp_path):
    def nearly_dry(lab):
        lab.world.ledger.add_container("reservoir", "trough", {"A1": (120.0, {"dye": 2.0})}, "lh_reservoir",
                                       max_volume_ul=50_000.0)

    result = await multidevice.run_assay(tmp_path / "dry", seed=4, prepare=nearly_dry)
    assert result.status == "step_failed" and "air" in result.detail
    verdicts = {o["verdict"] for o in result.operations}
    assert verdicts <= {"consistent", "honest_unknown"} and "honest_unknown" in verdicts  # the failed aspirate
    failed = [o for o in result.operations if o["state"] == "failed"]
    assert len(failed) == 1 and failed[0]["action"] == "aspirate" and failed[0]["effect"] != "verified"


async def test_run_reports_a_dropped_plate_instead_of_reading_an_empty_reader(tmp_path):
    from simlab.lab import Lab
    from simlab.agents.scripted import BhmsArm
    async with await Lab.start(tmp_path / "drop", seed=2, devices=("arm", "plate_reader")) as lab:
        lab.world.faults.inject(Fault("plate", "drop_object", OnEvent("move_started"),
                                      {"require_location": "in_gripper", "delay_s": 0.5}))
        arm = BhmsArm(lab.client("arm"), "arm-1")
        await arm.move("hotel")
        assert await arm.close_gripper()
        await arm.move("reader")  # the plate falls mid-carry
        assert (await arm.width_mm()) < 2.0  # the jaw says so
        from simlab.agents.scripted import Recorder
        reader = Recorder(lab.client("plate_reader"), "reader-1")
        with pytest.raises(Exception) as err:
            await reader.invoke("read_absorbance", {"wavelength": 560, "wells": ["A1"]})
        assert "no plate" in str(err.value)
        verdicts = {j.verdict for j in multidevice.judge_operations(lab.oracle, arm.operations + reader.operations)}
        assert verdicts <= {Verdict.CONSISTENT}, verdicts


def test_cli_writes_the_run_record(tmp_path):
    code = multidevice.main(["--scenario", "uc4", "--seed", "2", "--out", str(tmp_path)])
    record = json.loads((tmp_path / "uc4.json").read_text())
    assert code == 0 and record["all_consistent"] is True and record["realtime_factor"] > 1.0
