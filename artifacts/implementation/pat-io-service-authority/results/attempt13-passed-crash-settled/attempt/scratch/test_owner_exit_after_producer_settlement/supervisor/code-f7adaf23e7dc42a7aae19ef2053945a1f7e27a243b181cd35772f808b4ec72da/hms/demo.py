"""Synthetic home, microscope and manufacturing contracts; no physical limits."""
import copy

from .contracts import canonical
from .projections import data_schema, invoke_td_input
from .registry import FEATURES


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _td_schema(schema):
    """TD DataSchema projection: strict closure stays in execution contract."""
    return data_schema(schema)


def type_bundle(name, action_id, argument_schema, property_schema, *, unit, effect, resource):
    execution = {
        "profile": "hms.execution-contract/0.1", "requiredFeatures": sorted(FEATURES),
        "capabilities": ["sim:" + name],
        "properties": {"value": {"schema": property_schema, "unit": unit, "frame": "sim:" + name},
                       "ready": {"schema": {"type": "boolean"}, "unit": "1", "frame": None}},
        "actions": {action_id: {"inputSchema": argument_schema, "resources": [resource], "effect": effect,
                                "maxRunMs": 5000, "completionEvidence": ["simulation"],
                                "preconditions": [{"property": "ready", "equals": True, "maxAgeMs": 1000,
                                                   "evidenceKind": "simulation"}]}},
    }
    invoke_input = invoke_td_input(argument_schema)
    td = {
        "@context": ["https://www.w3.org/2022/wot/td/v1.1", {"hms": "https://example.invalid/hms/vocab#"}],
        "id": "urn:bud:hms:sim:" + name, "title": "Simulated " + name,
        "description": "Synthetic executable fixture; no hardware calibration or commissioned physical limits.",
        "securityDefinitions": {"local_os": {"scheme": "nosec"}}, "security": ["local_os"],
        "hms:commissioned": False,
        "properties": {key: (_td_schema(value["schema"]) | {"readOnly": True, "unit": value["unit"], "hms:coordinateFrame": value["frame"],
                     "forms": [{"href": f"https://example.invalid/simulation/{name}/properties/{key}", "op": "readproperty"}]})
                       for key, value in execution["properties"].items()},
        "actions": {action_id: {"input": invoke_input, "safe": False, "idempotent": False, "synchronous": False,
                                "forms": [{"href": f"https://example.invalid/simulation/{name}/actions/{action_id}", "op": "invokeaction"}]}},
    }
    return {"profile": "hms.type-bundle/0.1", "td": td, "execution": execution}


def definitions():
    number = {"type": "number", "minimum": 0, "maximum": 100}
    exact_unit = lambda unit: {"type": "string", "const": unit, "maxLength": 16}
    return [
        ("sim:home-fan", "set_level", type_bundle("home-fan", "set_level",
         object_schema({"level": number, "unit": exact_unit("percent")}), number,
         unit="percent", effect="setpoint", resource="fan-control")),
        ("sim:microscope", "move_absolute", type_bundle("microscope", "move_absolute",
         object_schema({"position": number, "unit": exact_unit("um"),
                        "frame": {"type": "string", "const": "sim:microscope", "maxLength": 64}}), number,
         unit="um", effect="motion", resource="focus-zone")),
        ("sim:inspection-cell", "inspect", type_bundle("inspection-cell", "inspect",
         object_schema({"recipe": {"type": "integer", "enum": [1, 2]},
                        "partId": {"type": "string", "minLength": 1, "maxLength": 64}}),
         {"type": "integer", "minimum": 0, "maximum": 1000000}, unit="1", effect="inspection", resource="cell-zone")),
    ]


def install(registry, owner):
    for instance_id, action_id, document in definitions():
        digest = registry.publish_type(owner, canonical(document))
        registry.enroll(owner, instance_id, digest, identity_kind="simulation", identity_ref=instance_id)
        actions = document["execution"]["actions"]
        resource_map = {role: instance_id + ":" + role for action in actions.values() for role in action["resources"]}
        binding = {"profile": "hms.binding/0.1", "instanceId": instance_id, "generation": "sim-binding:1",
                   "typeDigest": digest, "calibrationRevision": "synthetic:1", "controlGeneration": "sim-control:1",
                   "mode": "simulation", "adapterId": "simulator:local", "resourceMap": resource_map,
                   "argumentSchemas": {name: copy.deepcopy(action["inputSchema"]) for name, action in actions.items()}}
        registry.bind(owner, canonical(binding))
