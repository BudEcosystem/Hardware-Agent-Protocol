"""Durable procedure authority tests; synthetic policy and local simulation only."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hms.contracts import ContractError, canonical
from hms.journal import Admission, Context, Journal, JournalError
from hms.procedures import ProcedureStore, parse_procedure
from hms.runtime import Runtime
from journal_support import CONTEXT, TestPolicy, evidence, request


class ProcedurePolicy(TestPolicy):
    """Original policy exercises callbacks without pretending physical evidence."""
    def __init__(self):
        super().__init__()
        self.procedure_guard = None
        self.lease_expires_ms = 2500
        self.ready = True
        self.static_checks = 0

    def validate_bound(self, context, intent, now_ms):
        self.static_checks += 1
        self.authorize(context, "invoke", intent["instanceId"])
        self.authorize(context, "read", intent["instanceId"])
        self._validate(intent)

    def admit(self, context, intent, now_ms):
        self.validate_bound(context, intent, now_ms)
        if not self.ready:
            raise JournalError("PRECONDITION_FAILED")
        self.admissions += 1
        return Admission(("resource:" + intent["instanceId"],), "test-policy:1", self.lease_expires_ms)

    def recheck(self, context, operation, now_ms):
        if self.procedure_guard:
            self.procedure_guard(context, operation, now_ms)
        self.validate_bound(context, operation["intent"], now_ms)
        if not self.ready:
            raise JournalError("PRECONDITION_FAILED")


def document(namespace, count=2, key="procedure-key"):
    return {"protocol": "hms.procedure/0.1", "replayNamespace": namespace, "procedureKey": key,
            "procedure": {"profile": "hms.bound-sequence/0.1",
                "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 2000, "latestCompletionUnixMs": 2500},
                "steps": [{"stepId": "step:" + str(i), "request": json.loads(request(namespace, key + ":child:" + str(i),
                    instanceId="sim:instance:" + str(i)))} for i in range(count)]}}


def _crash_worker(directory, phase):
    """Called only by original tests, never an acquired executable."""
    root = Path(directory)
    policy = ProcedurePolicy()
    journal = Journal(root / "authority.db", policy, clock_ms=lambda: 1000)
    store = ProcedureStore(journal)
    envelope = json.loads((root / "request.json").read_text())
    journal._db.execute("PRAGMA cache_size=1")
    original = store._event

    def interrupt(procedure_id, now, kind, payload):
        original(procedure_id, now, kind, payload)
        if (phase == "parent_inside" and kind == "accepted") or (phase == "child_inside" and kind == "child_admitted"):
            # Spill many dirty pages inside the *same* transaction to make the
            # rollback recovery exercise storage, not merely process memory.
            journal._db.execute("INSERT INTO crash_spill VALUES (?)", (b"x" * 200000,))
            rollback = Path(str(journal.path) + "-journal")
            header = rollback.read_bytes()[:8]
            assert header != b"\x00" * 8
            (root / "dirty-header.json").write_text(json.dumps({"header": header.hex(), "bytes": rollback.stat().st_size}))
            os._exit(79)

    store._event = interrupt
    if phase == "parent_inside":
        store.submit(CONTEXT, envelope)
    else:
        procedure_id = store.submit(CONTEXT, envelope)["procedureId"]
        if store.status(CONTEXT, procedure_id)["executionState"] == "interrupted":
            store.resume(CONTEXT, procedure_id)
        store.tick()
        if phase == "after_handoff":
            operation_id = store.status(CONTEXT, procedure_id)["steps"][0]["operationId"]
            journal.claim_dispatch(operation_id)
        os._exit(80)
    raise AssertionError("Crash injection did not execute")


class ProcedureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "authority.db"
        self.now = 1000
        self.policy = ProcedurePolicy()
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.now, create=True)
        self.addCleanup(lambda: self.journal.close())
        self.store = ProcedureStore(self.journal)
        self.namespace = self.journal.issue_namespace(CONTEXT, 3000)["token"]
        self.request = document(self.namespace)

    def code(self, expected, fn, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def submit(self):
        self.procedure = self.store.submit(CONTEXT, self.request)["procedureId"]
        return self.procedure

    def status(self):
        return self.store.status(CONTEXT, self.procedure)

    def child(self, ordinal=0):
        return self.status()["steps"][ordinal]["operationId"]

    def finish(self, ordinal=0, release=True):
        operation = self.child(ordinal)
        ticket = self.journal.claim_dispatch(operation)
        self.journal.record_execution(ticket, "completed", evidence("completed"))
        if release:
            self.journal.release_resources(operation, evidence("resources_quiescent"))

    def reopen(self):
        self.journal.close()
        self.policy = ProcedurePolicy()
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.now)
        self.store = ProcedureStore(self.journal)

    def test_plan_reserves_keys_but_no_resources_and_immutable_copy(self):
        self.submit()
        self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM claims").fetchone()[0], 0)
        self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM pr_keys").fetchone()[0], 3)
        self.request["procedure"]["steps"][0]["request"]["intent"]["arguments"]["distance"] = 9
        self.store.tick()
        operation = self.journal.status(CONTEXT, self.child())
        self.assertEqual(operation["intent"]["arguments"]["distance"], 5)

    def test_future_child_cannot_be_invoked_early_and_linked_replay_works(self):
        self.submit()
        future = self.request["procedure"]["steps"][1]["request"]
        self.code("PROCEDURE_KEY_RESERVED", self.journal.submit, CONTEXT, canonical(future))
        self.store.tick()
        first = self.request["procedure"]["steps"][0]["request"]
        self.assertEqual(self.journal.submit(CONTEXT, canonical(first))["id"], self.child())
        self.assertIsNone(self.child(1))

    def test_existing_child_and_parent_key_collisions_are_refused(self):
        self.journal.submit(CONTEXT, canonical(self.request["procedure"]["steps"][1]["request"]))
        self.code("KEY_CONFLICT", self.store.submit, CONTEXT, self.request)
        self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM pr_procedures").fetchone()[0], 0)

    def test_concurrent_replay_has_one_parent_and_conflicts_require_read(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.store.submit(CONTEXT, self.request)["procedureId"], range(24)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(self.policy.static_checks, 2)
        self.policy.denied.add("invoke")
        self.now = 2600
        self.assertEqual(self.store.submit(CONTEXT, self.request)["procedureId"], ids[0])
        changed = copy.deepcopy(self.request)
        changed["procedure"]["steps"][0]["request"]["intent"]["arguments"]["distance"] = 6
        self.code("KEY_CONFLICT", self.store.submit, CONTEXT, changed)
        self.policy.denied.add("read")
        self.code("ACCESS_DENIED", self.store.submit, CONTEXT, changed)

    def test_completed_but_held_predecessor_blocks_different_resource(self):
        self.submit()
        self.store.tick()
        self.finish(release=False)
        self.store.tick()
        self.assertIsNone(self.child(1))
        self.assertEqual(self.status()["cursor"], 0)
        self.journal.release_resources(self.child(), evidence("resources_quiescent"))
        self.store.tick()
        self.assertIsNotNone(self.child(1))
        self.finish(1)
        self.store.tick()
        self.assertEqual((self.status()["executionState"], self.status()["cursor"]), ("completed", 2))

    def test_late_dispute_blocks_accepted_successor_dispatch(self):
        self.submit()
        self.store.tick()
        self.finish()
        self.store.tick()
        second = self.child(1)
        self.journal.dispute(self.child(), evidence("disputed"))
        self.code("PROCEDURE_DEPENDENCY_UNRESOLVED", self.journal.claim_dispatch, second)
        self.store.tick()
        self.assertEqual(self.status()["executionState"], "failed")
        self.assertEqual(self.journal.status(CONTEXT, second)["state"], "accepted")

    def test_late_dispute_visible_after_parent_completion(self):
        self.submit()
        for index in range(2):
            self.store.tick()
            self.finish(index)
        self.store.tick()
        self.journal.dispute(self.child(), evidence("disputed"))
        state = self.status()
        self.assertEqual(state["executionState"], "completed")
        self.assertEqual(state["aggregateVerification"], "disputed")
        self.assertIn(self.child(), state["unresolvedOperations"])

    def test_cancel_after_read_revoke_latches_and_reports_child_denial(self):
        self.submit()
        self.store.tick()
        operation_id = self.child()
        ticket = self.journal.claim_dispatch(operation_id)
        self.journal.record_execution(ticket, "running", evidence("running"))
        self.policy.denied.update({"read", "cancel"})
        result = self.store.cancel(CONTEXT, self.procedure)
        self.assertTrue(result["cancelRequested"])
        self.assertEqual(result["delivery"]["status"], "denied")
        self.assertEqual(result["delivery"]["code"], "ACCESS_DENIED")
        operation = self.journal._operation(operation_id)
        self.assertEqual(operation["cancel_state"], "not_requested")
        self.policy.denied.remove("read")
        # Parent control alone must not bypass the revoked cancel grant after
        # handoff. The operation's own policy still permits its delayed effect.
        self.policy.recheck(CONTEXT, operation, self.now)
        self.journal.record_execution(ticket, "completed", evidence("completed"))
        self.journal.release_resources(operation_id, evidence("resources_quiescent"))
        self.store.tick()
        self.assertIsNone(self.child(1))
        self.assertEqual(self.status()["executionState"], "canceled")

    def test_cancel_accepted_child_proves_no_effect_and_is_idempotent(self):
        self.submit()
        self.store.tick()
        result = self.store.cancel(CONTEXT, self.procedure)
        self.assertEqual(result["delivery"]["status"], "recorded")
        current = self.status()
        self.assertFalse(current["mayHaveActed"])
        self.assertFalse(current["unresolvedOperations"])
        self.assertEqual(current["steps"][0]["executionState"], "canceled")
        self.assertEqual(self.store.cancel(CONTEXT, self.procedure)["delivery"]["status"], "already_terminal")

    def test_owner_isolation_and_owner_cancel_without_future_permissions(self):
        self.submit()
        other = Context("other", CONTEXT.deployment)
        for fn in (self.store.status, self.store.cancel, self.store.resume, self.store.events):
            self.code("ACCESS_DENIED", fn, other, self.procedure)
        self.policy.denied.update({"read", "invoke", "cancel"})
        self.assertEqual(self.store.cancel(CONTEXT, self.procedure)["delivery"]["status"], "no_active_child")

    def test_restart_blocks_accepted_dispatch_until_resume(self):
        self.submit()
        self.store.tick()
        operation = self.child()
        self.reopen()
        self.assertEqual(self.status()["executionState"], "interrupted")
        self.code("PROCEDURE_PAUSED", self.journal.claim_dispatch, operation)
        self.store.resume(CONTEXT, self.procedure)
        self.assertEqual(self.child(), operation)
        self.assertIsNotNone(self.journal.claim_dispatch(operation))

    def test_unknown_child_reconciles_same_id_while_paused(self):
        self.submit()
        self.store.tick()
        operation = self.child()
        self.journal.claim_dispatch(operation)
        self.reopen()
        self.assertEqual(self.status()["steps"][0]["executionState"], "outcome_unknown")
        self.code("PROCEDURE_DEPENDENCY_UNRESOLVED", self.store.resume, CONTEXT, self.procedure)
        self.journal.reconcile(operation, "completed", evidence("completed"))
        self.journal.release_resources(operation, evidence("resources_quiescent"))
        self.store.resume(CONTEXT, self.procedure)
        self.store.tick()
        self.assertEqual(self.child(), operation)
        self.assertIsNotNone(self.child(1))

    def test_resume_rechecks_binding_permission_and_pending_start(self):
        self.submit()
        self.reopen()
        self.policy.binding = "binding:2"
        self.code("BINDING_CHANGED", self.store.resume, CONTEXT, self.procedure)
        self.policy.binding = "binding:1"
        self.policy.denied.add("invoke")
        self.code("ACCESS_DENIED", self.store.resume, CONTEXT, self.procedure)
        self.policy.denied.clear()
        self.now = 2000
        self.code("START_DEADLINE", self.store.resume, CONTEXT, self.procedure)

    def test_parent_deadline_preserves_handed_off_truth_and_claims(self):
        self.submit()
        self.store.tick()
        self.journal.claim_dispatch(self.child())
        self.now = 2500
        self.store.tick()
        current = self.status()
        self.assertEqual(current["executionState"], "expired")
        self.assertTrue(current["mayHaveActed"])
        self.assertEqual(current["steps"][0]["heldResources"], 1)
        self.assertIsNone(self.child(1))

    def test_first_dispatch_cannot_outlive_parent_start_and_paused_expiry_cleans_up(self):
        self.submit()
        self.store.tick()
        operation = self.child()
        self.reopen()
        self.now = 2000
        self.assertIsNone(self.journal.claim_dispatch(operation))
        self.assertEqual(self.journal.status(CONTEXT, operation)["state"], "rejected_before_dispatch")
        self.assertFalse(self.journal.status(CONTEXT, operation)["claims"])

    def test_namespace_pruning_preserves_links_but_forbids_parent_replay(self):
        self.submit()
        self.store.tick()
        operation = self.child()
        self.now = 3000
        self.journal.prune_expired_namespaces(CONTEXT)
        self.code("INVALID_REPLAY_NAMESPACE", self.store.submit, CONTEXT, self.request)
        self.assertEqual(self.child(), operation)
        self.assertEqual(self.journal.status(CONTEXT, operation)["state"], "accepted")

    def test_future_readiness_checked_only_at_actual_admission(self):
        self.policy.ready = False
        self.submit()
        self.policy.ready = True
        self.store.tick()
        self.assertIsNotNone(self.child())
        self.finish()
        self.policy.ready = False
        self.store.tick()
        self.assertEqual(self.status()["executionState"], "failed")
        self.assertEqual(self.status()["reason"], "PRECONDITION_FAILED")
        self.assertTrue(self.status()["mayHaveActed"])
        self.assertIsNone(self.child(1))

    def test_managed_record_failure_rolls_back_child_link_fences_and_claims(self):
        self.submit()
        original = self.store._event
        def fail(procedure_id, now, kind, payload):
            if kind == "child_admitted":
                raise OSError("synthetic procedure write failure")
            return original(procedure_id, now, kind, payload)
        self.store._event = fail
        with self.assertRaisesRegex(OSError, "synthetic"):
            self.store.tick()
        for table in ("operations", "replay_keys", "claims", "resource_floors", "events"):
            self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        self.assertIsNone(self.child())
        self.store._event = original
        self.store.tick()
        self.assertEqual(self.journal.status(CONTEXT, self.child())["claims"][0]["fence"], 1)

    def test_idle_tick_never_samples_clock_or_writes(self):
        changes = self.journal._db.total_changes
        self.journal.clock_ms = lambda: (_ for _ in ()).throw(AssertionError("idle clock"))
        self.store.tick()
        self.assertEqual(self.journal._db.total_changes, changes)

    def test_clock_regression_blocks_new_work_but_not_cancel_or_events(self):
        self.submit()
        self.now = 900
        self.store.tick()
        self.assertIsNone(self.child())
        self.store.cancel(CONTEXT, self.procedure)
        events = self.store.events(CONTEXT, self.procedure)
        self.assertEqual(events["events"][-1]["clock_status"], "regressed_clamped")

    def test_strict_profile_limits_and_window_containment(self):
        changes = []
        for count in (0, 17):
            changes.append(document(self.namespace, count))
        bad = copy.deepcopy(self.request); bad["procedure"]["branch"] = {}; changes.append(bad)
        bad = copy.deepcopy(self.request); bad["procedure"]["steps"][1]["stepId"] = "step:0"; changes.append(bad)
        bad = copy.deepcopy(self.request); bad["procedure"]["steps"][0]["request"]["operationKey"] = "procedure-key"; changes.append(bad)
        bad = copy.deepcopy(self.request); bad["procedure"]["steps"][0]["request"]["intent"]["timing"]["latestStartUnixMs"] = 2100; changes.append(bad)
        bad = copy.deepcopy(self.request); bad["procedure"]["steps"][0]["request"]["intent"]["arguments"]["huge"] = "x" * 65536; changes.append(bad)
        for bad in changes:
            with self.subTest(case=changes.index(bad)), self.assertRaises(ContractError):
                parse_procedure(bad)

    def test_partial_tables_or_missing_version_fail_closed(self):
        self.journal.close()
        for statement, code in [("DROP TABLE pr_events", "INCOMPLETE_PROCEDURE_DATABASE"),
                                ("DELETE FROM pr_meta", "UNSUPPORTED_PROCEDURE_DATABASE")]:
            path = Path(self.temp.name) / (code + ".db")
            policy = ProcedurePolicy()
            journal = Journal(path, policy, clock_ms=lambda: self.now, create=True)
            ProcedureStore(journal)
            journal._db.execute(statement)
            journal.close()
            journal = Journal(path, ProcedurePolicy(), clock_ms=lambda: self.now)
            try:
                self.code(code, ProcedureStore, journal)
            finally:
                journal.close()

    def test_waiting_page_does_not_starve_later_procedures(self):
        for i in range(65):
            envelope = document(self.namespace, 1, "fair:" + str(i))
            if i < 64:
                envelope["procedure"]["timing"]["notBeforeUnixMs"] = 1100
                envelope["procedure"]["steps"][0]["request"]["intent"]["timing"]["notBeforeUnixMs"] = 1100
            last = self.store.submit(CONTEXT, envelope)["procedureId"]
        self.store.tick()
        self.store.tick()
        self.assertIsNotNone(self.store.status(CONTEXT, last)["steps"][0]["operationId"])

    def test_events_are_bounded_and_ordered(self):
        self.submit()
        self.store.tick()
        first = self.store.events(CONTEXT, self.procedure, limit=1)
        self.assertEqual((len(first["events"]), first["next"]), (1, 1))
        rest = self.store.events(CONTEXT, self.procedure, after=first["next"])
        self.assertEqual(rest["next"], rest["head"])
        self.code("INVALID_CURSOR", self.store.events, CONTEXT, self.procedure, after=999)

    def test_sixteen_step_status_is_compact_and_never_copies_arguments(self):
        self.request = document(self.namespace, 16)
        self.submit()
        status = self.status()
        self.assertEqual(status["stepCount"], 16)
        self.assertLess(len(canonical(status)), 16000)
        self.assertTrue(all("request" not in step and "result" not in step for step in status["steps"]))

    def test_abrupt_crashes_preserve_atomic_parent_and_child_boundaries(self):
        self.journal._db.execute("CREATE TABLE crash_spill (data BLOB NOT NULL)")
        root = Path(self.temp.name)
        (root / "request.json").write_bytes(canonical(self.request))
        self.journal.close()
        worker = "import sys; sys.path.insert(0, 'tests'); from test_procedures import _crash_worker; _crash_worker(sys.argv[1], sys.argv[2])"
        for phase in ("parent_inside", "child_inside", "after_child", "after_handoff"):
            result = subprocess.run([sys.executable, "-c", worker, str(root), phase], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 79 if phase.endswith("inside") else 80, result.stderr)
            self.reopen()
            self.assertEqual(self.journal._db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM crash_spill").fetchone()[0], 0)
            count = self.journal._db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
            if phase == "parent_inside":
                self.assertEqual(self.journal._db.execute("SELECT COUNT(*) FROM pr_procedures").fetchone()[0], 0)
                self.assertEqual(count, 0)
            else:
                self.procedure = self.store.submit(CONTEXT, self.request)["procedureId"]
                self.assertEqual(count, 0 if phase == "child_inside" else 1)
                self.assertEqual(self.status()["executionState"], "interrupted")
                if phase == "after_handoff":
                    self.assertEqual(self.status()["steps"][0]["executionState"], "outcome_unknown")
                    self.assertEqual(self.status()["steps"][0]["heldResources"], 1)
            self.journal.close()
        self.assertNotEqual(json.loads((root / "dirty-header.json").read_text())["header"], "0" * 16)


class ProcedureRuntimeTests(unittest.TestCase):
    def test_four_step_sequence_uses_installed_actions_and_checked_status(self):
        with tempfile.TemporaryDirectory() as directory:
            wall = [1000]
            owner = Context("procedure-owner", "simulation:local")
            runtime = Runtime(directory, create=True, owner=owner,
                              wall_clock_ms=lambda: wall[0], monotonic_ms=lambda: wall[0])
            try:
                namespace = runtime.request(owner, "namespace", {"expiresUnixMs": 10000})["token"]
                steps = []
                for i, level in enumerate((12, 81, 0, 37)):
                    child = runtime.request(owner, "prepare", {"instanceId": "sim:home-fan", "actionId": "set_level",
                        "arguments": {"level": level, "unit": "percent"}, "operationKey": "fan:" + str(i),
                        "replayNamespace": namespace, "requiredEffect": "capability_completion",
                        "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                                   "maxRunMs": 500, "latestCompletionUnixMs": 5500}})["request"]
                    steps.append({"stepId": "fan-step:" + str(i), "request": child})
                envelope = {"protocol": "hms.procedure/0.1", "replayNamespace": namespace, "procedureKey": "four-fan-levels",
                    "procedure": {"profile": "hms.bound-sequence/0.1", "timing": {"notBeforeUnixMs": 1000,
                                  "latestStartUnixMs": 5000, "latestCompletionUnixMs": 5500}, "steps": steps}}
                procedure = runtime.request(owner, "procedure_submit", {"request": envelope})
                for _ in range(12):
                    runtime.tick()
                    wall[0] += 100
                current = runtime.request(owner, "procedure_status", {"procedureId": procedure["procedureId"]})
                self.assertEqual(current["executionState"], "completed")
                self.assertEqual(runtime.plant.observe("sim:home-fan")["effectCount"], 4)
                self.assertEqual(runtime.plant.observe("sim:home-fan")["value"], 37)
                replay = runtime.request(owner, "procedure_submit", {"request": envelope})
                self.assertEqual(replay["procedureId"], procedure["procedureId"])
                self.assertEqual(len({step["operationId"] for step in current["steps"]}), 4)
            finally:
                runtime.close()


# These helpers execute the repository's original C simulation fixture; they
# never execute an acquired controller, model, MCU emulator or physical driver.
from test_multi_adapter import MultiHarness as _MultiHarness, installation as _installation


class ProcedureMixedRouteTests(_MultiHarness):
    def test_five_steps_across_local_and_two_native_routes_replay_offline(self):
        local = _installation("procedure-local")
        first = _installation("procedure-native-a", compact=True)
        second = _installation("procedure-native-b", compact=True)
        self.open([local, first, second], create=True)
        selected = [(local, "fan"), (first, "focus"), (second, "inspection"),
                    (first, "fan"), (local, "focus")]
        steps = [{"stepId": "mixed-step:" + str(i), "request": self.prepare(config, role, key="mixed-child:" + str(i))}
                 for i, (config, role) in enumerate(selected)]
        envelope = {"protocol": "hms.procedure/0.1", "replayNamespace": self.namespace, "procedureKey": "mixed-sequence",
                    "procedure": {"profile": "hms.bound-sequence/0.1", "timing": {
                        "notBeforeUnixMs": self.wall, "latestStartUnixMs": self.wall + 3000,
                        "latestCompletionUnixMs": self.wall + 5000}, "steps": steps}}
        parent = self.call("procedure_submit", request=envelope)
        for _ in range(24):
            self.advance(100)
            current = self.call("procedure_status", procedureId=parent["procedureId"])
            if current["executionState"] == "completed":
                break
        self.assertEqual(current["executionState"], "completed", current)
        self.assertEqual(current["cursor"], 5)
        self.assertEqual(self.packet_count(first["adapterId"]), 2)
        self.assertEqual(self.packet_count(second["adapterId"]), 1)
        self.assertEqual(self.endpoints[first["adapterId"]].command(4), 2)
        self.assertEqual(self.endpoints[second["adapterId"]].command(4), 1)
        original_ids = [step["operationId"] for step in current["steps"]]
        self.reopen(online=())
        replay = self.call("procedure_submit", request=envelope)
        self.assertEqual(replay["procedureId"], parent["procedureId"])
        self.assertEqual([step["operationId"] for step in replay["steps"]], original_ids)
        self.assertEqual(replay["executionState"], "completed")
