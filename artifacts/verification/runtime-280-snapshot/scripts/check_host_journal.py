#!/usr/bin/env python3
"""Run host component tests and retain scoped, reproducible verification metadata."""
import datetime
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def main():
    runs = []
    for pattern in ("test_contracts.py", "test_journal.py"):
        stream = io.StringIO()
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern)
        result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        print(stream.getvalue(), end="")
        if not result.wasSuccessful() or result.skipped:
            raise SystemExit(1)
        runs.append({"pattern": pattern, "tests": result.testsRun, "failures": 0, "errors": 0, "skipped": 0})
    paths = [*sorted((ROOT / "hms").rglob("*.py")), ROOT / "hms/_vendor/rfc8785/LICENSE",
             ROOT / "schemas/invoke.schema.json", ROOT / "tests/test_contracts.py",
             ROOT / "tests/test_journal.py", ROOT / "tests/journal_support.py",
             ROOT / "tests/journal_crash_driver.py", ROOT / "tests/fixtures/host-intents.json",
             ROOT / "tests/journal_interruption_driver.py",
             Path(__file__).resolve()]
    artifact = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Original host parser/journal plus pinned canonicalizer; synthetic policy and effects only",
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "sqlite": sqlite3.sqlite_version, "jsonschema": importlib.metadata.version("jsonschema")},
        "runs": runs, "durability_configuration": {"journal_mode": "delete", "synchronous": "extra", "foreign_keys": True},
        "crash_phases": ["accepted", "dispatching", "synthetic_effect_before_receipt", "completed"],
        "interrupted_transaction_phases": ["submit", "dispatch", "completion", "cancel", "release", "namespace_prune"],
        "interrupted_transaction_evidence": "Each case observed a nonzero on-disk SQLite rollback-journal header before abrupt exit; reopened state and integrity were checked",
        "limitations": ["No physical/device or network adapter", "No power-loss/storage fault test",
                        "No production authentication/admission", "No endpoint fencing or stop timing proof"],
        "files": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
    }
    destination = ROOT / "artifacts/verification/host-journal.json"
    destination.write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps({"tests": sum(r["tests"] for r in runs), "artifact": str(destination.relative_to(ROOT))}))


if __name__ == "__main__":
    main()
