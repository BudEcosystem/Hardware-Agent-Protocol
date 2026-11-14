"""The packaged requirement index equals spec/bhms/14-conformance.md, and the vectors are well-formed."""

from __future__ import annotations

import json
from pathlib import Path

from bhms.conformance import requirements
from bhms.conformance.checks._util import vectors

SPEC = Path(__file__).resolve().parents[3] / "spec" / "bhms"


def test_packaged_index_equals_the_specification():
    rows = requirements.parse_index((SPEC / "14-conformance.md").read_text())
    assert [dict(r) for r in requirements.load()] == rows
    assert len(rows) == 257


def test_index_rows_are_well_formed():
    for row in requirements.load():
        assert row["level"] in {"MUST", "SHOULD", "MAY"}
        assert row["method"] in {"schema", "wire", "fault", "transport", "compact", "agent", "inspection"}
        assert row["id"].startswith("BHMS-") and row["summary"] and row["test"]


def test_vector_files_load_and_reference_known_requirements():
    known = {row["id"] for row in requirements.load()}
    malformed = vectors("malformed")["vectors"]
    assert len(malformed) >= 15
    for vec in malformed:
        assert set(vec["ids"]) <= known, vec["name"]
        assert vec["expect"]["rpcCodes"]
    arguments = vectors("arguments")
    assert len(arguments["refused"]) >= 20 and arguments["accepted"]
    programs = vectors("programs")
    assert len(programs["invalid"]) >= 15
    for case in programs["invalid"]:
        assert set(case["ids"]) <= known, case["name"]
    canonical = vectors("canonical")["vectors"]
    for vec in canonical:
        assert json.dumps(vec["value"]) is not None and vec["digest"].startswith("sha256:")
