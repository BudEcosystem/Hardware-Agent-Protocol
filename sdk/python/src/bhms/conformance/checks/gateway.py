"""The gateway profile (chapter 4.2, 7.6, 13): aggregation, cross-upstream leases, isolation of a stalled upstream."""

from __future__ import annotations

import asyncio
import json
import contextlib
import os
import signal
import time
from typing import Any

from bhms.conformance.context import Context
from bhms.conformance.core import check


def _namespaces(c: Context) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for device in c.axis_ids:
        out.setdefault(device.split("/", 1)[0] if "/" in device else "", []).append(device)
    return out


@check("gateway.namespaced-device-ids", ["BHMS-DEV-002"], profile="gateway", needs=("gateway",))
async def namespaced_ids(c: Context) -> None:
    """Upstreams that expose the same device id are served under distinct, prefixed, unique ids, in deviceId order."""
    ids = [d["deviceId"] for d in await c.devices(refresh=True)]
    c.expect(len(ids) == len(set(ids)), "deviceIds must be unique across upstreams")
    c.expect(ids == sorted(ids), "devices must be listed by deviceId")
    namespaces = _namespaces(c)
    c.expect(len(namespaces) >= 2 and all(namespaces), f"two upstreams that both expose axis-1 must yield two distinct ids, found {c.axis_ids}")
    for device in ids:
        c.expect("/" in device, f"{device}: an upstream id that collides must be prefixed <upstream>/<deviceId>")
        summary = (await c.describe(device))["deviceId"]
        c.expect(summary == device, f"the description of {device} names {summary}")


@check("gateway.ids-stable-across-restart", ["BHMS-DEV-002", "BHMS-DEV-001"], profile="gateway", needs=("gateway", "restart"), timeout=90)
async def ids_stable(c: Context) -> None:
    """Device ids and digests are the same after the gateway restarts."""
    before = {d["deviceId"]: d["digest"] for d in await c.devices(refresh=True)}
    await c.reconnect_base(await c.target.restart())
    await c.locate()
    after = {d["deviceId"]: d["digest"] for d in await c.devices(refresh=True)}
    c.expect(before == after, f"device ids or digests changed across a gateway restart: {sorted(set(before) ^ set(after))}")


@check("gateway.cross-upstream-lease", ["BHMS-LSE-013", "BHMS-LSE-001"], profile="gateway", needs=("gateway", "leases"))
async def cross_upstream_lease(c: Context) -> None:
    """One lease spans devices of two upstreams: all or nothing; usable on both; released together."""
    namespaces = _namespaces(c)
    first, second = (devices[0] for devices in list(namespaces.values())[:2])
    a, b = f"{first}/clamp", f"{second}/clamp"
    lease = (await c.ok("leases/acquire", {"resources": [b, a], "ttlMs": 30_000}))["lease"]
    c.expect(sorted(lease["resources"]) == sorted([a, b]), f"the lease must cover both upstreams' resources: {lease['resources']}")
    for device in (first, second):
        op = await c.run(device, "clamp", {"force": 5}, leaseId=lease["leaseId"])
        c.expect(op["state"] == "completed", f"clamp on {device} under the cross-upstream lease ended {op['state']}")
    held = await c.call("leases/acquire", {"resources": [a], "ttlMs": 30_000})
    c.refused(held, "LEASE_CONFLICT", what="a lease on a resource of the cross-upstream lease")
    await c.ok("leases/release", {"leaseId": lease["leaseId"]})
    for resource in (a, b):
        free = await c.ok("leases/acquire", {"resources": [resource], "ttlMs": 30_000})
        await c.ok("leases/release", {"leaseId": free["lease"]["leaseId"]})
    blocker = (await c.ok("leases/acquire", {"resources": [b], "ttlMs": 30_000}))["lease"]
    try:
        c.refused(await c.call("leases/acquire", {"resources": [a, b], "ttlMs": 30_000}), "LEASE_CONFLICT", what="spanning acquire with one resource held")
        alone = await c.ok("leases/acquire", {"resources": [a], "ttlMs": 30_000})
        await c.ok("leases/release", {"leaseId": alone["lease"]["leaseId"]})
    finally:
        await c.ok("leases/release", {"leaseId": blocker["leaseId"]})


