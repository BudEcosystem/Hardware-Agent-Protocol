"""BHMS-DEV-071: compact layouts must be mirrored by the description's schemas.

Checks the example sidecar and the canonical spec example (spec/bhms/examples):
a scaled field needs multipleOf == scale and bounds inside the wire range; an
unscaled integer wire field needs `type: integer` or `multipleOf: 1`; bool
mirrors boolean and f32 mirrors number. Also checks the generated digest header
is in sync with the sidecar.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SDK_C = HERE.parents[1]
ROOT = HERE.parents[3]
SIDECAR = SDK_C / "arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json"
HEADER = SDK_C / "arduino/BHMS/examples/LedAnalog/led_analog_digest.h"
SPEC_EXAMPLE = ROOT / "spec/bhms/examples/devices.describe.response.json"

RANGE = {"u8": (0, 255), "i8": (-128, 127), "u16": (0, 65535), "i16": (-32768, 32767),
         "u32": (0, 2**32 - 1), "i32": (-2**31, 2**31 - 1)}


def mirror_problems(where, schema, field):
    """Return the DEV-071 violations of one compact field against its schema."""
    t, scale = field["type"], field.get("scale")
    out = []
    if t == "bool":
        if schema.get("type") != "boolean" or scale is not None:
            out.append(f"{where}: bool must mirror boolean without scale")
    elif t == "f32":
        if schema.get("type") not in ("number", "integer"):
            out.append(f"{where}: f32 must mirror number")
    else:
        lo, hi = RANGE[t]
        if scale is not None:
            if schema.get("multipleOf") != scale:
                out.append(f"{where}: scaled field needs multipleOf == scale")
            lo, hi = lo * scale, hi * scale
        elif schema.get("type") != "integer" and schema.get("multipleOf") != 1:
            out.append(f"{where}: unscaled integer field needs type integer or multipleOf 1")
        for key, bound, cmp in (("minimum", lo, lambda a, b: a >= b - 1e-9),
                                ("maximum", hi, lambda a, b: a <= b + 1e-9)):
            if key in schema and not cmp(schema[key], bound):
                out.append(f"{where}: {key} {schema[key]} outside the wire range")
    return out


def description_problems(desc):
    problems = []
    for name, act in desc["actions"].items():
        c = act.get("compact")
        if not c:
            continue
        for f in c["args"]:
            problems += mirror_problems(f"{name}.args.{f['name']}",
                                        act["input"]["properties"][f["name"]], f)
        for f in c["result"]:
            problems += mirror_problems(f"{name}.result.{f['name']}",
                                        act["output"]["properties"][f["name"]], f)
    for name, prop in desc["properties"].items():
        c = prop.get("compact")
        if c:
            problems += mirror_problems(f"property {name}", prop["schema"], c)
    return problems


class DescriptionMirror(unittest.TestCase):
    def test_sidecar_is_mirrored(self):
        self.assertEqual(description_problems(json.loads(SIDECAR.read_text())), [])

    def test_canonical_spec_example_is_mirrored(self):
        desc = json.loads(SPEC_EXAMPLE.read_text())["message"]["result"]["description"]
        self.assertEqual(description_problems(desc), [])

    def test_checker_rejects_a_bare_number_for_an_integer_wire_field(self):
        bad = {"type": "number", "minimum": 1, "maximum": 500}
        self.assertTrue(mirror_problems("rate", bad, {"name": "rate", "type": "u16"}))
        self.assertEqual(mirror_problems("rate", {"type": "integer"}, {"name": "rate", "type": "u16"}), [])
        self.assertEqual(mirror_problems("r", {"type": "number", "multipleOf": 1}, {"name": "r", "type": "u8"}), [])

    @unittest.skipUnless(importlib.util.find_spec("pydantic"), "needs the sdk/python models")
    def test_digest_header_matches_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "h.h"
            subprocess.run([sys.executable, "-B", str(SDK_C / "tools/bhms_digest.py"), str(SIDECAR),
                            "--header", str(out)], check=True, capture_output=True)
            self.assertEqual(out.read_text(), HEADER.read_text())


if __name__ == "__main__":
    unittest.main()
