"""Scripted agents prove the lab (validation plan §11 Task 8): focus search, UC4, determinism."""

import pytest

from lab_helpers import bench
from simlab.agents.scripted import ScriptedAutofocus, ScriptedLoadAndImage
from simlab.faults import Fault, OnEvent
from simlab.oracle import Oracle


@pytest.mark.parametrize("seed", range(20))
def test_autofocus_finds_the_specimen_plane_within_2_um(seed):
    specimen_z = 30.0 + (seed * 7) % 41  # 30..70 um, different on every seed
    w, arm, scope = bench(seed, specimen_z_um=float(specimen_z), slide_site="microscope_stage")
    result = ScriptedAutofocus(scope).run()
    assert result.status == "ok" and abs(result.z_um - specimen_z) <= 2.0
    assert result.contrast > 2.0


def test_autofocus_reports_no_focus_on_an_empty_stage():
    w, arm, scope = bench(3, slide_site="slide_rack")
    result = ScriptedAutofocus(scope).run()
    assert result.status == "no_focus" and result.z_um is None


def test_load_and_image_ends_with_the_slide_home_and_in_focus_images():
    w, arm, scope = bench(5, specimen_z_um=48.0)
    report = ScriptedLoadAndImage(arm, scope).run()
    assert report.status == "ok", report
    assert w.ledger.location("slide") == "slide_rack"
    assert len(report.frames) == 2
    for frame_id in report.frames:
        frame = scope.frames.get(frame_id)
        assert frame.specimen_present and abs(frame.z_um - 48.0) <= 2.0
    assert report.focus.status == "ok" and abs(report.focus.z_um - 48.0) <= 2.0


def test_a_slide_dropped_in_transit_is_reported_not_imaged():
    w, arm, scope = bench(5)
    w.faults.inject(Fault("slide", "drop_object", OnEvent("move_started"),
                          {"require_location": "in_gripper", "delay_s": 0.4}))
    report = ScriptedLoadAndImage(arm, scope).run()
    assert report.status == "object_lost" and w.ledger.location("slide") == "lost"
    assert not [e for e in w.effect_log() if e.kind == "image_captured"]  # it never imaged an empty stage


def test_the_same_seed_gives_the_same_digest_and_a_different_seed_does_not():
    digests = []
    for seed in (11, 11, 12):
        w, arm, scope = bench(seed)
        assert ScriptedLoadAndImage(arm, scope).run().status == "ok"
        digests.append(w.digest())
    assert digests[0] == digests[1] and digests[0] != digests[2]


def test_every_effect_of_the_run_is_attributed_to_an_operation():
    w, arm, scope = bench(2)
    ScriptedLoadAndImage(arm, scope).run()
    physical = [e for e in w.effect_log() if e.device not in ("fault",)]
    assert physical and all(e.cause and e.cause.startswith("direct-") for e in physical)
    assert not Oracle(w).duplicates("direct-arm-1")
