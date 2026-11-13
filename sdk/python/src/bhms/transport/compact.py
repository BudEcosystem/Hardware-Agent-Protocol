"""BHMS-Compact transport: message and value codecs, layouts, and framing over a byte stream.

Implements spec/bhms/11-compact-binding.md for the gateway side (and for tests, harnesses and conformance checks that
play either side): every message of §11.2 in both directions, the value codec of §11.4 with the refusals of
BHMS-CMP-010, the ``compact`` layouts of a description (§4.8), the static layout rules BHMS-DEV-070/071, and
:class:`CompactLink`, which carries payloads in the ``HM`` frames of ``protocol/serial/frame.py`` (reused through the
:mod:`bhms.transport.hm_frame` symlink, never reimplemented) over a serial port, a pty, a Unix or a TCP socket.

This module is the one Python compact codec. The top level imports only the standard library so that firmware test
harnesses without the SDK's dependencies can load it by path (``sdk/c/tests/host/bhms_host.py`` does); the description
digest and the frame codec are imported on first use.

Example::

    link = CompactLink(await open_stream("/dev/ttyACM0", baud=115200))
    link.start()
    link.send(hello_req(nonce=1), session=0)
    reply = await link.receive(timeout=2.0)       # Incoming(frame, message=Hello(...), wire=b"~HM...~")

Thread-safety: one event loop; the codecs are pure functions.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import math
import os
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

# ----------------------------------------------------------------------------------------------- constants

CHANNEL = 1
CONTROL, STATUS_KIND, TELEMETRY = 1, 2, 3
COMPACT_VERSION = 1
MAX_PAYLOAD = 192

HELLO_REQ, INVOKE, CANCEL, READ, STOP, QUERY = 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
HELLO, STATUS, RESULT, VALUE, STOP_ACK, ERROR = 0x81, 0x82, 0x83, 0x84, 0x85, 0xFF

HELLO_NEW_SESSION = 0x01
FLAG_FENCING, FLAG_PERSISTENT_EPOCH, FLAG_STOP_SUPPORTED = 0x01, 0x02, 0x04

ST_ACCEPTED, ST_RUNNING, ST_COMPLETED, ST_FAILED, ST_CANCELED, ST_REJECTED = 1, 2, 3, 4, 5, 6
TERMINAL_STATES = (ST_COMPLETED, ST_FAILED, ST_CANCELED, ST_REJECTED)
CANCEL_NONE, CANCEL_REQUESTED, CANCEL_ACK, CANCEL_REFUSED, CANCEL_CONFIRMED = 0, 1, 2, 3, 4
PROGRESS_UNKNOWN = 255
EVIDENCE_NONE, EVIDENCE_REPORTED, EVIDENCE_MEASURED = 0, 1, 2
Q_VALID, Q_STALE, Q_INVALID, Q_UNKNOWN = 0, 1, 2, 3
AGE_UNKNOWN = 0xFFFFFFFF
READ_FRESH = 0x01
STOPACK_INITIATED, STOPACK_CONFIRMED, STOPACK_UNSUPPORTED = 0, 1, 2

ERROR_CODES = {1: "MALFORMED", 2: "UNKNOWN_ACTION", 3: "UNKNOWN_PROPERTY", 4: "OUT_OF_RANGE", 5: "FENCED",
               6: "LEASE_REQUIRED", 7: "BUSY", 8: "HANDLE_UNKNOWN", 9: "SESSION_MISMATCH", 10: "EXPIRED",
               11: "UNSUPPORTED", 12: "PRECONDITION", 13: "INHIBITED", 14: "HANDLE_CONFLICT", 15: "INTERNAL"}
ERR = {name: code for code, name in ERROR_CODES.items()}
(E_MALFORMED, E_UNKNOWN_ACTION, E_UNKNOWN_PROPERTY, E_OUT_OF_RANGE, E_FENCED, E_LEASE_REQUIRED, E_BUSY, E_HANDLE_UNKNOWN,
 E_SESSION_MISMATCH, E_EXPIRED, E_UNSUPPORTED, E_PRECONDITION, E_INHIBITED, E_HANDLE_CONFLICT, E_INTERNAL) = range(1, 16)

# ERROR codes that do not guarantee that an INVOKE did not start (spec 11.2).
NOT_A_PROOF = frozenset({E_HANDLE_UNKNOWN, E_SESSION_MISMATCH, E_HANDLE_CONFLICT})

QUALITY_NAMES = {Q_VALID: "valid", Q_STALE: "stale", Q_INVALID: "invalid", Q_UNKNOWN: "unknown"}
VALUE_EVIDENCE_NAMES = {0: "measured", 1: "reported", 2: "commanded", 3: "estimated", 4: "simulated"}


class CompactError(ValueError):
    """A payload that is not a valid BHMS-Compact message (BHMS-CMP-002), or a layout that cannot be used."""


class CompactValueError(ValueError):
    """A value the wire cannot carry exactly (BHMS-CMP-010). ``code`` is the BHMS error code to report
    (``INVALID_ARGUMENT`` or ``OUT_OF_RANGE``); nothing may be sent."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code, self.field = code, field


