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