@check("gateway.stalled-upstream-isolated", ["BHMS-SEC-061"], profile="gateway", needs=("gateway", "restart"), timeout=60)
async def stalled_upstream(c: Context) -> None:
    """With one upstream process stopped (SIGSTOP), requests to the other upstream keep their latency."""
    victims = {ns: up.server_pid() for ns, up in c.target.upstreams.items()}
    if len(victims) < 2 or not all(pid and os.path.isdir(f"/proc/{pid}") for pid in victims.values()):
        c.skip("the runner cannot find the upstream processes (needs the built-in gateway fixture on Linux)")
    children = [victims[ns] for ns in sorted(victims)]
    devices = [devs[0] for devs in list(_namespaces(c).values())[:2]]
    victim = children[0]
    os.kill(victim, signal.SIGSTOP)
    try:
        async def timed(device: str) -> tuple[str, bool, float]:
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(c.call("properties/read", {"deviceId": device, "property": "counter", "fresh": True}), 4.0)
                return device, response.ok, time.monotonic() - started
            except asyncio.TimeoutError:
                return device, False, time.monotonic() - started

        results = await asyncio.gather(*(timed(d) for d in devices))
        fast = [r for r in results if r[1] and r[2] < 1.5]
        c.expect(fast, f"no request was answered quickly while one upstream was stalled: {results}")
        for device in devices:  # on the same connection: a new connection to a stdio gateway would be a new gateway process
            answered = await asyncio.wait_for(c.call("devices/describe", {"deviceId": device}), 4.0)
            c.expect(answered.ok or answered.code in ("DEVICE_UNAVAILABLE", "BUSY"),
                     f"a stalled upstream must give DEVICE_UNAVAILABLE or BUSY, not {answered.describe()}")
    finally:
        os.kill(victim, signal.SIGCONT)
    deadline = time.monotonic() + 30  # a later answer to a liveness probe restores the upstream; the next checks need it
    while time.monotonic() < deadline:
        again = await asyncio.gather(*(c.call("properties/read", {"deviceId": d, "property": "counter", "fresh": True}) for d in devices))
        if all(r.ok for r in again):
            return
        await asyncio.sleep(0.3)
    c.fail("the stalled upstream was not restored within 30 s of resuming (a later answer to a liveness probe must restore it)")


def _local(device: str) -> str:
    """The upstream's own id of a gateway device id (``u0/axis-1`` -> ``axis-1``)."""
    return device.split("/", 1)[1]


@check("gateway.trace-context-propagated", ["BHMS-LIF-018"], profile="gateway", needs=("gateway", "faults"))
async def trace_context(c: Context) -> None:
    """traceparent and tracestate sent to the gateway reach the upstream unchanged."""
    axis = c.axis()
    trace = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", "tracestate": f"conf={c.unique('t')}"}
    c.result(await c.call("properties/read", {"deviceId": axis, "property": "counter", "fresh": True}, meta=c.wire.meta(**trace)))
    seen = (await c.counters(axis)).get("trace", {})
    c.expect(seen == trace, f"the upstream saw {seen}, the client sent {trace}")