# ----------------------------------------------------------------------------------------------- messages


@dataclass(frozen=True)
class HelloReq:
    nonce: int
    flags: int = 0
    version: int = COMPACT_VERSION

    @property
    def new_session(self) -> bool:
        return bool(self.flags & HELLO_NEW_SESSION)

    def encode(self) -> bytes:
        return struct.pack("<BBBI", HELLO_REQ, self.version, self.flags, self.nonce)


@dataclass(frozen=True)
class Hello:
    flags: int
    digest8: bytes
    epoch: int
    nonce: int
    last_handle: int
    ring: int
    max_active: int
    max_args: int
    version: int = COMPACT_VERSION

    @property
    def fencing(self) -> bool:
        return bool(self.flags & FLAG_FENCING)

    @property
    def persistent(self) -> bool:
        return bool(self.flags & FLAG_PERSISTENT_EPOCH)

    @property
    def stop_supported(self) -> bool:
        return bool(self.flags & FLAG_STOP_SUPPORTED)

    def encode(self) -> bytes:
        return struct.pack("<BBB8sIIHBBB", HELLO, self.version, self.flags, self.digest8, self.epoch, self.nonce,
                           self.last_handle, self.ring, self.max_active, self.max_args)


@dataclass(frozen=True)
class Invoke:
    handle: int
    action: int
    args: bytes = b""
    fence: int = 0
    ttl_ms: int = 0

    def encode(self) -> bytes:
        return struct.pack("<BHBIH", INVOKE, self.handle, self.action, self.fence, self.ttl_ms) + self.args


@dataclass(frozen=True)
class Cancel:
    handle: int

    def encode(self) -> bytes:
        return struct.pack("<BH", CANCEL, self.handle)


@dataclass(frozen=True)
class Read:
    request: int
    prop: int
    flags: int = 0

    @property
    def fresh(self) -> bool:
        return bool(self.flags & READ_FRESH)

    def encode(self) -> bytes:
        return struct.pack("<BHBB", READ, self.request, self.prop, self.flags)


@dataclass(frozen=True)
class Stop:
    reason: int = 0

    def encode(self) -> bytes:
        return struct.pack("<BB", STOP, self.reason)


@dataclass(frozen=True)
class Query:
    handle: int

    def encode(self) -> bytes:
        return struct.pack("<BH", QUERY, self.handle)


@dataclass(frozen=True)
class Status:
    handle: int
    state: int
    cancel: int = 0
    progress: int = PROGRESS_UNKNOWN

    def encode(self) -> bytes:
        return struct.pack("<BHBBB", STATUS, self.handle, self.state, self.cancel, self.progress)


@dataclass(frozen=True)
class Result:
    handle: int
    state: int
    evidence: int = 0
    fault: int = 0
    fields: bytes = b""

    def encode(self) -> bytes:
        return struct.pack("<BHBBB", RESULT, self.handle, self.state, self.evidence, self.fault) + self.fields


@dataclass(frozen=True)
class Value:
    request: int
    prop: int
    quality: int
    evidence: int
    sequence: int
    age_ms: int
    raw: bytes = b""

    def encode(self) -> bytes:
        return struct.pack("<BHBBBII", VALUE, self.request, self.prop, self.quality, self.evidence, self.sequence,
                           self.age_ms) + self.raw


@dataclass(frozen=True)
class StopAck:
    outcome: int
    evidence: int = 0
    canceled: int = 0

    def encode(self) -> bytes:
        return struct.pack("<BBBB", STOP_ACK, self.outcome, self.evidence, self.canceled)


