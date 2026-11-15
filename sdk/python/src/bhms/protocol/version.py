"""Protocol versions, the single source for every component (spec/bhms/03-lifecycle.md §3.3).

``PROTOCOL_VERSION`` is the revision this SDK implements (v0.2); ``SUPPORTED_VERSIONS`` lists every version its servers
serve and its clients speak, newest first. A request names its version in ``_meta["bhms/protocolVersion"]`` and is
answered with that version's behaviour: a ``2026-11-13`` (v0.1) request is never shown anything v0.1 did not define
(:func:`discover_for`), while every rule that protects a device (budgets, leases, scopes) applies whatever the version.
"""

from __future__ import annotations

import copy
from typing import Any

PROTOCOL_VERSION = "2026-11-15"
V0_1 = "2026-11-13"
SUPPORTED_VERSIONS: tuple[str, ...] = (PROTOCOL_VERSION, V0_1)


def is_v0_1(version: str | None) -> bool:
    """Whether a request speaks v0.1 (``2026-11-13``)."""
    return version == V0_1


def discover_for(result: dict[str, Any], version: str | None) -> dict[str, Any]:
    """``result`` of ``server/discover`` as a peer of ``version`` may see it.

    For a v0.1 request the members v0.2 added are left out (v0.1 message objects are closed, BHMS-LIF-015):
    ``capabilities.authority.budgets``, ``capabilities.programs.grants``, ``principal.budgets`` and every program-scoped
    grant (``programs:run:<digest>``) in ``principal.scopes``. A v0.2 result is returned unchanged.
    """
    if not is_v0_1(version):
        return result
    out = copy.copy(result)
    caps = dict(out.get("capabilities") or {})
    if "authority" in caps:
        caps["authority"] = {}
    if "programs" in caps:
        caps["programs"] = {k: v for k, v in caps["programs"].items() if k != "grants"}
    out["capabilities"] = caps
    principal = out.get("principal")
    if principal is not None:
        out["principal"] = {"id": principal["id"],
                            "scopes": [s for s in principal["scopes"] if not s.startswith("programs:run:")]}
    return out


__all__ = ["PROTOCOL_VERSION", "SUPPORTED_VERSIONS", "V0_1", "discover_for", "is_v0_1"]
