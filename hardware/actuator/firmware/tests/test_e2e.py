"""End-to-end: the firmware's real endpoint and arm logic (sim_arm, host build under ASan/UBSan)
on a pty, driven by the Task 9a Python harness (an independent struct-based implementation of the
BHMS-Compact layouts): HELLO -> enable -> move_joints in limits -> coupled-limit violation refused
(OUT_OF_RANGE naming the limit) -> E-stop pressed mid-move (operation stopped, state measured)
-> restart inhibit -> STOP.

BHMS_SIM_ARM is the sim_arm executable.
"""
import os
import pathlib
import struct
import sys
import tempfile
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
FW = HERE.parent
ROOT = FW.parents[2]
sys.path.insert(0, str(ROOT / "sdk/c/tests/host"))
sys.path.insert(0, str(ROOT / "hardware/actuator/cad"))

import bhms_host as h  # noqa: E402
import params  # noqa: E402

SIDECAR = __import__("json").loads((FW / "arm.sidecar.json").read_text())
DIGEST8 = bytes.fromhex(__import__("subprocess").run(
    [sys.executable, "-B", str(ROOT / "sdk/c/tools/bhms_digest.py"), str(FW / "arm.sidecar.json")],
    check=True, capture_output=True, text=True).stdout.split()[0][len("sha256:"):])[:8]
TIMEOUT = 6.0
ACT = {n: spec["compact"]["index"] for n, spec in SIDECAR["actions"].items()}
PROP = {n: spec["compact"]["index"] for n, spec in SIDECAR["properties"].items()}
ST = dict(ACCEPTED=1, RUNNING=2, COMPLETED=3, FAILED=4, CANCELED=5, REJECTED=6)
CODE = h.ERR

CAPS = params.Arm()


def i16(deg: float) -> bytes:
    return struct.pack("<h", round(deg * 100))


def move_args(yaw, sh, el, wr, roll, speed=100) -> bytes:
    return i16(yaw) + i16(sh) + i16(el) + i16(wr) + i16(roll) + bytes([speed])


class Arm:
    def __init__(self, tmp: pathlib.Path, extra=()):
        self.tmp = tmp
        self.fifo = tmp / "ctl"
        if not self.fifo.exists():
            os.mkfifo(self.fifo)
        self.ctl = os.open(self.fifo, os.O_RDWR | os.O_NONBLOCK)
        cmd = [os.environ["BHMS_SIM_ARM"], "--epoch", str(tmp / "epoch.bin"), "--ctl", str(self.fifo), *extra]
        self.target = h.spawn(cmd, tmp / f"stderr{time.monotonic_ns()}.txt")
        self.link = h.Link(self.target)
        self.session = 0
        self.handle = 0
        self.fence = 0
        self.backlog = []

    def close(self):
        self.target.close()
        os.close(self.ctl)

    def hw(self, line: str):
        os.write(self.ctl, (line + "\n").encode())

    def state_lines(self):
        return [l for l in self.target.stderr_lines() if l.startswith(("STATE", "SERVO_EN", "TOOL_EN"))]

    def hello(self):
        sent, wire, fr = self.link.exchange(h.hello_req(0xBEEF), 0, TIMEOUT)
        assert fr is not None, "no HELLO"
        p = fr.payload
        assert p[0] == h.HELLO
        t, ver, flags, digest, epoch, nonce, last, ring, max_active, max_args = struct.unpack("<BBB8sIIHBBB", p)
        self.session = epoch
        return dict(flags=flags, digest=digest, epoch=epoch, ring=ring, max_active=max_active, max_args=max_args)

    def next(self, timeout=TIMEOUT):
        if self.backlog:
            return self.backlog.pop(0)
        wire, fr = self.link.recv(timeout)
        return None if fr is None else fr

    def invoke(self, action: str, args: bytes = b"", lease=True):
        self.handle += 1
        if lease:
            self.fence += 1
        self.link.send(h.invoke(self.handle, ACT[action], args, fence=self.fence if lease else 0), self.session)
        return self.handle

    def until(self, pred, timeout=TIMEOUT):
        """Collect frames until pred(msg) is true; returns (matching msg, all frames seen)."""
        seen, deadline = [], time.monotonic() + timeout
        while time.monotonic() < deadline:
            fr = self.next(max(0.05, deadline - time.monotonic()))
            if fr is None:
                continue
            m = parse(fr)
            seen.append(m)
            if pred(m):
                return m, seen
        raise AssertionError(f"timeout; saw {seen}")

    def result(self, handle, timeout=TIMEOUT):
        m, _ = self.until(lambda m: m["type"] == "result" and m["handle"] == handle, timeout)
        return m

    def error(self, timeout=TIMEOUT):
        m, _ = self.until(lambda m: m["type"] == "error", timeout)
        return m

    def read(self, prop: str, fresh=False):
        req = 100 + PROP[prop]
        self.link.send(h.read(req, PROP[prop], fresh), self.session)
        m, _ = self.until(lambda m: m["type"] == "value" and m["request"] == req)
        return m

    def enable(self):
        hdl = self.invoke("enable")
        r = self.result(hdl)
        assert r["state"] == ST["COMPLETED"], r
        return r