@dataclass(frozen=True)
class Error:
    request_type: int
    ident: int
    code: int
    detail: int = 0

    @property
    def name(self) -> str:
        return ERROR_CODES.get(self.code, f"UNKNOWN_{self.code}")

    def encode(self) -> bytes:
        return struct.pack("<BBHBB", ERROR, self.request_type, self.ident, self.code, self.detail)


Message = HelloReq | Hello | Invoke | Cancel | Read | Stop | Query | Status | Result | Value | StopAck | Error

# (struct format after the type byte, exact length incl. type byte or minimum for variable messages, variable?)
_FIXED: dict[int, tuple[struct.Struct, int, bool]] = {
    HELLO_REQ: (struct.Struct("<BBI"), 7, False),
    HELLO: (struct.Struct("<BB8sIIHBBB"), 24, False),
    INVOKE: (struct.Struct("<HBIH"), 10, True),
    CANCEL: (struct.Struct("<H"), 3, False),
    READ: (struct.Struct("<HBB"), 5, False),
    STOP: (struct.Struct("<B"), 2, False),
    QUERY: (struct.Struct("<H"), 3, False),
    STATUS: (struct.Struct("<HBBB"), 6, False),
    RESULT: (struct.Struct("<HBBB"), 6, True),
    VALUE: (struct.Struct("<HBBBII"), 14, True),
    STOP_ACK: (struct.Struct("<BBB"), 4, False),
    ERROR: (struct.Struct("<BHBB"), 6, False),
}


def decode(payload: bytes) -> Message:
    """The message in ``payload``; :class:`CompactError` when its type is unknown or its length is not exactly the one its
    layout defines (BHMS-CMP-002: fixed messages exactly, variable ones at least their fixed part)."""
    if not payload:
        raise CompactError("empty payload")
    kind = payload[0]
    layout = _FIXED.get(kind)
    if layout is None:
        raise CompactError(f"unknown message type 0x{kind:02x}")
    fmt, length, variable = layout
    if len(payload) < length or (not variable and len(payload) != length):
        raise CompactError(f"message 0x{kind:02x} has {len(payload)} bytes, its layout needs "
                           f"{'at least ' if variable else ''}{length}")
    fields = fmt.unpack_from(payload, 1)
    rest = bytes(payload[length:])
    if kind == HELLO_REQ:
        return HelloReq(nonce=fields[2], flags=fields[1], version=fields[0])
    if kind == HELLO:
        version, flags, digest8, epoch, nonce, last, ring, active, max_args = fields
        return Hello(flags, digest8, epoch, nonce, last, ring, active, max_args, version)
    if kind == INVOKE:
        handle, action, fence, ttl = fields
        return Invoke(handle, action, rest, fence, ttl)
    if kind == CANCEL:
        return Cancel(*fields)
    if kind == READ:
        return Read(*fields)
    if kind == STOP:
        return Stop(*fields)
    if kind == QUERY:
        return Query(*fields)
    if kind == STATUS:
        return Status(*fields)
    if kind == RESULT:
        return Result(fields[0], fields[1], fields[2], fields[3], rest)
    if kind == VALUE:
        return Value(*fields, raw=rest)
    if kind == STOP_ACK:
        return StopAck(*fields)
    return Error(*fields)


# Builders of payloads (what a harness or a test sends or expects); each is `Message(...).encode()`.


def hello_req(nonce: int, new_session: bool = False) -> bytes:
    return HelloReq(nonce, HELLO_NEW_SESSION if new_session else 0).encode()


def hello(flags: int, digest8: bytes, epoch: int, nonce: int, last_handle: int, ring: int, max_active: int,
          max_args: int) -> bytes:
    return Hello(flags, digest8, epoch, nonce, last_handle, ring, max_active, max_args).encode()


def invoke(handle: int, action: int, args: bytes = b"", fence: int = 0, ttl_ms: int = 0) -> bytes:
    return Invoke(handle, action, args, fence, ttl_ms).encode()


def cancel(handle: int) -> bytes:
    return Cancel(handle).encode()


def query(handle: int) -> bytes:
    return Query(handle).encode()


def read(request: int, prop: int, fresh: bool = False) -> bytes:
    return Read(request, prop, READ_FRESH if fresh else 0).encode()


def stop(reason: int = 0) -> bytes:
    return Stop(reason).encode()


def status(handle: int, state: int, cancel_state: int, progress: int) -> bytes:
    return Status(handle, state, cancel_state, progress).encode()


