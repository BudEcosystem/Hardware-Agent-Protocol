"""Synthetic-controller persistence and local-envelope tests; no physical I/O.

SQLite fault injection checks the simulator's atomic virtual state/receipt model.
These checks do not establish power-loss durability or physical actuation atomicity.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from hms.contracts import ContractError, SAFE_INTEGER, intent_digest
from hms.journal import JournalError
from hms.simulator import SimulatedPlant


PRIMITIVES = {
    "sim:home-fan": ("set_level", {"level": 40, "unit": "percent"}, "fan-control"),
    "sim:microscope": (
        "move_absolute", {"position": 25, "unit": "um", "frame": "sim:microscope"}, "focus-zone"
    ),
    "sim:inspection-cell": ("inspect", {"recipe": 1, "partId": "part-17"}, "cell-zone"),
}


def operation(session, instance="sim:home-fan", *, key="op:first", fence=1):
    action, arguments, role = PRIMITIVES[instance]
    intent = {
        "instanceId": instance,
        "actionId": action,
        "endpointSession": session,
        "controlGeneration": "sim-control:1",
        "descriptionDigest": "sha256:" + "a" * 64,
        "bindingGeneration": "sim-binding:1",
        "calibrationRevision": "synthetic:1",
        "arguments": copy.deepcopy(arguments),
        "timing": {
            "notBeforeUnixMs": 1000,
            "latestStartUnixMs": 2000,
            "maxRunMs": 500,
            "latestCompletionUnixMs": 2500,
        },
        "requiredEffect": "capability_completion",
    }
    return {
        "id": key,
        "digest": intent_digest(intent),
        "intent": intent,
        "claims": [{"resource": instance + ":" + role, "fence": fence}],
    }


def rehash(op):
    op["digest"] = intent_digest(op["intent"])
    return op


class SimulatedPlantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "plant.db"
        self.plant = SimulatedPlant(self.path, create=True)

    def tearDown(self):
        self.plant.close()
        self.temp.cleanup()

    def reopen(self):
        self.plant.close()
        self.plant = SimulatedPlant(self.path)

    def assert_code(self, code, fn, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_all_installed_operations_persist_one_effect_with_retries(self):
        receipts = {}
        for instance in PRIMITIVES:
            with self.subTest(instance=instance):
                op = operation(self.plant.session, instance, key="op:" + instance)
                pending = self.plant.begin(op)
                self.assertEqual(pending["state"], "pending")
                self.assertEqual(self.plant.observe(instance)["effectCount"], 0)
                done = self.plant.finish(op["id"])
                self.assertEqual(done["state"], "completed")
                self.assertTrue(done["result"]["effectCommitted"])
                self.assertEqual(self.plant.begin(copy.deepcopy(op)), done)
                self.assertEqual(self.plant.finish(op["id"]), done)
                self.assertEqual(self.plant.observe(instance)["effectCount"], 1)
                receipts[instance] = (op, done)
        self.assertEqual(receipts["sim:home-fan"][1]["result"],
                         {"level": 40, "unit": "percent", "effectCommitted": True})
        self.assertEqual(receipts["sim:microscope"][1]["result"],
                         {"position": 25, "unit": "um", "frame": "sim:microscope", "effectCommitted": True})
        self.assertEqual(receipts["sim:inspection-cell"][1]["result"],
                         {"partId": "part-17", "recipe": 1, "inspection": "simulated-pass", "count": 1,
                          "effectCommitted": True})
        session = self.plant.session
        self.reopen()
        self.assertEqual(self.plant.session, session)
        for instance, (op, done) in receipts.items():
            with self.subTest(reopened=instance):
                self.assertEqual(self.plant.begin(op), done)
                self.assertEqual(self.plant.finish(op["id"]), done)
                self.assertEqual(self.plant.observe(instance)["effectCount"], 1)

    def test_distinct_inspection_intents_are_not_coalesced_by_arguments(self):
        first = operation(self.plant.session, "sim:inspection-cell")
        self.plant.begin(first)
        self.plant.finish(first["id"])
        second = operation(self.plant.session, "sim:inspection-cell", key="op:second", fence=2)
        self.plant.begin(second)
        done = self.plant.finish(second["id"])
        self.assertEqual(done["result"]["count"], 2)
        self.assertEqual(self.plant.observe("sim:inspection-cell")["effectCount"], 2)
        self.assertEqual(self.plant.finish(first["id"])["result"]["count"], 1)

    def test_concurrent_retries_commit_only_once(self):
        op = operation(self.plant.session, "sim:inspection-cell")
        def retry(_):
            self.plant.begin(copy.deepcopy(op))
            return self.plant.finish(op["id"])
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(retry, range(24)))
        self.assertTrue(all(item == results[0] for item in results))
        self.assertEqual(self.plant.observe("sim:inspection-cell"),
                         {"value": 1, "ready": True, "effectCount": 1})

    def test_existing_key_conflict_and_forged_digest_do_not_change_receipt(self):
        op = operation(self.plant.session)
        original = self.plant.begin(op)
        changed = copy.deepcopy(op)
        changed["intent"]["arguments"]["level"] = 70
        rehash(changed)
        self.assert_code("SIMULATOR_KEY_CONFLICT", self.plant.begin, changed)
        forged = copy.deepcopy(changed)
        forged["digest"] = op["digest"]
        with self.assertRaises((JournalError, ContractError)):
            self.plant.begin(forged)
        self.assertEqual(self.plant.receipt(op["id"]), original)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_new_request_digest_must_match_immutable_intent(self):
        op = operation(self.plant.session)
        op["digest"] = "sha256:" + "b" * 64
        with self.assertRaises((JournalError, ContractError)):
            self.plant.begin(op)
        self.assertIsNone(self.plant.receipt(op["id"]))
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM fences").fetchone()[0], 0)

    def test_caller_mutation_cannot_change_stored_pending_intent(self):
        op = operation(self.plant.session)
        returned = self.plant.begin(op)
        op["intent"]["arguments"]["level"] = 95
        returned["intent"]["arguments"]["level"] = 80
        done = self.plant.finish(op["id"])
        self.assertEqual(done["result"]["level"], 40)
        self.assertEqual(self.plant.observe("sim:home-fan")["value"], 40)

    def test_begin_rolls_back_fence_when_receipt_insert_fails(self):
        self.plant.db.execute("""CREATE TEMP TRIGGER refuse_receipt BEFORE INSERT ON receipts
            BEGIN SELECT RAISE(ABORT, 'synthetic receipt write failure'); END""")
        op = operation(self.plant.session, fence=7)
        with self.assertRaises(sqlite3.DatabaseError):
            self.plant.begin(op)
        self.assertFalse(self.plant.db.in_transaction)
        self.assertIsNone(self.plant.receipt(op["id"]))
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM fences").fetchone()[0], 0)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)
        self.plant.db.execute("DROP TRIGGER refuse_receipt")
        self.plant.begin(op)
        self.assertEqual(self.plant.db.execute("SELECT epoch FROM fences").fetchone()[0], 7)

    def test_finish_rolls_back_virtual_effect_when_receipt_update_fails(self):
        op = operation(self.plant.session, "sim:inspection-cell")
        self.plant.begin(op)
        self.plant.db.execute("""CREATE TEMP TRIGGER refuse_completion BEFORE UPDATE OF state ON receipts
            WHEN NEW.state = 'completed'
            BEGIN SELECT RAISE(ABORT, 'synthetic completion receipt failure'); END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.plant.finish(op["id"])
        self.assertFalse(self.plant.db.in_transaction)
        self.assertEqual(self.plant.receipt(op["id"])["state"], "pending")
        self.assertEqual(self.plant.observe("sim:inspection-cell"),
                         {"value": 0, "ready": True, "effectCount": 0})
        self.plant.db.execute("DROP TRIGGER refuse_completion")
        done = self.plant.finish(op["id"])
        self.assertEqual(done["result"]["count"], 1)
        self.assertEqual(self.plant.observe("sim:inspection-cell")["effectCount"], 1)

    def test_fence_supersession_is_checked_before_effect_and_persists(self):
        old = operation(self.plant.session, "sim:microscope", key="op:old", fence=1)
        new = operation(self.plant.session, "sim:microscope", key="op:new", fence=2)
        new["intent"]["arguments"]["position"] = 80
        rehash(new)
        self.plant.begin(old)
        self.plant.begin(new)
        canceled = self.plant.finish(old["id"])
        self.assertEqual(canceled["state"], "canceled")
        self.assertEqual(canceled["result"], {"reason": "superseded_fence", "effectCommitted": False})
        self.assertEqual(self.plant.observe("sim:microscope")["effectCount"], 0)
        self.plant.finish(new["id"])
        stale = operation(self.plant.session, "sim:microscope", key="op:stale", fence=1)
        self.assert_code("SIMULATOR_STALE_FENCE", self.plant.begin, stale)
        self.reopen()
        self.assert_code("SIMULATOR_STALE_FENCE", self.plant.begin, stale)
        self.assertIsNone(self.plant.receipt(stale["id"]))
        self.assertEqual(self.plant.observe("sim:microscope"),
                         {"value": 80, "ready": True, "effectCount": 1})

    def test_stale_session_refused_without_receipt_or_fence(self):
        op = operation("sim-session:obsolete", fence=20)
        self.assert_code("SIMULATOR_SESSION_CHANGED", self.plant.begin, op)
        self.assertIsNone(self.plant.receipt(op["id"]))
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM fences").fetchone()[0], 0)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_session_is_rechecked_immediately_before_effect(self):
        op = operation(self.plant.session)
        self.plant.begin(op)
        # Inject an endpoint-session transition after admission, before effects.
        self.plant.session = "sim-session:replacement"
        canceled = self.plant.finish(op["id"])
        self.assertEqual(canceled["state"], "canceled")
        self.assertEqual(canceled["result"],
                         {"reason": "endpoint_session_changed", "effectCommitted": False})
        self.assertEqual(self.plant.finish(op["id"]), canceled)
        self.assertEqual(self.plant.observe("sim:home-fan"),
                         {"value": 0, "ready": True, "effectCount": 0})

    def test_cancel_before_commit_and_late_cancel_preserve_terminal_result(self):
        op = operation(self.plant.session)
        self.plant.begin(op)
        canceled = self.plant.finish(op["id"], cancel_reason="operator_requested")
        self.assertEqual(canceled["result"], {"reason": "operator_requested", "effectCommitted": False})
        self.assertEqual(self.plant.begin(op), canceled)
        self.assertEqual(self.plant.finish(op["id"]), canceled)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)
        other = operation(self.plant.session, key="op:completed", fence=2)
        self.plant.begin(other)
        completed = self.plant.finish(other["id"])
        self.assertEqual(self.plant.finish(other["id"], cancel_reason="late_cancel"), completed)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 1)

    def test_reopen_cancels_pending_without_resume_or_effect(self):
        op = operation(self.plant.session, "sim:inspection-cell")
        self.plant.begin(op)
        self.reopen()
        canceled = self.plant.receipt(op["id"])
        self.assertEqual(canceled["state"], "canceled")
        self.assertEqual(canceled["result"],
                         {"reason": "simulator_owner_reopened", "effectCommitted": False})
        self.assertEqual(self.plant.begin(op), canceled)
        self.assertEqual(self.plant.finish(op["id"]), canceled)
        self.assertEqual(self.plant.observe("sim:inspection-cell")["effectCount"], 0)
        self.reopen()
        self.assertEqual(self.plant.receipt(op["id"]), canceled)

    def test_second_owner_cannot_cancel_live_pending_work(self):
        op = operation(self.plant.session)
        self.plant.begin(op)
        with self.assertRaises(JournalError) as caught:
            second = SimulatedPlant(self.path)
            second.close()
        self.assertEqual(caught.exception.code, "OWNER_BUSY")
        self.assertEqual(self.plant.receipt(op["id"])["state"], "pending")
        self.plant.finish(op["id"])
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 1)

    def test_abrupt_owner_exit_preserves_committed_state_and_receipts(self):
        code = """import json, os, sys
from hms.simulator import SimulatedPlant
from hms.contracts import intent_digest
plant = SimulatedPlant(sys.argv[1], create=True)
op = json.loads(sys.argv[2])
op['intent']['endpointSession'] = plant.session
op['digest'] = intent_digest(op['intent'])
plant.begin(op)
if sys.argv[3] == 'completed':
    plant.finish(op['id'])
os._exit(0)
"""
        op = operation("session:placeholder", "sim:inspection-cell")
        for state in ["pending", "completed"]:
            with self.subTest(state=state):
                child_path = Path(self.temp.name) / (state + ".db")
                result = subprocess.run(
                    [sys.executable, "-c", code, str(child_path), json.dumps(op), state],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                recovered = SimulatedPlant(child_path)
                try:
                    receipt = recovered.receipt(op["id"])
                    committed = state == "completed"
                    self.assertEqual(receipt["state"], "completed" if committed else "canceled")
                    self.assertEqual(receipt["result"]["effectCommitted"], committed)
                    self.assertEqual(recovered.observe("sim:inspection-cell"),
                                     {"value": int(committed), "ready": True,
                                      "effectCount": int(committed)})
                    self.assertEqual(recovered.finish(op["id"]), receipt)
                finally:
                    recovered.close()

    def test_local_argument_validation_precedes_receipt_and_fence(self):
        cases = [
            ("sim:home-fan", {"level": -0.1, "unit": "percent"}),
            ("sim:home-fan", {"level": 100.1, "unit": "percent"}),
            ("sim:home-fan", {"level": True, "unit": "percent"}),
            ("sim:home-fan", {"level": "40", "unit": "percent"}),
            ("sim:home-fan", {"level": 40, "unit": "rpm"}),
            ("sim:home-fan", {"level": 40}),
            ("sim:home-fan", {"level": 40, "unit": "percent", "override": True}),
            ("sim:microscope", {"position": -1, "unit": "um", "frame": "sim:microscope"}),
            ("sim:microscope", {"position": 101, "unit": "um", "frame": "sim:microscope"}),
            ("sim:microscope", {"position": False, "unit": "um", "frame": "sim:microscope"}),
            ("sim:microscope", {"position": 25, "unit": "mm", "frame": "sim:microscope"}),
            ("sim:microscope", {"position": 25, "unit": "um", "frame": "other:stage"}),
            ("sim:inspection-cell", {"recipe": 3, "partId": "part"}),
            ("sim:inspection-cell", {"recipe": 1.0, "partId": "part"}),
            ("sim:inspection-cell", {"recipe": True, "partId": "part"}),
            ("sim:inspection-cell", {"recipe": 1, "partId": ""}),
            ("sim:inspection-cell", {"recipe": 1, "partId": "x" * 65}),
            ("sim:inspection-cell", {"recipe": 1, "partId": 17}),
        ]
        for index, (instance, arguments) in enumerate(cases):
            with self.subTest(instance=instance, arguments=arguments):
                op = operation(self.plant.session, instance, key=f"op:invalid-{index}", fence=50)
                op["intent"]["arguments"] = arguments
                rehash(op)
                with self.assertRaises((JournalError, ContractError)):
                    self.plant.begin(op)
                self.assertIsNone(self.plant.receipt(op["id"]))
                self.assertEqual(self.plant.observe(instance)["effectCount"], 0)
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM fences").fetchone()[0], 0)

    def test_local_argument_boundaries_are_accepted(self):
        for instance, field in [("sim:home-fan", "level"), ("sim:microscope", "position")]:
            for index, value in enumerate([0, 0.25, 100], 1):
                with self.subTest(instance=instance, value=value):
                    op = operation(self.plant.session, instance, key=f"op:{instance}-{index}", fence=index)
                    op["intent"]["arguments"][field] = value
                    self.plant.begin(rehash(op))
                    self.assertEqual(self.plant.finish(op["id"])["result"][field], value)
        op = operation(self.plant.session, "sim:inspection-cell")
        op["intent"]["arguments"] = {"recipe": 2, "partId": "x" * 64}
        self.plant.begin(rehash(op))
        self.assertEqual(self.plant.finish(op["id"])["result"]["recipe"], 2)

    def test_claims_must_cover_fixed_resource_with_positive_integer_fence(self):
        resource = "sim:home-fan:fan-control"
        invalid = [[], [{"resource": "other:resource", "fence": 1}],
                   [{"resource": resource, "fence": 1}, {"resource": resource, "fence": 2}]]
        invalid += [[{"resource": resource, "fence": value}]
                    for value in [0, -1, True, 1.0, "1", SAFE_INTEGER + 1]]
        for index, claims in enumerate(invalid):
            with self.subTest(claims=claims):
                op = operation(self.plant.session, key=f"op:bad-claims-{index}")
                op["claims"] = claims
                with self.assertRaises((JournalError, ContractError)):
                    self.plant.begin(op)
                self.assertIsNone(self.plant.receipt(op["id"]))
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM fences").fetchone()[0], 0)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_unknown_action_and_malformed_host_intent_are_refused_at_begin(self):
        changes = [{"actionId": "toggle"}, {"instanceId": "sim:unknown"},
                   {"requiredEffect": "unrecognized"}, {"timing": {"maxRunMs": 100}}]
        for index, change in enumerate(changes):
            with self.subTest(change=change):
                op = operation(self.plant.session, key=f"op:bad-intent-{index}")
                op["intent"].update(change)
                rehash(op)
                with self.assertRaises((JournalError, ContractError)):
                    self.plant.begin(op)
                self.assertIsNone(self.plant.receipt(op["id"]))
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_local_execution_policy_refuses_physical_proof_and_excess_duration(self):
        physical = operation(self.plant.session, key="op:physical-proof")
        physical["intent"]["requiredEffect"] = "physical_verified"
        too_long = operation(self.plant.session, key="op:too-long")
        too_long["intent"]["timing"]["maxRunMs"] = 5001
        for op in [physical, too_long]:
            with self.subTest(operation=op["id"]):
                with self.assertRaises((JournalError, ContractError)):
                    self.plant.begin(rehash(op))
                self.assertIsNone(self.plant.receipt(op["id"]))
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM fences").fetchone()[0], 0)
        self.assertEqual(self.plant.observe("sim:home-fan")["effectCount"], 0)
        at_limit = operation(self.plant.session, key="op:duration-boundary")
        at_limit["intent"]["timing"]["maxRunMs"] = 5000
        self.plant.begin(rehash(at_limit))
        self.assertEqual(self.plant.finish(at_limit["id"])["state"], "completed")

    def test_missing_receipt_is_not_completed_or_created(self):
        self.assert_code("SIMULATOR_RECEIPT_MISSING", self.plant.finish, "op:missing")
        self.assertIsNone(self.plant.receipt("op:missing"))
        self.assertEqual(self.plant.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
