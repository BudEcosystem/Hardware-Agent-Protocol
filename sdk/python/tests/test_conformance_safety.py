"""The runner never moves a device it has not been told it may: identification only by declaration, effects only on request."""

from __future__ import annotations

import json
import sys

from bhms.conformance.core import Status
from bhms.conformance.runner import RunOptions, run


def _received(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _executable(entries):
    """Invokes whose action exists on a device (a lax server could run them), and any stop that names a device or a scope."""
    real = {"move_to", "pulse", "slow_move", "clamp", "dispense", "fault", "overdrive", "guard_finish", "guard_cancel", "guard_hold"}
    real_devices = {"axis-1", "pump-1"}
    stops = [e for e in entries if e["method"] == "stop" and (e.get("scope") or real_devices & set(e.get("deviceIds") or []))]
    return stops + [e for e in entries if e["method"] == "actions/invoke" and e.get("action") in real]


def _target(tmp_path, *extra):
    log = tmp_path / "received.jsonl"
    return f"stdio:{sys.executable} -m bhms.testing.broken_devices clamp-instead-of-refuse --undeclared --log {log} {' '.join(extra)}", log


async def test_devices_named_axis_and_pump_without_the_extension_get_no_effectful_check_and_no_stop(tmp_path):
    target, log = _target(tmp_path)
    report = await run(RunOptions(target=target, seed=11))
    assert _executable(_received(log)) == []
    by_name = {c.name: c for c in report.checks}
    assert by_name["arguments.refusals-from-description"].status is Status.SKIPPED
    assert by_name["operations.idempotency"].status is Status.SKIPPED
    assert "does not declare itself a conformance device" in by_name["operations.idempotency"].message
    assert by_name["arguments.unexecutable-refusals"].status is Status.PASSED  # the cases that cannot execute do run
    assert not [c for c in report.checks if c.status is Status.FAILED]
    assert report.exit_code == 3 and report.unproven_must and not report.claims["core"]["claimable"]


async def test_allow_effects_runs_them_and_then_finds_the_defect(tmp_path):
    target, log = _target(tmp_path)
    report = await run(RunOptions(target=target, seed=11, allow_effects=True, only=("arguments.vectors-refusals",)))
    assert _executable(_received(log))
    assert [c.name for c in report.checks if c.status is Status.FAILED] == ["arguments.vectors-refusals"]
    assert report.exit_code == 1


async def test_a_physical_target_needs_physical_ok_even_when_it_declares_itself(tmp_path):
    log = tmp_path / "received.jsonl"
    target = f"stdio:{sys.executable} -m bhms.testing.broken_devices clamp-instead-of-refuse --log {log}"
    report = await run(RunOptions(target=target, seed=11, physical=True, only=("arguments.vectors-refusals", "operations.idempotency")))
    assert _executable(_received(log)) == []
    assert {c.status for c in report.checks if c.name.startswith(("arguments.vectors", "operations.idem"))} == {Status.SKIPPED}
    assert report.meta["devices"] == "physical"
    allowed = await run(RunOptions(target=target, seed=11, physical=True, physical_ok=True, only=("arguments.vectors-refusals",)))
    assert _executable(_received(log))
    assert [c.status for c in allowed.checks if c.name == "arguments.vectors-refusals"] == [Status.FAILED]


async def test_an_arbitrary_url_target_does_not_claim_simulated_devices():
    report = await run(RunOptions(target="unix:/nonexistent/none.sock"))
    assert report.fatal  # unreachable: nothing to label
    from bhms.conformance.runner import _meta
    from bhms.conformance.targets import Target

    assert _meta(RunOptions(target="ws://example"), Target("ws://example", "ws", url="ws://example"), None, 1, "c", [], {})["devices"] == "unknown"