def result(handle: int, state: int, evidence: int, fault: int, fields: bytes = b"") -> bytes:
    return Result(handle, state, evidence, fault, fields).encode()


def value(request: int, prop: int, quality: int, evidence: int, seq: int, age_ms: int, raw: bytes = b"") -> bytes:
    return Value(request, prop, quality, evidence, seq, age_ms, raw).encode()


def stop_ack(outcome: int, evidence: int, canceled: int) -> bytes:
    return StopAck(outcome, evidence, canceled).encode()


def error(req_type: int, ident: int, code: int, detail: int = 0) -> bytes:
    return Error(req_type, ident, code, detail).encode()


# ----------------------------------------------------------------------------------------------- values (§11.4)

_TYPES: dict[str, tuple[str, int, int | float, int | float]] = {
    "u8": ("<B", 1, 0, 255), "i8": ("<b", 1, -128, 127), "u16": ("<H", 2, 0, 65535), "i16": ("<h", 2, -32768, 32767),
    "u32": ("<I", 4, 0, 2**32 - 1), "i32": ("<i", 4, -(2**31), 2**31 - 1),
    "f32": ("<f", 4, -math.inf, math.inf), "bool": ("<B", 1, 0, 1)}
TYPE_NAMES = tuple(_TYPES)
INTEGER_TYPES = ("u8", "i8", "u16", "i16", "u32", "i32")
_TOLERANCE = 1e-9  # BHMS-CMP-010 / DEV-071
_F32_TOLERANCE = 1e-6


def type_width(type_name: str) -> int:
    return _TYPES[type_name][1]


def type_range(type_name: str) -> tuple[int | float, int | float]:
    return _TYPES[type_name][2], _TYPES[type_name][3]


def encode_value(type_name: str, scale: float | None, value: Any, *, name: str | None = None) -> bytes:
    """The wire bytes of ``value`` for one field; refuses, never rounds, clamps or truncates (BHMS-CMP-010).

    ``INVALID_ARGUMENT``: a value that is not within 1e-9 (relative) of an integer after division by ``scale``, a
    non-number, a non-finite number, an ``f32`` whose binary32 conversion differs by more than 1e-6 x max(1, |value|).
    ``OUT_OF_RANGE``: an integer outside the field type's range.
    """
    fmt, _width, low, high = _TYPES[type_name]
    where = f"{name!r}: " if name else ""
    if type_name == "bool":
        if not isinstance(value, bool):
            raise CompactValueError("INVALID_ARGUMENT", f"{where}bool field needs true or false, got {value!r}", name)
        return struct.pack(fmt, 1 if value else 0)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise CompactValueError("INVALID_ARGUMENT", f"{where}{type_name} field needs a finite number, got {value!r}", name)
    if type_name == "f32":
        try:
            packed = struct.pack(fmt, value)
        except OverflowError:
            raise CompactValueError("OUT_OF_RANGE", f"{where}{value!r} is outside the f32 range", name) from None
        back = struct.unpack(fmt, packed)[0]
        if abs(back - value) > _F32_TOLERANCE * max(1.0, abs(value)):
            raise CompactValueError("INVALID_ARGUMENT", f"{where}{value!r} cannot be carried exactly as f32 (got {back!r})", name)
        return packed
    quotient = Decimal(repr(value)) / Decimal(repr(scale)) if scale is not None else Decimal(repr(value))
    nearest = quotient.to_integral_value()
    if abs(quotient - nearest) > Decimal(_TOLERANCE) * max(Decimal(1), abs(quotient)):
        raise CompactValueError("INVALID_ARGUMENT", f"{where}{value!r} is not a whole number of "
                                f"{scale if scale is not None else 1} (BHMS-CMP-010)", name)
    wire = int(nearest)
    if not low <= wire <= high:
        raise CompactValueError("OUT_OF_RANGE", f"{where}{value!r} is outside the {type_name} range "
                                f"{low}..{high} x {scale if scale is not None else 1}", name)
    return struct.pack(fmt, wire)


