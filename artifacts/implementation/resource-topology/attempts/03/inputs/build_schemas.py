"""Generate the original closed staged schemas; semantic graph checks are Python."""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = {"type": "string", "maxLength": 128, "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}(?![\s\S])"}
DIGEST = {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}(?![\s\S])"}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def array(item, maximum, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum, "uniqueItems": True}


def mapping(item, maximum, minimum=0):
    return {"type": "object", "propertyNames": NAME, "additionalProperties": item,
            "minProperties": minimum, "maxProperties": maximum}


def closed(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def document(profile, properties):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:bud:hms:schema:" + profile.removeprefix("hms.").replace("/", ":"),
        "description": "Staged synthetic shape contract. Python additionally enforces exact integer types, byte bounds, references and closure semantics.",
        **closed({"profile": {"const": profile}, **properties})}


def schemas():
    electrical = closed({"evidenceMode": {"const": "simulation"}, "nominalMilliVolt": integer(1, 5000),
        "maxSourceMicroAmp": integer(0, 20000), "maxSinkMicroAmp": integer(0, 20000),
        "modes": array({"enum": ["digital_input", "push_pull_output", "pwm_output"]}, 3, 1),
        "idleMode": {"const": "high_impedance"}})
    variants = {
        "hub": closed({}), "board": closed({}),
        "service": closed({"serviceProfile": {"const": "synthetic-service/0.1"}}),
        "driver": closed({"driverProfile": {"const": "synthetic-io-hub/0.1"}, "implementationDigest": DIGEST}),
        "pin": closed({"electrical": electrical}),
        "timer": closed({"minFrequencyHz": integer(1, 1000000), "maxFrequencyHz": integer(1, 1000000), "resolutionBits": integer(1, 16)}),
        "timer_channel": closed({"timer": NAME, "pin": NAME}),
        "bus": closed({"busProfile": {"const": "synthetic-i2c/0.1"}, "pins": array(NAME, 128, 1),
            "minRateHz": integer(1, 1000000), "maxRateHz": integer(1, 1000000), "addressBits": {"const": 7, "type": "integer"}}),
        "bus_address": closed({"bus": NAME, "address": integer(0, 127)}),
        "gpio_access": closed({"pin": NAME}), "pwm_access": closed({"channel": NAME}),
        "timer_access": closed({"timer": NAME}),
        "bus_access": closed({"bus": NAME, "addressNode": {"anyOf": [NAME, {"type": "null"}]}}),
    }
    node = {"oneOf": [closed({"kind": {"const": kind}, "contains": array(NAME, 128),
        "requires": array(NAME, 128), "properties": properties}) for kind, properties in variants.items()]}
    topology = document("hms.resource-topology/0.1", {"topologyId": NAME, "deployment": NAME,
        "nodes": mapping(node, 128, 1),
        "atoms": mapping(closed({"node": NAME, "purpose": {"enum": ["exclusive_hardware", "lifecycle"]}}), 128),
        "aliases": mapping(closed({"node": NAME, "includes": array(NAME, 384, 1)}), 256),
        "consumers": array(closed({"instanceId": NAME, "actionId": NAME, "rootAliases": array(NAME, 256, 1),
                                    "requires": array(NAME, 128)}), 128)})
    generations = document("hms.resource-generations/0.1", {"topologyDigest": DIGEST,
        "revision": integer(1, 9007199254740991), "nodes": mapping(NAME, 128, 1)})
    proof = document("hms.resource-binding-proof/0.1", {"instanceId": NAME, "bindingGeneration": NAME,
        "topologyDigest": DIGEST, "actionRoots": mapping(array(NAME, 256, 1), 128, 1),
        "expandedClaims": mapping(array(NAME, 32, 1), 128, 1), "dependencies": mapping(NAME, 128, 1),
        "closureDigest": DIGEST})
    return {"resource-topology.schema.json": topology, "resource-generations.schema.json": generations,
            "resource-binding-proof.schema.json": proof}


if __name__ == "__main__":
    for name, value in schemas().items():
        path = HERE / "staged/schemas" / name
        with path.open("x") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
