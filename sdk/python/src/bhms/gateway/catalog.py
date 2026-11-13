"""The aggregated device catalog of a gateway (spec/bhms/04-devices.md BHMS-DEV-002, 13-security.md BHMS-SEC-022).

Every device of every upstream is served as ``<namespace>/<upstream device id>`` (the namespace is the upstream's
configured name and never contains ``/``, so the split is unambiguous and ids stay unique and stable across gateway
restarts, BHMS-DEV-002). A *gateway description* is the upstream's verified description with its ``deviceId`` and every
resource id (device, action and property level) prefixed the same way, and a fresh ``digest`` (BHMS-DEV-021): the gateway
serves its own bytes, so its digest is its own. Descriptions are cached by upstream digest; a gateway description is
built once per (upstream digest, narrowing) and shared.

:class:`Catalog` keeps the entries in a sorted list (code-point order, BHMS-LIF-062) so a page of ``devices/list`` is a
bisect plus a slice, independent of how many devices there are; the set of resource ids the gateway can lease is
maintained incrementally. Entries of an upstream that is down stay (their devices read as ``offline``).

:class:`CatalogEntry` also provides the small interface :class:`~bhms.server.listen.Subscriptions` expects of a device
(``device_id``, ``properties[name].observable``), so one subscription implementation serves a device server and a gateway.

Thread-safety: one event loop.
"""

from __future__ import annotations

import bisect
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from bhms.protocol.canonical import digest
from bhms.server.validation import ArgumentValidator

log = logging.getLogger("bhms.gateway.catalog")

MAX_ID = 128


def gateway_id(namespace: str, upstream_id: str) -> str:
    return f"{namespace}/{upstream_id}"


@dataclass(frozen=True, slots=True)
class PropertyView:
    """The part of a property description subscriptions need."""

    observable: bool
    read_effect: str
    resources: tuple[str, ...]


def gateway_description(namespace: str, description: dict[str, Any]) -> dict[str, Any]:
    """``description`` as the gateway serves it (ids prefixed, digest recomputed); raises ``ValueError`` when an id no
    longer fits the 128-character limit."""

    def rid(resource: str) -> str:
        out = f"{namespace}/{resource}"
        if len(out) > MAX_ID:
            raise ValueError(f"resource id {out!r} exceeds {MAX_ID} characters")
        return out

    body = {k: v for k, v in description.items() if k != "digest"}
    device_id = gateway_id(namespace, body["deviceId"])
    if len(device_id) > MAX_ID:
        raise ValueError(f"device id {device_id!r} exceeds {MAX_ID} characters")
    body["deviceId"] = device_id
    body["resources"] = [rid(r) for r in body.get("resources", [])]
    for section in ("actions", "properties"):
        members = {}
        for name, member in body.get(section, {}).items():
            if member.get("resources"):
                member = {**member, "resources": [rid(r) for r in member["resources"]]}
            members[name] = member
        body[section] = members
    body["digest"] = digest(body)
    return body


@dataclass
class CatalogEntry:
    """One served device: its upstream identity, the upstream's own description and the gateway forms of it."""

    device_id: str
    namespace: str
    upstream_id: str
    upstream_description: dict[str, Any]
    upstream_summary: dict[str, Any]
    description: dict[str, Any]
    resources: tuple[str, ...]
    served: dict[str | None, tuple[dict[str, Any], str]] = field(default_factory=dict)
    validators: dict[str, ArgumentValidator] = field(default_factory=dict)
    _properties: dict[str, PropertyView] | None = None

    @property
    def digest(self) -> str:
        return self.description["digest"]

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self.description.get("capabilities", ()))

    @property
    def properties(self) -> dict[str, PropertyView]:
        if self._properties is None:
            self._properties = {n: PropertyView(bool(p.get("observable")), p.get("readEffect", "none"),
                                                tuple(p.get("resources") or self.description.get("resources", ())))
                                for n, p in self.description.get("properties", {}).items()}
        return self._properties

    def action(self, name: str) -> dict[str, Any] | None:
        return self.description["actions"].get(name)

    def validator(self, action: str) -> ArgumentValidator:
        """The (cached) argument validator of ``action`` over the *device's* own input schema."""
        found = self.validators.get(action)
        if found is None:
            found = self.validators[action] = ArgumentValidator(self.description["actions"][action]["input"])
        return found

    def action_resources(self, action: str) -> tuple[str, ...]:
        spec = self.description["actions"][action]
        return tuple(spec.get("resources") or ())


