"""Check model: results, outcomes and the registry that :func:`check` fills.

A *check* is an async function ``(c: Context) -> None`` that cites the requirement IDs it covers. It passes by returning,
fails by raising :class:`CheckFailed` (use ``c.expect`` / ``c.fail``), and is not applicable or skipped by raising
:class:`NotApplicable` or :class:`Skipped` with a reason (BHMS-CNF-002: a skipped row is never a pass).

``generic`` checks use only a device's own description and work against any BHMS server; the others rely on the
documented contract of the conformance device (``bhms.testing.conformance_device``) and are not applicable to a
server that does not advertise the ``org.bhms/conformance`` extension. ``effects`` checks execute actions: against a
non-conformance server they run only with ``--allow-effects``.

Thread-safety: the registry is filled at import time and read-only afterwards.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROFILES = ("core", "authority", "leases", "events", "programs", "registry", "gateway", "compact", "ws", "http", "agent")
CAPABILITY_PROFILES = {"leases": "leases", "events": "events", "programs": "programs", "registry": "programs.registry",
                       "authority": "authority"}


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not-applicable"


class CheckFailed(AssertionError):
    """The behaviour under test violates a requirement. ``ids`` narrows the failure to the requirements of the check that the
    failing assertion is about; the others are then reported as not proven (the check stopped before proving them)."""

    def __init__(self, message: str, ids: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.ids = ids


class Skipped(Exception):
    """The check could not run (missing means, not missing capability); the rows it covers stay unproven."""


class NotApplicable(Exception):
    """The requirement does not apply to this target (for example a capability that is not advertised)."""


@dataclass(frozen=True)
class CheckSpec:
    name: str
    ids: tuple[str, ...]
    profile: str
    fn: Callable[[Any], Awaitable[None]]
    generic: bool = False
    effects: bool = False
    needs: tuple[str, ...] = ()
    timeout: float = 60.0
    doc: str = ""


@dataclass
class CheckResult:
    name: str
    status: Status
    ids: tuple[str, ...]
    profile: str
    generic: bool
    message: str = ""
    seconds: float = 0.0
    failed_ids: tuple[str, ...] = ()
    """For an observer check: only these of ``ids`` failed."""
    warnings: tuple[str, ...] = ()
    """SHOULD-level findings of a check that passed its MUST parts."""

    def to_json(self) -> dict[str, Any]:
        out = {"check": self.name, "status": self.status.value, "requirements": list(self.ids), "profile": self.profile,
               "generic": self.generic, "message": self.message, "seconds": round(self.seconds, 3)}
        if self.failed_ids:
            out["failedRequirements"] = list(self.failed_ids)
        if self.warnings:
            out["warnings"] = list(self.warnings)
        return out


@dataclass
class RequirementRow:
    id: str
    level: str
    profile: str
    method: str
    status: Status
    reason: str = ""
    checks: tuple[str, ...] = ()
    unproven: bool = False
    """Skipped although an automated check exists: the claim is unsupported until it runs (exemptions are not unproven)."""


REGISTRY: list[CheckSpec] = []


def check(name: str, ids: list[str], *, profile: str = "core", generic: bool = False, effects: bool = False,
          needs: tuple[str, ...] = (), timeout: float = 60.0) -> Callable[[Callable[[Any], Awaitable[None]]], Callable[[Any], Awaitable[None]]]:
    """Register a check. ``needs`` lists capabilities/means the runner must find (see :mod:`bhms.conformance.runner`)."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")

    def register(fn: Callable[[Any], Awaitable[None]]) -> Callable[[Any], Awaitable[None]]:
        if any(spec.name == name for spec in REGISTRY):
            raise ValueError(f"duplicate check name {name!r}")
        REGISTRY.append(CheckSpec(name, tuple(ids), profile, fn, generic, effects, needs, timeout, (fn.__doc__ or "").strip()))
        return fn

    return register


@dataclass
class Observation:
    """What a whole-run observer concluded: requirement id -> list of violations (empty list = observed and fine)."""

    findings: dict[str, list[str]] = field(default_factory=dict)

    def ok(self, rid: str) -> None:
        self.findings.setdefault(rid, [])

    def bad(self, rid: str, message: str) -> None:
        bucket = self.findings.setdefault(rid, [])
        if len(bucket) < 5:
            bucket.append(message)
