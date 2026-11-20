"""Original design-boundary probes against the frozen baseline, not procedures.

Only the existing Python Journal, its pinned JSON canonicalizer, and SQLite run.
No acquired controller, Bluesky, LabOP, model, endpoint, or hardware executes.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import types

BASE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
package = types.ModuleType("procedure_review_baseline")
package.__path__ = [str(BASE / "sources/hms")]
sys.modules[package.__name__] = package
j = importlib.import_module(package.__name__ + ".journal")
c = importlib.import_module(package.__name__ + ".contracts")


class Policy:
    """Trusted synthetic policy; these probes do not verify registry admission."""
    def authorize(self, context, verb, target):
        pass

    def admit(self, context, intent, now_ms):
        return j.Admission(("resource:" + intent["instanceId"],), "probe:1", 1000)

    def recheck(self, context, operation, now_ms):
        pass

    def evidence(self, operation, evidence):
        if evidence.kind != "simulation" or evidence.source != "probe":
            raise j.JournalError("UNTRUSTED_EVIDENCE")


def envelope(namespace, key, instance="one"):
    return c.canonical({
        "protocol": "hms.invoke/0.1", "replayNamespace": namespace,
        "operationKey": key, "intent": {
            "instanceId": instance, "endpointSession": "session:1",
            "controlGeneration": "control:1", "actionId": "act",
            "descriptionDigest": "sha256:" + "0" * 64,
            "bindingGeneration": "binding:1", "calibrationRevision": "cal:1",
            "arguments": {}, "requiredEffect": "capability_completion",
            "timing": {"notBeforeUnixMs": 100, "latestStartUnixMs": 500,
                       "maxRunMs": 200, "latestCompletionUnixMs": 1000}}})


def expect_error(code, fn):
    try:
        fn()
    except j.JournalError as error:
        assert error.code == code, (code, error.code)
    else:
        raise AssertionError("Expected " + code)


def main():
    pins = json.loads((BASE / "source-pins.json").read_text())
    for pin in pins:
        path = BASE / "sources" / pin["sourcePath"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"], path
    context = j.Context("reviewer", "simulation")
    cases = []
    with tempfile.TemporaryDirectory(prefix="procedure-review-", dir=BASE) as temporary:
        path = Path(temporary) / "journal.sqlite"
        clock = [100]
        journal = j.Journal(path, Policy(), clock_ms=lambda: clock[0], create=True)
        namespace = journal.issue_namespace(context, expires_ms=1100)["token"]
        wire = envelope(namespace, "step-one")
        with journal._transaction():
            expect_error("POLICY_REENTRANCY", lambda: journal.submit(context, wire))
        assert not journal.work_items(("accepted",))
        cases.append({"id": "nested-submit-refused", "result": "PASS",
                      "observed": "POLICY_REENTRANCY; no operation admitted"})

        try:
            with journal._transaction():
                journal._db.execute("INSERT INTO meta VALUES ('probe_business', '1')")
                clock[0] = 101
                journal._now()
        except j.JournalError as error:
            assert error.code == "CLOCK_CHECK_AFTER_MUTATION"
        else:
            raise AssertionError("Expected CLOCK_CHECK_AFTER_MUTATION")
        assert journal._db.execute("SELECT value FROM meta WHERE key='probe_business'").fetchone() is None
        assert int(journal._meta("last_clock")) == 101
        cases.append({"id": "clock-sampling-after-business-write", "result": "PASS",
                      "observed": "Business write rolls back; observed clock floor persists"})

        first = journal.submit(context, wire)
        ticket = journal.claim_dispatch(first["id"])
        first = journal.record_execution(ticket, "completed", j.Evidence(
            "simulation", "probe", "completion:1", ("completed",)))
        assert first["state"] == "completed" and first["claims"] and first["may_have_acted"]
        cases.append({"id": "completion-is-not-quiescence", "result": "PASS",
                      "observed": "Completed child retains resource claims"})

        second = journal.submit(context, envelope(namespace, "step-two", "two"))
        assert second["state"] == "accepted"
        cases.append({"id": "different-resource-does-not-imply-sequence-barrier", "result": "PASS",
                      "observed": "Independent second operation admits despite predecessor held claims"})
        journal.request_cancel(context, second["id"])
        canceled = journal.status(context, second["id"])
        assert canceled["state"] == "canceled" and not canceled["may_have_acted"] and not canceled["claims"]
        cases.append({"id": "accepted-cancel-proves-no-handoff", "result": "PASS",
                      "observed": "Canceled before dispatch; no possible effect; claims released"})

        journal.release_resources(first["id"], j.Evidence(
            "simulation", "probe", "quiet:1", ("resources_quiescent",)))
        journal.dispute(first["id"], j.Evidence(
            "simulation", "probe", "dispute:1", ("disputed",)))
        disputed = journal.status(context, first["id"])
        assert disputed["state"] == "completed" and disputed["verification"] == "disputed" and not disputed["claims"]
        cases.append({"id": "late-dispute-after-resource-release", "result": "PASS",
                      "observed": "Completed and quiescent record can later become disputed"})

        third = journal.submit(context, envelope(namespace, "step-three", "three"))
        journal.claim_dispatch(third["id"])
        journal.close()
        journal = j.Journal(path, Policy(), clock_ms=lambda: clock[0])
        unknown = journal.status(context, third["id"])
        assert unknown["state"] == "outcome_unknown" and unknown["claims"] and unknown["may_have_acted"]
        assert journal.submit(context, envelope(namespace, "step-three", "three"))["id"] == third["id"]
        cases.append({"id": "restart-preserves-unknown-id-and-claims", "result": "PASS",
                      "observed": "Reopen marks handed-off operation unknown; exact replay returns original ID"})

        clock[0] = 1101
        journal.prune_expired_namespaces(context)
        assert journal._db.execute("SELECT COUNT(*) FROM replay_keys").fetchone()[0] == 0
        assert journal.status(context, third["id"])["state"] == "outcome_unknown"
        assert journal.status(context, first["id"])["verification"] == "disputed"
        cases.append({"id": "pruning-separates-key-retention-from-execution-history", "result": "PASS",
                      "observed": "Replay keys deleted; operation IDs, evidence and unresolved claims survive"})
        assert journal._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        journal.close()
    receipt = {
        "scope": "Original deterministic design-boundary probes against frozen baseline315 Journal; not tests of the new procedure implementation",
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
        "cases": cases, "tests": len(cases), "failures": 0,
        "sourcePins": "source-pins.json",
        "executedAcquiredControllersModelsHardwareOrMCU": False,
        "limitations": ["Permissive original synthetic policy; registry/current authorization behavior is source-reviewed, not verified by these probes",
                        "No subprocess crashes, power-loss simulation or native adapter execution in these probes",
                        "No procedure implementation exists in the frozen baseline; these results justify required seams, not conformance"]}
    (BASE / "baseline-probes.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"tests": len(cases), "failures": 0, "receipt": str(BASE / "baseline-probes.json")}))


if __name__ == "__main__":
    main()
