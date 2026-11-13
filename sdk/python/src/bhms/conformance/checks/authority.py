"""Chapter 7.4 and 13: principals, scopes, envelopes, ownership, stop independence and policy changes.

These checks need several principals with known credentials, which only the built-in gateway fixture defines
(:data:`bhms.conformance.targets.ROLES`): ``admin``, ``agent`` (read, lease, ``invoke:u0/*/*`` and a position bound of
100 mm), ``reader``, ``stopper`` and ``nobody``. Against any other target they are skipped with that reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

from bhms.conformance.context import Context
from bhms.conformance.core import check
from bhms.conformance.targets import ROLES, Role

NEEDS = ("principals",)


def _axis(c: Context, namespace: str = "u0") -> str:
    for device in c.axis_ids:
        if device.startswith(namespace + "/") or "/" not in device:
            return device
    return c.axis()


@check("authority.credentials-required", ["BHMS-SEC-001"], needs=NEEDS, generic=True)
async def credentials_required(c: Context) -> None:
    """A network request without a valid credential is refused; discover alone may be answered without a principal."""
    import websockets
    from websockets.exceptions import InvalidStatus

    if c.target.kind == "ws":
        for token in (None, "wrong-token"):
            try:
                conn = await websockets.connect(c.target.url, subprotocols=["bhms"],
                                                additional_headers={"Authorization": f"Bearer {token}"} if token else None)
            except InvalidStatus as exc:
                c.expect(exc.response.status_code == 401, f"HTTP {exc.response.status_code} for token {token!r}, expected 401")
            else:
                await conn.close()
                c.fail(f"a WebSocket upgrade with token {token!r} was accepted")
    else:
        c.skip("the credential check is implemented for WebSocket targets")


@check("authority.default-deny", ["BHMS-SEC-010", "BHMS-AUTH-002"], needs=NEEDS, generic=True)
async def default_deny(c: Context) -> None:
    """A principal with no scopes sees nothing and can do nothing beyond server/discover."""
    async with c.fresh_wire("nobody") as wire:
        c.result(await wire.request("server/discover", {}), "discover without scopes")
        listing = c.result(await wire.request("devices/list", {}), "devices/list without scopes")
        c.expect(listing["devices"] == [], f"a principal with no scopes must see no devices, saw {len(listing['devices'])}", ("BHMS-SEC-010",))
        device = _axis(c)
        c.refused(await wire.request("properties/read", {"deviceId": device, "property": "position"}), "UNKNOWN_DEVICE",
                  what="read by a principal without read scope", ids=("BHMS-AUTH-002", "BHMS-SEC-010"))
        c.refused(await wire.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}}),
                  "UNKNOWN_DEVICE", what="invoke by a principal without read scope", ids=("BHMS-AUTH-002", "BHMS-SEC-010"))
        c.refused(await wire.request("stop", {"reason": "nobody", "deviceIds": [device]}), "UNAUTHORIZED", what="stop without the stop scope",
                  ids=("BHMS-SEC-010",))
        ops = await wire.request("operations/list", {})
        c.expect(ops.error is not None or ops.result["operations"] == [], "a principal with no scopes must see no operations", ("BHMS-SEC-010",))


@check("authority.scope-refusals", ["BHMS-AUTH-002", "BHMS-AUTH-012"], needs=NEEDS)
async def scope_refusals(c: Context) -> None:
    """UNAUTHORIZED names the missing scope; a fresh transaction read needs invoke scope as well as read."""
    device, other = _axis(c, "u0"), _axis(c, "u1")
    async with c.fresh_wire("reader") as reader:
        response = await reader.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}})
        data = c.refused(response, "UNAUTHORIZED", what="invoke with read scope only", ids=("BHMS-AUTH-002",))
        c.expect("invoke" in (data.get("hint", "") + response.error["message"]), f"the refusal must name the missing scope: {response.error}", ("BHMS-AUTH-002",))
        response = await reader.request("properties/read", {"deviceId": device, "property": "fifo", "fresh": True})
        data = c.refused(response, "UNAUTHORIZED", what="fresh transaction read with read scope only", ids=("BHMS-AUTH-012",))
        c.expect("invoke" in (data.get("hint", "") + response.error["message"]), "the refusal must name the invoke scope", ("BHMS-AUTH-012",))
    async with c.fresh_wire("agent") as agent:
        response = await agent.request("actions/invoke", {"deviceId": other, "action": "pulse", "arguments": {"count": 1}})
        c.refused(response, "UNAUTHORIZED", what="invoke outside the granted pattern", ids=("BHMS-AUTH-002",))
        c.expect(f"invoke:{other}/pulse" in json.dumps(response.error) or "invoke" in response.data.get("hint", ""), "the refusal must name the scope", ("BHMS-AUTH-002",))


@check("authority.effective-envelope", ["BHMS-AUTH-010", "BHMS-AUTH-011"], needs=NEEDS)
async def effective_envelope(c: Context) -> None:
    """Policy bounds narrow the device bounds: beyond them OUT_OF_RANGE with the policy bound, inside they work, and the
    served description shows the narrowed bound, never a wider one."""
    device = _axis(c)
    spec = ROLES["agent"].bounds["u0/axis-1/move_to"]["position"]["maximum"]
    async with c.fresh_wire("agent") as agent:
        response = await agent.request("actions/invoke", {"deviceId": device, "action": "move_to", "arguments": {"position": spec + 50}})
        data = c.refused(response, "OUT_OF_RANGE", field="arguments.position", what="a value beyond the policy bound", ids=("BHMS-AUTH-010",))
        c.expect(isinstance(data.get("bound"), dict) and data["bound"].get("maximum") == spec, f"bound must be the policy maximum {spec}: {data.get('bound')}",
                 ("BHMS-AUTH-010",))
        op = (await agent.request("actions/invoke", {"deviceId": device, "action": "move_to", "arguments": {"position": spec}, "waitMs": 2000}))
        c.expect(op.ok and op.result["operation"]["state"] == "completed", f"a value at the policy bound must be admitted: {op.describe()}", ("BHMS-AUTH-010",))
        served = (await agent.request("devices/describe", {"deviceId": device})).result["description"]
        maximum = served["actions"]["move_to"]["input"]["properties"]["position"]["maximum"]
    declared = (await c.describe(device))["actions"]["move_to"]["input"]["properties"]["position"]["maximum"]
    c.expect(maximum <= declared, f"policy must only narrow: served maximum {maximum} exceeds the device's {declared}", ("BHMS-AUTH-011",))


@check("authority.stop-scope-independence", ["BHMS-SEC-040", "BHMS-AUTH-020"], needs=NEEDS)
async def stop_scope(c: Context) -> None:
    """stop is a scope of its own; with it, stop is not blocked by another principal's leases or queue."""
    device = _axis(c)
    async with c.fresh_wire("agent") as agent, c.fresh_wire("stopper") as stopper:
        c.refused(await agent.request("stop", {"reason": "agent", "deviceIds": [device]}), "UNAUTHORIZED", what="stop by a principal with invoke but no stop",
                  ids=("BHMS-SEC-040",))
        invoke = await stopper.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}})
        c.expect(invoke.error is not None, "a principal with only stop must not be able to invoke", ("BHMS-SEC-040",))
        lease = (await agent.request("leases/acquire", {"resources": [f"{device}/clamp", f"{device}/motion"], "ttlMs": 60_000})).result["lease"]
        await agent.request("actions/invoke", {"deviceId": device, "action": "slow_move", "arguments": {"duration_ms": 8000}})
        for i in range(10):
            await agent.request("actions/invoke", {"deviceId": device, "action": "move_to", "arguments": {"position": 10 + i}})
        started = time.monotonic()
        result = await stopper.request("stop", {"reason": "stopper", "deviceIds": [device]})
        elapsed = time.monotonic() - started
        stops = c.result(result, "stop by a principal holding only the stop scope", ("BHMS-SEC-040",))["stops"]
        c.expect(elapsed < 2.0, f"stop was blocked by another principal's lease and queue ({elapsed:.2f}s)", ("BHMS-AUTH-020",))
        c.expect(stops[0]["outcome"] in ("confirmed", "initiated") and lease["leaseId"] in stops[0]["revokedLeases"],
                 f"stop must proceed and revoke the other principal's lease: {stops[0]}", ("BHMS-AUTH-020",))


