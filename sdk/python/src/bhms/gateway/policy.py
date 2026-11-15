"""Gateway policy: scope refusals that name their rule, and the served (narrowed) descriptions
(spec/bhms/07-leases-and-authority.md §7.4, 13-security.md §13.2).

Authority itself — principals, scopes, the constant-time token check, ``invoke:`` globs and the hazardous-action rule —
is :mod:`bhms.runtime.authority`; the gateway adds what only a gateway has:

**Narrowed bounds are served, not just enforced.** A principal's policy ``bounds`` (``"<deviceId>/<action>": {member:
{minimum?, maximum?, enum?}}``) are intersected with the device's schema (BHMS-AUTH-010); :meth:`GatewayPolicy.served`
returns the description *that principal* is given, with the effective bound written into the input schema, so an agent
plans against the limits that will be enforced and the description digest (BHMS-DEV-021) is that of the narrowed bytes.
An empty intersection makes the action unavailable: it is absent from the served description and ``actions/invoke``
answers ``UNAUTHORIZED`` (BHMS-AUTH-011). Principals without bounds on a device share the unnarrowed description.

**Policy only narrows** (BHMS-SEC-011): :meth:`GatewayPolicy.check_loadable` rejects, when a policy is loaded or replaced,
any bound that widens a device bound of a device the gateway already knows. Bounds for devices not described yet are kept
and are harmless — the effective envelope is an intersection, so it can never exceed the device's own.

**Every refusal names its rule.** :func:`refusal` builds the error with a stable rule id in both the message and the hint:

=====================  ==========================================================================
``scope:read``          the principal has no ``read`` scope (devices then read as unknown, BHMS-AUTH-002)
``scope:invoke``        no ``invoke:<pattern>`` covers the action or fresh read
``scope:hazardous``     a hazardous action needs a scope naming it literally (BHMS-AUTH-003)
``scope:lease``         no ``lease`` scope
``scope:stop``          no ``stop`` / ``stop:<glob>`` scope for the device
``scope:operations``    an operation of another principal without ``operations:read`` or ``admin``
``bounds:<member>``     the value is outside the principal's narrowed envelope
``bounds:empty``        the principal's bounds leave the action no allowed value
=====================  ==========================================================================

Thread-safety: one event loop; a :class:`GatewayPolicy` is replaced wholesale when the policy changes.
"""

from __future__ import annotations

import json
from typing import Any

from bhms.gateway.catalog import Catalog, CatalogEntry
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy, Principal, check_budgets
from bhms.server.validation import effective_bounds


def refusal(code: str, rule: str, message: str, *, hint: str, **kw: Any) -> BhmsError:
    """A gateway refusal that names the policy rule that decided it (message and hint both carry ``rule``)."""
    return BhmsError(code, f"{message} (gateway policy rule {rule})", hint=f"{hint} [rule: {rule}]", **kw)


def unauthorized(rule: str, principal: Principal, what: str, scope: str) -> BhmsError:
    return refusal("UNAUTHORIZED", rule, f"principal {principal.id!r} may not {what}",
                   hint=f"missing scope {scope}; ask the gateway operator to grant it (the gateway decides, "
                        "BHMS-SEC-031)")


class GatewayPolicy:
    """A loaded :class:`~bhms.runtime.authority.Policy` plus the narrowing it implies for served descriptions."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self._index: dict[str, dict[str, dict[str, dict[str, dict[str, Any]]]]] = {}

    def bounds_of(self, principal: Principal, device_id: str) -> dict[str, dict[str, dict[str, Any]]]:
        """``{action: {member: bound}}`` the principal's policy sets for ``device_id`` (empty when none)."""
        index = self._index.get(principal.id)
        if index is None:
            index = {}
            for key, members in principal.bounds.items():
                device, _, action = key.rpartition("/")
                index.setdefault(device, {})[action] = members
            self._index[principal.id] = index
        return index.get(device_id, {})

    # ------------------------------------------------------------------ served descriptions

    def served(self, entry: CatalogEntry, principal: Principal) -> tuple[dict[str, Any], str]:
        """``(description, digest)`` as served to ``principal`` (narrowed by its bounds; cached)."""
        bounds = self.bounds_of(principal, entry.device_id)
        signature = None if not bounds else json.dumps(bounds, sort_keys=True)
        found = entry.served.get(signature)
        if found is None:
            description = entry.description if signature is None else _narrow(entry.description, bounds)
            found = entry.served[signature] = (description, description["digest"])
            if len(entry.served) > 64:  # principals with distinct bounds are few; never grow without bound
                for stale in [k for k in entry.served if k != signature and k is not None][:32]:
                    del entry.served[stale]
        return found

    def summary(self, entry: CatalogEntry, principal: Principal, status: str) -> dict[str, Any]:
        """The ``DeviceSummary`` for ``devices/list`` (consistent with :meth:`served`: same digest and actions)."""
        description, served_digest = self.served(entry, principal)
        base = entry.upstream_summary
        return {**base, "deviceId": entry.device_id, "status": status, "digest": served_digest,
                "actions": sorted(description["actions"])}

    def envelope(self, entry: CatalogEntry, principal: Principal, action: str) -> dict[str, dict[str, Any]]:
        """The principal's raw policy bounds for ``action`` (applied by the argument validator)."""
        return self.bounds_of(principal, entry.device_id).get(action, {})

    def unavailable_actions(self, entry: CatalogEntry, principal: Principal) -> set[str]:
        """Actions whose envelope is empty for ``principal`` (BHMS-AUTH-011)."""
        description, _ = self.served(entry, principal)
        return set(entry.description["actions"]) - set(description["actions"])

    # ------------------------------------------------------------------ loading

    def check_loadable(self, catalog: Catalog) -> None:
        """Reject bounds that would widen a device bound (BHMS-SEC-011) and budgets that cannot measure an action they name
        (BHMS-AUTH-031); unknown devices are tolerated (admission refuses an unmeasurable action later)."""
        describe = lambda device_id: (e.description if (e := catalog.get(device_id)) else None)  # noqa: E731
        self.policy.check_bounds(describe, allow_unknown=True)
        check_budgets(self.policy, describe, sorted(catalog), allow_unknown=True)


def _narrow(description: dict[str, Any], bounds: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Write the effective envelope into the input schemas; drop actions whose envelope is empty."""
    actions = dict(description["actions"])
    for action, members in bounds.items():
        spec = actions.get(action)
        if spec is None:
            continue
        properties = dict(spec["input"].get("properties", {}))
        empty = False
        for member, bound in members.items():
            node = properties.get(member)
            if node is None:
                continue
            effective = effective_bounds(node, bound)
            if effective.get("empty"):
                empty = True
                break
            narrowed = {k: v for k, v in node.items() if k not in ("minimum", "maximum", "enum")}
            for keyword in ("minimum", "maximum", "enum"):
                if keyword in effective:
                    narrowed[keyword] = effective[keyword]
            properties[member] = narrowed
        if empty:
            del actions[action]
        else:
            actions[action] = {**spec, "input": {**spec["input"], "properties": properties}}
    body = {**{k: v for k, v in description.items() if k != "digest"}, "actions": actions}
    body["digest"] = digest(body)
    return body


__all__ = ["GatewayPolicy", "refusal", "unauthorized"]
