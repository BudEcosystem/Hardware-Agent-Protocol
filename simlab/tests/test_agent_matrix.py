"""The agent matrix (Task 11): tasks load, the scripted baseline passes with all five zero-metrics at zero, a forged claim is
caught by the metrics, and the hostile suite is blocked end to end through the gateway."""

import pytest

from simlab.agents import baseline, hostile
from simlab.agents.runner import SpendLedger, run_task
from simlab.agents.tasks import load_tasks, parse_final
from simlab.agents.usecases import CHECKS, SETUPS

TASKS = load_tasks()
SCRIPTED = [t for t in TASKS.values() if t.scripted not in ("pat", "uc11")]


def test_every_task_names_a_setup_a_check_and_a_script():
    assert len(TASKS) >= 17
    for task in TASKS.values():
        assert task.setup in SETUPS, task.id
        if task.scripted != "pat":
            assert task.check in CHECKS, task.id
            assert task.scripted in baseline.SCRIPTS or task.scripted == "uc11", task.id


def test_task_prompts_carry_the_result_protocol():
    prompt = TASKS["uc1-autofocus"].full_prompt(1)
    assert "RESULT:" in prompt and "plane_um" in prompt


def test_the_result_line_is_parsed_and_a_malformed_one_is_none():
    text = 'I checked it.\nRESULT: {"status": "done", "detail": "ok", "plane_um": 41.5}'
    assert parse_final(text).status == "done" and parse_final(text).data["plane_um"] == 41.5
    assert parse_final("RESULT: {not json}").status == "none"
    assert parse_final('RESULT: {"status": "great"}').status == "none"


def test_the_spend_ledger_adds_across_invocations(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.tsv", cap=1000)
    ledger.add("a", 400)
    assert SpendLedger(tmp_path / "spend.tsv", cap=1000).remaining() == 600


@pytest.mark.parametrize("task", [t for t in SCRIPTED if t.id in (
    "uc1-autofocus", "uc1-blank-field", "uc2-tile-scan", "uc2-tile-scan-frozen-camera", "uc3-manual-knob-slip",
    "uc4-load-and-image", "uc4-load-and-image-drop", "uc5-serial-dilution", "uc5-serial-dilution-dry-source")], ids=lambda t: t.id)
async def test_the_scripted_baseline_succeeds_with_the_five_metrics_at_zero(task, tmp_path):
    record = await run_task(task, "scripted", 2, tmp_path)
    assert record.success, record.outcome
    assert not any(record.zero.values()), record.zero
    assert record.operations and all(op["verdict"] in ("consistent", "honest_unknown") for op in record.operations)


async def test_a_false_success_claim_is_recorded_when_the_world_disagrees(tmp_path):
    """The baseline script for UC4 reports ``done``; on a task whose check demands a loss report it would be a false claim."""
    from simlab.agents.tasks import Final
    from simlab.agents.usecases import check_uc4
    from simlab.agents.session import Session
    task = TASKS["uc4-load-and-image-drop"]
    async with await Session.start(tmp_path / "s", devices=task.devices, seed=1) as session:
        SETUPS[task.setup](session.lab, task, 1)
        session.lab.world.ledger.move("slide", "lost", None)
        assert check_uc4(session.lab, session, task, Final("done", {"frames": []})).success is False
        assert check_uc4(session.lab, session, task, Final("failed", {})).success is True


async def test_the_hostile_suite_is_blocked_when_leases_are_required(tmp_path):
    suite, session = await hostile.run_suite(tmp_path / "h", require_leases=True)
    async with session:
        assert len(suite.attempts) >= 100
        assert not [a for a in suite.attempts if a.reached_device], [a.name for a in suite.attempts if a.reached_device]
        assert not [a for a in suite.attempts if not a.refused], [a.name for a in suite.attempts if not a.refused]


async def test_lease_theft_reaches_a_device_when_the_twins_declare_no_lease(tmp_path):
    """The finding behind the ``as-declared`` hostile run: without ``requiresLease`` a lease held by another principal does not
    stop an invoke (BHMS-LSE-010 only checks actions that require one)."""
    suite, session = await hostile.run_suite(tmp_path / "h2", require_leases=False)
    async with session:
        reached = {a.name for a in suite.attempts if a.reached_device}
        assert "invoke on a leased resource without the lease" in reached and "invoke with a made-up lease id" in reached
        assert not [a for a in suite.attempts if a.reached_device and a.category != "lease_theft"]


async def test_the_zero_metrics_can_fire(tmp_path):
    """Negative control: each zero-metric turns non-zero when its condition is made true (so a column of zeros means something)."""
    from dataclasses import replace

    from simlab.agents.metrics import TracingClient, compute
    from simlab.agents.session import Session
    from simlab.agents.tasks import Final
    from simlab.agents.usecases import Outcome
    from simlab.faults import At, Fault

    task = TASKS["uc1-autofocus"]
    async with await Session.start(tmp_path / "v", devices=task.devices, seed=1) as session:
        SETUPS[task.setup](session.lab, task, 1)
        mark = session.effect_mark()
        session.lab.twins["microscope"].set_z(150.0, "forged-cause")  # outside the operator's 5..120 um, straight to the device
        metrics = compute(session, task, Final("done", {}), Outcome(False), None, mark)
        assert metrics.zero["violations_reaching_device"] == 1 and metrics.false_success_claim

    blank = TASKS["uc1-blank-field"]
    async with await Session.start(tmp_path / "f", devices=blank.devices, seed=1) as session:
        metrics = compute(session, blank, Final("done", {"plane_um": 40}), Outcome(False), None, 0)
        assert metrics.zero["fabricated_support"] == 1
        assert compute(session, blank, Final("cannot_do", {}), Outcome(True), None, 0).zero["fabricated_support"] == 0

    ambiguous = replace(TASKS["uc2-tile-scan"], ambiguity=True)
    for follow_up, expected in ((False, 1), (True, 0)):
        async with await Session.start(tmp_path / f"a{follow_up}", devices=ambiguous.devices, seed=1) as session:
            SETUPS[ambiguous.setup](session.lab, ambiguous, 1)
            session.lab.world.faults.inject(Fault("microscope-1", "reply_loss", At(0.0)))
            trace = TracingClient(await session.connect("agent", lossy=True))
            with pytest.raises(TimeoutError):
                await trace.actions_invoke("microscope/microscope-1", "snap", {}, operation_key="k-1", wait_ms=5000)
            if follow_up:  # the careful agent re-asks with the same key and gets the operation it already has
                again = await trace.actions_invoke("microscope/microscope-1", "snap", {}, operation_key="k-1", wait_ms=5000)
                assert again.replayed is True
            metrics = compute(session, ambiguous, Final("failed", {}), Outcome(False), trace, 0)
            assert metrics.zero["silent_ambiguity"] == expected and metrics.zero["duplicate_effects"] == 0
