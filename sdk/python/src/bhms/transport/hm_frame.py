"""Experimental HMS serial framing; no authority, replay or device execution.

Wire format and security boundary: spec/07-constrained-binding.md.
Only the bounded framing codec is implemented here.
"""
from dataclasses import dataclass
import struct

FLAG, ESCAPE = 0x7E, 0x7D
VERSION = 1
MAX_PAYLOAD = 192
HEADER = struct.Struct('>2sBBBBQIH')
MAX_RAW = HEADER.size + MAX_PAYLOAD + 2
MAX_WIRE = 2 * MAX_RAW + 2
KINDS = frozenset({1, 2, 3, 4})


def fcs16(data):
    """Uncomplemented reflected FCS register, polynomial 0x8408."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc


@dataclass(frozen=True)
class Frame:
    kind: int
    channel: int
    session: int
    sequence: int
    payload: bytes


def encode(frame):
    if frame.kind not in KINDS or type(frame.kind) is not int:
        raise ValueError('Unsupported kind')
    for value, width in ((frame.channel, 8), (frame.session, 64), (frame.sequence, 32)):
        if type(value) is not int or not 0 <= value < 2**width:
            raise ValueError('Out-of-range integer')
    if not isinstance(frame.payload, bytes) or len(frame.payload) > MAX_PAYLOAD:
        raise ValueError('Payload must be bytes within fixed bound')
    raw = HEADER.pack(b'HM', VERSION, frame.kind, 0, frame.channel,
                      frame.session, frame.sequence, len(frame.payload)) + frame.payload
    raw += struct.pack('<H', fcs16(raw) ^ 0xFFFF)
    out = bytearray([FLAG])
    for byte in raw:
        if byte in (FLAG, ESCAPE):
            out.extend((ESCAPE, byte ^ 0x20))
        else:
            out.append(byte)
    out.append(FLAG)
    return bytes(out)


def decode_raw(raw):
    if not HEADER.size + 2 <= len(raw) <= MAX_RAW:
        raise ValueError('Invalid frame length')
    if fcs16(raw) != 0xF0B8:
        raise ValueError('Invalid FCS')
    magic, version, kind, flags, channel, session, sequence, length = HEADER.unpack_from(raw)
    if magic != b'HM' or version != VERSION or flags or kind not in KINDS:
        raise ValueError('Unsupported header')
    if length > MAX_PAYLOAD or len(raw) != HEADER.size + length + 2:
        raise ValueError('Payload length mismatch')
    return Frame(kind, channel, session, sequence, bytes(raw[HEADER.size:-2]))


class Decoder:
    """One byte in, at most one event out; retains at most MAX_RAW bytes.

    feed returns ('frame', Frame), ('error', reason), or None. No event queue.
    Reset on UART errors, connection changes or an external absolute frame
    deadline. The caller, not this framing layer, owns that timer.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.buffer = bytearray()
        self.active = self.escaped = self.discarding = False

    def feed(self, byte):
        if type(byte) is not int or not 0 <= byte <= 255:
            raise ValueError('Expected one octet')
        if byte == FLAG:
            event = None
            if self.active and not self.discarding:
                if self.escaped:
                    event = ('error', 'Aborted escape')
                elif self.buffer:
                    try:
                        event = ('frame', decode_raw(self.buffer))
                    except ValueError as error:
                        event = ('error', str(error))
            self.buffer.clear()
            self.active, self.escaped, self.discarding = True, False, False
            return event
        if not self.active or self.discarding:
            return None
        if self.escaped:
            byte ^= 0x20
            self.escaped = False
        elif byte == ESCAPE:
            self.escaped = True
            return None
        if len(self.buffer) == MAX_RAW:
            self.buffer.clear()
            self.discarding = True
            return ('error', 'Frame overflow')
        self.buffer.append(byte)
        return None
