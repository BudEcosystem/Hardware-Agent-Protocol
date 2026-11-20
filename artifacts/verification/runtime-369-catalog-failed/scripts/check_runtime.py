#!/usr/bin/env python3
"""Retain full local test results and synthetic three-scenario execution traces."""
import datetime
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trace():
    from hms.journal import Context
    from hms.runtime import Runtime
    owner = Context("trace-owner", "simulation:local")
    clock = [1000]
    with tempfile.TemporaryDirectory(prefix="hms-simulation-trace-") as directory:
        runtime = Runtime(directory, create=True, owner=owner,
                          wall_clock_ms=lambda: clock[0], monotonic_ms=lambda: clock[0])
        try:
            namespace = runtime.request(owner, "namespace", {"expiresUnixMs": 10000})["token"]
            records = []
            cases = [("sim:home-fan", "set_level", {"level": 37, "unit": "percent"}),
                     ("sim:microscope", "move_absolute", {"position": 42, "unit": "um", "frame": "sim:microscope"}),
                     ("sim:inspection-cell", "inspect", {"recipe": 1, "partId": "trace-part:1"})]
            for instance, action, arguments in cases:
                prepared = runtime.request(owner, "prepare", {
                    "instanceId": instance, "actionId": action, "arguments": arguments,
                    "operationKey": instance, "replayNamespace": namespace, "requiredEffect": "capability_completion",
                    "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000, "maxRunMs": 500, "latestCompletionUnixMs": 5500}})
                accepted = runtime.request(owner, "invoke", {"request": prepared["request"]})
                records.append({"prepared": prepared, "accepted": accepted})
            runtime.tick()
            for record in records:
                record["running"] = runtime.operation(owner, record["accepted"]["operationId"])
            clock[0] = 1100
            runtime.tick()
            for record in records:
                operation_id = record["accepted"]["operationId"]
                instance = record["accepted"]["instanceId"]
                record["completed"] = runtime.operation(owner, operation_id)
                record["observation"] = runtime.request(owner, "observe", {
                    "instanceId": instance, "property": "value", "maxAgeMs": 0, "evidenceKind": "simulation"})
                record["events"] = runtime.request(owner, "events", {"operationId": operation_id})
                record["retainedReplay"] = runtime.request(owner, "invoke", {"request": record["prepared"]["request"]})
                record["effectCount"] = runtime.plant.observe(instance)["effectCount"]
                if (record["completed"]["executionState"] != "completed" or record["effectCount"] != 1 or
                        record["completed"]["effectVerification"] != "unverified" or
                        record["completed"]["resourceClaims"] or record["retainedReplay"]["operationId"] != operation_id):
                    raise RuntimeError("synthetic trace invariant failed")
            return {"scope": "Synthetic plant and virtual clocks only; no physical verification", "scenarios": records}
        finally:
            runtime.close()


def main():
    endpoint_receipt = ROOT / 'artifacts/verification/endpoint-scenarios.json'
    endpoint = json.loads(endpoint_receipt.read_text())
    if not endpoint['passed']:
        raise RuntimeError('Build/check the original compact scenario fixture first')
    for item in endpoint['files'] + endpoint['outputs']:
        if digest(ROOT / item['path']) != item['sha256']:
            raise RuntimeError('Compact fixture provenance changed: '+item['path'])
    paths = sorted(set([*ROOT.glob("hms/**/*.py"), *ROOT.glob("tests/**/*.py"),
                        *ROOT.glob("schemas/*.json"), *ROOT.glob("examples/**/*.json"),
                        *ROOT.glob("tests/fixtures/*.json"), *ROOT.glob("protocol/serial/*.py"),
                        ROOT / "scripts/check_descriptions.py", ROOT / "scripts/check_wot_profile.py",
                        ROOT / "scripts/build_api_schema.py",
                        ROOT / "protocol/endpoint/vectors.json",
                        ROOT / "research/mcp/raw/schema__2026-07-28__schema.json",
                        ROOT / "research/protocols/wot-artifacts/td-schema-1.1.json", Path(__file__).resolve(),
                        endpoint_receipt, *[ROOT / item['path'] for item in endpoint['files']+endpoint['outputs']]]))
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in paths}
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    destination = ROOT / "artifacts/verification"
    destination.mkdir(exist_ok=True)
    log = destination / "local-runtime-tests.txt"
    log.write_text(output.getvalue())
    import test_multi_cli
    multi_path = destination / 'multi-cli-trace.json'
    multi_path.write_text(json.dumps(test_multi_cli.LAST_REPORT, indent=2) + '\n')
    import test_procedure_transport
    procedure_path = destination / 'procedure-transport-trace.json'
    procedure_path.write_text(json.dumps(test_procedure_transport.LAST_REPORT, indent=2) + '\n')
    print(output.getvalue().split("----------------------------------------------------------------------")[-1].strip())
    if not result.wasSuccessful() or result.skipped:
        print(f"Full log: {log}")
        raise SystemExit(1)
    trace_path = destination / "local-runtime-traces.json"
    trace_path.write_text(json.dumps(trace(), indent=2) + "\n")
    compact_path = destination / 'compact-host-traces.json'
    compact_path.write_text(json.dumps(compact_trace(), indent=2) + '\n')
    if hashes != {str(path.relative_to(ROOT)): digest(path) for path in paths}:
        raise RuntimeError("verification inputs changed during run")
    artifact = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": "python3 scripts/check_runtime.py",
        "scope": "All local Python suites, real Linux UDS/CLI subprocess integration, original native compact C scenarios, synthetic devices and clocks",
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "sqlite": sqlite3.sqlite_version, "jsonschema": importlib.metadata.version("jsonschema")},
        "tests": result.testsRun, "failures": 0, "errors": 0, "skipped": 0,
        "combined_runtime_crash_phases": ["accepted", "dispatch_claimed", "plant_pending", "plant_committed"],
        "procedure_crash_phases": ["parent_inside", "child_inside", "after_child", "after_handoff"],
        "limitations": ["No physical device, sensor, acquired controller or model execution", "No power-loss durability proof",
                        "One Unix UID is one principal; no per-agent delegation", "No bounded independent stop path",
                        "No remote transport, complete endpoint firmware, timing benchmark or Harness execution",
                        "Ordered bound procedures only; PAT synthesis/learning/promotion, parameterized control flow and physical I/O/driver/hub providers remain unimplemented",
                        "Mixed CLI trace records bounded unchanged-request retries after confirmed pre-admission freshness refusals; no availability guarantee"],
        "files": [{"path": path, "sha256": value} for path, value in hashes.items()],
        "outputs": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)} for path in (log, trace_path, compact_path, multi_path, procedure_path)],
    }
    artifact_path = destination / "local-runtime.json"
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps({"tests": result.testsRun, "artifact": str(artifact_path.relative_to(ROOT)), "scenarios": 3}))


