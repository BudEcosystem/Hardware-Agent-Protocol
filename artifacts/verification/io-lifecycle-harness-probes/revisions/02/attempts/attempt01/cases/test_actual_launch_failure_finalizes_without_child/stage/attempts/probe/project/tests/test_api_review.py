"""Independent adversarial checks of the checked local API boundary.

Fixtures come from temporary real Runtime instances. All effects and evidence
are synthetic; no acquired implementation or physical interface is exercised.
"""
import copy
import hashlib
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from hms.api_contracts import ResponseError, validate_params, validate_result
from hms.client import Client
from hms.contracts import canonical
from hms.journal import Context
from hms.projections import invoke_td_input
from hms.runtime import Runtime


class ApiReview(unittest.TestCase):
    @staticmethod
    def prepare_params(namespace, key="review:1"):
        return {
            "instanceId": "sim:home-fan", "actionId": "set_level",
            "arguments": {"level": 30, "unit": "percent"},
            "operationKey": key, "replayNamespace": namespace,
            "requiredEffect": "capability_completion",
            "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                       "maxRunMs": 500, "latestCompletionUnixMs": 5500},
        }

    @classmethod
    def setUpClass(cls):
        owner = Context("api-review-owner", "simulation:local")
        with tempfile.TemporaryDirectory() as directory:
            time = [1000]
            runtime = Runtime(directory, create=True, owner=owner,
                              wall_clock_ms=lambda: time[0], monotonic_ms=lambda: time[0])
            try:
                call = lambda method, params: runtime.request(owner, method, params)
                namespace = call("namespace", {"expiresUnixMs": 10000})["token"]
                cls.preparation = cls.prepare_params(namespace)
                cls.prepared = call("prepare", cls.preparation)
                cls.description = call("describe", {"instanceId": "sim:home-fan"})
                cls.discovery = call("discover", {})
                cls.accepted = call("invoke", {"request": cls.prepared["request"]})
                runtime.tick()
                time[0] = 1100
                runtime.tick()
                target = {"operationId": cls.accepted["operationId"]}
                cls.completed = call("operation", target)
                cls.events = call("events", target)
                cls.event_tail = call("events", target | {"after": 2, "limit": 1})
            finally:
                runtime.close()

    @staticmethod
    def rehash_description(result):
        digest = "sha256:" + hashlib.sha256(
            b"HMS-TYPE-BUNDLE-v0.1\0" + canonical(result["type"])
        ).hexdigest()
        result["descriptionDigest"] = result["instance"]["type_digest"] = digest
        if result["binding"] is not None:
            result["binding"]["typeDigest"] = digest

    def reject_description(self, mutate):
        result = copy.deepcopy(self.description)
        mutate(result)
        self.rehash_description(result)
        with self.assertRaises(ResponseError):
            validate_result("describe", result, {"instanceId": "sim:home-fan"})

    def test_recomputed_digest_cannot_legitimize_effect_flags_or_write_forms(self):
        changes = [
            lambda d: d["type"]["td"]["actions"]["set_level"].__setitem__("safe", True),
            lambda d: d["type"]["td"]["actions"]["set_level"].__setitem__("idempotent", True),
            lambda d: d["type"]["td"]["actions"]["set_level"].__setitem__("synchronous", True),
            lambda d: d["type"]["td"]["properties"]["value"]["forms"][0].__setitem__("op", "writeproperty"),
            lambda d: d["type"]["td"]["properties"]["value"].__setitem__("forms", [42]),
            lambda d: d["type"]["td"].__setitem__("events", {}),
            lambda d: d["type"]["td"].__setitem__("forms", [{"href": "https://example.invalid/raw", "op": "writeallproperties"}]),
        ]
        for index, mutate in enumerate(changes):
            with self.subTest(index=index):
                self.reject_description(mutate)

    def test_preconditions_must_resolve_and_match_the_property_schema(self):
        for field, value in (("property", "missing"), ("equals", "true")):
            with self.subTest(field=field):
                self.reject_description(lambda d: d["type"]["execution"]["actions"]["set_level"]
                                        ["preconditions"][0].__setitem__(field, value))

    def test_action_schema_must_be_object_even_if_td_projection_agrees(self):
        def mutate(result):
            schema = {"type": "number"}
            result["type"]["execution"]["actions"]["set_level"]["inputSchema"] = schema
            result["type"]["td"]["actions"]["set_level"]["input"] = invoke_td_input(schema)
        self.reject_description(mutate)

    def test_required_properties_must_exist_even_if_td_projection_agrees(self):
        def mutate(result):
            schema = result["type"]["execution"]["actions"]["set_level"]["inputSchema"]
            schema["required"] = ["missing"]
            result["type"]["td"]["actions"]["set_level"]["input"] = invoke_td_input(schema)
        self.reject_description(mutate)

    def test_binding_schema_must_be_a_valid_schema_not_just_keyword_shaped(self):
        for mutate in (
            lambda d: d["binding"]["argumentSchemas"]["set_level"].__setitem__("required", ["missing"]),
            lambda d: d["binding"]["argumentSchemas"]["set_level"].__setitem__("required", ["level", "level"]),
        ):
            with self.subTest(mutate=mutate):
                self.reject_description(mutate)

    def test_simulation_binding_requires_simulation_identity(self):
        self.reject_description(lambda d: d["instance"].__setitem__("identity_kind", "device"))

    def test_inactive_description_binding_cannot_retain_presence(self):
        self.reject_description(lambda d: d.__setitem__("bindingActive", False))

    def test_inventory_cannot_advertise_activity_without_a_binding(self):
        result = copy.deepcopy(self.discovery)
        result["items"][0]["bindingGeneration"] = None
        with self.assertRaises(ResponseError):
            validate_result("discover", result)

    def test_rejected_before_dispatch_cannot_retain_resource_claims(self):
        result = copy.deepcopy(self.accepted)
        result["executionState"] = "rejected_before_dispatch"
        with self.assertRaises(ResponseError):
            validate_result("operation", result)

    def test_verification_requires_attached_physical_evidence_result(self):
        result = copy.deepcopy(self.completed)
        result["effectVerification"] = "verified"
        result["result"] = None
        with self.assertRaises(ResponseError):
            validate_result("operation", result)

    def test_confirmed_cancellation_cannot_be_attached_to_completed_state(self):
        result = copy.deepcopy(self.completed)
        result["cancellationState"] = "confirmed"
        with self.assertRaises(ResponseError):
            validate_result("operation", result)

    def test_execution_event_needs_its_claimed_transition_assertion(self):
        for kind in ("simulation", "runtime"):
            result = copy.deepcopy(self.events)
            event = next(e for e in result["events"] if e["kind"] == "execution_evidence"
                         and e["payload"]["state"] == "completed")
            event["payload"]["evidence"]["kind"] = kind
            event["payload"]["evidence"]["assertions"] = ["running"] if kind == "simulation" else ["completed"]
            with self.subTest(kind=kind), self.assertRaises(ResponseError):
                validate_result("events", result)

    def test_release_dispute_and_cancel_ack_events_need_matching_assertions(self):
        for kind, payload in (
            ("resources_released", {}), ("evidence_dispute", {}), ("cancel_ack", {"accepted": True}),
        ):
            result = copy.deepcopy(self.events)
            event = result["events"][-1]
            event["kind"] = kind
            event["payload"] = payload | {"evidence": {
                "kind": "simulation", "source": "simulator:local",
                "reference": "review:receipt", "assertions": ["running"],
            }}
            with self.subTest(kind=kind), self.assertRaises(ResponseError):
                validate_result("events", result)

    def test_event_audit_times_do_not_regress_within_a_page(self):
        result = copy.deepcopy(self.events)
        result["events"][-1]["time_ms"] = 0
        with self.assertRaises(ResponseError):
            validate_result("events", result)

    def test_partial_event_page_does_not_require_a_repeated_acceptance_event(self):
        self.assertIs(validate_result("events", self.event_tail, {
            "operationId": self.completed["operationId"], "after": 2, "limit": 1,
        }), self.event_tail)

    def test_caller_mutation_during_transport_cannot_change_prepared_identity(self):
        params = copy.deepcopy(self.preparation)

        def transport(_path, method, snapshot):
            self.assertEqual(method, "prepare")
            params["arguments"]["level"] = 99
            params["operationKey"] = "changed:caller"
            self.assertEqual(snapshot["arguments"]["level"], 30)
            self.assertEqual(snapshot["operationKey"], "review:1")
            return copy.deepcopy(self.prepared)

        with patch("hms.client.call", side_effect=transport) as send:
            result = Client("unused").request("prepare", params)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["request"]["intent"]["arguments"]["level"], 30)
        self.assertEqual(result["request"]["operationKey"], "review:1")

    def test_rejected_mutation_response_is_never_retried(self):
        malformed = copy.deepcopy(self.completed)
        malformed["effectVerification"] = "verified"
        malformed["result"] = None
        with patch("hms.client.call", return_value=malformed) as send:
            with self.assertRaises(ResponseError):
                Client("unused").request("invoke", {"request": self.prepared["request"]})
        self.assertEqual(send.call_count, 1)

    def test_oversized_in_memory_values_are_rejected_without_copying_their_size(self):
        # Allocate hostile caller-owned inputs before measuring validator work.
        # The transport parser has a separate byte cap; this tests direct callers.
        for value in ("x" * (4 * 1024 * 1024), [0] * 200000):
            result = {"token": value}
            with self.subTest(input_type=type(value).__name__):
                tracemalloc.start()
                try:
                    with self.assertRaises(ResponseError):
                        validate_result("namespace", result)
                    _, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertLess(peak, 1024 * 1024,
                                "rejection allocated storage proportional to oversized input")

    def test_runtime_caller_mutation_after_validation_cannot_change_preparation(self):
        owner = Context("api-review-mutation", "simulation:local")
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(directory, create=True, owner=owner,
                              wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)
            try:
                namespace = runtime.request(owner, "namespace", {"expiresUnixMs": 10000})["token"]
                params = self.prepare_params(namespace)

                def interleaved_validation(method, snapshot):
                    validate_params(method, snapshot)
                    # Deterministically model another holder of the caller's
                    # object changing it after validation but before dispatch.
                    params["arguments"]["level"] = 99
                    params["operationKey"] = "changed:caller"

                with patch("hms.runtime.validate_params", side_effect=interleaved_validation):
                    result = runtime.request(owner, "prepare", params)
                self.assertEqual(result["request"]["intent"]["arguments"]["level"], 30)
                self.assertEqual(result["request"]["operationKey"], "review:1")
            finally:
                runtime.close()

    def test_receipt_can_precede_journal_settlement_and_reconcile_after_reopen(self):
        owner = Context("api-review-recovery", "simulation:local")
        with tempfile.TemporaryDirectory() as directory:
            now = [1000]
            runtime = Runtime(directory, create=True, owner=owner,
                              wall_clock_ms=lambda: now[0], monotonic_ms=lambda: now[0])
            try:
                namespace = runtime.request(owner, "namespace", {"expiresUnixMs": 10000})["token"]
                prepared = runtime.request(owner, "prepare", self.prepare_params(namespace))
                operation = runtime.request(owner, "invoke", {"request": prepared["request"]})
                target = {"operationId": operation["operationId"]}
                runtime.tick()
                # Model the real inter-database crash interval: plant state and
                # receipt committed, Journal still running with retained claims.
                runtime.plant.finish(operation["operationId"])
                result = runtime.request(owner, "operation", target)
                self.assertEqual(result["executionState"], "running")
                self.assertTrue(result["result"]["output"]["effectCommitted"])
                self.assertTrue(result["resourceClaims"])
                runtime.close()
                runtime = Runtime(directory, wall_clock_ms=lambda: now[0], monotonic_ms=lambda: now[0])
                result = runtime.request(owner, "operation", target)
                self.assertEqual(result["executionState"], "outcome_unknown")
                self.assertTrue(result["result"]["output"]["effectCommitted"])
                runtime.tick()
                result = runtime.request(owner, "operation", target)
                self.assertEqual(result["executionState"], "completed")
                self.assertEqual(result["resourceClaims"], [])
                self.assertEqual(runtime.plant.observe("sim:home-fan")["effectCount"], 1)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
