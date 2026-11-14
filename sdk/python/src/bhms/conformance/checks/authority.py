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
from typing import Any

from bhms.conformance.context import Context
from bhms.conformance.core import NotApplicable, check
from bhms.conformance.targets import ROLES, Role

NEEDS = ("principals",)


def _axis(c: Context, namespace: str = "u0") -> str:
    for device in c.axis_ids:
        if device.startswith(namespace + "/") or "/" not in device:
            return device
    return c.axis()


def _outside_grant(c: Context) -> tuple[str, str, dict[str, object]]:
    """A device, action and arguments outside what the ``agent`` role may invoke (behind the gateway: the other upstream; on a
    single device server: ``pump-1``)."""
    if c.is_gateway:
        return _axis(c, "u1"), "pulse", {"count": 1}
    return c.pump(), "dispense", {"volume": 5.0}


@check("authority.default-deny", ["BHMS-SEC-010", "BHMS-AUTH-002", "BHMS-DEV-010"], profile="authority", needs=NEEDS)
async def default_deny(c: Context) -> None:
    """A principal with no scopes sees nothing and can do nothing beyond server/discover."""
    async with c.fresh_wire("nobody") as wire:
        c.result(await wire.request("server/discover", {}), "discover without scopes")
        listing = c.result(await wire.request("devices/list", {}), "devices/list without scopes")
        c.expect(listing["devices"] == [], f"a principal with no scopes must see no devices, saw {len(listing['devices'])}", ("BHMS-SEC-010", "BHMS-DEV-010"))
        c.expect(("nextCursor" not in listing) and "total" not in listing, "devices/list must not reveal hidden devices through counts or cursors",
                 ("BHMS-DEV-010",))
        device = _axis(c)
        c.refused(await wire.request("properties/read", {"deviceId": device, "property": "position"}), "UNKNOWN_DEVICE",
                  what="read by a principal without read scope", ids=("BHMS-AUTH-002", "BHMS-SEC-010"))
        c.refused(await wire.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}}),
                  "UNKNOWN_DEVICE", what="invoke by a principal without read scope", ids=("BHMS-AUTH-002", "BHMS-SEC-010"))
        c.refused(await wire.request("stop", {"reason": "nobody", "deviceIds": [device]}), "UNAUTHORIZED", what="stop without the stop scope",
                  ids=("BHMS-SEC-010",))
        ops = await wire.request("operations/list", {})
        c.expect(ops.error is not None or ops.result["operations"] == [], "a principal with no scopes must see no operations", ("BHMS-SEC-010",))


@check("authority.scope-refusals", ["BHMS-AUTH-002", "BHMS-AUTH-012"], profile="authority", needs=NEEDS)
async def scope_refusals(c: Context) -> None:
    """UNAUTHORIZED names the missing scope; a fresh transaction read needs invoke scope as well as read."""
    device = _axis(c, "u0")
    other, other_action, other_args = _outside_grant(c)
    async with c.fresh_wire("reader") as reader:
        response = await reader.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}})
        data = c.refused(response, "UNAUTHORIZED", what="invoke with read scope only", ids=("BHMS-AUTH-002",))
        c.expect("invoke" in (data.get("hint", "") + response.error["message"]), f"the refusal must name the missing scope: {response.error}", ("BHMS-AUTH-002",))
        response = await reader.request("properties/read", {"deviceId": device, "property": "fifo", "fresh": True})
        data = c.refused(response, "UNAUTHORIZED", what="fresh transaction read with read scope only", ids=("BHMS-AUTH-012",))
        c.expect("invoke" in (data.get("hint", "") + response.error["message"]), "the refusal must name the invoke scope", ("BHMS-AUTH-012",))
    async with c.fresh_wire("agent") as agent:
        response = await agent.request("actions/invoke", {"deviceId": other, "action": other_action, "arguments": other_args})
        c.refused(response, "UNAUTHORIZED", what="invoke outside the granted pattern", ids=("BHMS-AUTH-002",))
        c.expect(f"invoke:{other}/{other_action}" in json.dumps(response.error) or "invoke" in response.data.get("hint", ""),
                 "the refusal must name the scope", ("BHMS-AUTH-002",))


