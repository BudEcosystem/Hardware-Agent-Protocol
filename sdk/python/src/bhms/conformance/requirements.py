"""The requirement index of ``spec/bhms/14-conformance.md`` as data (``requirements.json``, shipped with the package).

``python -m bhms.conformance.requirements --write`` regenerates the JSON from the specification chapter (run it from a
checkout); ``tests/test_conformance_requirements.py`` fails when the two differ, so a runner can never report against a
stale index. Each row: ``id, area, level (MUST|SHOULD|MAY), profile, method, summary, test, since``.

Thread-safety: the loaded index is immutable.
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

ROW = re.compile(r"^\| (BHMS-[A-Z]+-\d{3}) \| (MUST|SHOULD|MAY) \| (\S+) \| (.*) \| (\w+) \| (.*) \|$")


FIRST_VERSION = "2026-11-13"
ADDED = re.compile(r"^### Added in (\d{4}-\d{2}-\d{2})")
ID = re.compile(r"BHMS-[A-Z]+-\d{3}")


def parse_index(text: str) -> list[dict[str, str]]:
    """Rows of the requirement index (section 14.4) of the conformance chapter, each with ``since``: the protocol version
    that introduced it (section 14.6 lists the requirements of every later version; all others date from the first)."""
    index = text.split("## 14.4 Requirement index", 1)[1]
    since: dict[str, str] = {}
    if "## 14.6 " in index:
        version = None
        for line in index.split("## 14.6 ", 1)[1].splitlines():
            if line.startswith("## "):
                break
            added = ADDED.match(line)
            if added:
                version = added.group(1)
            elif line.startswith("### "):
                version = None  # another list (amendments keep the version that introduced the requirement)
            elif version is not None:
                for rid in ID.findall(line):
                    since[rid] = version
    rows = []
    for line in index.splitlines():
        match = ROW.match(line)
        if match:
            rid, level, profile, summary, method, test = match.groups()
            rows.append({"id": rid, "area": rid.split("-")[1], "level": level, "profile": profile, "method": method,
                         "summary": summary, "test": test, "since": since.get(rid, FIRST_VERSION)})
    return rows


@lru_cache(maxsize=1)
def load() -> tuple[dict[str, Any], ...]:
    """The packaged index."""
    return tuple(json.loads(resources.files("bhms.conformance").joinpath("requirements.json").read_text()))


def by_id() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in load()}


def for_profiles(profiles: set[str]) -> list[dict[str, Any]]:
    return [row for row in load() if row["profile"] in profiles]


def _main(argv: list[str]) -> int:
    spec = Path(__file__).resolve().parents[5] / "spec" / "bhms" / "14-conformance.md"
    rows = parse_index(spec.read_text())
    target = Path(__file__).with_name("requirements.json")
    rendered = json.dumps(rows, indent=1, ensure_ascii=False) + "\n"
    if "--write" in argv:
        target.write_text(rendered)
        print(f"wrote {len(rows)} requirements to {target}")
        return 0
    return 0 if target.read_text() == rendered else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
