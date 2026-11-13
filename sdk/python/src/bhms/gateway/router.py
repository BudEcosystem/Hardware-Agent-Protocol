"""Request routing of the gateway: one handler per BHMS method (spec/bhms/06-operations.md §6.5, 07-leases-and-authority.md).

Admission order for ``actions/invoke`` — the spec's §6.5 with the gateway's additions, and the reason for each:

1. the dispatcher validated ``_meta`` and the params shape, and the transport authenticated the principal;
2. **the gateway's own key lookup** ``(principal, operationKey)`` — before any policy or scope check (BHMS-OPS-033,
   BHMS-AUTH-014): a retry of an admitted request returns the original operation even after its scope was revoked, its
   lease expired or the description changed; a different intent under the same key is ``KEY_CONFLICT``;
3. resolve ``ns/device`` and the action; 4. authorize (``invoke:`` scope, hazardous rule, non-empty envelope);
5. pin check against the description *served to this principal* (narrowed bounds change its digest);
6. validate the arguments against the device's schema, then the principal's narrowed envelope (``OUT_OF_RANGE`` with the
   effective bound, rule ``bounds:<member>``);
7. lease check on the gateway lease; the upstream's own lease id is forwarded (BHMS-LSE-011);
8. reachability (``DEVICE_UNAVAILABLE`` while the upstream is down or stalled), unresolved ``unknown`` operations on
   the same resources (``STALE``, BHMS-OPS-042) and a writable journal (BHMS-AUTH-025);
9. forward with the deterministic upstream key (:func:`~bhms.gateway.journal.upstream_key`).

A refusal at any step, and a refusal by the upstream before it created anything (``mayHaveActed: false``), is a JSON-RPC
error and creates **no** operation (BHMS-OPS-040). The gateway's record is written once the upstream answered (or when it
did not answer and the outcome is therefore ``unknown``, BHMS-OPS-004); if the gateway dies between sending and
recording, the client's retry carries the same key, derives the same upstream key, and the upstream returns the operation it
already created (``replayed``).

Everything after admission is mirrored: upstream operation notifications, ``operations/get``/``wait`` replies and
reconciliation answers are applied to the gateway record along the legal transitions of §6.3
(:meth:`~bhms.gateway.journal.ForwardJournal.mirror`). When an upstream link breaks or stalls, operations in flight become
``unknown`` at once; when it is back the gateway asks the upstream (``operations/get``, or — if the forward itself was in
doubt and the upstream's epoch is unchanged — a re-send of the *same* upstream request, which the upstream deduplicates)
and records the answer as a ``reconciliation``. A re-send is never made across an epoch change (BHMS-OPS-081).

``stop`` goes to every upstream concurrently, on a path that bypasses queues and concurrency limits (BHMS-AUTH-020), with a
deadline of ``waitMs`` plus ``stop_deadline_ms``; devices whose upstream did not answer in time report ``initiated``.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from bhms.gateway.catalog import CatalogEntry
from bhms.gateway.journal import upstream_key
from bhms.gateway.policy import refusal, unauthorized
from bhms.gateway.upstreams import Upstream
from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.jsonrpc.session import RequestContext
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Principal
from bhms.runtime.operations import (OperationRecord, intent_digest, iso, key_conflict_error, now_ns, server_key,
                                     unknown_error)
from bhms.runtime.store import StoreError
from bhms.server.handlers import summary_matches
from bhms.server.server import decode_cursor, encode_cursor
from bhms.transport.base import TransportClosed

if TYPE_CHECKING:
    from bhms.gateway.gateway import Gateway

log = logging.getLogger("bhms.gateway.router")

_TRACE_KEYS = ("traceparent", "tracestate")
NOT_SENT = (BhmsError,)


def trace_of(ctx: RequestContext) -> dict[str, Any] | None:
    """``traceparent``/``tracestate`` of the request, propagated unchanged upstream (BHMS-LIF-018)."""
    meta = ctx.params.get("_meta") or {}
    found = {k: meta[k] for k in _TRACE_KEYS if k in meta}
    return found or None


def _limit(requested: int | None, maximum: int, default: int = 100) -> int:
    return min(requested or min(default, maximum), maximum)


def _tag(exc: BhmsError, rule: str) -> BhmsError:
    """``exc`` with the policy rule that produced it named in message and hint."""
    return BhmsError(exc.code, f"{exc.message} (gateway policy rule {rule})", field=exc.field, bound=exc.bound,
                     operation_id=exc.operation_id, may_have_acted=exc.may_have_acted, retry=exc.retry,
                     hint=f"{exc.hint} [rule: {rule}]")


class Router:
    """The handlers of a gateway; see the module docstring."""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway
        self.by_upstream: dict[tuple[str, str], str] = {}  # (namespace, upstream operationId) -> gateway operationId
        self.unknown: dict[str, OperationRecord] = {}
        self._reconciling: set[str] = set()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._reconcile_kick = asyncio.Event()
        self._reconciler: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        journal = self.gateway.journal
        journal.on_unknown.append(self._became_unknown)
        journal.listeners.append(self._changed)
        for rec in journal.unknown_operations():
            self.unknown[rec.id] = rec
        for row in journal.store.operations_in_states(["dispatching", "running", "unknown"]):
            uid = row.private.get("upstreamOperationId")
            if uid:
                self.by_upstream[(row.private["upstream"], uid)] = row.id
        self._reconciler = asyncio.get_running_loop().create_task(self._reconcile_loop(), name="bhms-gateway-reconcile")

    async def close(self) -> None:
        if self._reconciler is not None:
            self._reconciler.cancel()
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*([self._reconciler] if self._reconciler else []), *self._tasks, return_exceptions=True)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------------ registration

    def register(self, rpc: RpcServer) -> None:
        table = {
            "devices/list": self.devices_list, "devices/describe": self.devices_describe,
            "properties/read": self.properties_read, "actions/invoke": self.actions_invoke,
            "operations/get": self.operations_get, "operations/wait": self.operations_wait,
            "operations/list": self.operations_list, "operations/cancel": self.operations_cancel, "stop": self.stop,
            "subscriptions/listen": self.listen, "leases/acquire": self.leases_acquire,
            "leases/renew": self.leases_renew, "leases/release": self.leases_release, "events/read": self.events_read}
        for method, handler in table.items():
            rpc.register(method, handler, cancellable=True if method == "leases/acquire" else None)

    # ------------------------------------------------------------------ devices

    def status_of(self, entry: CatalogEntry) -> str:
        """Device status as served: the upstream's own while it is reachable, ``offline`` when it is not."""
        up = self.gateway.upstreams[entry.namespace]
        return entry.upstream_summary.get("status", "unknown") if up.status == "up" else "offline"

    def _visible(self, principal: Principal, device_id: str, *, field: str = "deviceId") -> CatalogEntry:
        entry = self.gateway.catalog.get(device_id)
        if entry is None or not principal.can_read:
            raise refusal("UNKNOWN_DEVICE", "scope:read" if entry is not None else "routing:unknown-device",
                          f"no device {device_id!r}", field=field,
                          hint="devices/list shows the devices you can use")
        return entry

    async def devices_list(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        if not principal.can_read:
            return {"devices": []}  # BHMS-DEV-010
        limit = _limit(params.limit, gw.config.max_page_size)
        after = decode_cursor("d", params.cursor) if params.cursor is not None else None
        flt = params.filter
        devices: list[dict[str, Any]] = []
        more = False
        for entry in gw.catalog.after(after):
            status = self.status_of(entry)
            if flt is not None and not summary_matches(flt, entry.upstream_summary, status):
                continue
            if len(devices) == limit:
                more = True
                break
            devices.append(gw.policy.summary(entry, principal, status))
        result: dict[str, Any] = {"devices": devices}
        if more:
            result["nextCursor"] = encode_cursor("d", devices[-1]["deviceId"])
        return result

    async def devices_describe(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        entry = self._visible(principal, params.device_id)
        description, served_digest = gw.policy.served(entry, principal)
        if params.digest is not None and params.digest != served_digest:
            raise BhmsError("STALE", f"{entry.device_id}'s description changed", field="digest", bound=served_digest,
                            hint="describe again without digest and update your cached copy (BHMS-DEV-022)")
        return {"description": description}

    async def properties_read(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        entry = self._visible(principal, params.device_id)
        spec = entry.properties.get(params.property)
        if spec is not None and spec.read_effect == "transaction":
            if not principal.can_invoke(entry.device_id, params.property, entry.capabilities):
                raise refusal("UNAUTHORIZED", "scope:invoke",
                              f"a read of {entry.device_id}.{params.property} may start a device transaction",
                              field="property", hint=f"ask for scope invoke:{entry.device_id}/{params.property}; the "
                              "gateway cannot know whether a retained observation exists, so it requires the scope for "
                              "every read of a transaction property (BHMS-AUTH-012)")
            resources = spec.resources
            lease = gw.leases.manager.held_by(principal.id, resources)
            if lease is None:
                raise BhmsError("LEASE_REQUIRED", f"reading {entry.device_id}.{params.property} needs a lease on "
                                f"{', '.join(resources)}", field="property",
                                hint=f"acquire a lease on {', '.join(resources)} with leases/acquire first")
        up = gw.upstreams[entry.namespace]
        forward = {k: v for k, v in ctx.params.items() if k != "_meta"}
        forward["deviceId"] = entry.upstream_id
        reply = await up.call("properties/read", forward, trace=trace_of(ctx))
        return {"observation": reply["observation"]}

    # ------------------------------------------------------------------ actions/invoke

    async def actions_invoke(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        raw = ctx.params
        key = params.operation_key
        if key is not None and key.startswith(("d-", "g-")) and (key.startswith("d-") or not principal.gateway):
            raise refusal("INVALID_ARGUMENT", "key:reserved-prefix", f"operationKey prefix {key[:2]} is reserved",
                          field="operationKey", hint="use a key that does not start with d- or g- (BHMS-OPS-037)")
        if params.wait_ms is not None and params.wait_ms > gw.config.max_wait_ms:
            raise _wait_error("waitMs", params.wait_ms, gw.config.max_wait_ms)
        digest = intent_digest("actions/invoke", raw)
        if key is None:
            rec, replayed = await self._admit(principal, params, raw, server_key(), "server", digest, ctx), False
        else:
            async with gw.journal.admission(principal.id, key):
                existing = gw.journal.lookup_key(principal.id, key)  # BHMS-OPS-033: before any policy check
                if existing is not None:
                    if existing.op["requestDigest"] != digest:
                        raise key_conflict_error(existing, key)
                    rec, replayed = existing, True
                else:
                    rec, replayed = await self._admit(principal, params, raw, key, "client", digest, ctx), False
        if replayed:
            await self._refresh(rec)
        if params.wait_ms and not rec.settled:
            rec = await self._wait(rec, params.wait_ms)
        return {"operation": rec.wire(), "replayed": replayed}

    async def _admit(self, principal: Principal, params: Any, raw: dict[str, Any], key: str, origin: str, digest: str,
                     ctx: RequestContext) -> OperationRecord:
        gw = self.gateway
        entry = self._visible(principal, params.device_id)
        spec = entry.action(params.action)
        if spec is None:
            raise refusal("UNKNOWN_ACTION", "routing:unknown-action", f"{entry.device_id} has no action "
                          f"{params.action!r}", field="action",
                          hint=f"actions of {entry.device_id}: {', '.join(sorted(entry.description['actions'])) or 'none'}")
        hazardous = spec["effect"] == "hazardous"
        if not principal.can_invoke(entry.device_id, params.action, entry.capabilities, hazardous):
            rule = "scope:hazardous" if hazardous and principal.can_invoke(
                entry.device_id, params.action, entry.capabilities, False) else "scope:invoke"
            raise unauthorized(rule, principal, f"invoke {entry.device_id}/{params.action}",
                               f"invoke:{entry.device_id}/{params.action}" + (
                                   " (hazardous actions need the literal action name)" if hazardous else ""))
        description, served_digest = gw.policy.served(entry, principal)
        if params.action not in description["actions"]:
            raise refusal("UNAUTHORIZED", "bounds:empty", f"your policy bounds leave {entry.device_id}/"
                          f"{params.action} no allowed value", hint="ask the gateway operator to widen the bounds "
                          "(they can only narrow the device's own, BHMS-AUTH-011)")
        if params.description_digest is not None and params.description_digest != served_digest:
            raise BhmsError("STALE", f"{entry.device_id}'s description changed since you read it",
                            field="descriptionDigest", bound=served_digest,
                            hint="describe the device again and re-plan against the new bounds")
        validator = entry.validator(params.action)
        admitted = validator.admit(raw["arguments"])
        envelope = gw.policy.envelope(entry, principal, params.action)
        if envelope:
            try:
                validator.check_envelope(admitted, envelope)
            except BhmsError as exc:
                member = (exc.field or "").rsplit(".", 1)[-1]
                raise _tag(exc, f"bounds:{member}") from None
        resources = tuple(spec.get("resources") or ())
        lease_id = fence = upstream_lease = None
        if spec.get("requiresLease"):
            lease = gw.leases.manager.check(principal, params.lease_id, resources)
            lease_id, fence = lease.lease_id, lease.fence
            upstream_lease = gw.leases.upstream_lease_id(lease.lease_id, entry.namespace)
        up = gw.upstreams[entry.namespace]
        if not up.available:
            raise up.unavailable()
        self._check_inhibition(resources)
        gw.require_journal()
        ukey = upstream_key(gw.config.id, principal.id, key)
        forward: dict[str, Any] = {"deviceId": entry.upstream_id, "action": params.action,
                                   "arguments": raw["arguments"], "operationKey": ukey,
                                   "descriptionDigest": entry.upstream_description["digest"]}
        for member in ("deadlineMs", "require"):
            if raw.get(member) is not None:
                forward[member] = raw[member]
        if upstream_lease is not None:
            forward["leaseId"] = upstream_lease
        private = {"upstream": up.name, "upstreamDeviceId": entry.upstream_id, "upstreamKey": ukey,
                   "upstreamRequest": forward, "upstreamEpoch": up.epoch, "resources": list(resources),
                   "effectClass": spec["effect"]}
        deadline_ns = now_ns() + raw["deadlineMs"] * 1_000_000 if raw.get("deadlineMs") else None
        common = dict(principal=principal.id, key=key, key_origin=origin, request_digest=digest,
                      arguments=raw["arguments"], device_id=entry.device_id, action=params.action, private=private,
                      require=raw.get("require"), lease_id=lease_id, fence=fence, deadline_ns=deadline_ns,
                      admitted=admitted)
        cause = None
        try:
            reply = await up.call("actions/invoke", forward, trace=trace_of(ctx))
        except BhmsError as exc:
            if not exc.may_have_acted:
                raise  # refused before anything was created: a JSON-RPC error, no operation (BHMS-OPS-040)
            cause = f"upstream {up.name}: {exc.message}"
        except (TransportClosed, asyncio.TimeoutError) as exc:
            cause = f"the connection to upstream {up.name} failed while forwarding ({type(exc).__name__}): {exc}"
        try:
            if cause is not None:
                return gw.journal.admit_in_doubt(cause=cause, **common)
            return gw.journal.admit_forwarded(upstream_op=reply["operation"], **common)
        except StoreError as exc:
            gw.journal_failed(exc)
            raise BhmsError("INTERNAL", "the gateway could not record an operation the upstream accepted",
                            may_have_acted=True, retry="same-key",
                            hint="retry with the same operationKey: the upstream returns the same operation") from None

    def _check_inhibition(self, resources: tuple[str, ...]) -> None:
        needed = set(resources)
        if not needed:
            return
        for rec in self.unknown.values():
            if rec.private.get("effectClass", "none") != "none" and not rec.private.get("inhibitionLifted") \
                    and needed.intersection(rec.resources):
                raise refusal("STALE", "isolation:unknown-operation",
                              f"operation {rec.id} on the same resources has an unknown outcome", field="operationId",
                              operation_id=rec.id,
                              hint=f"reconcile {rec.id} first (operations/get, read the device state, or stop the "
                                   "device); new work on its resources is refused until then (BHMS-OPS-042)")

    # ------------------------------------------------------------------ operations

    def _operation_for(self, principal: Principal, op_id: str) -> OperationRecord:
        rec = self.gateway.journal.get(op_id)
        if rec is None or (rec.principal != principal.id and not principal.operations_all):
            raise refusal("INVALID_ARGUMENT", "scope:operations", f"no operation {op_id!r} is visible to you",
                          field="operationId",
                          hint="use an operationId returned to you (operations/list shows yours); seeing other "
                               "principals' operations needs scope operations:read")
        return rec

    async def operations_get(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = self.gateway.auth.authenticate(ctx)
        rec = self._operation_for(principal, params.operation_id)
        await self._refresh(rec)
        return {"operation": rec.wire(history=True)}

    async def operations_wait(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        if params.timeout_ms > gw.config.max_wait_ms:
            raise _wait_error("timeoutMs", params.timeout_ms, gw.config.max_wait_ms)
        rec = self._operation_for(principal, params.operation_id)
        rec = await self._wait(rec, params.timeout_ms)
        return {"operation": rec.wire(history=True)}

    async def operations_list(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        page, cursor = gw.journal.list(principal=None if principal.operations_all else principal.id,
                                       limit=_limit(params.limit, gw.config.max_page_size), after=params.cursor,
                                       device_id=params.device_id, state=params.state,
                                       parent_id=params.parent_operation_id)
        result: dict[str, Any] = {"operations": page}
        if cursor is not None:
            result["nextCursor"] = cursor
        return result

    async def operations_cancel(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        rec = gw.journal.get(params.operation_id)
        if rec is None:
            raise refusal("INVALID_ARGUMENT", "scope:operations", f"no operation {params.operation_id!r}",
                          field="operationId", hint="use an operationId returned to you")
        if rec.principal != principal.id and not principal.admin:
            raise refusal("UNAUTHORIZED", "ownership:cancel", "only the principal that created an operation (or admin) "
                          "may cancel it", field="operationId", hint="ask its owner, or use stop if the device must "
                          "halt (BHMS-OPS-054)")
        if rec.terminal:
            return {"operation": rec.wire()}
        up = gw.upstreams[rec.private["upstream"]]
        uid = rec.private.get("upstreamOperationId")
        try:
            if uid is None or not up.available:
                raise up.unavailable() if uid is not None else TransportClosed("not forwarded yet")
            reply = await up.call("operations/cancel", {"operationId": uid, "reason": params.reason},
                                  trace=trace_of(ctx))
            self._apply(rec, reply["operation"], "operations/cancel")
        except (BhmsError, TransportClosed, asyncio.TimeoutError) as exc:
            if isinstance(exc, BhmsError) and not exc.may_have_acted and exc.code != "DEVICE_UNAVAILABLE":
                raise
            # BHMS-OPS-053: record the request and forward it when the upstream can be reached
            with contextlib.suppress(StoreError):
                gw.journal.mark_private(rec, cancelRequested=True, cancelReason=params.reason)
                gw.journal.set_cancel(rec, "requested", reason=params.reason,
                                      detail="recorded by the gateway; forwarded when the upstream is reachable")
        return {"operation": rec.wire()}

    # ------------------------------------------------------------------ mirroring and reconciliation

    def _apply(self, rec: OperationRecord, upstream_op: dict[str, Any], source: str) -> None:
        gw = self.gateway
        try:
            gw.journal.mirror(rec, upstream_op, source=source)
        except StoreError as exc:
            gw.journal_failed(exc)
            return
        uid = rec.private.get("upstreamOperationId")
        if uid:
            self.by_upstream[(rec.private["upstream"], uid)] = rec.id

    def on_operation_notification(self, up: Upstream, operation: dict[str, Any]) -> None:
        gid = self.by_upstream.get((up.name, operation.get("operationId")))
        rec = self.gateway.journal.get(gid) if gid else None
        if rec is not None:
            self._apply(rec, operation, "notification")

    def _became_unknown(self, rec: OperationRecord) -> None:
        self.unknown[rec.id] = rec
        with contextlib.suppress(StoreError):
            self.gateway.events.append("operation.state", severity="warning", device_id=rec.op.get("deviceId"),
                                       operation_id=rec.id, message=rec.op.get("error", {}).get("message"),
                                       data={"state": "unknown", "previousState": "dispatching"})
        self._reconcile_kick.set()

    def _changed(self, rec: OperationRecord, wire: dict[str, Any]) -> None:
        if wire["state"] != "unknown":
            self.unknown.pop(rec.id, None)

    def upstream_lost(self, up: Upstream, cause: str) -> None:
        """Operations in flight on ``up`` become ``unknown`` (BHMS-OPS-004)."""
        journal = self.gateway.journal
        for rec in journal.live():
            if rec.private.get("upstream") == up.name and rec.state in ("dispatching", "running"):
                try:
                    journal.link_lost(rec, f"upstream {up.name} is {up.status} ({cause}); the device may have acted")
                except StoreError as exc:
                    self.gateway.journal_failed(exc)

    def upstream_back(self, up: Upstream) -> None:
        self._reconcile_kick.set()

    async def _reconcile_loop(self) -> None:
        while True:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._reconcile_kick.wait(), 2.0)
            self._reconcile_kick.clear()
            for rec in list(self.unknown.values()):
                if self.gateway.upstreams[rec.private["upstream"]].available:
                    await self.reconcile(rec)

    async def _refresh(self, rec: OperationRecord, timeout: float = 3.0) -> None:
        if not rec.terminal:
            await self.reconcile(rec, timeout=timeout)

    async def reconcile(self, rec: OperationRecord, *, timeout: float = 3.0) -> bool:
        """Ask the upstream for the truth about ``rec`` and record the answer; True when the record changed."""
        gw = self.gateway
        if rec.terminal or rec.id in self._reconciling:
            return False
        up = gw.upstreams[rec.private["upstream"]]
        if not up.available:
            return False
        self._reconciling.add(rec.id)
        try:
            before = (rec.state, rec.op["effect"], rec.op["cancel"]["state"])
            uid = rec.private.get("upstreamOperationId")
            if uid is not None:
                reply = await up.call("operations/get", {"operationId": uid}, timeout=timeout)
                self._apply(rec, reply["operation"], "operations/get")
            elif up.epoch == rec.private.get("upstreamEpoch"):
                # The forward was in doubt. The upstream's epoch is unchanged, so its journal survived and the same
                # upstream key returns the operation it already created (BHMS-OPS-030) instead of a second one.
                reply = await up.call("actions/invoke", rec.private["upstreamRequest"], timeout=timeout)
                self._apply(rec, reply["operation"], "re-sent forward")
            else:
                self._note_unreconcilable(rec, "the upstream's epoch changed, so its record of this request is lost and "
                                               "re-sending could execute it twice (BHMS-OPS-081)")
                return False
            if rec.private.get("cancelRequested") and not rec.terminal and rec.op["cancel"]["state"] in (
                    "none", "requested") and rec.private.get("upstreamOperationId"):
                reply = await up.call("operations/cancel", {
                    "operationId": rec.private["upstreamOperationId"], "reason": rec.private.get("cancelReason")},
                    timeout=timeout)
                gw.journal.mark_private(rec, cancelRequested=False)
                self._apply(rec, reply["operation"], "operations/cancel")
            return before != (rec.state, rec.op["effect"], rec.op["cancel"]["state"])
        except BhmsError as exc:
            if exc.field == "operationId":
                self._note_unreconcilable(rec, "the upstream does not know this operation any more (its journal was "
                                               f"lost or pruned): {exc.message}")
            else:
                log.info("reconciling %s: %s", rec.id, exc)
        except (TransportClosed, asyncio.TimeoutError) as exc:
            log.info("reconciling %s: %r", rec.id, exc)
        except StoreError as exc:
            gw.journal_failed(exc)
        finally:
            self._reconciling.discard(rec.id)
        return False

    def _note_unreconcilable(self, rec: OperationRecord, why: str) -> None:
        if rec.private.get("unreconcilable") == why:
            return
        with contextlib.suppress(StoreError):
            self.gateway.journal.mark_private(rec, unreconcilable=why)
            self.gateway.journal.annotate(rec, "correction", f"cannot be reconciled with the upstream: {why}")

    async def _wait(self, rec: OperationRecord, wait_ms: int) -> OperationRecord:
        """Wait up to ``wait_ms`` for ``rec`` to settle, asking the upstream to wait server-side (BHMS-OPS-060)."""
        gw = self.gateway
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_ms / 1000
        up = gw.upstreams[rec.private["upstream"]]
        while not rec.settled:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            uid = rec.private.get("upstreamOperationId")
            if uid is None or not up.available:
                await gw.journal.wait(rec, min(remaining, 0.5))
                continue
            limit = (up.client.server.limits.max_wait_ms if up.client and up.client.server else 30_000) / 1000
            chunk = min(remaining, limit)
            try:
                reply = await up.call("operations/wait", {"operationId": uid, "timeoutMs": int(chunk * 1000)},
                                      timeout=chunk + up.cfg.timeout_ms / 1000)
                self._apply(rec, reply["operation"], "operations/wait")
            except (BhmsError, TransportClosed, asyncio.TimeoutError):
                await gw.journal.wait(rec, min(max(0.0, deadline - loop.time()), 0.5))
        return rec

    # ------------------------------------------------------------------ stop

    async def stop(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        """``stop`` fan-out; see the module docstring (BHMS-AUTH-020..026)."""
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        wait_ms = params.wait_ms or 0
        if wait_ms > gw.config.max_wait_ms:
            raise _wait_error("waitMs", wait_ms, gw.config.max_wait_ms)
        if not principal.may_stop_any:
            raise unauthorized("scope:stop", principal, "stop devices", "stop or stop:<deviceGlob>")
        targets = [d for d in gw.catalog if principal.can_stop(d)] if params.scope == "all" \
            else list(dict.fromkeys(params.device_ids))
        results: dict[str, dict[str, Any]] = {}
        groups: dict[str, list[CatalogEntry]] = {}
        for device_id in targets:
            entry = gw.catalog.get(device_id)
            if entry is None or not principal.can_stop(device_id):
                code, text = ("UNAUTHORIZED", f"you may not stop {device_id}") if entry is not None and \
                    principal.can_read else ("UNKNOWN_DEVICE", f"no device {device_id!r}")
                rule = "scope:stop" if code == "UNAUTHORIZED" else "routing:unknown-device"
                error = refusal(code, rule, text, hint="nothing was stopped on this device; check the id and your "
                                                       "stop scope")
                results[device_id] = {"deviceId": device_id, "outcome": "failed", "evidence": "none",
                                      "canceledOperations": [], "revokedLeases": [], "error": error.to_operation_error()}
            else:
                groups.setdefault(entry.namespace, []).append(entry)
        deadline = wait_ms / 1000 + gw.config.stop_deadline_ms / 1000
        trace = trace_of(ctx)
        calls: dict[str, asyncio.Task[dict[str, Any]]] = {}
        for namespace, entries in groups.items():  # every upstream at once, bypassing queues (BHMS-AUTH-020)
            up = gw.upstreams[namespace]
            calls[namespace] = asyncio.get_running_loop().create_task(up.call(
                "stop", {"deviceIds": [e.upstream_id for e in entries], "reason": params.reason, "waitMs": wait_ms},
                priority=True, trace=trace, timeout=deadline))
        degraded = self._stop_bookkeeping([e for es in groups.values() for e in es], params.reason, results)
        if calls:
            await asyncio.wait(list(calls.values()), timeout=deadline)
        for namespace, task in calls.items():
            self._stop_results(groups[namespace], task, results, params.reason)
        out = []
        for device_id in targets:
            result = results[device_id]
            if degraded or not gw.journal_ok:
                result["detail"] = "degraded-audit"
            out.append(result)
        return {"stops": out}

    def _stop_bookkeeping(self, entries: list[CatalogEntry], reason: str, results: dict[str, dict[str, Any]]) -> bool:
        """The gateway's own part of BHMS-AUTH-021: record the stop on its operations, revoke its leases."""
        gw = self.gateway
        degraded = False
        for entry in entries:
            revoked = [lease.lease_id for lease in gw.leases.manager.revoke_covering(entry.resources)]
            canceled: list[str] = []
            requested: list[str] = []
            for rec in gw.journal.live():
                if rec.op.get("deviceId") == entry.device_id and rec.state in ("dispatching", "running", "unknown"):
                    try:
                        gw.journal.annotate(rec, "stop", f"stop: {reason}")
                        if rec.op["cancel"]["state"] in ("none", "refused"):
                            gw.journal.set_cancel(rec, "requested", reason=f"stop: {reason}")
                    except StoreError as exc:
                        degraded = True
                        gw.journal_failed(exc)
                    requested.append(rec.id)
            for row in gw.journal.store.operations_in_states(["unknown"]):
                if row.record.get("deviceId") == entry.device_id and row.id not in requested:
                    requested.append(row.id)
            results[entry.device_id] = {"deviceId": entry.device_id, "canceledOperations": canceled,
                                        "revokedLeases": revoked, **({"cancelRequestedOperations": requested}
                                                                     if requested else {})}
        return degraded

    def _stop_results(self, entries: list[CatalogEntry], task: asyncio.Task[dict[str, Any]],
                      results: dict[str, dict[str, Any]], reason: str) -> None:
        gw = self.gateway
        by_upstream_id = {e.upstream_id: e for e in entries}
        namespace = entries[0].namespace
        if task.done() and task.exception() is None:
            for stop in task.result()["stops"]:
                entry = by_upstream_id.get(stop["deviceId"])
                if entry is None:
                    continue
                mine = results[entry.device_id]
                merged = {**stop, "deviceId": entry.device_id}
                for member in ("canceledOperations", "cancelRequestedOperations"):
                    ids = [self.by_upstream[(namespace, uid)] for uid in stop.get(member, [])
                           if (namespace, uid) in self.by_upstream]
                    mine_ids = mine.get(member, []) if member == "cancelRequestedOperations" else []
                    combined = list(dict.fromkeys([*ids, *mine_ids]))
                    if combined or member == "canceledOperations":
                        merged[member] = combined
                    else:
                        merged.pop(member, None)
                mapped = [gw.leases.gateway_lease_of(lid) for lid in stop.get("revokedLeases", [])]
                merged["revokedLeases"] = list(dict.fromkeys([*[m for m in mapped if m], *mine["revokedLeases"]]))
                results[entry.device_id] = merged
                if merged["outcome"] == "confirmed":
                    self._lift_inhibition(entry)
            return
        for entry in entries:
            mine = results[entry.device_id]
            exc = task.exception() if task.done() else None
            if not task.done() or (isinstance(exc, BhmsError) and exc.code == "DEADLINE_EXCEEDED"):
                mine.update(outcome="initiated", evidence="none", detail=(
                    f"upstream {namespace} did not answer within the deadline; the stop request was sent and a later "
                    "stop event carries the outcome"))
                task.add_done_callback(lambda t, e=entry: self._late_stop(e, t, reason))
                continue
            sent = not (isinstance(exc, BhmsError) and not exc.may_have_acted)
            error = (exc if isinstance(exc, BhmsError) else BhmsError(
                "DEVICE_UNAVAILABLE", f"upstream {namespace} failed while stopping: {exc}"[:500], may_have_acted=True,
                hint="the stop may or may not have been received; use the installation's independent emergency "
                     "stop if the device must halt now"))
            mine.update(outcome="failed", evidence="none", error=error.to_operation_error())
            if sent:
                mine["detail"] = "the stop request may have been received by the upstream"
        for entry in entries:
            with contextlib.suppress(StoreError):
                gw.events.append("stop", severity="warning", device_id=entry.device_id, message=reason[:1000],
                                 data={"outcome": results[entry.device_id]["outcome"], "reason": reason})

    def _late_stop(self, entry: CatalogEntry, task: asyncio.Future[dict[str, Any]], reason: str) -> None:
        if task.cancelled() or task.exception() is not None:
            return
        for stop in task.result()["stops"]:
            if stop["deviceId"] == entry.upstream_id:
                if stop["outcome"] == "confirmed":
                    self._lift_inhibition(entry)
                with contextlib.suppress(StoreError):
                    self.gateway.events.append("stop", severity="warning", device_id=entry.device_id,
                                               message=reason[:1000], data={"outcome": stop["outcome"],
                                                                            "reason": reason})

    def _lift_inhibition(self, entry: CatalogEntry) -> None:
        """A confirmed stop lifts the unknown-operation inhibition of the device's operations (BHMS-OPS-042)."""
        for rec in list(self.unknown.values()):
            if rec.op.get("deviceId") == entry.device_id:
                with contextlib.suppress(StoreError):
                    self.gateway.journal.mark_private(rec, inhibitionLifted=True)
                    self.gateway.journal.annotate(rec, "stop", "a confirmed stop lifted the resource inhibition; the "
                                                               "outcome is still unknown")

    # ------------------------------------------------------------------ leases, events, subscriptions

    async def leases_acquire(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = self.gateway.auth.authenticate(ctx)
        lease = await self.gateway.leases.acquire(principal, params.resources, params.ttl_ms, params.wait_ms,
                                                  trace_of(ctx))
        return {"lease": lease.wire()}

    async def leases_renew(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = self.gateway.auth.authenticate(ctx)
        return {"lease": (await self.gateway.leases.renew(principal, params.lease_id, params.ttl_ms,
                                                          trace_of(ctx))).wire()}

    async def leases_release(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = self.gateway.auth.authenticate(ctx)
        return {"lease": (await self.gateway.leases.release(principal, params.lease_id, trace_of(ctx))).wire()}

    async def events_read(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        gw = self.gateway
        principal = gw.auth.authenticate(ctx)
        if not principal.can_read:
            raise unauthorized("scope:read", principal, "read events", "read")
        events, cursor, gap = gw.events.read(after=params.after, limit=_limit(params.limit, gw.config.max_page_size),
                                             device_id=params.device_id, types=params.types)
        return {"events": events, "cursor": cursor, "gap": gap}

    async def listen(self, params: Any, ctx: RequestContext) -> Any:
        principal = self.gateway.auth.authenticate(ctx)
        return self.gateway.subscriptions.listen(principal, params, ctx)


def _wait_error(field: str, value: int, limit: int) -> BhmsError:
    return refusal("OUT_OF_RANGE", "limits:max-wait", f"{field} {value} is above limits.maxWaitMs {limit}", field=field,
                   bound={"maximum": limit}, hint=f"send {field} of at most {limit} and wait again if needed")


__all__ = ["Router", "trace_of"]
_ = (iso, unknown_error)
