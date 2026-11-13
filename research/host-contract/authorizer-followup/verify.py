"""Offline hashes and full LF coverage only; no SQLite or acquired-code execution."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def coverage(sources):
    for source in sources:
        data = (ROOT / source["path"]).read_bytes()
        lines = data.splitlines(keepends=True)
        if len(lines) != source["lfLines"] or not data.endswith(b"\n"):
            raise ValueError("line count mismatch")
        covered = []
        for chunk in source["chunks"]:
            start, end = chunk["start"], chunk["end"]
            if not 1 <= start <= end <= len(lines):
                raise ValueError("invalid range")
            if hashlib.sha256(b"".join(lines[start - 1:end])).hexdigest() != chunk["sha256"]:
                raise ValueError("chunk mismatch")
            covered.extend(range(start, end + 1))
        if covered != list(range(1, len(lines) + 1)):
            raise ValueError("full reading coverage incomplete")


def verify():
    index = json.loads((HERE / "index.json").read_text())
    names = set()
    for row in index["files"]:
        path = Path(row["path"])
        if path.is_absolute() or ".." in path.parts or row["path"] in names:
            raise ValueError("unsafe or duplicate path")
        names.add(row["path"])
        data = (ROOT / path).read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("file mismatch")
    actual = {str(path.relative_to(ROOT)) for path in HERE.rglob("*") if path.is_file()
              and path.name not in {"index.json", "verification.json"}}
    if names != actual:
        raise ValueError("inventory mismatch")
    reading = json.loads((HERE / "reading.json").read_text())
    coverage(reading["sources"])
    for source in reading["sources"]:
        if hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("reading source mismatch")
    bad = copy.deepcopy(reading["sources"])
    bad[0]["chunks"] = []
    try:
        coverage(bad)
    except ValueError:
        pass
    else:
        raise ValueError("missing full coverage accepted")
    return {"passed": True, "files": len(names), "fullyReadSources": len(reading["sources"]),
            "lfLines": sum(s["lfLines"] for s in reading["sources"]),
            "negativeCoverageChecks": 1, "sqliteTestsExecuted": False}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
