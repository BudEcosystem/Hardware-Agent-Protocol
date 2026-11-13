#!/usr/bin/env python3
"""Check retained LwM2M evidence. Executes no acquired code and uses no network."""

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "research/constrained/lwm2m-current"
READING = ROOT / "research/constrained/reading-lwm2m-current-full.json"
DOC = ROOT / "docs/lwm2m-current-binding.md"
checks = 0
verified_files = set()
inputs = set()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local(path):
    require(not Path(path).is_absolute(), f"Expected repository-relative path: {path}")
    resolved = (ROOT / path).resolve()
    require(resolved.is_relative_to(BASE) or resolved in {READING, DOC},
            f"Out-of-scope path: {path}")
    return resolved


def read(path):
    resolved = local(path)
    inputs.add(resolved)
    return resolved.read_bytes()


def verify(path, expected, size=None):
    global checks
    data = read(path)
    require(digest(data) == expected, f"Hash mismatch: {path}")
    if size is not None:
        require(len(data) == size, f"Size mismatch: {path}")
    verified_files.add(local(path))
    checks += 1
    return data


def read_json(path):
    return json.loads(read(str(path.relative_to(ROOT))))


def lf_lines(data):
    split = data.split(b"\n")
    return [line + b"\n" for line in split[:-1]] + ([split[-1]] if split[-1] else [])


