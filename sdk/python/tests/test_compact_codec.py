"""BHMS-Compact codecs, layouts and the framing link (spec/bhms/11-compact-binding.md)."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import socket
from pathlib import Path

import pytest

from bhms.transport import compact as c

ROOT = Path(__file__).resolve().parents[3]
LED = json.loads((ROOT / "sdk/c/arduino/BHMS/examples/LedAnalog/led_analog.sidecar.json").read_text())
ARM = json.loads((ROOT / "hardware/actuator/firmware/arm.sidecar.json").read_text())

SPEC_INVOKE_WIRE = bytes.fromhex("7e484d01010001000000000000002900000007000e021100009c0100000000f4016400e5f97e")
SPEC_RESULT_WIRE = bytes.fromhex("7e484d0102000100000000000000290000000900088311000302" "00f50133227e")


class _NullStream:
    def __init__(self):
        self.written = bytearray()

    async def read(self):
        await asyncio.sleep(3600)
        return b""

    def write(self, data, *, urgent=False):
        self.written += data

    async def close(self):
        pass


def test_spec_worked_example_bytes():  # 11.10
    payload = c.invoke(17, 0, bytes.fromhex("f4016400"), fence=412)
    assert len(payload) == 14 and payload.hex() == "021100009c0100000000f4016400"
    link = c.CompactLink(_NullStream())
    assert link.send(payload, session=41, sequence=7) == SPEC_INVOKE_WIRE
    assert len(SPEC_INVOKE_WIRE) == 38
    result = c.result(17, 3, 2, 0, bytes.fromhex("f501"))
    assert link.send(result, session=41, sequence=9, kind=c.STATUS_KIND) == SPEC_RESULT_WIRE
    assert c.decode(result) == c.Result(17, 3, 2, 0, b"\xf5\x01")


MESSAGES = [
    c.HelloReq(0xC0FFEE, c.HELLO_NEW_SESSION), c.Hello(0x07, bytes(range(8)), 41, 5, 17, 4, 2, 16),
    c.Invoke(65535, 255, b"\x01\x02", 2**32 - 1, 65535), c.Cancel(9), c.Read(7, 3, c.READ_FRESH), c.Stop(3), c.Query(1),
    c.Status(2, 2, 2, 50), c.Result(3, 3, 1, 0, b"\x01\x00"), c.Result(3, 4, 0, 21), c.Value(0, 1, 2, 1, 9, 0xFFFFFFFF),
    c.Value(7, 0, 0, 0, 9, 12, b"\x55\x01"), c.StopAck(0, 2, 3), c.Error(2, 17, 8, 1)]


@pytest.mark.parametrize("message", MESSAGES, ids=lambda m: type(m).__name__)
def test_every_message_round_trips_and_is_exact(message):  # CMP-002
    payload = message.encode()
    assert c.decode(payload) == message
    fixed_size = c._FIXED[payload[0]][1]
    variable = c._FIXED[payload[0]][2]
    for broken in (payload[:-1], payload + b"\x00"):
        if variable and len(broken) >= fixed_size:
            continue  # a longer variable part is a different valid message
        with pytest.raises(c.CompactError):
            c.decode(broken)


def test_unknown_and_empty_payloads_are_refused():
    for bad in (b"", b"\x00", b"\x07abc", b"\x80"):
        with pytest.raises(c.CompactError):
            c.decode(bad)


def test_frame_sizes_follow_cmp_003():
    link = c.CompactLink(_NullStream())
    assert len(link.send(c.invoke(1, 0, bytes(8)), session=1)) <= 64  # a typical INVOKE
    assert len(link.send(c.invoke(1, 0, bytes(8)), session=1)) == 24 + 18
    assert len(link.send(c.invoke(1, 0, bytes(182)), session=1)) <= 2 * (20 + 192 + 2) + 2  # largest INVOKE: one frame


# ------------------------------------------------------------------------------------------------ values


def test_scaled_fields_carry_integers_and_never_round():  # CMP-010
    assert c.encode_value("u16", 0.1, 50.0) == bytes.fromhex("f401")
    assert c.encode_value("u16", 0.1, 50.1) == (501).to_bytes(2, "little")
    with pytest.raises(c.CompactValueError) as bad:
        c.encode_value("u16", 0.1, 50.05)  # the spec's own example: half a step
    assert bad.value.code == "INVALID_ARGUMENT"
    with pytest.raises(c.CompactValueError) as high:
        c.encode_value("u16", 0.1, 7000.0)
    assert high.value.code == "OUT_OF_RANGE"
    with pytest.raises(c.CompactValueError) as low:
        c.encode_value("u8", None, -1)
    assert low.value.code == "OUT_OF_RANGE"
    assert c.encode_value("i16", 0.01, -150.0) == (-15000).to_bytes(2, "little", signed=True)


def test_unscaled_integers_refuse_fractions_but_accept_integral_floats():
    assert c.encode_value("u8", None, 5.0) == b"\x05"
    with pytest.raises(c.CompactValueError):
        c.encode_value("u8", None, 5.5)


def test_f32_must_survive_the_conversion():
    assert c.decode_value("f32", None, c.encode_value("f32", None, 1.5)) == 1.5
    assert c.encode_value("f32", None, 0.1)  # within 1e-6 relative
    with pytest.raises(c.CompactValueError):
        c.encode_value("f32", None, 1e40)
    for bad in (float("nan"), float("inf"), "1", None, True):
        with pytest.raises(c.CompactValueError):
            c.encode_value("f32", None, bad)


def test_bool_is_strict():
    assert c.encode_value("bool", None, True) == b"\x01"
    for bad in (1, 0, "true", None):
        with pytest.raises(c.CompactValueError):
            c.encode_value("bool", None, bad)
    with pytest.raises(c.CompactError):
        c.decode_value("bool", None, b"\x02")


def test_decoding_applies_the_scale_in_exact_decimal():
    assert c.decode_value("u16", 0.1, (501).to_bytes(2, "little")) == 50.1
    assert c.decode_value("u16", 0.1, (3).to_bytes(2, "little")) == 0.3  # not 0.30000000000000004
    assert c.decode_value("i16", 0.01, (-15000).to_bytes(2, "little", signed=True)) == -150.0
    assert c.decode_value("u8", None, b"\x07") == 7 and isinstance(c.decode_value("u8", None, b"\x07"), int)
    with pytest.raises(c.CompactError):
        c.decode_value("u16", None, b"\x01")


def test_fields_in_layout_order_and_exact_result_length():
    fields = (c.Field("a", "u8"), c.Field("b", "i16", 0.5), c.Field("c", "bool"))
    data = c.encode_fields(fields, {"c": True, "b": -1.5, "a": 9})
    assert data == bytes([9]) + (-3).to_bytes(2, "little", signed=True) + b"\x01"
    assert c.decode_fields(fields, data) == {"a": 9, "b": -1.5, "c": True}
    with pytest.raises(c.CompactError):
        c.decode_fields(fields, data + b"\x00")
    with pytest.raises(c.CompactValueError):
        c.encode_fields(fields, {"a": 1, "b": 0.0})


# ------------------------------------------------------------------------------------------------ layouts


@pytest.mark.parametrize("sidecar", [LED, ARM], ids=["led", "arm"])
def test_shipped_sidecars_obey_the_layout_rules(sidecar):  # DEV-070/071
    assert c.layout_problems(sidecar) == []
    layouts = c.layouts_from_description(sidecar)
    assert set(layouts.actions) == set(sidecar["actions"]) and set(layouts.properties) == set(sidecar["properties"])


def test_layout_indices_come_from_the_layouts_not_from_name_order():  # CMP-011
    layouts = c.layouts_from_description(ARM)
    by_index = {layout.index: name for name, layout in layouts.actions.items()}
    assert by_index[0] == "move_joints"
    shuffled = copy.deepcopy(ARM)
    names = list(shuffled["actions"])
    shuffled["actions"] = {n: shuffled["actions"][n] for n in reversed(names)}
    assert {n: layout.index for n, layout in c.layouts_from_description(shuffled).actions.items()} == \
        {n: layout.index for n, layout in layouts.actions.items()}


def test_layout_problems_are_found():
    broken = copy.deepcopy(LED)
    broken["actions"]["led_set"]["compact"]["args"] = []
    assert ("BHMS-DEV-070" in [r for r, _ in c.layout_problems(broken)])
    unscaled = copy.deepcopy(LED)
    unscaled["actions"]["led_set"]["output"]["properties"]["writes"] = {"type": "number", "minimum": 0, "maximum": 255}
    assert any("unscaled integer" in m for _, m in c.layout_problems(unscaled))
    scaled = copy.deepcopy(ARM)
    scaled["actions"]["move_joints"]["input"]["properties"]["base_yaw"]["multipleOf"] = 0.5
    assert any("mirrored" in m for _, m in c.layout_problems(scaled))


def test_layouts_refuse_what_cannot_be_translated():
    missing = copy.deepcopy(LED)
    del missing["actions"]["led_set"]["compact"]
    with pytest.raises(c.CompactError, match="no compact layout"):
        c.layouts_from_description(missing)
    clash = copy.deepcopy(ARM)
    clash["actions"]["home"]["compact"]["index"] = 0
    with pytest.raises(c.CompactError, match="unique"):
        c.layouts_from_description(clash)
    bad_scale = copy.deepcopy(LED)
    bad_scale["properties"]["analog0"]["compact"] = {"index": 0, "type": "f32", "scale": 0.1}
    with pytest.raises(c.CompactError, match="scale"):
        c.layouts_from_description(bad_scale)


def test_digest8_is_the_first_eight_bytes_of_the_description_digest():
    assert c.digest8_of(LED).hex() == "238ae39cebf1188c"  # the LedAnalog firmware's digest8 (sdk/c 9a report)
    assert c.description_digest(LED).startswith("sha256:238ae39cebf1188c")


# ------------------------------------------------------------------------------------------------ the link


async def _pair():
    a, b = socket.socketpair()
    return c.CompactLink(c.FdStream(os.dup(a.fileno()))), os.dup(b.fileno()), (a, b)


async def test_link_delivers_valid_frames_and_drops_everything_else():
    link, raw, socks = await _pair()
    link.start()
    try:
        good = link.frame.encode(link.frame.Frame(c.STATUS_KIND, c.CHANNEL, 5, 0, c.error(2, 1, 8)))
        corrupt = bytearray(good)
        corrupt[12] ^= 0x04
        other_channel = link.frame.encode(link.frame.Frame(c.STATUS_KIND, 2, 5, 1, c.error(2, 1, 8)))
        control_kind = link.frame.encode(link.frame.Frame(c.CONTROL, c.CHANNEL, 5, 2, c.error(2, 1, 8)))
        bad_length = link.frame.encode(link.frame.Frame(c.STATUS_KIND, c.CHANNEL, 5, 3, c.error(2, 1, 8) + b"\x00"))
        os.write(raw, bytes(corrupt) + other_channel + control_kind + bad_length + b"\x00garbage\x7e" + good)
        got = await link.receive(2.0)
        assert got.message == c.Error(2, 1, 8) and got.session == 5 and got.wire == good
        assert await link.receive(0.1) is None
        assert link.stats["frame-error"] >= 1 and link.stats["other-channel"] == 1 and link.stats["wrong-kind"] == 1
        assert link.stats["malformed"] == 1
    finally:
        os.close(raw)
        await link.close()
        for s in socks:
            s.close()


async def test_link_resynchronises_after_a_cut_frame():
    link, raw, socks = await _pair()
    link.start()
    try:
        good = link.frame.encode(link.frame.Frame(c.TELEMETRY, c.CHANNEL, 5, 0, c.status(3, 2, 0, 50)))
        os.write(raw, good[: len(good) // 2] + good + good)  # a frame cut in two by the next flag
        first, second = await link.receive(2.0), await link.receive(2.0)
        assert first.message == second.message == c.Status(3, 2, 0, 50)
        assert first.kind == c.TELEMETRY
    finally:
        os.close(raw)
        await link.close()
        for s in socks:
            s.close()


async def test_link_send_writes_the_frame_at_once_and_counts_sequences():
    stream = _NullStream()
    link = c.CompactLink(stream)
    first = link.send(c.hello_req(1), session=0)
    second = link.send(c.stop(1), session=77)
    assert bytes(stream.written) == first + second and link.tx_seq == 2
    link.reset_sequence()
    assert link.tx_seq == 0


async def test_end_of_stream_raises_link_closed_every_time():
    link, raw, socks = await _pair()
    link.start()
    os.close(raw)
    socks[1].close()
    for _ in range(2):
        with pytest.raises(c.LinkClosed):
            await link.receive(2.0)
    await link.close()
    socks[0].close()


async def test_open_stream_refuses_unknown_forms():
    with pytest.raises(OSError):
        await c.open_stream("ttyACM0")


async def test_input_without_a_flag_byte_cannot_grow_the_link_buffer():  # unbounded-memory guard
    a, b = socket.socketpair()
    link = c.CompactLink(c.FdStream(a.detach()))
    link.start()
    peer = c.FdStream(b.detach())
    try:
        for _ in range(20):
            peer.write(b"\x55" * 1000)  # no 0x7E anywhere
        for _ in range(100):
            if link.stats["overlong"] >= 1:
                break
            await asyncio.sleep(0.02)
        assert link.stats["overlong"] >= 1 and len(link._wire) <= link.frame.MAX_WIRE
    finally:
        await link.close()
        await peer.close()


async def test_a_serial_line_that_does_not_drain_cannot_grow_the_output_queue():
    read_end, write_end = os.pipe()  # nobody reads: the pipe fills and writes would queue forever
    stream = c.FdStream(write_end)
    try:
        for _ in range(64):
            stream.write(b"\x00" * 4096)
        assert len(stream._out) <= c.MAX_PENDING_OUTPUT and stream.dropped > 0
    finally:
        await stream.close()
        os.close(read_end)


def test_the_packaged_frame_module_is_byte_identical_to_the_firmware_protocol_source():
    """``bhms/transport/hm_frame.py`` is a copy of ``protocol/serial/frame.py`` (a symlink does not survive packaging); the one
    framing implementation stays one: refresh with ``cp protocol/serial/frame.py sdk/python/src/bhms/transport/hm_frame.py``."""
    root = Path(__file__).resolve().parents[3]
    source = root / "protocol" / "serial" / "frame.py"
    copy = root / "sdk" / "python" / "src" / "bhms" / "transport" / "hm_frame.py"
    if not source.is_file():
        pytest.skip("outside the repository tree: protocol/serial/frame.py is not there to compare with")
    assert not copy.is_symlink()
    assert copy.read_bytes() == source.read_bytes()


async def test_a_stop_still_gets_queued_when_a_stalled_line_refuses_ordinary_writes(caplog):  # CMP-050
    read_end, write_end = os.pipe()
    stream = c.FdStream(write_end)
    link = c.CompactLink(stream)
    try:
        for _ in range(64):
            stream.write(b"\x00" * 4096)  # fills the pipe and then the queue: ordinary writes are refused
        assert stream.dropped > 0
        before = len(stream._out)
        link.send(c.Invoke(1, 0, b"", 0, 0))
        assert len(stream._out) == before  # an INVOKE is refused, and the refusal is logged
        assert stream.dropped > 0 and "not draining" in caplog.text
        link.send(c.Stop(3), session=1)
        assert len(stream._out) > before  # the STOP got through on the reserved headroom
    finally:
        await stream.close()
        os.close(read_end)


async def test_every_dropped_stop_is_logged_not_only_the_first_or_every_hundredth(caplog):
    read_end, write_end = os.pipe()
    stream = c.FdStream(write_end)
    try:
        for _ in range(64):
            stream.write(b"\x00" * 4096)
        for _ in range(c.URGENT_HEADROOM):  # exhaust the reserved headroom, then every further STOP is refused
            stream.write(b"\x00", urgent=True)
        caplog.clear()
        stream.dropped = 5  # not 1 and not a multiple of 100: the counter rule alone would stay silent
        stream.write(b"\x00", urgent=True)
        assert "INCLUDING A STOP" in caplog.text
    finally:
        await stream.close()
        os.close(read_end)


def test_the_stop_and_stop_ack_vectors_of_spec_11_with_their_tokens():
    from bhms.transport import hm_frame

    stop = bytes.fromhex("7e484d01010001000000000000002900000009000305032afb847e")
    ack = bytes.fromhex("7e484d0102000100000000000000290000000a0005850102022a25ff7e")
    assert hm_frame.encode(hm_frame.Frame(1, 1, 41, 9, c.Stop(3, 0x2A).encode())) == stop
    assert hm_frame.encode(hm_frame.Frame(2, 1, 41, 10, c.StopAck(c.STOPACK_CONFIRMED, c.EVIDENCE_MEASURED, 2, 0x2A).encode())) == ack
    assert c.decode(c.Stop(3, 0x2A).encode()) == c.Stop(3, 0x2A) and c.decode(c.StopAck(1, 2, 2, 0x2A).encode()).token == 0x2A
    assert c.COMPACT_VERSION == 2
