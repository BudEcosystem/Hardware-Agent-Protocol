#!/usr/bin/env python3
"""Generate arm.sidecar.json (the BHMS device description of the BHMS Arm) and the digest
header core/arm_digest.h from it.

The joint ranges come from hardware/actuator/cad/params.py (the single source of truth);
action and property order must equal the compact indices in core/arm_device.h (a test,
tests/test_device_table.py, compares this description to the C tables).

    gen_sidecar.py            # (re)write arm.sidecar.json and core/arm_digest.h
    gen_sidecar.py --check    # fail if either file is out of date
"""
import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
FW = HERE.parent
ROOT = FW.parents[2]
sys.path.insert(0, str(ROOT / "hardware" / "actuator" / "cad"))
sys.path.insert(0, str(ROOT / "sdk" / "c" / "tools"))

import params  # noqa: E402
import bhms_digest  # noqa: E402

ARM = params.Arm()
J = [j.name for j in ARM.joints]
LIM = {j.name: (j.lower_deg, j.upper_deg) for j in ARM.joints}

FAULTS = ("1 estop, 2 estop_fault_contact_A_or_Q2, 3 servo_rail_fault, 4 overcurrent, "
          "5 servo_comm, 6 servo_error, 7 tool_lost, 8 timeout, 9 overtemp, 10 stopped, "
          "11 bus_collision, 12 limit, 13 selftest, 14 no_actuator_power, 15 power_sense, "
          "16 servo_config, 17 tool, 18 following_error, 19 watchdog_reset, 20 calibration, 21 stall")
WHY = ("1 estop_latched, 2 estop_pressed, 3 hard_fault, 4 fault, 5 not_enabled, 6 parked, "
       "7 no_actuator_power, 8 no_tool, 9 wrong_tool, 10 tool_not_ready, 11 tool_mounted, "
       "12 tool_reserved, 13 power_sense, 14 stopping, 15 not_calibrated, 16 overtemp, "
       "17 not_disabled")
LIMITS = ("detail 0..4 = joint range of base_yaw, shoulder_pitch, elbow_pitch, wrist_pitch, "
          "wrist_roll; 16 = coupled forearm_pitch (shoulder+elbow <= 175 deg), "
          "17 = hairpin (elbow+wrist_pitch <= 165 deg), 18 = tool_pitch "
          "(shoulder+elbow+wrist_pitch <= 183 deg); 240 = speed")


def num(unit, lo=None, hi=None, mult=None, integer=False):
    s = {"type": "integer" if integer else "number", "x-bhms-unit": unit}
    if lo is not None:
        s["minimum"] = lo
    if hi is not None:
        s["maximum"] = hi
    if mult is not None:
        s["multipleOf"] = mult
    return s


def obj(props, required=None):
    return {"type": "object", "additionalProperties": False,
            "required": list(props) if required is None else required, "properties": props}


def prop(desc, schema, evidence, ctype, scale=None, rate=None):
    c = {"type": ctype}
    if scale is not None:
        c["scale"] = scale
    p = {"description": desc, "schema": schema, "evidence": evidence, "observable": False,
         "readEffect": "none", "compact": c}
    return p


