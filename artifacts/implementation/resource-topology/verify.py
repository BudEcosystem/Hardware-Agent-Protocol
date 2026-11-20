"""Offline staged artifact verification; no source imports or runtime calls."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def rows_valid(rows, base):
    seen = set()
    for row in rows:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts or row["path"] in seen:
            raise ValueError("unsafe/duplicate path")
        seen.add(row["path"])
        data = (base / relative).read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("hash/length mismatch: " + row["path"])
    return seen


def verify():
    index = json.loads((HERE / "index.json").read_text())
    files = rows_valid(index["files"], ROOT)
    actual = {str(path.relative_to(ROOT)) for path in HERE.rglob("*") if path.is_file()
              and path.name not in {"index.json", "verification.json"}}
    if files != actual:
        raise ValueError("inventory mismatch")
    baseline = json.loads((HERE / "baseline/inputs.json").read_text())["files"]
    rows_valid(baseline, HERE / "baseline")
    prior_seals = []
    for seal in sorted((HERE / "seals").iterdir()) if (HERE / "seals").exists() else []:
        historical = json.loads((seal / "prior-index.json").read_text())
        rows_valid(historical["files"], seal / "files")
        archive = json.loads((seal / "archive.json").read_text())
        if hashlib.sha256((seal / "prior-index.json").read_bytes()).hexdigest() != archive["originalIndexSha256"]:
            raise ValueError("historical seal changed")
        prior_seals.append({"seal": seal.name, "files": len(historical["files"])})
    proofs = []
    for attempt in sorted((HERE / "attempts").iterdir()):
        before = json.loads((attempt / "before.json").read_text())
        after = json.loads((attempt / "after.json").read_text())
        rows_valid(before, attempt / "inputs")
        receipt = json.loads((attempt / "result.json").read_text())
        if before != after or not receipt["inputsUnchanged"] or len(before) != receipt["inputCount"]:
            raise ValueError("attempt stability mismatch")
        passed = (receipt["failures"] == receipt["errors"] == receipt["skips"] ==
                  receipt["expectedFailures"] == receipt["unexpectedSuccesses"] == 0 and
                  receipt["importsScopedToSnapshots"])
        if passed != receipt["passed"]:
            raise ValueError("attempt outcome mismatch")
        proofs.append({"attempt": attempt.name, "tests": receipt["tests"], "passed": passed})
    latest = json.loads((sorted((HERE / "attempts").iterdir())[-1] / "after.json").read_text())
    rows_valid(latest, HERE)
    for corrupt in ([index["files"][0] | {"sha256": "0" * 64}], [index["files"][0]] * 2):
        try:
            rows_valid(corrupt, ROOT)
        except ValueError:
            pass
        else:
            raise ValueError("negative integrity check accepted corruption")
    return {"passed": True, "indexedFiles": len(files), "baselineInputs": len(baseline),
            "attempts": proofs, "priorSeals": prior_seals, "negativeIntegrityChecks": 2, "runtimeOrProviderExecuted": False}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