def decode_value(type_name: str, scale: float | None, data: bytes, *, name: str | None = None) -> Any:
    """The JSON value of one field's wire bytes (``wire x scale`` in exact decimal arithmetic, so 501 x 0.1 is 50.1)."""
    fmt, width, _low, _high = _TYPES[type_name]
    if len(data) != width:
        raise CompactError(f"field {name or type_name} needs {width} bytes, got {len(data)}")
    raw = struct.unpack(fmt, data)[0]
    if type_name == "bool":
        if raw > 1:
            raise CompactError(f"field {name or 'bool'}: bool byte {raw} is neither 0 nor 1")
        return bool(raw)
    if type_name == "f32":
        if not math.isfinite(raw):
            raise CompactError(f"field {name or 'f32'}: non-finite f32")
        return raw
    if scale is None:
        return raw
    scaled = Decimal(raw) * Decimal(repr(scale))
    if scaled == scaled.to_integral_value() and Decimal(repr(scale)) == Decimal(repr(scale)).to_integral_value():
        return int(scaled)
    return float(scaled)


@dataclass(frozen=True)
class Field:
    """One argument, result or property field of a layout."""

    name: str
    type: str
    scale: float | None = None

    @property
    def width(self) -> int:
        return _TYPES[self.type][1]


def encode_fields(fields: Sequence[Field], values: Mapping[str, Any]) -> bytes:
    """The layout's fields concatenated in order (INVOKE arguments)."""
    missing = [f.name for f in fields if f.name not in values]
    if missing:
        raise CompactValueError("INVALID_ARGUMENT", f"missing argument(s) {missing}", missing[0])
    return b"".join(encode_value(f.type, f.scale, values[f.name], name=f.name) for f in fields)


def decode_fields(fields: Sequence[Field], data: bytes) -> dict[str, Any]:
    """The values of a RESULT's fields (exact length, BHMS-CMP-002)."""
    expected = sum(f.width for f in fields)
    if len(data) != expected:
        raise CompactError(f"result fields need {expected} bytes, got {len(data)}")
    out: dict[str, Any] = {}
    offset = 0
    for f in fields:
        out[f.name] = decode_value(f.type, f.scale, data[offset:offset + f.width], name=f.name)
        offset += f.width
    return out


@dataclass(frozen=True)
class ActionLayout:
    index: int
    args: tuple[Field, ...]
    result: tuple[Field, ...]


@dataclass(frozen=True)
class PropertyLayout:
    index: int
    type: str
    scale: float | None = None

    @property
    def field(self) -> Field:
        return Field("value", self.type, self.scale)


@dataclass(frozen=True)
class Layouts:
    """The compact layouts of one description, by action and property name (never derived from name order, BHMS-CMP-011)."""

    actions: dict[str, ActionLayout] = field(default_factory=dict)
    properties: dict[str, PropertyLayout] = field(default_factory=dict)


def _field(entry: Any, where: str) -> Field:
    if not isinstance(entry, dict) or entry.get("type") not in _TYPES or not isinstance(entry.get("name", "value"), str):
        raise CompactError(f"{where}: not a compact field {entry!r}")
    scale = entry.get("scale")
    if scale is not None and (isinstance(scale, bool) or not isinstance(scale, int | float) or not scale > 0
                              or entry["type"] in ("f32", "bool")):
        raise CompactError(f"{where}: scale must be a positive number on an integer field, got {scale!r} on {entry['type']}")
    return Field(entry.get("name", "value"), entry["type"], scale)


def layouts_from_description(description: Mapping[str, Any]) -> Layouts:
    """The layouts of ``description``; :class:`CompactError` when an action or property has none (a compact device serves
    only layouts it can translate) or the indices repeat."""
    actions: dict[str, ActionLayout] = {}
    for name, action in (description.get("actions") or {}).items():
        raw = action.get("compact")
        if not isinstance(raw, dict) or not isinstance(raw.get("index"), int):
            raise CompactError(f"action {name!r} has no compact layout")
        actions[name] = ActionLayout(raw["index"], tuple(_field(f, f"action {name!r} args") for f in raw.get("args", [])),
                                     tuple(_field(f, f"action {name!r} result") for f in raw.get("result", [])))
    properties: dict[str, PropertyLayout] = {}
    for name, prop in (description.get("properties") or {}).items():
        raw = prop.get("compact")
        if not isinstance(raw, dict) or not isinstance(raw.get("index"), int):
            raise CompactError(f"property {name!r} has no compact layout")
        one = _field({"name": "value", **raw}, f"property {name!r}")
        properties[name] = PropertyLayout(raw["index"], one.type, one.scale)
    for label, indices in (("action", [a.index for a in actions.values()]), ("property", [p.index for p in properties.values()])):
        if len(indices) != len(set(indices)):
            raise CompactError(f"{label} indices must be unique: {sorted(indices)}")
        if any(not 0 <= i <= 255 for i in indices):
            raise CompactError(f"{label} indices must fit a byte: {sorted(indices)}")
    return Layouts(actions, properties)


