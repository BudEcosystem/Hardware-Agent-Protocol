"""Cross-language wire framing tests, without a serial port or device runtime."""
import importlib.util
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hms_frame', ROOT / 'protocol/serial/frame.py')
codec = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = codec
spec.loader.exec_module(codec)


def framed_raw(raw):
    encoded = bytearray([codec.FLAG])
    for byte in raw:
        encoded.extend((codec.ESCAPE, byte ^ 0x20) if byte in (codec.FLAG, codec.ESCAPE) else (byte,))
    return bytes(encoded) + bytes([codec.FLAG])


def seal(raw):
    return raw + struct.pack('<H', codec.fcs16(raw) ^ 0xFFFF)


def python_events(wire):
    parser = codec.Decoder()
    frames, errors = [], 0
    for byte in wire:
        event = parser.feed(byte)
        if event:
            if event[0] == 'frame': frames.append(event[1])
            else: errors += 1
        if len(parser.buffer) > codec.MAX_RAW:
            raise AssertionError('Bounded storage exceeded')
    return frames, errors


class SerialFrame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('gcc')
        if compiler is None:
            raise RuntimeError('gcc is required for cross-language framing verification')
        cls.temp = tempfile.TemporaryDirectory(prefix='hms-frame-')
        cls.binary = Path(cls.temp.name) / 'frame-test'
        subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Wconversion', '-Werror',
                        str(ROOT / 'protocol/serial/frame.c'), str(ROOT / 'tests/serial_frame_driver.c'),
                        '-o', str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def c_events(self, wire):
        result = subprocess.run([str(self.binary)], input=wire, capture_output=True, check=True)
        frames, errors = [], 0
        for line in result.stdout.decode().splitlines():
            if line == 'E': errors += 1
            else: frames.append(codec.decode_raw(bytes.fromhex(line[2:])))
        return frames, errors

    def assert_decoders(self, wire, expected, errors=None):
        py = python_events(wire)
        self.assertEqual(self.c_events(wire), py)
        self.assertEqual(py[0], expected)
        if errors is not None: self.assertEqual(py[1], errors)

    def test_fcs_check_value_and_residue(self):
        self.assertEqual(codec.fcs16(b'123456789') ^ 0xFFFF, 0x906E)
        self.assertEqual(codec.fcs16(b'123456789\x6e\x90'), 0xF0B8)

    def test_retained_vectors_match_wire_bytes_in_both_languages(self):
        for vector in json.loads((ROOT / 'tests/fixtures/serial-frames.json').read_text()):
            frame = codec.Frame(vector['kind'], vector['channel'], vector['session'], vector['sequence'],
                                bytes.fromhex(vector['payload_hex']))
            wire = bytes.fromhex(vector['wire_hex'])
            self.assertEqual(codec.encode(frame), wire)
            self.assert_decoders(wire, [frame], 0)

    def test_all_octet_values_and_maximum_frames(self):
        frames = [codec.Frame(3, 255, 2**64 - 1, 2**32 - 1, bytes(range(192))),
                  codec.Frame(3, 0, 0, 0, bytes(range(192, 256))),
                  codec.Frame(4, 0, 1, 7, bytes([0x7E, 0x7D]) * 96)]
        for frame in frames:
            wire = codec.encode(frame)
            self.assertLessEqual(len(wire), codec.MAX_WIRE)
            self.assert_decoders(wire, [frame], 0)

    def test_shared_flags_noise_and_empty_frames(self):
        frame = codec.Frame(1, 0, 12, 13, b'probe')
        wire = codec.encode(frame)
        self.assert_decoders(b'ignored-before-start' + b'\x7e' * 3 + wire + wire[1:] + b'\x7e' * 4,
                             [frame, frame], 0)

    def test_all_single_bit_corruptions_of_raw_frame_are_rejected(self):
        frame = codec.Frame(2, 1, 18, 28, b'acknowledgement is not actuation')
        raw = codec.HEADER.pack(b'HM', 1, 2, 0, 1, 18, 28, len(frame.payload)) + frame.payload
        raw = seal(raw)
        wire = bytearray()
        for index in range(len(raw)):
            for bit in range(8):
                corrupt = bytearray(raw)
                corrupt[index] ^= 1 << bit
                wire.extend(framed_raw(corrupt))
        self.assert_decoders(bytes(wire) + codec.encode(frame), [frame], len(raw) * 8)

    def test_valid_checksum_does_not_bypass_header_and_length_checks(self):
        base = bytearray(codec.HEADER.pack(b'HM', 1, 1, 0, 0, 1, 2, 0))
        wire = bytearray()
        for index, value in [(0, ord('X')), (2, 2), (3, 0), (3, 5), (4, 1), (19, 1)]:
            bad = bytearray(base)
            bad[index] = value
            wire.extend(framed_raw(seal(bad)))
        wire.extend(framed_raw(seal(base + b'extra')))
        self.assert_decoders(bytes(wire), [], 7)

    def test_overflow_and_dangling_escape_resynchronize(self):
        frame = codec.Frame(1, 0, 1, 1, b'next')
        self.assert_decoders(b'\x7e' + b'X' * 10000 + codec.encode(frame), [frame], 1)
        self.assert_decoders(b'\x7eHM\x7d' + codec.encode(frame), [frame], 1)

    def test_external_reset_drops_partial_state_and_waits_for_flag(self):
        frame = codec.Frame(1, 0, 1, 1, b'session reset')
        wire = codec.encode(frame)
        parser = codec.Decoder()
        for byte in wire[:10]: parser.feed(byte)
        parser.reset()
        events = [parser.feed(byte) for byte in wire[10:-1]]
        self.assertTrue(all(event is None for event in events))
        events = [parser.feed(byte) for byte in wire]
        self.assertEqual([event for event in events if event], [('frame', frame)])

    def test_seeded_noise_then_known_frames_stays_bounded(self):
        rng = random.Random(20261106)
        frame = codec.Frame(2, 1, 500, 8, b'recovery')
        wire = bytes(rng.randrange(256) for _ in range(100000)) + b'\x7e' + codec.encode(frame)
        self.assert_decoders(wire, [frame])

    def test_encoder_rejects_range_overflow_instead_of_truncating(self):
        for frame in [codec.Frame(1, 0, 0, 0, b'x' * 193), codec.Frame(1, -1, 0, 0, b''),
                      codec.Frame(1, 0, 2**64, 0, b''), codec.Frame(1, 0, 0, 2**32, b''),
                      codec.Frame(5, 0, 0, 0, b''), codec.Frame(1, True, 0, 0, b'')]:
            with self.assertRaises(ValueError): codec.encode(frame)

    def test_parser_struct_has_a_small_fixed_native_storage_footprint(self):
        size = int(subprocess.check_output([str(self.binary), '--size']))
        self.assertLessEqual(size, 256)  # Host ABI only; not an AVR firmware RAM claim.

    def test_every_truncated_prefix_recovers_at_the_next_frame(self):
        frame = codec.Frame(3, 2, 8, 9, bytes([0x7E, 0x7D]) * 96)
        wire = codec.encode(frame)
        stream = b''.join(wire[:end] + wire for end in range(1, len(wire)))
        # A complete body missing only its closing flag legally shares the next
        # frame's opening flag, so that final case yields two complete frames.
        self.assert_decoders(stream, [frame] * len(wire))

    def test_extreme_claimed_lengths_are_never_allocation_requests(self):
        stream, expected = bytearray(), []
        for claimed in (0, 1, 191, 192, 193, 255, 256, 65534, 65535):
            for actual in (0, 1, 191, 192, 193, 255, 256):
                payload = b'\x55' * actual
                header = codec.HEADER.pack(b'HM', 1, 2, 0, 0, 1, 1, claimed)
                stream.extend(framed_raw(seal(header + payload)))
                if claimed == actual and actual <= codec.MAX_PAYLOAD:
                    expected.append(codec.Frame(2, 0, 1, 1, payload))
        self.assert_decoders(bytes(stream), expected)

    def test_receiver_accepts_alternative_escapes_without_dropping_control_bytes(self):
        frame = codec.Frame(1, 0, 1, 1, b'\x00\x03\x11\x13\x7d\x7e')
        raw = seal(codec.HEADER.pack(b'HM', 1, 1, 0, 0, 1, 1, len(frame.payload)) + frame.payload)
        wire = b'\x7e' + b''.join(bytes((0x7D, byte ^ 0x20)) if byte != 0x5E else bytes((byte,))
                                  for byte in raw) + b'\x7e'
        self.assert_decoders(wire, [frame], 0)


if __name__ == '__main__':
    unittest.main()
