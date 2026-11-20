"""Synthetic combined-runtime crash boundary driver; invoked only by tests."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hms.journal import Context
from hms.runtime import Runtime

runtime = Runtime(sys.argv[1], create=True, owner=Context("test-owner", "simulation:local"),
                  wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)
owner = Context("test-owner", "simulation:local")
namespace = runtime.request(owner, "namespace", {"expiresUnixMs": 10000})["token"]
request = runtime.request(owner, "prepare", {
    "instanceId": "sim:home-fan", "actionId": "set_level", "arguments": {"level": 41, "unit": "percent"},
    "operationKey": "crash-operation", "replayNamespace": namespace, "requiredEffect": "capability_completion",
    "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000, "maxRunMs": 500, "latestCompletionUnixMs": 5500},
})["request"]
operation = runtime.request(owner, "invoke", {"request": request})
phase = sys.argv[2]
if phase == "dispatch_claimed":
    runtime.journal.claim_dispatch(operation["operationId"])
elif phase in {"plant_pending", "plant_committed"}:
    runtime.tick()
    if phase == "plant_committed":
        runtime.plant.finish(operation["operationId"])
elif phase != "accepted":
    raise ValueError(phase)
print(json.dumps({"request": request, "operation": operation}), flush=True)
os._exit(73)
