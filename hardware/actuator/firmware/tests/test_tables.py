"""The firmware's constant tables must equal cad/params.py (the source of truth) and the compact
layouts must equal arm.sidecar.json field for field (index, type, scale, local limits, lease flag),
so the gateway's translation and the device's own checks cannot disagree.

Runs the `dump_tables` helper built by CMake (BHMS_DUMP_TABLES).
"""
import importlib.util
import json
import math
import os
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
FW = HERE.parent
ROOT = FW.parents[2]
sys.path.insert(0, str(ROOT / "hardware" / "actuator" / "cad"))
import params  # noqa: E402

_spec = importlib.util.spec_from_file_location("mirror", ROOT / "sdk/c/tests/host/test_description_mirror.py")
mirror = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror)

DUMP = json.loads(subprocess.run([os.environ["BHMS_DUMP_TABLES"]], check=True, capture_output=True,
                                 text=True).stdout)
SIDECAR = json.loads((FW / "arm.sidecar.json").read_text())
ARM = params.Arm()
TOOLS = params.Tools()
INTERFACE = (FW / "INTERFACE.md").read_text()

RANGE = {"u8": (0, 255), "i8": (-128, 127), "u16": (0, 65535), "i16": (-32768, 32767),
         "u32": (0, 2**32 - 1), "i32": (-2**31, 2**31 - 1)}


class ParamsSync(unittest.TestCase):
    def test_joints(self):
        joints = DUMP["servos"][:5]
        self.assertEqual(len(joints), len(ARM.joints))
        for c, p in zip(joints, ARM.joints):
            self.assertEqual(c["name"], p.name)
            self.assertEqual(c["id"], p.servo_id)
            self.assertEqual((c["lo"], c["hi"]), (p.lower_deg, p.upper_deg))
            self.assertEqual(c["ratio"], p.ratio)
            self.assertEqual(c["torque"], round(p.torque_limit * 1000))
        # The shoulder cap is a design requirement (docs/design.md section 4): 78 %.
        self.assertEqual(joints[1]["torque"], 780)

    def test_tool_servos_match_interface(self):
        tool = DUMP["servos"][5:]
        self.assertEqual([t["id"] for t in tool], [6, 7, 8])
        # INTERFACE.md section 3.1: gripper at most 15 %, knob 2.5 %, presser 20 %.
        self.assertEqual([t["torque"] for t in tool], [150, 25, 200])
        self.assertAlmostEqual(tool[0]["hi"], TOOLS.gripper_stroke / 12.0 * 180 / math.pi, places=2)
        self.assertEqual(tool[2]["hi"], 180.0)

    def test_coupled_limits(self):
        self.assertEqual(len(DUMP["coupled"]), len(ARM.coupled_limits))
        for c, p in zip(DUMP["coupled"], ARM.coupled_limits):
            self.assertEqual((c["name"], tuple(c["joints"]), c["lo"], c["hi"]),
                             (p.name, p.joints, p.lo, p.hi))

    def test_speed_pose_tools(self):
        self.assertEqual(DUMP["noload"], params.Servo().no_load_speed_rad_s)
        self.assertEqual(DUMP["pullup"], TOOLS.tool_id_pullup)
        self.assertEqual([(t["code"], t["name"], t["r"]) for t in DUMP["tools"]],
                         [(c, n, r) for c, n, r in TOOLS.tool_ids])
        # Rest pose: INTERFACE.md section 4 "yaw 0, shoulder 30, elbow 90, wrist 45, roll 0".
        self.assertEqual(DUMP["rest"], [0, 30, 90, 45, 0])
        self.assertIn("yaw 0°, shoulder 30°, elbow 90°, wrist 45°, roll 0°", INTERFACE)
        self.assertEqual(DUMP["margin"], 3.0)
        # The rest pose is itself inside every limit, with the enable margin.
        q = dict(zip([j.name for j in ARM.joints], DUMP["rest"]))
        self.assertTrue(ARM.coupled_ok(q))


class SidecarSync(unittest.TestCase):
    def test_mirror_rules(self):
        self.assertEqual(mirror.description_problems(SIDECAR), [])

    def test_digest_header_equals_sidecar(self):
        sys.path.insert(0, str(ROOT / "sdk/c/tools"))
        import bhms_digest
        self.assertEqual(list(bhms_digest.digest_of(SIDECAR)[:8]), DUMP["digest8"])

    def test_device_flags(self):
        self.assertEqual((DUMP["fencing"], DUMP["stop"]), (1, 1))
        self.assertEqual(SIDECAR["safety"]["stop"], "supported")

    def test_actions_match(self):
        acts = SIDECAR["actions"]
        self.assertEqual(len(acts), len(DUMP["actions"]))
        for name, spec in acts.items():
            c = DUMP["actions"][spec["compact"]["index"]]
            self.assertEqual(c["lease"], 1 if spec["requiresLease"] else 0, name)
            self.assertEqual(c["cancel"], 1 if spec["cancel"] == "supported" else 0, name)
            self.check_fields(name, spec["compact"]["args"], c["args"], spec["input"]["properties"])
            self.check_fields(name, spec["compact"]["result"], c["results"], spec["output"]["properties"])
        # Every motion/power/tool action needs a lease, hold does not; all hazardous ones are leased (DEV-033).
        for name, spec in acts.items():
            if spec["effect"] == "hazardous":
                self.assertTrue(spec["requiresLease"], name)
        self.assertFalse(acts["hold"]["requiresLease"])

    def check_fields(self, name, layout, cfields, schema_props):
        self.assertEqual(len(layout), len(cfields), name)
        for f, c in zip(layout, cfields):
            self.assertEqual(f["type"], c["type"], f"{name}.{f['name']}")
            sch = schema_props[f["name"]]
            scale = f.get("scale")
            if f["type"] in RANGE and "lo" in c:
                # Local limits are in wire units: the schema's minimum/maximum divided by the scale.
                k = scale or 1
                self.assertEqual(c["lo"], round(sch["minimum"] / k), f"{name}.{f['name']} lo")
                self.assertEqual(c["hi"], round(sch["maximum"] / k), f"{name}.{f['name']} hi")
            elif f["type"] in RANGE and "minimum" in sch and scale is None:
                lo, hi = RANGE[f["type"]]
                self.assertTrue(lo <= sch["minimum"] <= sch["maximum"] <= hi)

    def test_joint_ranges_in_description_equal_params(self):
        move = SIDECAR["actions"]["move_joints"]["input"]["properties"]
        for j in ARM.joints:
            self.assertEqual((move[j.name]["minimum"], move[j.name]["maximum"]), (j.lower_deg, j.upper_deg))
        for c, f in zip(DUMP["actions"][0]["args"][:5], ARM.joints):
            self.assertEqual((c["lo"], c["hi"]), (round(f.lower_deg * 100), round(f.upper_deg * 100)))

    def test_properties_match(self):
        props = SIDECAR["properties"]
        self.assertEqual(len(props), len(DUMP["properties"]))
        for name, spec in props.items():
            idx = spec["compact"]["index"]
            self.assertEqual(DUMP["properties"][idx]["type"], spec["compact"]["type"], name)
        # Measured evidence is claimed only for things the firmware measures.
        self.assertEqual(props["estop_state"]["evidence"], "measured")
        self.assertEqual(props["estop_contact_open"]["evidence"], "measured")
        self.assertEqual(props["servo_rail_mv"]["evidence"], "measured")
        self.assertEqual(props["base_yaw_position_deg"]["evidence"], "measured")


if __name__ == "__main__":
    unittest.main()
