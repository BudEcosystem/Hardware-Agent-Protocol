#!/usr/bin/env python3
"""Audit retained OPC reference evidence; execute no acquired source or service."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "research/industrial-opcua"
checks = 0
files = set()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def local(path):
    result = (ROOT / path).resolve()
    require(result.is_relative_to(BASE), f"Out-of-lane path: {path}")
    return result


def verify(path, expected, size=None):
    global checks
    resolved = local(path)
    data = resolved.read_bytes()
    require(digest(data) == expected, f"Hash mismatch: {path}")
    if size is not None:
        require(len(data) == size, f"Size mismatch: {path}")
    checks += 1
    files.add(resolved)
    return data


def lf_lines(data):
    split = data.split(b"\n")
    return [line + b"\n" for line in split[:-1]] + ([split[-1]] if split[-1] else [])


def read_json(name):
    return json.loads((BASE / name).read_text())


def uncovered_ranges(count, covered):
    result, start = [], None
    for i in range(1, count + 2):
        if i <= count and i not in covered:
            if start is None:
                start = i
        elif start is not None:
            result.append([start, i - 1])
            start = None
    return result


manifest = [json.loads(line) for line in (BASE / "manifest.jsonl").read_text().splitlines()]
require(len(manifest) == 8, "Expected eight acquired primary-source exports/pages")
by_id = {item["id"]: item for item in manifest}
require(len(by_id) == len(manifest), "Duplicate acquisition id")
for item in manifest:
    require(item["status"] == "acquired", "Unexpected acquisition status")
    data = verify(item["raw_path"], item["sha256"], item["bytes"])
    if item.get("text_path"):
        text = verify(item["text_path"], item["text_sha256"])
        if item["id"].endswith("-markdown"):
            require(text == data, "Markdown text copy is not byte-identical")

receipt = read_json("reading-opcua-full.json")
require(receipt["path_base"] == "repository_root", "Unexpected path convention")
require(len(receipt["sources"]) == 4, "Unexpected reading source count")
coverage, chunks = {}, 0
for item in receipt["sources"]:
    source = by_id[item["id"]]
    require(item["raw_path"] == source["raw_path"], "Reading raw path drift")
    require(item["text_path"] == source["text_path"], "Reading text path drift")
    verify(item["raw_path"], item["raw_sha256"])
    data = verify(item["text_path"], item["text_sha256"], item["text_bytes"])
    lines = lf_lines(data)
    require(len(lines) == item["line_count"], "Incorrect LF count")
    covered = set()
    previous_end = 0
    for chunk in item["coverage_ranges"]:
        start, end = chunk["start_line"], chunk["end_line"]
        require(previous_end < start <= end <= len(lines), "Invalid/overlapping reading interval")
        previous_end = end
        data = b"".join(lines[start - 1:end])
        require(len(data) == chunk["bytes"] and digest(data) == chunk["sha256"], "Chunk hash/size mismatch")
        require(chunk["status"] == "read_untruncated", "Unfinished reading chunk")
        covered.update(range(start, end + 1))
        chunks += 1
    require(len(covered) == item["read_line_count"], "Read-line count mismatch")
    full = covered == set(range(1, len(lines) + 1))
    require(full == item["coverage_complete"], "False full/selected reading scope")
    require(item["coverage_gaps"] == uncovered_ranges(len(lines), covered), "Incorrect unread gaps")
    require((item["reading_status"] == "read_full") == full, "Reading status contradicts coverage")
    coverage[item["id"]] = (lines, covered)

sections = read_json("metadata/selected-sections.json")
require(len(sections) == 22, "Unexpected selected section count")
source_lines, covered = coverage["part4-markdown"]
headings = []
for index, line in enumerate(source_lines, 1):
    match = re.match(rb"^(\d+(?:\.\d+)*) ([A-Z][^\r\n]*)\r?\n?$", line)
    if match:
        headings.append((index, match[1].decode(), match[2].decode()))
section_lines = set()
for item in sections:
    require(item["source_path"] == by_id["part4-markdown"]["text_path"], "Section source mismatch")
    start, end = item["start_line"], item["end_line"]
    selected = set(range(start, end + 1))
    require(selected <= covered, "Selected section not fully covered by reading receipt")
    require(not selected & section_lines, "Overlapping selected sections")
    section_lines |= selected
    data = verify(item["path"], item["sha256"], item["bytes"])
    require(data == b"".join(source_lines[start - 1:end]), "Section is not exact source slice")
    require(data.startswith((item["section"] + " " + item["title"]).encode()), "Incorrect section heading")
    depth = item["section"].count(".")
    next_heading = next((line for line, number, _ in headings
                         if line > start and number.count(".") <= depth), len(source_lines) + 1)
    require(end == next_heading - 1, "Claimed complete section omits text before next peer heading")
    require(item["reading_status"] == "read_complete_selected_section", "Unread selected section")

figures = read_json("figure-manifest.json")
require(len(figures["figures"]) == 31, "Unexpected figure count")
figures_by_part = {"4": [], "10": []}
for item in figures["figures"]:
    verify(item["path"], item["sha256"], item["bytes"])
    require(item["reading_status"] == "visually_reviewed_full_asset", "Unreviewed figure")
    require(item["sha256"] + ".png" in item["url"], "Figure URL/content hash mismatch")
    require(item["source_html"] == by_id[f"part{item['part']}-full-html"]["raw_path"], "Figure HTML source drift")
    figures_by_part[item["part"]].append(item["figure_id"])

xml = ET.fromstring(local(by_id["part10-sts-xml"]["raw_path"]).read_bytes())
xml_figures = {node.attrib["id"] for node in xml.iter("fig")}
require(xml_figures == set(figures_by_part["10"]), "Not all available Part10 XML figures retained")
missing_ids = {"fig_3_program-states-and-transitions", "fig_11_sequence-of-operations"}
refs = {node.attrib.get("rid") for node in xml.iter("xref")}
require(missing_ids <= refs and not missing_ids & xml_figures, "Missing-figure provenance changed")
require(len(figures["unavailable_referenced_figures"]) == 2, "Missing-figure disclosure absent")

metadata_paths = [BASE / "manifest.jsonl", BASE / "reading-opcua-full.json", BASE / "figure-manifest.json"]
metadata_paths += sorted((BASE / "metadata").glob("*.json"))
metadata_paths += [Path(__file__).resolve(), BASE / "README.md"]
metadata_paths += [ROOT / "docs/opcua-binding.md"]
metadata = [{"path": str(path.relative_to(ROOT)), "sha256": digest(path.read_bytes())} for path in metadata_paths]
result = {
    "passed": True,
    "command": "python3 research/industrial-opcua/audit_opcua.py",
    "scope": "Retained primary-reference bytes, selected-section slices, reader-asserted LF chunk coverage, figure assets and absent-figure structural evidence. No device, acquired code, conformance or physical-safety test.",
    "acquisition_records": len(manifest),
    "repository_pins": 0,
    "file_hash_checks": checks,
    "unique_verified_files": len(files),
    "reading_sources": len(receipt["sources"]),
    "reading_full_text_sources": sum(item["coverage_complete"] for item in receipt["sources"]),
    "reading_partial_text_sources": sum(not item["coverage_complete"] for item in receipt["sources"]),
    "reading_chunk_hashes": chunks,
    "part4_read_lines": len(coverage["part4-markdown"][1]),
    "part4_total_lines": len(coverage["part4-markdown"][0]),
    "part4_complete_selected_sections": len(sections),
    "part4_selected_section_lines": len(section_lines),
    "part10_available_text_lines": len(coverage["part10-markdown"][0]),
    "figures_visually_reviewed": {part: len(ids) for part, ids in figures_by_part.items()},
    "part10_referenced_figures_unavailable": 2,
    "metadata_hashes": metadata,
}
print(json.dumps(result, indent=2))
