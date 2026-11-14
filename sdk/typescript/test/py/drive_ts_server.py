"""Drive a TypeScript BHMS device server with the Python reference client (strict: every message is schema-validated).

Usage: python3 drive_ts_server.py <target> -- prints one JSON line {"ok": true, "checks": [...]} or exits non-zero with a
traceback. ``<target>`` is any Client.connect target, e.g. ``stdio:node dist/src/testing/conformanceDevice.js --memory``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from bhms.client import Client
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError

checks: list[str] = []


def check(condition: bool, what: str) -> None:
    if not condition:
        raise AssertionError(what)
    checks.append(what)


async def expect_error(coro, code: str, what: str) -> BhmsError:
    try:
        await coro
    except BhmsError as exc:
        check(exc.bhms_code == code, f"{what}: {exc.bhms_code} (wanted {code})")
        return exc
    raise AssertionError(f"{what}: no error raised")


async def main(target: str) -> None:
    async with await Client.connect(target, strict=True, timeout=20.0) as client:
        server = client.server
        check(server.server_info.name == "conformance-device", "serverInfo.name")
        check(server.capabilities.leases is not None and server.capabilities.events is not None, "capabilities")

        listing = await client.devices_list()
        check([d.device_id for d in listing.devices] == ["axis-1", "pump-1"], "devices/list order")
        described = await client.devices_describe("axis-1")
        wire = described.description.model_dump(by_alias=True, exclude_none=True, mode="json")
        stated = wire.pop("digest")
        check(stated == digest(wire), "the TypeScript description digest verifies with the Python canonicalizer")
        await expect_error(client.devices_describe("axis-1", digest="sha256:" + "0" * 64), "STALE", "describe pin")

        key = f"py-{time.time_ns()}"
        first = await client.actions_invoke("axis-1", "move_to", {"position": 12.5}, operation_key=key, wait_ms=2000)
        check(first.operation.state == "completed" and first.operation.effect == "verified", "move_to verified")
        again = await client.actions_invoke("axis-1", "move_to", {"position": 12.5}, operation_key=key)
        check(again.replayed and again.operation.operation_id == first.operation.operation_id, "replay on the same key")
        err = await expect_error(client.actions_invoke("axis-1", "move_to", {"position": 13}, operation_key=key),
                                 "KEY_CONFLICT", "key conflict")
        check(err.operation_id == first.operation.operation_id, "KEY_CONFLICT carries operationId")
        err = await expect_error(client.actions_invoke("axis-1", "move_to", {"position": 999}), "OUT_OF_RANGE", "range")
        check(err.field == "arguments.position" and err.bound == {"maximum": 200}, "OUT_OF_RANGE field and bound")
        await expect_error(client.actions_invoke("axis-1", "move_to", {"position": {"value": 1, "unit": "m"}}),
                           "UNIT_MISMATCH", "unit mismatch")
        await expect_error(client.actions_invoke("axis-1", "clamp", {"force": 5}), "LEASE_REQUIRED", "lease required")

        lease = (await client.leases_acquire(["axis-1/clamp"], 5000)).lease
        clamp = await client.actions_invoke("axis-1", "clamp", {"force": 5}, lease_id=lease.lease_id, wait_ms=2000)
        check(clamp.operation.state == "completed" and clamp.operation.fence == lease.fence, "clamp under a lease")
        check((await client.leases_release(lease.lease_id)).lease.state == "released", "lease released")

        obs = (await client.properties_read("pump-1", "pressure")).observation
        check(obs.quality == "valid" and obs.unit == "kPa", "properties/read")

        async with await client.subscribe(operations={"all": True}) as sub:
            op = await client.actions_invoke("axis-1", "pulse", {"count": 3}, operation_key=f"{key}-pulse", wait_ms=2000)
            seen = []
            async for note in sub:
                seen.append(note.method)
                if note.method == "notifications/operation" and note.params.operation.operation_id == \
                        op.operation.operation_id and note.params.operation.state == "completed":
                    break
            check("notifications/operation" in seen, "operation notification delivered")

        program = {"bhmsProgram": "2026-11-13", "name": "py_scan", "description": "pulse twice and read the counter",
                   "input": {"type": "object", "additionalProperties": False, "required": ["n"],
                             "properties": {"n": {"type": "integer", "x-bhms-unit": "1", "minimum": 1, "maximum": 3}}},
                   "maxDurationMs": 60000,
                   "steps": [{"kind": "repeat", "times": "${n}", "as": "i", "steps": [
                       {"kind": "invoke", "deviceId": "axis-1", "action": "pulse", "arguments": {"count": 1}, "saveAs": "p"}]},
                       {"kind": "read", "deviceId": "axis-1", "property": "counter", "fresh": True, "saveAs": "c"}],
                   "output": {"pulses": "${p.pulses}", "counter": "${c.value}"}}
        info = (await client.programs_register(program)).info
        check(info.digest == digest(program) and info.max_executed_steps == 4, "programs/register digest and limits")
        ran = await client.programs_run(digest=info.digest, arguments={"n": 2}, operation_key=f"{key}-prog", wait_ms=5000)
        done = ran.operation
        check(done.state == "completed" and done.program_digest == info.digest, f"program completed ({done.state})")
        check(done.result["pulses"] >= 2 and done.progress.steps_completed == 3, "program output and progress")
        kids = (await client.operations_list(parent_operation_id=done.operation_id)).operations
        check(len(kids) == 2 and all(k.key_origin == "derived" for k in kids), "derived-key child operations")

        slow = await client.actions_invoke("axis-1", "slow_move", {"duration_ms": 5000}, operation_key=f"{key}-slow")
        await asyncio.sleep(0.05)
        await client.operations_cancel(slow.operation.operation_id, reason="py test")
        done = (await client.operations_wait(slow.operation.operation_id, 2000)).operation
        check(done.state == "canceled", "cancel of a running operation")

        stop = await client.stop("py test stop", device_ids=["axis-1", "ghost"])
        outcomes = {s.device_id: s.outcome for s in stop.stops}
        check(outcomes == {"axis-1": "confirmed", "ghost": "failed"}, f"stop outcomes {outcomes}")

        events = await client.events_read(types=["stop"])
        check(len(events.events) >= 1 and not events.gap, "events/read")
        counters = await client.request("x-conformance/counters")
        check(counters["counter"] >= 3, "device counters over the extension")
        refused = await client.subscribe(observations=[{"deviceId": "ghost", "property": "x"}])
        check(refused.acknowledged.refused and refused.acknowledged.refused[0].bhms_code == "UNKNOWN_DEVICE",
              "refused subscription part")
        await refused.cancel()
    print(json.dumps({"ok": True, "checks": checks}))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
