"""Capture and execute only the original staged pure resource-contract tests."""
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
    attempts = HERE / "attempts"; attempts.mkdir(exist_ok=True)
    attempt = attempts / ("%02d" % (len(list(attempts.iterdir())) + 1)); attempt.mkdir()
    paths = sorted([*HERE.glob("staged/**/*.py"), *HERE.glob("staged/**/*.json"),
                    HERE / "test_resource_topology.py", HERE / "build_schemas.py", Path(__file__)])
    before = [pin(path) for path in paths]
    for path in paths:
        output = attempt / "inputs" / path.relative_to(HERE)
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(path.read_bytes())
    (attempt / "before.json").write_text(json.dumps(before, indent=2) + "\n")
    started, clock = datetime.now(timezone.utc).isoformat(), time.monotonic()
    spec = importlib.util.spec_from_file_location("test_resource_topology", HERE / "test_resource_topology.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    (attempt / "tests.txt").write_text(stream.getvalue())
    after = [pin(path) for path in paths]
    (attempt / "after.json").write_text(json.dumps(after, indent=2) + "\n")
    imports = {name: str(Path(value.__file__).resolve()) for name, value in sys.modules.items()
               if name.startswith("hms") and getattr(value, "__file__", None)}
    scoped = all(str(HERE / "staged") + "/" in path for path in imports.values()) and "hms.runtime" not in imports
    passed = result.wasSuccessful() and not result.skipped and not result.expectedFailures and before == after and scoped
    receipt = {"schema": "hms-staged-pure-tests/1", "startedUtc": started, "seconds": time.monotonic() - clock,
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skips": len(result.skipped), "expectedFailures": len(result.expectedFailures),
        "unexpectedSuccesses": len(result.unexpectedSuccesses), "inputCount": len(before),
        "inputsUnchanged": before == after, "importsScopedToSnapshots": scoped, "imports": imports,
        "passed": passed, "limits": ["Pure contract/set-closure evidence only, not Runtime claim exclusion.",
            "No provider, database, hardware, model or acquired program execution.",
            "Generation nonreuse across history is not established by one parsed snapshot."]}
    (attempt / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(stream.getvalue())
    print(json.dumps({key: receipt[key] for key in ("tests", "failures", "errors", "inputCount", "inputsUnchanged", "passed")}))
    raise SystemExit(0 if passed else 1)
