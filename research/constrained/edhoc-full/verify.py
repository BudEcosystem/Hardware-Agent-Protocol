#!/usr/bin/env python3
"""Offline archival checks, not an EDHOC implementation or proof of reading."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
REVIEWED_PAGES = [6, 8, 10, 11, 16, 20, 26, 35, 36, 37, 38, 49, 50,
                  51, 52, 53, 55, 62, 63, 65, 66, 68, 69, 79, 81]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_path(value):
    relative = Path(value)
    path = (ROOT / relative).resolve()
    require(not relative.is_absolute() and path.is_relative_to(ROOT),
            f"Not a repository-relative local path: {value}")
    return path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_hash(path, expected):
    require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None, "Invalid SHA-256")
    actual = digest(local_path(path).read_bytes())
    require(actual == expected, f"Hash mismatch: {path}")


def lf_lines(data):
    # Keep CR and PDF form-feed bytes within their LF-delimited lines.
    parts = data.split(b"\n")
    return [part + b"\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def verify_coverage(row):
    intervals = row.get("coverage_ranges", [])
    claims_full = row.get("coverage_complete", False) or row.get("reading_status") == "read_full"
    if "text_path" not in row:
        require(not intervals and not claims_full, "Full reading lacks a text source")
        return 0
    lines = lf_lines(local_path(row["text_path"]).read_bytes())
    require(row["line_count"] == len(lines), "LF line count mismatch")
    covered = set()
    last_end = 0
    for chunk in intervals:
        start, end = chunk["start_line"], chunk["end_line"]
        require(isinstance(start, int) and isinstance(end, int), "Invalid range type")
        require(1 <= start <= end <= len(lines), "Coverage outside text")
        require(start > last_end, "Overlapping or out-of-order coverage")
        require(digest(b"".join(lines[start - 1:end])) == chunk["sha256"],
                "Coverage hash mismatch")
        covered.update(range(start, end + 1))
        last_end = end
    if claims_full:
        require(covered == set(range(1, len(lines) + 1)), "Incomplete full-reading claim")
    require(abs(row["text_coverage_fraction"] - len(covered) / len(lines)) < 1e-12,
            "Incorrect coverage fraction")
    return len(intervals)


def expect_rejection(function):
    try:
        function()
    except ValueError:
        return
    raise AssertionError("Negative self-check unexpectedly passed")


def main():
    reading = json.loads((BASE / "reading.json").read_text())
    manifest = [json.loads(line) for line in (BASE / "manifest.jsonl").read_text().splitlines()]
    require(len(manifest) == 6 and len({r["id"] for r in manifest}) == 6,
            "Unexpected retrieval inventory")
    checked = set()
    for row in manifest:
        require(row["status"] == "downloaded" and row["retrieved_at"], "Incomplete acquisition")
        require(row["url"].startswith(("https://www.rfc-editor.org/", "https://www.iana.org/")),
                "Unexpected source origin")
        verify_hash(row["raw_path"], row["sha256"])
        checked.add(row["raw_path"])
        require(local_path(row["raw_path"]).stat().st_size == row["bytes"], "Raw size mismatch")
        if "text_path" in row:
            verify_hash(row["text_path"], row["text_sha256"])
            checked.add(row["text_path"])
    sources = reading["sources"]
    require({s["id"] for s in sources} == {m["id"] for m in manifest}, "Reading/source mismatch")
    chunks = 0
    for row in sources:
        acquisition = next(m for m in manifest if m["id"] == row["id"])
        require(row["raw_path"] == acquisition["raw_path"] and
                row["raw_sha256"] == acquisition["sha256"], "Reading acquisition mismatch")
        for path_key, hash_key in (("raw_path", "raw_sha256"), ("text_path", "text_sha256")):
            if path_key in row:
                verify_hash(row[path_key], row[hash_key])
                checked.add(row[path_key])
        chunks += verify_coverage(row)
    for row in reading["integrity_files"] + reading["figures"]:
        verify_hash(row["path"], row["sha256"])
        checked.add(row["path"])
    require(sum(s["coverage_complete"] for s in sources) == 4, "Wrong full-source count")
    rfc = next(s for s in sources if s["id"] == "rfc9528-text")
    require(rfc["line_count"] == 4671 and rfc["reading_status"] == "read_full",
            "Missing complete RFC reading assertion")
    text = local_path(rfc["text_path"]).read_text(encoding="utf-8")
    for label, count in (("Figure", 13), ("Table", 15)):
        actual = list(map(int, re.findall(rf"^\s*{label} (\d+):", text, re.MULTILINE)))
        require(actual == list(range(1, count + 1)), f"Unexpected {label} inventory")
    require([f["pdf_page"] for f in reading["figures"]] == REVIEWED_PAGES,
            "Selected visual page inventory mismatch")
    require(all(f["visual_review_status"] == "reviewed_figures_and_tables"
                for f in reading["figures"]), "Unreviewed visual listed as evidence")
    pdf = next(s for s in sources if s["id"] == "rfc9528-pdf")
    require(pdf["pdf_page_count"] == 82 and not pdf["coverage_complete"] and
            not pdf["all_pdf_pages_reviewed"] and pdf["reviewed_pdf_pages"] == REVIEWED_PAGES,
            "PDF review scope overclaimed")
    require(reading["errata"] == [{"id": 8258, "status": "Reported", "type": "Technical"},
                                  {"id": 8272, "status": "Reported", "type": "Technical"}],
            "Errata status mismatch")
    metadata = json.loads((BASE / "raw/rfc9528-metadata.json").read_text())
    require(metadata["status"] == "PROPOSED STANDARD" and
            all(metadata[k] == [] for k in ("updates", "updated_by", "obsoletes", "obsoleted_by")),
            "Metadata snapshot changed")
    prior = json.loads((ROOT / "research/constrained/reading-oscore-full.json").read_text())
    old = next(s for s in prior["sources"] if s["id"] == "edhoc-rfc9528")
    require(rfc["raw_sha256"] == old["raw_sha256"] and not old["coverage_complete"],
            "Prior selected-source relationship changed")
    broken = deepcopy(rfc)
    broken["coverage_ranges"].pop()
    expect_rejection(lambda: verify_coverage(broken))
    broken_hash = deepcopy(rfc)
    broken_hash["coverage_ranges"][0]["sha256"] = "0" * 64
    expect_rejection(lambda: verify_coverage(broken_hash))
    overlap = deepcopy(rfc)
    overlap["coverage_ranges"].insert(1, deepcopy(overlap["coverage_ranges"][0]))
    expect_rejection(lambda: verify_coverage(overlap))
    fake_full_pdf = deepcopy(pdf)
    fake_full_pdf["coverage_complete"] = True
    expect_rejection(lambda: verify_coverage(fake_full_pdf))
    expect_rejection(lambda: local_path("../outside-root"))
    expect_rejection(lambda: verify_hash(rfc["raw_path"], "0" * 64))
    report = {"status": "pass", "checked_at": datetime.now(timezone.utc).isoformat(),
              "retrieval_records": len(manifest), "unique_files_checked": len(checked),
              "full_text_sources": 4, "rfc9528_lf_lines": 4671, "coverage_chunks": chunks,
              "figures": 13, "tables": 15, "selected_pdf_pages_reviewed": 25,
              "total_pdf_pages": 82, "negative_self_checks": 6,
              "scope": "Archival hashes and declared coverage consistency only; no crypto, controller, hardware or conformance execution."}
    (BASE / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
