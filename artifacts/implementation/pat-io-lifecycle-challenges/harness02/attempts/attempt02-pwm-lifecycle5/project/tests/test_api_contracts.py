"""Reject forged or contradictory domain evidence at the client boundary."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hms.api_contracts import ResponseError, validate_params, validate_result
from hms.client import Client
from hms.contracts import ContractError, SAFE_INTEGER, canonical, intent_digest
from hms.ipc import IpcError
from hms.journal import Context
from hms.runtime import Runtime
from scripts.build_api_schema import build

ROOT = Path(__file__).resolve().parents[1]


class ApiContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            now = [1000]
            runtime = Runtime(directory, create=True, owner=Context("api-test", "simulation:local"),
                              wall_clock_ms=lambda: now[0], monotonic_ms=lambda: now[0])
            try:
                owner = Context("api-test", "simulation:local")
                call = lambda method, params: runtime.request(owner, method, params)
                cls.namespace = call("namespace", {"expiresUnixMs": 10000})
                cls.params = {"instanceId": "sim:home-fan", "actionId": "set_level", "arguments": {"level": 34, "unit": "percent"},
                    "replayNamespace": cls.namespace["token"], "operationKey": "operation:1", "requiredEffect": "capability_completion",
                    "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000, "maxRunMs": 500, "latestCompletionUnixMs": 5500}}
                cls.prepared = call("prepare", cls.params)
                cls.description = call("describe", {"instanceId": "sim:home-fan"})
                cls.discovery = call("discover", {})
                cls.accepted = call("invoke", {"request": cls.prepared["request"]})
                runtime.tick()
                now[0] = 1100
                runtime.tick()
                cls.operation = call("operation", {"operationId": cls.accepted["operationId"]})
                cls.observation = call("observe", {"instanceId": "sim:home-fan", "property": "value", "maxAgeMs": 0, "evidenceKind": "simulation"})
                cls.events = call("events", {"operationId": cls.accepted["operationId"]})
            finally:
                runtime.close()

    def test_schema_is_reproducible_and_every_reference_is_local(self):
        schema = json.loads((ROOT / "schemas/local-api.schema.json").read_text())
        self.assertEqual(schema, build())
        stack = [schema]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "$ref" in node:
                    self.assertTrue(node["$ref"].startswith("#/$defs/"))
                    self.assertIn(node["$ref"].split("/")[-1], schema["$defs"])
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    def test_all_real_method_results_validate(self):
        for method, result in [("discover", self.discovery), ("describe", self.description), ("namespace", self.namespace),
                               ("prepare", self.prepared), ("invoke", self.accepted), ("operation", self.operation),
                               ("observe", self.observation), ("events", self.events)]:
            self.assertIs(validate_result(method, result), result)

    def test_operation_cannot_be_substituted_for_another_request(self):
        with self.assertRaises(ResponseError):
            validate_result("operation", self.operation, {"operationId": "someone-else"})
        modified = copy.deepcopy(self.prepared["request"])
        modified["intent"]["arguments"]["level"] = 35
        with self.assertRaises(ResponseError):
            validate_result("invoke", self.operation, {"request": modified})

    def test_simulation_cannot_claim_physical_verification(self):
        result = copy.deepcopy(self.operation)
        result["effectVerification"] = "verified"
        with self.assertRaises(ResponseError):
            validate_result("operation", result)

    def test_acceptance_cannot_claim_an_effect_or_release_its_claims(self):
        for field, value in [("mayHaveActed", True), ("resourceClaims", []), ("result", self.operation["result"])]:
            result = copy.deepcopy(self.accepted)
            result[field] = value
            with self.subTest(field=field), self.assertRaises(ResponseError):
                validate_result("operation", result)

    def test_completed_result_cannot_claim_no_effect(self):
        result = copy.deepcopy(self.operation)
        result["result"]["output"]["effectCommitted"] = False
        with self.assertRaises(ResponseError):
            validate_result("operation", result)

    def test_duplicate_claims_and_noninteger_fences_are_refused(self):
        for value in (True, 1.0, -1):
            result = copy.deepcopy(self.accepted)
            result["resourceClaims"][0]["fence"] = value
            with self.subTest(value=value), self.assertRaises(ResponseError):
                validate_result("operation", result)
        result = copy.deepcopy(self.accepted)
        result["resourceClaims"] *= 2
        with self.assertRaises(ResponseError):
            validate_result("operation", result)

    def test_unknown_fields_and_versions_fail_closed(self):
        for field, value in [("principal", "admin"), ("protocol", "hms.operation/999"), ("executionState", "probably_done")]:
            result = copy.deepcopy(self.operation)
            result[field] = value
            with self.subTest(field=field), self.assertRaises(ResponseError):
                validate_result("operation", result)

    def test_observation_must_match_target_age_and_requested_evidence(self):
        base = {"instanceId": "sim:home-fan", "property": "value", "maxAgeMs": 0, "evidenceKind": "simulation"}
        for changes in ({"instanceId": "other"}, {"property": "ready"}, {"evidenceKind": "physical_sensor"}):
            with self.subTest(changes=changes), self.assertRaises(ResponseError):
                validate_result("observe", self.observation, base | changes)
        result = copy.deepcopy(self.observation)
        result["ageUpperBoundMs"] = 1
        with self.assertRaises(ResponseError):
            validate_result("observe", result, base)

    def test_observation_uncertainty_and_freshness_cannot_contradict(self):
        for path, value in [("unit", "metres"), ("ageUpperBoundMs", None), ("acquisitionLatencyBoundMs", 1)]:
            result = copy.deepcopy(self.observation)
            result[path] = value
            with self.subTest(path=path), self.assertRaises(ResponseError):
                validate_result("observe", result)

    def test_description_hash_and_binding_must_agree(self):
        result = copy.deepcopy(self.description)
        result["type"]["td"]["title"] = "changed description"
        with self.assertRaises(ResponseError):
            validate_result("describe", result)
        result = copy.deepcopy(self.description)
        result["binding"]["instanceId"] = "different-device"
        with self.assertRaises(ResponseError):
            validate_result("describe", result)

    def test_self_consistent_hash_does_not_excuse_contradictory_projection(self):
        result = copy.deepcopy(self.description)
        result["type"]["td"]["properties"]["value"]["unit"] = "metres"
        digest = "sha256:" + hashlib.sha256(b"HMS-TYPE-BUNDLE-v0.1\0" + canonical(result["type"])).hexdigest()
        result["descriptionDigest"] = result["instance"]["type_digest"] = result["binding"]["typeDigest"] = digest
        with self.assertRaises(ResponseError):
            validate_result("describe", result)

    def test_description_cannot_introduce_remote_schema_references(self):
        result = copy.deepcopy(self.description)
        result["type"]["execution"]["properties"]["value"]["schema"]["$ref"] = "https://example.invalid/remote"
        with self.assertRaises(ResponseError):
            validate_result("describe", result)

    def test_events_cannot_hide_a_sequence_gap_or_change_operation(self):
        for change in ("gap", "target", "huge_cursor", "empty"):
            result = copy.deepcopy(self.events)
            if change == "gap":
                result["events"].pop(1)
            elif change == "target":
                result["events"][0]["operation_id"] = "different"
            elif change == "huge_cursor":
                result["next"] = result["head"] = SAFE_INTEGER
            else:
                result["events"] = []
            with self.subTest(change=change), self.assertRaises(ResponseError):
                validate_result("events", result, {"operationId": self.operation["operationId"]})

    def test_preparation_must_echo_immutable_caller_fields(self):
        result = copy.deepcopy(self.prepared)
        result["request"]["intent"]["arguments"]["level"] = 99
        result["requestDigest"] = intent_digest(result["request"]["intent"])
        with self.assertRaises(ResponseError):
            validate_result("prepare", result, self.params)

    def test_namespace_cannot_change_requested_expiry_or_epoch(self):
        with self.assertRaises(ResponseError):
            validate_result("namespace", self.namespace, {"expiresUnixMs": 10001})
        result = copy.deepcopy(self.namespace)
        result["epoch"] += 1
        with self.assertRaises(ResponseError):
            validate_result("namespace", result)

    def test_validation_cache_does_not_merge_integer_and_float_input_types(self):
        from hms.registry import validate_type_bundle
        valid = copy.deepcopy(self.description["type"])
        self.assertEqual(validate_type_bundle(valid), self.description["descriptionDigest"])
        for field in ("duration", "precondition_age"):
            invalid = copy.deepcopy(valid)
            action = invalid["execution"]["actions"]["set_level"]
            if field == "duration":
                action["maxRunMs"] = float(action["maxRunMs"])
            else:
                action["preconditions"][0]["maxAgeMs"] = float(action["preconditions"][0]["maxAgeMs"])
            self.assertEqual(canonical(valid), canonical(invalid))
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_type_bundle(invalid)
        valid["td"]["actions"]["set_level"]["safe"] = True
        with self.assertRaises(ContractError):
            validate_type_bundle(valid)

    def test_client_refuses_invalid_request_before_transport(self):
        with patch("hms.client.call") as transport:
            with self.assertRaises(ContractError):
                Client("unused").request("observe", {"instanceId": "a", "property": "b", "principal": "admin"})
            transport.assert_not_called()

    def test_client_makes_one_attempt_on_loss_or_invalid_response(self):
        params = {"request": self.prepared["request"]}
        with patch("hms.client.call", side_effect=IpcError("TRANSPORT_TIMEOUT")) as transport:
            with self.assertRaises(IpcError):
                Client("unused").request("invoke", params)
            self.assertEqual(transport.call_count, 1)
        with patch("hms.client.call", return_value={"status": "success"}) as transport:
            with self.assertRaises(ResponseError):
                Client("unused").request("invoke", params)
            self.assertEqual(transport.call_count, 1)


if __name__ == "__main__":
    unittest.main()
