from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from hms.journal import Context, Evidence, Journal, JournalError
from journal_support import CONTEXT, TestPolicy, evidence, request


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "journal.db"
        self.now = 1000
        self.policy = TestPolicy()
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.now, create=True)
        self.namespace = self.journal.issue_namespace(CONTEXT, 3000)["token"]
        self.wire = request(self.namespace)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def assert_code(self, code, fn, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def submit(self):
        return self.journal.submit(CONTEXT, self.wire)

    def reopen(self):
        self.journal.close()
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.now)

    def test_duplicate_before_fresh_admission_and_authorized_conflict(self):
        op = self.submit()
        self.policy.denied.add("invoke")
        self.assertEqual(self.submit()["id"], op["id"])
        self.assertEqual(self.policy.admissions, 1)
        changed = json.loads(self.wire)
        changed["intent"]["arguments"]["distance"] = 6
        self.assert_code("KEY_CONFLICT", self.journal.submit, CONTEXT, json.dumps(changed).encode())
        self.policy.denied.add("read")
        self.assert_code("ACCESS_DENIED", self.journal.submit, CONTEXT, json.dumps(changed).encode())

    def test_concurrent_duplicate_one_operation_and_one_admission(self):
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(lambda _: self.submit()["id"], range(24)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self.policy.admissions, 1)
        self.assertEqual(self.journal.events(CONTEXT, results[0])["head"], 1)

    def test_principal_and_deployment_isolation(self):
        op = self.submit()
        for context in [Context("other", CONTEXT.deployment), Context(CONTEXT.principal, "other")]:
            self.assert_code("INVALID_REPLAY_NAMESPACE", self.journal.submit, context, self.wire)
            self.assert_code("ACCESS_DENIED", self.journal.status, context, op["id"])

    def test_expiry_floor_purge_restart_and_unknown_effect_retention(self):
        early = self.journal.issue_namespace(CONTEXT, 3000)["token"]
        later = self.journal.issue_namespace(CONTEXT, 4000)["token"]
        op = self.journal.submit(CONTEXT, request(early))
        self.journal.claim_dispatch(op["id"])
        self.now = 3000
        self.assertEqual(self.journal.submit(CONTEXT, request(early))["id"], op["id"])
        self.assert_code("EXPIRED_REPLAY_NAMESPACE", self.journal.submit, CONTEXT, request(early, "new"))
        self.assertEqual(self.journal.prune_expired_namespaces(CONTEXT), 2)
        self.reopen()
        self.assert_code("INVALID_REPLAY_NAMESPACE", self.journal.submit, CONTEXT, request(early))
        current = self.journal.status(CONTEXT, op["id"])
        self.assertEqual(current["state"], "outcome_unknown")
        self.assertEqual(len(current["claims"]), 1)
        later_wire = request(later, timing={"notBeforeUnixMs": 3000, "latestStartUnixMs": 3500,
                                          "maxRunMs": 100, "latestCompletionUnixMs": 3800})
        self.policy.lease_expires_ms = 3600
        self.assert_code("RESOURCE_BUSY", self.journal.submit, CONTEXT, later_wire)
        self.assertEqual(self.journal._db.execute("SELECT floor FROM series").fetchone()[0], 3)

    def test_namespace_forgery_and_expiry_order(self):
        self.assert_code("NAMESPACE_ORDER", self.journal.issue_namespace, CONTEXT, 2999)
        self.assert_code("INVALID_REPLAY_NAMESPACE", self.journal.submit, CONTEXT, request(self.namespace[:-1] + "z"))

    def test_transaction_rollback_admission_and_fence_allocation(self):
        original = self.journal._event
        def fail(*_):
            raise OSError("synthetic journal write failure")
        self.journal._event = fail
        with self.assertRaises(OSError):
            self.submit()
        for table in ("operations", "claims", "replay_keys", "resource_floors", "events"):
            self.assertEqual(self.journal._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.journal._event = original
        self.assertEqual(self.submit()["claims"][0]["fence"], 1)

    def test_conflicting_resources_and_fence_monotonicity(self):
        op = self.submit()
        self.assert_code("RESOURCE_BUSY", self.journal.submit, CONTEXT, request(self.namespace, "second"))
        self.journal.request_cancel(CONTEXT, op["id"])
        second = self.journal.submit(CONTEXT, request(self.namespace, "second"))
        self.assertEqual(second["claims"][0]["fence"], 2)

    def test_dispatch_rechecks_binding_and_refuses_early_or_expired(self):
        self.wire = request(self.namespace, timing={"notBeforeUnixMs": 1100, "latestStartUnixMs": 2000,
                                                  "maxRunMs": 100, "latestCompletionUnixMs": 2500})
        op = self.submit()
        self.assert_code("NOT_YET_STARTABLE", self.journal.claim_dispatch, op["id"])
        self.now = 1100
        self.policy.binding = "binding:2"
        self.assert_code("BINDING_CHANGED", self.journal.claim_dispatch, op["id"])
        self.assertFalse(self.journal.status(CONTEXT, op["id"])["may_have_acted"])
        self.now = 1900
        self.assertIsNone(self.journal.claim_dispatch(op["id"]))
        current = self.journal.status(CONTEXT, op["id"])
        self.assertEqual(current["state"], "rejected_before_dispatch")
        self.assertFalse(current["may_have_acted"])
        self.assertFalse(current["claims"])

    def test_no_redispatch_after_claim_and_recovery_keeps_claims(self):
        op = self.submit()
        ticket = self.journal.claim_dispatch(op["id"])
        self.assert_code("NOT_DISPATCHABLE", self.journal.claim_dispatch, op["id"])
        self.reopen()
        self.assertEqual(self.submit()["state"], "outcome_unknown")
        self.assert_code("STALE_WORKER", self.journal.record_execution, ticket, "completed", evidence("completed"))
        self.assert_code("NOT_DISPATCHABLE", self.journal.claim_dispatch, op["id"])
        recovered = self.journal.reconcile(op["id"], "running", evidence("running"))
        self.assertEqual(len(recovered["claims"]), 1)
        monitor = self.journal.monitoring_ticket(op["id"])
        self.journal.record_execution(monitor, "completed", evidence("completed"))

    def test_cancel_before_dispatch_vs_completion_race(self):
        op = self.submit()
        canceled = self.journal.request_cancel(CONTEXT, op["id"])
        self.assertEqual((canceled["state"], canceled["cancel_state"], canceled["may_have_acted"]),
                         ("canceled", "confirmed", False))
        self.assert_code("NOT_DISPATCHABLE", self.journal.claim_dispatch, op["id"])
        op = self.journal.submit(CONTEXT, request(self.namespace, "second"))
        ticket = self.journal.claim_dispatch(op["id"])
        self.journal.request_cancel(CONTEXT, op["id"])
        self.journal.record_execution(ticket, "completed", evidence("completed"))
        late = self.journal.acknowledge_cancel(ticket, True, evidence("cancel_ack"))
        self.assertEqual((late["state"], late["cancel_state"]), ("completed", "acknowledged"))

    def test_cancel_ack_is_not_termination_and_unknown_needs_reconcile(self):
        op = self.submit()
        ticket = self.journal.claim_dispatch(op["id"])
        self.journal.request_cancel(CONTEXT, op["id"])
        ack = self.journal.acknowledge_cancel(ticket, True, evidence("cancel_ack"))
        self.assertEqual(ack["state"], "dispatching")
        self.journal.mark_unknown(ticket, "lost_reply")
        self.assert_code("RECONCILIATION_REQUIRED", self.journal.record_execution, ticket, "canceled", evidence("terminated"))
        self.assert_code("QUIESCENCE_REQUIRED", self.journal.release_resources, op["id"], evidence("resources_quiescent"))
        final = self.journal.reconcile(op["id"], "canceled", evidence("terminated"))
        self.assertEqual(final["cancel_state"], "confirmed")
        self.assertTrue(final["claims"])
        self.journal.release_resources(op["id"], evidence("resources_quiescent"))

    def test_verification_evidence_and_terminal_history(self):
        self.wire = request(self.namespace, requiredEffect="physical_verified")
        op = self.submit()
        ticket = self.journal.claim_dispatch(op["id"])
        self.assert_code("PHYSICAL_EVIDENCE_REQUIRED", self.journal.record_execution, ticket, "completed", evidence("completed"))
        self.assert_code("PHYSICAL_EVIDENCE_REQUIRED", self.journal.record_execution, ticket, "completed", evidence("completed", "physical_verified"))
        self.assert_code("UNTRUSTED_EVIDENCE", self.journal.record_execution, ticket, "completed",
                         Evidence("sensor", "other", "trace:2", ("completed", "physical_verified")))
        self.journal.record_execution(ticket, "failed", evidence("failed", "verification_failed"))
        self.journal.dispute(op["id"], evidence("disputed"))
        self.assertEqual(self.journal.status(CONTEXT, op["id"])["state"], "failed")
        self.assert_code("INVALID_TRANSITION", self.journal.record_execution, ticket, "completed", evidence("completed"))

    def test_event_pages_are_contiguous_and_bounded(self):
        op = self.submit()
        ticket = self.journal.claim_dispatch(op["id"])
        self.journal.record_execution(ticket, "running", evidence("running"))
        self.journal.record_execution(ticket, "completed", evidence("completed"))
        first = self.journal.events(CONTEXT, op["id"], limit=2)
        second = self.journal.events(CONTEXT, op["id"], after=first["next"], limit=2)
        self.assertEqual([e["sequence"] for e in first["events"] + second["events"]], [1, 2, 3, 4])
        self.assertFalse(first["gap"])
        self.assert_code("INVALID_CURSOR", self.journal.events, CONTEXT, op["id"], after=5)
        self.assert_code("INVALID_CURSOR", self.journal.events, CONTEXT, op["id"], limit=101)

    def test_clock_regression_denies_new_admission_preserves_reads(self):
        op = self.submit()
        self.now = 900
        self.assertEqual(self.submit()["id"], op["id"])
        self.assert_code("CLOCK_REGRESSION", self.journal.issue_namespace, CONTEXT, 4000)
        self.assert_code("CLOCK_REGRESSION", self.journal.claim_dispatch, op["id"])
        canceled = self.journal.request_cancel(CONTEXT, op["id"])
        self.assertEqual(canceled["state"], "canceled")
        self.assertEqual(self.journal.events(CONTEXT, op["id"])["events"][-1]["clock_status"], "regressed_clamped")

    def test_clock_failure_does_not_discard_execution_evidence(self):
        op = self.submit()
        ticket = self.journal.claim_dispatch(op["id"])
        self.journal.clock_ms = lambda: None
        result = self.journal.record_execution(ticket, "completed", evidence("completed"))
        self.assertEqual(result["state"], "completed")
        self.assertEqual(self.journal.events(CONTEXT, op["id"])["events"][-1]["clock_status"], "unavailable_clamped")

    def test_expired_refusal_persists_clock_floor_despite_rollback(self):
        self.now = 3000
        self.assert_code("EXPIRED_REPLAY_NAMESPACE", self.journal.submit, CONTEXT, self.wire)
        self.assertEqual(self.journal._db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0], "3000")
        self.now = 1500
        self.reopen()
        self.assert_code("CLOCK_REGRESSION", self.journal.submit, CONTEXT, self.wire)
        self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)

    def test_event_time_quality_uses_same_clock_sample_as_timestamp(self):
        op = self.submit()
        values = iter([900, 1100])
        self.journal.clock_ms = lambda: next(values)
        self.journal.request_cancel(CONTEXT, op["id"])
        last = self.journal.events(CONTEXT, op["id"])["events"][-1]
        self.assertEqual((last["time_ms"], last["clock_status"]), (1000, "regressed_clamped"))

    def test_mutable_evidence_assertions_rejected(self):
        self.assert_code("INVALID_EVIDENCE", Evidence, "sensor", "test", "test:1", ["completed"])

    def test_policy_callback_mutation_cannot_rewrite_projection(self):
        op = self.submit()
        def recheck(context, snapshot, now):
            snapshot["intent"]["arguments"]["distance"] = 9000
            snapshot["id"] = "op:wrong"
        def check_evidence(snapshot, value):
            snapshot["state"] = "completed"
            snapshot["verification"] = "verified"
            snapshot["id"] = "op:wrong"
        self.policy.recheck = recheck
        self.policy.evidence = check_evidence
        ticket = self.journal.claim_dispatch(op["id"])
        result = self.journal.record_execution(ticket, "completed", evidence("completed"))
        self.assertEqual(result["id"], op["id"])
        self.assertEqual(result["intent"]["arguments"]["distance"], 5)
        self.assertEqual(result["verification"], "unverified")

    def test_final_physical_verification_cannot_use_stale_running_evidence(self):
        self.wire = request(self.namespace, requiredEffect="physical_verified")
        self.policy.evidence = lambda *_: None  # Trusted synthetic verifier fixture.
        op = self.submit()
        ticket = self.journal.claim_dispatch(op["id"])
        running = Evidence("sensor", "synthetic-test-sensor", "test:1", ("running", "physical_verified"))
        self.journal.record_execution(ticket, "running", running)
        self.assert_code("PHYSICAL_EVIDENCE_REQUIRED", self.journal.record_execution, ticket, "completed", evidence("completed"))
        contradictory = Evidence("sensor", "synthetic-test-sensor", "test:2",
                                 ("completed", "physical_verified", "verification_failed"))
        self.assert_code("CONTRADICTORY_VERIFICATION", self.journal.record_execution, ticket, "completed", contradictory)
        complete = Evidence("sensor", "synthetic-test-sensor", "test:3", ("completed", "physical_verified"))
        self.assertEqual(self.journal.record_execution(ticket, "completed", complete)["verification"], "verified")

    def test_owner_exclusion_explicit_creation_and_durability_settings(self):
        self.assert_code("OWNER_BUSY", Journal, self.path, self.policy, clock_ms=lambda: self.now)
        self.assert_code("MISSING_AUTHORITY_DATABASE", Journal, Path(self.temp.name) / "missing.db",
                         self.policy, clock_ms=lambda: self.now)
        self.assertEqual(self.journal._db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        self.assertEqual(self.journal._db.execute("PRAGMA synchronous").fetchone()[0], 3)
        self.assertEqual(self.journal._db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        authority = self.journal.authority_id
        self.reopen()
        self.assertEqual(self.journal.authority_id, authority)

    def test_subprocess_crash_windows(self):
        driver = Path(__file__).with_name("journal_crash_driver.py")
        for phase, expected, effects in [("accepted", "accepted", 0), ("dispatching", "outcome_unknown", 0),
                                          ("effect_before_receipt", "outcome_unknown", 1), ("completed", "completed", 1)]:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                done = subprocess.run([sys.executable, str(driver), str(root / "ledger.db"), phase], capture_output=True, text=True)
                self.assertIn(done.returncode, {31, 32, 33, 34}, done.stderr)
                with Journal(root / "ledger.db", TestPolicy(), clock_ms=lambda: 1000) as journal:
                    result = journal.submit(CONTEXT, (root / "request.json").read_bytes())
                    self.assertEqual(result["state"], expected)
                    self.assertEqual(result["id"], (root / "operation.txt").read_text())
                    self.assertEqual(journal._db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    if expected != "accepted":
                        self.assert_code("NOT_DISPATCHABLE", journal.claim_dispatch, result["id"])
                    effect_file = root / "effect.json"
                    self.assertEqual(json.loads(effect_file.read_text())["syntheticEffectCount"] if effect_file.exists() else 0, effects)

    def test_interrupted_transactions_restore_atomic_state(self):
        driver = Path(__file__).with_name("journal_interruption_driver.py")
        phases = ("submit", "dispatch", "completion", "cancel", "release", "prune")
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                done = subprocess.run([sys.executable, str(driver), str(root / "ledger.db"), phase],
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 73, done.stderr)
                interrupted = json.loads(done.stdout)
                self.assertGreater(interrupted["journal_bytes"], 512)
                self.assertTrue(interrupted["journal_header"].startswith("d9d505f920a163d7"))
                with Journal(root / "ledger.db", TestPolicy(), clock_ms=lambda: 1000) as journal:
                    self.assertEqual(journal._db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    counts = {table: journal._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                              for table in ("operations", "claims", "replay_keys", "resource_floors", "events", "namespaces")}
                    self.assertEqual(counts["namespaces"], 1)
                    self.assertEqual(journal._db.execute("SELECT floor FROM series").fetchone()[0], 1)
                    if phase == "submit":
                        for table in ("operations", "claims", "replay_keys", "resource_floors", "events"):
                            self.assertEqual(counts[table], 0)
                        result = journal.submit(CONTEXT, (root / "request.json").read_bytes())
                        self.assertEqual(result["claims"][0]["fence"], 1)
                        continue
                    result = journal.submit(CONTEXT, (root / "request.json").read_bytes())
                    self.assertEqual(result["id"], (root / "operation.txt").read_text())
                    expected = "outcome_unknown" if phase == "completion" else "completed" if phase == "release" else "accepted"
                    self.assertEqual(result["state"], expected)
                    self.assertEqual(result["may_have_acted"], phase in {"completion", "release"})
                    self.assertEqual(result["claims"], [{"resource": "axis:focus", "fence": 1}])
                    self.assertEqual(counts["operations"], 1)
                    self.assertEqual(counts["claims"], 1)
                    self.assertEqual(counts["replay_keys"], 1)
                    self.assertEqual(counts["resource_floors"], 1)
                    kinds = [event["kind"] for event in journal.events(CONTEXT, result["id"])["events"]]
                    expected_kinds = ["accepted"]
                    if phase in {"completion", "release"}:
                        expected_kinds += ["dispatch_claimed", "recovery_unknown" if phase == "completion" else "execution_evidence"]
                    self.assertEqual(kinds, expected_kinds)

    def test_late_receipt_refusal_retains_observed_clock_floor(self):
        operation = self.submit()
        ticket = self.journal.claim_dispatch(operation["id"])
        self.journal.record_execution(ticket, "completed", evidence("completed"))
        self.journal.release_resources(operation["id"], evidence("resources_quiescent"))
        head = self.journal.events(CONTEXT, operation["id"])["head"]
        self.now = 3000
        self.assert_code("INVALID_TRANSITION", self.journal.record_execution,
                         ticket, "completed", evidence("completed"))
        self.assertEqual(self.journal.events(CONTEXT, operation["id"])["head"], head)
        self.assertEqual(self.journal._db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0], "3000")
        self.now = 1500
        self.reopen()
        self.assert_code("CLOCK_REGRESSION", self.journal.submit,
                         CONTEXT, request(self.namespace, "second"))
        self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 1)
