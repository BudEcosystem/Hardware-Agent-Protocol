#!/usr/bin/env python3
"""Measure original local simulation reads; no physical hardware or model load."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hms.client import Client
from hms.ipc import Server
from hms.journal import Context
from hms.runtime import Runtime


def summarize(samples):
    ordered = sorted(samples)
    percentile = lambda p: ordered[max(0, math.ceil(p * len(ordered)) - 1)]
    return {"samplesMs": samples, "count": len(samples), "p50Ms": percentile(.5),
            "p95Ms": percentile(.95), "p99Ms": percentile(.99), "maxMs": max(samples)}


def main():
    inputs = [*sorted(ROOT.glob("hms/**/*.py")), *sorted(ROOT.glob("schemas/*.json")), Path(__file__).resolve()]
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    results = {}
    with tempfile.TemporaryDirectory(prefix="hms-local-benchmark-") as directory:
        directory = Path(directory)
        runtime = Runtime(directory / "state", create=True, owner=Context(f"posix:{os.getuid()}", "simulation:local"))
        server = Server(runtime, directory / "control.sock")
        thread = threading.Thread(target=server.serve_forever)
        runtime.start()
        thread.start()
        client = Client(directory / "control.sock")
        cases = {"discover": {"limit": 20}, "describe": {"instanceId": "sim:home-fan"},
                 "observe": {"instanceId": "sim:home-fan", "property": "value", "maxAgeMs": 1000, "evidenceKind": "simulation"}}
        try:
            for method, params in cases.items():
                for _ in range(3):
                    client.request(method, params)
                samples = []
                for _ in range(20):
                    before = time.perf_counter_ns()
                    client.request(method, params)
                    samples.append((time.perf_counter_ns() - before) / 1_000_000)
                results["warmCheckedClient:" + method] = summarize(samples)
            samples = []
            for _ in range(5):
                before = time.perf_counter_ns()
                completed = subprocess.run([sys.executable, "-m", "hms", "--socket", str(directory / "control.sock"), "discover"],
                                           cwd=ROOT, capture_output=True, text=True, timeout=15, check=True)
                samples.append((time.perf_counter_ns() - before) / 1_000_000)
                if len(json.loads(completed.stdout)["items"]) != 3:
                    raise RuntimeError("unexpected discovery result")
            results["coldCli:discover"] = summarize(samples)
            if runtime.last_worker_error is not None:
                raise RuntimeError("simulation worker failed during measurement")
            for instance in ("sim:home-fan", "sim:microscope", "sim:inspection-cell"):
                if runtime.plant.observe(instance)["effectCount"] != 0:
                    raise RuntimeError("read benchmark unexpectedly changed synthetic plant")
        finally:
            server.close()
            thread.join()
            runtime.close()
    if hashes != {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}:
        raise RuntimeError("benchmark inputs changed during measurement")
    cpu_info = Path("/proc/cpuinfo").read_text() if Path("/proc/cpuinfo").exists() else ""
    model = next((line.split(":", 1)[1].strip() for line in cpu_info.splitlines() if line.startswith("model name")), "unreported")
    artifact = {"createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "One client, three synthetic instances, same-host Linux UDS, original read-only control path",
        "method": "perf_counter_ns elapsed around complete checked request; nearest-rank percentiles; three warmups per warm method",
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "cpuModel": model,
                        "logicalCpuCount": os.cpu_count(), "clock": vars(time.get_clock_info("perf_counter"))},
        "results": results, "files": [{"path": key, "sha256": value} for key, value in hashes.items()],
        "limitations": ["No physical action, controller, sensor, model inference or Harness time is included",
            "Warm client uses a fresh socket per request; cold CLI includes Python process startup and imports",
            "Simulation worker remains active; other host load, thermal state and filesystem latency were uncontrolled",
            "Small sequential sample sets; p99 is not a statistically qualified tail bound and maximum is not a real-time guarantee",
            "No acceptance limit or cross-machine performance claim is established"]}
    destination = ROOT / "artifacts/verification/local-read-benchmark.json"
    destination.write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps({name: {key: value for key, value in result.items() if key != "samplesMs"}
                      for name, result in results.items()}, indent=2))
    print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