def build_properties():
    props = []  # (name, spec) in compact-index order
    for name in J:
        lo, hi = LIM[name]
        props.append((f"{name}_position_deg", prop(
            f"Measured angle of {name} from its servo's absolute encoder (cached, refreshed about every 25 ms).",
            num("deg", lo - 5, hi + 5), "measured", "f32")))
    for name in J:
        props.append((f"{name}_load_pct", prop(
            f"Servo load of {name}, signed, 0.1 % of the servo's rated torque per count.",
            num("%", -100, 100, 0.1), "measured", "i16", 0.1)))
    for name in J:
        props.append((f"{name}_current_ma", prop(
            f"Servo current of {name}.", num("mA", 0, 65535, integer=True), "measured", "u16")))
    for name in J:
        props.append((f"{name}_temperature_c", prop(
            f"Servo temperature of {name}. The servo protects itself at 70 C.",
            num("Cel", 0, 255, integer=True), "measured", "u8")))
    for name in J:
        props.append((f"{name}_speed_dps", prop(
            f"Measured angular speed of {name}.", num("deg/s", -2000, 2000), "measured", "f32")))
    props += [
        ("vin_mv", prop("Input supply voltage VIN (ADC x 11). Below 9000 mV the arm reports no actuator power.",
                        num("mV", 0, 65535, integer=True), "measured", "u16")),
        ("servo_rail_mv", prop("Servo-rail voltage measured by the INA219 (4 mV LSB).",
                               num("mV", 0, 65535, integer=True), "measured", "u16")),
        ("servo_rail_ma", prop("Servo-rail current measured by the INA219.",
                               num("mA", -32768, 32767, integer=True), "measured", "i16")),
        ("estop_contact_open", prop("E-stop contact B (GPIO8): true when the mushroom is pressed, "
                                    "the loop is open, or the connector is out.",
                                    {"type": "boolean"}, "measured", "bool")),
        ("estop_state", prop("Measured E-stop state from contact B and the rail: 0 released, 1 pressed, "
                             "2 fault (contact A welded or Q2 shorted: GPIO8 high with the rail above 2 V; "
                             "latched until power-cycle).",
                             num("1", 0, 2, integer=True), "measured", "u8")),
        ("estop_latched", prop("Firmware restart inhibit: true after an E-stop until an explicit enable "
                               "action with the contact released.", {"type": "boolean"}, "reported", "bool")),
        ("arm_state", prop("0 boot, 1 no actuator power (USB only), 2 disabled, 3 enabling, 4 ready, "
                           "5 moving, 6 parked (torque released), 7 estop, 8 fault.",
                           num("1", 0, 8, integer=True), "reported", "u8")),
        ("fault_code", prop("Last latched fault, 0 = none: " + FAULTS + ".",
                            num("1", 0, 255, integer=True), "reported", "u8")),
        ("torque_enabled", prop("Whether the arm servos are holding torque.", {"type": "boolean"},
                                "commanded", "bool")),
        ("tool_id", prop("Tool identity decoded from the TOOL_ID divider after 5 stable samples: "
                         "0 none, 1 gripper, 2 knob_turner, 3 button_presser, 4 slider_pusher, "
                         "5..8 reserved, 254 short circuit.", num("1", 0, 255, integer=True), "measured", "u8")),
        ("tool_state", prop("0 none, 1 detected (unpowered), 2 powering, 3 ready, 4 lost (hot unplug), "
                            "5 unmounting.", num("1", 0, 5, integer=True), "reported", "u8")),
        ("gripper_opening_mm", prop("Measured gripper opening between the finger pads (gripper ready only).",
                                    num("mm", 0, 61), "measured", "f32")),
        ("knob_angle_deg", prop("Knob-turner output angle relative to the mount position, multi-turn, "
                                "from the servo (knob turner ready only).", num("deg", -1300, 1300),
                                "measured", "f32")),
        ("knob_sensor_deg", prop("Knob-turner output encoder (AS5600 analog out), single turn "
                                 "(knob turner ready only).", num("deg", 0, 360), "measured", "f32")),
        ("presser_force_pct", prop("Button-presser FSR reading as a percentage of full scale above the "
                                   "reading at mount (uncalibrated; presser ready only).",
                                   num("%", 0, 100), "measured", "f32")),
        ("pose_unknown", prop("True when the arm may have moved while unpowered (after an E-stop or "
                              "power loss): re-home before use.", {"type": "boolean"}, "reported", "bool")),
        ("calibrated", prop("True when the joint zero offsets come from a stored calibration. Until then "
                            "every limit is relative to an assumed zero and enable is refused.",
                            {"type": "boolean"}, "reported", "bool")),
        ("watchdog_reset", prop("True when the controller reset itself (watchdog) since power-up: servo "
                                "power dropped and the arm may have fallen; enable again.",
                                {"type": "boolean"}, "reported", "bool")),
        ("temperature_warning", prop("True when any joint servo is at or above 60 C. Motion is refused "
                                     "at 70 C.", {"type": "boolean"}, "measured", "bool")),
        ("servo_error", prop("Servo id (high byte) and status error bits (low byte: 1 voltage, 2 sensor, "
                             "4 temperature, 8 current, 0x20 overload) of the last servo-error fault.",
                             num("1", 0, 65535, integer=True), "measured", "u16")),
        ("move_error_deg", prop("Worst joint error at the end of the last move, also when it failed.",
                                num("deg", 0, 720), "measured", "f32")),
    ]
    return props


