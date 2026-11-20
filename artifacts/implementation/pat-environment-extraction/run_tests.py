"""Original staged pure-test runner with immutable per-attempt inputs/logs."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE / "staged"))


def pin(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(HERE)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


if __name__ == "__main__":
    attempts = HERE / "attempts"
    attempts.mkdir(exist_ok=True)
    attempt = attempts / ("%02d" % (len(list(attempts.iterdir())) + 1))
    attempt.mkdir()
    paths = sorted([*HERE.glob("staged/**/*.py"), *HERE.glob("staged/**/*.json"),
                    *HERE.glob("baseline/sources/**/*.py"), *HERE.glob("baseline/sources/**/*.json"),
                    HERE / "fixtures/families.json", HERE / "test_environment.py", Path(__file__)])
    before = [pin(path) for path in paths]
    for path in paths:
        destination = attempt / "inputs" / path.relative_to(HERE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    (attempt / "before.json").write_text(json.dumps(before, indent=2) + "\n")
    started = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    stream = io.StringIO()
    spec = importlib.util.spec_from_file_location("test_environment", HERE / "test_environment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    output = stream.getvalue()
    (attempt / "tests.txt").write_text(output)
    after = [pin(path) for path in paths]
    (attempt / "after.json").write_text(json.dumps(after, indent=2) + "\n")
    imported = {name: str(Path(value.__file__).resolve()) for name, value in sys.modules.items()
                if name.startswith("hms") and getattr(value, "__file__", None)}
    imports_ok = all(str(HERE) + "/" in path for path in imported.values()) and "hms.runtime" not in imported
    passed = result.wasSuccessful() and not result.skipped and not result.expectedFailures and before == after and imports_ok
    receipt = {"schema": "hms-staged-pure-tests/1", "startedUtc": started,
        "endedUtc": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - start,
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skips": len(result.skipped), "expectedFailures": len(result.expectedFailures),
        "unexpectedSuccesses": len(result.unexpectedSuccesses), "inputCount": len(before),
        "inputsUnchanged": before == after, "importsScopedToSnapshots": imports_ok,
        "importedLocalModules": imported, "passed": passed,
        "limits": ["Pure original compiler/data validation only.", "No Runtime, worker, device, model or live admission executed.",
                   "Fixed-identity differential oracle explicitly normalizes only COMPILER_DIGEST in the staged module."]}
    (attempt / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(output)
    print(json.dumps({key: receipt[key] for key in ("tests", "failures", "errors", "inputsUnchanged", "importsScopedToSnapshots", "passed")}))
    raise SystemExit(0 if passed else 1)
