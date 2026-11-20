"""Receipt bookkeeping fixtures only; never recursively run the project suite."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_runtime.py"
SPEC = importlib.util.spec_from_file_location("runtime_receipt_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ResultFixture:
    def __init__(self, *, failures=(), errors=(), skipped=()):
        self.testsRun = 7
        self.failures = list(failures)
        self.errors = list(errors)
        self.skipped = list(skipped)
        self.expectedFailures = []
        self.unexpectedSuccesses = []

    def wasSuccessful(self):
        return not self.failures and not self.errors and not self.unexpectedSuccesses


class RuntimeReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hms-runtime-receipts-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.py"
        self.source.write_bytes(b"initial source\n")
        self.dest = self.root / "artifacts/verification"
        self.dest.mkdir(parents=True)
        self.previous = self.dest / "local-runtime.json"
        self.previous.write_text('{"tests": 369, "historical": true}\n')
        self.old_success = self.previous.read_bytes()
        self.identity = {"compilerDigest": "fixture:identity", "manifest": {},
                         "currentManifest": {}, "import_matches_current": True}

    def run_fixture(self, result=None, mutate=None, **overrides):
        result = result or ResultFixture()
        def execute(root, stream):
            pointer = json.loads((self.dest / "local-runtime-current.json").read_text())
            self.assertEqual(pointer["status"], "running")
            self.assertFalse(pointer["current_pass"])
            stream.write("controlled result fixture\n")
            if mutate:
                mutate()
            return result
        options = {"paths_provider": lambda root: sorted(root.glob("*.py")),
                   "prepare": lambda root: None, "run_tests": execute,
                   "identity": lambda: dict(self.identity),
                   "reports_provider": lambda: {
                       "multi-cli-trace.json": {"module_loaded": True, "report": {"passed": False, "actual": 1}},
                       "procedure-transport-trace.json": {"module_loaded": True, "report": {"cases": {"partial": {}}}}},
                   "trace_producers": {"local-runtime-traces.json": lambda: {"fixture": True}}}
        options.update(overrides)
        return runner.run_attempt(self.root, **options)

    def assert_retained(self, artifact, receipt):
        pointer = json.loads((self.dest / "local-runtime-current.json").read_text())
        self.assertEqual(pointer["receipt"]["path"], str(receipt.relative_to(self.root)))
        self.assertEqual(pointer["receipt"]["sha256"], runner.digest(receipt))
        self.assertEqual(pointer["current_pass"], artifact["passed"])
        for item in artifact["files_before"] + artifact["files_after"]:
            data = (self.root / item["snapshot_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
        for item in artifact["outputs"]:
            self.assertEqual(runner.digest(self.root / item["path"]), item["sha256"])
        return pointer

    def test_failed_counts_reports_and_prior_success_are_retained(self):
        result = ResultFixture(failures=[("fail-case", "assertion")],
                               errors=[("error-case", "exception")],
                               skipped=[("skip-case", "reason")])
        artifact, receipt = self.run_fixture(result)
        pointer = self.assert_retained(artifact, receipt)
        self.assertEqual((artifact["tests"], artifact["failures"], artifact["errors"], artifact["skipped"]), (7, 1, 1, 1))
        self.assertEqual(artifact["status"], "failed")
        self.assertTrue(artifact["inputs_stable"])
        self.assertTrue(artifact["compiler_identity_stable"])
        self.assertEqual(self.previous.read_bytes(), self.old_success)
        self.assertEqual((self.root / pointer["last_success"]["path"]).read_bytes(), self.old_success)
        self.assertEqual(json.loads((receipt.parent / "outputs/multi-cli-trace.json").read_text()), {"passed": False, "actual": 1})
        self.assertFalse((receipt.parent / "outputs/local-runtime-traces.json").exists())
        self.assertFalse((self.dest / "local-runtime-tests.txt").exists())

    def test_pass_then_failure_keeps_immutable_success_and_advances_current(self):
        passed, first = self.run_fixture()
        self.assert_retained(passed, first)
        self.assertTrue(passed["passed"])
        saved_success = self.previous.read_bytes()
        saved_receipt = first.read_bytes()
        saved_log = (self.dest / "local-runtime-tests.txt").read_bytes()
        failed, second = self.run_fixture(ResultFixture(failures=[("later", "failed")]))
        pointer = self.assert_retained(failed, second)
        self.assertNotEqual(first.parent, second.parent)
        self.assertEqual(first.read_bytes(), saved_receipt)
        self.assertEqual(self.previous.read_bytes(), saved_success)
        self.assertEqual((self.dest / "local-runtime-tests.txt").read_bytes(), saved_log)
        self.assertFalse(pointer["current_pass"])

    def test_changed_added_and_removed_inputs_invalidate_nominal_test_pass(self):
        removed = self.root / "remove.py"
        removed.write_bytes(b"removed input\n")
        def mutate():
            self.source.write_bytes(b"changed source\n")
            removed.unlink()
            (self.root / "added.py").write_bytes(b"new source\n")
        artifact, receipt = self.run_fixture(mutate=mutate)
        self.assert_retained(artifact, receipt)
        self.assertFalse(artifact["passed"])
        self.assertFalse(artifact["inputs_stable"])
        self.assertEqual(artifact["input_changes"], {"added": ["added.py"], "removed": ["remove.py"], "changed": ["source.py"]})
        self.assertEqual((receipt.parent / "inputs-before/source.py").read_bytes(), b"initial source\n")
        self.assertEqual((receipt.parent / "inputs-after/source.py").read_bytes(), b"changed source\n")
        self.assertEqual(self.previous.read_bytes(), self.old_success)

    def test_trace_error_and_compiler_drift_preserve_result_and_log(self):
        calls = [0]
        def identity():
            calls[0] += 1
            return dict(self.identity, compilerDigest="fixture:" + str(calls[0]))
        def broken_trace():
            raise RuntimeError("trace failed after tests")
        artifact, receipt = self.run_fixture(identity=identity,
                                             trace_producers={"broken.json": broken_trace})
        self.assert_retained(artifact, receipt)
        self.assertEqual(artifact["status"], "error")
        self.assertEqual(artifact["tests"], 7)
        self.assertFalse(artifact["compiler_identity_stable"])
        self.assertIn("trace failed after tests", (receipt.parent / "outputs/local-runtime-tests.txt").read_text())
        self.assertEqual(self.previous.read_bytes(), self.old_success)

    def test_preflight_and_missing_input_produce_error_receipts_without_tests(self):
        ran = []
        def execute(root, stream):
            ran.append(True)
            return ResultFixture()
        missing = self.root / "missing.py"
        artifact, receipt = self.run_fixture(run_tests=execute,
                                             paths_provider=lambda root: [self.source, missing])
        self.assert_retained(artifact, receipt)
        self.assertEqual(artifact["status"], "error")
        self.assertFalse(artifact["test_result_available"])
        self.assertFalse(artifact["stable_input_proof"])
        self.assertFalse(ran)
        self.assertEqual(artifact["tests"], 0)
        self.assertEqual(len(artifact["input_capture_errors"]), 2)
        def fail_preflight(root):
            raise RuntimeError("invalid native fixture provenance")
        preflight, second = self.run_fixture(run_tests=execute, prepare=fail_preflight)
        self.assert_retained(preflight, second)
        self.assertEqual(preflight["status"], "error")
        self.assertTrue(preflight["inputs_stable"])
        self.assertFalse(preflight["test_result_available"])
        self.assertFalse(ran)

    def test_expected_failure_and_skip_do_not_publish_success(self):
        for name in ("expectedFailures", "skipped"):
            with self.subTest(category=name):
                result = ResultFixture()
                setattr(result, name, [("unproven-case", "not a passing test")])
                self.assertTrue(result.wasSuccessful())
                artifact, receipt = self.run_fixture(result)
                self.assert_retained(artifact, receipt)
                self.assertFalse(artifact["passed"])
                self.assertEqual(artifact["status"], "failed")
                self.assertEqual(artifact["expected_failures" if name == "expectedFailures" else "skipped"], 1)
                self.assertEqual(self.previous.read_bytes(), self.old_success)

    def test_failure_artifacts_are_copied_and_hash_mismatch_is_not_a_pass(self):
        failure = self.dest / "transport-failures/case-1"
        failure.mkdir(parents=True)
        payload = failure / "database.sqlite"
        payload.write_bytes(b"fixture DB snapshot, never opened")
        manifest = failure / "manifest.json"
        manifest.write_text(json.dumps({"files": [{"path": payload.name, "sha256": runner.digest(payload), "bytes": payload.stat().st_size}]}))
        reports = lambda: {"procedure-transport-trace.json": {"module_loaded": True,
                            "report": {"cases": {"failure": {"failureArtifacts": [str(manifest.relative_to(self.root))]}}}}}
        artifact, receipt = self.run_fixture(ResultFixture(failures=[("transport", "failure")]), reports_provider=reports)
        self.assert_retained(artifact, receipt)
        copied = receipt.parent / "outputs/transport-failures/case-1/database.sqlite"
        self.assertEqual(copied.read_bytes(), payload.read_bytes())
        payload.write_bytes(b"changed later")
        changed, second = self.run_fixture(reports_provider=reports)
        self.assert_retained(changed, second)
        self.assertEqual(changed["status"], "error")
        self.assertFalse(changed["passed"])
        self.assertEqual(copied.read_bytes(), b"fixture DB snapshot, never opened")


if __name__ == "__main__":
    unittest.main()