def field(name, ctype, scale=None):
    f = {"name": name, "type": ctype}
    if scale is not None:
        f["scale"] = scale
    return f


def action(desc, inp, out, effect, idem, cancel, evidence, max_ms, lease, resources,
           args, result, verified=None, typical=None, pre=None, lease_loss="hold"):
    a = {"description": desc, "input": obj(inp), "output": obj(out), "effect": effect,
         "idempotency": idem, "cancel": cancel, "completionEvidence": evidence,
         "maxDurationMs": max_ms, "requiresLease": lease, "resources": resources,
         "onLeaseLoss": lease_loss,
         "compact": {"index": 0, "args": args, "result": result}}
    if verified:
        a["verifiedBy"] = verified
    if typical:
        a["typicalDurationMs"] = typical
    if pre:
        a["preconditions"] = pre
    return a


def build_actions():
    pos = [f"{n}_position_deg" for n in J]
    jin = {n: num("deg", LIM[n][0], LIM[n][1], 0.01) for n in J}
    jin["speed_pct"] = num("%", 5, 100, integer=True)
    # The pose must also satisfy the three coupled limits; the device refuses it otherwise.
    move = action(
        "Move all five joints to absolute angles along a straight line in joint space, at speed_pct of "
        "the per-joint speed limit (servo no-load speed / ratio). The device refuses a goal outside any "
        "joint range or coupled limit with OUT_OF_RANGE: " + LIMITS + ". Every waypoint and every "
        "fresh measured pose (4 deg slack) is checked on the device, with a 15 deg following-error "
        "bound: a jammed or lagging joint freezes the arm at its measured pose and fails the move "
        "(fault 12 or 18); the arm then accepts only a move back inside, enable or hold. Result: "
        "worst joint error at the end, measured.",
        jin, {"max_error_deg": num("deg", 0, 655.35, 0.01)}, "reversible", "absolute", "supported",
        "measured", 60000, True, ["bhms-arm/joints"],
        [field(n, "i16", 0.01) for n in J] + [field("speed_pct", "u8")],
        [field("max_error_deg", "u16", 0.01)], verified=pos, typical=1500,
        pre="Arm state ready (enable first); E-stop released and not latched.")
    home = action(
        "Move to the rest pose (yaw 0, shoulder 30, elbow 90, wrist pitch 45, roll 0 deg; forearm on "
        "the support) at no more than 30 % speed. Result: worst joint error, measured.",
        {"speed_pct": num("%", 5, 100, integer=True)}, {"max_error_deg": num("deg", 0, 655.35, 0.01)},
        "reversible", "idempotent", "supported", "measured", 60000, True, ["bhms-arm/joints"],
        [field("speed_pct", "u8")], [field("max_error_deg", "u16", 0.01)], verified=pos, typical=3000,
        pre="Arm state ready.")
    hold = action(
        "Freeze the arm where it is: abort a running motion (it ends canceled) and keep holding torque.",
        {}, {}, "none", "idempotent", "unsupported", "reported", 1000, False, [], [], [], typical=10,
        lease_loss="finish")
    release = action(
        "Release torque on the five arm joints. The arm first moves to the rest pose at 25 % speed so it "
        "settles on the support (the gear trains are not self-locking), then torque is disabled and the "
        "arm is parked. Needs an explicit enable afterwards.",
        {}, {}, "hazardous", "idempotent", "supported", "measured", 90000, True, ["bhms-arm/joints"],
        [], [], verified=pos, typical=5000, pre="Arm state ready.")
    enable = action(
        "Energise the arm: boot self-test of the servo rail (first time), rail on, ping, verify and "
        "program every servo's angle window, torque cap (shoulder 78 %) and return delay, read back the "
        "measured pose and refuse if it violates a joint or coupled limit with a 3 deg margin, then "
        "set goal = present and enable torque. The only way out of an E-stop latch; refused (INHIBITED) "
        "while the E-stop contact is open.",
        {}, {}, "hazardous", "idempotent", "supported", "measured", 15000, True, ["bhms-arm/power"],
        [], [], verified=["servo_rail_mv", "torque_enabled"], typical=1500,
        pre="E-stop released; VIN >= 9 V; not a contact A/Q2 fault.")
    mount = action(
        "Power the tool on the flange and bring it up (INTERFACE section 5): tool ID stable, TOOL_EN on, "
        "wait 50 ms, ping the tool servo, program its limits and enable torque. Result: tool_id.",
        {}, {"tool_id": num("1", 1, 4, integer=True)}, "reversible", "idempotent", "supported",
        "measured", 8000, True, ["bhms-arm/tool"], [], [field("tool_id", "u8")], verified=["tool_state"],
        typical=1000, pre="Arm ready; a valid tool (1..4) detected and unpowered.")
    unmount = action(
        "Tool-change step before the unlocking roll: disable the tool servo's torque, clear TOOL_EN and "
        "wait out the V_TOOL discharge (60 ms). The client then rolls the wrist -30 deg and retracts "
        "(move_joints). Refused while the E-stop is not released.",
        {}, {}, "reversible", "idempotent", "supported", "measured", 3000, True, ["bhms-arm/tool"],
        [], [], verified=["tool_state"], typical=100, pre="Tool ready.")
    grip = action(
        "Move the gripper to a total opening and limit the finger force (servo torque cap, at most 15 %). "
        "If the fingers stop short of the target for 250 ms the object is grasped (grasped = true). "
        "Result: measured opening.",
        {"width_mm": num("mm", 0, 60, 0.1), "force_pct": num("%", 1, 15, integer=True)},
        {"width_mm": num("mm", 0, 60, 0.1), "grasped": {"type": "boolean"}},
        "hazardous", "absolute", "supported", "measured", 8000, True, ["bhms-arm/tool"],
        [field("width_mm", "u16", 0.1), field("force_pct", "u8")],
        [field("width_mm", "u16", 0.1), field("grasped", "bool")], verified=["gripper_opening_mm"],
        typical=800, pre="Gripper ready.")
    turn = action(
        "Turn the knob to an absolute multi-turn angle relative to the mount position, with a servo "
        "torque cap of torque_pct (at most 2.5 %, which keeps the spiral flexure within +-25 deg). "
        "A move that stops short (torque cap, mechanical stop) fails with fault 21; the angle "
        "reached stays readable as knob_angle_deg.",
        {"angle_deg": num("deg", -1200, 1200, 0.1), "torque_pct": num("%", 0.1, 2.5, 0.1)},
        {"angle_deg": num("deg", -1200, 1200, 0.1), "reached": {"type": "boolean"}},
        "hazardous", "absolute", "supported", "measured", 40000, True, ["bhms-arm/tool"],
        [field("angle_deg", "i16", 0.1), field("torque_pct", "u8", 0.1)],
        [field("angle_deg", "i16", 0.1), field("reached", "bool")], verified=["knob_angle_deg"],
        typical=3000, pre="Knob turner ready.")
    press = action(
        "Extend the presser cam toward depth_mm, stop at force_limit_pct of the FSR scale, then retract. "
        "Result: peak force and the depth reached. The force scale is uncalibrated (percent of FSR full "
        "scale above the mount reading).",
        {"depth_mm": num("mm", 0, 7.8, 0.1), "force_limit_pct": num("%", 1, 100, integer=True)},
        {"peak_force_pct": num("%", 0, 100, integer=True), "depth_mm": num("mm", 0, 25.5, 0.1)},
        "hazardous", "absolute", "supported", "measured", 8000, True, ["bhms-arm/tool"],
        [field("depth_mm", "u8", 0.1), field("force_limit_pct", "u8")],
        [field("peak_force_pct", "u8"), field("depth_mm", "u8", 0.1)], verified=["presser_force_pct"],
        typical=1200, pre="Button presser ready.")
    calibrate = action(
        "Calibrate the joint zero offsets. With the arm resting at the rest pose on its support (yaw 0, "
        "shoulder 30, elbow 90, wrist pitch 45, roll 0 deg) and the servo rail off, the device powers the "
        "rail with torque off, reads every joint's raw position, defines it as the rest pose, switches the "
        "rail off and stores the offsets in flash (two-copy, CRC). Nothing moves. Refused unless the arm is "
        "disabled. Enable is refused until the arm is calibrated.",
        {}, {}, "irreversible", "idempotent", "supported", "measured", 20000, True,
        ["bhms-arm/joints", "bhms-arm/power"], [], [], verified=["calibrated"], typical=2500,
        pre="Rail off, E-stop released, VIN >= 9 V; arm resting at the rest pose.")
    return [("move_joints", move), ("home", home), ("hold", hold), ("release_torque", release),
            ("enable", enable), ("tool_mount", mount), ("tool_unmount", unmount), ("grip", grip),
            ("turn", turn), ("press", press), ("calibrate", calibrate)]


