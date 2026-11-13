"""Chapter 7: leases and fencing (profile ``leases``)."""

from __future__ import annotations

import asyncio

from bhms.conformance.context import Context
from bhms.conformance.core import check


def _min_ttl(c: Context) -> int:
    """The shortest lease the server grants (a lease that must expire during a check uses it)."""
    return int(c.caps["leases"].get("minTtlMs", 50))


async def _acquire(c: Context, resources: list[str], ttl: int, **kw: int) -> dict:
    return (await c.ok("leases/acquire", {"resources": resources, "ttlMs": ttl, **kw}))["lease"]


@check("leases.grant-renew-release", ["BHMS-LSE-002", "BHMS-LSE-003", "BHMS-LSE-006"], profile="leases")
async def grant_renew_release(c: Context) -> None:
    """Exclusive grant, strictly increasing fences, renew keeps the fence, released and expired leases are LEASE_EXPIRED."""
    axis = c.axis()
    clamp = f"{axis}/clamp"
    one = await _acquire(c, [clamp], 30_000)
    c.expect(one["state"] == "active" and one["fence"] >= 1 and one["resources"] == [clamp], f"lease {one}")
    conflict = await c.call("leases/acquire", {"resources": [clamp], "ttlMs": 30_000})
    data = c.refused(conflict, "LEASE_CONFLICT", what="an overlapping acquire")
    text = str(conflict.error)
    c.expect(clamp in text, f"LEASE_CONFLICT must name the resources: {text[:200]}")
    c.expect("expiresAt" in str(data) or "expir" in text.lower(), "LEASE_CONFLICT must give the expiry so a client knows when to retry")
    renewed = (await c.ok("leases/renew", {"leaseId": one["leaseId"], "ttlMs": 40_000}))["lease"]
    c.expect(renewed["fence"] == one["fence"], "renew must keep the fence")
    c.expect(renewed["expiresAt"] >= one["expiresAt"], "renew must not shorten the lease")
    await c.ok("leases/release", {"leaseId": one["leaseId"]})
    released = await c.call("leases/renew", {"leaseId": one["leaseId"], "ttlMs": 1000})
    c.refused(released, "LEASE_EXPIRED", what="renew of a released lease")
    fences = [one["fence"]]
    for _ in range(3):
        lease = await _acquire(c, [clamp], 30_000)
        fences.append(lease["fence"])
        await c.ok("leases/release", {"leaseId": lease["leaseId"]})
    c.expect(all(b > a for a, b in zip(fences, fences[1:])), f"fences must strictly increase: {fences}")
    short = await _acquire(c, [clamp], _min_ttl(c))
    await asyncio.sleep(_min_ttl(c) / 1000 * 2 + 0.2)
    c.refused(await c.call("leases/renew", {"leaseId": short["leaseId"], "ttlMs": 1000}), "LEASE_EXPIRED", what="renew of an expired lease")
    c.expect((await _acquire(c, [clamp], 30_000))["fence"] > fences[-1], "a lease acquired after expiry has a higher fence")


@check("leases.parameter-bounds", ["BHMS-LSE-004", "BHMS-LSE-007", "BHMS-LSE-001"], profile="leases")
async def parameter_bounds(c: Context) -> None:
    """ttlMs and waitMs outside the advertised range are OUT_OF_RANGE; unknown resources and leases are refused; a failed
    multi-resource acquire holds nothing."""
    axis = c.axis()
    limits = c.caps["leases"]
    clamp, motion = f"{axis}/clamp", f"{axis}/motion"
    low = await c.call("leases/acquire", {"resources": [clamp], "ttlMs": limits["minTtlMs"] - 1})
    c.refused(low, "OUT_OF_RANGE", field="ttlMs", what="ttlMs below minTtlMs")
    high = await c.call("leases/acquire", {"resources": [clamp], "ttlMs": limits["maxTtlMs"] + 1})
    c.refused(high, "OUT_OF_RANGE", field="ttlMs", what="ttlMs above maxTtlMs")
    wait = await c.call("leases/acquire", {"resources": [clamp], "ttlMs": 1000, "waitMs": limits["maxWaitMs"] + 1})
    c.refused(wait, "OUT_OF_RANGE", field="waitMs", what="waitMs above maxWaitMs")
    unknown = await c.call("leases/acquire", {"resources": [clamp, "no-such-device/resource"], "ttlMs": 1000})
    data = c.refused(unknown, "INVALID_ARGUMENT", what="an unknown resource")
    c.expect("resources[1]" in str(data.get("field", "")) or "no-such-device/resource" in str(unknown.error), "the refusal must name the unknown resource or its index")
    for method, params in (("leases/renew", {"leaseId": "lease-fabricated", "ttlMs": 1000}), ("leases/release", {"leaseId": "lease-fabricated"})):
        c.refused(await c.call(method, params), "LEASE_EXPIRED", what=f"{method} of a fabricated lease")
    held = await _acquire(c, [clamp], 30_000)
    try:
        both = await c.call("leases/acquire", {"resources": [motion, clamp], "ttlMs": 30_000})
        c.refused(both, "LEASE_CONFLICT", what="a two-resource acquire while one resource is held")
        alone = await _acquire(c, [motion], 30_000)
        await c.ok("leases/release", {"leaseId": alone["leaseId"]})
    finally:
        await c.ok("leases/release", {"leaseId": held["leaseId"]})
    again = await _acquire(c, [motion, clamp], 30_000)
    c.expect(sorted(again["resources"]) == sorted([motion, clamp]), "after a failed all-or-nothing acquire both resources are free")
    await c.ok("leases/release", {"leaseId": again["leaseId"]})