@check("gateway.fence-forwarded", ["BHMS-LSE-011"], profile="gateway", needs=("gateway", "faults", "leases"))
async def fence_forwarded(c: Context) -> None:
    """The gateway forwards its lease so that the enforcement point can reject a superseded holder: the upstream's record of this
    very operation (found by its derived key, BHMS-AUTH-014) carries a lease id and fence, and after the upstream's lease is
    superseded through a direct path, the gateway's request under its still-active lease is refused FENCED with no device effect."""
    import base64
    import hashlib

    axis = c.axis()
    key = c.unique("fence")
    wire = c._fault_wire(axis)
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 60_000}))["lease"]
    try:
        op = await c.run(axis, "clamp", {"force": 3}, leaseId=lease["leaseId"], operationKey=key)
        c.expect(op["state"] == "completed", f"clamp under the gateway lease ended {op['state']}")
        principal = c.discover_result["principal"]["id"]
        gateway_id = c.discover_result["serverInfo"]["name"]
        digest = hashlib.sha256(f"{gateway_id}\n{principal}\n{key}".encode()).digest()
        upstream_key = "g-" + base64.b32encode(digest).decode().lower().rstrip("=")[:26]  # BHMS-AUTH-014, pinned formula
        upstream_ops = (await c.ok("operations/list", {"deviceId": _local(axis), "limit": 100}, wire=wire))["operations"]
        mine = [o for o in upstream_ops if o["operationKey"] == upstream_key]
        c.expect(mine, f"the upstream has no operation under the derived key {upstream_key}")
        c.expect(mine[0].get("leaseId") and isinstance(mine[0].get("fence"), int) and mine[0]["fence"] >= 1,
                 f"the upstream's record of this operation carries no lease id and fence: {mine[0].get('leaseId')} {mine[0].get('fence')}")
        c.expect(mine[0]["leaseId"] != lease["leaseId"], "the gateway must forward the upstream's own lease id, not its own")
        base = await c.counter(axis)
        # supersede the upstream's lease through a path that bypasses the gateway: a stop revokes it, a newer lease takes its place
        await c.ok("stop", {"reason": "conformance: supersede the upstream lease", "deviceIds": [_local(axis)]}, wire=wire)
        newer = (await c.ok("leases/acquire", {"resources": [f"{_local(axis)}/clamp"], "ttlMs": 30_000}, wire=wire))["lease"]
        try:
            stale = await c.invoke(axis, "clamp", {"force": 3}, leaseId=lease["leaseId"])
            c.refused(stale, "FENCED", what="a request under a lease the enforcement point has superseded")
            c.expect(await c.counter(axis) == base, "the superseded holder's command reached the device")
        finally:
            await c.ok("leases/release", {"leaseId": newer["leaseId"]}, wire=wire)
    finally:
        with contextlib.suppress(Exception):
            await c.ok("leases/release", {"leaseId": lease["leaseId"]})


@check("gateway.refuses-wrong-upstream-digest", ["BHMS-SEC-022"], profile="gateway", needs=("gateway", "faults"), timeout=60)
async def wrong_upstream_digest(c: Context) -> None:
    """A description whose upstream digest is not the digest of the description is not served: an upstream that revises its
    description while serving a wrong digest does not change what the gateway serves; the revision is served once the digest is
    right."""
    import asyncio
    import time

    victim, healthy = c.axis_ids[-1], c.axis_ids[0]
    c.expect(victim != healthy, "needs two upstreams")

    async def revision() -> str | None:
        """The revision text of the served description, None when the device is not served at all."""
        c._descriptions.pop(victim, None)
        response = await c.call("devices/describe", {"deviceId": victim})
        if response.code == "UNKNOWN_DEVICE":
            return None
        events = (c.result(response)["description"].get("events") or {})
        return str((events.get("conformance.revised") or {}).get("description", ""))

    before = await revision()
    await c.inject("bad_digest", victim)
    try:
        await c.inject("change_description", victim)  # a new description body, advertised with a digest that does not match it
        await asyncio.sleep(2.5)
        served = await revision()
        # refused or not served (the spec allows either): what must never happen is that the revised body is served
        c.expect(served is None or served == before, "the gateway served a description whose upstream digest is wrong (BHMS-SEC-022)")
        c.expect(any(d["deviceId"] == healthy for d in await c.devices(refresh=True)), "the other upstream's devices must stay served")
    finally:
        await c.inject("good_digest", victim)
    deadline = time.monotonic() + 10
    now = await revision()
    while (now is None or now == before) and time.monotonic() < deadline:
        await asyncio.sleep(0.3)
        now = await revision()
    c.expect(now is not None and now != before, "the revised description must be served once the upstream's digest is right again")


