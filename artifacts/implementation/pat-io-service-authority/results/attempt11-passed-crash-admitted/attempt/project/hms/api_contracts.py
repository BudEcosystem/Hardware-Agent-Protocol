"""Method-specific schemas and cross-field checks for the local API.

Validation establishes profile consistency, not physical truth or authority.
All schema references are retained local fragments; no remote resolution occurs.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError

from .contracts import ContractError, canonical, identifier, intent_digest, parse_invoke
from .journal import JournalError

_SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas/local-api.schema.json").read_text())
Draft202012Validator.check_schema(_SCHEMA)
_STRICT = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int))
METHOD_RESULTS = dict(_SCHEMA["x-hms-method-results"])
_VALIDATORS = {name: _STRICT({"$ref": "#/$defs/" + name, "$defs": _SCHEMA["$defs"]})
               for name in {*METHOD_RESULTS.values(), *(method + "Params" for method in METHOD_RESULTS), "error"}}


class ResponseError(ContractError):
    """A reply cannot be used as domain evidence; admission may already exist."""


def _shape(name, value):
    canonical(value)  # Host byte/tree/numeric profile is stricter than JSON Schema.
    if next(_VALIDATORS[name].iter_errors(value), None) is not None:
        raise ContractError("local API schema mismatch: " + name)


def validate_params(method, params):
    if method not in METHOD_RESULTS:
        raise ContractError("unknown local method")
    _shape(method + "Params", params)
    if method == "invoke":
        parse_invoke(canonical(params["request"]))
    elif method == "procedure_submit":
        from .procedures import parse_procedure
        parse_procedure(params["request"])
    elif method == "prepare":
        timing = params["timing"]
        if not timing["notBeforeUnixMs"] <= timing["latestStartUnixMs"] <= timing["latestCompletionUnixMs"]:
            raise ContractError("inconsistent preparation timing")


def _require(condition):
    if not condition:
        raise ResponseError("inconsistent local API result")


def _equal(left, right):
    return canonical(left) == canonical(right)


def _evidence(value):
    assertions = set(value["assertions"])
    _require(not {"physical_verified", "verification_failed"} <= assertions)
    if "physical_verified" in assertions:
        _require(value["kind"] in {"sensor", "controller"})


def _synthetic_io_result(operation, output):
    """Check a historical finite-I/O receipt projection, never current pad state.

    Activation can precede cancellation. A completed board cycle can also be
    retained before authority settlement, so the reverse state implication is
    deliberately absent. Receipt identity/authenticity is checked by the
    installed adapter; this boundary establishes only typed profile consistency.
    """
    _require(set(output) == {"profile", "primitive", "result", "safeIdleState", "receiptDigest"})
    _require(output["profile"] == "hms.synthetic-io-result/1")
    _require(type(output["primitive"]) is str and output["primitive"] in {"gpio_pulse", "pwm_burst"})
    digest = output["receiptDigest"]
    _require(type(digest) is str and len(digest) == 71 and digest.startswith("sha256:") and
             all(character in "0123456789abcdef" for character in digest[7:]))
    result = output["result"]
    _require(type(result) is dict and set(result) == {"activationCommitted", "cycleCompleted", "safeIdle", "reason"})
    _require(all(type(result[key]) is bool for key in ("activationCommitted", "cycleCompleted", "safeIdle")))
    _require(result["activationCommitted"] and result["safeIdle"] and operation["mayHaveActed"])
    if result["cycleCompleted"]:
        _require(result["reason"] is None)
    else:
        identifier(result["reason"])
    if operation["executionState"] == "completed":
        _require(result["cycleCompleted"])
    elif operation["executionState"] in {"canceled", "failed"}:
        _require(not result["cycleCompleted"])
    idle = output["safeIdleState"]
    _require(type(idle) is dict and 1 <= len(idle) <= 32)
    shapes = {
        "pin": {"kind": "pin", "mode": "high_impedance", "level": None},
        "timer": {"kind": "timer", "enabled": False, "frequencyHz": 0, "resolutionBits": 0},
        "timer_channel": {"kind": "timer_channel", "enabled": False, "dutyPermille": 0},
    }
    kinds = []
    for resource, leaf in idle.items():
        identifier(resource)
        _require(type(leaf) is dict and type(leaf.get("kind")) is str and leaf["kind"] in shapes)
        expected = shapes[leaf["kind"]]
        _require(set(leaf) == set(expected))
        # Canonicalization alone would equate 0.0 with 0; retain exact types.
        _require(all(type(leaf[key]) is type(value) and leaf[key] == value for key, value in expected.items()))
        kinds.append(leaf["kind"])
    _require(sorted(kinds) == (["pin"] if output["primitive"] == "gpio_pulse" else
                               ["pin", "timer", "timer_channel"]))


def _description(result):
    from .registry import validate_type_bundle, schema_profile
    bundle = result["type"]
    digest = validate_type_bundle(bundle)
    _require(digest == result["descriptionDigest"] == result["instance"]["type_digest"])
    binding = result["binding"]
    if binding is None:
        _require(not result["bindingActive"] and result["presence"] is None)
    else:
        _require(binding["instanceId"] == result["instance"]["id"] and binding["typeDigest"] == digest)
        if binding["mode"] == "simulation":
            _require(result["instance"]["identity_kind"] == "simulation")
        for schema in binding["argumentSchemas"].values():
            schema_profile(schema)
    if not result["bindingActive"]:
        _require(result["presence"] is None)
    execution = bundle["execution"]
    if binding is not None:
        roles = {role for action in execution["actions"].values() for role in action["resources"]}
        _require(set(binding["resourceMap"]) == roles and set(binding["argumentSchemas"]) == set(execution["actions"]))


def _procedure_status(result):
    steps = result["steps"]
    _require(len(steps) == result["stepCount"] and result["cursor"] <= len(steps))
    _require(len({step["stepId"] for step in steps}) == len(steps))
    _require([step["ordinal"] for step in steps] == list(range(len(steps))))
    timing = result["timing"]
    _require(timing["notBeforeUnixMs"] <= timing["latestStartUnixMs"] <= timing["latestCompletionUnixMs"])
    linked = [step["operationId"] for step in steps if step["operationId"] is not None]
    _require(len(linked) == len(set(linked)))
    _require(all(step["operationId"] is not None for step in steps[:len(linked)]))
    _require(max(0, len(linked) - 1) <= result["cursor"] <= len(linked))
    _require(all(step["executionState"] == "completed" and not step["heldResources"]
                 for step in steps[:result["cursor"]]))
    if result["executionState"] == "accepted":
        _require(not linked and result["cursor"] == 0)
    elif result["executionState"] == "running":
        _require(bool(linked))
    if result["cancelRequested"]:
        _require(result["executionState"] in {"completed", "failed", "canceled", "expired"})
    unresolved = []
    for step in steps:
        state = step["executionState"]
        if step["operationId"] is None:
            _require(state == "unstarted" and step["eventSequence"] == 0 and not step["mayHaveActed"] and
                     step["heldResources"] == 0 and step["effectVerification"] == "unverified" and
                     step["cancellationState"] == "not_requested")
            continue
        _require(state != "unstarted" and step["eventSequence"] > 0)
        if state in {"accepted", "dispatching", "running", "outcome_unknown"}:
            _require(step["heldResources"] > 0)
        if state in {"accepted", "rejected_before_dispatch", "rejected_before_start"}:
            _require(not step["mayHaveActed"])
        elif state != "canceled":
            _require(step["mayHaveActed"])
        if state in {"accepted", "rejected_before_dispatch"}:
            _require(step["cancellationState"] == "not_requested")
        if state == "rejected_before_start":
            _require(step["heldResources"] == 0)
        if state == "rejected_before_dispatch" or (state == "canceled" and not step["mayHaveActed"]):
            _require(step["heldResources"] == 0)
        if state == "canceled":
            _require(step["cancellationState"] == "confirmed")
        if step["cancellationState"] == "confirmed":
            _require(state == "canceled")
        if not step["mayHaveActed"]:
            _require(step["effectVerification"] == "unverified")
        if (step["heldResources"] or state in {"accepted", "dispatching", "running", "outcome_unknown"} or
                step["effectVerification"] in {"failed", "disputed"}):
            unresolved.append(step["operationId"])
    _require(result["mayHaveActed"] == any(step["mayHaveActed"] for step in steps))
    _require(result["unresolvedOperations"] == unresolved)
    verifications = {step["effectVerification"] for step in steps}
    expected = "disputed" if "disputed" in verifications else "failed" if "failed" in verifications else "unverified"
    _require(result["aggregateVerification"] == expected)
    if result["executionState"] == "completed":
        # Completion is a historical control transition. A later evidence
        # dispute remains visible without rewriting that history.
        _require(result["cursor"] == len(steps) and
                 all(step["executionState"] == "completed" and not step["heldResources"] for step in steps))
    if result["executionState"] == "canceled":
        _require(result["cancelRequested"])


def _procedure_events(result, params):
    events = result["events"]
    _require(result["next"] <= result["head"])
    _require(all(event["procedure_id"] == result["procedureId"] for event in events))
    for event in events:
        if event["kind"] == "cancel_delivery":
            _cancel_delivery(event["payload"])
    if events:
        _require(all(event["sequence"] == events[0]["sequence"] + index for index, event in enumerate(events)))
        _require(result["next"] == events[-1]["sequence"])
    else:
        _require(result["next"] == result["head"])
    _require(all(right["time_ms"] >= left["time_ms"] for left, right in zip(events, events[1:])))
    if params is not None:
        after = params.get("after", 0)
        _require(result["procedureId"] == params["procedureId"] and after <= result["head"] and
                 len(events) <= params.get("limit", 100) and result["next"] == after + len(events))


def _cancel_delivery(delivery):
    _require((delivery["operationId"] is None) == (delivery["status"] == "no_active_child"))
    _require((delivery["code"] is not None) == (delivery["status"] == "denied"))


def validate_result(method, result, params=None):
    """Validate one response, optionally correlating it with its exact request.

    Callers must preserve replay identity on any failure after a mutation was
    sent. This function never retries, grants authority or verifies a sensor.
    """
    try:
        if method not in METHOD_RESULTS:
            raise ContractError("unknown local method")
        _shape(METHOD_RESULTS[method], result)
        if params is not None:
            validate_params(method, params)
        if method in {"procedure_submit", "procedure_status", "procedure_resume"}:
            _procedure_status(result)
            if params is not None:
                if method == "procedure_submit":
                    from .procedures import procedure_digest
                    request = params["request"]
                    _require(result["requestDigest"] == procedure_digest(request))
                    _require(_equal(result["timing"], request["procedure"]["timing"]))
                    _require(len(result["steps"]) == len(request["procedure"]["steps"]))
                    for projected, retained in zip(result["steps"], request["procedure"]["steps"]):
                        _require(projected["stepId"] == retained["stepId"] and
                                 projected["requestDigest"] == intent_digest(retained["request"]["intent"]))
                else:
                    _require(result["procedureId"] == params["procedureId"])
        elif method == "procedure_cancel":
            _require(result["cancelRequested"])
            _require(result["executionState"] in {"completed", "failed", "canceled", "expired"})
            delivery = result["delivery"]
            _cancel_delivery(delivery)
            _require(result["cancelBlockedCode"] == delivery["code"])
            if params is not None:
                _require(result["procedureId"] == params["procedureId"])
        elif method == "procedure_events":
            _procedure_events(result, params)
        elif method in {"invoke", "operation", "cancel"}:
            state = result["executionState"]
            resources = [claim["resource"] for claim in result["resourceClaims"]]
            _require(resources == sorted(set(resources)))
            if state in {"accepted", "dispatching", "running", "outcome_unknown"}:
                _require(bool(resources))
            if state in {"accepted", "rejected_before_dispatch"}:
                _require(not result["mayHaveActed"] and result["result"] is None and result["cancellationState"] == "not_requested")
            elif state == "rejected_before_start":
                _require(not result["mayHaveActed"] and not resources and result["result"] is None)
            elif state != "canceled":
                _require(result["mayHaveActed"])
            if state == "canceled":
                _require(result["cancellationState"] == "confirmed")
            if result["cancellationState"] == "confirmed":
                _require(state == "canceled")
            if state == "rejected_before_dispatch" or (state == "canceled" and not result["mayHaveActed"]):
                _require(not resources)
            if result["effectVerification"] == "verified":
                _require(result["result"] is not None and result["result"]["evidenceKind"] in {"sensor", "controller"})
            if not result["mayHaveActed"]:
                _require(result["result"] is None and result["effectVerification"] == "unverified")
            if result["result"] is not None and "profile" in result["result"]["output"]:
                _require(result["result"]["evidenceKind"] == "simulation")
                _synthetic_io_result(result, result["result"]["output"])
            elif result["result"] is not None and result["result"]["evidenceKind"] == "simulation":
                _require(result["effectVerification"] != "verified")
                output = result["result"]["output"]
                _require(type(output.get("effectCommitted")) is bool)
                if state == "completed":
                    _require(output["effectCommitted"])
                elif state in {"canceled", "failed"}:
                    _require(not output["effectCommitted"])
            if params is not None:
                if method == "invoke":
                    intent = params["request"]["intent"]
                    _require(result["requestDigest"] == intent_digest(intent) and result["instanceId"] == intent["instanceId"] and
                             result["actionId"] == intent["actionId"])
                else:
                    _require(result["operationId"] == params["operationId"])
        elif method == "observe":
            _require(result["receipt"]["clockDomain"] == "host-monotonic")
            uncertainty, age = result["measurementUncertainty"], result["ageUpperBoundMs"]
            if uncertainty is not None:
                _require(uncertainty["unit"] == result["unit"])
            if age is None:
                _require(result["quality"] == "unknown")
            else:
                _require(result["acquisitionLatencyBoundMs"] is not None and result["clockUncertaintyMs"] is not None)
                _require(age >= result["acquisitionLatencyBoundMs"] + result["clockUncertaintyMs"])
            if params is not None:
                _require(result["instanceId"] == params["instanceId"] and result["propertyId"] == params["property"])
                if "evidenceKind" in params:
                    _require(result["evidenceKind"] == params["evidenceKind"])
                if "maxAgeMs" in params:
                    _require(result["quality"] == "valid" and age is not None and age <= params["maxAgeMs"])
        elif method == "discover":
            ids = [item["instanceId"] for item in result["items"]]
            _require(ids == sorted(set(ids)))
            _require(result["cursor"] is None or bool(ids))
            for item in result["items"]:
                if item["bindingActive"]:
                    _require(item["bindingGeneration"] is not None)
                if item["presence"] is not None:
                    _require(item["bindingActive"] and item["bindingGeneration"] is not None)
            if params is not None:
                _require(len(ids) <= params.get("limit", 20))
        elif method == "describe":
            _description(result)
            if params is not None:
                _require(result["instance"]["id"] == params["instanceId"])
                if "digest" in params:
                    _require(result["descriptionDigest"] == params["digest"])
        elif method == "namespace":
            _require(result["token"].split(":")[:3] == ["replay", result["authorityId"], str(result["epoch"])])
            _require(len(result["token"].split(":")) == 4)
            if params is not None:
                _require(result["expiresUnixMs"] == params["expiresUnixMs"])
        elif method == "prepare":
            request = parse_invoke(canonical(result["request"]))
            _require(result["requestDigest"] == intent_digest(request["intent"]))
            if params is not None:
                for field in ("replayNamespace", "operationKey"):
                    _require(request[field] == params[field])
                for field in ("instanceId", "actionId", "arguments", "timing", "requiredEffect"):
                    _require(_equal(request["intent"][field], params[field]))
        elif method == "events":
            events = result["events"]
            _require(result["next"] <= result["head"])
            if events:
                _require(all(event["sequence"] == events[0]["sequence"] + index for index, event in enumerate(events)))
                _require(result["next"] == events[-1]["sequence"])
                _require(len({event["operation_id"] for event in events}) == 1)
            else:
                _require(result["next"] == result["head"])
            for event in events:
                if "evidence" in event["payload"]:
                    _evidence(event["payload"]["evidence"])
                    evidence = event["payload"]["evidence"]
                    assertions = set(evidence["assertions"])
                    if event["kind"] in {"execution_evidence", "reconciled"}:
                        assertion = {"running": "running", "completed": "completed", "failed": "failed", "canceled": "terminated",
                                     "rejected_before_start": "start_excluded"}[event["payload"]["state"]]
                        _require(assertion in assertions and evidence["kind"] != "runtime")
                    elif event["kind"] == "resources_released":
                        _require("resources_quiescent" in assertions)
                    elif event["kind"] == "evidence_dispute":
                        _require("disputed" in assertions)
                    elif event["kind"] == "cancel_ack":
                        _require("cancel_ack" in assertions)
            _require(all(right["time_ms"] >= left["time_ms"] for left, right in zip(events, events[1:])))
            if params is not None:
                after = params.get("after", 0)
                _require(after <= result["head"] and len(events) <= params.get("limit", 100))
                _require(result["next"] == after + len(events))
                _require(all(event["operation_id"] == params["operationId"] for event in events))
        return result
    except ResponseError:
        raise
    except (ContractError, JournalError, SchemaError, KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise ResponseError("invalid local API result") from error
