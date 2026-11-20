"""Offline frozen-lane verification; never import or execute staged HMS code."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def validate_rows(rows, base):
    seen = set()
    for row in rows:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts or row["path"] in seen:
            raise ValueError("unsafe or duplicate path")
        seen.add(row["path"])
        data = (base / relative).read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("pin mismatch: " + row["path"])
    return seen


def verify(compare_live=False):
    index = json.loads((HERE / "index.json").read_text())
    paths = validate_rows(index["files"], ROOT)
    actual = {str(path.relative_to(ROOT)) for path in HERE.rglob("*") if path.is_file()
              and path.name not in {"index.json", "verification.json"}}
    if actual != paths:
        raise ValueError("sealed inventory mismatch")
    originals = json.loads((HERE / "baseline/inputs.json").read_text())["files"]
    validate_rows(originals, HERE / "baseline/sources")
    if compare_live:
        validate_rows(originals, ROOT)
    results = []
    for attempt in sorted((HERE / "attempts").iterdir()):
        before = json.loads((attempt / "before.json").read_text())
        after = json.loads((attempt / "after.json").read_text())
        validate_rows(before, attempt / "inputs")
        receipt = json.loads((attempt / "result.json").read_text())
        if before != after or not receipt["inputsUnchanged"] or len(before) != receipt["inputCount"]:
            raise ValueError("attempt input stability mismatch")
        expected = (receipt["failures"] == receipt["errors"] == receipt["skips"] ==
                    receipt["expectedFailures"] == receipt["unexpectedSuccesses"] == 0
                    and receipt["importsScopedToSnapshots"])
        if receipt["passed"] != expected:
            raise ValueError("incorrect attempt outcome")
        results.append({"attempt": attempt.name, "passed": receipt["passed"], "tests": receipt["tests"]})
    changes = []
    for path in sorted((HERE / "staged").rglob("*")):
        if path.is_file() and path.read_bytes() != (HERE / "baseline/sources" / path.relative_to(HERE / "staged")).read_bytes():
            changes.append(str(path.relative_to(HERE / "staged")))
    if changes != ["hms/pat_compiler.py"]:
        raise ValueError("unexpected staged edits")
    # Exercise hash and duplicate guards without mutating any retained file.
    for corrupt in ([index["files"][0] | {"sha256": "0" * 64}], [index["files"][0]] * 2):
        try:
            validate_rows(corrupt, ROOT)
        except ValueError:
            pass
        else:
            raise ValueError("negative integrity guard accepted corruption")
    return {"passed": True, "indexedFiles": len(paths), "baselineInputs": len(originals),
            "stagedChanges": changes, "attempts": results, "liveComparison": compare_live,
            "negativeIntegrityChecks": 2}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare-live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.compare_live), indent=2))
