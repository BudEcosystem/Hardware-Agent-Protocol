#!/usr/bin/env python3
"""Retain full local test results and synthetic three-scenario execution traces."""
import datetime
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import os
import sqlite3
import sys
import tempfile
import unittest
import traceback
import uuid

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


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic_json(path, value):
    """Publish a complete pointer/compatibility receipt, never a partial JSON file."""
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def input_paths(root):
    endpoint_receipt = root / "artifacts/verification/endpoint-scenarios.json"
    paths = set([*root.glob("hms/**/*.py"), *root.glob("tests/**/*.py"),
                 *root.glob("schemas/*.json"), *root.glob("examples/**/*.json"),
                 *root.glob("tests/fixtures/**/*.json"), *root.glob("protocol/serial/*.py"),
                 *[root / name for name in (
                     "scripts/check_descriptions.py", "scripts/check_wot_profile.py",
                     "scripts/build_api_schema.py", "scripts/check_runtime.py", "scripts/build_io_example.py",
                     "protocol/endpoint/vectors.json",
                     "research/mcp/raw/schema__2026-07-28__schema.json",
                     "research/protocols/wot-artifacts/td-schema-1.1.json")], endpoint_receipt])
    # Malformed/missing fixture metadata is diagnosed by preflight, after a
    # receipt directory and the available source snapshot have been retained.
    try:
        endpoint = json.loads(endpoint_receipt.read_text())
        for item in endpoint["files"] + endpoint["outputs"]:
            candidate = root / item["path"]
            if Path(item["path"]).is_absolute() or not candidate.resolve().is_relative_to(root):
                raise ValueError("Endpoint fixture path outside project")
            paths.add(candidate)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return sorted(paths)


def preflight(root):
    endpoint = json.loads((root / "artifacts/verification/endpoint-scenarios.json").read_text())
    if not endpoint["passed"]:
        raise RuntimeError("Build/check the original compact scenario fixture first")
    for item in endpoint["files"] + endpoint["outputs"]:
        path = root / item["path"]
        if Path(item["path"]).is_absolute() or not path.resolve().is_relative_to(root):
            raise RuntimeError("Compact fixture path outside project")
        if digest(path) != item["sha256"]:
            raise RuntimeError("Compact fixture provenance changed: " + item["path"])


def compiler_identity():
    from hms.pat_compiler import compiler_digest, compiler_manifest, _identity
    imported, current = compiler_manifest(), _identity()
    return {"compilerDigest": compiler_digest(), "manifest": imported,
            "currentManifest": current, "import_matches_current": imported == current}


def execute_tests(root, stream):
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    return unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)


def test_reports():
    reports = {}
    for module, filename in (("test_multi_cli", "multi-cli-trace.json"),
                             ("test_endpoint_cli", "endpoint-cli-trace.json"),
                             ("test_procedure_transport", "procedure-transport-trace.json"),
                             ("test_io_transport", "io-transport-trace.json"),
                             ("test_runtime_profiles", "runtime-profiles-trace.json"),
                             ("test_runtime_ipc", "runtime-ipc-trace.json")):
        loaded = sys.modules.get(module)
        reports[filename] = {"module_loaded": loaded is not None,
                             "report": getattr(loaded, "LAST_REPORT", None)}
    return reports


def environment():
    try:
        schema_version = importlib.metadata.version("jsonschema")
    except importlib.metadata.PackageNotFoundError:
        schema_version = None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "jsonschema": schema_version}


def capture_inputs(root, attempt, phase, paths_provider):
    rows, errors = [], []
    try:
        paths = sorted(set(paths_provider(root)))
    except Exception as error:
        return [], [{"stage": phase, "error": repr(error)}]
    for path in paths:
        try:
            relative = path.relative_to(root)
            if not path.resolve().is_relative_to(root):
                raise ValueError("Input symlink escapes project")
            data = path.read_bytes()
            saved = attempt / phase / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            with saved.open("xb") as handle:
                handle.write(data)
            rows.append({"path": str(relative), "sha256": hashlib.sha256(data).hexdigest(),
                         "bytes": len(data), "snapshot_path": str(saved.relative_to(root))})
        except Exception as error:
            errors.append({"path": str(path), "stage": phase, "error": repr(error)})
    return rows, errors


