"""Host-side BHMS-Compact test harness.

Speaks the compact binding (spec/bhms/11-compact-binding.md) to firmware over a
pty, reusing protocol/serial/frame.py for framing and the SDK's compact codec
(sdk/python/src/bhms/transport/compact.py, Task 9b) for the payloads, so there is
one Python codec. The codec shares no code with the C library, so tests built on
it remain a real differential check of the C encoders and decoders.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import select
import subprocess
import sys
import termios
import time
import tty
import pty
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("hms_serial_frame", ROOT / "protocol" / "serial" / "frame.py")
frame = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frame)

CONTROL, STATUS, TELEMETRY = 1, 2, 3  # frame kinds
CHANNEL = 1

# The payload codec is the SDK's one compact codec (sdk/python/src/bhms/transport/compact.py): the gateway bridge, the
# conformance checks and this harness all build and parse messages with it. It is stdlib-only at its top level, so it is
# loaded by path (no pydantic, no `bhms` package import: the simavr container has neither).
_codec_spec = importlib.util.spec_from_file_location(
    "bhms_compact_codec", ROOT / "sdk" / "python" / "src" / "bhms" / "transport" / "compact.py")
codec = importlib.util.module_from_spec(_codec_spec)
sys.modules["bhms_compact_codec"] = codec  # dataclasses resolve their module by name
_codec_spec.loader.exec_module(codec)

HELLO_REQ, INVOKE, CANCEL, READ, STOP, QUERY = (codec.HELLO_REQ, codec.INVOKE, codec.CANCEL, codec.READ, codec.STOP,
                                                codec.QUERY)
HELLO, STATUS_MSG, RESULT, VALUE, STOP_ACK, ERROR = (codec.HELLO, codec.STATUS, codec.RESULT, codec.VALUE, codec.STOP_ACK,
                                                     codec.ERROR)
ERR = codec.ERR
hello_req, invoke, cancel, query, read, stop = (codec.hello_req, codec.invoke, codec.cancel, codec.query, codec.read,
                                                codec.stop)
hello, result, status, value, stop_ack, error = (codec.hello, codec.result, codec.status, codec.value, codec.stop_ack,
                                                 codec.error)


@dataclass
class Target:
    """A running firmware (native or simavr) reachable over a pty."""

    proc: subprocess.Popen
    master: int
    stderr_path: pathlib.Path

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        os.close(self.master)

    def stderr_lines(self) -> list[str]:
        return self.stderr_path.read_text(errors="replace").splitlines() if self.stderr_path.exists() else []


def spawn(cmd: list[str], stderr_path: pathlib.Path) -> Target:
    """Start `cmd` with its stdin/stdout on a raw pty (the 'serial port')."""
    master, slave = pty.openpty()
    tty.setraw(slave, termios.TCSANOW)
    err = open(stderr_path, "wb")
    proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=err, close_fds=True)
    os.close(slave)
    err.close()
    return Target(proc, master, stderr_path)


class Link:
    """Gateway-side endpoint of the serial link."""

    def __init__(self, target: Target):
        self.t = target
        self.seq = 0
        self.buf = bytearray()

    def send(self, payload: bytes, session: int, kind: int = CONTROL, channel: int = CHANNEL,
             corrupt: int | None = None) -> bytes:
        wire = frame.encode(frame.Frame(kind, channel, session, self.seq, payload))
        self.seq += 1
        if corrupt is not None:
            b = bytearray(wire)
            b[corrupt] ^= 0x04
            wire = bytes(b)
        os.write(self.t.master, wire)
        return wire

    def recv_wire(self, timeout: float = 5.0) -> bytes | None:
        """Raw bytes of the next complete frame (flag to flag), or None on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            start = self.buf.find(0x7E)
            if start >= 0:
                end = self.buf.find(0x7E, start + 1)
                while end == start + 1:  # skip empty frames (adjacent flags)
                    start, end = end, self.buf.find(0x7E, end + 1)
                if end > start:
                    wire = bytes(self.buf[start:end + 1])
                    del self.buf[:end]  # keep the closing flag: it may open the next frame
                    return wire
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            r, _, _ = select.select([self.t.master], [], [], left)
            if r:
                try:
                    self.buf += os.read(self.t.master, 4096)
                except OSError:
                    return None

    def recv(self, timeout: float = 5.0):
        wire = self.recv_wire(timeout)
        if wire is None:
            return None, None
        dec = frame.Decoder()
        ev = None
        for b in wire:
            ev = dec.feed(b) or ev
        assert ev is not None and ev[0] == "frame", ev
        return wire, ev[1]

    def expect_silence(self, seconds: float = 0.4) -> None:
        assert self.recv_wire(seconds) is None, "unexpected frame from the device"

    def exchange(self, payload: bytes, session: int, timeout: float = 5.0):
        sent = self.send(payload, session)
        wire, fr = self.recv(timeout)
        return sent, wire, fr


def expected_wire(kind: int, session: int, seq: int, payload: bytes) -> bytes:
    return frame.encode(frame.Frame(kind, CHANNEL, session, seq, payload))