@check("authority.ownership", ["BHMS-OPS-054", "BHMS-OPS-062", "BHMS-LSE-005"], needs=NEEDS)
async def ownership(c: Context) -> None:
    """Operations and leases belong to their creator: others cannot see, cancel, renew, release or use them."""
    device = _axis(c)
    async with c.fresh_wire("agent") as agent, c.fresh_wire("reader") as reader:
        op = c.result(await agent.request("actions/invoke", {"deviceId": device, "action": "slow_move", "arguments": {"duration_ms": 1500}}))["operation"]
        c.refused(await reader.request("operations/get", {"operationId": op["operationId"]}), "INVALID_ARGUMENT", field="operationId",
                  what="another principal's operation", ids=("BHMS-OPS-062",))
        c.refused(await reader.request("operations/cancel", {"operationId": op["operationId"]}), "UNAUTHORIZED",
                  what="cancel by another principal", ids=("BHMS-OPS-054",))
        mine = await c.call("operations/cancel", {"operationId": op["operationId"]})
        c.expect(mine.ok, f"an admin may cancel another principal's operation: {mine.describe()}", ("BHMS-OPS-054",))
        lease = c.result(await agent.request("leases/acquire", {"resources": [f"{device}/clamp"], "ttlMs": 30_000}))["lease"]
        for method, params in (("leases/renew", {"leaseId": lease["leaseId"], "ttlMs": 1000}), ("leases/release", {"leaseId": lease["leaseId"]})):
            c.refused(await c.call(method, params), "LEASE_CONFLICT", what=f"{method} of another principal's lease", ids=("BHMS-LSE-005",))
        c.refused(await c.invoke(device, "clamp", {"force": 5}, leaseId=lease["leaseId"]), "LEASE_CONFLICT", what="using another principal's lease",
                  ids=("BHMS-LSE-005",))
        await agent.request("leases/release", {"leaseId": lease["leaseId"]})


