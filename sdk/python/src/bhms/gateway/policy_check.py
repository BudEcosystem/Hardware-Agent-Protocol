"""What a gateway policy grants, device by device (``bhms gateway check-policy <config>``).

Scope patterns are short and easy to get wrong: ``invoke:<deviceGlob>/<actionGlob>`` splits at the **last** ``/``, so behind
a gateway (device ids ``<namespace>/<device>``) ``invoke:knob/*`` names a device called ``knob`` and matches nothing; the
gateway then refuses everything, correctly and silently (Task 11, S7). :func:`check_policy` evaluates every scope of every
principal against the devices actually served, with the same matching code the gateway uses at admission
(:class:`~bhms.runtime.authority.Principal`), and reports what each scope matches and what looks like a mistake:

* a scope that matches nothing (with the likely intended spelling for the last-``/`` mistake);
* a string that is not a BHMS scope;
* hazardous actions a glob does not grant (BHMS-AUTH-003: they need a literal action name) — a note, not a warning;
* a principal that may act on a device but may not stop it (the agent then has no safe action on a fault; S5).

:func:`collect_devices` starts the configured upstreams without serving anything (no listener, journal in memory) and
returns their device descriptions. Thread-safety: pure functions; ``collect_devices`` runs on one event loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bhms.gateway.config import GatewayConfig
from bhms.runtime.authority import Principal

FIXED_SCOPES = {
    "read": "discover, list and describe every device, retained reads, events, its own operations",
    "lease": "leases/acquire, renew and release on any resource",
    "programs:run": "programs/run (each step still needs its invoke scope)",
    "programs:register": "programs/register",
    "operations:read": "see other principals' operations (never cancel them)",
    "operations:resolve": "operations/resolve: re-run reconciliation, and resolve an unknown operation with evidence",
    "admin": "everything, including other principals' operations",
}


@dataclass
class ScopeReport:
    """One scope of one principal: what it matches among the served devices."""

    scope: str
    matches: list[str] = field(default_factory=list)
    note: str | None = None
    warning: str | None = None

    def wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"scope": self.scope, "matches": self.matches}
        if self.note:
            out["note"] = self.note
        if self.warning:
            out["warning"] = self.warning
        return out


@dataclass
class PolicyReport:
    """The result of :func:`check_policy`: per principal its scopes, and warnings about the principal as a whole."""

    principals: dict[str, list[ScopeReport]]
    warnings: dict[str, list[str]]
    devices: int

    @property
    def warning_count(self) -> int:
        return sum(1 for rows in self.principals.values() for row in rows if row.warning) + sum(
            len(found) for found in self.warnings.values())

    def wire(self) -> dict[str, Any]:
        return {"devices": self.devices, "warnings": self.warning_count,
                "principals": {name: {"scopes": [row.wire() for row in rows], "warnings": self.warnings.get(name, [])}
                               for name, rows in self.principals.items()}}

    def render(self, *, limit: int = 12) -> str:
        """Plain text: one block per principal, one line per scope, at most ``limit`` matches spelled out per scope."""
        lines = [f"{self.devices} device{'s' if self.devices != 1 else ''} served"]
        for name, rows in self.principals.items():
            lines.append(f"\nprincipal {name}")
            for row in rows:
                shown = ", ".join(row.matches[:limit]) + (f", ... ({len(row.matches)} in all)" if len(row.matches) > limit else "")
                lines.append(f"  {row.scope}: {shown or 'matches nothing'}")
                if row.note:
                    lines.append(f"    note: {row.note}")
                if row.warning:
                    lines.append(f"    WARNING: {row.warning}")
            for warning in self.warnings.get(name, []):
                lines.append(f"  WARNING: {warning}")
        count = self.warning_count
        lines.append(f"\n{count} warning{'s' if count != 1 else ''}")
        return "\n".join(lines)


def _invoke_report(scope: str, devices: list[dict[str, Any]]) -> ScopeReport:
    only = Principal("check", (scope,))
    matches, skipped = [], []
    for device in devices:
        device_id, capabilities = device["deviceId"], tuple(device.get("capabilities") or ())
        for name, action in sorted((device.get("actions") or {}).items()):
            hazardous = action.get("effect") == "hazardous"
            if only.can_invoke(device_id, name, capabilities, hazardous):
                matches.append(f"{device_id}/{name}" + (" (hazardous)" if hazardous else ""))
            elif hazardous and only.can_invoke(device_id, name, capabilities, False):
                skipped.append(f"{device_id}/{name}")
        for name, prop in sorted((device.get("properties") or {}).items()):
            if prop.get("readEffect") == "transaction" and only.can_invoke(device_id, name, capabilities):
                matches.append(f"{device_id}/{name} (fresh transaction read)")
    report = ScopeReport(scope, sorted(matches))
    if skipped:
        report.note = (f"does not grant the hazardous {', '.join(skipped)}: a hazardous action needs a scope that names it "
                       "literally (BHMS-AUTH-003)")
    if not matches:
        report.warning = _no_invoke_match(scope, devices)
    return report


def _no_invoke_match(scope: str, devices: list[dict[str, Any]]) -> str:
    pattern = scope[len("invoke:"):]
    if pattern.startswith("cap:"):
        return f"matches no device capability; served capabilities: {sorted({c for d in devices for c in d.get('capabilities') or ()})}"
    if "/" not in pattern:
        return f"is not <deviceGlob>/<actionGlob>; write invoke:{pattern}/* for every action of the devices matching {pattern}"
    widened = Principal("check", (f"{scope}/*",))
    if any(widened.can_invoke(d["deviceId"], name, tuple(d.get("capabilities") or ()), a.get("effect") == "hazardous")
           for d in devices for name, a in (d.get("actions") or {}).items()):
        device_glob = pattern.rpartition("/")[0]
        return (f"matches nothing: the pattern splits at the last \"/\", so it names actions of a device {device_glob!r}, "
                f"which does not exist; for the actions of the devices matching {pattern} write {scope}/*")
    return "matches no action of any served device"


def _stop_report(scope: str, devices: list[dict[str, Any]]) -> ScopeReport:
    only = Principal("check", (scope,))
    report = ScopeReport(scope, sorted(d["deviceId"] for d in devices if only.can_stop(d["deviceId"])))
    if not report.matches:
        report.warning = "matches no device (stop:<glob> matches the whole device id, for example stop:bench/*)"
    return report


def check_policy(principals: Any, devices: list[dict[str, Any]]) -> PolicyReport:
    """Evaluate ``principals`` (:class:`~bhms.runtime.authority.Principal` objects) against ``devices`` (device
    descriptions, or dicts with ``deviceId``, ``capabilities``, ``actions`` and ``properties``)."""
    devices = sorted(devices, key=lambda d: d["deviceId"])
    everything = [d["deviceId"] for d in devices]
    out: dict[str, list[ScopeReport]] = {}
    warnings: dict[str, list[str]] = {}
    for principal in principals:
        rows = []
        for scope in principal.scopes:
            if scope.startswith("invoke:"):
                rows.append(_invoke_report(scope, devices))
            elif scope == "stop" or scope.startswith("stop:"):
                rows.append(_stop_report(scope, devices))
            elif scope == "read":
                rows.append(ScopeReport(scope, list(everything), note=FIXED_SCOPES[scope]))
            elif scope in FIXED_SCOPES:
                rows.append(ScopeReport(scope, [FIXED_SCOPES[scope]]))
            else:
                rows.append(ScopeReport(scope, warning="is not a BHMS scope and grants nothing (known: read, lease, "
                                                       "invoke:<deviceGlob>/<actionGlob>, invoke:cap:<capabilityGlob>, "
                                                       "stop, stop:<deviceGlob>, programs:run, programs:register, "
                                                       "operations:read, operations:resolve, admin)"))
        out[principal.id] = rows
        if not principal.admin:
            unstoppable = sorted(
                d["deviceId"] for d in devices if not principal.can_stop(d["deviceId"]) and any(
                    a.get("effect", "none") != "none" and principal.can_invoke(
                        d["deviceId"], name, tuple(d.get("capabilities") or ()), a.get("effect") == "hazardous")
                    for name, a in (d.get("actions") or {}).items()))
            if unstoppable:
                warnings[principal.id] = [
                    f"may act on {', '.join(unstoppable)} but may not stop {'it' if len(unstoppable) == 1 else 'them'}: on a "
                    "fault the principal has no safe action; grant " + ", ".join(f"stop:{d}" for d in unstoppable)
                    + " (bhms.runtime.authority.agent_scopes)"]
    return PolicyReport(out, warnings, len(devices))


async def collect_devices(config: GatewayConfig) -> list[dict[str, Any]]:
    """Start the configured upstreams (nothing is served, the journal is in memory), wait until they are connected and
    return the descriptions of the devices the gateway would serve, under the ids it would serve them."""
    from dataclasses import replace

    from bhms.gateway.gateway import Gateway

    gateway = Gateway(replace(config, listen=()), memory=True)
    await gateway.start()
    try:
        return [gateway.catalog.get(device_id).description for device_id in gateway.catalog]
    finally:
        await gateway.close()


__all__ = ["PolicyReport", "ScopeReport", "check_policy", "collect_devices"]
