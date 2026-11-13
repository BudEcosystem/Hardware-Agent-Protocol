#!/usr/bin/env python3
"""Verify retained source provenance and coverage metadata; execute no source code."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "research/embedded"
repositories = json.loads((BASE / "repositories.json").read_text())["repositories"]
reading = json.loads((BASE / "reading-log.json").read_text())
count = 0
lines_total = 0
bytes_total = 0
for entry in reading["files"]:
    data = (ROOT / entry["path"]).read_bytes()
    line_count = data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))
    assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
    assert len(data) == entry["bytes"], entry["path"]
    assert data.count(b"\n") == entry["lf_count"], entry["path"]
    assert line_count == entry["logical_lines"], entry["path"]
    assert data.endswith(b"\n") == entry["ends_with_lf"], entry["path"]
    assert entry["reading_status"] == "read_full", entry["path"]
    assert entry["read_ranges_inclusive"] == [[1, line_count]], entry["path"]
    assert entry["covered_lines"] == line_count, entry["path"]
    count += 1
    lines_total += line_count
    bytes_total += len(data)
for entry in repositories:
    checkout = str(ROOT / entry["checkout_path"])
    commit = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
    assert commit == entry["commit"], entry["id"]
    status = subprocess.check_output(["git", "-C", checkout, "status", "--porcelain"], text=True)
    assert not status, (entry["id"], status)
    expected = set(entry["inspected_files"])
    actual = {f["repository_relative_path"] for f in reading["files"] if f["repository"] == entry["id"]}
    assert actual == expected, entry["id"]
assert reading["totals"] == {
    "files_read_full": count,
    "covered_logical_lines": lines_total,
    "bytes_hashed": bytes_total,
}
print(f"Verified {count} full-file records, {lines_total} logical lines, {bytes_total} bytes, and {len(repositories)} clean pinned checkouts.")
