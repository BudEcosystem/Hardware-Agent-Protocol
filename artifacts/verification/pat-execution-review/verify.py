#!/usr/bin/env python3
"""Verify frozen review hashes and LF coverage; never import or execute HMS."""
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
LANE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(compare_live=False):
    index = json.loads((LANE / "index.json").read_text())
    paths = set()
    for item in index["files"]:
        path = ROOT / item["path"]
        require(path.is_relative_to(LANE), "out-of-lane manifest path")
        require(item["path"] not in paths, "duplicate manifest path")
        paths.add(item["path"])
        data = path.read_bytes()
        require(len(data) == item["bytes"] and digest(data) == item["sha256"], "manifest mismatch: " + item["path"])
    actual = {str(path.relative_to(ROOT)) for path in LANE.rglob("*") if path.is_file()
              and path.name not in {"index.json", "verification.json"}}
    require(paths == actual, "manifest inventory mismatch")
    acquisition = json.loads((LANE / "acquisition.json").read_text())
    reading = json.loads((LANE / "reading.json").read_text())
    after = json.loads((LANE / "source-after.json").read_text())
    acquired = {row["source"]: row for row in acquisition["items"]}
    stability = {row["source"]: row for row in after["checks"]}
    require(len(acquired) == len(acquisition["items"]) == len(reading["sources"]) == len(stability), "source inventory mismatch")
    require(after["all_stable"] is True, "review captured source drift")
    full_count = chunks = lines_read = 0
    seen = set()
    live_matches = []
    for row in reading["sources"]:
        source = row["source"]
        require(source not in seen and source in acquired, "duplicate or unknown reading source")
        seen.add(source)
        item = acquired[source]
        data = (ROOT / item["snapshot"]).read_bytes()
        require(digest(data) == row["sha256"] == item["sha256"], "source digest mismatch")
        require(data.endswith(b"\n") and data.count(b"\n") == item["lf_lines"], "LF extent mismatch")
        split = data.splitlines(keepends=True)
        require(len(split) == item["lf_lines"], "unexpected non-LF line boundary")
        previous = 0
        covered = 0
        for chunk in row["chunks"]:
            start, end = chunk["start_lf"], chunk["end_lf"]
            require(type(start) is int and type(end) is int and previous < start <= end <= len(split), "invalid or overlapping coverage")
            if row["scope"] == "full":
                require(start == previous + 1, "gap in full reading")
            require(digest(b"".join(split[start - 1:end])) == chunk["sha256"], "chunk digest mismatch")
            previous = end
            covered += end - start + 1
            chunks += 1
        if row["scope"] == "full":
            require(previous == len(split), "incomplete full reading")
            full_count += 1
        else:
            require(row["scope"] == "selected", "unsupported reading scope")
        require(covered == row["lines_read"], "reading count mismatch")
        lines_read += covered
        stamp = stability[source]
        require(stamp["stable"] is True and stamp["before_sha256"] == stamp["snapshot_sha256"] == stamp["after_sha256"] == item["sha256"], "stability mismatch")
        if compare_live:
            live_matches.append(digest((ROOT / source).read_bytes()) == item["sha256"])
    require(full_count == reading["full_sources"] and chunks == reading["chunks"] and lines_read == reading["lines_read"], "aggregate reading mismatch")
    require(not compare_live or all(live_matches), "current source drift")
    return {"schema": "hms-readonly-review-verification/1", "status": "verified",
            "scope": "frozen artifact integrity and reading coverage; not runtime testing",
            "files_verified": len(paths), "sources": len(seen), "full_sources": full_count,
            "chunks": chunks, "lines_read": lines_read, "review_before_after_stable": True,
            "current_live_compared": compare_live, "current_live_matches": all(live_matches) if compare_live else None}


if __name__ == "__main__":
    require(sys.argv[1:] in ([], ["--compare-live"]), "usage: verify.py [--compare-live]")
    print(json.dumps(verify(bool(sys.argv[1:])), indent=2))
