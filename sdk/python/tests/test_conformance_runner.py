"""The conformance runner against the Python reference targets, its report format, the CLI and every broken fixture."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
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


@pytest.mark.timeout(900)
async def test_python_reference_server_passes_every_core_check():
    reference_report = await reference()
    failed = [(c.name, c.message) for c in reference_report.checks if c.status is Status.FAILED]
    assert failed == []
    assert not reference_report.must_failed
    # a single-principal stdio server is a complete core claim: no authority profile, nothing unproven (R27)
    assert reference_report.exit_code == 0 and not reference_report.unproven_must
    assert all(claim["claimable"] for claim in reference_report.claims.values())
    assert set(reference_report.claims) == {"core", "leases", "events", "programs", "registry"}
    assert reference_report.meta["authority"].startswith("single-principal") and reference_report.meta["reportKind"] == "conformance"
    passed = [c for c in reference_report.checks if c.status is Status.PASSED]
    assert len(passed) >= 70
    skipped = [c.name for c in reference_report.checks if c.status is Status.SKIPPED]
    # a stdio conformance device offers faults, restart and a state directory; only the multi-principal checks need the gateway fixture
    assert skipped == []  # nothing the reference device offers is left unrun
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
    assert report["formatVersion"] == 1 and report["exitCode"] == 0 and report["summary"]["mustFailed"] == 0
    assert report["summary"]["mustUnproven"] == 0 and report["claims"]["core"]["claimable"] and meta["reportKind"] == "conformance"


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


def test_inspection_exemptions_match_the_index_so_nothing_is_silently_downgraded():
    index = requirements.by_id()
    for rid, (kind, _) in coverage.EXEMPT.items():
        if kind == "inspection":
            assert index[rid]["method"] == "inspection", f"{rid} is exempt as inspection but the index says {index[rid]['method']}"
        assert kind != "not-applicable" or rid == "BHMS-EVT-013"  # the one row that v0.1 cannot exercise (read is one global scope)


async def test_cli_runs_one_check_and_writes_the_json_report(tmp_path):
    out = tmp_path / "report.json"
    result = await invoke("conformance", "conformance-device", "--only", "lifecycle.nan-tokens", "--json", str(out), "--seed", "3", "--allow-unproven",
                          env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text())
    assert [c["check"] for c in report["checks"] if c["status"] == "passed"][:1] == ["lifecycle.nan-tokens"]
    assert "lifecycle.nan-tokens" in result.output and "passed" in result.output


async def test_json_to_stdout_is_parseable_and_the_table_goes_to_stderr():
    result = await invoke("conformance", "conformance-device", "--only", "lifecycle.nan-tokens", "--json", "-", "--seed", "3",
                          env={"COLUMNS": "200"})
    report = json.loads(result.stdout)
    assert report["formatVersion"] == 1 and report["conformance"]["seed"] == 3 and report["claims"]
    assert "lifecycle.nan-tokens" in result.stderr and result.exit_code == 3  # one check run: the claim is unsupported


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


async def test_every_broken_server_fails_the_expected_checks():
    """Each deliberately broken server, run against its own checks (plus those that drive observer defects), fails exactly them."""
    import bhms.conformance.checks  # noqa: F401

    assert len(DEFECTS) >= 20

    async def one(name: str):
        defect = DEFECTS[name]
        only = tuple(c for c in (*defect.checks, *defect.drive) if c != "observers.all-traffic")
        target = f"stdio:{sys.executable} -m bhms.testing.broken_devices {name}"
        return name, await run(RunOptions(target=target, only=only or ("none",), seed=5))

    for name, report in await asyncio.gather(*(one(n) for n in DEFECTS)):
        defect = DEFECTS[name]
        failed_checks = {c.name for c in report.checks if c.status is Status.FAILED}
        failed_rows = {r.id for r in report.rows if r.status is Status.FAILED}
        assert failed_checks == set(defect.checks), f"{name}: failed {sorted(failed_checks)}"
        assert set(defect.requirements) <= failed_rows, f"{name}: rows {sorted(failed_rows)}"
        assert report.exit_code == 1, name


@pytest.mark.slow
@pytest.mark.timeout(1800)
async def test_every_broken_server_fails_exactly_the_expected_checks_in_the_full_set():
    """Slow (about 5 minutes): every defect against the FULL applicable check set fails exactly ``Defect.full``.
    Run it with ``python3 -m pytest -m slow`` (nightly), not in the default suite."""
    import bhms.conformance.checks  # noqa: F401

    slots = asyncio.Semaphore(6)

    async def one(name: str):
        async with slots:
            return name, await run(RunOptions(target=f"stdio:{sys.executable} -m bhms.testing.broken_devices {name}", seed=5))

    for name, report in await asyncio.gather(*(one(n) for n in DEFECTS)):
        defect = DEFECTS[name]
        failed_checks = {c.name for c in report.checks if c.status is Status.FAILED}
        assert failed_checks == set(defect.full), f"{name}: failed {sorted(failed_checks)}"
        assert set(defect.requirements) <= {r.id for r in report.rows if r.status is Status.FAILED}, name
        assert report.exit_code == 1, name


async def test_a_multi_principal_target_is_reported_as_multi_principal():
    """``capabilities.authority`` is an empty object: its presence, not its truth value, says a scope policy is enforced."""
    import io

    from rich.console import Console

    from bhms.conformance.runner import render

    report = await run(RunOptions(target="conformance-device:principals", only=("none",), seed=5))
    assert not report.fatal, report.fatal
    assert report.meta["authority"] == "multi-principal: a scope policy is enforced"
    assert report.to_json()["conformance"]["authority"].startswith("multi-principal")
    out = io.StringIO()
    render(report, console=Console(file=out, width=200, highlight=False))
    assert "authority: multi-principal" in out.getvalue() and "single-principal" not in out.getvalue()


def test_device_command_replaces_the_command_of_every_conformance_device_fixture():
    from bhms.conformance.targets import TargetError, resolve

    base = ["node", "/opt/dev.js"]
    for flavour in ("stdio", "ws", "unix", "principals"):
        target = resolve(f"conformance-device:{flavour}", device_command="node /opt/dev.js")
        assert target.command[:2] == base and "bhms.testing.conformance_device" not in " ".join(target.command), flavour
        if target.extra_command:
            assert target.extra_command[:2] == base
    default = resolve("conformance-device")
    assert default.command[1:3] == ["-m", "bhms.testing.conformance_device"]
    with pytest.raises(TargetError, match="conformance-device fixtures only"):
        resolve("gateway", device_command="node x.js")
    with pytest.raises(TargetError, match="empty"):
        resolve("conformance-device", device_command="  ")


async def test_cli_device_command_launches_the_given_device_with_the_runners_fixtures(tmp_path):
    out = tmp_path / "report.json"
    command = f"{sys.executable} -m bhms.testing.conformance_device"  # any implementation's device goes here
    result = await invoke("conformance", "conformance-device", "--device-command", command, "--only", "lifecycle.nan-tokens", "--json", str(out),
                          "--seed", "3", "--allow-unproven", env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "lifecycle.nan-tokens" in [c["check"] for c in json.loads(out.read_text())["checks"] if c["status"] == "passed"]
    refused = await invoke("conformance", "gateway", "--device-command", command, "--json", "-", env={"COLUMNS": "200"})
    assert refused.exit_code == 2, refused.output
