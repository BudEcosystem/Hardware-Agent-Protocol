"""The method handlers of :class:`~bhms.server.server.DeviceServer`: one function per BHMS method.

Each handler authenticates the request (BHMS-SEC-001), applies the scope rules of §7.4 and delegates to the runtime.
The dispatcher (:class:`bhms.jsonrpc.Server`) has already checked ``_meta``, the protocol version, the capability and
the params shape, so ``params`` is the validated pydantic model and ``ctx.params`` the raw request params (used where
the spec digests a request exactly as sent).

Cancellation (BHMS-LIF-050): ``actions/invoke``, ``programs/run``, ``operations/cancel`` and ``stop`` are detached
when the client goes away — the work they started continues and is recorded. ``operations/wait``,
``subscriptions/listen`` and ``leases/acquire`` (whose wait grants nothing until it ends) are cancellable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.jsonrpc.session import RequestContext
from bhms.protocol.errors import BhmsError

if TYPE_CHECKING:
    from bhms.server.server import DeviceServer


def _limit(requested: int | None, maximum: int, default: int = 100) -> int:
    return min(requested or min(default, maximum), maximum)


def _capability_matches(pattern: str, capabilities: tuple[str, ...]) -> bool:
    if pattern.endswith(".*"):
        prefix = pattern[:-1]
        return any(c.startswith(prefix) for c in capabilities)
    return pattern in capabilities


def register(srv: DeviceServer, rpc: RpcServer) -> None:  # noqa: C901 - one closure per method, registered together
    """Register every BHMS method of ``srv`` on ``rpc``."""
    from bhms.server.server import _wait_error, decode_cursor, encode_cursor

    # ------------------------------------------------------------------ devices

    async def devices_list(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        if not principal.can_read:
            return {"devices": []}  # BHMS-DEV-010: nothing reveals hidden devices
        limit = _limit(params.limit, srv.max_page_size)
        after = decode_cursor("d", params.cursor) if params.cursor is not None else None
        flt = params.filter
        matches = []
        for dev in sorted(srv.devices.values(), key=lambda d: d.device_id):
            if after is not None and dev.device_id <= after:
                continue
            status = dev.status
            summary = dev.summary(status)
            if flt is not None:
                if flt.capability is not None and not _capability_matches(flt.capability, dev.capabilities):
                    continue
                if flt.tag is not None and flt.tag not in dev.tags:
                    continue
                if flt.status is not None and flt.status != status:
                    continue
                if flt.text is not None:
                    needle = flt.text.casefold()
                    haystack = [summary["name"], summary["summary"], *summary["tags"]]
                    if not any(needle in h.casefold() for h in haystack):
                        continue
            matches.append(summary)
            if len(matches) > limit:
                break
        result: dict[str, Any] = {"devices": matches[:limit]}
        if len(matches) > limit:
            result["nextCursor"] = encode_cursor("d", matches[limit - 1]["deviceId"])
        return result

    async def devices_describe(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        dev = srv.visible_device(principal, params.device_id)
        description = dev.description()
        if params.digest is not None and params.digest != description["digest"]:
            raise BhmsError("STALE", f"{dev.device_id}'s description changed", field="digest",
                            bound=description["digest"],
                            hint="describe again without digest and update your cached copy (BHMS-DEV-022)")
        return {"description": description}

    async def properties_read(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        dev = srv.visible_device(principal, params.device_id)
        observation = await srv.observations.read(dev, params.property, max_age_ms=params.max_age_ms,
                                                  fresh=params.fresh, principal=principal)
        return {"observation": observation}

    # ------------------------------------------------------------------ operations

    async def actions_invoke(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        rec, replayed = await srv.invoke(principal, params, ctx.params)
        if params.wait_ms:
            rec = await srv.journal.wait(rec, params.wait_ms / 1000)
        return {"operation": rec.wire(), "replayed": replayed}

    async def operations_get(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        return {"operation": srv.operation_for(principal, params.operation_id).wire(history=True)}

    async def operations_wait(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        if params.timeout_ms > srv.max_wait_ms:
            raise _wait_error("timeoutMs", params.timeout_ms, srv.max_wait_ms)
        rec = srv.operation_for(principal, params.operation_id)
        rec = await srv.journal.wait(rec, params.timeout_ms / 1000)
        return {"operation": rec.wire(history=True)}

    async def operations_list(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        page, cursor = srv.journal.list(principal=None if principal.admin else principal.id,
                                        limit=_limit(params.limit, srv.max_page_size), after=params.cursor,
                                        device_id=params.device_id, state=params.state,
                                        parent_id=params.parent_operation_id)
        result: dict[str, Any] = {"operations": page}
        if cursor is not None:
            result["nextCursor"] = cursor
        return result

    async def operations_cancel(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        rec = srv.journal.get(params.operation_id)
        if rec is None:
            raise BhmsError("INVALID_ARGUMENT", f"no operation {params.operation_id!r}", field="operationId",
                            hint="use an operationId returned to you")
        if rec.principal != principal.id and not principal.admin:
            raise BhmsError("UNAUTHORIZED", "only the principal that created an operation (or admin) may cancel it",
                            field="operationId", hint="ask its owner, or use stop if the device must halt "
                                                      "(BHMS-OPS-054)")
        if rec.op["kind"] == "program":
            await srv.programs.cancel(rec, params.reason)
        else:
            srv.executor.cancel(rec, params.reason)
        return {"operation": rec.wire()}

    async def stop(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        return {"stops": await srv.stopper.stop(principal, params)}

    async def listen(params: Any, ctx: RequestContext) -> Any:
        principal = srv.authenticate(ctx)
        return srv.subscriptions.listen(principal, params, ctx)

    # ------------------------------------------------------------------ leases

    def _lease_principal(ctx: RequestContext) -> Any:
        principal = srv.authenticate(ctx)
        if not principal.has("lease"):
            raise BhmsError("UNAUTHORIZED", "leases need the lease scope", hint="missing scope lease")
        return principal

    async def leases_acquire(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = _lease_principal(ctx)
        lease = await srv.leases.acquire(principal, params.resources, params.ttl_ms, params.wait_ms)
        return {"lease": lease.wire()}

    async def leases_renew(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = _lease_principal(ctx)
        return {"lease": srv.leases.renew(principal, params.lease_id, params.ttl_ms).wire()}

    async def leases_release(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = _lease_principal(ctx)
        return {"lease": srv.leases.release(principal, params.lease_id).wire()}

    # ------------------------------------------------------------------ events

    async def events_read(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        if not principal.can_read:
            raise BhmsError("UNAUTHORIZED", "events/read needs the read scope", hint="missing scope read")
        # read is one global scope in v0.1, so every device event is visible to a reader (BHMS-EVT-013)
        events, cursor, gap = srv.events.read(after=params.after, limit=_limit(params.limit, srv.max_page_size),
                                              device_id=params.device_id, types=params.types)
        return {"events": events, "cursor": cursor, "gap": gap}

    # ------------------------------------------------------------------ programs

    async def programs_run(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        if params.wait_ms is not None and params.wait_ms > srv.max_wait_ms:
            raise _wait_error("waitMs", params.wait_ms, srv.max_wait_ms)
        rec, replayed = await srv.programs.run(principal, params, ctx.params)
        if params.wait_ms:
            rec = await srv.journal.wait(rec, params.wait_ms / 1000)
        return {"operation": rec.wire(), "replayed": replayed}

    async def programs_register(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        return {"info": await srv.programs.register(principal, ctx.params["program"])}

    async def programs_get(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        program, info = srv.programs.get(principal, params.digest)
        return {"program": program, "info": info}

    async def programs_list(params: Any, ctx: RequestContext) -> dict[str, Any]:
        principal = srv.authenticate(ctx)
        infos, cursor = srv.programs.list(principal, params.cursor, _limit(params.limit, srv.max_page_size))
        result: dict[str, Any] = {"programs": infos}
        if cursor is not None:
            result["nextCursor"] = cursor
        return result

    table = {
        "devices/list": devices_list, "devices/describe": devices_describe, "properties/read": properties_read,
        "actions/invoke": actions_invoke, "operations/get": operations_get, "operations/wait": operations_wait,
        "operations/list": operations_list, "operations/cancel": operations_cancel, "stop": stop,
        "subscriptions/listen": listen, "leases/acquire": leases_acquire, "leases/renew": leases_renew,
        "leases/release": leases_release, "events/read": events_read, "programs/run": programs_run,
        "programs/register": programs_register, "programs/get": programs_get, "programs/list": programs_list,
    }
    for method, handler in table.items():
        rpc.register(method, handler, cancellable=True if method == "leases/acquire" else None)


__all__ = ["register"]