@check("authority.effective-envelope", ["BHMS-AUTH-010", "BHMS-AUTH-011"], profile="authority", needs=NEEDS)
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


@check("authority.stop-scope-independence", ["BHMS-SEC-040", "BHMS-AUTH-020"], profile="authority", needs=NEEDS)
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


@check("authority.ownership", ["BHMS-OPS-054", "BHMS-OPS-062", "BHMS-LSE-005"], profile="authority", needs=NEEDS)
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


@check("authority.key-isolation", ["BHMS-AUTH-014", "BHMS-OPS-030"], profile="authority", needs=NEEDS)
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


@check("authority.policy-changes", ["BHMS-AUTH-013", "BHMS-SEC-012", "BHMS-SEC-011"], profile="authority", needs=("principals", "policy"), timeout=60)
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
            narrow = ROLES["agent"].bounds["u0/axis-1/move_to"]["position"]["maximum"]
            beyond = await agent.request("actions/invoke", {"deviceId": device, "action": "move_to", "arguments": {"position": narrow + 50}})
            data = c.refused(beyond, "OUT_OF_RANGE", what="a value beyond the old bound after a policy that widens it was offered",
                             ids=("BHMS-SEC-011",))
            c.expect(isinstance(data.get("bound"), dict) and data["bound"].get("maximum") == narrow,
                     f"a policy that widens a device bound must be rejected at load; the effective bound became {data.get('bound')}, not {narrow}",
                     ("BHMS-SEC-011",))
        finally:
            with contextlib.suppress(Exception):
                await c.target.reload_policy(ROLES)
            await asyncio.sleep(0.1)


@check("authority.hazardous-needs-literal-scope", ["BHMS-AUTH-003"], profile="authority", needs=NEEDS)
async def hazardous_literal(c: Context) -> None:
    """A glob invoke scope grants ordinary actions but never a hazardous one; only a scope naming it literally does."""
    device = _axis(c)
    async with c.fresh_wire("globber") as glob, c.fresh_wire("exact") as exact:
        lease = c.result(await glob.request("leases/acquire", {"resources": [f"{device}/clamp"], "ttlMs": 30_000}))["lease"]
        ok = await glob.request("actions/invoke", {"deviceId": device, "action": "clamp", "arguments": {"force": 5}, "leaseId": lease["leaseId"], "waitMs": 2000})
        c.expect(ok.ok, f"the glob scope must grant an ordinary action: {ok.describe()}", ("BHMS-AUTH-003",))
        refused = await glob.request("actions/invoke", {"deviceId": device, "action": "overdrive", "arguments": {"force": 5}, "leaseId": lease["leaseId"]})
        c.refused(refused, "UNAUTHORIZED", what="a hazardous action under a glob scope", ids=("BHMS-AUTH-003",))
        await glob.request("leases/release", {"leaseId": lease["leaseId"]})
        lease = c.result(await exact.request("leases/acquire", {"resources": [f"{device}/clamp"], "ttlMs": 30_000}))["lease"]
        granted = await exact.request("actions/invoke", {"deviceId": device, "action": "overdrive", "arguments": {"force": 5}, "leaseId": lease["leaseId"], "waitMs": 2000})
        c.expect(granted.ok and granted.result["operation"]["state"] == "completed",
                 f"a scope naming the hazardous action must grant it: {granted.describe()}", ("BHMS-AUTH-003",))
        await exact.request("leases/release", {"leaseId": lease["leaseId"]})


