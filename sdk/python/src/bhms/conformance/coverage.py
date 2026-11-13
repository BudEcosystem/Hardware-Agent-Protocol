"""Requirement rows: which checks cover which ID, and why some IDs have no automated check.

:func:`rows` folds the check results of a run into one status per requirement of the claimed profiles (BHMS-CNF-002).
``EXEMPT`` lists every ID that no check can prove, with the reason; ``tests/test_conformance_runner.py::test_every_core_must_is_covered_or_has_a_recorded_reason`` asserts that every
other ``core`` MUST is covered by at least one registered check and that no exemption is stale.

Thread-safety: pure functions.
"""

from __future__ import annotations

from typing import Any

from bhms.conformance import requirements
from bhms.conformance.core import REGISTRY, CheckResult, RequirementRow, Status

INSPECTION = "inspection"
UNTESTABLE = "not-yet-testable"
NOT_APPLICABLE = "not-applicable"

EXEMPT: dict[str, tuple[str, str]] = {}
"""requirement id -> (kind, reason); filled by :mod:`bhms.conformance.exemptions`."""

from bhms.conformance.exemptions import EXEMPT as _EXEMPT  # noqa: E402

EXEMPT.update(_EXEMPT)


def covering(ids: set[str] | None = None) -> dict[str, list[str]]:
    """requirement id -> names of registered checks that cite it."""
    out: dict[str, list[str]] = {}
    for spec in REGISTRY:
        for rid in spec.ids:
            out.setdefault(rid, []).append(spec.name)
    from bhms.conformance.observers import observed_ids

    for rid in observed_ids():
        out.setdefault(rid, []).append("observers.all-traffic")
    return out


def rows(results: list[CheckResult], profiles: list[str], unavailable: dict[str, str], ctx: Any = None) -> list[RequirementRow]:
    by_id: dict[str, list[tuple[CheckResult, bool]]] = {}
    for result in results:
        for rid in result.ids:
            failed_here = result.status is Status.FAILED and (not result.failed_ids or rid in result.failed_ids)
            by_id.setdefault(rid, []).append((result, failed_here))
    out = []
    for row in requirements.for_profiles(set(profiles)):
        rid = row["id"]
        entries = by_id.get(rid, [])
        base = dict(id=rid, level=row["level"], profile=row["profile"], method=row["method"])
        failed = [(r, f) for r, f in entries if f]
        passed = [r for r, f in entries if r.status is Status.PASSED and not f]
        if failed:
            out.append(RequirementRow(status=Status.FAILED, reason=failed[0][0].message[:400],
                                      checks=tuple(r.name for r, _ in failed), **base))
        elif passed:
            out.append(RequirementRow(status=Status.PASSED, checks=tuple(r.name for r in passed), **base))
        elif entries and all(r.status is Status.FAILED for r, _ in entries):
            out.append(RequirementRow(status=Status.SKIPPED, checks=tuple(r.name for r, _ in entries), unproven=True, **base,
                                      reason=f"{entries[0][0].name} failed on another requirement before this one was proven"))
        elif entries:
            skipped = [r for r, _ in entries if r.status is Status.SKIPPED]
            chosen = skipped[0] if skipped else entries[0][0]
            status = Status.SKIPPED if skipped else Status.NOT_APPLICABLE
            out.append(RequirementRow(status=status, reason=chosen.message, checks=tuple(r.name for r, _ in entries),
                                      unproven=status is Status.SKIPPED, **base))
        elif rid == "BHMS-TRN-010" and ctx is not None and ctx.target.kind != "stdio":
            out.append(RequirementRow(status=Status.NOT_APPLICABLE, reason="stdio framing only; the other bindings frame messages themselves",
                                      **base))
        elif rid in EXEMPT:
            kind, reason = EXEMPT[rid]
            status = Status.NOT_APPLICABLE if kind == NOT_APPLICABLE else Status.SKIPPED
            out.append(RequirementRow(status=status, reason=f"{kind}: {reason}", **base))
        else:
            out.append(RequirementRow(status=Status.SKIPPED, reason="no automated check implemented for this requirement",
                                      unproven=True, **base))
    return out
