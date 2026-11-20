"""Known age expiry may defer an unadmitted child; invalid evidence may not."""
import json
import tempfile
import unittest

from hms.journal import Context, JournalError, ObservationAgeExpired
from hms.runtime import Runtime


class ProcedureFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.wall = self.mono = 1000
        self.owner = Context("procedure-freshness", "simulation:local")
        self.runtime = Runtime(self.temp.name, create=True, owner=self.owner,
            wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.addCleanup(self.runtime.close)
        self.namespace = self.runtime.request(self.owner, "namespace", {"expiresUnixMs": 20000})["token"]
        child = self.runtime.request(self.owner, "prepare", {"instanceId": "sim:home-fan", "actionId": "set_level",
            "arguments": {"level": 37, "unit": "percent"}, "operationKey": "child",
            "replayNamespace": self.namespace, "requiredEffect": "capability_completion",
            "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 9000,
                       "maxRunMs": 500, "latestCompletionUnixMs": 10000}})["request"]
        self.envelope = {"protocol": "hms.procedure/0.1", "replayNamespace": self.namespace,
            "procedureKey": "parent", "procedure": {"profile": "hms.bound-sequence/0.1",
                "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 9000, "latestCompletionUnixMs": 10000},
                "steps": [{"stepId": "fan", "request": child}]}}
        self.parent = self.runtime.procedures.submit(self.owner, self.envelope)["procedureId"]

    def status(self):
        return self.runtime.procedures.status(self.owner, self.parent)

    def observation(self, *, quality="valid", latency=0, value=True):
        reg = self.runtime.registry
        row = reg._observation("sim:home-fan", "ready")
        reg.report_observation("sim:home-fan", property_id="ready", adapter_id="simulator:local",
            endpoint_session=row["endpointSession"], binding_generation=row["bindingGeneration"],
            value=value, evidence_kind="simulation", quality=quality, stream_epoch=row["streamEpoch"],
            sequence=row["sequence"] + 1,
            acquisition={"clockDomain": "simulator-monotonic", "clockEpoch": reg.receipt_epoch, "ticksMs": self.mono},
            acquisition_latency_bound_ms=latency, clock_uncertainty_ms=0,
            measurement_uncertainty={"absolute": 0, "unit": "1", "method": "test_exact"})

    def test_age_only_deferral_retains_original_key_then_admits_once(self):
        self.wall += 1101; self.mono += 1101
        with self.assertRaises(ObservationAgeExpired) as error:
            self.runtime.registry.observe(self.owner, "sim:home-fan", "ready", max_age_ms=1000, evidence_kind="simulation")
        self.assertEqual("OBSERVATION_STALE", error.exception.code)
        for _ in range(3):
            self.runtime.procedures.tick()
            self.assertEqual("accepted", self.status()["executionState"])
            self.assertIsNone(self.status()["steps"][0]["operationId"])
        self.assertEqual(0, self.runtime.journal._db.execute("SELECT count(*) FROM operations").fetchone()[0])
        self.assertEqual(2, self.runtime.journal._db.execute("SELECT count(*) FROM pr_keys").fetchone()[0])
        self.runtime.adapters["simulator:local"].refresh(force=True)
        self.runtime.procedures.tick()
        operation = self.status()["steps"][0]["operationId"]
        self.assertIsNotNone(operation)
        retained = json.loads(self.runtime.journal._db.execute("SELECT request FROM pr_steps").fetchone()[0])
        self.assertEqual(self.envelope["procedure"]["steps"][0]["request"], retained)
        self.runtime.tick(); self.wall += 100; self.mono += 100; self.runtime.tick()
        self.assertEqual("completed", self.status()["executionState"])
        self.assertEqual(operation, self.status()["steps"][0]["operationId"])
        self.assertEqual(1, self.runtime.plant.observe("sim:home-fan")["effectCount"])

    def test_expired_age_does_not_extend_parent_or_child_deadline(self):
        self.wall += 1101; self.mono += 1101
        self.runtime.procedures.tick()
        self.wall = self.mono = 9000
        self.runtime.procedures.tick()
        self.assertEqual("expired", self.status()["executionState"])
        self.assertIsNone(self.status()["steps"][0]["operationId"])
        self.assertEqual(0, self.runtime.plant.observe("sim:home-fan")["effectCount"])

    def test_invalid_quality_is_not_treated_as_age_expiry(self):
        self.observation(quality="invalid")
        with self.assertRaises(JournalError) as error:
            self.runtime.registry.observe(self.owner, "sim:home-fan", "ready", max_age_ms=1000)
        self.assertNotIsInstance(error.exception, ObservationAgeExpired)
        self.runtime.procedures.tick()
        self.assertEqual("failed", self.status()["executionState"])
        self.assertEqual("OBSERVATION_STALE", self.status()["reason"])
        self.assertIsNone(self.status()["steps"][0]["operationId"])

    def test_unknown_age_bound_is_not_treated_as_age_expiry(self):
        self.observation(latency=None)
        self.runtime.procedures.tick()
        self.assertEqual("failed", self.status()["executionState"])
        self.assertEqual("OBSERVATION_STALE", self.status()["reason"])
        self.assertIsNone(self.status()["steps"][0]["operationId"])

    def test_false_predicate_remains_a_substantive_refusal(self):
        self.observation(value=False)
        self.runtime.procedures.tick()
        self.assertEqual("failed", self.status()["executionState"])
        self.assertEqual("PRECONDITION_FAILED", self.status()["reason"])
        self.assertIsNone(self.status()["steps"][0]["operationId"])


if __name__ == "__main__":
    unittest.main()