class ImageList(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            self.sources.append(dict(attrs).get("src"))


def main():
    manifest = [json.loads(line) for line in read(
        "research/constrained/lwm2m-current/manifest.jsonl").splitlines()]
    require(len(manifest) == 12, "Expected twelve acquired sources/renditions")
    by_id = {item["id"]: item for item in manifest}
    require(len(by_id) == len(manifest), "Duplicate acquisition id")
    for item in manifest:
        require(item["status"] == "acquired" and item["http_status"] == 200,
                "Unsuccessful acquisition")
        verify(item["raw_path"], item["sha256"], item["bytes"])
        verify(item["text_path"], item["text_sha256"], item["text_bytes"])

    receipt = read_json(READING)
    require(len(receipt["sources"]) == 9, "Expected nine complete text readings")
    read_ids = {item["id"] for item in receipt["sources"]}
    require(len(read_ids) == 9 and not any(name.endswith("-pdf") for name in read_ids),
            "Duplicate source or false PDF full-reading claim")
    require({item["id"] for item in receipt["unread_text_renditions"]}
            == {"core-122-pdf", "transport-122-pdf", "release-122-pdf"},
            "Missing disclosure of unread PDF text renditions")
    chunks = 0
    total_lines = 0
    actual_ranges = {}
    for item in receipt["sources"]:
        acquired = by_id[item["id"]]
        require(item["raw_path"] == acquired["raw_path"]
                and item["text_path"] == acquired["text_path"], "Reading path drift")
        verify(item["raw_path"], item["raw_sha256"])
        lines = lf_lines(verify(item["text_path"], item["text_sha256"]))
        require(len(lines) == item["line_count"], "Incorrect LF line count")
        cursor = 1
        ranges = []
        for interval in item["coverage_ranges"]:
            start, end = interval["start_line"], interval["end_line"]
            require(start == cursor and start <= end <= len(lines),
                    "Missing, overlapping or invalid full-reading interval")
            require(digest(b"".join(lines[start - 1:end])) == interval["sha256"],
                    "Reading interval hash mismatch")
            ranges.append([start, end])
            cursor = end + 1
            chunks += 1
        require(cursor == len(lines) + 1 and item["coverage_complete"] is True,
                "Full-reading assertion does not cover all archived text")
        total_lines += len(lines)
        actual_ranges[item["id"]] = ranges

    progress = read_json(BASE / "metadata/read-progress.json")
    require(actual_ranges == progress["untruncated_read_ranges"],
            "Reading receipt differs from retained progress intervals")
    require(total_lines == 12771 and chunks == 46, "Unexpected reading totals")
    expected_counts = {
        "full_text_sources": 9, "full_text_lines": 12771, "coverage_ranges": 46,
        "full_specifications": 2, "semantic_figures": 48,
        "reviewed_pdf_page_renders": 42, "acquired_sources": 12,
    }
    require(receipt["counts"] == expected_counts, "Reading count summary drift")

    figures = json.loads(verify(receipt["figure_manifest_path"],
                                receipt["figure_manifest_sha256"]))
    require(len(figures["renders"]) == 42, "Expected forty-two figure page renders")
    expected_figures = {"core": 28, "transport": 20}
    require(figures["semantic_figure_counts"] == expected_figures,
            "Unexpected semantic figure count")
    inventories = {}
    figure_indices = {name: [] for name in expected_figures}
    for document, count in expected_figures.items():
        inventory = read_json(BASE / f"metadata/{document}-images.json")
        parser = ImageList()
        parser.feed(read(by_id[f"{document}-122-html"]["raw_path"]).decode("utf-8"))
        require([item["src"] for item in inventory] == parser.sources,
                "HTML image inventory differs from archived raw HTML")
        require(len(inventory) == count + 1 and not inventory[0]["parent_text"],
                "Missing semantic figure or changed decorative-logo exclusion")
        inventories[document] = inventory

    page_keys = set()
    for item in figures["renders"]:
        document, page = item["document"], item["pdf_page_one_based"]
        require((document, page) not in page_keys, "Duplicate rendered page")
        page_keys.add((document, page))
        data = verify(item["path"], item["sha256"], item["bytes"])
        require(data.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid PNG signature")
        source = by_id[f"{document}-122-pdf"]
        require(item["source_pdf"] == source["raw_path"], "Wrong source PDF")
        verify(item["source_pdf"], item["source_pdf_sha256"])
        require(item["reading_status"] == "visually_reviewed_full_rendered_page"
                and item["review_note"], "Missing figure review assertion")
        require(Path(item["path"]).name in progress["figures_visually_reviewed"],
                "Figure absent from reading progress")
        require(item["captions"] == [inventories[document][index]["parent_text"]
                                     for index in item["figure_indices"]],
                "Figure caption/inventory mismatch")
        figure_indices[document].extend(item["figure_indices"])
    for document, count in expected_figures.items():
        require(sorted(figure_indices[document]) == list(range(1, count + 1)),
                "Not every semantic figure reviewed exactly once")
    require(sum(doc == "core" for doc, _ in page_keys) == 25
            and sum(doc == "transport" for doc, _ in page_keys) == 17,
            "Incorrect figure-page distribution")

    marker = b"No commit found for the ref v1_2-dev"
    for source_id in ["core-122-html", "core-122-pdf"]:
        require(marker in read(by_id[source_id]["text_path"]),
                "Missing-appendix provenance changed")
    status = read_json(BASE / "metadata/version-status.json")
    require(status["current_approved_baseline"]["version"] == "1.2.2"
            and status["current_approved_baseline"]["approved_date"] == "2024-06-13",
            "Baseline/version drift")
    require(len(status["source_pins"]) == 12, "Incomplete status-source pins")
    for pin in status["source_pins"]:
        acquired = by_id[pin["id"]]
        require(pin["raw_path"] == acquired["raw_path"]
                and pin["raw_sha256"] == acquired["sha256"]
                and pin["text_path"] == acquired["text_path"]
                and pin["text_sha256"] == acquired["text_sha256"],
                "Status-source pin mismatch")

    read(str(DOC.relative_to(ROOT)))
    read(str(Path(__file__).resolve().relative_to(ROOT)))
    hashes = [{"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())}
              for path in sorted(inputs)]
    metadata = [item for item in hashes if local(item["path"]) not in verified_files]
    result = {
        "passed": True,
        "command": "python3 -I -B research/constrained/lwm2m-current/audit_lwm2m_current.py",
        "scope": "Retained primary-source/rendition bytes, reader-asserted complete LF coverage, "
                 "HTML semantic-figure inventory, reader-asserted PDF figure reviews, "
                 "missing-appendix evidence and exact input hashes. Mechanical integrity "
                 "checks cannot establish human comprehension, normative conformance, "
                 "interoperability or physical safety.",
        "acquisition_records": len(manifest),
        "repository_pins": 0,
        "file_hash_checks": checks,
        "unique_verified_files": len(verified_files),
        "reading_sources": len(read_ids),
        "reading_full_text_sources": len(read_ids),
        "reading_partial_text_sources": 0,
        "reading_chunk_hashes": chunks,
        "reading_lines": total_lines,
        "full_specifications": [
            {"id": "core-122-html", "lines": 7896, "appendices": "A-M available text", "pdf_pages": 156},
            {"id": "transport-122-html", "lines": 3876, "appendices": "A-D", "pdf_pages": 110},
        ],
        "semantic_figures_visually_reviewed": expected_figures,
        "reviewed_pdf_page_renders": 42,
        "unread_pdf_text_renditions": 3,
        "publication_gap": "Core Appendix K is a missing-revision placeholder in both official exports; "
                           "separate v1.0.1 and v1.1 XSDs were read, not substituted into the publication.",
        "input_file_count": len(hashes),
        "input_hashes": hashes,
        "metadata_hashes": metadata,
        "limitations": [
            "Complete published available HTML text and semantic figures, not every PDF page visually reviewed.",
            "No full baseline diff, full Git commit/repository pin, or linked bibliography full-reading claim.",
            "No acquired code, examples, XML compiler, device, broker or network-service execution.",
            "No RAM, flash, deadline, watchdog, firmware activation or physical-stop measurements.",
            "Observed publication conflicts are analyst findings, not approved errata.",
        ],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
