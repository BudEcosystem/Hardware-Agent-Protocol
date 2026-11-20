"""Build detached original data fixtures; no Runtime or device construction."""
import copy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "baseline/sources"))
from hms.demo import definitions
from hms.registry import validate_type_bundle


def metadata(unit=None, frame=None, unit_argument=None, frame_argument=None):
    return {"unit": unit, "frame": frame, "unitArgument": unit_argument, "frameArgument": frame_argument}


def build():
    artifact = json.loads((HERE / "baseline/sources/tests/fixtures/pat-compiler.json").read_text())
    result = {}
    fields = [
        {"level": metadata("percent", unit_argument="unit"), "unit": metadata()},
        {"position": metadata("um", "sim:microscope", "unit", "frame"), "unit": metadata(), "frame": metadata()},
        {"recipe": metadata("1"), "partId": metadata()},
    ]
    for family, (instance, action, bundle), argument_metadata in zip(("fan", "focus", "inspection"), definitions(), fields):
        candidate = copy.deepcopy(artifact)
        if family == "focus":
            candidate["roles"]["fan"].update(capabilityFamily="sim:microscope", actions=[action])
            for declaration in candidate["parameters"].values():
                declaration.update(unit="um", frame=instance)
            for step in candidate["steps"]:
                step["actionId"] = action
                step["arguments"] = {"position": step["arguments"]["level"], "unit": {"literal": "um"},
                                     "frame": {"literal": instance}}
        elif family == "inspection":
            candidate["roles"]["fan"].update(capabilityFamily="sim:inspection-cell", actions=[action])
            for declaration in candidate["parameters"].values():
                declaration.update(valueSchema={"type": "integer", "minimum": 1, "maximum": 2, "enum": [1, 2]}, unit="1")
            for step in candidate["steps"]:
                step["actionId"] = action
                step["arguments"] = {"recipe": step["arguments"]["level"], "partId": {"literal": "part:original"}}
        execution = bundle["execution"]
        binding = {"profile": "hms.binding/0.1", "instanceId": instance, "generation": "binding:1",
            "typeDigest": validate_type_bundle(bundle), "calibrationRevision": "calibration:1",
            "controlGeneration": "control:1", "mode": "simulation", "adapterId": "simulator:fixture",
            "resourceMap": {role: "resource:" + role for record in execution["actions"].values() for role in record["resources"]},
            "argumentSchemas": {key: copy.deepcopy(value["inputSchema"]) for key, value in execution["actions"].items()}}
        descriptor = {"type": bundle, "binding": binding, "endpointSession": "session:1", "driverProfile": "sqlite-simulation",
            "driverDigest": "sha256:" + "a" * 64, "installationDigest": "sha256:" + "b" * 64,
            "argumentMetadata": {action: argument_metadata}}
        result[family] = {"artifact": candidate, "bindings": {"fan": descriptor},
                          "parameters": {"initialLevel": 1, "finalLevel": 2}}
    return result


if __name__ == "__main__":
    path = HERE / "fixtures/families.json"
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        raise SystemExit("refusing to overwrite fixtures")
    path.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
