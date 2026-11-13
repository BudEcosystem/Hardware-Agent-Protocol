"""Chapter 5: observations, freshness, evidence, retained samples after effects, subscriptions."""

from __future__ import annotations

import asyncio
import time

from bhms.conformance.context import Context
from bhms.conformance.core import check


@check("observations.read-semantics", ["BHMS-OBS-012", "BHMS-OBS-004", "BHMS-OBS-005", "BHMS-OBS-010"])
async def read_semantics(c: Context) -> None:
    """Unknown property lists the names; sequences increase in an epoch; maxAgeMs unmet is STALE naming it."""
    axis = c.axis()
    response = await c.read(axis, "no_such_property")
    data = c.refused(response, "INVALID_ARGUMENT", field="property", what="read of an unknown property")
    c.expect("position" in data.get("hint", "") and "temperature" in data.get("hint", ""), f"the hint must list the device's property names: {data.get('hint')!r}")
    first = c.result(await c.read(axis, "position", fresh=True))["observation"]
    second = c.result(await c.read(axis, "position", fresh=True))["observation"]
    c.expect(first["epoch"] == second["epoch"] and second["sequence"] > first["sequence"],
             f"sequence must increase with every acquisition within an epoch: {first['sequence']} -> {second['sequence']}")
    c.expect(first["unit"] == "mm" and first["quality"] == "valid" and first["evidence"] == "measured", f"observation fields: {first}")
    c.expect(first["ageMs"] >= 0 and first["acquiredAt"] and first["receivedAt"], "an observation carries ageMs, acquiredAt and receivedAt")
    relaxed = c.result(await c.read(axis, "position", maxAgeMs=60_000))["observation"]
    c.expect(relaxed["ageMs"] <= 60_000, "maxAgeMs must be honoured")
    strict = await c.read(axis, "position", maxAgeMs=0)
    if not strict.ok:
        data = c.refused(strict, "STALE", field="maxAgeMs", what="maxAgeMs 0")
        c.expect(data.get("bound") == 0, f"STALE bound must be the requested maxAgeMs 0, is {data.get('bound')!r}")


@check("observations.stale-and-invalid-sensors", ["BHMS-OBS-001", "BHMS-OBS-003", "BHMS-OBS-010"], needs=("faults",))
async def stale_and_invalid(c: Context) -> None:
    """A failed measurement is quality invalid with value null; a slow acquisition ages the sample conservatively and
    fails maxAgeMs with STALE naming the parameter."""
    axis = c.axis()
    await c.inject("sensor_invalid")
    bad = c.result(await c.read(axis, "position", fresh=True))["observation"]
    c.expect(bad["quality"] in ("invalid", "unknown") and bad["value"] is None, f"a failed measurement must be invalid with value null, was {bad}")
    await c.inject("sensor_valid")
    good = c.result(await c.read(axis, "position", fresh=True))["observation"]
    c.expect(good["quality"] == "valid" and good["value"] is not None, "the sensor recovered but the read is not valid")
    await c.inject("sensor_stale")
    slow = c.result(await c.read(axis, "temperature", fresh=True))["observation"]
    c.expect(slow["quality"] == "stale" and slow["ageMs"] >= 10_000, f"a sample that took 10 s to acquire must be stale and at least 10000 ms old: {slow['quality']} {slow['ageMs']}")
    response = await c.read(axis, "temperature", maxAgeMs=5000)
    data = c.refused(response, "STALE", field="maxAgeMs", what="maxAgeMs below the achievable age")
    c.expect(data.get("bound") == 5000, f"STALE bound should be 5000, is {data.get('bound')!r}")


@check("observations.retained-after-effect", ["BHMS-OBS-006", "BHMS-OBS-011"])
async def retained_after_effect(c: Context) -> None:
    """A settled effect forgets retained samples of on-demand properties but never the sample of a transaction property."""
    axis = c.axis()
    before = c.result(await c.read(axis, "position", fresh=True))["observation"]
    op = await c.run(axis, "move_to", {"position": 77.5})
    c.expect(op["state"] == "completed", "move_to failed")
    after = c.result(await c.read(axis, "position"))["observation"]
    c.expect(after["value"] == 77.5, f"a plain read after a move must not return the pre-move sample: {after['value']} (before {before['value']})",
             ("BHMS-OBS-006",))
    c.expect(after["sequence"] > before["sequence"], "the post-move reading must be a new acquisition (higher sequence)", ("BHMS-OBS-006",))
    # the transaction property
    refused = await c.read(axis, "fifo", fresh=True)
    c.refused(refused, "LEASE_REQUIRED", what="fresh read of a transaction property without a lease", ids=("BHMS-OBS-011",))
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/motion"], "ttlMs": 30_000}))["lease"]
    try:
        popped = c.result(await c.read(axis, "fifo", fresh=True))["observation"]
        again = c.result(await c.read(axis, "fifo", fresh=True))["observation"]
        c.expect(again["value"] == popped["value"] + 1, "each fresh acquisition of the FIFO pops one value")
    finally:
        await c.ok("leases/release", {"leaseId": lease["leaseId"]})
    retained = c.result(await c.read(axis, "fifo"), "retained read of a transaction property without a lease", ("BHMS-OBS-011",))["observation"]
    c.expect(retained["value"] == again["value"] and retained["sequence"] == again["sequence"],
             "a plain read of a transaction property needs only read authority and returns the retained sample", ("BHMS-OBS-011",))
    await c.run(axis, "pulse", {"count": 1})
    still = c.result(await c.read(axis, "fifo"), "retained read after an effect", ("BHMS-OBS-006",))["observation"]
    c.expect(still["sequence"] == retained["sequence"] and still["value"] == retained["value"],
             "an effect settling on the device must not forget (or re-acquire) the retained sample of a transaction property (BHMS-OBS-006)",
             ("BHMS-OBS-006",))