def compact_trace():
    from test_endpoint_binding import CompactBindingTests
    fixture = CompactBindingTests()
    fixture.setUp()
    records = []
    try:
        cases = [('sim:home-fan','set_level',{'level':25,'unit':'percent'}),
                 ('sim:microscope','move_absolute',{'position':42,'unit':'um','frame':'sim:microscope'}),
                 ('sim:inspection-cell','inspect',{'recipe':1,'partId':'trace:part'})]
        for index, (instance, action, args) in enumerate(cases):
            request = fixture.prepare(instance, action, args, key=instance)
            accepted = fixture.invoke(request)
            fixture.runtime.tick()
            dispatched = fixture.status(accepted)
            reopened = None
            if index == 0:
                fixture.reopen()
                reopened = fixture.status(accepted)
            completed = fixture.finish(accepted)
            row = fixture.runtime.compact._row(accepted['operationId'])
            records.append({'request':request,'accepted':accepted,'dispatched':dispatched,'afterReopen':reopened,
                'completed':completed, 'replay':fixture.invoke(request), 'mapping':json.loads(row['mapping']),
                'payloadHex':row['payload'].hex(), 'receiptHex':row['receipt'].hex(), 'retired':bool(row['retired']),
                'events':fixture.call('events',operationId=accepted['operationId']),
                'observation':fixture.call('observe',instanceId=instance,property='value')})
        dispatches, effects = fixture.control_call(4), fixture.control_call(5)
        if dispatches != 3 or effects != 3 or fixture.packet_count(0x20) != 3:
            raise RuntimeError('Compact trace effect/replay invariant failed')
        packets = [dict(direction=row['direction'], boot=row['boot'], sequence=row['sequence'], wireHex=row['wire'].hex())
                   for row in fixture.runtime.journal._db.execute('SELECT * FROM ep_packets ORDER BY id')]
        return {'scope':'Original native C fixture behind durable Runtime; virtual clock and test-only independent counters; no physical evidence',
                'scenarios':records,'dispatchCount':dispatches,'effectCount':effects,'packets':packets}
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    main()
