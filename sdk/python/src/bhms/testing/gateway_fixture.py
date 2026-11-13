"""The gateway the conformance runner builds for itself: two conformance devices (``u0``, ``u1``) behind a policy with
named principals.

``gateway_toml`` renders the configuration; ``ROLES`` are the principals (``admin``; ``agent`` with ``invoke:u0/*/*`` and a
100 mm position bound; ``reader``; ``stopper``; ``nobody``; ``globber`` with the glob ``invoke:u0/axis-1/*``; ``exact`` with the
literal ``invoke:u0/axis-1/overdrive``). Upstreams are device servers the runner starts on Unix sockets
(``python -m bhms.testing.conformance_device unix:<path> --gateway``), so the runner can also reach them directly to inject
faults while observing through the gateway (``--upstream``).

Thread-safety: pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Role:
    """A principal of the gateway fixture: its scopes and, optionally, bounds that narrow device bounds."""

    scopes: tuple[str, ...]
    bounds: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)


ROLES: dict[str, Role] = {
    "admin": Role(("admin",)),
    "agent": Role(("read", "lease", "invoke:u0/*/*", "programs:run"),
                  {"u0/axis-1/move_to": {"position": {"maximum": 100}}}),
    "reader": Role(("read",)),
    "stopper": Role(("stop",)),
    "nobody": Role(()),
    "globber": Role(("read", "lease", "invoke:u0/axis-1/*")),
    "exact": Role(("read", "lease", "invoke:u0/axis-1/overdrive")),
}
TOKEN_PREFIX = "conformance-token-"
NAMESPACES = ("u0", "u1")


def gateway_toml(flavour: str, url: str | None, state: Path | None, principals: dict[str, Role],
                 upstream_urls: dict[str, str]) -> str:
    """The configuration of the fixture gateway; ``upstream_urls`` maps namespace to the upstream's ``unix:`` URL."""
    from bhms.runtime.authority import token_digest

    listen = {"stdio": '"stdio"', "ws": f'"{url}"', "http": f'"{url}"'}[flavour]
    lines = ["[gateway]", 'id = "conformance-gateway"', f'state_dir = "{state}"', f"listen = [{listen}]", "upstream_timeout_ms = 10000",
             'instructions = "Conformance gateway: two simulated conformance devices."', ""]
    for name in NAMESPACES:
        lines += ["[[upstream]]", f'name = "{name}"', f'url = "{upstream_urls[name]}"', ""]
    for role, spec in principals.items():
        lines += [f"[principals.{role}]", f'tokens = ["{token_digest(TOKEN_PREFIX + role)}"]',
                  "scopes = [" + ", ".join(f'"{s}"' for s in spec.scopes) + "]"]
        if spec.bounds:
            parts = []
            for action, members in spec.bounds.items():
                inner = ", ".join(f"{m} = {{ {', '.join(f'{k} = {v}' for k, v in b.items())} }}" for m, b in members.items())
                parts.append(f'"{action}" = {{ {inner} }}')
            lines.append("bounds = { " + ", ".join(parts) + " }")
        lines.append("")
    return "\n".join(lines)