def layout_problems(description: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``(requirement id, problem)`` for every violation of BHMS-DEV-070/071 in one description (empty: valid)."""
    out: list[tuple[str, str]] = []
    device = description.get("deviceId")

    def mirror(label: str, schema: dict[str, Any], field_type: str, scale: float | None) -> None:
        low, high = type_range(field_type)
        if scale is None:
            if field_type in INTEGER_TYPES:
                if schema.get("type") != "integer" and schema.get("multipleOf") != 1:
                    out.append(("BHMS-DEV-071", f"{label}: an unscaled integer field needs type integer or multipleOf 1"))
                if "minimum" in schema and schema["minimum"] < low or "maximum" in schema and schema["maximum"] > high:
                    out.append(("BHMS-DEV-071", f"{label}: minimum/maximum must lie inside the {field_type} range"))
            elif field_type == "bool" and schema.get("type") != "boolean":
                out.append(("BHMS-DEV-071", f"{label}: a bool field mirrors type boolean"))
            return
        if abs(schema.get("multipleOf", 0) - scale) > 1e-12 * max(1.0, scale):
            out.append(("BHMS-DEV-071", f"{label}: scale {scale} must be mirrored by multipleOf (is {schema.get('multipleOf')!r})"))
        if "minimum" not in schema or "maximum" not in schema or schema["minimum"] < low * scale - 1e-9 \
                or schema["maximum"] > high * scale + 1e-9:
            out.append(("BHMS-DEV-071", f"{label}: minimum/maximum must lie inside the {field_type} range times {scale}"))

    action_indices: list[int] = []
    for name, action in (description.get("actions") or {}).items():
        layout = action.get("compact")
        if not layout:
            continue
        action_indices.append(layout["index"])
        schema = action.get("input") or {}
        members = set(schema.get("properties") or {})
        names = [f["name"] for f in layout["args"]]
        if sorted(names) != sorted(members):
            out.append(("BHMS-DEV-070", f"{device}.{name}: args {names} must map every input member {sorted(members)} exactly once"))
        for f in layout["args"]:
            member = (schema.get("properties") or {}).get(f["name"], {})
            if f["name"] in members and f["name"] not in (schema.get("required") or []) and "default" not in member:
                out.append(("BHMS-DEV-070", f"{device}.{name}.{f['name']}: a mapped member must be required or declare a default"))
            mirror(f"{device}.{name}.{f['name']}", member, f["type"], f.get("scale"))
        output = (action.get("output") or {}).get("properties") or {}
        for f in layout["result"]:
            if f["name"] not in output:
                out.append(("BHMS-DEV-070", f"{device}.{name}: result field {f['name']!r} names no output member"))
            else:
                mirror(f"{device}.{name} result {f['name']}", output[f["name"]], f["type"], f.get("scale"))
    property_indices = []
    for name, prop in (description.get("properties") or {}).items():
        layout = prop.get("compact")
        if layout:
            property_indices.append(layout["index"])
            mirror(f"{device}.{name}", prop.get("schema") or {}, layout["type"], layout.get("scale"))
    for label, indices in (("action", action_indices), ("property", property_indices)):
        if len(indices) != len(set(indices)):
            out.append(("BHMS-DEV-070", f"{device}: {label} indices must be unique: {sorted(indices)}"))
    return out


def description_digest(description: Mapping[str, Any]) -> str:
    """``sha256:<hex>`` of the JCS form of ``description`` without its ``digest`` member (BHMS-DEV-021)."""
    from bhms.protocol.canonical import digest

    return digest({k: v for k, v in description.items() if k != "digest"})


def digest8_of(description: Mapping[str, Any]) -> bytes:
    """The first 8 bytes of the description digest: what the endpoint reports in HELLO (§11.2)."""
    return bytes.fromhex(description_digest(description)[len("sha256:"):])[:8]


# ----------------------------------------------------------------------------------------------- byte streams


class LinkClosed(ConnectionError):
    """The byte stream ended (device unplugged, peer closed)."""


class ByteStream(Protocol):
    """What :class:`CompactLink` needs of a serial port, pty or socket."""

    async def read(self) -> bytes:
        """Next bytes, or ``b""`` at end of stream."""

    def write(self, data: bytes) -> None:
        """Queue ``data`` for sending; never blocks."""

    async def close(self) -> None: ...


class FdStream:
    """A non-blocking file descriptor (tty, pty, pipe) driven by the event loop."""

    def __init__(self, fd: int) -> None:
        os.set_blocking(fd, False)
        self._fd = fd
        self._loop = asyncio.get_running_loop()
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self._out = bytearray()
        self._writing = False
        self._closed = False
        self._loop.add_reader(fd, self._on_readable)

    def _on_readable(self) -> None:
        try:
            data = os.read(self._fd, 4096)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        self._inbox.put_nowait(data)
        if not data:
            self._loop.remove_reader(self._fd)

    async def read(self) -> bytes:
        if self._closed and self._inbox.empty():
            return b""
        data = await self._inbox.get()
        if not data:
            self._inbox.put_nowait(b"")  # end of stream stays visible to every later read
        return data

    def write(self, data: bytes) -> None:
        if self._closed:
            return
        self._out += data
        self._flush()

    def _flush(self) -> None:
        while self._out:
            try:
                written = os.write(self._fd, self._out)
            except BlockingIOError:
                if not self._writing:
                    self._loop.add_writer(self._fd, self._flush)
                    self._writing = True
                return
            except OSError:
                self._out.clear()
                break
            del self._out[:written]
        if self._writing:
            self._loop.remove_writer(self._fd)
            self._writing = False

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            self._loop.remove_reader(self._fd)
        if self._writing:
            with contextlib.suppress(Exception):
                self._loop.remove_writer(self._fd)
        with contextlib.suppress(OSError):
            os.close(self._fd)
        self._inbox.put_nowait(b"")


class SocketStream:
    """An asyncio ``StreamReader``/``StreamWriter`` pair (Unix or TCP socket)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader, self._writer = reader, writer

    async def read(self) -> bytes:
        try:
            return await self._reader.read(4096)
        except (ConnectionError, OSError):
            return b""

    def write(self, data: bytes) -> None:
        if not self._writer.is_closing():
            self._writer.write(data)

    async def close(self) -> None:
        self._writer.close()
        with contextlib.suppress(Exception):
            await self._writer.wait_closed()


def _open_serial_fd(path: str, baud: int) -> int:
    import termios
    import tty

    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        if os.isatty(fd):
            tty.setraw(fd, termios.TCSANOW)
            speed = getattr(termios, f"B{baud}", None)
            if speed is None:
                raise OSError(f"unsupported baud rate {baud}")
            attrs = termios.tcgetattr(fd)
            attrs[2] |= termios.CLOCAL | termios.CREAD
            attrs[4] = attrs[5] = speed
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIOFLUSH)
    except BaseException:
        os.close(fd)
        raise
    return fd


