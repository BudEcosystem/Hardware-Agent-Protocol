"""Bounded PAT parsing/lowering and original local-simulation executions."""
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import SAFE_INTEGER, canonical
from hms.demo import definitions, object_schema, type_bundle
from hms.installations import installation_digest, legacy_installation
from hms.journal import Context
from hms.pat_contracts import PatError, matches_static, parse_pat, pat_digest, validate_parameters
from hms.pat_compiler import COMPILER_DIGEST, compile_pat, compiler_digest, compiler_manifest
from hms.procedures import parse_procedure, procedure_digest
from hms.registry import validate_type_bundle
from hms.runtime import Runtime


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/pat-compiler.json"


def artifact():
    return json.loads(FIXTURE.read_text())


def metadata(unit=None, frame=None, unit_argument=None, frame_argument=None):
    return {"unit": unit, "frame": frame, "unitArgument": unit_argument, "frameArgument": frame_argument}


def descriptor(bundle=None, *, instance="sim:home-fan", action="set_level", fields=None):
    bundle = copy.deepcopy(bundle or definitions()[0][2])
    digest = validate_type_bundle(bundle)
    execution = bundle["execution"]
    binding = {"profile": "hms.binding/0.1", "instanceId": instance, "generation": "binding:1",
        "typeDigest": digest, "calibrationRevision": "calibration:1", "controlGeneration": "control:1",
        "mode": "simulation", "adapterId": "simulator:fixture",
        "resourceMap": {role: "resource:" + role for action_record in execution["actions"].values() for role in action_record["resources"]},
        "argumentSchemas": {name: copy.deepcopy(value["inputSchema"]) for name, value in execution["actions"].items()}}
    return {"type": bundle, "binding": binding, "endpointSession": "session:1", "driverProfile": "sqlite-simulation",
        "driverDigest": "sha256:" + "a" * 64, "installationDigest": "sha256:" + "b" * 64,
        "argumentMetadata": {action: fields or {"level": metadata("percent", unit_argument="unit"), "unit": metadata()}}}


def compile_fixture(value=None, params=None, bindings=None, **changes):
    value = value or artifact()
    options = {"origin_ms": 1000, "caller_deadline_ms": 3500,
        "replay_namespace": "replay:fixture:1:token", "procedure_key": "parent:1",
        "operation_keys": {step["stepId"]: "child:" + step["stepId"] for step in value["steps"]},
        "context": {"taskKind": value["taskKind"], "inputProfile": value["inputProfile"],
                    "evidenceMode": "simulation", "deployment": "test:simulation"}}
    options.update(changes)
    return compile_pat(value, params if params is not None else {"initialLevel": 12, "finalLevel": 73},
                       bindings if bindings is not None else {"fan": descriptor()}, **options)


