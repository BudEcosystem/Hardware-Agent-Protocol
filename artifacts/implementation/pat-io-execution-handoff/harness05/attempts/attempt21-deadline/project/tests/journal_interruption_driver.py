"""Subprocess-only uncommitted SQLite interruption fixture; no physical I/O."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hms.journal import Journal
from journal_support import CONTEXT, TestPolicy, evidence, request


def main(path, phase):
    root = path.parent
    journal = Journal(path, TestPolicy(), clock_ms=lambda: 1000, create=True)
    namespace = journal.issue_namespace(CONTEXT, 3000)["token"]
    wire = request(namespace)
    (root / "request.json").write_bytes(wire)
    operation = None
    ticket = None
    if phase != "submit":
        operation = journal.submit(CONTEXT, wire)
        (root / "operation.txt").write_text(operation["id"])
    if phase in {"completion", "release"}:
        ticket = journal.claim_dispatch(operation["id"])
    if phase == "release":
        journal.record_execution(ticket, "completed", evidence("completed"))

    # Force dirty-page spills so the process dies with a rollback journal on
    # disk, rather than merely losing uncommitted Python/SQLite memory.
    journal._db.execute("PRAGMA cache_size=1")
    journal._db.execute("PRAGMA cache_spill=ON")

    def interrupt():
        rollback = Path(str(path) + "-journal")
        blob = rollback.read_bytes() if rollback.exists() else b""
        record = {"journal_bytes": len(blob), "journal_header": blob[:28].hex()}
        os.write(1, json.dumps(record).encode())
        os._exit(73)

    original_event = journal._event

    def interrupted_event(*args):
        original_event(*args)
        interrupt()  # Event INSERT completed, public transaction has not committed.

    journal._event = interrupted_event
    if phase == "submit":
        journal.submit(CONTEXT, wire)
    elif phase == "dispatch":
        journal.claim_dispatch(operation["id"])
    elif phase == "completion":
        journal.record_execution(ticket, "completed", evidence("completed"))
    elif phase == "cancel":
        journal.request_cancel(CONTEXT, operation["id"])
    elif phase == "release":
        journal.release_resources(operation["id"], evidence("resources_quiescent"))
    elif phase == "prune":
        journal.clock_ms = lambda: 3000

        def before_statement(sql):
            # The floor and replay-key deletes have run; namespace delete and
            # COMMIT have not. All business writes must roll back together.
            if sql.startswith("DELETE FROM namespaces"):
                interrupt()

        journal._db.set_trace_callback(before_statement)
        journal.prune_expired_namespaces(CONTEXT)
    raise RuntimeError("interruption point not reached")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
