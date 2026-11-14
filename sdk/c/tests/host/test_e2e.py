"""End-to-end BHMS-Compact test: the host harness drives the LedAnalog device over
a pty and asserts byte-exact frames.

Targets (selected with BHMS_TARGET):
  native  (default)  tests/host/sim_device built by CMake (ASan/UBSan) — BHMS_SIM_DEVICE
  simavr             the Arduino example firmware (ATmega328P) in simavr —
                     BHMS_SIMAVR_CMD is the runner command line; the runner takes
                     `--eeprom FILE` and prints "LED 0|1" on stderr like sim_device.
BHMS_ANALOG is the value the device must report for the analog property (default 341).
"""
import importlib.util
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bhms_host as h  # noqa: E402

SDK_C = HERE.parents[1]
DIGEST8 = bytes([0x23, 0x8A, 0xE3, 0x9C, 0xEB, 0xF1, 0x18, 0x8C])
ANALOG = int(os.environ.get("BHMS_ANALOG", "341"))
TARGET = os.environ.get("BHMS_TARGET", "native")
FLAGS = 0x02  # PERSISTENT_EPOCH only: no fencing, no stop procedure
TIMEOUT = float(os.environ.get("BHMS_TIMEOUT", "5"))


def command(tmp: pathlib.Path) -> list[str]:
    if TARGET == "simavr":
        return shlex.split(os.environ["BHMS_SIMAVR_CMD"]) + ["--eeprom", str(tmp / "eeprom.bin")]
    exe = os.environ.get("BHMS_SIM_DEVICE", str(SDK_C / "build" / "sim_device"))
    return [exe, "--epoch", str(tmp / "epoch.bin"), "--analog", str(ANALOG)]


