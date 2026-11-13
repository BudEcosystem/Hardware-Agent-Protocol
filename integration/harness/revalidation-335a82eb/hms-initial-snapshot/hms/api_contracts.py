"""Method-specific schemas and cross-field checks for the local API.

Validation establishes profile consistency, not physical truth or authority.
All schema references are retained local fragments; no remote resolution occurs.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError

from .contracts import ContractError, canonical, intent_digest, parse_invoke
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
        if method in {"invoke", "operation", "cancel"}:
            state = result["executionState"]
            resources = [claim["resource"] for claim in result["resourceClaims"]]
            _require(resources == sorted(set(resources)))
            if state in {"accepted", "dispatching", "running", "outcome_unknown"}:
                _require(bool(resources))
            if state in {"accepted", "rejected_before_dispatch"}:
                _require(not result["mayHaveActed"] and result["result"] is None and result["cancellationState"] == "not_requested")
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
            if result["result"] is not None and result["result"]["evidenceKind"] == "simulation":
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
                        assertion = {"running": "running", "completed": "completed", "failed": "failed", "canceled": "terminated"}[event["payload"]["state"]]
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
