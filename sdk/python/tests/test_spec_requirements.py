"""Normative requirement IDs in spec/bhms are unique, indexed and referenced consistently."""

from __future__ import annotations

import re
from pathlib import Path

SPEC = Path(__file__).resolve().parents[3] / "spec" / "bhms"
DEFINITION = re.compile(r"\*\*(BHMS-[A-Z]{3,4}-\d{3})\*\*")
REFERENCE = re.compile(r"BHMS-[A-Z]{3,4}-\d{3}")
AREAS = {"LIF", "TRN", "DEV", "OBS", "OPS", "LSE", "AUTH", "PRG", "EVT", "ERR", "CMP", "AGT", "SEC", "CNF"}
METHODS = {"schema", "wire", "fault", "transport", "compact", "agent", "inspection"}
CHAPTERS = sorted(SPEC.glob("[0-9][0-9]-*.md"))
CONFORMANCE = SPEC / "14-conformance.md"


def _definitions() -> list[str]:
    found = []
    for chapter in CHAPTERS:
        text = chapter.read_text()
        if chapter == CONFORMANCE:
            text = text.split("## 14.4 Requirement index", 1)[0]
        found += DEFINITION.findall(text)
    return found


def _index_rows() -> dict[str, list[str]]:
    index = CONFORMANCE.read_text().split("## 14.4 Requirement index", 1)[1]
    rows = {}
    for line in index.splitlines():
        if line.startswith("| BHMS-"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            rows[cells[0]] = cells
    return rows


def test_requirement_ids_are_unique_and_well_formed():
    ids = _definitions()
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})
    assert {i.split("-")[1] for i in ids} == AREAS
    assert len(ids) > 200


def test_every_requirement_is_indexed_with_a_test():
    ids = set(_definitions())
    rows = _index_rows()
    assert set(rows) == ids
    for rid, cells in rows.items():
        _, level, profile, summary, method, test = cells
        assert level in {"MUST", "SHOULD", "MAY"}, rid
        assert method in METHODS, rid
        assert summary and test, rid


def test_every_reference_resolves():
    ids = set(_definitions())
    for path in sorted(SPEC.glob("*.md")) + [SPEC / "examples" / "README.md"]:
        for ref in REFERENCE.findall(path.read_text()):
            assert ref in ids, f"{path.name} references undefined {ref}"


def test_every_example_comment_reference_resolves():
    ids = set(_definitions())
    for path in sorted((SPEC / "examples").glob("*.json")):
        for ref in REFERENCE.findall(path.read_text()):
            assert ref in ids, f"{path.name} references undefined {ref}"