async def open_stream(port: str, baud: int = 115200) -> ByteStream:
    """Open the physical link: ``/dev/ttyACM0`` (also ``serial:`` and ``pty:`` followed by a device path; configured with
    ``baud``, 8N1, raw), ``unix:/path/to/socket`` or ``tcp://host:port`` (a serial-to-network bridge)."""
    if port.startswith("unix:"):
        path = port[5:]
        reader, writer = await asyncio.open_unix_connection(path[2:] if path.startswith("//") else path)
        return SocketStream(reader, writer)
    if port.startswith("tcp://"):
        host, _, number = port[6:].rstrip("/").rpartition(":")
        reader, writer = await asyncio.open_connection(host.strip("[]"), int(number))
        return SocketStream(reader, writer)
    for prefix in ("serial:", "pty:"):
        if port.startswith(prefix):
            port = port[len(prefix):]
    if not port.startswith(("/", ".")):
        raise OSError(f"cannot open {port!r}: expected a device path, unix:<path> or tcp://host:port")
    return FdStream(_open_serial_fd(port, baud))


# ----------------------------------------------------------------------------------------------- the link


@dataclass(frozen=True)
class Incoming:
    """One valid compact frame received: its header, decoded message and the exact wire bytes (both flags)."""

    frame: Any
    message: Message
    wire: bytes

    @property
    def session(self) -> int:
        return int(self.frame.session)

    @property
    def kind(self) -> int:
        return int(self.frame.kind)


def _frame_module() -> Any:
    from bhms.transport import hm_frame

    return hm_frame