@check("observations.subscription-delivery", ["BHMS-OBS-021", "BHMS-OBS-022", "BHMS-LIF-043"], needs=("faults",), timeout=40)
async def subscription_delivery(c: Context) -> None:
    """Notifications follow acquisitions within the rate floor, deliver quality changes at once, never start
    transactions on their own."""
    axis = c.axis()
    stream, ack = await c.wire.listen({"observations": [{"deviceId": axis, "property": "position", "minIntervalMs": 100},
                                                        {"deviceId": axis, "property": "fifo"}]})
    refused = ack["params"].get("refused") or []
    c.expect(not refused, f"observable properties must not be refused: {refused}")
    stream.drain()
    started = time.monotonic()
    while time.monotonic() - started < 1.0:
        await c.read(axis, "position", fresh=True)
        await asyncio.sleep(0.01)
    items = [n for n in stream.drain() if n["method"] == "notifications/observation" and n["params"]["property"] == "position"]
    ceiling = int(1.0 / (max(100, c.caps.get("observations", {}).get("minIntervalMs", 0)) / 1000)) + 3
    c.expect(1 <= len(items) <= ceiling, f"{len(items)} position notifications in 1 s at minIntervalMs 100 (expected 1..{ceiling})")
    await c.inject("sensor_invalid")
    await c.read(axis, "position", fresh=True)
    seen = await stream.until(lambda n: n["method"] == "notifications/observation" and n["params"]["observation"]["quality"] == "invalid", 2.0)
    c.expect(seen is not None, "a quality change valid -> invalid must be delivered even inside the rate floor")
    await c.inject("sensor_valid")
    await stream.cancel()
    # a subscription alone must not pop the FIFO
    lease = (await c.ok("leases/acquire", {"resources": [f"{axis}/motion"], "ttlMs": 30_000}))["lease"]
    try:
        one = c.result(await c.read(axis, "fifo", fresh=True))["observation"]["value"]
        await asyncio.sleep(0.4)
        two = c.result(await c.read(axis, "fifo", fresh=True))["observation"]["value"]
        c.expect(two == one + 1, f"the FIFO was popped by something other than reads: {one} -> {two}")
    finally:
        await c.ok("leases/release", {"leaseId": lease["leaseId"]})


@check("observations.required-fresh", ["BHMS-OBS-030"], needs=("faults",))
async def required_fresh(c: Context) -> None:
    """requiresFresh: STALE naming requiresFresh[0] with the property and age bound, before any dispatch."""
    pump = c.pump()
    resource = (await c.describe(pump))["actions"]["dispense"]["resources"][0]
    lease = (await c.ok("leases/acquire", {"resources": [resource], "ttlMs": 30_000}))["lease"]
    base = await c.counter(c.axis())
    try:
        ok = await c.run(pump, "dispense", {"volume": 5.0}, leaseId=lease["leaseId"])
        c.expect(ok["state"] == "completed", f"dispense with a fresh valid pressure: {ok['state']} {ok.get('error')}")
        for fault in ("sensor_stale", "sensor_invalid"):
            await c.inject(fault)
            response = await c.invoke(pump, "dispense", {"volume": 5.0}, leaseId=lease["leaseId"])
            data = c.refused(response, "STALE", field="requiresFresh[0]", what=f"dispense with {fault}")
            c.expect(isinstance(data.get("bound"), dict) and data["bound"].get("property") == "pressure" and data["bound"].get("maxAgeMs") == 1000,
                     f"STALE bound must be {{property: pressure, maxAgeMs: 1000}}, is {data.get('bound')!r}")
            c.expect("pressure" in data.get("hint", ""), "the hint must name the property")
            await c.inject("none")
    finally:
        await c.ok("leases/release", {"leaseId": lease["leaseId"]})
    c.expect(await c.counter(c.axis()) == base + 1, "only the one valid dispense may have reached the device")
