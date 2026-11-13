"""Each deliberately broken MCP bridge fails the agent check recorded for it and no other."""

from __future__ import annotations

import sys

import pytest

from bhms.conformance.core import Status
from bhms.conformance.runner import RunOptions, run
from bhms.conformance.targets import resolve
from bhms.testing.broken_bridges import DEFECTS


async def _run_all():
    device = resolve("conformance-device:ws")
    await device.open_base()
    try:
        bridge = [sys.executable, "-m", "bhms", "mcp", device.url, "--token", device.token]

        async def one(name):
            target = "mcp:" + " ".join([sys.executable, "-m", "bhms.testing.broken_bridges", name, "--", *bridge])
            return name, await run(RunOptions(target=target, profiles=("agent",), device_target=device.url, token=device.token,
                                              seed=9))

        results = []
        for name in DEFECTS:  # one device, so one bridge at a time
            results.append(await one(name))
        return results
    finally:
        await device.aclose()


@pytest.mark.timeout(900)
async def test_every_broken_bridge_fails_the_expected_agent_check():
    import bhms.conformance.checks  # noqa: F401

    for name, report in await _run_all():
        defect = DEFECTS[name]
        failed = {c.name for c in report.checks if c.status is Status.FAILED}
        rows = {r.id for r in report.rows if r.status is Status.FAILED}
        assert failed == set(defect.checks), f"{name}: failed {sorted(failed)}"
        assert set(defect.requirements) <= rows, f"{name}: rows {sorted(rows)}"
        assert report.exit_code == 1


async def test_the_unbroken_bridge_passes_the_agent_profile():
    import bhms.conformance.checks  # noqa: F401

    report = await run(RunOptions(target="agent-bridge", profiles=("agent",), seed=9))
    assert [c.name for c in report.checks if c.status is Status.FAILED] == []
    assert sum(c.status is Status.PASSED for c in report.checks) == 7 and not report.must_failed
    # the two rows no check can prove yet block the claim (R30): the function-tool adapter and the hostile-text device
    assert {r.id for r in report.unproven_must} == {"BHMS-AGT-050", "BHMS-SEC-020"} and report.exit_code == 3
