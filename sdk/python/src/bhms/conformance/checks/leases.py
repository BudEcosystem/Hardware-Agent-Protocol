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


@check("leases.held-lease-blocks-everyone", ["BHMS-LSE-014", "BHMS-LSE-007", "BHMS-LSE-010"], profile="leases")
async def held_lease_blocks(c: Context) -> None:
    """While a resource is leased, an action on it that does not declare requiresLease is refused without that lease
    (LEASE_CONFLICT naming the resource, not the holder); a lease supplied with such an action is validated (fabricated:
    LEASE_EXPIRED, not covering: LEASE_CONFLICT); the device is never reached; with the lease the action runs."""
    axis = c.axis()
    clamp, motion = f"{axis}/clamp", f"{axis}/motion"
    spec = (await c.describe(axis))["actions"]["pulse"]
    c.expect(not spec.get("requiresLease") and motion in spec.get("resources", []), "pulse must use axis motion without requiring a lease")
    c.refused(await c.invoke(axis, "pulse", {"count": 1}, leaseId="lease-fabricated"), "LEASE_EXPIRED",
              what="pulse with a fabricated lease while nothing is leased")
    lease = await _acquire(c, [motion], 30_000)
    other = await _acquire(c, [clamp], 30_000)
    try:
        base = await c.counter(axis)
        bare = await c.invoke(axis, "pulse", {"count": 1})
        data = c.refused(bare, "LEASE_CONFLICT", field="leaseId", what="pulse without the lease held on its resource")
        c.expect(data.get("bound") == [motion], f"the refusal must list the leased resources in bound: {data.get('bound')}")
        c.expect(lease["leaseId"] not in str(bare.error), "the refusal must not disclose the lease that holds the resource")
        c.expect(data.get("mayHaveActed") is False, "a lease refusal must say that nothing acted")
        c.refused(await c.invoke(axis, "pulse", {"count": 1}, leaseId="lease-fabricated"), "LEASE_EXPIRED", what="pulse with a fabricated lease")
        c.refused(await c.invoke(axis, "pulse", {"count": 1}, leaseId=other["leaseId"]), "LEASE_CONFLICT",
                  what="pulse with a lease on another resource")
        c.expect(await c.counter(axis) == base, "a refused action reached the device")
        done = await c.run(axis, "pulse", {"count": 1}, leaseId=lease["leaseId"])
        c.expect(done["state"] == "completed" and done.get("leaseId") == lease["leaseId"] and done.get("fence") == lease["fence"],
                 f"with the lease the action runs and records it: {done['state']} {done.get('leaseId')}")
        c.expect(await c.counter(axis) == base + 1, "exactly the one admitted pulse may have reached the device")
    finally:
        await c.ok("leases/release", {"leaseId": lease["leaseId"]})
        await c.ok("leases/release", {"leaseId": other["leaseId"]})
    free = await c.run(axis, "pulse", {"count": 1})
    c.expect(free["state"] == "completed", f"after the lease ended the action runs without one: {free['state']}")


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


@check("leases.loss-behaviour", ["BHMS-LSE-012"], profile="leases", needs=("faults",), timeout=90)
async def loss_behaviour(c: Context) -> None:
    """Losing the lease of a running operation applies its onLeaseLoss: cancel ends it canceled, finish lets it complete,
    hold commands the device to hold and ends it failed with LEASE_EXPIRED; nothing new starts under the lost lease."""
    import asyncio

    axis = c.axis()
    resource = f"{axis}/motion"
    ttl = max(_min_ttl(c), 300)
    holds_before = (await c.counters(axis)).get("holds", 0)
    outcomes = {}
    for mode, duration in (("cancel", ttl + 6000), ("finish", ttl + 700), ("hold", ttl + 6000)):
        lease = await _acquire(c, [resource], ttl)
        op = await c.invoke_op(axis, f"guard_{mode}", {"duration_ms": duration}, leaseId=lease["leaseId"])
        c.expect(op["state"] in ("dispatching", "running"), f"guard_{mode} should start at once, is {op['state']}")
        outcomes[mode] = await c.settle(op["operationId"], 15)
        await asyncio.sleep(0.3)  # the lease is certainly lost by now, whichever side's clock ran out first
        again = await c.invoke(axis, f"guard_{mode}", {"duration_ms": 10}, leaseId=lease["leaseId"])
        c.refused(again, "LEASE_EXPIRED", what=f"a new guard_{mode} under the lost lease")
    c.expect(outcomes["cancel"]["state"] == "canceled", f"onLeaseLoss cancel: the operation ended {outcomes['cancel']['state']}")
    c.expect(outcomes["finish"]["state"] == "completed", f"onLeaseLoss finish: the operation ended {outcomes['finish']['state']}")
    err = outcomes["hold"].get("error") or {}
    c.expect(outcomes["hold"]["state"] == "failed" and err.get("bhmsCode") == "LEASE_EXPIRED",
             f"onLeaseLoss hold: the operation ended {outcomes['hold']['state']} {err}")
    await asyncio.sleep(0.05)
    c.expect((await c.counters(axis)).get("holds", 0) == holds_before + 1, "onLeaseLoss hold must command the device to hold exactly once")
