"""Integrated synthetic authority/registry/plant tests; no physical device I/O."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hms.contracts import ContractError
from hms.journal import Context, JournalError
from hms.runtime import Runtime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.wall = self.mono = 1000
        self.owner = Context("test-owner", "simulation:local")
        self.open(create=True)
        self.namespace = self.call("namespace", expiresUnixMs=10000)["token"]

    def open(self, create=False):
        self.runtime = Runtime(self.directory.name, create=create, owner=self.owner if create else None,
                               wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.addCleanup(self.runtime.close)

    def call(self, method, **params):
        return self.runtime.request(self.owner, method, params)

    def prepare(self, instance="sim:home-fan", action="set_level", arguments=None, key="operation:1", **changes):
        params = dict(instanceId=instance, actionId=action, arguments=arguments or {"level": 25, "unit": "percent"},
                      operationKey=key, replayNamespace=self.namespace, requiredEffect="capability_completion",
                      timing={"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                              "maxRunMs": 500, "latestCompletionUnixMs": 5500})
        params.update(changes)
        return self.call("prepare", **params)["request"]

    def invoke(self, request=None):
        return self.call("invoke", request=request or self.prepare())

    def status(self, operation):
        return self.call("operation", operationId=operation["operationId"])

    def advance(self, ms=100):
        self.wall += ms
        self.mono += ms
        self.runtime.tick()

    def test_three_scenarios_complete_with_explicit_simulation_evidence(self):
        cases = [("sim:home-fan", "set_level", {"level": 25, "unit": "percent"}, 25),
                 ("sim:microscope", "move_absolute", {"position": 42, "unit": "um", "frame": "sim:microscope"}, 42),
                 ("sim:inspection-cell", "inspect", {"recipe": 1, "partId": "part:A"}, 1)]
        operations = []
        for instance, action, args, value in cases:
            op = self.invoke(self.prepare(instance, action, args, key=instance))
            self.assertEqual(op["executionState"], "accepted")
            operations.append(op)
        self.runtime.tick()
        self.assertTrue(all(self.status(op)["executionState"] == "running" for op in operations))
        self.advance()
        for op, (instance, _, _, value) in zip(operations, cases):
            status = self.status(op)
            self.assertEqual(status["executionState"], "completed")
            self.assertEqual(status["effectVerification"], "unverified")
            self.assertEqual(status["result"]["evidenceKind"], "simulation")
            self.assertEqual(status["resourceClaims"], [])
            observation = self.call("observe", instanceId=instance, property="value", maxAgeMs=0, evidenceKind="simulation")
            self.assertEqual(observation["value"], value)
            self.assertEqual(self.runtime.plant.observe(instance)["effectCount"], 1)

    def test_duplicate_after_completion_and_restart_has_one_effect(self):
        request = self.prepare()
        op = self.invoke(request)
        self.runtime.tick()
        self.advance()
        self.runtime.close()
        self.open()
        duplicate = self.invoke(request)
        self.assertEqual(duplicate["operationId"], op["operationId"])
        self.assertEqual(duplicate["executionState"], "completed")
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 1)
        changed = copy.deepcopy(request)
        changed["intent"]["arguments"]["level"] = 99
        with self.assertRaisesRegex(JournalError, "KEY_CONFLICT"):
            self.invoke(changed)

    def test_resource_claim_excludes_second_operation(self):
        self.invoke()
        with self.assertRaisesRegex(JournalError, "RESOURCE_BUSY"):
            self.invoke(self.prepare(key="operation:2"))

    def test_cancel_before_dispatch_proves_no_effect(self):
        op = self.invoke()
        result = self.call("cancel", operationId=op["operationId"])
        self.runtime.tick()
        self.assertEqual(result["executionState"], "canceled")
        self.assertFalse(result["mayHaveActed"])
        self.assertEqual(result["resourceClaims"], [])
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_cancel_running_is_orthogonal_until_adapter_receipt(self):
        op = self.invoke()
        self.runtime.tick()
        requested = self.call("cancel", operationId=op["operationId"])
        self.assertEqual(requested["executionState"], "running")
        self.assertEqual(requested["cancellationState"], "requested")
        self.assertTrue(requested["resourceClaims"])
        self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "canceled")
        self.assertFalse(self.status(op)["result"]["output"]["effectCommitted"])

    def test_deadline_prevents_late_effect(self):
        op = self.invoke()
        self.runtime.tick()
        self.advance(500)
        self.assertEqual(self.status(op)["executionState"], "failed")
        self.assertEqual(self.status(op)["result"]["output"]["reason"], "execution_deadline")

    def test_backward_wall_clock_fails_closed_before_effect(self):
        op = self.invoke()
        self.runtime.tick()
        self.wall = 999
        self.mono = 1100
        with self.assertRaisesRegex(JournalError, "CLOCK_REGRESSION"):
            self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "failed")
        self.assertEqual(self.status(op)["result"]["output"]["reason"], "clock_authority_lost")
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_invalid_wall_clock_fails_closed_before_effect(self):
        op = self.invoke()
        self.runtime.tick()
        self.wall = None
        self.mono = 1100
        with self.assertRaisesRegex(JournalError, "INVALID_CLOCK"):
            self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "failed")
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_monotonic_failure_still_records_requested_cancellation(self):
        op = self.invoke()
        self.runtime.tick()
        self.call("cancel", operationId=op["operationId"])
        self.mono = 999
        with self.assertRaises(JournalError):
            self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "canceled")
        self.assertEqual(self.status(op)["resourceClaims"], [])

    def test_binding_invalidation_cancels_pending_simulation(self):
        op = self.invoke()
        self.runtime.tick()
        self.runtime.registry.invalidate(self.owner, "sim:home-fan")
        self.advance()
        self.assertEqual(self.status(op)["executionState"], "failed")
        self.assertFalse(self.status(op)["result"]["output"]["effectCommitted"])

    def limited_user(self):
        user = Context("test-user", "simulation:local")
        for verb in ("read", "invoke:set_level", "cancel"):
            self.runtime.registry.grant(self.owner, user.principal, "sim:home-fan", verb)
        self.runtime.registry.grant(self.owner, user.principal, "*", "namespace")
        return user

    def test_revocation_after_dispatch_prevents_effect_but_allows_result_read(self):
        user = self.limited_user()
        request = self.prepare()
        request["replayNamespace"] = self.runtime.request(user, "namespace", {"expiresUnixMs": 10000})["token"]
        op = self.runtime.request(user, "invoke", {"request": request})
        self.runtime.tick()
        self.runtime.registry.grant(self.owner, user.principal, "sim:home-fan", "invoke:set_level", enabled=False)
        self.advance()
        status = self.runtime.request(user, "operation", {"operationId": op["operationId"]})
        self.assertEqual(status["executionState"], "failed")
        self.assertFalse(status["result"]["output"]["effectCommitted"])

    def test_authorization_filters_inventory_before_pagination(self):
        user = self.limited_user()
        found = self.runtime.request(user, "discover", {"limit": 1})
        self.assertEqual([i["instanceId"] for i in found["items"]], ["sim:home-fan"])
        self.assertIsNone(found["cursor"])
        page = self.call("discover", limit=1)
        self.assertIsNotNone(page["cursor"])
        with self.assertRaisesRegex(JournalError, "INVALID_CURSOR"):
            self.runtime.request(user, "discover", {"limit": 1, "cursor": page["cursor"]})
        self.runtime.registry.grant(self.owner, user.principal, "sim:microscope", "read")
        with self.assertRaisesRegex(JournalError, "REGISTRY_CURSOR_STALE"):
            self.call("discover", limit=1, cursor=page["cursor"])

    def test_restart_reconciles_effect_committed_before_journal_receipt(self):
        op = self.invoke()
        self.runtime.tick()
        self.runtime.plant.finish(op["operationId"])
        self.runtime.close()
        self.open()
        self.assertEqual(self.status(op)["executionState"], "outcome_unknown")
        self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "completed")
        self.assertEqual(self.status(op)["resourceClaims"], [])
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 1)

    def test_restart_pending_simulation_cancels_without_resend(self):
        op = self.invoke()
        self.runtime.tick()
        self.runtime.close()
        self.open()
        self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "canceled")
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_missing_adapter_receipt_stays_unknown_and_keeps_claims(self):
        op = self.invoke()
        self.runtime.journal.claim_dispatch(op["operationId"])
        self.runtime.close()
        self.open()
        self.runtime.tick()
        self.assertEqual(self.status(op)["executionState"], "outcome_unknown")
        self.assertTrue(self.status(op)["resourceClaims"])

    def test_accepted_work_rechecks_after_restart(self):
        op = self.invoke()
        self.runtime.close()
        self.open()
        self.runtime.tick()
        self.advance()
        self.assertEqual(self.status(op)["executionState"], "completed")

    def test_prepare_rejects_unknown_action_and_physical_claim(self):
        with self.assertRaisesRegex(JournalError, "UNKNOWN_ACTION"):
            self.prepare(action="arbitrary")
        with self.assertRaisesRegex(JournalError, "PHYSICAL_EVIDENCE_UNAVAILABLE"):
            self.prepare(requiredEffect="physical_verified")
        with self.assertRaisesRegex(JournalError, "ARGUMENT_SCHEMA_MISMATCH"):
            self.prepare(arguments={"level": 101, "unit": "percent"})

    def test_missing_plant_is_not_silently_reinitialized(self):
        self.runtime.close()
        (Path(self.directory.name) / "simulated-plant.db").unlink()
        with self.assertRaises(JournalError):
            self.open()

    def test_process_crashes_across_combined_runtime_boundaries(self):
        for phase, expected, effects, held in [
            ("accepted", "completed", 1, False),
            ("dispatch_claimed", "outcome_unknown", 0, True),
            ("plant_pending", "canceled", 0, False),
            ("plant_committed", "completed", 1, False),
        ]:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                child = subprocess.run([sys.executable, str(Path(__file__).with_name("runtime_crash_driver.py")),
                                        directory, phase], capture_output=True, text=True, timeout=20)
                self.assertEqual(child.returncode, 73, child.stderr)
                record = json.loads(child.stdout)
                clock = [1000]
                runtime = Runtime(directory, wall_clock_ms=lambda: clock[0], monotonic_ms=lambda: clock[0])
                try:
                    runtime.tick()
                    clock[0] = 1100
                    runtime.tick()
                    status = runtime.request(self.owner, "operation", {"operationId": record["operation"]["operationId"]})
                    self.assertEqual(status["executionState"], expected)
                    self.assertEqual(bool(status["resourceClaims"]), held)
                    self.assertEqual(runtime.plant.observe("sim:home-fan")["effectCount"], effects)
                    duplicate = runtime.request(self.owner, "invoke", {"request": record["request"]})
                    self.assertEqual(duplicate["operationId"], status["operationId"])
                finally:
                    runtime.close()


if __name__ == "__main__":
    unittest.main()