def retained_failures(root, attempt, reports):
    """Copy only explicit transport failure manifests and their listed artifacts."""
    manifests = set()
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "failureArtifacts":
                    if not isinstance(item, list) or not all(isinstance(p, str) for p in item):
                        raise ValueError("Malformed failureArtifacts list")
                    manifests.update(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(reports)
    outputs = []
    allowed = (root / "artifacts/verification/transport-failures").resolve()
    for name in sorted(manifests):
        source = (root / name).resolve()
        if Path(name).is_absolute() or not source.is_relative_to(allowed) or source.name != "manifest.json":
            raise ValueError("Failure manifest outside owned transport failure directory")
        manifest_bytes = source.read_bytes()
        manifest = json.loads(manifest_bytes)
        files = [(source, manifest_bytes)]
        for item in manifest["files"]:
            path = source.parent / item["path"]
            if Path(item["path"]).is_absolute() or not path.resolve().is_relative_to(source.parent):
                raise ValueError("Failure artifact escapes manifest directory")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"] or len(data) != item["bytes"]:
                raise ValueError("Failure artifact hash/size mismatch: " + str(path))
            files.append((path, data))
        for path, data in files:
            saved = attempt / "outputs/transport-failures" / path.relative_to(allowed)
            saved.parent.mkdir(parents=True, exist_ok=True)
            with saved.open("xb") as handle:
                handle.write(data)
            outputs.append({"path": str(saved.relative_to(root)),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "original_path": str(path.relative_to(root))})
    return outputs


def run_attempt(root=ROOT, *, paths_provider=input_paths, prepare=preflight,
                run_tests=execute_tests, identity=compiler_identity,
                reports_provider=test_reports, trace_producers=None):
    """Record one attempt; callbacks permit isolated bookkeeping tests only."""
    root = Path(root).resolve()
    destination = root / "artifacts/verification"
    attempts = destination / "runtime-attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    attempt_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:12]
    attempt = attempts / attempt_id
    attempt.mkdir()  # A completed attempt directory is never reused or overwritten.
    started = utc_now()
    current = destination / "local-runtime-current.json"
    previous_success = destination / "local-runtime.json"
    last_success = None
    if previous_success.exists():
        saved = attempt / "previous-success.json"
        saved.write_bytes(previous_success.read_bytes())
        last_success = {"path": str(saved.relative_to(root)), "sha256": digest(saved),
                        "scope": "Retained prior success receipt; not this attempt's outcome or a claim that old live paths still match"}
    pointer = {"schema": "hms-runtime-current/1", "attempt_id": attempt_id,
               "started_at": started, "status": "running", "current_pass": False,
               "attempt_dir": str(attempt.relative_to(root)), "receipt": None,
               "last_success": last_success}
    atomic_json(current, pointer)
    (attempt / "started.json").write_text(json.dumps(pointer, indent=2) + "\n")
    before, before_errors = capture_inputs(root, attempt, "inputs-before", paths_provider)
    before_identity = after_identity = None
    result = None
    output = io.StringIO()
    outputs, runner_errors, reasons = [], [], []
    stage = "preflight"
    def error_record(error):
        runner_errors.append({"stage": stage, "type": type(error).__name__,
                              "message": str(error), "traceback": traceback.format_exc()})
        output.write("\nRunner error at " + stage + ": " + traceback.format_exc())
    def save_json(name, value):
        path = attempt / "outputs" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as handle:
            handle.write(json.dumps(value, indent=2) + "\n")
        outputs.append({"path": str(path.relative_to(root)), "sha256": digest(path)})
    try:
        if before_errors:
            raise RuntimeError("Unable to snapshot every pre-run input")
        prepare(root)
        stage = "compiler_identity_before"
        before_identity = identity()
        save_json("pat-compiler-identity-before.json", before_identity)
        stage = "tests"
        result = run_tests(root, output)
    except (Exception, KeyboardInterrupt, SystemExit) as error:
        error_record(error)
    # Collect the actual reports even if preflight/discovery/tests failed.
    stage = "test_reports"
    try:
        reports = reports_provider()
        for name, value in reports.items():
            if Path(name).name != name:
                raise ValueError("Report filename must be a basename")
            save_json(name, value["report"] if value["module_loaded"] else {"available": False, "reason": "test module not loaded"})
        outputs.extend(retained_failures(root, attempt, reports))
    except Exception as error:
        error_record(error)
    tests_ok = (result is not None and result.testsRun > 0 and result.wasSuccessful()
                and not result.skipped and not result.expectedFailures)
    if tests_ok and not runner_errors:
        for name, producer in (trace_producers if trace_producers is not None else {
                "local-runtime-traces.json": trace, "compact-host-traces.json": compact_trace}).items():
            stage = "trace:" + name
            try:
                save_json(name, producer())
            except Exception as error:
                error_record(error)
    stage = "compiler_identity_after"
    try:
        after_identity = identity()
        save_json("pat-compiler-identity-after.json", after_identity)
    except Exception as error:
        error_record(error)
    after, after_errors = capture_inputs(root, attempt, "inputs-after", paths_provider)
    before_hashes = {r["path"]: r["sha256"] for r in before}
    after_hashes = {r["path"]: r["sha256"] for r in after}
    inputs_stable = not before_errors and not after_errors and before_hashes == after_hashes
    identity_stable = (before_identity is not None and before_identity == after_identity and
                       before_identity.get("import_matches_current") is True)
    if not tests_ok:
        reasons.append("tests_incomplete_failed_or_skipped")
    if not inputs_stable:
        reasons.append("input_snapshot_changed_or_incomplete")
    if not identity_stable:
        reasons.append("compiler_identity_changed_or_unavailable")
    if runner_errors:
        reasons.append("runner_error")
    save_json("pat-compiler-identity.json", {
        "compilerDigest": (before_identity or {}).get("compilerDigest"),
        "manifest": (before_identity or {}).get("manifest"),
        "before": before_identity, "after": after_identity, "stable": identity_stable,
        "scope": "Observed compiler/dependency identity before and after this attempt; no physical qualification"})
    log = attempt / "outputs/local-runtime-tests.txt"
    log.write_text(output.getvalue())
    outputs.append({"path": str(log.relative_to(root)), "sha256": digest(log)})
    def details(name):
        return [{"test": str(test), "detail": value} for test, value in getattr(result, name, [])]
    status = "error" if runner_errors else ("failed" if reasons else "passed")
    artifact = {
        "schema": "hms-runtime-attempt/1", "attempt_id": attempt_id,
        "started_at": started, "created_at": utc_now(), "status": status,
        "passed": status == "passed", "command": "python3 scripts/check_runtime.py",
        "scope": "All local Python suites, Linux UDS/CLI subprocess integration, original native compact C scenarios, synthetic devices/clocks; controlled fixtures only when explicitly injected by bookkeeping tests",
        "environment": environment(), "tests": getattr(result, "testsRun", 0),
        "failures": len(getattr(result, "failures", [])), "errors": len(getattr(result, "errors", [])),
        "skipped": len(getattr(result, "skipped", [])),
        "expected_failures": len(getattr(result, "expectedFailures", [])),
        "unexpected_successes": len(getattr(result, "unexpectedSuccesses", [])),
        "test_result_available": result is not None, "failure_details": details("failures"),
        "error_details": details("errors"), "skip_details": details("skipped"),
        "expected_failure_details": details("expectedFailures"),
        "unexpected_success_details": [str(test) for test in getattr(result, "unexpectedSuccesses", [])],
        "runner_errors": runner_errors, "failure_reasons": reasons,
        "inputs_stable": inputs_stable, "stable_input_proof": inputs_stable,
        "input_capture_errors": before_errors + after_errors,
        "input_changes": {"added": sorted(after_hashes.keys() - before_hashes.keys()),
                          "removed": sorted(before_hashes.keys() - after_hashes.keys()),
                          "changed": sorted(k for k in before_hashes.keys() & after_hashes.keys()
                                            if before_hashes[k] != after_hashes[k])},
        "compiler_identity_stable": identity_stable,
        "files": [{"path": r["path"], "sha256": r["sha256"]} for r in before],
        "files_before": before, "files_after": after, "outputs": outputs,
        "combined_runtime_crash_phases": ["accepted", "dispatch_claimed", "plant_pending", "plant_committed"],
        "procedure_crash_phases": ["parent_inside", "child_inside", "after_child", "after_handoff"],
        "limitations": ["No physical device, sensor, acquired controller or neural-model execution; original synthetic plant/I/O models are executed",
                        "No power-loss durability proof; snapshots are sequential per-file observations, not an atomic filesystem snapshot or detection of transient change-and-restore",
                        "One Unix UID is one principal; no per-agent delegation or bounded independent stop path",
                        "No remote transport, complete endpoint firmware, timing benchmark or Harness execution",
                        "PAT compiler/catalog are host libraries; no production qualification, model synthesis/learning or physical I/O providers",
                        "Failure counts describe tests actually run; named scenario lists are intended suite scope, not proof they passed when this attempt failed"],
        "last_success_before_attempt": last_success,
    }
    receipt = attempt / "receipt.json"
    with receipt.open("x") as handle:
        handle.write(json.dumps(artifact, indent=2) + "\n")
    reference = {"path": str(receipt.relative_to(root)), "sha256": digest(receipt)}
    if artifact["passed"]:
        # Compatibility aliases are last-success artifacts only. All authoritative
        # output references above point into this immutable attempt directory.
        for item in outputs:
            source = root / item["path"]
            if source.parent == attempt / "outputs":
                target = destination / source.name
                temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
                temporary.write_bytes(source.read_bytes())
                os.replace(temporary, target)
        atomic_json(previous_success, artifact)
        last_success = reference
    pointer.update(status=status, current_pass=artifact["passed"], receipt=reference,
                   completed_at=artifact["created_at"], inputs_stable=inputs_stable,
                   stable_input_proof=inputs_stable, last_success=last_success)
    atomic_json(current, pointer)
    return artifact, receipt


def main():
    artifact, receipt = run_attempt()
    print(json.dumps({"tests": artifact["tests"], "failures": artifact["failures"],
                      "errors": artifact["errors"], "skipped": artifact["skipped"],
                      "status": artifact["status"], "inputs_stable": artifact["inputs_stable"],
                      "artifact": str(receipt.relative_to(ROOT)),
                      "current": "artifacts/verification/local-runtime-current.json"}))
    raise SystemExit(0 if artifact["passed"] else 1)


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
