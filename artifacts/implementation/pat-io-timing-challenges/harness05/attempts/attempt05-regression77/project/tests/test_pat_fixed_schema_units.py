"""Pure fixed-schema unit grammar; original fixtures, no provider qualification.

These tests do not open a Runtime or execute a device model. Driver/install
identities are explicit fixture labels, never current installed attestations.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hms import pat_compiler as compiler
from hms.contracts import canonical
from hms.demo import object_schema, type_bundle
from hms.pat_contracts import PatError
from hms.registry import validate_type_bundle

ROOT = Path(__file__).resolve().parents[1]
FIXED = "hms.pat.argument.fixed-schema-unit/0.1"


def fixed(unit):
    return {"profile": FIXED, "unit": unit, "frame": None,
            "unitArgument": None, "frameArgument": None}


def legacy(unit=None, frame=None, unit_argument=None, frame_argument=None):
    return {"unit": unit, "frame": frame, "unitArgument": unit_argument,
            "frameArgument": frame_argument}


def fixed_case(pwm=False):
    value = json.loads((ROOT / "tests/fixtures/pat-compiler.json").read_text())
    properties = {"durationMs": {"type": "integer", "minimum": 1, "maximum": 4999}}
    units = {"durationMs": "ms"}
    params = {"durationMs": 21}
    if pwm:
        properties.update(frequencyHz={"type": "integer", "minimum": 100, "maximum": 10000},
                          dutyPermille={"type": "integer", "minimum": 0, "maximum": 1000},
                          resolutionBits={"type": "integer", "const": 8})
        units.update(frequencyHz="Hz", dutyPermille="permille", resolutionBits="bit")
        params.update(frequencyHz=1500, dutyPermille=375, resolutionBits=8)
    else:
        properties["level"] = {"type": "integer", "minimum": 0, "maximum": 1}
        units["level"] = "1"
        params["level"] = 1
    bundle = type_bundle("fixed-schema-fixture", "apply", object_schema(properties),
                         {"type": "integer", "minimum": 0, "maximum": 1},
                         unit="1", effect="fixture-only", resource="fixture-resource")
    digest = validate_type_bundle(bundle)
    binding = {"profile": "hms.binding/0.1", "instanceId": "fixture:fixed-units",
        "generation": "binding:7", "typeDigest": digest, "calibrationRevision": "fixture:1",
        "controlGeneration": "control:9", "mode": "simulation", "adapterId": "fixture:route",
        "resourceMap": {"fixture-resource": "fixture:shared-resource"},
        "argumentSchemas": {"apply": copy.deepcopy(bundle["execution"]["actions"]["apply"]["inputSchema"])}}
    descriptor = {"type": bundle, "binding": binding, "endpointSession": "fixture:session:1",
        "driverProfile": "fixture-fixed-units/1", "driverDigest": "sha256:" + "a" * 64,
        "installationDigest": "sha256:" + "b" * 64,
        "argumentMetadata": {"apply": {key: fixed(unit) for key, unit in units.items()}}}
    value.update(name="fixed-schema-unit-fixture", taskKind="fixture.units",
                 inputProfile="fixture.fixed-units/1")
    value["parameters"] = {}
    for key, schema in properties.items():
        domain = ({"type": "integer", "minimum": schema["const"], "maximum": schema["const"]}
                  if "const" in schema else copy.deepcopy(schema))
        value["parameters"][key] = {"valueSchema": domain, "unit": units[key], "frame": None}
    value["roles"] = {"fan": {"capabilityFamily": "sim:fixed-schema-fixture", "actions": ["apply"],
                               "driverProfiles": ["fixture-fixed-units/1"]}}
    value["timingBudget"] = {"latestStartOffsetMs": 500, "latestCompletionOffsetMs": 6000,
                              "maxRunSumMs": 5000}
    value["steps"] = [{"stepId": "initial", "role": "fan", "actionId": "apply",
        "arguments": {key: {"parameter": key} for key in properties},
        "timing": {"notBeforeOffsetMs": 0, "latestStartOffsetMs": 500,
                   "maxRunMs": 5000, "latestCompletionOffsetMs": 6000}}]
    value["effectBudget"]["maxInvocations"] = 1
    value["outcomeContract"]["requiredCompletedSteps"] = ["initial"]
    return {"artifact": value, "parameters": params, "bindings": {"fan": descriptor}}


def lower(case):
    value = case["artifact"]
    return compiler.compile_pat(value, case["parameters"], case["bindings"], origin_ms=1000,
        caller_deadline_ms=10000, replay_namespace="fixture:replay", procedure_key="fixture:parent",
        operation_keys={step["stepId"]: "fixture:child:" + step["stepId"] for step in value["steps"]},
        context={"taskKind": value["taskKind"], "inputProfile": value["inputProfile"],
                 "evidenceMode": "simulation", "deployment": "fixture:deployment"})


def environment(case):
    return compiler.evaluation_environment(case["artifact"], case["bindings"],
                                           deployment="fixture:deployment")


def info(case, key="durationMs"):
    return case["bindings"]["fan"]["argumentMetadata"]["apply"][key]


def intent(result):
    return result["request"]["procedure"]["steps"][0]["request"]["intent"]


class FixedSchemaUnitTests(unittest.TestCase):
    def refuse_both(self, case, code=None):
        for call in (lower, environment):
            with self.subTest(call=call.__name__):
                if code is None:
                    with self.assertRaises(PatError):
                        call(case)
                else:
                    with self.assertRaisesRegex(PatError, code):
                        call(case)

    def test_gpio_shaped_contract_retains_exact_arguments_keys_and_bounds(self):
        case = fixed_case(); result = lower(case)
        self.assertEqual(intent(result)["arguments"], {"durationMs": 21, "level": 1})
        self.assertEqual(intent(result)["timing"], {"notBeforeUnixMs": 1000, "latestStartUnixMs": 1500,
                                                  "maxRunMs": 5000, "latestCompletionUnixMs": 7000})
        self.assertEqual(result["request"]["procedureKey"], "fixture:parent")
        self.assertEqual(result["request"]["procedure"]["steps"][0]["request"]["operationKey"],
                         "fixture:child:initial")
        self.assertEqual(intent(result)["bindingGeneration"], "binding:7")
        self.assertEqual(intent(result)["controlGeneration"], "control:9")
        self.assertFalse(result["report"]["admitted"])
        self.assertFalse(result["report"]["physicalObjectiveVerified"])
        self.assertEqual(result["report"]["unitConversions"], [])
        self.assertEqual(result["report"]["frameConversions"], [])

    def test_pwm_shaped_contract_has_explicit_hz_permille_bit_and_ms(self):
        case = fixed_case(pwm=True); result = lower(case)
        self.assertEqual(intent(result)["arguments"], case["parameters"])
        self.assertEqual({key: row["unit"] for key, row in
                          case["bindings"]["fan"]["argumentMetadata"]["apply"].items()},
                         {"durationMs": "ms", "frequencyHz": "Hz", "dutyPermille": "permille",
                          "resolutionBits": "bit"})
        self.assertTrue(all(type(x) is int for x in intent(result)["arguments"].values()))
        for key in ("patDigest", "compilerDigest", "evaluationEnvironment", "environmentDigest", "dependencies"):
            self.assertEqual(environment(case)[key], result[key])

    def test_argument_spelling_cannot_infer_units(self):
        case = fixed_case(); descriptor = case["bindings"]["fan"]
        for schema in (descriptor["type"]["execution"]["actions"]["apply"]["inputSchema"],
                       descriptor["binding"]["argumentSchemas"]["apply"]):
            schema["properties"]["q9"] = schema["properties"].pop("durationMs")
            schema["required"] = ["q9" if key == "durationMs" else key for key in schema["required"]]
        # Rebuild the TD from the new schema: no fake type digest or stale projection.
        schema = descriptor["type"]["execution"]["actions"]["apply"]["inputSchema"]
        descriptor["type"] = type_bundle("fixed-schema-fixture", "apply", schema,
            {"type": "integer", "minimum": 0, "maximum": 1}, unit="1",
            effect="fixture-only", resource="fixture-resource")
        descriptor["binding"]["typeDigest"] = validate_type_bundle(descriptor["type"])
        descriptor["argumentMetadata"]["apply"]["q9"] = descriptor["argumentMetadata"]["apply"].pop("durationMs")
        case["artifact"]["steps"][0]["arguments"]["q9"] = case["artifact"]["steps"][0]["arguments"].pop("durationMs")
        self.assertEqual(intent(lower(case))["arguments"], {"q9": 21, "level": 1})
        info(case, "q9")["unit"] = "1"
        self.refuse_both(case, "PAT_SEMANTICS_MISMATCH")

    def test_literals_use_registered_units_without_synthesized_companions(self):
        case = fixed_case(pwm=True)
        for key, value in case["parameters"].items():
            case["artifact"]["steps"][0]["arguments"][key] = {"literal": value}
        expected = copy.deepcopy(case["parameters"])
        case["parameters"] = {}; case["artifact"]["parameters"] = {}
        self.assertEqual(intent(lower(case))["arguments"], expected)
        self.assertEqual(set(intent(lower(case))["arguments"]), set(expected))
        for wrong in (True, 21.0, -1, 5000):
            broken = copy.deepcopy(case)
            broken["artifact"]["steps"][0]["arguments"]["durationMs"] = {"literal": wrong}
            self.refuse_both(broken)

    def test_tagged_metadata_is_closed_bounded_and_exactly_typed(self):
        changes = [{"profile": value} for value in (None, True, 1, 1.0, {}, "unknown", FIXED + ".next")]
        changes += [{"unit": value} for value in (None, True, 1, 1.0, {}, "", "m" * 129)]
        changes += [{"scale": 1000}, {"converter": "arbitrary:callback"}, {"schemaDigest": "sha256:" + "c" * 64}]
        for change in changes:
            case = fixed_case(); info(case).update(change)
            with self.subTest(change=change):
                self.refuse_both(case)
        for missing in ("profile", "unit", "frame", "unitArgument", "frameArgument"):
            case = fixed_case(); info(case).pop(missing)
            with self.subTest(missing=missing):
                self.refuse_both(case)
        case = fixed_case(); info(case)["unit"] = "m" * 65536
        self.refuse_both(case)

    def test_fixed_units_require_numeric_type_and_binding_schemas(self):
        for kind, schema in (("string", {"type": "string", "maxLength": 10}),
                             ("boolean", {"type": "boolean"}), ("null", {"type": "null"})):
            case = fixed_case()
            case["bindings"]["fan"]["binding"]["argumentSchemas"]["apply"]["properties"]["durationMs"] = schema
            with self.subTest(binding_kind=kind):
                self.refuse_both(case, "PAT_METADATA_MISMATCH")
        # A tagged entry cannot be attached to a legacy string companion either.
        case = json.loads((ROOT / "tests/fixtures/pat-environment.json").read_text())["fan"]
        case["bindings"]["fan"]["argumentMetadata"]["set_level"]["unit"] = fixed("1")
        self.refuse_both(case, "PAT_METADATA_MISMATCH")

    def test_fixed_frame_and_companion_fields_must_all_be_null(self):
        for field in ("frame", "unitArgument", "frameArgument"):
            for value in (False, 0, "level", "frame:device", {}):
                case = fixed_case(); info(case)[field] = value
                with self.subTest(field=field, value=value):
                    self.refuse_both(case, "PAT_METADATA_MISMATCH")

    def test_parameter_units_are_exact_with_no_conversion_or_dimensionless_alias(self):
        for key, wrong in (("durationMs", "s"), ("frequencyHz", "kHz"),
                           ("dutyPermille", "percent"), ("resolutionBits", "1"),
                           ("durationMs", "1"), ("frequencyHz", "hz")):
            case = fixed_case(pwm=True); case["artifact"]["parameters"][key]["unit"] = wrong
            with self.subTest(key=key, unit=wrong):
                self.refuse_both(case, "PAT_SEMANTICS_MISMATCH")
        case = fixed_case(); case["artifact"]["parameters"]["durationMs"]["frame"] = "frame:device"
        self.refuse_both(case, "PAT_SEMANTICS_MISMATCH")

    def test_bool_float_and_declared_schema_numeric_aliases_are_not_normalized(self):
        for key in ("level", "durationMs"):
            for wrong in (True, 1.0):
                case = fixed_case(); case["parameters"][key] = wrong
                with self.subTest(key=key, value=wrong), self.assertRaises(PatError):
                    lower(case)
        for field, wrong in (("minimum", True), ("maximum", 4999.0)):
            case = fixed_case(); case["artifact"]["parameters"]["durationMs"]["valueSchema"][field] = wrong
            with self.subTest(field=field):
                self.refuse_both(case)

    def test_whole_domains_and_enum_holes_survive_narrow_applicability(self):
        for target in ("type-domain", "binding-domain", "binding-enum-hole"):
            case = fixed_case()
            case["artifact"]["applicability"]["all"].append(
                {"field": "parameters.durationMs", "op": "equals", "literal": 21})
            if target == "type-domain":
                case["artifact"]["parameters"]["durationMs"]["valueSchema"]["maximum"] = 5000
            else:
                schema = case["bindings"]["fan"]["binding"]["argumentSchemas"]["apply"]["properties"]["durationMs"]
                if target == "binding-domain":
                    schema["maximum"] = 100
                else:
                    schema["enum"] = [1, 21, 4999]
            with self.subTest(target=target):
                self.refuse_both(case, "PAT_ARGUMENT_DOMAIN")
        case = fixed_case(pwm=True)
        case["artifact"]["parameters"]["resolutionBits"]["valueSchema"]["maximum"] = 9
        self.refuse_both(case, "PAT_ARGUMENT_DOMAIN")

    def test_profile_and_unit_are_committed_to_metadata_and_environment(self):
        case = fixed_case(); first = lower(case); metadata = case["bindings"]["fan"]["argumentMetadata"]
        digest = "sha256:" + hashlib.sha256(canonical(metadata)).hexdigest()
        self.assertEqual(first["dependencies"][0]["metadataDigest"], digest)
        self.assertEqual(first["evaluationEnvironment"]["roles"]["fan"]["argumentMetadataDigest"], digest)
        # The dimensionless level keeps identical semantics/arguments in both forms,
        # but its explicit metadata profile still changes dependency identity.
        info(case, "level").pop("profile")
        second = lower(case)
        self.assertEqual(first["request"], second["request"])
        self.assertEqual(first["requestDigest"], second["requestDigest"])
        self.assertNotEqual(first["environmentDigest"], second["environmentDigest"])
        self.assertNotEqual(first["runBindingDigest"], second["runBindingDigest"])
        info(case)["unit"] = "ticks"
        case["artifact"]["parameters"]["durationMs"]["unit"] = "ticks"
        third = lower(case)
        self.assertEqual(second["request"], third["request"])
        self.assertNotEqual(second["dependencies"][0]["metadataDigest"], third["dependencies"][0]["metadataDigest"])
        self.assertNotEqual(second["environmentDigest"], third["environmentDigest"])
        manifest = compiler.compiler_manifest()
        source = next(row for row in manifest["sources"] if row["path"] == "hms/pat_compiler.py")
        self.assertEqual(source["sha256"], hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest())

    def test_sessions_determinism_detachment_and_call_time_purity_remain(self):
        case = fixed_case(); original = copy.deepcopy(case); first = lower(case)
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("file I/O")), \
             patch("pathlib.Path.read_text", side_effect=AssertionError("file I/O")), \
             patch("time.time_ns", side_effect=AssertionError("wall clock")), \
             patch("time.monotonic", side_effect=AssertionError("monotonic clock")), \
             patch("sqlite3.connect", side_effect=AssertionError("database")):
            self.assertEqual(first, lower(case))
            self.assertEqual(environment(case)["environmentDigest"], first["environmentDigest"])
        self.assertEqual(case, original)
        first["dependencies"][0]["metadataDigest"] = "changed"
        self.assertEqual(case, original)
        case["bindings"]["fan"]["endpointSession"] = "fixture:session:2"
        second = lower(case); clean = lower(original)
        self.assertEqual(clean["environmentDigest"], second["environmentDigest"])
        self.assertNotEqual(clean["dependencies"], second["dependencies"])
        self.assertNotEqual(clean["requestDigest"], second["requestDigest"])
        self.assertNotEqual(clean["runBindingDigest"], second["runBindingDigest"])

    def test_legacy_companion_units_and_frames_still_require_exact_wire_arguments(self):
        families = json.loads((ROOT / "tests/fixtures/pat-environment.json").read_text())
        for family in ("fan", "focus", "inspection"):
            case = copy.deepcopy(families[family]); result = lower(case)
            self.assertEqual(result["report"]["unitConversions"], [])
            self.assertEqual(result["report"]["frameConversions"], [])
        for family, argument in (("fan", "unit"), ("focus", "frame")):
            case = copy.deepcopy(families[family])
            case["artifact"]["steps"][0]["arguments"][argument] = {"literal": "wrong"}
            with self.subTest(family=family):
                self.refuse_both(case)
        case = copy.deepcopy(families["fan"])
        case["bindings"]["fan"]["argumentMetadata"]["set_level"]["level"]["unitArgument"] = None
        self.refuse_both(case, "PAT_METADATA_REQUIRED")
        case = copy.deepcopy(families["focus"])
        case["bindings"]["fan"]["argumentMetadata"]["move_absolute"]["position"]["frameArgument"] = None
        self.refuse_both(case, "PAT_METADATA_REQUIRED")

    def test_unprofiled_nondimensionless_metadata_still_refuses_in_mixed_action(self):
        for unit in ("ms", "Hz", "permille", "bit"):
            case = fixed_case(); info(case)["unit"] = unit
            case["artifact"]["parameters"]["durationMs"]["unit"] = unit
            info(case).pop("profile")
            with self.subTest(unit=unit):
                self.refuse_both(case, "PAT_METADATA_REQUIRED")
        case = fixed_case()
        case["bindings"]["fan"]["argumentMetadata"]["apply"]["level"] = legacy("1")
        self.assertEqual(intent(lower(case))["arguments"], {"durationMs": 21, "level": 1})
        info(case, "level")["unit"] = None
        self.refuse_both(case, "PAT_METADATA_REQUIRED")


if __name__ == "__main__":
    unittest.main()
