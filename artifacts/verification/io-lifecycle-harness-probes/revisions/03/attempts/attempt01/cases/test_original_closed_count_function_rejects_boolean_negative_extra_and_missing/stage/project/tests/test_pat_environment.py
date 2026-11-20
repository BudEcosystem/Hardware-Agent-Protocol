"""Pure environment/compiler tests; retained baseline outputs, no Runtime."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hms import pat_compiler as compiler
from hms.pat_contracts import PatError

HERE = Path(__file__).resolve().parent
FAMILY_PATH = HERE / "fixtures/pat-environment.json"
FAMILIES = json.loads(FAMILY_PATH.read_text())
BASELINE = json.loads((HERE / "fixtures/pat-environment-baseline.json").read_text())
BASELINE_DIGEST = BASELINE["provenance"]["baselineCompilerDigest"]


def family(which="fan"):
    return copy.deepcopy(FAMILIES[which])


def extract(case=None, **changes):
    case = case or family()
    return compiler.evaluation_environment(case["artifact"], case["bindings"], deployment=changes.pop("deployment", "test:simulation"), **changes)


def lower(case=None, **changes):
    case = case or family()
    artifact = case["artifact"]
    options = {"origin_ms": 1000, "caller_deadline_ms": 3500,
        "replay_namespace": "replay:fixture:1:token", "procedure_key": "parent:1",
        "operation_keys": {step["stepId"]: "child:" + step["stepId"] for step in artifact["steps"]},
        "context": {"taskKind": artifact["taskKind"], "inputProfile": artifact["inputProfile"],
                    "evidenceMode": "simulation", "deployment": "test:simulation"}}
    options.update(changes)
    return compiler.compile_pat(artifact, case["parameters"], case["bindings"], **options)


class EnvironmentTests(unittest.TestCase):
    def test_three_original_families_share_exact_environment_and_dependencies(self):
        for which in FAMILIES:
            with self.subTest(family=which):
                case = family(which)
                evidence, plan = extract(case), lower(case)
                for key in evidence:
                    self.assertEqual(evidence[key], plan[key])
                self.assertNotIn("request", evidence)

    def test_pure_extraction_does_not_call_lowering_parameters_clocks_io_or_database(self):
        case = family()
        with patch.object(compiler, "compile_pat", side_effect=AssertionError("lowering")), \
             patch.object(compiler, "validate_parameters", side_effect=AssertionError("sample parameters")), \
             patch("pathlib.Path.read_bytes", side_effect=AssertionError("I/O")), \
             patch("time.time_ns", side_effect=AssertionError("clock")), \
             patch("time.monotonic", side_effect=AssertionError("clock")), \
             patch("sqlite3.connect", side_effect=AssertionError("database")):
            self.assertEqual(extract(case)["evaluationEnvironment"]["evidenceMode"], "simulation")

    def test_role_closure_rejects_missing_extra_wrong_shape(self):
        for bindings in ({}, {"other": family()["bindings"]["fan"]}, [], None,
                         family()["bindings"] | {"extra": family()["bindings"]["fan"]}):
            with self.subTest(bindings=bindings), self.assertRaises(PatError):
                extract(family() | {"bindings": bindings})

    def test_artifact_shape_and_integral_float_refused_before_normalization(self):
        for candidate in ({}, [], None, family()["artifact"] | {"code": "no"}):
            with self.subTest(candidate=candidate), self.assertRaises(PatError):
                extract(family() | {"artifact": candidate})
        case = family()
        case["artifact"]["parameters"]["initialLevel"]["valueSchema"]["maximum"] = 100.0
        with self.assertRaises(PatError):
            extract(case)

    def test_descriptor_metadata_type_installation_and_driver_refuse(self):
        mutations = [lambda d: d.pop("argumentMetadata"),
            lambda d: d.update(type=[]), lambda d: d["binding"].update(typeDigest="sha256:" + "0" * 64),
            lambda d: d.update(installationDigest=None), lambda d: d.update(driverDigest="not-digest"),
            lambda d: d.update(driverProfile="unknown"), lambda d: d.update(endpointSession=None),
            lambda d: d["argumentMetadata"]["set_level"]["level"].update(unitArgument="missing"),
            lambda d: d["binding"]["argumentSchemas"]["set_level"]["properties"]["level"].update(maximum={})]
        for i, mutate in enumerate(mutations):
            case = family(); mutate(case["bindings"]["fan"])
            with self.subTest(mutation=i), self.assertRaises(PatError):
                extract(case)

    def test_full_domain_remains_guarded_despite_narrow_applicability(self):
        case = family()
        case["artifact"]["applicability"]["all"].append({"field": "parameters.initialLevel", "op": "range", "minimum": 0, "maximum": 20})
        case["bindings"]["fan"]["binding"]["argumentSchemas"]["set_level"]["properties"]["level"]["maximum"] = 50
        for function in (extract, lower):
            with self.subTest(function=function.__name__), self.assertRaisesRegex(PatError, "PAT_ARGUMENT_DOMAIN"):
                function(case)

    def test_parameter_units_frames_and_literal_companions_refuse(self):
        cases = []
        case = family(); case["artifact"]["parameters"]["initialLevel"]["unit"] = "volts"; cases.append(case)
        case = family("focus"); case["artifact"]["parameters"]["initialLevel"]["frame"] = "other:frame"; cases.append(case)
        case = family(); case["artifact"]["steps"][0]["arguments"]["unit"]["literal"] = "volts"; cases.append(case)
        case = family("focus"); case["artifact"]["steps"][0]["arguments"].pop("frame"); cases.append(case)
        for i, case in enumerate(cases):
            with self.subTest(case=i), self.assertRaises(PatError):
                extract(case)

    def test_parameter_companion_full_domain_must_be_single_exact_unit(self):
        case = family()
        case["artifact"]["parameters"]["unit"] = {"valueSchema": {"type": "string", "minLength": 7, "maxLength": 7, "enum": ["percent"]}, "unit": None, "frame": None}
        for step in case["artifact"]["steps"]:
            step["arguments"]["unit"] = {"parameter": "unit"}
        case["parameters"]["unit"] = "percent"
        self.assertEqual(extract(case)["environmentDigest"], lower(case)["environmentDigest"])
        # A nominal percent value cannot hide another declared companion value.
        case["artifact"]["parameters"]["unit"]["valueSchema"]["enum"].append("notunit")
        with self.assertRaises(PatError):
            extract(case)

    def test_primitive_timing_bound_remains_static(self):
        case = family()
        case["artifact"]["steps"][0]["timing"].update(maxRunMs=6000, latestCompletionOffsetMs=6500)
        case["artifact"]["timingBudget"].update(latestCompletionOffsetMs=7000, maxRunSumMs=6500)
        with self.assertRaisesRegex(PatError, "PAT_TIME_BOUNDS"):
            extract(case)

    def test_context_is_strict_and_changes_identity(self):
        first = extract()
        self.assertNotEqual(first["environmentDigest"], extract(deployment="other:deployment")["environmentDigest"])
        for deployment in (None, {}, "", 1):
            with self.subTest(deployment=deployment), self.assertRaises(PatError):
                extract(deployment=deployment)
        for evidence_mode in (None, "physical", True, {}, 1):
            with self.subTest(evidence_mode=evidence_mode), self.assertRaises(PatError):
                extract(evidence_mode=evidence_mode)

    def test_session_excluded_but_dependencies_and_run_identity_change(self):
        case = family(); before = extract(case); plan = lower(case)
        case["bindings"]["fan"]["endpointSession"] = "session:2"
        after, later = extract(case), lower(case)
        self.assertEqual(before["evaluationEnvironment"], after["evaluationEnvironment"])
        self.assertEqual(before["environmentDigest"], after["environmentDigest"])
        self.assertNotEqual(before["dependencies"], after["dependencies"])
        self.assertNotEqual(plan["runBindingDigest"], later["runBindingDigest"])
        self.assertNotEqual(plan["requestDigest"], later["requestDigest"])

    def test_binding_driver_installation_identity_changes_are_visible(self):
        first = extract()
        for field in ("instanceId", "generation", "controlGeneration", "calibrationRevision", "adapterId"):
            case = family(); case["bindings"]["fan"]["binding"][field] = "changed:2"
            with self.subTest(field=field):
                self.assertNotEqual(first["environmentDigest"], extract(case)["environmentDigest"])
        for field in ("driverDigest", "installationDigest"):
            case = family(); case["bindings"]["fan"][field] = "sha256:" + "c" * 64
            with self.subTest(field=field):
                self.assertNotEqual(first["environmentDigest"], extract(case)["environmentDigest"])

    def test_outputs_and_inputs_are_detached(self):
        case = family(); before = copy.deepcopy(case); output = extract(case)
        self.assertEqual(case, before)
        output["dependencies"][0]["bindingGeneration"] = "tampered"
        output["evaluationEnvironment"]["roles"]["fan"]["driverDigest"] = "tampered"
        self.assertEqual(extract(case), extract(before))
        case["bindings"]["fan"]["driverDigest"] = "sha256:" + "d" * 64
        self.assertNotEqual(output["environmentDigest"], extract(case)["environmentDigest"])

    def test_compiler_identity_has_actual_source_and_context_changes(self):
        manifest = compiler.compiler_manifest()
        row = next(row for row in manifest["sources"] if row["path"] == "hms/pat_compiler.py")
        self.assertEqual(row["sha256"], hashlib.sha256((HERE.parent / "hms/pat_compiler.py").read_bytes()).hexdigest())
        self.assertNotEqual(compiler.COMPILER_DIGEST, BASELINE_DIGEST)
        first = extract()
        with patch.object(compiler, "COMPILER_DIGEST", "sha256:" + "e" * 64):
            second, plan = extract(), lower()
        self.assertNotEqual(first["environmentDigest"], second["environmentDigest"])
        self.assertEqual(second["environmentDigest"], plan["environmentDigest"])

    def test_static_environment_does_not_assert_parameter_applicability(self):
        case = family()
        case["artifact"]["applicability"]["all"].append({"field": "parameters.initialLevel", "op": "equals", "literal": 99})
        self.assertEqual(extract(case)["environmentDigest"], extract()["environmentDigest"])
        with self.assertRaisesRegex(PatError, "PAT_NOT_APPLICABLE"):
            lower(case)

    def test_role_map_order_is_deterministic(self):
        case = family()
        case["artifact"]["roles"]["other"] = copy.deepcopy(case["artifact"]["roles"]["fan"])
        case["artifact"]["steps"][1]["role"] = "other"
        case["bindings"]["other"] = copy.deepcopy(case["bindings"]["fan"])
        case["bindings"]["other"]["binding"]["instanceId"] = "sim:other"
        before = extract(case)
        case["bindings"] = dict(reversed(list(case["bindings"].items())))
        case["artifact"]["roles"] = dict(reversed(list(case["artifact"]["roles"].items())))
        self.assertEqual(before, extract(case))
        self.assertEqual([row["role"] for row in before["dependencies"]], ["fan", "other"])

    def test_baseline_lowering_equal_with_only_implementation_identity_normalized(self):
        self.assertEqual(hashlib.sha256(FAMILY_PATH.read_bytes()).hexdigest(),
                         BASELINE["provenance"]["descriptorFixtures"]["sha256"])
        self.assertEqual(len(BASELINE["positives"]), 6)
        for record in BASELINE["positives"]:
            case = family(record["family"])
            case["parameters"] = copy.deepcopy(record["parameters"])
            expected = record["output"]
            with self.subTest(family=record["family"], parameters=record["parameters"]):
                actual = lower(case, **record["options"])
                for field in ("request", "requestDigest", "patDigest", "dependencies", "report"):
                    self.assertEqual(expected[field], actual[field])
                # Compare the complete old output, changing only implementation
                # identity for this compatibility oracle. Other tests use the
                # actual imported compiler identity.
                with patch.object(compiler, "COMPILER_DIGEST", BASELINE_DIGEST):
                    self.assertEqual(expected, lower(case, **record["options"]))

    def test_existing_concrete_parameter_time_identity_and_context_checks_remain(self):
        self.assertEqual(len(BASELINE["negatives"]), 9)
        self.assertTrue(any(type(row["parameters"]["initialLevel"]) is float for row in BASELINE["negatives"]))
        for i, record in enumerate(BASELINE["negatives"]):
            case = family(record["family"])
            case["parameters"] = copy.deepcopy(record["parameters"])
            with self.subTest(case=i):
                with self.assertRaises(PatError) as new:
                    lower(case, **record["options"])
                self.assertEqual(new.exception.code, record["errorCode"])