@check("authority.key-isolation", ["BHMS-AUTH-014", "BHMS-OPS-030"], needs=NEEDS)
async def key_isolation(c: Context) -> None:
    """The same operationKey from two principals is two operations (keys are per principal)."""
    device = _axis(c)
    key = c.unique("shared")
    before = await c.counter(device)
    async with c.fresh_wire("agent") as agent:
        mine = c.result(await agent.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}, "operationKey": key, "waitMs": 2000}))
        theirs = c.result(await c.call("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}, "operationKey": key, "waitMs": 2000}))
        c.expect(mine["operation"]["operationId"] != theirs["operation"]["operationId"] and theirs["replayed"] is False,
                 "two principals using one key must get two operations", ("BHMS-AUTH-014",))
        again = c.result(await agent.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}, "operationKey": key, "waitMs": 2000}))
        c.expect(again["replayed"] is True and again["operation"]["operationId"] == mine["operation"]["operationId"],
                 "a principal's own replay finds its own operation", ("BHMS-OPS-030",))
    c.expect(await c.counter(device) == before + 2, "each principal's request must have acted exactly once", ("BHMS-AUTH-014",))


@check("authority.policy-changes", ["BHMS-AUTH-013", "BHMS-SEC-012", "BHMS-SEC-011"], needs=("principals", "policy"), timeout=60)
async def policy_changes(c: Context) -> None:
    """A reloaded policy applies to new admissions at once (running work continues), is recorded as policy.changed, and a
    policy that widens a device bound does not take effect."""
    device = _axis(c)
    revoked = {**ROLES, "agent": Role(("read", "lease"), ROLES["agent"].bounds)}
    widened = {**ROLES, "agent": Role(ROLES["agent"].scopes, {"u0/axis-1/move_to": {"position": {"maximum": 5000}}})}
    async with c.fresh_wire("agent") as agent:
        running = c.result(await agent.request("actions/invoke", {"deviceId": device, "action": "slow_move", "arguments": {"duration_ms": 1200}}))["operation"]
        cursor = (await c.ok("events/read", {"limit": 1}))["cursor"] if "events" in c.caps else None
        try:
            await c.target.reload_policy(revoked)
            refused = await agent.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}})
            c.refused(refused, "UNAUTHORIZED", what="invoke after the scope was revoked", ids=("BHMS-AUTH-013",))
            final = await c.settle(running["operationId"], 8)
            c.expect(final["state"] == "completed", f"revoking a scope must not cancel running work: {final['state']}", ("BHMS-AUTH-013",))
            if cursor is not None:
                types = [e["type"] for e in (await c.ok("events/read", {"after": cursor, "limit": 200}))["events"]]
                c.expect("policy.changed" in types, f"a policy change must be recorded as a policy.changed event; saw {sorted(set(types))}", ("BHMS-SEC-012",))
            await c.target.reload_policy(ROLES)
            restored = await agent.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}, "waitMs": 1000})
            c.expect(restored.ok, f"restoring the policy must take effect without a restart: {restored.describe()}", ("BHMS-SEC-012",))
            await c.target.reload_policy(widened)
            served = (await agent.request("devices/describe", {"deviceId": device})).result["description"]
            maximum = served["actions"]["move_to"]["input"]["properties"]["position"]["maximum"]
            narrow = ROLES["agent"].bounds["u0/axis-1/move_to"]["position"]["maximum"]
            c.expect(maximum == narrow, f"a policy that widens a bound must be rejected at load; the served maximum became {maximum}, not {narrow}",
                     ("BHMS-SEC-011",))
        finally:
            with contextlib.suppress(Exception):
                await c.target.reload_policy(ROLES)
            await asyncio.sleep(0.1)
