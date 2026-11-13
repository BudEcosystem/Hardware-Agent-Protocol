"""The conformance runner against the Python reference targets, its report format, the CLI and every broken fixture."""

from __future__ import annotations

import asyncio
import json
import sys

from typer.testing import CliRunner

from bhms.cli.main import app
from bhms.conformance import coverage, requirements
from bhms.conformance.core import REGISTRY, Status
from bhms.conformance.runner import RunOptions, run
from bhms.testing.broken_devices import DEFECTS


_REPORT = None


async def reference():
    """One full core-profile run against the conformance device over stdio, shared by the report tests."""
    global _REPORT
    if _REPORT is None:
        import bhms.conformance.checks  # noqa: F401

        _REPORT = await run(RunOptions(target="conformance-device", seed=7, strict=True))
    return _REPORT


async def invoke(*args, env=None):
    """One CLI command in a thread of its own (its asyncio.run must not meet the loop of the test)."""
    return await asyncio.to_thread(lambda: CliRunner().invoke(app, list(args), env=env, catch_exceptions=False))


async def test_python_reference_server_passes_every_core_check():
    reference_report = await reference()
    failed = [(c.name, c.message) for c in reference_report.checks if c.status is Status.FAILED]
    assert failed == []
    assert reference_report.exit_code == 0 and not reference_report.must_failed
    passed = [c for c in reference_report.checks if c.status is Status.PASSED]
    assert len(passed) >= 70
    skipped = [c.name for c in reference_report.checks if c.status is Status.SKIPPED]
    # a stdio conformance device offers faults, restart and a state directory; only the multi-principal checks need the gateway fixture
    assert all(name.startswith("authority.") for name in skipped), skipped
    assert {r.status for r in reference_report.rows} <= {Status.PASSED, Status.SKIPPED, Status.NOT_APPLICABLE}
    assert not any(r.status is Status.FAILED for r in reference_report.rows)


async def test_report_states_what_bhms_cnf_001_to_005_require():
    report = (await reference()).to_json()
    meta = report["conformance"]
    assert meta["protocolVersion"] == "2026-11-13"                                   # CNF-001
    assert {"core", "leases", "events", "programs", "registry"} <= set(meta["profiles"])
    assert meta["transport"] == "stdio" and meta["implementation"]["name"] == "conformance-device"
    assert meta["schemaDigest"].startswith("sha256:") and meta["seed"] == 7        # CNF-003
    assert meta["command"] and meta["devices"] == "simulated"                       # CNF-003, CNF-005
    claimed = set(meta["profiles"])
    wanted = {row["id"] for row in requirements.load() if row["profile"] in claimed}
    assert {r["id"] for r in report["requirements"]} == wanted                       # CNF-002: one row per requirement
    assert {r["status"] for r in report["requirements"]} <= {"passed", "failed", "skipped", "not-applicable"}
    for row in report["requirements"]:
        if row["status"] in ("skipped", "not-applicable"):
            assert row["reason"], row["id"]                                          # a skipped row says why
    assert report["exitCode"] == 0 and report["summary"]["mustFailed"] == 0


def test_every_core_must_is_covered_or_has_a_recorded_reason():
    import bhms.conformance.checks  # noqa: F401

    covered = coverage.covering()
    for row in requirements.load():
        if row["profile"] == "core" and row["level"] == "MUST":
            assert row["id"] in covered or row["id"] in coverage.EXEMPT, row["id"]
    for rid, (kind, reason) in coverage.EXEMPT.items():
        assert rid not in covered, f"{rid} has a check; remove its exemption"
        assert kind in {"inspection", "not-yet-testable", "not-applicable"} and reason
    for spec in REGISTRY:
        assert set(spec.ids) <= {r["id"] for r in requirements.load()}, spec.name
    assert len({s.name for s in REGISTRY}) == len(REGISTRY)


async def test_cli_runs_one_check_and_writes_the_json_report(tmp_path):
    out = tmp_path / "report.json"
    result = await invoke("conformance", "conformance-device", "--only", "lifecycle.nan-tokens", "--json", str(out), "--seed", "3",
                          env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text())
    assert [c["check"] for c in report["checks"] if c["status"] == "passed"][:1] == ["lifecycle.nan-tokens"]
    assert "lifecycle.nan-tokens" in result.output and "passed" in result.output


async def test_cli_exit_status_two_for_an_unreachable_target_and_a_bad_profile(tmp_path):
    result = await invoke("conformance", f"unix:{tmp_path}/nothing.sock")
    assert result.exit_code == 2 and "cannot reach" in result.output
    result = await invoke("conformance", "conformance-device", "--profile", "nonsense")
    assert result.exit_code == 2
    result = await invoke("conformance", "--coverage", "--profile", "core")
    assert result.exit_code == 0 and "BHMS-LIF-001" in result.output and "UNCOVERED" not in result.output


async def test_cli_exit_status_one_when_a_must_fails():
    command = f"stdio:{sys.executable} -m bhms.testing.broken_devices batch-accepted"
    result = await invoke("conformance", command, "--only", "transport.batch-rejected", env={"COLUMNS": "200"})
    assert result.exit_code == 1 and "FAILED BHMS-TRN-002" in result.output


async def test_every_broken_server_fails_exactly_the_expected_checks():
    """Each deliberately broken server fails the checks recorded for it, and the requirement rows they name."""

    async def one(name: str):
        defect = DEFECTS[name]
        only = tuple(c for c in (*defect.checks, *defect.drive) if c != "observers.all-traffic")
        target = f"stdio:{sys.executable} -m bhms.testing.broken_devices {name}"
        return name, await run(RunOptions(target=target, only=only or ("none",), seed=5))

    import bhms.conformance.checks  # noqa: F401

    for name, report in await asyncio.gather(*(one(n) for n in DEFECTS)):
        defect = DEFECTS[name]
        failed_checks = {c.name for c in report.checks if c.status is Status.FAILED}
        failed_rows = {r.id for r in report.rows if r.status is Status.FAILED}
        assert failed_checks == set(defect.checks), f"{name}: failed {sorted(failed_checks)}"
        assert set(defect.requirements) <= failed_rows, f"{name}: rows {sorted(failed_rows)}"
        assert report.exit_code == 1, name
        assert len(DEFECTS) >= 20