def build():
    props = build_properties()
    acts = build_actions()
    for i, (_, a) in enumerate(acts):
        a["compact"]["index"] = i
    for i, (_, p) in enumerate(props):
        p["compact"]["index"] = i
    return {
        "deviceId": "bhms-arm",
        "name": "BHMS Arm",
        "description": ("A 5-axis desktop arm (STS3215 servos) with a quick-change tool flange (gripper, "
                        "knob turner, button presser, slider pusher), driven by an RP2040 controller over "
                        "BHMS-Compact. Joint ranges, three coupled pitch limits, the shoulder torque cap "
                        "and the E-stop restart inhibit are enforced on the device. After an E-stop the "
                        "arm may have moved: re-home before use. Faults: " + FAULTS + "."),
        "capabilities": ["bhms.arm.joints", "bhms.arm.tool"],
        "tags": ["bhms-arm"],
        "resources": ["bhms-arm/joints", "bhms-arm/power", "bhms-arm/tool"],
        "identity": {"manufacturer": "Bud Labs", "model": "BHMS Arm", "firmwareVersion": "1.0.0"},
        "properties": {n: p for n, p in props},
        "actions": {n: a for n, a in acts},
        "safety": {
            "stop": "supported", "stopEvidence": "measured", "stopMaxDurationMs": 3000,
            "onDisconnect": "unknown",
            "summary": ("STOP freezes motion and keeps holding torque (confirmed from servo moving flags). "
                        "The E-stop button cuts the servo rail in hardware; the arm has no brakes and "
                        "falls, then the device latches and refuses motion until an explicit enable with "
                        "the contact released. Link loss does not stop the arm."),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    desc = build()
    text = json.dumps(desc, indent=2) + "\n"
    raw = bhms_digest.digest_of(desc)
    header = bhms_digest.header_text("arm.sidecar.json", raw)
    out_json = FW / "arm.sidecar.json"
    out_h = FW / "core" / "arm_digest.h"
    if args.check:
        ok = out_json.read_text() == text and out_h.read_text() == header
        print("up to date" if ok else "OUT OF DATE: run tools/gen_sidecar.py")
        return 0 if ok else 1
    out_json.write_text(text)
    out_h.write_text(header)
    print("sha256:" + raw.hex())
    return 0


if __name__ == "__main__":
    sys.exit(main())