class Catalog:
    """All devices of all upstreams, in device-id order; see the module docstring."""

    def __init__(self) -> None:
        self._entries: dict[str, CatalogEntry] = {}
        self._ids: list[str] = []
        self._resource_refs: dict[str, int] = {}
        self.resource_set: set[str] = set()
        self.version = 0

    # ------------------------------------------------------------------ queries (also the Subscriptions interface)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, device_id: object) -> bool:
        return device_id in self._entries

    def get(self, device_id: str, default: Any = None) -> CatalogEntry | Any:
        return self._entries.get(device_id, default)

    def __getitem__(self, device_id: str) -> CatalogEntry:
        return self._entries[device_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._ids)

    def entries_of(self, namespace: str) -> list[CatalogEntry]:
        return [e for e in self._entries.values() if e.namespace == namespace]

    def after(self, device_id: str | None) -> Iterator[CatalogEntry]:
        """Entries with an id strictly greater than ``device_id`` (all of them when None), in order."""
        index = 0 if device_id is None else bisect.bisect_right(self._ids, device_id)
        for position in range(index, len(self._ids)):
            yield self._entries[self._ids[position]]

    def resources(self) -> set[str]:
        """The resource ids the gateway can lease (for the lease manager)."""
        return self.resource_set

    # ------------------------------------------------------------------ changes

    def replace_upstream(self, namespace: str, descriptions: dict[str, dict[str, Any]],
                         summaries: dict[str, dict[str, Any]]) -> bool:
        """Make the catalog's devices of ``namespace`` exactly ``descriptions``; True when anything changed."""
        changed = False
        wanted: dict[str, tuple[str, dict[str, Any]]] = {}
        for upstream_id, description in descriptions.items():
            wanted[gateway_id(namespace, upstream_id)] = (upstream_id, description)
        for current in [e for e in self._entries.values() if e.namespace == namespace]:
            if current.device_id not in wanted:
                self._remove(current)
                changed = True
        for device_id, (upstream_id, description) in sorted(wanted.items()):
            existing = self._entries.get(device_id)
            summary = summaries[upstream_id]
            if existing is not None and existing.upstream_description["digest"] == description["digest"]:
                existing.upstream_summary = summary
                continue
            try:
                served = gateway_description(namespace, description)
            except ValueError as exc:
                log.error("not serving %s: %s", device_id, exc)
                if existing is not None:
                    self._remove(existing)
                    changed = True
                continue
            entry = CatalogEntry(device_id, namespace, upstream_id, description, summary, served,
                                 tuple(served["resources"]))
            if existing is not None:
                self._remove(existing)
            self._add(entry)
            changed = True
        if changed:
            self.version += 1
        return changed

    def _add(self, entry: CatalogEntry) -> None:
        self._entries[entry.device_id] = entry
        bisect.insort(self._ids, entry.device_id)
        for resource in self._all_resources(entry):
            self._resource_refs[resource] = self._resource_refs.get(resource, 0) + 1
            self.resource_set.add(resource)

    def _remove(self, entry: CatalogEntry) -> None:
        del self._entries[entry.device_id]
        index = bisect.bisect_left(self._ids, entry.device_id)
        if index < len(self._ids) and self._ids[index] == entry.device_id:
            del self._ids[index]
        for resource in self._all_resources(entry):
            left = self._resource_refs.get(resource, 1) - 1
            if left <= 0:
                self._resource_refs.pop(resource, None)
                self.resource_set.discard(resource)
            else:
                self._resource_refs[resource] = left

    @staticmethod
    def _all_resources(entry: CatalogEntry) -> set[str]:
        found = set(entry.resources)
        for section in ("actions", "properties"):
            for member in entry.description.get(section, {}).values():
                found.update(member.get("resources") or ())
        return found


__all__ = ["Catalog", "CatalogEntry", "PropertyView", "gateway_description", "gateway_id"]
