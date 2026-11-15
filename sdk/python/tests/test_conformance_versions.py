"""A conformance run tests one protocol version and says which (spec/bhms/14-conformance.md BHMS-CNF-007, BHMS-LIF-026).

Requirements added in 2026-11-15 (section 14.6) are not applicable to a 2026-11-13 run, so an implementation of v0.1 (the
TypeScript SDK until Task 15b) gets an honest v0.1 report, and a v0.2 claim needs every v0.2 row.
"""

from __future__ import annotations

from bhms.conformance import requirements
from bhms.conformance.core import Status
from bhms.conformance.runner import RunOptions, run
from bhms.protocol.version import V0_1


async def test_a_v0_1_run_marks_the_v0_2_rows_not_applicable_and_says_so():
    report = await run(RunOptions(target="conformance-device", profiles=("core",), only=("lifecycle.stateless", "lifecycle.earlier",
                                  "transport.credential", "operations.late-terminal"), protocol_version=V0_1, allow_unproven=True))
    assert report.meta["protocolVersion"] == V0_1
    later = {r["id"] for r in requirements.load() if r["since"] > V0_1}
    rows = {r.id: r for r in report.rows}
    for rid in later & set(rows):
        assert rows[rid].status is Status.NOT_APPLICABLE and "introduced in 2026-11-15" in rows[rid].reason, rid
    checks = {c.name: c for c in report.checks}
    assert checks["operations.late-terminal-report"].status is Status.NOT_APPLICABLE
    assert checks["lifecycle.stateless-connection"].status is Status.PASSED


async def test_the_default_run_tests_the_newest_shared_version():
    report = await run(RunOptions(target="conformance-device", profiles=("core",), only=("lifecycle.earlier-version",),
                                  allow_unproven=True))
    assert report.meta["protocolVersion"] == "2026-11-15"
    assert {c.name: c.status for c in report.checks}["lifecycle.earlier-version-behaviour"] is Status.PASSED


async def test_an_unknown_version_is_a_fatal_error_of_the_run():
    report = await run(RunOptions(target="conformance-device", protocol_version="1999-01-01"))
    assert report.fatal and report.exit_code == 2
