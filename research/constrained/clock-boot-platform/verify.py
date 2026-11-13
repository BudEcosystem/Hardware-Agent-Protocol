#!/usr/bin/env python3
"""Original offline verifier for this nested primary-source reading receipt.

Hashes establish byte/coverage consistency, not reading comprehension or device
qualification. Never imports or executes acquired code; all mutations below are
copies of JSON metadata in memory.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LANE = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lf_lines(data: bytes) -> list[bytes]:
    parts = data.split(b"\n")
    return [p + b"\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def local(path: str, *, lane_only: bool = True) -> Path:
    require(isinstance(path, str) and not Path(path).is_absolute(), "relative path")
    p = (ROOT / path).resolve()
    require(p.is_relative_to(LANE if lane_only else ROOT), "path outside scope")
    require(p.is_file(), "missing file")
    return p


def validate(receipt: dict) -> dict:
    require(receipt["schema_version"] == 1, "schema version")
    manifest = [json.loads(line) for line in local(receipt["manifest_path"]).read_text().splitlines()]
    by_id = {r["id"]: r for r in manifest}
    require(len(by_id) == len(manifest), "duplicate acquisition id")
    sources = receipt["sources"]
    require(len({r["id"] for r in sources}) == len(sources), "duplicate source id")
    require(set(by_id) == {r["id"] for r in sources}, "acquisition/reading mismatch")
    full = selected = covered = 0
    for row in sources:
        acquired = by_id[row["id"]]
        raw = local(row["raw_path"]).read_bytes()
        txt = local(row["text_path"]).read_bytes()
        require(row["raw_path"] == acquired["raw_path"], "raw path mismatch")
        require(digest(raw) == row["raw_sha256"] == acquired["sha256"], "raw hash")
        require(len(raw) == acquired["bytes"] and acquired["http_status"] == 200, "raw size/status")
        require(row["url"] == acquired["url"] and row["final_url"] == acquired["final_url"], "URL mismatch")
        require(digest(txt) == row["text_sha256"], "text hash")
        lines = lf_lines(txt)
        require(row["line_count"] == len(lines), "line count")
        seen: set[int] = set()
        last = 0
        for part in row["coverage_ranges"]:
            start, end = part["start_line"], part["end_line"]
            require(type(start) is int and type(end) is int and last < start <= end <= len(lines), "range/order")
            require(end - start < 300, "unbounded reading chunk")
            require(digest(b"".join(lines[start - 1:end])) == part["sha256"], "chunk hash")
            seen.update(range(start, end + 1))
            last = end
        complete = len(seen) == len(lines)
        require(type(row["coverage_complete"]) is bool and row["coverage_complete"] == complete, "coverage assertion")
        expected = "full_file_read" if complete else "selected_ranges_read"
        require(row["reading_status"] == acquired["reading_status"] == expected, "reading status")
        require(row["covered_line_count"] == len(seen), "covered count")
        require(len(seen) > 0, "unread source")
        full += complete
        selected += not complete
        covered += len(seen)
    figures = json.loads(local(receipt["figure_manifest_path"]).read_text())
    require(len({r["path"] for r in figures}) == len(figures), "duplicate figure")
    for row in figures:
        require(row["source_id"] in by_id, "figure source")
        require(type(row["pdf_page_1_based"]) is int and row["pdf_page_1_based"] > 0, "figure page")
        require(row["visual_inspection"] == "reviewed", "unreviewed figure")
        require(row["source_raw_sha256"] == by_id[row["source_id"]]["sha256"], "figure raw pin")
        require(digest(local(row["path"]).read_bytes()) == row["sha256"], "figure hash")
    for row in receipt["integrity_files"]:
        require(digest(local(row["path"], lane_only=False).read_bytes()) == row["sha256"], "integrity file hash")
    totals = dict(sources=len(sources), full_files=full, selected_files=selected,
                  covered_lf_lines=covered, visually_reviewed_pages=len(figures))
    require(totals == receipt["totals"], "totals")
    return totals


def main() -> None:
    receipt_path = LANE / "reading.json"
    receipt = json.loads(receipt_path.read_text())
    totals = validate(receipt)
    bad_cases = []
    changed = copy.deepcopy(receipt); changed["sources"][0]["raw_sha256"] = "0" * 64; bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["sources"][0]["coverage_complete"] = True; bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["sources"][0]["coverage_ranges"][0]["end_line"] += 1; bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["sources"][0]["line_count"] += 1; bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["sources"][0]["text_path"] = "../escape"; bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["sources"].append(changed["sources"][0]); bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["sources"][0]["coverage_ranges"].append(changed["sources"][0]["coverage_ranges"][0]); bad_cases.append(changed)
    changed = copy.deepcopy(receipt); changed["totals"]["full_files"] += 1; bad_cases.append(changed)
    for changed in bad_cases:
        try:
            validate(changed)
        except ValueError:
            pass
        else:
            raise AssertionError("negative metadata check accepted")
    print(json.dumps(dict(ok=True, reading_sha256=digest(receipt_path.read_bytes()),
                         **totals, negative_metadata_checks=len(bad_cases),
                         scope="Offline byte/coverage integrity only; no acquired-code or device execution."), indent=2))


if __name__ == "__main__":
    main()
