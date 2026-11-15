"""The gateway the conformance runner builds for itself: two conformance devices (``u0``, ``u1``) behind a policy with
named principals.

``gateway_toml`` renders the configuration; ``ROLES`` are the principals (``admin``; ``agent`` with ``invoke:u0/*/*`` and a
100 mm position bound; ``reader``; ``stopper``; ``nobody``; ``globber`` with the glob ``invoke:u0/axis-1/*``; ``exact`` with the
literal ``invoke:u0/axis-1/overdrive``; ``resolver`` with ``operations:read`` and ``operations:resolve``). Upstreams are device servers the runner starts on Unix sockets
(``python -m bhms.testing.conformance_device unix:<path> --gateway``), so the runner can also reach them directly to inject
faults while observing through the gateway (``--upstream``).

Thread-safety: pure functions.
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Role:
    """A principal of the gateway fixture: its scopes and, optionally, bounds that narrow device bounds and cumulative
    budgets (7.4.1)."""

    scopes: tuple[str, ...]
    bounds: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    budgets: tuple[dict[str, object], ...] = ()


GRANT_PROGRAM: dict[str, object] = {
    "bhmsProgram": "2026-11-15", "name": "conformance_grant", "maxDurationMs": 10_000,
    "description": "One pulse of axis-1: the reviewed program the programmer role may run without invoke scope.",
    "input": {"type": "object", "additionalProperties": False, "properties": {}},
    "steps": [{"kind": "invoke", "deviceId": "axis-1", "action": "pulse", "arguments": {"count": 1}}]}
"""The program of the ``programmer`` role's program-scoped grant (BHMS-PRG-023); device-local ids (programs are served by
device servers)."""


def _grant_scope() -> str:
    from bhms.protocol.canonical import digest

    return f"programs:run:{digest(GRANT_PROGRAM)}"


ROLES: dict[str, Role] = {
    "admin": Role(("admin",)),
    "agent": Role(("read", "lease", "invoke:u0/*/*", "programs:run"),
                  {"u0/axis-1/move_to": {"position": {"maximum": 100}}}),
    "reader": Role(("read",)),
    "stopper": Role(("stop",)),
    "nobody": Role(()),
    "globber": Role(("read", "lease", "invoke:u0/axis-1/*")),
    "exact": Role(("read", "lease", "invoke:u0/axis-1/overdrive")),
    "resolver": Role(("read", "operations:read", "operations:resolve")),
    "budgeted": Role(("read", "invoke:u0/axis-1/pulse"), budgets=(
        {"id": "pulses", "action": "u0/axis-1/pulse", "quantity": "/count", "unit": "1", "total": 5},)),
    "budgeted-restart": Role(("read", "invoke:u0/axis-1/pulse"), budgets=(
        {"id": "pulses-durable", "action": "u0/axis-1/pulse", "quantity": "/count", "unit": "1", "total": 1000},)),
    "programmer": Role(("read", "lease", _grant_scope())),
}
TOKEN_PREFIX = "conformance-token-"
NAMESPACES = ("u0", "u1")


def gateway_toml(flavour: str, url: str | None, state: Path | None, principals: dict[str, Role],
                 upstream_urls: dict[str, str]) -> str:
    """The configuration of the fixture gateway; ``upstream_urls`` maps namespace to the upstream's ``unix:`` URL; empty means each upstream is a stdio child of this gateway."""
    from bhms.runtime.authority import token_digest

    listen = {"stdio": '"stdio"', "ws": f'"{url}"', "http": f'"{url}"'}[flavour]
    lines = ["[gateway]", 'id = "conformance-gateway"', f'state_dir = "{state}"', f"listen = [{listen}]", "upstream_timeout_ms = 10000",
             'instructions = "Conformance gateway: two simulated conformance devices."', ""]
    for name in NAMESPACES:
        if upstream_urls:
            lines += ["[[upstream]]", f'name = "{name}"', f'url = "{upstream_urls[name]}"', ""]
        else:  # the spare gateway of a stdio fixture owns its upstreams: separate processes, separate lease arbitration
            lines += ["[[upstream]]", f'name = "{name}"', 'stdio = "{python} -m bhms.testing.conformance_device --memory"', ""]
    for role, spec in principals.items():
        lines += [f"[principals.{role}]", f'tokens = ["{token_digest(TOKEN_PREFIX + role)}"]',
                  "scopes = [" + ", ".join(f'"{s}"' for s in spec.scopes) + "]"]
        if spec.bounds:
            parts = []
            for action, members in spec.bounds.items():
                inner = ", ".join(f"{m} = {{ {', '.join(f'{k} = {v}' for k, v in b.items())} }}" for m, b in members.items())
                parts.append(f'"{action}" = {{ {inner} }}')
            lines.append("bounds = { " + ", ".join(parts) + " }")
        if spec.budgets:
            lines.append("budgets = [" + ", ".join(
                "{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in budget.items()) + " }" for budget in spec.budgets) + "]")
        lines.append("")
    return "\n".join(lines)


def localize_roles(roles: dict[str, Role]) -> dict[str, Role]:
    """Roles written for the gateway (ids under ``u0/``) as a single device server sees them: no namespace, and ``agent``
    may invoke only on ``axis-1`` (so ``pump-1`` is outside its grant)."""
    def local(text: str) -> str:
        return text.replace("u0/*/*", "axis-1/*").replace("u0/", "")

    return {name: Role(tuple(local(s) for s in role.scopes),
                       {local(action): members for action, members in role.bounds.items()},
                       tuple({**b, "action": local(str(b["action"]))} for b in role.budgets)) for name, role in roles.items()}


def device_roles() -> dict[str, Role]:
    """The principals for ``conformance-device --principals``."""
    return localize_roles(ROLES)


def device_policy_document(principals: dict[str, Role]) -> dict[str, dict[str, object]]:
    """A ``GatewayPolicy`` document (``{"principals": ...}``) for :class:`bhms.runtime.authority.Policy.from_document`."""
    from bhms.runtime.authority import token_digest

    out: dict[str, dict[str, object]] = {}
    for name, role in principals.items():
        entry: dict[str, object] = {"tokens": [token_digest(TOKEN_PREFIX + name)], "scopes": list(role.scopes)}
        if role.bounds:
            entry["bounds"] = {action: members for action, members in role.bounds.items()}
        if role.budgets:
            entry["budgets"] = [dict(b) for b in role.budgets]
        out[name] = entry
    return {"principals": out}
