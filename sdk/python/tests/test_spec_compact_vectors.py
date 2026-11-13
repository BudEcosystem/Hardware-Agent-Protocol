"""The worked BHMS-Compact frames in spec/bhms/11-compact-binding.md decode with the reused HM frame codec."""

from __future__ import annotations

import importlib.util
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHAPTER = (ROOT / "spec" / "bhms" / "11-compact-binding.md").read_text()


def _frame_module():
    spec = importlib.util.spec_from_file_location("hm_frame", ROOT / "protocol" / "serial" / "frame.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _worked_frames() -> list[bytes]:
    section = CHAPTER.split("## 11.10 Worked example", 1)[1]
    blocks = re.findall(r"```\n(.*?)```", section, re.S)
    return [bytes.fromhex(" ".join(block.split())) for block in blocks]


def _decode(frame, wire: bytes):
    decoder = frame.Decoder()
    events = [event for event in (decoder.feed(byte) for byte in wire) if event is not None]
    assert len(events) == 1 and events[0][0] == "frame", events
    return events[0][1]


def test_worked_invoke_and_result_frames():
    frame = _frame_module()
    invoke_wire, result_wire = _worked_frames()
    invoke = _decode(frame, invoke_wire)
    assert (invoke.kind, invoke.channel, invoke.session, invoke.sequence) == (1, 1, 41, 7)
    assert struct.unpack("<BHBIHHH", invoke.payload) == (0x02, 17, 0, 412, 0, 500, 100)
    assert len(invoke_wire) == 24 + len(invoke.payload) <= 64  # BHMS-CMP-003, no stuffing here
    assert frame.encode(invoke) == invoke_wire
    result = _decode(frame, result_wire)
    assert (result.kind, result.channel, result.session, result.sequence) == (2, 1, 41, 9)
    assert struct.unpack("<BHBBBH", result.payload) == (0x83, 17, 3, 2, 0, 501)
    assert frame.encode(result) == result_wire
