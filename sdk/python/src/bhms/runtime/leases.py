"""Leases with TTL and per-resource fences (spec/bhms/07-leases-and-authority.md §7.2–7.3).

* ``acquire`` is all-or-nothing and never holds a subset while it waits (BHMS-LSE-001); a conflict that outlasts
  ``waitMs`` is ``LEASE_CONFLICT`` naming the conflicting resources and when the blocking lease expires, never the
  holder (BHMS-LSE-002).
* Every grant takes the next value of the server-wide fence counter, committed with fsync before the lease exists, so
  fences strictly increase across restarts; renew keeps the fence (BHMS-LSE-003).
* TTL and waits are range-checked (BHMS-LSE-004); a lease belongs to its principal (BHMS-LSE-005); expiry runs on the
  monotonic clock, with a timer per lease and a lazy check on every use (BHMS-LSE-006); unknown ids read as expired
  (BHMS-LSE-007).
* :meth:`LeaseManager.check` is the admission and pre-dispatch check of BHMS-LSE-010 with its exact codes.
* :meth:`LeaseManager.revoke_covering` (``stop``) revokes active leases and raises the fence of their resources so a
  superseded holder is ``FENCED``.

Leases are not persisted: after a restart every earlier lease id is unknown (``LEASE_EXPIRED``), while the fence counter
continues. ``on_end(lease, reason)`` lets the server apply ``onLeaseLoss`` to running operations (BHMS-LSE-012) and
record ``lease.expired``/``lease.revoked`` events.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import iso, new_id, now_ns
from bhms.runtime.store import Store, StoreError

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal


@dataclass
class Lease:
    """A lease as held by the server (``expires_mono`` drives expiry; the wall times are for display)."""

    lease_id: str
    principal: str
    resources: tuple[str, ...]
    fence: int
    state: str
    acquired_ns: int
    ttl_ms: int
    expires_mono: float
    expires_ns: int
    timer: asyncio.TimerHandle | None = None

    def wire(self) -> dict[str, Any]:
        return {"leaseId": self.lease_id, "resources": list(self.resources), "fence": self.fence,
                "state": self.state, "acquiredAt": iso(self.acquired_ns), "expiresAt": iso(self.expires_ns),
                "ttlMs": self.ttl_ms}


class LeaseManager:
    """Leases of one server; see the module docstring.

    Args:
        store: provides the durable fence counter.
        resources: callable returning the set of resource ids the server knows (BHMS-LSE-004).
        on_end: ``(lease, "expired" | "revoked")`` callback.
    """

    def __init__(self, store: Store, *, resources: Callable[[], set[str]], min_ttl_ms: int = 1000,
                 max_ttl_ms: int = 600_000, max_wait_ms: int = 30_000,
                 on_end: Callable[[Lease, str], None] | None = None, remember: int = 4096) -> None:
        self.store = store
        self.min_ttl_ms, self.max_ttl_ms, self.max_wait_ms = min_ttl_ms, max_ttl_ms, max_wait_ms
        self._resources = resources
        self._on_end = on_end
        self._leases: OrderedDict[str, Lease] = OrderedDict()
        self._holder: dict[str, str] = {}
        self._highest: dict[str, int] = {}
        self._changed = asyncio.Event()
        self._remember = remember

    @property
    def capability(self) -> dict[str, int]:
        return {"minTtlMs": self.min_ttl_ms, "maxTtlMs": self.max_ttl_ms, "maxWaitMs": self.max_wait_ms}

    # ------------------------------------------------------------------ queries

    def get(self, lease_id: str) -> Lease | None:
        lease = self._leases.get(lease_id)
        if lease is not None:
            self._expire_if_due(lease)
        return lease

    def active(self) -> list[Lease]:
        return [lease for lease in list(self._leases.values()) if not self._expire_if_due(lease)
                and lease.state == "active"]

    def holder_of(self, resource: str) -> Lease | None:
        lease_id = self._holder.get(resource)
        lease = self._leases.get(lease_id) if lease_id else None
        if lease is None or self._expire_if_due(lease) or lease.state != "active":
            return None
        return lease

    def held_by(self, principal_id: str, resources: Iterable[str]) -> Lease | None:
        """An active lease of ``principal_id`` covering every one of ``resources`` (BHMS-OBS-011)."""
        needed = set(resources)
        for lease in self.active():
            if lease.principal == principal_id and needed.issubset(lease.resources):
                return lease
        return None

    # ------------------------------------------------------------------ acquire / renew / release

    def _check_ttl(self, ttl_ms: int) -> None:
        if not self.min_ttl_ms <= ttl_ms <= self.max_ttl_ms:
            raise BhmsError("OUT_OF_RANGE", f"ttlMs {ttl_ms} is outside [{self.min_ttl_ms}, {self.max_ttl_ms}]",
                            field="ttlMs", bound={"minimum": self.min_ttl_ms, "maximum": self.max_ttl_ms},
                            hint=f"send ttlMs between {self.min_ttl_ms} and {self.max_ttl_ms} and renew before it "
                                 "expires")

    async def acquire(self, principal: Principal, resources: list[str], ttl_ms: int,
                      wait_ms: int | None = None) -> Lease:
        """All-or-nothing grant over ``resources`` (BHMS-LSE-001..004)."""
        self._check_ttl(ttl_ms)
        wait = wait_ms or 0
        if wait > self.max_wait_ms:
            raise BhmsError("OUT_OF_RANGE", f"waitMs {wait} is above the maximum {self.max_wait_ms}", field="waitMs",
                            bound={"maximum": self.max_wait_ms}, hint=f"send waitMs of at most {self.max_wait_ms}")
        known = self._resources()
        for index, resource in enumerate(resources):
            if resource not in known:
                raise BhmsError("INVALID_ARGUMENT", f"resources[{index}] {resource!r} is not a resource of this "
                                "server", field=f"resources[{index}]",
                                hint="use resource ids from the device descriptions (devices/describe .resources)")
        if len(set(resources)) != len(resources):
            raise BhmsError("INVALID_ARGUMENT", "resources lists a resource twice", field="resources",
                            hint="list each resource once")
        deadline = time.monotonic() + wait / 1000
        while True:
            blocking = [(r, lease) for r in resources if (lease := self.holder_of(r)) is not None]
            if not blocking:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                soonest = min(lease.expires_mono for _, lease in blocking)
                expires_in = max(0, math.ceil((soonest - time.monotonic()) * 1000))
                raise BhmsError("LEASE_CONFLICT", f"{', '.join(sorted({r for r, _ in blocking}))} "
                                f"{'is' if len(blocking) == 1 else 'are'} leased by another holder",
                                field="resources", bound=sorted({r for r, _ in blocking}),
                                hint=f"the blocking lease expires in {expires_in} ms unless renewed; retry later or "
                                     "pass waitMs")
            self._changed.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._changed.wait(), remaining)
        fence = self.store.next_counter("fence")  # durable before the grant (BHMS-LSE-003)
        now_mono, wall = time.monotonic(), now_ns()
        lease = Lease(new_id("lease"), principal.id, tuple(resources), fence, "active", wall, ttl_ms,
                      now_mono + ttl_ms / 1000, wall + ttl_ms * 1_000_000)
        for resource in resources:
            self._holder[resource] = lease.lease_id
            self._highest[resource] = max(self._highest.get(resource, 0), fence)
        self._leases[lease.lease_id] = lease
        self._arm(lease)
        self._trim()
        return lease

    def _owned(self, principal: Principal, lease_id: str) -> Lease:
        lease = self.get(lease_id)
        if lease is None:
            raise BhmsError("LEASE_EXPIRED", f"lease {lease_id} is unknown or long expired", field="leaseId",
                            hint="acquire a new lease with leases/acquire")
        if lease.principal != principal.id:
            raise BhmsError("LEASE_CONFLICT", f"lease {lease_id} belongs to another principal", field="leaseId",
                            hint="use a lease you acquired yourself")
        return lease

    def renew(self, principal: Principal, lease_id: str, ttl_ms: int) -> Lease:
        """Extend an active lease; the fence is unchanged (BHMS-LSE-003, BHMS-LSE-006)."""
        self._check_ttl(ttl_ms)
        lease = self._owned(principal, lease_id)
        if lease.state == "revoked":
            raise BhmsError("FENCED", f"lease {lease_id} was revoked", field="leaseId",
                            hint="a stop or policy revoked it; acquire a new lease")
        if lease.state != "active":
            raise BhmsError("LEASE_EXPIRED", f"lease {lease_id} is {lease.state}", field="leaseId",
                            hint="acquire a new lease with leases/acquire")
        now_mono, wall = time.monotonic(), now_ns()
        lease.ttl_ms = ttl_ms
        lease.expires_mono = now_mono + ttl_ms / 1000
        lease.expires_ns = wall + ttl_ms * 1_000_000
        self._arm(lease)
        return lease

    def release(self, principal: Principal, lease_id: str) -> Lease:
        """Release an active lease; a lease that is not active is returned unchanged (BHMS-LSE-006)."""
        lease = self._owned(principal, lease_id)
        if lease.state == "active":
            self._end(lease, "released")
        return lease

    # ------------------------------------------------------------------ fencing

    def check(self, principal: Principal, lease_id: str | None, resources: Iterable[str]) -> Lease:
        """The admission/pre-dispatch check of BHMS-LSE-010; returns the lease or raises its exact refusal."""
        needed = list(resources)
        if lease_id is None:
            raise BhmsError("LEASE_REQUIRED", f"this needs a lease on {', '.join(needed)}", field="leaseId", bound=needed,
                            hint=f"acquire a lease on {', '.join(needed)} with leases/acquire and pass its leaseId")
        lease = self.get(lease_id)
        if lease is None or lease.state in ("expired", "released"):
            state = "unknown" if lease is None else lease.state
            raise BhmsError("LEASE_EXPIRED", f"lease {lease_id} is {state}", field="leaseId",
                            hint="acquire a new lease with leases/acquire")
        if lease.state == "revoked":
            raise BhmsError("FENCED", f"lease {lease_id} was revoked", field="leaseId",
                            hint="a stop or policy revoked it; acquire a new lease")
        if lease.principal != principal.id:
            raise BhmsError("LEASE_CONFLICT", f"lease {lease_id} belongs to another principal", field="leaseId",
                            hint="use a lease you acquired yourself")
        missing = [r for r in needed if r not in lease.resources]
        if missing:
            raise BhmsError("LEASE_CONFLICT", f"lease {lease_id} does not cover {', '.join(missing)}",
                            field="leaseId", bound=missing,
                            hint=f"acquire a lease that covers {', '.join(needed)}")
        superseded = [r for r in needed if self._highest.get(r, 0) > lease.fence]
        if superseded:
            raise BhmsError("FENCED", f"lease {lease_id} was superseded on {', '.join(superseded)}", field="leaseId",
                            hint="a newer lease exists for these resources; acquire a new lease")
        return lease

    def revoke_covering(self, resources: Iterable[str], *, reason: str = "stop") -> list[Lease]:
        """Revoke every active lease covering any of ``resources`` and raise their fences (BHMS-AUTH-021)."""
        wanted = set(resources)
        return self._revoke([lease for lease in self.active() if wanted.intersection(lease.resources)])

    def revoke(self, lease_id: str) -> Lease | None:
        """Revoke one active lease (a gateway whose upstream lease was lost) and raise the fence of its resources;
        None when it is unknown or not active."""
        lease = self.get(lease_id)
        revoked = self._revoke([lease]) if lease is not None and lease.state == "active" else []
        return revoked[0] if revoked else None

    def _revoke(self, revoked: list[Lease]) -> list[Lease]:
        if not revoked:
            return []
        try:
            fence: int | None = self.store.next_counter("fence")
        except StoreError:
            fence = None  # journal unwritable (BHMS-AUTH-025): revoked leases are FENCED by state alone
        for lease in revoked:
            if fence is not None:
                for resource in lease.resources:
                    self._highest[resource] = max(self._highest.get(resource, 0), fence)
            self._end(lease, "revoked")
        return revoked

    def revoke_principal(self, principal_id: str) -> list[Lease]:
        """Revoke the active leases of a principal whose ``lease`` scope was removed (BHMS-AUTH-013)."""
        found = [lease for lease in self.active() if lease.principal == principal_id]
        for lease in found:
            self._end(lease, "revoked")
        return found

    # ------------------------------------------------------------------ expiry

    def _arm(self, lease: Lease) -> None:
        if lease.timer is not None:
            lease.timer.cancel()
        loop = asyncio.get_running_loop()
        lease.timer = loop.call_at(loop.time() + max(0.0, lease.expires_mono - time.monotonic()),
                                   self._expire_if_due, lease)

    def _expire_if_due(self, lease: Lease) -> bool:
        """Expire ``lease`` when its TTL has passed on the monotonic clock; True if it is (now) expired."""
        if lease.state != "active":
            return lease.state == "expired"
        if time.monotonic() < lease.expires_mono:
            if lease.timer is None or lease.timer.cancelled():
                self._arm(lease)
            return False
        self._end(lease, "expired")
        return True

    def _end(self, lease: Lease, state: str) -> None:
        lease.state = state
        if lease.timer is not None:
            lease.timer.cancel()
            lease.timer = None
        for resource in lease.resources:
            if self._holder.get(resource) == lease.lease_id:
                del self._holder[resource]
        self._changed.set()
        if state in ("expired", "revoked") and self._on_end is not None:
            self._on_end(lease, state)

    def _trim(self) -> None:
        while len(self._leases) > self._remember:
            oldest_id, oldest = next(iter(self._leases.items()))
            if oldest.state == "active":
                self._leases.move_to_end(oldest_id)
                if all(lease.state == "active" for lease in self._leases.values()):
                    return
                continue
            del self._leases[oldest_id]

    def close(self) -> None:
        for lease in self._leases.values():
            if lease.timer is not None:
                lease.timer.cancel()
                lease.timer = None


__all__ = ["Lease", "LeaseManager"]