@check("authority.read-revocation-ends-delivery", ["BHMS-LIF-042"], profile="authority", needs=("principals", "policy"), timeout=60)
async def read_revocation(c: Context) -> None:
    """Notifications are authorized at delivery: after a principal's read scope is revoked, nothing more reaches it."""
    if "events" not in c.caps:
        c.not_applicable("the server does not advertise events")
    device = _axis(c)
    revoked = {**ROLES, "reader": Role(())}
    async with c.fresh_wire("reader") as reader:
        stream, _ = await reader.listen({"events": {}})
        try:
            await c.ok("stop", {"reason": "conformance delivery", "deviceIds": [device]})
            seen = await stream.until(lambda n: n["method"] == "notifications/event", 3.0)
            c.expect(seen is not None, "the reader must receive events while it has read scope")
            await c.target.reload_policy(revoked)
            stream.drain()
            await c.ok("stop", {"reason": "conformance after revocation", "deviceIds": [device]})
            late = await stream.until(lambda n: n["method"] == "notifications/event", 1.5)
            c.expect(late is None, "an event was delivered after the principal's read scope was revoked")
        finally:
            await c.target.reload_policy(ROLES)
            await stream.cancel()


def _program(steps: list[dict[str, object]], name: str) -> dict[str, object]:
    return {"bhmsProgram": "2026-11-13", "name": name, "description": "authority conformance program",
            "input": {"type": "object", "additionalProperties": False, "properties": {}}, "maxDurationMs": 60_000, "steps": steps}


@check("authority.programs-need-authority", ["BHMS-PRG-006", "BHMS-PRG-021"], profile="authority", needs=("principals", "cap:programs"))
async def programs_authority(c: Context) -> None:
    """programs:run, an invoke scope for every step and a covering lease are checked before step 1, at every run, whoever
    registered the program."""
    device, pump = _axis(c), c.pump()
    base = await c.counter(device)
    own = _program([{"kind": "invoke", "deviceId": device, "action": "pulse", "arguments": {"count": 1}}], "auth_own")
    outside = _program([{"kind": "invoke", "deviceId": pump, "action": "dispense", "arguments": {"volume": 5.0}}], "auth_outside")
    leased = _program([{"kind": "invoke", "deviceId": device, "action": "clamp", "arguments": {"force": 5}}], "auth_leased")
    async with c.fresh_wire("reader") as reader, c.fresh_wire("agent") as agent:
        c.refused(await reader.request("programs/run", {"program": own, "arguments": {}}), "UNAUTHORIZED",
                  what="a program run without programs:run", ids=("BHMS-PRG-006",))
        c.refused(await agent.request("programs/run", {"program": outside, "arguments": {}}), "UNAUTHORIZED",
                  what="a program with a step outside the invoke grant", ids=("BHMS-PRG-006",))
        refused = await agent.request("programs/run", {"program": leased, "arguments": {}})
        c.refused(refused, "LEASE_REQUIRED", what="a program whose step needs a lease, run without one", ids=("BHMS-PRG-006",))
        info = (await c.ok("programs/register", {"program": own}))["info"]
        c.refused(await reader.request("programs/run", {"digest": info["digest"], "arguments": {}}), "UNAUTHORIZED",
                  what="running a registered program without programs:run", ids=("BHMS-PRG-021",))
        registered = (await c.ok("programs/register", {"program": outside}))["info"]
        c.refused(await agent.request("programs/run", {"digest": registered["digest"], "arguments": {}}), "UNAUTHORIZED",
                  what="registration must not grant the step authority", ids=("BHMS-PRG-021",))
    c.expect(await c.counter(device) == base, "a refused program reached the device")


@check("authority.operator-resolution", ["BHMS-OPS-100", "BHMS-OPS-101", "BHMS-OPS-102"], profile="authority",
       needs=("principals", "faults"))
