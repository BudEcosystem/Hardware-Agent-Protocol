"""Stop (chapter 7.5, BHMS-AUTH-02x): the one request that never waits behind anything."""

from __future__ import annotations

import time

from bhms.conformance.context import Context
from bhms.conformance.core import check


@check("stop.semantics", ["BHMS-AUTH-020", "BHMS-AUTH-021", "BHMS-AUTH-023", "BHMS-AUTH-024", "BHMS-AUTH-022"])
async def stop_semantics(c: Context) -> None:
    """Stop cancels queued work, requests cancellation of running work, revokes leases, reports per device (unknown
    devices fail alone), returns promptly and never claims confirmation without evidence."""
    axis, pump = c.axis(), c.pump()
    has_leases = "leases" in c.caps
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 60_000}))["lease"] if has_leases else None
    running = await c.invoke_op(axis, "slow_move", {"duration_ms": 5000})
    queued = [await c.invoke_op(axis, "move_to", {"position": 10 + i}) for i in range(3)]
    c.expect(all(q["state"] == "accepted" for q in queued), "the operations behind the busy resource must be queued")
    started = time.monotonic()
    result = await c.ok("stop", {"reason": "conformance stop", "deviceIds": [axis, "no_such_device", pump]})
    elapsed = time.monotonic() - started
    c.expect(elapsed < 2.0, f"stop with waitMs 0 must return promptly, took {elapsed:.2f}s")
    by_device = {s["deviceId"]: s for s in result["stops"]}
    c.expect(set(by_device) == {axis, "no_such_device", pump}, f"one result per requested device: {sorted(by_device)}")
    bad = by_device["no_such_device"]
    c.expect(bad["outcome"] == "failed" and (bad.get("error") or {}).get("bhmsCode") == "UNKNOWN_DEVICE", f"unknown device: {bad}")
    stopped = by_device[axis]
    c.expect(stopped["outcome"] in ("confirmed", "initiated"), f"axis-1 has a stop procedure, outcome {stopped['outcome']}")
    handled = set(stopped["canceledOperations"]) | set(stopped.get("cancelRequestedOperations", []))
    c.expect({q["operationId"] for q in queued} <= handled, f"queued operations must be canceled by stop: {sorted(handled)}")
    c.expect(sorted(stopped["canceledOperations"]) == sorted(q["operationId"] for q in queued),
             f"operations that never dispatched are canceled, not merely asked to cancel: {stopped['canceledOperations']}")
    c.expect(running["operationId"] in handled, "the running operation must have cancellation requested by stop")
    if lease:
        c.expect(lease["leaseId"] in stopped["revokedLeases"], "stop must revoke active leases on the device")
    c.expect(by_device[pump]["outcome"] != "confirmed", f"pump-1 has no stop procedure; outcome must not be confirmed: {by_device[pump]['outcome']}")
    final = await c.settle(running["operationId"], 5)
    c.expect(final["state"] == "canceled", f"the running operation ended {final['state']}")
    for q in queued:
        got = await c.settle(q["operationId"], 5)
        c.expect(got["state"] == "canceled" and got["effect"] == "none", f"queued operation after stop: {got['state']}/{got['effect']}")
        c.expect(any(h.get("kind") == "stop" for h in got["history"]), "a stop must leave a history entry on the operations it touched")
    everything = await c.ok("stop", {"reason": "conformance stop all", "scope": "all"})
    c.expect({s["deviceId"] for s in everything["stops"]} >= {axis, pump}, "scope all must cover every device")
    waited = await c.ok("stop", {"reason": "conformance stop wait", "deviceIds": [axis], "waitMs": 500})
    c.expect(waited["stops"][0]["outcome"] in ("confirmed", "initiated"), f"stop with waitMs: {waited['stops'][0]['outcome']}")


@check("stop.closed-parameters", ["BHMS-AUTH-026", "BHMS-LIF-015"], generic=True)
async def stop_parameters(c: Context) -> None:
    """Stop accepts only reason, deviceIds or scope, waitMs: motion parameters are refused (aimed at a device that does not exist)."""
    target = "no_such_device"  # a lax server that ignores an extra member still has nothing to stop
    for extra in ({"position": 5}, {"setpoint": 1}, {"action": "move_to"}, {"arguments": {"position": 1}}):
        response = await c.call("stop", {"reason": "closed", "deviceIds": [target], **extra})
        c.refused(response, "INVALID_ARGUMENT", what=f"stop with {extra}")
    # no case without a target or with scope "all": a server that ignored the defect could stop every device
    c.refused(await c.call("stop", {"deviceIds": [target]}), "INVALID_ARGUMENT", what="stop without a reason")


@check("stop.not-blocked-by-load", ["BHMS-AUTH-020"])
async def stop_under_load(c: Context) -> None:
    """With a saturated queue and every resource leased, stop is still dispatched within its budget."""
    axis, pump = c.axis(), c.pump()
    leases = []
    if "leases" in c.caps:
        for resource in (f"{axis}/clamp", f"{axis}/motion"):
            leases.append((await c.ok("leases/acquire", {"resources": [resource], "ttlMs": 60_000}))["lease"])
    await c.invoke_op(axis, "slow_move", {"duration_ms": 8000})
    for i in range(20):
        await c.invoke_op(axis, "move_to", {"position": 20 + i})
    started = time.monotonic()
    result = await c.ok("stop", {"reason": "conformance load", "deviceIds": [axis, pump]})
    c.expect(time.monotonic() - started < 2.0, "stop was delayed by queued work or held leases")
    stopped = result["stops"][0]
    handled = set(stopped["canceledOperations"]) | set(stopped.get("cancelRequestedOperations", []))
    c.expect(stopped["outcome"] in ("confirmed", "initiated") and len(handled) >= 20, f"stop under load: {stopped['outcome']}, handled {len(handled)} operations")
    for lease in leases:
        c.expect(lease["leaseId"] in stopped["revokedLeases"], "the held lease must be revoked by stop")


@check("stop.target-validation", ["BHMS-AUTH-026", "BHMS-LIF-015"])
async def stop_target_validation(c: Context) -> None:
    """Device-specific (these two requests would stop real devices on a server that ignored the defect): stop needs exactly one
    target, and a reason."""
    axis = c.axis()
    c.refused(await c.call("stop", {"reason": "closed"}), "INVALID_ARGUMENT", what="stop without a target")
    c.refused(await c.call("stop", {"reason": "closed", "deviceIds": [axis], "scope": "all"}), "INVALID_ARGUMENT", what="stop with two targets")
    c.refused(await c.call("stop", {"deviceIds": [axis]}), "INVALID_ARGUMENT", what="stop without a reason")