@check("gateway.restart-recovery", ["BHMS-OPS-005", "BHMS-OPS-034", "BHMS-OPS-063", "BHMS-OPS-080", "BHMS-OPS-081", "BHMS-LSE-003",
                                    "BHMS-DEV-001", "BHMS-EVT-011", "BHMS-LIF-045"],
       profile="gateway", needs=("gateway", "restart", "durable"), timeout=120)
async def gateway_restart(c: Context) -> None:
    """Kill the gateway (its upstreams are independent processes and survive) with a keyed completed operation, a running one
    and a lease: same epoch and records after restart; the in-flight operation passes through unknown and is reconciled with the
    upstream without a re-send (the device's counter does not move); a wiped state is a new epoch and a gap."""
    import asyncio

    axis = c.axis()
    key = c.unique("gw-durable")
    done = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "operationKey": key, "waitMs": 3000})
    running = await c.invoke_op(axis, "slow_move", {"duration_ms": 20_000})
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 60_000}))["lease"]
    counter_before = await c.counter(axis)
    cursor = (await c.ok("events/read", {"limit": 500}))["cursor"] if "events" in c.caps else None
    epoch = c.discover_result["epoch"]
    digest = (await c.describe(axis))["digest"]
    await c.reconnect_base(await c.target.restart(kill=True))
    await c.locate()
    c.expect(c.discover_result["epoch"] == epoch, f"a durable gateway keeps its epoch across a restart: {epoch} -> {c.discover_result['epoch']}")
    c.expect(c.axis() == axis and (await c.describe(axis))["digest"] == digest, "device ids and digests must survive a gateway restart")
    again = await c.ok("actions/invoke", {"deviceId": axis, "action": "pulse", "arguments": {"count": 1}, "operationKey": key})
    c.expect(again["replayed"] is True and again["operation"]["operationId"] == done["operation"]["operationId"],
             "a key must survive a gateway restart (replayed true, same operation)")
    c.expect((await c.get_op(done["operation"]["operationId"]))["state"] == "completed", "a settled operation must survive a gateway restart")
    deadline = asyncio.get_running_loop().time() + 15
    while True:  # the in-flight operation is found dispatching/running at start: unknown, then reconciled with the upstream
        interrupted = await c.get_op(running["operationId"])
        kinds = [(h.get("kind"), h.get("state")) for h in interrupted.get("history", [])]
        if ("state", "unknown") in kinds and interrupted["state"] != "unknown" or asyncio.get_running_loop().time() > deadline:
            break
        await asyncio.sleep(0.3)
    c.expect(("state", "unknown") in kinds, f"in-flight work must pass through unknown after a restart (BHMS-OPS-080); history: {kinds}")
    if interrupted["state"] != "unknown":
        c.expect(any(k == "reconciliation" for k, _ in kinds), f"leaving unknown needs a reconciliation entry (BHMS-OPS-005); history: {kinds}")
        c.expect((interrupted.get("error") or {}).get("mayHaveActed") is not False or interrupted["state"] != "failed",
                 "a command the upstream is still executing must not reconcile to a failure with mayHaveActed false")
    c.expect(await c.counter(axis) == counter_before, "the restarted gateway re-sent a command to the device (BHMS-OPS-081)")
    fresh = (await c.ok("leases/acquire", {"resources": [f"{axis}/motion"], "ttlMs": 5_000}))["lease"]
    c.expect(fresh["fence"] > lease["fence"], f"fences must increase across a gateway restart: {lease['fence']} -> {fresh['fence']}")
    await c.ok("leases/release", {"leaseId": fresh["leaseId"]})
    await c.ok("stop", {"reason": "conformance: end the in-flight operation", "deviceIds": [axis]})
    await c.target.stop_base(kill=False)
    await c.target.wipe_state()
    await c.reconnect_base(await c.target.open_base())
    await c.locate()
    c.expect(c.discover_result["epoch"] != epoch, "a wiped gateway store must start a new epoch")
    if cursor is not None:
        response = await c.call("events/read", {"after": cursor})
        c.expect(response.ok and response.result["gap"] is True,
                 f"reading from a cursor of an earlier epoch must report gap true (BHMS-EVT-011): {response.describe()}")


