"""Cross-device leases (spec/bhms/07-leases-and-authority.md BHMS-LSE-011, BHMS-LSE-013).

The gateway is the lease authority for the resources it names: ``<namespace>/<upstream resource id>`` (two upstreams that
both declare ``axis-1`` do not clash). Its :class:`~bhms.runtime.leases.LeaseManager` arbitrates every acquire — all or
nothing, conflicts, fences that increase across restarts, expiry, ownership — exactly as a device server does; the gateway
lease carries the gateway's own fence.

A lease that spans upstreams is also held *upstream*, on behalf of its holder (the upstream sees the gateway as the
principal), so that each upstream's own enforcement point can reject a superseded holder (BHMS-LSE-011):

* **acquire** — the gateway reserves the resources locally first (that is where contenders are arbitrated and where
  ``waitMs`` is spent), then acquires the upstream leases in *ascending resource-id order* (BHMS-LSE-013); because ids start
  with the namespace this is one upstream lease per upstream, in namespace order. The gateway lease is returned, and its id
  becomes known to anyone, only after **all** upstream leases are held; if one cannot be acquired, those already held are
  released and the local reservation is dropped, so nothing is held partially (BHMS-LSE-001). An upstream conflict is
  reported as ``LEASE_CONFLICT`` naming the gateway's resource ids and never the holder.
* **renew** — the gateway lease and every upstream lease are renewed together; if an upstream refuses (it lost the lease),
  the gateway lease is revoked at once (a ``FENCED`` holder is safe, a half-valid one is not).
* **release / expiry / revocation** (``stop``, policy) — the upstream leases are released with the gateway lease. A lost
  release is harmless: the upstream lease expires by its TTL.
* **invoke** — :meth:`GatewayLeases.upstream_lease_id` maps a gateway lease to the id the upstream expects; the upstream
  checks it and its fence itself.

An upstream that does not advertise ``leases`` is covered by the gateway lease alone (the gateway then is the only
path to it and says so with ``capabilities.gateway``).

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bhms.gateway.policy import unauthorized
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Principal
from bhms.runtime.leases import Lease, LeaseManager
from bhms.transport.base import TransportClosed

if TYPE_CHECKING:
    from bhms.gateway.gateway import Gateway

log = logging.getLogger("bhms.gateway.leases")


@dataclass
class UpstreamLease:
    """A lease the gateway holds on one upstream on behalf of a gateway lease."""

    namespace: str
    lease_id: str
    resources: tuple[str, ...]
    upstream_resources: tuple[str, ...]


class GatewayLeases:
    """Gateway lease authority; see the module docstring."""

    def __init__(self, gateway: Gateway) -> None:
        cfg = gateway.config
        self.gateway = gateway
        self.manager = LeaseManager(gateway.store, resources=gateway.catalog.resources, min_ttl_ms=cfg.lease_min_ttl_ms,
                                    max_ttl_ms=cfg.lease_max_ttl_ms, max_wait_ms=cfg.lease_max_wait_ms,
                                    on_end=self._ended)
        self._upstream: dict[str, dict[str, UpstreamLease]] = {}
        self._reverse: dict[str, str] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    @property
    def capability(self) -> dict[str, int]:
        return self.manager.capability

    def close(self) -> None:
        self.manager.close()
        for task in list(self._tasks):
            task.cancel()

    # ------------------------------------------------------------------ methods

    @staticmethod
    def _require_scope(principal: Principal) -> None:
        if not principal.has("lease"):
            raise unauthorized("scope:lease", principal, "use leases", "lease")

    async def acquire(self, principal: Principal, resources: list[str], ttl_ms: int, wait_ms: int | None,
                      trace: dict[str, Any] | None = None) -> Lease:
        """``leases/acquire`` over gateway resource ids; see the module docstring for the order of steps."""
        self._require_scope(principal)
        started = time.monotonic()
        lease = await self.manager.acquire(principal, resources, ttl_ms, wait_ms)
        held: list[UpstreamLease] = []
        try:
            for namespace in sorted({r.split("/", 1)[0] for r in lease.resources}):
                mine = tuple(sorted(r for r in lease.resources if r.split("/", 1)[0] == namespace))
                up = self.gateway.upstreams[namespace]
                if "leases" not in up.capabilities:
                    continue
                bounds = up.capabilities["leases"]
                remaining = max(0, (wait_ms or 0) - int((time.monotonic() - started) * 1000))
                upstream_resources = tuple(r.split("/", 1)[1] for r in mine)
                params: dict[str, Any] = {
                    "resources": list(upstream_resources),
                    "ttlMs": min(max(ttl_ms, bounds.get("minTtlMs", ttl_ms)), bounds.get("maxTtlMs", ttl_ms))}
                if remaining:
                    params["waitMs"] = min(remaining, bounds.get("maxWaitMs", remaining))
                reply = await up.call("leases/acquire", params, trace=trace,
                                      timeout=up.cfg.timeout_ms / 1000 + remaining / 1000)
                held.append(UpstreamLease(namespace, reply["lease"]["leaseId"], mine, upstream_resources))
        except BaseException as exc:
            await self._release_all(held)
            self.manager.release(principal, lease.lease_id)
            if isinstance(exc, BhmsError):
                raise _translate(exc, held_namespace=namespace) from None  # noqa: F821 - bound by the loop above
            if isinstance(exc, (TransportClosed, asyncio.TimeoutError)):
                raise BhmsError("DEVICE_UNAVAILABLE", f"the lease could not be acquired on upstream {namespace!r}",
                                may_have_acted=False, hint="no lease is held; retry (gateway rule: "
                                "isolation:upstream-unavailable)") from None
            raise
        self._upstream[lease.lease_id] = {u.namespace: u for u in held}
        for item in held:
            self._reverse[item.lease_id] = lease.lease_id
        return lease

    async def renew(self, principal: Principal, lease_id: str, ttl_ms: int,
                    trace: dict[str, Any] | None = None) -> Lease:
        self._require_scope(principal)
        lease = self.manager.renew(principal, lease_id, ttl_ms)
        held = list(self._upstream.get(lease_id, {}).values())

        async def renew_one(item: UpstreamLease) -> None:
            up = self.gateway.upstreams[item.namespace]
            bounds = up.capabilities.get("leases", {})
            await up.call("leases/renew", {"leaseId": item.lease_id, "ttlMs": min(
                max(ttl_ms, bounds.get("minTtlMs", ttl_ms)), bounds.get("maxTtlMs", ttl_ms))}, trace=trace)

        results = await asyncio.gather(*(renew_one(i) for i in held), return_exceptions=True)
        failed = [r for r in results if isinstance(r, BaseException)]
        if failed:
            self.manager.revoke(lease_id)  # a half-valid lease is worse than a revoked one
            first = failed[0]
            if isinstance(first, BhmsError):
                raise _translate(first, held_namespace=None) from None
            raise BhmsError("DEVICE_UNAVAILABLE", "an upstream could not renew its part of the lease; the lease was "
                            "revoked", may_have_acted=False,
                            hint="acquire a new lease (gateway rule: isolation:upstream-unavailable)") from None
        return lease

    async def release(self, principal: Principal, lease_id: str, trace: dict[str, Any] | None = None) -> Lease:
        self._require_scope(principal)
        lease = self.manager.release(principal, lease_id)
        await self._release_all(list(self._upstream.pop(lease_id, {}).values()), trace)
        return lease

    # ------------------------------------------------------------------ mapping and lifecycle

    def upstream_lease_id(self, lease_id: str, namespace: str) -> str | None:
        """The upstream's id for gateway lease ``lease_id`` on ``namespace`` (None: the gateway alone guards it)."""
        item = self._upstream.get(lease_id, {}).get(namespace)
        return item.lease_id if item is not None else None

    def gateway_lease_of(self, upstream_lease_id: str) -> str | None:
        return self._reverse.get(upstream_lease_id)

    def _ended(self, lease: Lease, reason: str) -> None:
        """Expiry or revocation: release the upstream parts in the background (they would expire anyway)."""
        held = list(self._upstream.pop(lease.lease_id, {}).values())
        if held:
            task = asyncio.get_running_loop().create_task(self._release_all(held))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        self.gateway.lease_ended(lease, reason)

    async def _release_all(self, held: list[UpstreamLease], trace: dict[str, Any] | None = None) -> None:
        async def one(item: UpstreamLease) -> None:
            up = self.gateway.upstreams[item.namespace]
            with contextlib.suppress(BhmsError, TransportClosed, asyncio.TimeoutError):
                await up.call("leases/release", {"leaseId": item.lease_id}, priority=True, trace=trace, timeout=2.0)
            self._reverse.pop(item.lease_id, None)

        await asyncio.gather(*(one(i) for i in reversed(held)))


def _translate(exc: BhmsError, *, held_namespace: str | None) -> BhmsError:
    """An upstream lease refusal in the gateway's vocabulary: resource ids prefixed, holder never disclosed."""
    if exc.code != "LEASE_CONFLICT" or not isinstance(exc.bound, list) or held_namespace is None:
        return exc
    return BhmsError("LEASE_CONFLICT", f"{', '.join(f'{held_namespace}/{r}' for r in exc.bound)} "
                     f"{'is' if len(exc.bound) == 1 else 'are'} leased by another holder", field="resources",
                     bound=[f"{held_namespace}/{r}" for r in exc.bound], may_have_acted=False,
                     hint=(exc.hint or "retry later or pass waitMs") + " (the holder is on the upstream server)")


__all__ = ["GatewayLeases", "UpstreamLease"]
