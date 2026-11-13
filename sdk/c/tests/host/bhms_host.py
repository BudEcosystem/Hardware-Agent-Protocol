"""Host-side BHMS-Compact test harness.

Speaks the compact binding (spec/bhms/11-compact-binding.md) to firmware over a
pty, reusing protocol/serial/frame.py for framing. It is an independent
implementation of the payload layouts (struct-based, no shared code with the C
library), so tests built on it are real differential checks. The gateway side
(Task 9b: sdk/python transport/compact.py) is a separate deliverable.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import select
import struct
import subprocess
import termios
import time
import tty
import pty
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("hms_serial_frame", ROOT / "protocol" / "serial" / "frame.py")
frame = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frame)

CONTROL, STATUS, TELEMETRY = 1, 2, 3
CHANNEL = 1

# Message types
HELLO_REQ, INVOKE, CANCEL, READ, STOP, QUERY = 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
HELLO, STATUS_MSG, RESULT, VALUE, STOP_ACK, ERROR = 0x81, 0x82, 0x83, 0x84, 0x85, 0xFF

ERR = dict(MALFORMED=1, UNKNOWN_ACTION=2, UNKNOWN_PROPERTY=3, OUT_OF_RANGE=4, FENCED=5,
           LEASE_REQUIRED=6, BUSY=7, HANDLE_UNKNOWN=8, SESSION_MISMATCH=9, EXPIRED=10,
           UNSUPPORTED=11, PRECONDITION=12, INHIBITED=13, HANDLE_CONFLICT=14, INTERNAL=15)


def hello_req(nonce: int, new_session: bool = False) -> bytes:
    return struct.pack("<BBBI", HELLO_REQ, 1, 1 if new_session else 0, nonce)


def invoke(handle: int, action: int, args: bytes = b"", fence: int = 0, ttl_ms: int = 0) -> bytes:
    return struct.pack("<BHBIH", INVOKE, handle, action, fence, ttl_ms) + args


def cancel(handle: int) -> bytes:
    return struct.pack("<BH", CANCEL, handle)


def query(handle: int) -> bytes:
    return struct.pack("<BH", QUERY, handle)


def read(request: int, prop: int, fresh: bool = False) -> bytes:
    return struct.pack("<BHBB", READ, request, prop, 1 if fresh else 0)


def stop(reason: int = 0) -> bytes:
    return struct.pack("<BB", STOP, reason)


def hello(flags: int, digest8: bytes, epoch: int, nonce: int, last_handle: int, ring: int,
          max_active: int, max_args: int) -> bytes:
    return struct.pack("<BBB8sIIHBBB", HELLO, 1, flags, digest8, epoch, nonce, last_handle, ring,
                       max_active, max_args)


def result(handle: int, state: int, evidence: int, fault: int, fields: bytes = b"") -> bytes:
    return struct.pack("<BHBBB", RESULT, handle, state, evidence, fault) + fields


def status(handle: int, state: int, cancel_state: int, progress: int) -> bytes:
    return struct.pack("<BHBBB", STATUS_MSG, handle, state, cancel_state, progress)


def value(request: int, prop: int, quality: int, evidence: int, seq: int, age_ms: int,
          raw: bytes = b"") -> bytes:
    return struct.pack("<BHBBBII", VALUE, request, prop, quality, evidence, seq, age_ms) + raw


def stop_ack(outcome: int, evidence: int, canceled: int) -> bytes:
    return struct.pack("<BBBB", STOP_ACK, outcome, evidence, canceled)


def error(req_type: int, ident: int, code: int, detail: int = 0) -> bytes:
    return struct.pack("<BBHBB", ERROR, req_type, ident, code, detail)


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