@check("leases.enforcement-at-admission", ["BHMS-LSE-010", "BHMS-LSE-007"], profile="leases")
async def enforcement(c: Context) -> None:
    """A lease-requiring action needs an active, covering lease: LEASE_REQUIRED, LEASE_EXPIRED, FENCED, LEASE_CONFLICT; the
    device is never reached by a refusal."""
    axis = c.axis()
    base = await c.counter(axis)
    clamp, motion = f"{axis}/clamp", f"{axis}/motion"
    c.refused(await c.invoke(axis, "clamp", {"force": 10}), "LEASE_REQUIRED", what="clamp without a lease")
    c.refused(await c.invoke(axis, "clamp", {"force": 10}, leaseId="lease-fabricated"), "LEASE_EXPIRED", what="clamp with an unknown lease")
    lease = await _acquire(c, [clamp], 30_000)
    done = await c.run(axis, "clamp", {"force": 10}, leaseId=lease["leaseId"])
    c.expect(done["state"] == "completed" and done.get("leaseId") == lease["leaseId"] and done.get("fence") == lease["fence"],
             f"an operation records the lease and fence it ran under: {done.get('leaseId')} {done.get('fence')}")
    wrong = await _acquire(c, [motion], 30_000)
    c.refused(await c.invoke(axis, "clamp", {"force": 10}, leaseId=wrong["leaseId"]), "LEASE_CONFLICT", what="clamp with a lease that does not cover its resource")
    await c.ok("leases/release", {"leaseId": wrong["leaseId"]})
    await c.ok("leases/release", {"leaseId": lease["leaseId"]})
    c.refused(await c.invoke(axis, "clamp", {"force": 10}, leaseId=lease["leaseId"]), "LEASE_EXPIRED", what="clamp with a released lease")
    short = await _acquire(c, [clamp], _min_ttl(c))
    await asyncio.sleep(_min_ttl(c) / 1000 * 2 + 0.2)
    c.refused(await c.invoke(axis, "clamp", {"force": 10}, leaseId=short["leaseId"]), "LEASE_EXPIRED", what="clamp with an expired lease")
    revoked = await _acquire(c, [clamp], 30_000)
    stop = (await c.ok("stop", {"reason": "conformance: revoke", "deviceIds": [axis]}))["stops"][0]
    c.expect(revoked["leaseId"] in stop["revokedLeases"], f"stop must revoke the device's active leases: {stop['revokedLeases']}")
    c.refused(await c.invoke(axis, "clamp", {"force": 10}, leaseId=revoked["leaseId"]), "FENCED", what="clamp with a lease revoked by stop")
    c.refused(await c.call("leases/renew", {"leaseId": revoked["leaseId"], "ttlMs": 1000}), "FENCED", what="renew of a revoked lease")
    c.expect(await c.counter(axis) == base + 1, "only the one valid clamp may have reached the device")


@check("leases.key-lookup-before-lease", ["BHMS-OPS-033"], profile="leases")
async def key_lookup_first(c: Context) -> None:
    """A same-key retry returns the original operation even after its lease has expired (the key lookup precedes the
    lease check), instead of LEASE_EXPIRED."""
    axis = c.axis()
    lease = await _acquire(c, [f"{axis}/clamp"], _min_ttl(c) * 4)
    key = c.unique("lease-replay")
    params = {"deviceId": axis, "action": "clamp", "arguments": {"force": 5}, "operationKey": key, "leaseId": lease["leaseId"], "waitMs": 3000}
    first = await c.ok("actions/invoke", params)
    await asyncio.sleep(_min_ttl(c) / 1000 * 4 + 0.3)
    again = await c.ok("actions/invoke", params)
    c.expect(again["replayed"] is True and again["operation"]["operationId"] == first["operation"]["operationId"],
             "a retry with an expired lease must still find the original operation by its key")


@check("transport.connection-close-keeps-state", ["BHMS-TRN-005"], profile="leases", needs=("persistent",))
async def close_keeps_state(c: Context) -> None:
    """Closing a connection cancels no operation and releases no lease."""
    axis = c.axis()
    async with c.fresh_wire() as wire:
        lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 60_000}, wire=wire))["lease"]
        op = (await c.ok("actions/invoke", {"deviceId": axis, "action": "slow_move", "arguments": {"duration_ms": 500}}, wire=wire))["operation"]
    await asyncio.sleep(0.1)
    c.expect((await c.get_op(op["operationId"]))["state"] in ("dispatching", "running", "completed"), "closing the connection cancelled the operation")
    final = await c.settle(op["operationId"])
    c.expect(final["state"] == "completed", f"the operation must keep running after its connection closed, ended {final['state']}")
    renewed = (await c.ok("leases/renew", {"leaseId": lease["leaseId"], "ttlMs": 60_000}))["lease"]
    c.expect(renewed["state"] == "active", "closing the connection released the lease")
    await c.ok("leases/release", {"leaseId": lease["leaseId"]})
