"""Chapter 9: the event log and event subscriptions (profile ``events``)."""

from __future__ import annotations

import asyncio

from bhms.conformance.context import Context
from bhms.conformance.core import check


async def _all_events(c: Context, **filters: object) -> list[dict]:
    out, after = [], None
    for _ in range(200):
        page = await c.ok("events/read", {"limit": 50, **filters, **({"after": after} if after else {})})
        out.extend(page["events"])
        if not page["events"] or page["cursor"] == after:
            break
        after = page["cursor"]
    return out


@check("events.read-order-and-stability", ["BHMS-EVT-001", "BHMS-EVT-010", "BHMS-EVT-012"], profile="events")
async def read_order(c: Context) -> None:
    """Events come in cursor order, strictly after `after`, identical when read twice; early events are retained."""
    first = await _all_events(c)
    second = await _all_events(c)
    c.expect(first == second[: len(first)], "the same range read twice must have identical cursors and content")
    cursors = [e["cursor"] for e in first]
    c.expect(len(cursors) == len(set(cursors)), "event cursors must be unique")
    if len(first) >= 3:
        middle = first[len(first) // 2]
        later = (await c.ok("events/read", {"after": middle["cursor"], "limit": 500}))["events"]
        c.expect(later and later[0]["cursor"] == first[len(first) // 2 + 1]["cursor"], "events after a cursor must start strictly after it")
        c.expect(middle["cursor"] not in [e["cursor"] for e in later], "events/read returned the `after` event itself")
        c.expect([e["cursor"] for e in later] == cursors[len(first) // 2 + 1: len(first) // 2 + 1 + len(later)], "events/read must keep cursor order")
    retention = c.caps["events"].get("retentionS", 0)
    c.expect(retention >= 1, "capabilities.events.retentionS must be advertised")
    c.expect(not (await c.ok("events/read", {"after": cursors[0], "limit": 1}))["gap"] if cursors else True, "an event inside retention must not be a gap")


@check("events.recorded-types", ["BHMS-EVT-002"], profile="events", needs=("faults",))
async def recorded_types(c: Context) -> None:
    """stop, lease.revoked, device.epoch and operation.state transitions into unknown are recorded as events."""
    axis = c.axis()
    log = await _all_events(c)
    c.expect(any(e["type"] == "device.epoch" for e in log), "the log must contain a device.epoch event for the server start")
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/clamp"], "ttlMs": 30_000}))["lease"]
    await c.inject("crash_next")
    op = await c.run(axis, "pulse", {"count": 1})
    c.expect(op["state"] == "unknown", f"expected an unknown operation, got {op['state']}")
    await c.ok("stop", {"reason": "conformance events", "deviceIds": [axis]})
    types = {}
    for event in await _all_events(c):
        types.setdefault(event["type"], []).append(event)
    for needed in ("stop", "lease.revoked", "operation.state"):
        c.expect(needed in types, f"no {needed} event recorded; types seen: {sorted(types)}")
    unknown = [e for e in types["operation.state"] if e.get("operationId") == op["operationId"] and e.get("data", {}).get("state") == "unknown"]
    c.expect(unknown, "the transition into unknown must be recorded as an operation.state event")
    c.expect(any(e.get("data", {}).get("leaseId") == lease["leaseId"] or lease["leaseId"] in str(e) for e in types["lease.revoked"]),
             "the lease.revoked event must identify the lease")


@check("events.listen-replay-then-live", ["BHMS-EVT-020", "BHMS-LIF-041"], profile="events")
async def listen_seam(c: Context) -> None:
    """events.after replays retained events then goes live with no duplicate and no omission."""
    axis = c.axis()
    cursor = (await c.ok("events/read", {"limit": 1}))["cursor"]
    for _ in range(3):
        await c.ok("stop", {"reason": "conformance seam", "deviceIds": [axis]})
    stream, ack = await c.wire.listen({"events": {"after": cursor, "deviceIds": [axis]}})
    c.expect(ack["method"] == "notifications/subscriptions/acknowledged", "the first message must be the acknowledgement")

    async def produce() -> None:
        for _ in range(5):
            await c.ok("stop", {"reason": "conformance seam live", "deviceIds": [axis]})
            await asyncio.sleep(0.02)

    producer = asyncio.ensure_future(produce())
    await producer
    await asyncio.sleep(0.4)
    got = [n["params"]["event"]["cursor"] for n in stream.drain() if n["method"] == "notifications/event"]
    await stream.cancel()
    c.expect(len(got) == len(set(got)), f"events were delivered twice: {got}")
    after_cursor = (await c.ok("events/read", {"after": cursor, "deviceId": axis, "limit": 500}))["events"]
    c.expect(got == [e["cursor"] for e in after_cursor], f"replay + live must equal events/read after the cursor: delivered {len(got)}, log {len(after_cursor)}")


@check("events.no-notification-without-listen", ["BHMS-LIF-045"], profile="events")
async def no_state_without_listen(c: Context) -> None:
    """Subscription state does not outlive its listen request: after cancelling, nothing is delivered."""
    axis = c.axis()
    stream, _ = await c.wire.listen({"events": {}})
    await stream.cancel()
    await asyncio.sleep(0.2)
    await c.wire.settle(0.05)
    await c.ok("stop", {"reason": "conformance quiet", "deviceIds": [axis]})
    stray = await c.wire.settle(0.4)
    c.expect(not stray and stream.queue.empty(), f"notifications arrived without an open subscription: {stray!r}")