class CompactLink:
    """Frames and unframes compact payloads over a :class:`ByteStream`.

    ``send`` encodes with ``protocol/serial/frame.py`` and writes at once (it never waits, so a STOP is on the wire before
    anything queued behind it could be). Received bytes go through the reused ``Decoder``; a frame is delivered only when
    its FCS is valid, its channel is 1 (BHMS-CMP-001), its kind is status or telemetry and its payload is exactly one
    message (BHMS-CMP-002). Everything else is counted in ``stats`` and dropped; a corrupt frame never needs more than the
    next flag to resynchronise. ``tx_seq`` is the per-direction diagnostic counter (reset it on a new epoch).
    """

    def __init__(self, stream: ByteStream, *, max_pending: int = 1024) -> None:
        self.stream = stream
        self.frame = _frame_module()
        self.decoder = self.frame.Decoder()
        self.session = 0
        self.tx_seq = 0
        self.stats: collections.Counter[str] = collections.Counter()
        self._wire = bytearray()
        self._inbox: asyncio.Queue[Incoming | None] = asyncio.Queue(max_pending)
        self._task: asyncio.Task[None] | None = None
        self.closed = False

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._pump(), name="bhms-compact-link")

    def send(self, message: Message | bytes, session: int | None = None, *, kind: int = CONTROL,
             channel: int = CHANNEL, sequence: int | None = None) -> bytes:
        """Frame and write one payload; returns the wire bytes. ``session`` defaults to :attr:`session`."""
        payload = message if isinstance(message, bytes) else message.encode()
        seq = self.tx_seq if sequence is None else sequence
        wire = self.frame.encode(self.frame.Frame(kind, channel, self.session if session is None else session,
                                                  seq % 2**32, payload))
        if sequence is None:
            self.tx_seq = (self.tx_seq + 1) % 2**32
        if not self.closed:
            self.stream.write(wire)
        self.stats["tx"] += 1
        return wire

    def reset_sequence(self) -> None:
        self.tx_seq = 0

    async def receive(self, timeout: float | None = None) -> Incoming | None:
        """The next valid frame, or None when ``timeout`` seconds pass; :class:`LinkClosed` at end of stream."""
        try:
            item = await asyncio.wait_for(self._inbox.get(), timeout)
        except asyncio.TimeoutError:
            return None
        if item is None:
            if not self._inbox.full():
                self._inbox.put_nowait(None)  # end of stream stays visible to every later receive
            raise LinkClosed("the byte stream ended")
        return item

    async def _pump(self) -> None:
        try:
            while True:
                chunk = await self.stream.read()
                if not chunk:
                    break
                for byte in chunk:
                    self._feed(byte)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken stream ends the link, the supervisor reopens it
            self.stats["stream-error"] += 1
        self.closed = True
        while self._inbox.full():
            self._inbox.get_nowait()
        self._inbox.put_nowait(None)

    def _feed(self, byte: int) -> None:
        event = self.decoder.feed(byte)
        self._wire.append(byte)
        if byte == self.frame.FLAG:
            wire, self._wire = bytes(self._wire), bytearray([byte])
            if event is not None:
                self._deliver(event, wire)
        elif event is not None:
            self._deliver(event, bytes(self._wire))

    def _deliver(self, event: tuple[str, Any], wire: bytes) -> None:
        if event[0] == "error":
            self.stats["frame-error"] += 1
            return
        frame = event[1]
        if frame.channel != CHANNEL:
            self.stats["other-channel"] += 1
            return
        if frame.kind not in (STATUS_KIND, TELEMETRY):
            self.stats["wrong-kind"] += 1
            return
        try:
            message = decode(frame.payload)
        except CompactError:
            self.stats["malformed"] += 1
            return
        if message.__class__ in (HelloReq, Invoke, Cancel, Read, Stop, Query):
            self.stats["wrong-direction"] += 1
            return
        self.stats["rx"] += 1
        try:
            self._inbox.put_nowait(Incoming(frame, message, wire))
        except asyncio.QueueFull:
            self.stats["overflow"] += 1

    async def close(self) -> None:
        self.closed = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self.stream.close()


__all__ = [name for name in dir() if not name.startswith("_") and name not in (
    "annotations", "asyncio", "collections", "contextlib", "math", "os", "struct", "Mapping", "Sequence", "dataclass",
    "field", "Decimal", "Any", "Protocol")]