class PatCompilerTests(unittest.TestCase):
    def test_artifact_snapshot_digest_and_key_order_are_immutable(self):
        original = artifact()
        parsed = parse_pat(original)
        digest = pat_digest(parsed)
        original["steps"][0]["arguments"]["unit"]["literal"] = "changed"
        self.assertEqual(parsed["steps"][0]["arguments"]["unit"]["literal"], "percent")
        reordered = dict(reversed(list(parsed.items())))
        self.assertEqual(pat_digest(reordered), digest)
        parsed["version"] = "2"
        self.assertNotEqual(pat_digest(parsed), digest)

    def test_duplicate_fields_numeric_loss_and_oversized_artifacts_refuse(self):
        for raw in (b'{"protocol":"a","protocol":"b"}', b'{"n":1e999}', b'{"n":-0}', b" " * 65537):
            with self.subTest(raw=raw[:30]), self.assertRaises(PatError):
                parse_pat(raw)
        value = artifact()
        value["steps"][0]["arguments"]["unit"]["literal"] = "x" * 65536
        with self.assertRaises(PatError):
            parse_pat(value)

    def test_integral_float_cannot_be_normalized_to_integer(self):
        value = artifact()
        value["parameters"]["initialLevel"]["valueSchema"]["maximum"] = 100.0
        with self.assertRaises(PatError):
            parse_pat(value)
        value = artifact()
        value["steps"][0]["timing"]["maxRunMs"] = 500.0
        with self.assertRaises(PatError):
            parse_pat(value)
        for wrong in (True, 12.0, -1, 101):
            with self.subTest(wrong=wrong), self.assertRaises(PatError):
                compile_fixture(params={"initialLevel": wrong, "finalLevel": 50})
        value = artifact()
        value["steps"][0]["arguments"]["level"] = {"literal": 12.0}
        del value["parameters"]["initialLevel"]
        with self.assertRaises(PatError):
            parse_pat(value)

    def test_arbitrary_json_wrong_types_always_raise_paterror(self):
        paths = [("parameters", "initialLevel", "valueSchema", "type"),
                 ("roles", "fan", "actions"), ("steps", 0, "role"),
                 ("steps", 0, "arguments", "level", "parameter"),
                 ("applicability", "all", 0, "field"), ("timingBudget", "maxRunSumMs")]
        for path in paths:
            for wrong in ({}, [], None, True):
                value = artifact()
                target = value
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = wrong
                with self.subTest(path=path, wrong=wrong), self.assertRaises(PatError):
                    parse_pat(value)

    def test_unsupported_control_flow_predicates_and_code_are_refused(self):
        for change in ({"loop": {}}, {"runtimeGuardProfile": "temperature-must-stay-below-limit"},
                       {"executionPlacement": "arduino-local-loop"}):
            with self.assertRaises(PatError):
                parse_pat(artifact() | change)
        for field in ("observations.temperature", "context.gpuMemory", "steps.initial.result", "environment.HOME"):
            value = artifact()
            value["applicability"]["all"] = [{"field": field, "op": "equals", "literal": "yes"}]
            with self.assertRaises(PatError):
                parse_pat(value)
        value = artifact()
        value["steps"][0]["arguments"]["level"] = {"expression": "__import__('os').system('bad')"}
        with self.assertRaises(PatError):
            parse_pat(value)

    def test_static_matching_is_typed_and_not_self_granting(self):
        value = artifact()
        value["applicability"]["all"].append({"field": "parameters.initialLevel", "op": "range", "minimum": 0, "maximum": 20})
        options = dict(task_kind=value["taskKind"], input_profile=value["inputProfile"], evidence_mode="simulation")
        self.assertTrue(matches_static(value, {"initialLevel": 20, "finalLevel": 100}, **options))
        self.assertFalse(matches_static(value, {"initialLevel": 21, "finalLevel": 100}, **options))
        self.assertFalse(matches_static(value, {"initialLevel": 20, "finalLevel": 100}, **(options | {"task_kind": "novel"})))
        with self.assertRaisesRegex(PatError, "PAT_NOT_APPLICABLE"):
            compile_fixture(value, {"initialLevel": 21, "finalLevel": 100})

    def test_unknown_unused_parameters_and_roles_refuse(self):
        value = artifact()
        value["parameters"]["unused"] = copy.deepcopy(value["parameters"]["initialLevel"])
        with self.assertRaisesRegex(PatError, "PAT_UNUSED_PARAMETER"):
            parse_pat(value)
        with self.assertRaises(PatError):
            validate_parameters(artifact(), {"initialLevel": 1, "finalLevel": 2, "extra": 3})
        value = artifact()
        value["roles"]["unused"] = copy.deepcopy(value["roles"]["fan"])
        with self.assertRaisesRegex(PatError, "PAT_UNUSED_REQUIREMENT"):
            parse_pat(value)

    def test_timing_total_budget_deadline_overflow_and_key_collisions_refuse(self):
        for changes in ({"origin_ms": True}, {"origin_ms": 1000.0}, {"origin_ms": SAFE_INTEGER - 100},
                        {"caller_deadline_ms": 2999}, {"operation_keys": {"initial": "same", "final": "same"}},
                        {"operation_keys": {"initial": "parent:1", "final": "child:2"}}):
            with self.subTest(changes=changes), self.assertRaises(PatError):
                compile_fixture(**changes)
        for field, value in (("maxRunSumMs", 999), ("latestCompletionOffsetMs", 600)):
            candidate = artifact()
            candidate["timingBudget"][field] = value
            with self.assertRaises(PatError):
                parse_pat(candidate)

    def test_whole_parameter_domain_must_fit_both_concrete_schemas(self):
        binding = descriptor()
        binding["binding"]["argumentSchemas"]["set_level"]["properties"]["level"]["maximum"] = 50
        with self.assertRaisesRegex(PatError, "PAT_ARGUMENT_DOMAIN"):
            compile_fixture(params={"initialLevel": 12, "finalLevel": 30}, bindings={"fan": binding})

    def test_driver_capability_type_and_binding_dependencies_must_agree(self):
        for field, value in (("driverProfile", "other-driver"), ("driverDigest", "not-a-digest"),
                             ("installationDigest", None)):
            binding = descriptor()
            binding[field] = value
            with self.subTest(field=field), self.assertRaises(PatError):
                compile_fixture(bindings={"fan": binding})
        binding = descriptor()
        binding["binding"]["typeDigest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(PatError, "PAT_DEPENDENCY_MISMATCH"):
            compile_fixture(bindings={"fan": binding})
        value = artifact()
        value["roles"]["fan"]["capabilityFamily"] = "sim:camera"
        with self.assertRaisesRegex(PatError, "PAT_CAPABILITY_MISMATCH"):
            compile_fixture(value)

    def test_missing_or_forged_unit_metadata_is_not_inferred(self):
        binding = descriptor()
        del binding["argumentMetadata"]
        with self.assertRaises(PatError):
            compile_fixture(bindings={"fan": binding})
        for change in ({"unit": None}, {"unitArgument": None}, {"unitArgument": "unrelated"},
                       {"unit": "metres"}, {"unitArgument": "level"}):
            binding = descriptor()
            binding["argumentMetadata"]["set_level"]["level"].update(change)
            with self.subTest(change=change), self.assertRaises(PatError):
                compile_fixture(bindings={"fan": binding})

    def test_malformed_binding_schemas_have_structured_refusals(self):
        for field, wrong in (("type", []), ("minimum", "zero"), ("maximum", {})):
            binding = descriptor()
            binding["binding"]["argumentSchemas"]["set_level"]["properties"]["level"][field] = wrong
            with self.subTest(field=field), self.assertRaises(PatError):
                compile_fixture(bindings={"fan": binding})

    def test_literal_companion_cannot_bypass_metadata_even_if_schema_allows_it(self):
        value = artifact()
        value["steps"][0]["arguments"]["unit"]["literal"] = "metres"
        binding = descriptor()
        # Keep type schema strict: mismatch must already refuse. The exact
        # metadata check also protects providers with a broader string domain.
        with self.assertRaises(PatError):
            compile_fixture(value, bindings={"fan": binding})

    def test_evaluation_environment_excludes_session_but_pins_driver_and_metadata(self):
        first = compile_fixture()
        binding = descriptor()
        binding["endpointSession"] = "session:2"
        later = compile_fixture(bindings={"fan": binding})
        self.assertEqual(first["environmentDigest"], later["environmentDigest"])
        self.assertNotEqual(first["runBindingDigest"], later["runBindingDigest"])
        self.assertNotEqual(first["requestDigest"], later["requestDigest"])
        binding["driverDigest"] = "sha256:" + "c" * 64
        upgraded = compile_fixture(bindings={"fan": binding})
        self.assertNotEqual(upgraded["environmentDigest"], later["environmentDigest"])
        self.assertEqual(set(first["evaluationEnvironment"]["roles"]["fan"]),
            {"typeDigest", "bindingDigest", "installationDigest", "argumentMetadataDigest", "driverProfile", "driverDigest"})

    def test_same_inputs_lower_identically_new_keys_and_origin_are_explicit(self):
        first = compile_fixture()
        self.assertEqual(first, compile_fixture())
        self.assertEqual(first["request"], parse_procedure(first["request"]))
        self.assertEqual(first["requestDigest"], procedure_digest(first["request"]))
        self.assertFalse(first["report"]["admitted"])
        changed = compile_fixture(origin_ms=1100, procedure_key="parent:2",
                                  operation_keys={"initial": "next:1", "final": "next:2"})
        self.assertEqual(first["patDigest"], changed["patDigest"])
        self.assertNotEqual(first["requestDigest"], changed["requestDigest"])

    def test_compiler_identity_contains_actual_sources_and_validation_packages(self):
        identity = compiler_manifest()
        self.assertEqual(COMPILER_DIGEST, compiler_digest())
        for row in identity["sources"]:
            self.assertEqual(row["sha256"], hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest())
        self.assertEqual({row["package"] for row in identity["packages"]},
                         {"jsonschema", "referencing", "jsonschema-specifications", "attrs", "rpds-py"})
        self.assertTrue(all(row["fileCount"] > 0 for row in identity["packages"]))
        identity["sources"].clear()
        self.assertTrue(compiler_manifest()["sources"])

    def test_compiler_identity_changes_with_actual_extensionless_schema_resource(self):
        from hms.pat_compiler import _identity
        target = "jsonschema_specifications/schemas/draft202012/vocabularies/validation"
        actual_distribution = importlib.metadata.distribution
        original = actual_distribution("jsonschema-specifications")
        self.assertIn(target, {str(item) for item in original.files})
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory) / "validation"
            resource.write_bytes(original.locate_file(target).read_bytes())
            class Distribution:
                files, version = original.files, original.version
                def locate_file(self, item):
                    return resource if str(item) == target else original.locate_file(item)
            def distribution(package):
                return Distribution() if package == "jsonschema-specifications" else actual_distribution(package)
            with patch("hms.pat_compiler.importlib.metadata.distribution", side_effect=distribution):
                before = _identity()
                value = json.loads(resource.read_bytes()); value["title"] = "changed retained schema"
                resource.write_bytes(canonical(value))
                after = _identity()
            before_packages = {row["package"]: row for row in before["packages"]}
            after_packages = {row["package"]: row for row in after["packages"]}
            self.assertNotEqual(before_packages.pop("jsonschema-specifications")["codeDigest"],
                                after_packages.pop("jsonschema-specifications")["codeDigest"])
            self.assertEqual(before_packages, after_packages)

    def test_missing_installed_extensionless_schema_refuses_identity(self):
        from hms.pat_compiler import _identity
        target = "jsonschema_specifications/schemas/draft202012/vocabularies/validation"
        actual_distribution = importlib.metadata.distribution
        original = actual_distribution("jsonschema-specifications")
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent-resource"
            class Distribution:
                files, version = original.files, original.version
                def locate_file(self, item):
                    return missing if str(item) == target else original.locate_file(item)
            def distribution(package):
                return Distribution() if package == "jsonschema-specifications" else actual_distribution(package)
            with patch("hms.pat_compiler.importlib.metadata.distribution", side_effect=distribution):
                with self.assertRaises(PatError) as refused:
                    _identity()
            self.assertEqual(refused.exception.code, "PAT_COMPILER_IDENTITY_UNAVAILABLE")

    def test_pure_lowering_does_not_open_files_or_sample_a_clock(self):
        # Identity is already fixed at module import. Compilation itself is pure.
        value, binding = artifact(), descriptor()
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("compiler I/O")), \
             patch("time.time", side_effect=AssertionError("compiler clock")), \
             patch("time.time_ns", side_effect=AssertionError("compiler clock")):
            result = compile_fixture(value, bindings={"fan": binding})
        self.assertEqual(result["report"]["stepCount"], 2)

    def test_generic_non_demo_action_uses_explicit_semantic_companions(self):
        args = object_schema({"ticks": {"type": "integer", "minimum": 0, "maximum": 100},
            "uom": {"type": "string", "const": "ticks", "maxLength": 16},
            "coordinates": {"type": "string", "const": "frame:calibrated", "maxLength": 64}})
        bundle = type_bundle("custom-actuator", "drive", args, {"type": "integer", "minimum": 0, "maximum": 100},
                             unit="ticks", effect="motion", resource="custom-zone")
        fields = {"ticks": metadata("ticks", "frame:calibrated", "uom", "coordinates"),
                  "uom": metadata(), "coordinates": metadata()}
        binding = descriptor(bundle, instance="fixture:custom", action="drive", fields=fields)
        value = artifact()
        value["roles"]["fan"].update(capabilityFamily="sim:custom-actuator", actions=["drive"])
        for declaration in value["parameters"].values():
            declaration.update(unit="ticks", frame="frame:calibrated")
        for step in value["steps"]:
            step["actionId"] = "drive"
            step["arguments"] = {"ticks": step["arguments"]["level"], "uom": {"literal": "ticks"},
                                  "coordinates": {"literal": "frame:calibrated"}}
        compiled = compile_fixture(value, bindings={"fan": binding})
        self.assertEqual(compiled["request"]["procedure"]["steps"][1]["request"]["intent"]["actionId"], "drive")
        value["parameters"]["initialLevel"]["frame"] = "wrong:frame"
        with self.assertRaisesRegex(PatError, "PAT_SEMANTICS_MISMATCH"):
            compile_fixture(value, bindings={"fan": binding})

    def test_all_three_families_compile_and_execute_across_two_local_aliases(self):
        owner = Context("pat-compiler-owner", "simulation:multi")
        wall = [1000]
        configs = []
        for alias in ("east", "west"):
            config = legacy_installation()
            config["adapterId"] = "pat-route:" + alias
            config["instances"] = {role: "sim:" + alias + ":" + role for role in config["instances"]}
            config["resources"] = {role: "resource:" + alias + ":" + role for role in config["resources"]}
            configs.append(config)
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(directory, create=True, owner=owner, installations=configs,
                              wall_clock_ms=lambda: wall[0], monotonic_ms=lambda: wall[0])
            try:
                namespace = runtime.request(owner, "namespace", {"expiresUnixMs": 20000})["token"]
                for alias_index, config in enumerate(configs):
                    for role in ("fan", "focus", "inspection"):
                        instance = config["instances"][role]
                        description = runtime.request(owner, "describe", {"instanceId": instance})
                        value, params, fields = self._family(role, instance, alias_index)
                        action_id = value["roles"]["fan"]["actions"][0]
                        bound = {"type": description["type"], "binding": description["binding"],
                            "endpointSession": description["presence"]["session"], "driverProfile": config["driver"],
                            "driverDigest": "sha256:" + hashlib.sha256((ROOT / "hms/local_adapter.py").read_bytes()).hexdigest(),
                            "installationDigest": "sha256:" + installation_digest(config),
                            "argumentMetadata": {action_id: fields}}
                        compiled = compile_fixture(value, params, {"fan": bound}, origin_ms=wall[0],
                            caller_deadline_ms=wall[0] + 2500, replay_namespace=namespace,
                            procedure_key="parent:" + instance,
                            operation_keys={step["stepId"]: instance + ":" + step["stepId"] for step in value["steps"]},
                            context={"taskKind": value["taskKind"], "inputProfile": value["inputProfile"],
                                     "evidenceMode": "simulation", "deployment": owner.deployment})
                        parent = runtime.request(owner, "procedure_submit", {"request": compiled["request"]})
                        for _ in range(12):
                            runtime.tick()
                            status = runtime.request(owner, "procedure_status", {"procedureId": parent["procedureId"]})
                            if status["executionState"] == "completed":
                                break
                            wall[0] += 100
                        self.assertEqual(status["executionState"], "completed", status)
                        plant = runtime.adapters[config["adapterId"]].plant.observe(instance)
                        self.assertEqual(plant["effectCount"], 2)
                        expected = params.get("finalLevel", params.get("finalPosition", 2))
                        self.assertEqual(plant["value"], expected)
                        repeated = runtime.request(owner, "procedure_submit", {"request": compiled["request"]})
                        self.assertEqual(repeated["procedureId"], parent["procedureId"])
                        self.assertEqual(runtime.adapters[config["adapterId"]].plant.observe(instance)["effectCount"], 2)
            finally:
                runtime.close()

    @staticmethod
    def _family(role, instance, variant):
        value = artifact()
        if role == "fan":
            return value, {"initialLevel": 11 + variant, "finalLevel": 75 - variant}, {
                "level": metadata("percent", unit_argument="unit"), "unit": metadata()}
        if role == "focus":
            value["roles"]["fan"].update(capabilityFamily="sim:microscope", actions=["move_absolute"])
            value["parameters"] = {key: {"valueSchema": {"type": "integer", "minimum": 0, "maximum": 100},
                "unit": "um", "frame": instance} for key in ("initialPosition", "finalPosition")}
            for step, parameter in zip(value["steps"], value["parameters"]):
                step["actionId"] = "move_absolute"
                step["arguments"] = {"position": {"parameter": parameter}, "unit": {"literal": "um"},
                                      "frame": {"literal": instance}}
            return value, {"initialPosition": 7 + variant, "finalPosition": 63 - variant}, {
                "position": metadata("um", instance, "unit", "frame"), "unit": metadata(), "frame": metadata()}
        value["roles"]["fan"].update(capabilityFamily="sim:inspection-cell", actions=["inspect"])
        value["parameters"] = {key: {"valueSchema": {"type": "integer", "minimum": 1, "maximum": 2, "enum": [1, 2]},
            "unit": "1", "frame": None} for key in ("firstRecipe", "secondRecipe")}
        value["parameters"]["part"] = {"valueSchema": {"type": "string", "minLength": 1, "maxLength": 64}, "unit": None, "frame": None}
        for step, parameter in zip(value["steps"], ("firstRecipe", "secondRecipe")):
            step["actionId"] = "inspect"
            step["arguments"] = {"recipe": {"parameter": parameter}, "partId": {"parameter": "part"}}
        return value, {"firstRecipe": 1, "secondRecipe": 2, "part": "part:compiled:" + str(variant)}, {
            "recipe": metadata("1"), "partId": metadata()}