def parse(fr):
    p = fr.payload
    t = p[0]
    if t == h.STATUS_MSG:
        _, hd, st, cancel, prog = struct.unpack("<BHBBB", p[:6])
        return dict(type="status", handle=hd, state=st, cancel=cancel, progress=prog, kind=fr.kind)
    if t == h.RESULT:
        _, hd, st, ev, fault = struct.unpack("<BHBBB", p[:6])
        return dict(type="result", handle=hd, state=st, evidence=ev, fault=fault, fields=p[6:], kind=fr.kind)
    if t == h.ERROR:
        _, rt, ident, code, detail = struct.unpack("<BBHBB", p)
        return dict(type="error", req=rt, id=ident, code=code, detail=detail)
    if t == h.VALUE:
        _, req, prop, q, ev, seq, age = struct.unpack("<BHBBBII", p[:14])
        return dict(type="value", request=req, prop=prop, quality=q, evidence=ev, raw=p[14:], age=age)
    if t == h.STOP_ACK:
        _, outcome, ev, canceled = struct.unpack("<BBBB", p)
        return dict(type="stop_ack", outcome=outcome, evidence=ev, canceled=canceled, kind=fr.kind)
    return dict(type="other", payload=p)


def f32(m):
    return struct.unpack("<f", m["raw"])[0]