async def operator_resolution(c: Context) -> None:
    """operations/resolve: only an operator may call it; the device is asked first and its evidence wins; what the device
    cannot explain is recorded as the operator's statement, after the unchanged history, and audited."""
    if not (c.caps.get("operations") or {}).get("resolve"):
        raise NotApplicable("the server does not offer operations/resolve (capabilities.operations.resolve)")
    device = _axis(c)
    basis = "conformance: axis inspected, at rest; treating the pulse as not completed"
    async with c.fresh_wire("agent") as agent, c.fresh_wire("reader") as reader, c.fresh_wire("resolver") as resolver:
        async def lose() -> dict[str, Any]:
            await c.inject("crash_next")
            op = c.result(await agent.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1},
                                                                 "waitMs": 5000}))["operation"]
            c.expect(op["state"] == "unknown", f"a crashed handler must leave the operation unknown, is {op['state']}")
            return op

        await c.inject("amnesia")  # the device cannot say what happened
        op = await lose()
        resolution = {"state": "failed", "basis": basis}
        params = {"operationId": op["operationId"], "resolution": resolution}
        for name, wire in (("the owner", agent), ("a read-only principal", reader)):
            refused = c.refused(await wire.request("operations/resolve", params), "UNAUTHORIZED",
                                what=f"operations/resolve by {name}", ids=("BHMS-OPS-100",))
            c.expect("operations:resolve" in str(refused.get("hint", "")), "the refusal must name the scope operations:resolve", ("BHMS-OPS-100",))
        asked = c.result(await resolver.request("operations/resolve", {"operationId": op["operationId"]}),
                         "operations/resolve by a principal with operations:resolve", ("BHMS-OPS-100",))["operation"]
        c.expect(asked["state"] == "unknown" and not [h for h in asked["history"] if h["kind"] == "reconciliation"],
                 f"without a resolution nothing may be recorded when the device cannot say: {asked['state']}", ("BHMS-OPS-101",))
        claim = await resolver.request("operations/resolve", {"operationId": op["operationId"], "resolution": {
            "state": "failed", "basis": basis, "mayHaveActed": False, "effect": "unverified"}})
        c.refused(claim, "INVALID_ARGUMENT", what="a resolution that claims nothing happened without effect none", ids=("BHMS-OPS-102",))
        before = asked["history"]
        done = c.result(await resolver.request("operations/resolve", params))["operation"]
        c.expect(done["state"] == "failed" and (done.get("error") or {}).get("mayHaveActed") is True,
                 f"the operator's resolution must be recorded: {done['state']}", ("BHMS-OPS-102",))
        c.expect(done["history"][:len(before)] == before, "earlier history entries were changed or removed", ("BHMS-OPS-102",))
        last = done["history"][-1]
        me = (c.result(await resolver.request("server/discover", {})).get("principal") or {}).get("id")
        c.expect(last["kind"] == "reconciliation" and (last.get("operator") or {}).get("basis") == basis
                 and last["operator"].get("principal") == me,
                 f"the entry must be a reconciliation carrying operator {{principal: {me}, basis}}: {last}", ("BHMS-OPS-102",))
        if "events" in c.caps:
            events = [e for e in (await c.ok("events/read", {"types": ["operation.resolved"], "limit": 100}))["events"]
                      if e.get("operationId") == op["operationId"]]
            c.expect(any((e.get("data") or {}).get("source") == "operator" for e in events),
                     "an operator's resolution must be recorded as an operation.resolved event with source operator", ("BHMS-OPS-102",))
        same = c.result(await resolver.request("operations/resolve", {"operationId": op["operationId"], "resolution": {
            "state": "failed", "basis": "a second opinion"}}))["operation"]
        c.expect(same["history"] == done["history"], "resolving an operation that is no longer unknown must change nothing", ("BHMS-OPS-101",))
        free = c.result(await agent.request("actions/invoke", {"deviceId": device, "action": "pulse", "arguments": {"count": 1}, "waitMs": 5000}))
        c.expect(free["operation"]["state"] == "completed", "after the resolution the resource must admit new work", ("BHMS-OPS-102",))
        await c.inject("none")  # the device can explain itself again: its evidence wins over the operator
        op = await lose()
        won = c.result(await resolver.request("operations/resolve", {"operationId": op["operationId"], "resolution": {
            "state": "completed", "basis": "the operator believes it finished", "result": {"pulses": 1}}}))["operation"]
        entry = [h for h in won["history"] if h["kind"] == "reconciliation"][-1]
        c.expect(won["state"] == "failed" and "operator" not in entry,
                 f"device evidence (started, not finished) must be recorded, not the operator's claim: {won['state']} {entry}", ("BHMS-OPS-101",))
