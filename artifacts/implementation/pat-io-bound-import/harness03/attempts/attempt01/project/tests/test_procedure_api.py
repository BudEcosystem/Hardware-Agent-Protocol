"""Adversarial procedure API, CLI and MCP projection contracts.

These tests mutate real checked-runtime projections. They test boundary truth
and request correlation, not a second implementation of the procedure engine.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from hms.api_contracts import ResponseError, validate_params, validate_result
from hms.cli import _parser, main as cli_main
from hms.client import Client
from hms.contracts import ContractError, canonical
from hms.ipc import IpcError
from hms.journal import Context, Evidence
from hms.mcp import MODERN, PREFIX, Projection, catalog, dumps
from hms.runtime import Runtime
from scripts.build_api_schema import build


ROOT = Path(__file__).resolve().parents[1]


class ProcedureApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            now = [1000]
            owner = Context("procedure-api-owner", "simulation:local")
            runtime = Runtime(directory, create=True, owner=owner,
                              wall_clock_ms=lambda: now[0], monotonic_ms=lambda: now[0])
            try:
                call = lambda method, params: runtime.request(owner, method, params)
                namespace = call("namespace", {"expiresUnixMs": 10000})["token"]
                steps = []
                for index, value in enumerate((23, 74)):
                    child = call("prepare", {"instanceId": "sim:home-fan", "actionId": "set_level",
                        "arguments": {"level": value, "unit": "percent"}, "operationKey": "api-child:" + str(index),
                        "replayNamespace": namespace, "requiredEffect": "capability_completion",
                        "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                                   "maxRunMs": 500, "latestCompletionUnixMs": 5500}})["request"]
                    steps.append({"stepId": "api-step:" + str(index), "request": child})
                cls.request = {"protocol": "hms.procedure/0.1", "replayNamespace": namespace, "procedureKey": "api-parent",
                    "procedure": {"profile": "hms.bound-sequence/0.1", "timing": {
                        "notBeforeUnixMs": 1000, "latestStartUnixMs": 5000, "latestCompletionUnixMs": 5500}, "steps": steps}}
                cls.params = {"request": cls.request}
                cls.accepted = call("procedure_submit", cls.params)
                cls.identity = {"procedureId": cls.accepted["procedureId"]}
                runtime.procedures.tick()
                cls.pending = call("procedure_status", cls.identity)
                runtime.tick()
                cls.running = call("procedure_status", cls.identity)
                for _ in range(4):
                    now[0] += 100
                    runtime.tick()
                cls.completed = call("procedure_status", cls.identity)
                assert cls.completed["executionState"] == "completed"
                cls.events = call("procedure_events", cls.identity)
                first_id = cls.completed["steps"][0]["operationId"]
                binding = runtime.registry._binding("sim:home-fan")[0]
                runtime.journal.dispute(first_id, Evidence("simulation", binding["adapterId"], "api:late-dispute", ("disputed",)))
                cls.disputed = call("procedure_status", cls.identity)
                cancel_request = copy.deepcopy(cls.request)
                cancel_request["procedureKey"] = "api-parent-cancel"
                for index, step in enumerate(cancel_request["procedure"]["steps"]):
                    step["request"]["operationKey"] = "api-cancel-child:" + str(index)
                canceled = call("procedure_submit", {"request": cancel_request})
                cls.cancel_identity = {"procedureId": canceled["procedureId"]}
                runtime.procedures.tick()
                cls.cancel_ack = call("procedure_cancel", cls.cancel_identity)
                cls.canceled = call("procedure_status", cls.cancel_identity)
                cls.cancel_events = call("procedure_events", cls.cancel_identity)
            finally:
                runtime.close()

    def reject_status(self, value):
        with self.assertRaises(ResponseError):
            validate_result("procedure_status", value)

    def test_real_results_validate_including_late_disputed_completion(self):
        for result in (self.accepted, self.pending, self.running, self.completed, self.disputed, self.canceled):
            with self.subTest(state=result["executionState"]):
                self.assertIs(validate_result("procedure_status", result), result)
        self.assertIs(validate_result("procedure_submit", self.accepted, self.params), self.accepted)
        self.assertIs(validate_result("procedure_cancel", self.cancel_ack, self.cancel_identity), self.cancel_ack)
        self.assertIs(validate_result("procedure_events", self.events, self.identity), self.events)
        self.assertIs(validate_result("procedure_events", self.cancel_events, self.cancel_identity), self.cancel_events)
        self.assertEqual(self.disputed["aggregateVerification"], "disputed")

    def test_parent_and_child_request_digest_mismatches_are_rejected(self):
        for mutate in (
                lambda r: r.update(requestDigest="sha256:" + "0" * 64),
                lambda r: r["steps"][0].update(requestDigest="sha256:" + "0" * 64),
                lambda r: r["steps"][0].update(stepId="some-other-step"),
                lambda r: r["timing"].update(latestCompletionUnixMs=5600)):
            result = copy.deepcopy(self.accepted)
            mutate(result)
            with self.assertRaises(ResponseError):
                validate_result("procedure_submit", result, self.params)
        changed = copy.deepcopy(self.request)
        changed["procedure"]["steps"][0]["request"]["operationKey"] = "different-retained-key"
        with self.assertRaises(ResponseError):
            validate_result("procedure_submit", self.accepted, {"request": changed})

    def test_ids_and_steps_cannot_be_substituted_duplicated_or_reordered(self):
        for method, result in (("procedure_status", self.completed), ("procedure_resume", self.running),
                               ("procedure_cancel", self.cancel_ack), ("procedure_events", self.events)):
            with self.subTest(method=method), self.assertRaises(ResponseError):
                validate_result(method, result, {"procedureId": "procedure:someone-else"})
        for mutate in (
                lambda r: r["steps"][1].update(operationId=r["steps"][0]["operationId"]),
                lambda r: r["steps"][1].update(stepId=r["steps"][0]["stepId"]),
                lambda r: r["steps"].reverse(),
                lambda r: r.update(stepCount=1)):
            result = copy.deepcopy(self.completed)
            mutate(result)
            self.reject_status(result)

    def test_unstarted_child_cannot_claim_effect_or_evidence(self):
        for field, value in (("mayHaveActed", True), ("heldResources", 1), ("eventSequence", 1),
                             ("executionState", "completed"), ("effectVerification", "verified"),
                             ("cancellationState", "requested")):
            result = copy.deepcopy(self.accepted)
            result["steps"][0][field] = value
            if field == "mayHaveActed":
                result["mayHaveActed"] = True
            with self.subTest(field=field):
                self.reject_status(result)

    def test_handed_off_child_cannot_deny_possible_effect(self):
        for state in ("dispatching", "running", "outcome_unknown", "completed", "failed"):
            result = copy.deepcopy(self.running)
            result["steps"][0].update(executionState=state, mayHaveActed=False)
            result["mayHaveActed"] = False
            with self.subTest(state=state):
                self.reject_status(result)

    def test_pending_child_cannot_falsely_release_claims_or_acknowledge_cancel(self):
        for change in ({"heldResources": 0}, {"cancellationState": "requested"},
                       {"cancellationState": "confirmed"}, {"mayHaveActed": True}):
            result = copy.deepcopy(self.pending)
            result["steps"][0].update(change)
            self.reject_status(result)
        result = copy.deepcopy(self.pending)
        result["steps"][0]["executionState"] = "rejected_before_start"
        self.reject_status(result)

    def test_cursor_cannot_skip_unlinked_or_uncompleted_children(self):
        result = copy.deepcopy(self.accepted)
        result["cursor"] = result["stepCount"]
        self.reject_status(result)
        result = copy.deepcopy(self.running)
        result["cursor"] = 1
        self.reject_status(result)
        result = copy.deepcopy(self.completed)
        result["executionState"] = "running"
        result["cursor"] = 0
        self.reject_status(result)
        result = copy.deepcopy(self.accepted)
        result["executionState"] = "running"
        self.reject_status(result)
        result = copy.deepcopy(self.pending)
        result["executionState"] = "accepted"
        self.reject_status(result)

    def test_false_parent_completion_and_aggregate_are_rejected(self):
        result = copy.deepcopy(self.running)
        result["executionState"] = "completed"
        self.reject_status(result)
        for field, value in (("mayHaveActed", False), ("unresolvedOperations", ["op:invented"]),
                             ("aggregateVerification", "verified"), ("aggregateVerification", "failed")):
            result = copy.deepcopy(self.completed)
            result[field] = value
            self.reject_status(result)
        result = copy.deepcopy(self.disputed)
        result["aggregateVerification"] = "unverified"
        result["unresolvedOperations"] = []
        self.reject_status(result)

    def test_cancellation_state_and_delivery_must_be_consistent(self):
        for state in ("accepted", "running", "interrupted"):
            result = copy.deepcopy(self.cancel_ack)
            result["executionState"] = state
            with self.subTest(state=state), self.assertRaises(ResponseError):
                validate_result("procedure_cancel", result, self.cancel_identity)
        for change in ({"operationId": None}, {"status": "denied"}, {"code": "ACCESS_DENIED"},
                       {"status": "no_active_child"}):
            result = copy.deepcopy(self.cancel_ack)
            result["delivery"].update(change)
            with self.assertRaises(ResponseError):
                validate_result("procedure_cancel", result)
        result = copy.deepcopy(self.canceled)
        result["cancelRequested"] = False
        self.reject_status(result)
        result = copy.deepcopy(self.running)
        result["cancelRequested"] = True
        self.reject_status(result)

    def test_event_gaps_foreign_parent_and_reversed_clock_are_rejected(self):
        for mutate in (
                lambda r: r["events"][1].update(sequence=r["events"][1]["sequence"] + 1),
                lambda r: r["events"][0].update(procedure_id="procedure:foreign"),
                lambda r: r["events"][1].update(time_ms=0),
                lambda r: r.update(gap=True),
                lambda r: r.update(next=r["next"] - 1)):
            result = copy.deepcopy(self.events)
            mutate(result)
            with self.assertRaises(ResponseError):
                validate_result("procedure_events", result, self.identity)
        with self.assertRaises(ResponseError):
            validate_result("procedure_events", self.events, self.identity | {"after": 1})

    def test_event_payloads_cannot_claim_authority_or_contradict_delivery(self):
        result = copy.deepcopy(self.events)
        result["events"][0]["payload"]["principal"] = "admin"
        with self.assertRaises(ResponseError):
            validate_result("procedure_events", result, self.identity)
        result = copy.deepcopy(self.cancel_events)
        event = next(event for event in result["events"] if event["kind"] == "cancel_delivery")
        event["payload"] = {"operationId": None, "status": "denied", "code": None}
        with self.assertRaises(ResponseError):
            validate_result("procedure_events", result, self.cancel_identity)

    def test_strict_params_and_results_reject_unknown_authority_fields(self):
        for method, params in (("procedure_submit", self.params), ("procedure_status", self.identity),
                               ("procedure_cancel", self.identity), ("procedure_resume", self.identity),
                               ("procedure_events", self.identity)):
            with self.subTest(method=method), self.assertRaises(ContractError):
                validate_params(method, copy.deepcopy(params) | {"principal": "admin"})
        for path in ((), ("procedure",), ("procedure", "steps", 0), ("procedure", "steps", 0, "request")):
            request = copy.deepcopy(self.request)
            target = request
            for part in path:
                target = target[part]
            target["authorization"] = "approved"
            with self.assertRaises(ContractError):
                validate_params("procedure_submit", {"request": request})
        result = copy.deepcopy(self.completed)
        result["steps"][0]["result"] = {"physicalVerified": True}
        self.reject_status(result)

    def test_integer_profile_bounds_and_no_dynamic_branches(self):
        for field, value in (("after", True), ("after", 1.0), ("after", -1), ("limit", 101), ("limit", 0)):
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                validate_params("procedure_events", self.identity | {field: value})
        for value in (True, 2.0, -1, 17):
            result = copy.deepcopy(self.completed)
            result["cursor"] = value
            self.reject_status(result)
        request = copy.deepcopy(self.request)
        request["procedure"]["steps"][1]["branch"] = {"when": "previous.result > 0"}
        with self.assertRaises(ContractError):
            validate_params("procedure_submit", {"request": request})

    def test_client_does_not_retry_uncertain_procedure_submission(self):
        for behavior in (IpcError("TRANSPORT_TIMEOUT"), {"success": True}):
            options = {"side_effect": behavior} if isinstance(behavior, Exception) else {"return_value": behavior}
            with patch("hms.client.call", **options) as transport:
                with self.assertRaises((IpcError, ResponseError)):
                    Client("unused").request("procedure_submit", self.params)
                self.assertEqual(transport.call_count, 1)
                self.assertEqual(transport.call_args.args[1], "procedure_submit")
                self.assertEqual(transport.call_args.args[2], self.params)

    def test_schema_build_is_reproducible_for_procedure_methods(self):
        schema = json.loads((ROOT / "schemas/local-api.schema.json").read_text())
        self.assertEqual(schema, build())
        for method in ("procedure_submit", "procedure_status", "procedure_cancel", "procedure_resume", "procedure_events"):
            self.assertIn(method, schema["x-hms-method-results"])
            Draft202012Validator({"$ref": "#/$defs/" + method + "Params", "$defs": schema["$defs"]}).check_schema(schema)

    def test_mcp_catalog_annotations_and_schemas_match_authority_effects(self):
        tools = {tool["name"]: tool for tool in catalog()}
        for method in ("procedure_submit", "procedure_status", "procedure_cancel", "procedure_resume", "procedure_events"):
            tool = tools["hardware_" + method]
            mutation = method in {"procedure_submit", "procedure_cancel", "procedure_resume"}
            self.assertEqual(tool["annotations"]["readOnlyHint"], not mutation)
            self.assertEqual(tool["annotations"]["destructiveHint"], mutation)
            self.assertFalse(tool["annotations"]["idempotentHint"])
            self.assertFalse(tool["annotations"]["openWorldHint"])
            for field in ("inputSchema", "outputSchema"):
                Draft202012Validator.check_schema(tool[field])
        submit = tools["hardware_procedure_submit"]
        Draft202012Validator(submit["inputSchema"]).validate(self.params)
        Draft202012Validator(submit["outputSchema"]).validate({"ok": True, "result": self.accepted})
        self.assertFalse(Draft202012Validator(submit["inputSchema"]).is_valid(self.params | {"principal": "admin"}))

    def test_mcp_projects_bad_response_as_unconfirmed_once(self):
        class WrongClient:
            def __init__(self):
                self.calls = []

            def request(self, method, params):
                self.calls.append((method, copy.deepcopy(params)))
                return {"status": "complete"}

        client = WrongClient()
        output = queue.Queue()
        projection = Projection(client, output.put_nowait, clock=lambda: 1)
        try:
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "hardware_procedure_submit", "arguments": copy.deepcopy(self.params),
                "_meta": {PREFIX + "protocolVersion": MODERN, PREFIX + "clientCapabilities": {}}}}
            projection.receive(dumps(request).encode())
            response = output.get(timeout=2)
            structured = response["result"]["structuredContent"]
            self.assertFalse(structured["ok"])
            self.assertEqual(structured["error"], {"code": "INVALID_RESPONSE", "outcome": "unconfirmed"})
            self.assertEqual(client.calls, [("procedure_submit", self.params)])
        finally:
            projection.close()

    def test_cli_parses_explicit_file_identity_and_event_cursor(self):
        parsed = _parser().parse_args(["--socket", "socket", "procedure-submit", "--request-file", "bound.json"])
        self.assertEqual(parsed.request_file, Path("bound.json"))
        parsed = _parser().parse_args(["procedure-events", "procedure:retained", "--socket", "socket", "--after", "7", "--limit", "3"])
        self.assertEqual((parsed.procedure, parsed.after, parsed.limit), ("procedure:retained", 7, 3))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bound.json"
            path.write_bytes(canonical(self.request))
            with patch("hms.client.call", return_value=self.accepted) as transport, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["procedure-submit", "--socket", "socket", "--request-file", str(path)]), 0)
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(transport.call_args.args[1:3], ("procedure_submit", self.params))

    def test_cli_rejects_duplicate_json_fields_without_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"protocol":"hms.procedure/0.1","protocol":"hms.procedure/0.1"}')
            error = io.StringIO()
            with patch("hms.client.call") as transport, contextlib.redirect_stderr(error):
                self.assertEqual(cli_main(["procedure-submit", "--socket", "socket", "--request-file", str(path)]), 1)
            transport.assert_not_called()
            self.assertEqual(json.loads(error.getvalue())["error"]["code"], "INVALID_REQUEST")

    def test_cli_invalid_response_reports_uncertainty_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bound.json"
            path.write_bytes(canonical(self.request))
            error = io.StringIO()
            with patch("hms.client.call", return_value={"success": True}) as transport, contextlib.redirect_stderr(error):
                self.assertEqual(cli_main(["procedure-submit", "--socket", "socket", "--request-file", str(path)]), 1)
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(json.loads(error.getvalue())["error"]["code"], "INVALID_RESPONSE")