class ArmE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.arm = Arm(self.tmp)

    def tearDown(self):
        self.arm.close()
        self._tmp.cleanup()

    def test_acceptance_flow(self):
        a = self.arm
        hello = a.hello()
        # PERSISTENT_EPOCH | STOP_SUPPORTED | FENCING (0x02 | 0x04 | 0x01); the digest is the sidecar's.
        self.assertEqual(hello["flags"], 0x07)
        self.assertEqual(hello["digest"], DIGEST8)
        self.assertEqual(hello["epoch"], 1)
        # Before enable: a valid move is refused with the reason (PRECONDITION, not_enabled = 5).
        a.invoke("move_joints", move_args(20, 40, 60, 5, 10))
        e = a.error()
        self.assertEqual((e["code"], e["detail"]), (CODE["PRECONDITION"], 5))
        # The no-lease path: a motion action without a fence is refused by the endpoint.
        a.invoke("move_joints", move_args(20, 40, 60, 5, 10), lease=False)
        self.assertEqual(a.error()["code"], CODE["LEASE_REQUIRED"])
        # Enable: a measured RESULT, the arm is READY (state 4), torque on.
        r = a.enable()
        self.assertEqual(r["evidence"], 2)
        self.assertEqual(a.read("arm_state")["raw"], bytes([4]))
        self.assertEqual(a.read("torque_enabled")["raw"], bytes([1]))
        # In-limit move: RUNNING then a measured COMPLETED, error < 2 deg.
        hdl = a.invoke("move_joints", move_args(20, 40, 60, 5, 10))
        r = a.result(hdl)
        self.assertEqual((r["state"], r["evidence"]), (ST["COMPLETED"], 2))
        self.assertLess(struct.unpack("<H", r["fields"])[0] / 100.0, 2.0)
        yaw = a.read("base_yaw_position_deg")
        self.assertEqual((yaw["quality"], yaw["evidence"]), (0, 0))  # valid, measured
        self.assertAlmostEqual(f32(yaw), 20.0, delta=2.0)
        self.assertAlmostEqual(f32(a.read("shoulder_pitch_position_deg")), 40.0, delta=2.0)
        # Coupled-limit violations: refused on the device, each naming the limit.
        for pose, detail in [((0, 80, 100, 0, 0), 0x10),     # shoulder+elbow 180 > 175
                             ((0, 0, 100, 70, 0), 0x11),     # elbow+wrist 170 > 165
                             ((0, 50, 40, 95, 0), 0x12),     # sum 185 > 183
                             ((0, 30, 100, 100, 0), 0x11)]:  # the INTERFACE.md example
            a.invoke("move_joints", move_args(*pose))
            e = a.error()
            self.assertEqual((e["code"], e["detail"]), (CODE["OUT_OF_RANGE"], detail), pose)
        # A single joint beyond its own range is refused by the compact layout (detail = argument).
        a.invoke("move_joints", move_args(0, 96, 90, 45, 0))
        e = a.error()
        self.assertEqual((e["code"], e["detail"]), (CODE["OUT_OF_RANGE"], 1))
        # None of that moved the arm.
        self.assertAlmostEqual(f32(a.read("shoulder_pitch_position_deg")), 40.0, delta=2.0)
        # Measured power properties.
        rail = struct.unpack("<H", a.read("servo_rail_mv")["raw"])[0]
        self.assertGreater(rail, 11000)
        self.assertEqual(a.read("estop_state")["raw"], bytes([0]))
        self.assertEqual(a.read("estop_contact_open")["raw"], bytes([0]))
        # STOP at rest: initiated then confirmed (measured).
        a.link.send(h.stop(2), a.session)
        m, _ = a.until(lambda m: m["type"] == "stop_ack")
        self.assertIn(m["outcome"], (0, 1))
        if m["outcome"] == 0:
            m, _ = a.until(lambda m: m["type"] == "stop_ack")
        self.assertEqual((m["outcome"], m["evidence"]), (1, 2))

    def test_estop_flow(self):
        a = self.arm
        a.hello()
        a.enable()
        # A slow, long move so the E-stop arrives mid-motion.
        hdl = a.invoke("move_joints", move_args(-100, 50, 80, 20, 60, speed=5))
        m, _ = a.until(lambda m: m["type"] == "status" and m["handle"] == hdl)
        self.assertEqual(m["state"], ST["RUNNING"])
        time.sleep(0.4)
        t0 = time.monotonic()
        a.hw("estop 1")
        # The pin edge stops the operation (CANCELED) and acknowledges the stop with the cancel count.
        ack, seen = a.until(lambda m: m["type"] == "stop_ack")
        self.assertEqual(ack["canceled"], 1)
        self.assertLess(time.monotonic() - t0, 1.0)
        res = a.result(hdl) if not any(s.get("handle") == hdl and s["state"] == ST["CANCELED"] for s in seen if s["type"] in ("result", "status")) else None
        if res is not None:
            self.assertEqual(res["state"], ST["CANCELED"])
        # The rail was cut (SERVO_EN low) and the E-stop is observable as measured properties.
        time.sleep(0.2)
        lines = a.state_lines()
        self.assertEqual([l for l in lines if l.startswith("SERVO_EN")][-1], "SERVO_EN 0")
        self.assertTrue(any(l == "STATE 7" for l in lines))  # E-stop state
        self.assertEqual(a.read("estop_state")["raw"], bytes([1]))
        self.assertEqual(a.read("estop_state")["evidence"], 0)
        self.assertEqual(a.read("estop_contact_open")["raw"], bytes([1]))
        self.assertEqual(a.read("estop_latched")["raw"], bytes([1]))
        self.assertEqual(struct.unpack("<H", a.read("servo_rail_mv")["raw"])[0], 0)
        self.assertEqual(a.read("pose_unknown")["raw"], bytes([1]))  # "arm may have moved"
        # Servo-derived properties are unknown while unpowered: no substituted value.
        v = a.read("base_yaw_position_deg")
        self.assertEqual((v["quality"], v["raw"]), (3, b""))
        # While pressed: INHIBITED by the endpoint.
        a.invoke("move_joints", move_args(0, 30, 90, 45, 0))
        self.assertEqual(a.error()["code"], CODE["INHIBITED"])
        # Release: the rail must not come back; the arm refuses, naming the latch (reason 1).
        a.hw("estop 0")
        time.sleep(0.4)
        self.assertEqual([l for l in a.state_lines() if l.startswith("SERVO_EN")][-1], "SERVO_EN 0")
        a.invoke("move_joints", move_args(0, 30, 90, 45, 0))
        e = a.error()
        self.assertEqual((e["code"], e["detail"]), (CODE["INHIBITED"], 1))
        self.assertEqual(a.read("estop_state")["raw"], bytes([0]))
        self.assertEqual(a.read("estop_latched")["raw"], bytes([1]))
        # Explicit enable (new lease) recovers; then the arm moves again.
        a.enable()
        self.assertEqual(a.read("estop_latched")["raw"], bytes([0]))
        self.assertEqual(a.read("pose_unknown")["raw"], bytes([0]))
        hdl = a.invoke("move_joints", move_args(10, 40, 60, 5, 5))
        self.assertEqual(a.result(hdl)["state"], ST["COMPLETED"])

    def test_estop_pressed_blocks_enable(self):
        a = self.arm
        a.hello()
        a.hw("estop 1")
        time.sleep(0.3)
        a.invoke("enable")
        self.assertEqual(a.error()["code"], CODE["INHIBITED"])
        a.hw("estop 0")
        time.sleep(0.3)
        a.invoke("enable")  # released: the enable goes through
        self.assertEqual(a.result(a.handle)["state"], ST["COMPLETED"])

    def test_calibration_gate_and_procedure(self):
        a = self.arm
        a.close()
        self.arm = a = Arm(self.tmp, extra=("--uncalibrated", "1"))
        a.hello()
        self.assertEqual(a.read("calibrated")["raw"], bytes([0]))
        self.assertEqual(a.read("watchdog_reset")["raw"], bytes([0]))
        # Until calibrated the limits would be relative to an assumed zero: enable is refused (reason 15).
        a.invoke("enable")
        e = a.error()
        self.assertEqual((e["code"], e["detail"]), (CODE["PRECONDITION"], 15))
        # The calibrate action needs a lease, then defines the rest pose and stores the offsets.
        a.invoke("calibrate", lease=False)
        self.assertEqual(a.error()["code"], CODE["LEASE_REQUIRED"])
        hdl = a.invoke("calibrate")
        r = a.result(hdl, 10)
        self.assertEqual((r["state"], r["evidence"]), (ST["COMPLETED"], 2))
        self.assertEqual(a.read("calibrated")["raw"], bytes([1]))
        self.assertEqual([l for l in a.state_lines() if l.startswith("SERVO_EN")][-1], "SERVO_EN 0")
        a.enable()  # now allowed
        self.assertEqual(a.read("arm_state")["raw"], bytes([4]))

    def test_epoch_persists_across_reboot(self):
        a = self.arm
        self.assertEqual(a.hello()["epoch"], 1)
        a.close()
        self.arm = Arm(self.tmp)
        self.assertEqual(self.arm.hello()["epoch"], 2)

    def test_gripper_tool_flow(self):
        a = self.arm
        a.hw("tool 1000")
        a.hello()
        time.sleep(0.2)
        self.assertEqual(a.read("tool_id")["raw"], bytes([1]))
        self.assertEqual(a.read("tool_state")["raw"], bytes([1]))  # detected, unpowered
        a.enable()
        hdl = a.invoke("tool_mount")
        self.assertEqual(a.result(hdl)["state"], ST["COMPLETED"])
        self.assertEqual(a.read("tool_state")["raw"], bytes([3]))
        # grip(30 mm, 10 %): measured width.
        hdl = a.invoke("grip", struct.pack("<HB", 300, 10))
        r = a.result(hdl, 10)
        self.assertEqual((r["state"], r["evidence"]), (ST["COMPLETED"], 2))
        width, grasped = struct.unpack("<HB", r["fields"])
        self.assertAlmostEqual(width / 10.0, 30.0, delta=1.5)
        self.assertEqual(grasped, 0)
        self.assertAlmostEqual(f32(a.read("gripper_opening_mm")), 30.0, delta=1.5)
        # Force above the 15 % cap is refused by the layout; a knob action on a gripper is a precondition.
        a.invoke("grip", struct.pack("<HB", 300, 16))
        self.assertEqual(a.error()["code"], CODE["OUT_OF_RANGE"])
        a.invoke("turn", struct.pack("<hB", 900, 10))
        e = a.error()
        self.assertEqual((e["code"], e["detail"]), (CODE["PRECONDITION"], 9))  # wrong tool
        # Hot unplug: TOOL_EN is dropped at once and the tool is reported lost.
        a.hw("tool none")
        time.sleep(0.3)
        self.assertEqual([l for l in a.state_lines() if l.startswith("TOOL_EN")][-1], "TOOL_EN 0")
        self.assertEqual(a.read("tool_state")["raw"], bytes([4]))
        self.assertEqual(a.read("tool_id")["raw"], bytes([0]))


if __name__ == "__main__":
    unittest.main()
