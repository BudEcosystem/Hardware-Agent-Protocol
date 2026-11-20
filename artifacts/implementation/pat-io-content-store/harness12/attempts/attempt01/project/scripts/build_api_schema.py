#!/usr/bin/env python3
"""Generate the self-contained local API schema from explicit profile tables."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_INT = 2**53 - 1


def ref(name):
    return {"$ref": "#/$defs/" + name}


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


def array(items, maximum, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def mapping(schema, maximum, minimum=0):
    return {"type": "object", "propertyNames": ref("id"), "additionalProperties": schema,
            "minProperties": minimum, "maxProperties": maximum}


def build():
    host = json.loads((ROOT / "schemas/invoke.schema.json").read_text())
    definitions = copy.deepcopy(host.pop("$defs"))
    for key in ("$schema", "$id", "title"):
        host.pop(key)
    definitions["invoke"] = host
    identifier, tick = ref("id"), ref("tick")
    positive = {"type": "integer", "minimum": 1, "maximum": MAX_INT}
    boolean = {"type": "boolean"}
    digest = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}(?![\\s\\S])"}
    definitions.update(digest=digest, positive=positive)
    definitions["evidenceKind"] = {"enum": ["physical_sensor", "controller_measurement", "command_echo", "estimate", "simulation"]}
    definitions["clock"] = obj({"clockDomain": identifier, "clockEpoch": identifier, "ticksMs": tick})
    definitions["uncertainty"] = obj({"absolute": {"type": "number", "minimum": 0}, "unit": identifier, "method": identifier})
    definitions["observation"] = obj({
        "protocol": {"const": "hms.observation/0.1"}, "instanceId": identifier, "propertyId": identifier,
        "value": {}, "unit": identifier, "frame": nullable(identifier), "evidenceKind": ref("evidenceKind"),
        "source": identifier, "quality": {"enum": ["valid", "stale", "invalid", "unknown"]},
        "streamEpoch": identifier, "sequence": tick, "endpointSession": identifier, "controlGeneration": identifier,
        "bindingGeneration": identifier, "calibrationRevision": identifier, "acquisition": ref("clock"), "receipt": ref("clock"),
        "acquisitionLatencyBoundMs": nullable(tick), "clockUncertaintyMs": nullable(tick),
        "measurementUncertainty": nullable(ref("uncertainty")), "ageUpperBoundMs": nullable(tick)})
    definitions["operation"] = obj({
        "protocol": {"const": "hms.operation/0.1"}, "operationId": identifier, "requestDigest": digest,
        "instanceId": identifier, "actionId": identifier,
        "executionState": {"enum": ["accepted", "dispatching", "running", "outcome_unknown", "completed", "failed", "canceled", "rejected_before_dispatch", "rejected_before_start"]},
        "cancellationState": {"enum": ["not_requested", "requested", "acknowledged", "rejected", "confirmed"]},
        "effectVerification": {"enum": ["unverified", "verified", "failed", "disputed"]}, "mayHaveActed": boolean,
        "eventSequence": positive, "resourceClaims": array(obj({"resource": identifier, "fence": positive}), 32),
        "result": nullable(obj({"evidenceKind": {"enum": ["sensor", "controller", "simulation"]}, "output": {"type": "object"}}))})
    definitions["presence"] = obj({"session": identifier, "expires_ms": tick})
    definitions["inventoryItem"] = obj({"instanceId": identifier, "descriptionDigest": digest,
        "identityKind": {"enum": ["simulation", "gateway", "device"]}, "retired": boolean,
        "bindingGeneration": nullable(identifier), "bindingActive": boolean, "presence": nullable(ref("presence"))})
    definitions["discovery"] = obj({"items": array(ref("inventoryItem"), 100),
        "cursor": nullable({"type": "string", "minLength": 1, "maxLength": 1024}), "registryRevision": positive})
    definitions["valueSchema"] = obj({
        "type": {"enum": ["object", "array", "string", "number", "integer", "boolean", "null"]},
        "properties": mapping(ref("valueSchema"), 64), "required": array(identifier, 64),
        "additionalProperties": {"const": False}, "items": ref("valueSchema"),
        "minItems": tick, "maxItems": {"type": "integer", "minimum": 0, "maximum": 256},
        "minimum": {"type": "number"}, "maximum": {"type": "number"}, "enum": {"type": "array"}, "const": {},
        "minLength": tick, "maxLength": {"type": "integer", "minimum": 0, "maximum": 4096}}, ["type"])
    keyword_sets = {"object": {"properties", "required", "additionalProperties"},
                    "array": {"items", "minItems", "maxItems"}, "string": {"minLength", "maxLength"},
                    "number": {"minimum", "maximum"}, "integer": {"minimum", "maximum"},
                    "boolean": set(), "null": set()}
    mandatory = {"object": ["properties", "required", "additionalProperties"], "array": ["items", "maxItems"],
                 "string": ["maxLength"]}
    definitions["valueSchema"]["allOf"] = [
        {"if": {"properties": {"type": {"const": kind}}},
         "then": {"required": mandatory.get(kind, []),
                  "properties": {key: False for key in definitions["valueSchema"]["properties"]
                                 if key not in ({"type", "enum", "const"} | allowed)}}}
        for kind, allowed in keyword_sets.items()]
    definitions["propertyContract"] = obj({"schema": ref("valueSchema"), "unit": identifier, "frame": nullable(identifier)})
    definitions["actionContract"] = obj({"inputSchema": ref("valueSchema"), "resources": array(identifier, 32, 1),
        "effect": identifier, "maxRunMs": {"type": "integer", "minimum": 1, "maximum": 4294967295},
        "preconditions": array(obj({"property": identifier, "equals": {}, "maxAgeMs": {"type": "integer", "minimum": 0, "maximum": 600000},
                                    "evidenceKind": ref("evidenceKind")}), 32),
        "completionEvidence": array({"enum": ["controller", "sensor", "simulation"]}, 32, 1)})
    features = ["binding-generations/1", "durable-operations/1", "host-invoke/0.1", "physical-evidence/1"]
    definitions["executionContract"] = obj({"profile": {"const": "hms.execution-contract/0.1"},
        "requiredFeatures": array({"enum": features}, 4, 4) | {"uniqueItems": True}, "capabilities": array(identifier, 16, 1),
        "properties": mapping(ref("propertyContract"), 32, 1), "actions": mapping(ref("actionContract"), 32, 1)})
    definitions["typeBundle"] = obj({"profile": {"const": "hms.type-bundle/0.1"}, "td": {"type": "object"},
                                     "execution": ref("executionContract")})
    definitions["binding"] = obj({"profile": {"const": "hms.binding/0.1"}, "instanceId": identifier, "generation": identifier,
        "typeDigest": digest, "calibrationRevision": identifier, "controlGeneration": identifier,
        "mode": {"enum": ["simulation", "uncommissioned"]}, "adapterId": identifier,
        "resourceMap": mapping(identifier, 1024, 1), "argumentSchemas": mapping(ref("valueSchema"), 32, 1)})
    definitions["instance"] = obj({"id": identifier, "deployment": identifier, "type_digest": digest,
        "identity_kind": {"enum": ["simulation", "gateway", "device"]}, "identity_ref": identifier,
        "retired": {"type": "integer", "enum": [0, 1]}})
    definitions["description"] = obj({"instance": ref("instance"), "descriptionDigest": digest, "type": ref("typeBundle"),
        "binding": nullable(ref("binding")), "bindingActive": boolean, "presence": nullable(ref("presence")), "registryRevision": positive})
    definitions["namespace"] = obj({"token": identifier, "epoch": positive, "expiresUnixMs": tick, "authorityId": identifier})
    definitions["prepared"] = obj({"request": ref("invoke"), "requestDigest": digest, "admitted": {"const": False}})
    assertions = ["running", "completed", "failed", "terminated", "cancel_ack", "resources_quiescent", "physical_verified", "verification_failed", "disputed", "start_excluded"]
    definitions["evidence"] = obj({"kind": {"enum": ["sensor", "controller", "simulation", "runtime"]},
        "source": identifier, "reference": identifier, "assertions": array({"enum": assertions}, 32, 1)})
    payloads = {
        "accepted": obj({"digest": digest}), "dispatch_claimed": obj({"attemptId": identifier, "ownerEpoch": positive}),
        "execution_evidence": obj({"state": {"enum": ["running", "completed", "failed", "canceled", "rejected_before_start"]}, "evidence": ref("evidence")}),
        "reconciled": obj({"state": {"enum": ["running", "completed", "failed", "canceled", "rejected_before_start"]}, "evidence": ref("evidence")}),
        "canceled_before_dispatch": obj({"proof": {"const": "exclusive_accepted_state"}}), "cancel_requested": obj({}),
        "cancel_ack": obj({"accepted": boolean, "evidence": ref("evidence")}),
        "resources_released": obj({"evidence": ref("evidence")}), "evidence_dispute": obj({"evidence": ref("evidence")}),
        **{name: obj({"reason": identifier}) for name in ("recovery_unknown", "outcome_unknown", "rejected_before_dispatch")}}
    definitions["event"] = {"oneOf": [obj({"operation_id": identifier, "sequence": positive, "time_ms": tick,
        "clock_status": {"enum": ["unqualified_host_clock", "regressed_clamped", "unavailable_clamped"]},
        "kind": {"const": name}, "payload": payload}) for name, payload in payloads.items()]}
    definitions["events"] = obj({"events": array(ref("event"), 100), "next": tick, "head": tick, "gap": {"const": False}})
    definitions["procedureTiming"] = obj({name: tick for name in
        ("notBeforeUnixMs", "latestStartUnixMs", "latestCompletionUnixMs")})
    definitions["procedureRequest"] = obj({"protocol": {"const": "hms.procedure/0.1"},
        "replayNamespace": identifier, "procedureKey": identifier,
        "procedure": obj({"profile": {"const": "hms.bound-sequence/0.1"},
            "timing": ref("procedureTiming"), "steps": array(obj({"stepId": identifier,
                "request": ref("invoke")}), 16, 1)})})
    definitions["procedureState"] = {"enum": ["accepted", "running", "interrupted", "completed", "failed", "canceled", "expired"]}
    definitions["procedureStep"] = obj({"stepId": identifier,
        "ordinal": {"type": "integer", "minimum": 0, "maximum": 15},
        "requestDigest": digest, "operationId": nullable(identifier),
        "executionState": {"enum": ["unstarted", *definitions["operation"]["properties"]["executionState"]["enum"]]},
        "cancellationState": copy.deepcopy(definitions["operation"]["properties"]["cancellationState"]),
        "effectVerification": copy.deepcopy(definitions["operation"]["properties"]["effectVerification"]),
        "mayHaveActed": boolean, "heldResources": {"type": "integer", "minimum": 0, "maximum": 32},
        "eventSequence": tick})
    definitions["procedureStatus"] = obj({"protocol": {"const": "hms.procedure-status/0.1"},
        "procedureId": identifier, "requestDigest": digest, "profile": {"const": "hms.bound-sequence/0.1"},
        "executionState": ref("procedureState"), "cancelRequested": boolean, "cancelBlockedCode": nullable(identifier),
        "reason": nullable(identifier), "timing": ref("procedureTiming"),
        "cursor": {"type": "integer", "minimum": 0, "maximum": 16},
        "stepCount": {"type": "integer", "minimum": 1, "maximum": 16}, "eventSequence": positive,
        "mayHaveActed": boolean, "aggregateVerification": {"enum": ["unverified", "failed", "disputed"]},
        "unresolvedOperations": array(identifier, 16), "steps": array(ref("procedureStep"), 16, 1)})
    definitions["procedureCancel"] = obj({"protocol": {"const": "hms.procedure-cancel/0.1"},
        "procedureId": identifier, "executionState": ref("procedureState"), "cancelRequested": boolean,
        "cancelBlockedCode": nullable(identifier), "eventSequence": positive,
        "delivery": obj({"operationId": nullable(identifier),
            "status": {"enum": ["no_active_child", "recorded", "denied", "already_terminal"]},
            "code": nullable(identifier)})})
    procedure_payloads = {
        "accepted": obj({"requestDigest": digest, "stepCount": {"type": "integer", "minimum": 1, "maximum": 16}}),
        "state_changed": obj({"state": ref("procedureState"), "reason": nullable(identifier)}),
        "child_admitted": obj({"stepId": identifier, "ordinal": {"type": "integer", "minimum": 0, "maximum": 15},
                              "operationId": identifier}),
        "cursor_advanced": obj({"cursor": {"type": "integer", "minimum": 1, "maximum": 16}}),
        "cancel_requested": obj({}),
        "cancel_delivery": copy.deepcopy(definitions["procedureCancel"]["properties"]["delivery"])}
    definitions["procedureEvent"] = {"oneOf": [obj({"procedure_id": identifier, "sequence": positive, "time_ms": tick,
        "clock_status": {"enum": ["unqualified_host_clock", "regressed_clamped", "unavailable_clamped"]},
        "kind": {"const": name}, "payload": payload}) for name, payload in procedure_payloads.items()]}
    definitions["procedureEvents"] = obj({"protocol": {"const": "hms.procedure-events/0.1"},
        "procedureId": identifier, "events": array(ref("procedureEvent"), 100),
        "next": tick, "head": tick, "gap": {"const": False}})
    definitions["error"] = obj({"code": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,63}(?![\\s\\S])"}})
    params = {
        "discover": obj({"capability": identifier, "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                         "cursor": {"type": "string", "minLength": 1, "maxLength": 1024}}, []),
        "describe": obj({"instanceId": identifier, "digest": digest}, ["instanceId"]),
        "observe": obj({"instanceId": identifier, "property": identifier, "maxAgeMs": {"type": "integer", "minimum": 0, "maximum": 600000},
                        "evidenceKind": ref("evidenceKind")}, ["instanceId", "property"]),
        "namespace": obj({"expiresUnixMs": tick}), "invoke": obj({"request": ref("invoke")}),
        "operation": obj({"operationId": identifier}), "cancel": obj({"operationId": identifier}),
        "events": obj({"operationId": identifier, "after": tick, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["operationId"]),
        "prepare": obj({"instanceId": identifier, "actionId": identifier, "arguments": {"type": "object"},
            "operationKey": identifier, "replayNamespace": identifier,
            "timing": copy.deepcopy(definitions["intent"]["properties"]["timing"]),
            "requiredEffect": {"enum": ["capability_completion", "physical_verified"]}})}
    results = {"discover": "discovery", "describe": "description", "observe": "observation", "namespace": "namespace",
               "prepare": "prepared", "invoke": "operation", "operation": "operation", "cancel": "operation", "events": "events"}
    params.update(procedure_submit=obj({"request": ref("procedureRequest")}),
                  procedure_status=obj({"procedureId": identifier}),
                  procedure_cancel=obj({"procedureId": identifier}),
                  procedure_resume=obj({"procedureId": identifier}),
                  procedure_events=obj({"procedureId": identifier, "after": tick,
                      "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["procedureId"]))
    results.update(procedure_submit="procedureStatus", procedure_status="procedureStatus",
                   procedure_resume="procedureStatus", procedure_cancel="procedureCancel",
                   procedure_events="procedureEvents")
    for name, schema in params.items():
        definitions[name + "Params"] = schema
    definitions["request"] = {"oneOf": [obj({"protocol": {"const": "hctl.local/0.1"}, "requestId": identifier,
        "method": {"const": name}, "params": ref(name + "Params")}) for name in params]}
    definitions["response"] = {"oneOf": [
        obj({"protocol": {"const": "hctl.local/0.1"}, "requestId": identifier,
             "result": {"anyOf": [ref(name) for name in sorted(set(results.values()))]}}),
        obj({"protocol": {"const": "hctl.local/0.1"}, "requestId": nullable(identifier), "error": ref("error")})]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/hms/schema/local-api/0.1",
            "title": "Experimental HMS local API", "oneOf": [ref("request"), ref("response")],
            "$comment": "All references are local. Host JSON byte/tree/numeric limits and method-specific semantic checks also apply.",
            "$defs": definitions, "x-hms-method-results": results}


if __name__ == "__main__":
    destination = ROOT / "schemas/local-api.schema.json"
    destination.write_text(json.dumps(build(), indent=2) + "\n")
    print(destination.relative_to(ROOT))
