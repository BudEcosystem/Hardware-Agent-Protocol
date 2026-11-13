"""The gateway profile (chapter 4.2, 7.6, 13): aggregation, cross-upstream leases, isolation of a stalled upstream."""

from __future__ import annotations

import asyncio
import os
import signal
import time

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
    """The gateway forwards its lease to the enforcement point: the upstream's own record of the operation carries a lease id
    and a fence (so a superseded holder can be rejected there)."""
    axis = c.axis()
    key = c.unique("fence")
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 30_000}))["lease"]
    try:
        op = await c.run(axis, "clamp", {"force": 3}, leaseId=lease["leaseId"], operationKey=key)
    finally:
        await c.ok("leases/release", {"leaseId": lease["leaseId"]})
    c.expect(op["state"] == "completed", f"clamp under the gateway lease ended {op['state']}")
    wire = c._fault_wire(axis)
    upstream_ops = (await c.ok("operations/list", {"deviceId": _local(axis), "limit": 50}, wire=wire))["operations"]
    forwarded = [o for o in upstream_ops if o["action"] == "clamp" and o.get("leaseId") and isinstance(o.get("fence"), int)]
    c.expect(forwarded, "the upstream recorded no clamp operation under a lease with a fence: the gateway did not forward it")


@check("gateway.refuses-wrong-upstream-digest", ["BHMS-SEC-022"], profile="gateway", needs=("gateway", "faults"), timeout=60)
async def wrong_upstream_digest(c: Context) -> None:
    """A description whose upstream digest is not the digest of the description is not served: an upstream that revises its
    description while serving a wrong digest does not change what the gateway serves; the revision is served once the digest is
    right."""
    import asyncio
    import time

    victim, healthy = c.axis_ids[-1], c.axis_ids[0]
    c.expect(victim != healthy, "needs two upstreams")

    async def revision() -> str:
        c._descriptions.pop(victim, None)
        events = (await c.describe(victim)).get("events") or {}
        return str((events.get("conformance.revised") or {}).get("description", ""))

    before = await revision()
    await c.inject("bad_digest", victim)
    try:
        await c.inject("change_description", victim)  # a new description body, advertised with a digest that does not match it
        await asyncio.sleep(2.5)
        c.expect(await revision() == before, "the gateway served a description whose upstream digest is wrong (BHMS-SEC-022)")
        c.expect(any(d["deviceId"] == healthy for d in await c.devices(refresh=True)), "the other upstream's devices must stay served")
    finally:
        await c.inject("good_digest", victim)
    deadline = time.monotonic() + 10
    now = before
    while now == before and time.monotonic() < deadline:
        await asyncio.sleep(0.3)
        now = await revision()
    c.expect(now != before, "the revised description must be served once the upstream's digest is right again")


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
        c.expect(response.ok and response.result["gap"] is True or response.code == "INVALID_ARGUMENT",
                 f"reading from a cursor of an earlier epoch is a gap (or INVALID_ARGUMENT): {response.describe()}")
