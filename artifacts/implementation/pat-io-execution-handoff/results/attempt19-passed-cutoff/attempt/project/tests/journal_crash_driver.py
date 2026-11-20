"""Subprocess-only synthetic crash fixture. No hardware or transport I/O."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hms.journal import Journal
from journal_support import CONTEXT, TestPolicy, evidence, request

path, phase = sys.argv[1:3]
root = Path(path).parent
journal = Journal(path, TestPolicy(), clock_ms=lambda: 1000, create=True)
namespace = journal.issue_namespace(CONTEXT, 3000)["token"]
wire = request(namespace)
(root / "request.json").write_bytes(wire)
op = journal.submit(CONTEXT, wire)
(root / "operation.txt").write_text(op["id"])
if phase == "accepted":
    os._exit(31)
ticket = journal.claim_dispatch(op["id"])
if phase == "dispatching":
    os._exit(32)
# This file is a separately persisted synthetic effect counter.
with (root / "effect.json").open("w") as output:
    output.write(json.dumps({"syntheticEffectCount": 1}))
    output.flush()
    os.fsync(output.fileno())
if phase == "effect_before_receipt":
    os._exit(33)
journal.record_execution(ticket, "completed", evidence("completed"))
os._exit(34)