class LedAnalogE2E(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.target = None
        self.boot()

    def tearDown(self):
        if self.target:
            self.target.close()
        self._tmp.cleanup()

    def boot(self):
        if self.target:
            self.target.close()
        self.n_boots = getattr(self, "n_boots", 0) + 1
        self.target = h.spawn(command(self.tmp), self.tmp / f"stderr{self.n_boots}.txt")
        self.link = h.Link(self.target)

    def leds(self):
        return [ln for ln in self.target.stderr_lines() if ln.startswith("LED ")]

    def expect(self, wire, kind, session, seq, payload):
        want = h.expected_wire(kind, session, seq, payload)
        self.assertEqual(wire.hex() if wire else None, want.hex())

    def do_hello(self, nonce, new_session=False):
        sent, wire, fr = self.link.exchange(h.hello_req(nonce, new_session), 0, TIMEOUT)
        self.assertIsNotNone(wire, "no HELLO within timeout")
        return wire, fr

    def test_acceptance_sequence(self):
        link = self.link
        # HELLO (the device boots into epoch 1: erased EEPROM cell, then incremented).
        wire, fr = self.do_hello(0xC0FFEE)
        self.expect(wire, h.STATUS, 1, 0,
                    h.hello(FLAGS, DIGEST8, 1, 0xC0FFEE, 0, 4, 2, 1))
        self.assertEqual(len(wire), 24 + 24)

        # INVOKE(led on): RESULT completed, reported, writes=1; the LED turned on.
        sent = link.send(h.invoke(1, 0, bytes([1])), 1)
        self.assertEqual(len(sent), 24 + 10 + 1)  # 10 fixed bytes + 1 argument byte, no padding
        wire, _ = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 1, 1, h.result(1, 3, 1, 0, bytes([1])))
        self.assertEqual(self.leds(), ["LED 1"])

        # READ(analog): VALUE valid/measured with the sampled level.
        link.send(h.read(7, 0), 1)
        wire, _ = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 1, 2,
                    h.value(7, 0, 0, 0, 1, 0xFFFFFFFF, ANALOG.to_bytes(2, "little")))

        # Retransmitted INVOKE (same handle, identical payload) is answered from the
        # replay ring: byte-identical RESULT payload, LED NOT written again.
        link.send(h.invoke(1, 0, bytes([1])), 1)
        wire, _ = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 1, 3, h.result(1, 3, 1, 0, bytes([1])))
        self.assertEqual(self.leds(), ["LED 1"])

        # A new handle does execute (writes counter proves the earlier one did not).
        link.send(h.invoke(2, 0, bytes([0])), 1)
        wire, _ = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 1, 4, h.result(2, 3, 1, 0, bytes([2])))
        self.assertEqual(self.leds(), ["LED 1", "LED 0"])

        # Same handle with a different payload: HANDLE_CONFLICT, no effect.
        link.send(h.invoke(1, 0, bytes([0])), 1)
        wire, _ = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 1, 5, h.error(h.INVOKE, 1, h.ERR["HANDLE_CONFLICT"]))

        # STOP with a stale session is accepted; this board has no stop procedure.
        link.send(h.stop(1, 9), 999)
        wire, _ = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 1, 6, h.stop_ack(2, 0, 0, 9))  # the token is echoed
        link.expect_silence()
        self.assertEqual(self.leds(), ["LED 1", "LED 0"])

    def test_the_effect_report_holds_only_effects_whatever_the_frames_carry(self):
        """stderr is the effect report ("LED 0|1" lines) that tests count pin changes in. A frame byte 0x0A must not leak
        anything into it: simavr's UART echo did (a line of frame bytes, then a colour reset glued to the next "LED" line),
        so a board whose HELLO held 0x0A looked as if its LED had never changed."""
        link = self.link
        wire, _ = self.do_hello(0x0A0A0A0A)
        self.assertIn(b"\x0a\x0a\x0a\x0a", wire)
        link.send(h.invoke(1, 0, bytes([1])), 1)
        wire, fr = link.recv(TIMEOUT)
        self.assertEqual(fr.payload, h.result(1, 3, 1, 0, bytes([1])))
        self.assertEqual(self.target.stderr_lines(), ["LED 1"])

    def test_corruption_and_recovery(self):
        link = self.link
        self.do_hello(1)
        for pos in (3, 10, 22, 25, 30):
            link.send(h.invoke(1, 0, bytes([1])), 1, corrupt=pos)
        link.expect_silence()
        self.assertEqual(self.leds(), [])
        link.send(h.invoke(1, 0, bytes([1])), 1)
        wire, fr = link.recv(TIMEOUT)
        self.assertEqual(fr.payload, h.result(1, 3, 1, 0, bytes([1])))
        # Wrong channel and wrong kind are discarded without a reply.
        link.send(h.invoke(2, 0, bytes([1])), 1, channel=2)
        link.send(h.invoke(2, 0, bytes([1])), 1, kind=h.STATUS)
        link.expect_silence()
        self.assertEqual(self.leds(), ["LED 1"])

    def test_errors(self):
        link = self.link
        self.do_hello(1)
        # detail: UNKNOWN_ACTION/UNKNOWN_PROPERTY echo the bad index, MALFORMED the argument index.
        for payload, code, req_type, ident, detail in [
            (h.invoke(1, 5, bytes([1])), "UNKNOWN_ACTION", h.INVOKE, 1, 5),
            (h.invoke(1, 0, bytes([1, 1])), "MALFORMED", h.INVOKE, 1, 0),
            (h.invoke(1, 0, bytes([2])), "MALFORMED", h.INVOKE, 1, 0),
            (h.read(3, 9), "UNKNOWN_PROPERTY", h.READ, 3, 9),
            (h.query(40), "HANDLE_UNKNOWN", h.QUERY, 40, 0),
            (h.cancel(40), "HANDLE_UNKNOWN", h.CANCEL, 40, 0),
        ]:
            link.send(payload, 1)
            wire, fr = link.recv(TIMEOUT)
            self.assertEqual(fr.payload, h.error(req_type, ident, h.ERR[code], detail), code)
        link.send(h.invoke(1, 0, bytes([1])), 77)  # wrong session
        wire, fr = link.recv(TIMEOUT)
        self.assertEqual((fr.session, fr.payload), (1, h.error(h.INVOKE, 1, h.ERR["SESSION_MISMATCH"])))
        self.assertEqual(self.leds(), [])

    def test_reboot_epoch_and_query(self):
        link = self.link
        self.do_hello(1)
        link.send(h.invoke(1, 0, bytes([1])), 1)
        link.recv(TIMEOUT)
        # Power-cycle: the persistent boot counter advances, the ring is gone.
        self.boot()
        link = self.link
        wire, fr = self.do_hello(2)
        self.expect(wire, h.STATUS, 2, 0, h.hello(FLAGS, DIGEST8, 2, 2, 0, 4, 2, 1))
        # The gateway restarts and QUERYs with the epoch it remembers: the refusal is
        # stamped with the current epoch, so old-incarnation work is recognisable.
        link.send(h.query(1), 1)
        wire, fr = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 2, 1, h.error(h.QUERY, 1, h.ERR["SESSION_MISMATCH"]))
        link.send(h.query(1), 2)
        wire, fr = link.recv(TIMEOUT)
        self.expect(wire, h.STATUS, 2, 2, h.error(h.QUERY, 1, h.ERR["HANDLE_UNKNOWN"]))
        # NEW_SESSION with nothing active is honoured: epoch 3, counters restart.
        wire, fr = self.do_hello(3, new_session=True)
        self.expect(wire, h.STATUS, 3, 0, h.hello(FLAGS, DIGEST8, 3, 3, 0, 4, 2, 1))

    @unittest.skipUnless(importlib.util.find_spec("pydantic"), "needs the sdk/python models")
    def test_sidecar_digest_matches_firmware(self):
        out = subprocess.run(
            [sys.executable, "-B", str(SDK_C / "tools" / "bhms_digest.py"),
             str(SDK_C / "arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json"), "--check"],
            capture_output=True, text=True, check=True).stdout
        self.assertIn(DIGEST8.hex(), out.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
