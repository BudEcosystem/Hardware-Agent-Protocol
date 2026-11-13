"""Fault-injection runs: every scenario must end in an honest outcome (unknown, refusal, detection) and never in a lie."""

import pytest

from simlab.runs import fault_runs


@pytest.mark.parametrize("name", sorted(fault_runs.SCENARIOS))
async def test_fault_scenario_gives_an_honest_outcome(name, tmp_path):
    outcome = await fault_runs.SCENARIOS[name](tmp_path / name)
    assert outcome.passed, (outcome.expectation, outcome.observed, outcome.verdicts)
    assert set(outcome.verdicts) <= fault_runs.ACCEPTABLE