@check("security.schema-validation-bounds", ["BHMS-SEC-021"], needs=("faults",), timeout=120)
async def schema_validation_bounds(c: Context) -> None:
    """A consumer of foreign descriptions (a gateway) validates schemas with bounded resources and never fetches. Each rule is
    tested on its own, with a correct digest every time: an upstream schema nested 64 deep (``deep``), one with 20 000 subschemas
    (``wide``) and a small one with a remote ``$ref`` (``remote_ref``) must each stop being served while the gateway stays
    responsive, and nothing may connect to the referenced URL. A gateway that enforces only some of the rules fails."""
    if not c.is_gateway:
        c.not_applicable("a device server validates only the schemas of its own devices; foreign schemas are validated by gateways and clients")
    victim = c.axis_ids[-1]
    connections: list[str] = []

    async def trap(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append("connected")
        writer.close()

    async def served_again() -> bool:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not any(d["deviceId"] == victim for d in await c.devices(refresh=True)):
            await asyncio.sleep(0.3)
        c._descriptions.clear()
        return any(d["deviceId"] == victim for d in await c.devices(refresh=True))

    server = await asyncio.start_server(trap, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/hostile-schema.json"
    variants = {"deep": "nested 64 levels deep", "wide": "of 20 000 subschemas", "remote_ref": "with a remote $ref"}
    problems: list[str] = []
    try:
        for variant, what in variants.items():
            await c.ok("x-conformance/inject", {"fault": "hostile_schema", "variant": variant, "url": url}, wire=c._fault_wire(victim))
            worst = 0.0
            for _ in range(12):  # about 3.5 s: the hostile description reaches the gateway; it must stay responsive meanwhile
                started = time.monotonic()
                await c.ok("devices/list", {"limit": 10})
                worst = max(worst, time.monotonic() - started)
                await asyncio.sleep(0.3)
            response = await c.call("devices/describe", {"deviceId": victim})
            if response.ok and _is_hostile(response.result, variant, url):
                problems.append(f"{variant}: the gateway still serves a schema {what}")
            if worst >= 3.0:
                problems.append(f"{variant}: the gateway stalled for {worst:.1f}s while handling the hostile schema")
            await asyncio.sleep(0.3)
            if connections:
                problems.append(f"{variant}: the gateway connected to the URL of a remote $ref (no network fetch)")
                connections.clear()
            await c.ok("x-conformance/inject", {"fault": "none"}, wire=c._fault_wire(victim))
            if not await served_again():
                problems.append(f"{variant}: {victim} is not served again after its schema became sane")
    finally:
        await c.ok("x-conformance/inject", {"fault": "none"}, wire=c._fault_wire(victim))
        server.close()
        await server.wait_closed()
    c.expect(not problems, "schema validation is not bounded (BHMS-SEC-021): " + "; ".join(problems))


def _is_hostile(describe_result: Any, variant: str, url: str) -> bool:
    """Whether a devices/describe result still carries the conformance device's hostile ``pulse`` schema of this variant."""
    try:
        count = describe_result["description"]["actions"]["pulse"]["input"]["properties"]["count"]
    except (KeyError, TypeError):
        return False
    if not isinstance(count, dict):
        return False
    if variant == "wide":
        return isinstance(count.get("anyOf"), list) and len(count["anyOf"]) > 10_000
    nested = count["properties"].get("x") if isinstance(count.get("properties"), dict) else None
    if variant == "remote_ref":
        return isinstance(nested, dict) and nested.get("$ref") == url
    return isinstance(nested, dict) and "properties" in nested
