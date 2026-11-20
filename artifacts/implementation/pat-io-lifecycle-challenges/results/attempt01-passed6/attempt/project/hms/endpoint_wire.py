"""Compact endpoint packets and correlated receipt validation, profile v0.1.

These pure codecs do not enroll, authenticate, commission, persist, send, retry,
or translate clocks. A gateway must retain its admitted mapping before dispatch.
Binary u64 clock values are exact Python integers, not JSON-safe host numbers.
"""
from dataclasses import dataclass
from enum import IntEnum
import struct

from protocol.serial.frame import Frame

VERSION = 1
ABSENT_TIME = 2**64 - 1
MAX_HORIZON = 2**31 - 1
MAX_ARGUMENTS = 72
MAX_RESULT = 32


class WireError(ValueError):
    """Invalid or uncorrelated data; possible prior effects remain unresolved."""


class Opcode(IntEnum):
    HELLO = 0x01
    BIND = 0x10
    ARM = 0x11
    REVOKE = 0x12
    OP = 0x20
    QUERY = 0x21
    CANCEL = 0x22
    RETIRE = 0x23


class Status(IntEnum):
    OK = 0
    UNSUPPORTED = 1
    BAD_LENGTH = 2
    RESERVED_FIELD = 3
    BAD_STATE = 4
    BOOT_MISMATCH = 5
    CONTEXT_MISMATCH = 6
    BUSY = 7
    OLD_OR_FORGOTTEN = 8
    CONFLICT = 9
    UNKNOWN_PRIMITIVE = 10
    BAD_ARGUMENT = 11
    RESOURCE_MISMATCH = 12
    STALE_FENCE = 13
    BAD_TIME = 14
    START_EXPIRED = 15
    LEASE_INVALID = 16
    UNCOMMISSIONED_OR_EVIDENCE_UNSUPPORTED = 17
    BOOT_UNQUALIFIED = 18
    COUNTER_EXHAUSTED = 19
    NOT_SEEN = 20
    CLOCK_UNQUALIFIED = 21
    RECONCILIATION_REQUIRED = 22


class Execution(IntEnum):
    QUEUED = 1
    RUNNING = 2
    COMPLETED = 3
    FAILED = 4
    CANCELED = 5
    REJECTED_BEFORE_START = 6
    OUTCOME_UNKNOWN = 7


_OP = struct.Struct('>BBIHI32sHBBBBHQQQIQ')
_REFERENCE = struct.Struct('>BBIHI32s')
_CONTROL = struct.Struct('>IH32sBHQQIB')
_HELLO = struct.Struct('>16s32s32sIH32sBHBBBBBQQIB8I')
_RECEIPT = struct.Struct('>IHI32sBBBBBBHIQQQB')


def _require(condition, message='Invalid endpoint packet'):
    if not condition:
        raise WireError(message)


def _uint(value, bits, *, positive=False):
    _require(type(value) is int and int(positive) <= value < 2**bits, 'Invalid unsigned endpoint integer')
    return value


def _bytes(value, length, *, nonzero=False):
    _require(type(value) is bytes and len(value) == length and (not nonzero or any(value)), 'Invalid endpoint byte field')
    return value


def _tick(value):
    _uint(value, 64)
    _require(value != ABSENT_TIME, 'Absent-time sentinel is not a deadline')
    return value


@dataclass(frozen=True)
class Reference:
    control_generation: int
    context_handle: int
    call_number: int
    intent_digest: bytes

    def __post_init__(self):
        _uint(self.control_generation, 32, positive=True)
        _uint(self.context_handle, 16, positive=True)
        _uint(self.call_number, 32, positive=True)
        _bytes(self.intent_digest, 32)

    def payload(self, opcode):
        _require(type(opcode) in (int, Opcode) and opcode in (Opcode.QUERY, Opcode.CANCEL, Opcode.RETIRE),
                 'Expected record operation')
        return _REFERENCE.pack(VERSION, opcode, self.control_generation, self.context_handle,
                               self.call_number, self.intent_digest)


@dataclass(frozen=True)
class Operation:
    reference: Reference
    primitive_id: int
    resource_mask: int
    fences: tuple
    arguments: bytes
    required_effect: int
    not_before: int
    latest_start: int
    latest_completion: int
    max_run_ms: int
    lease_until: int

    def __post_init__(self):
        _require(type(self.reference) is Reference)
        _uint(self.primitive_id, 16, positive=True)
        _uint(self.resource_mask, 8, positive=True)
        _require(type(self.fences) is tuple and len(self.fences) == self.resource_mask.bit_count())
        for fence in self.fences:
            _uint(fence, 32, positive=True)
        _require(type(self.arguments) is bytes and len(self.arguments) <= MAX_ARGUMENTS)
        _require(type(self.required_effect) is int and self.required_effect in (0, 1))
        for value in (self.not_before, self.latest_start, self.latest_completion, self.lease_until):
            _tick(value)
        _require(self.not_before < self.latest_start <= self.latest_completion <= self.lease_until,
                 'Invalid endpoint timing order')
        _uint(self.max_run_ms, 32, positive=True)
        _require(self.max_run_ms <= MAX_HORIZON, 'Runtime exceeds endpoint profile horizon')

    def payload(self):
        ref = self.reference
        prefix = _OP.pack(VERSION, Opcode.OP, ref.control_generation, ref.context_handle, ref.call_number,
                          ref.intent_digest, self.primitive_id, self.resource_mask, len(self.arguments),
                          self.required_effect, 0, 0, self.not_before, self.latest_start,
                          self.latest_completion, self.max_run_ms, self.lease_until)
        return prefix + b''.join(struct.pack('>I', fence) for fence in self.fences) + self.arguments

    @classmethod
    def parse(cls, payload):
        _require(type(payload) is bytes and 88 <= len(payload) <= 192, 'Invalid OP length')
        v = _OP.unpack_from(payload)
        _require(v[:2] == (VERSION, Opcode.OP) and v[10:12] == (0, 0), 'Invalid OP prefix/reserved bits')
        mask, length = v[7:9]
        end = 88 + 4 * mask.bit_count()
        _require(len(payload) == end + length and length <= MAX_ARGUMENTS, 'Invalid OP variable length')
        fences = tuple(struct.unpack_from('>I', payload, offset)[0] for offset in range(88, end, 4))
        return cls(Reference(*v[2:6]), v[6], mask, fences, payload[end:], v[9], *v[12:17])


def hello():
    return bytes((VERSION, Opcode.HELLO))


def bind(expected_control_generation, context_handle, manifest_digest, context_digest):
    return struct.pack('>BBIH32s32s', VERSION, Opcode.BIND,
                       _uint(expected_control_generation, 32, positive=True), _uint(context_handle, 16, positive=True),
                       _bytes(manifest_digest, 32, nonzero=True), _bytes(context_digest, 32, nonzero=True))


def arm(control_generation, context_handle, context_digest, lease_until):
    return struct.pack('>BBIH32sQ', VERSION, Opcode.ARM,
                       _uint(control_generation, 32, positive=True), _uint(context_handle, 16, positive=True),
                       _bytes(context_digest, 32, nonzero=True), _tick(lease_until))


def revoke(control_generation, context_handle):
    return struct.pack('>BBIHH', VERSION, Opcode.REVOKE,
                       _uint(control_generation, 32, positive=True), _uint(context_handle, 16, positive=True), 6)


@dataclass(frozen=True)
class Request:
    """A syntactically checked exact frame; no admission or current authority claim."""
    frame: Frame

    def __post_init__(self):
        f = self.frame
        _require(type(f) is Frame and f.kind == 1 and type(f.kind) is int and f.channel == 0 and type(f.channel) is int)
        _uint(f.session, 64)
        _uint(f.sequence, 32)
        p = f.payload
        _require(type(p) is bytes and 2 <= len(p) <= 192 and p[0] == VERSION)
        try:
            opcode = Opcode(p[1])
        except ValueError as error:
            raise WireError('Unknown request opcode') from error
        if opcode == Opcode.HELLO:
            _require(len(p) == 2 and f.session == 0, 'HELLO must use discovery session zero')
            return
        _require(f.session > 0 and f.sequence > 0, 'Missing boot/session correlation')
        if opcode == Opcode.OP:
            Operation.parse(p)
        elif opcode in (Opcode.QUERY, Opcode.CANCEL, Opcode.RETIRE):
            _require(len(p) == 44, 'Invalid record-reference length')
            Reference(*_REFERENCE.unpack(p)[2:])
        elif opcode == Opcode.BIND:
            _require(len(p) == 72, 'Invalid BIND length')
            values = struct.unpack('>BBIH32s32s', p)
            _require(bind(*values[2:]) == p)
        elif opcode == Opcode.ARM:
            _require(len(p) == 48, 'Invalid ARM length')
            values = struct.unpack('>BBIH32sQ', p)
            _require(arm(*values[2:]) == p)
        else:
            _require(len(p) == 10, 'Invalid REVOKE length')
            values = struct.unpack('>BBIHH', p)
            _require(revoke(*values[2:4]) == p, 'Reserved revocation reason')

    @property
    def opcode(self):
        return Opcode(self.frame.payload[1])

    @property
    def reference(self):
        if self.opcode == Opcode.OP:
            return Operation.parse(self.frame.payload).reference
        if self.opcode in (Opcode.QUERY, Opcode.CANCEL, Opcode.RETIRE):
            return Reference(*_REFERENCE.unpack(self.frame.payload)[2:])
        return None


@dataclass(frozen=True)
class Refusal:
    opcode: Opcode
    status: Status


@dataclass(frozen=True)
class Control:
    control_generation: int
    context_handle: int
    context_digest: bytes
    state: int
    flags: int
    now: int
    armed_until: int
    call_high_water: int
    held_resources: int


@dataclass(frozen=True)
class Hello:
    boot_epoch: int
    incarnation: bytes
    firmware_digest: bytes
    manifest_digest: bytes
    control: Control
    resource_count: int
    max_arguments: int
    max_result: int
    active_capacity: int
    receipt_capacity: int
    fence_floors: tuple


@dataclass(frozen=True)
class Receipt:
    reference: Reference
    execution: Execution
    cancellation: int
    evidence_kind: int
    verification: int
    held_resources: int
    may_have_acted: bool
    reason: int
    revision: int
    queued_at: int
    started_at: int | None
    terminal_at: int | None
    result: bytes


@dataclass(frozen=True)
class Retired:
    reference: Reference


def _control(value, boot):
    _require(value.control_generation > 0 and value.state <= 4 and value.flags < 128, 'Invalid endpoint state')
    flags = value.flags
    _require(bool(flags & 1) == (boot > 0), 'Boot qualification/session mismatch')
    _require(not (flags & 4 and flags & 8), 'Simulation and physical commissioning conflict')
    _require(value.now != ABSENT_TIME and value.armed_until != ABSENT_TIME)
    _require(bool(value.context_handle) == bool(any(value.context_digest)), 'Incomplete context identity')
    if value.state == 1:
        _require(value.context_handle > 0, 'Bound state is missing its context identity')
    if value.state == 2:
        _require(flags & 1 and flags & 16 and not flags & 34 and flags & 12, 'Unqualified ARMED state')
        _require(value.context_handle > 0 and value.armed_until > value.now, 'Invalid active context lease')
        _require(value.armed_until - value.now <= 60000, 'Context lease exceeds profile horizon')
    else:
        _require(flags & 32, 'Inactive endpoint must inhibit ordinary actuation')
        _require(value.armed_until == 0, 'Inactive context lease must be zero')


def decode_response(frame, request, *, operation=None, simulator_only=None):
    """Validate one response against its exact request and optional retained OP.

    A HELLO remains diagnostic. The caller owns authenticated route selection,
    endpoint sequence/revision continuity, durable retention and evidence policy.
    A Refusal never proves that a previous possibly delivered command did not act.
    """
    _require(type(request) is Request and type(frame) is Frame)
    _require(type(frame.kind) is int and frame.kind == 2 and type(frame.channel) is int and frame.channel == 0)
    _uint(frame.sequence, 32, positive=True)
    _uint(frame.session, 64)
    p = frame.payload
    _require(type(p) is bytes and 7 <= len(p) <= 192, 'Invalid response length')
    _require(p[0] == VERSION and p[1] == (request.opcode | 0x80), 'Response opcode mismatch')
    _require(int.from_bytes(p[2:6], 'big') == request.frame.sequence, 'Response request correlation mismatch')
    if request.opcode != Opcode.HELLO:
        _require(frame.session == request.frame.session, 'Endpoint boot changed; reconcile before reuse')
    try:
        status = Status(p[6])
    except ValueError as error:
        raise WireError('Unknown endpoint status') from error
    if status != Status.OK:
        _require(len(p) == 7, 'Error response must not carry a receipt')
        return Refusal(request.opcode, status)
    if request.opcode == Opcode.HELLO:
        _require(len(p) == 186, 'Invalid HELLO response length')
        v = _HELLO.unpack_from(p, 7)
        control = Control(v[3], v[4], v[5], v[6], v[7], v[13], v[14], v[15], v[16])
        _control(control, frame.session)
        _require(v[8] <= 8 and v[9] <= MAX_ARGUMENTS and v[10] <= MAX_RESULT and v[11:13] == (1, 1))
        _require(control.held_resources < 2**v[8] and all(x == 0 for x in v[17 + v[8]:]))
        return Hello(frame.session, *v[:3], control, *v[8:13], tuple(v[17:]))
    if request.opcode in (Opcode.BIND, Opcode.ARM, Opcode.REVOKE):
        _require(len(p) == 69, 'Invalid control response length')
        result = Control(*_CONTROL.unpack_from(p, 7))
        _control(result, frame.session)
        original = request.frame.payload
        generation, handle = struct.unpack_from('>IH', original, 2)
        expected_generation = generation + (request.opcode != Opcode.ARM)
        _require(result.control_generation == expected_generation and result.context_handle == handle,
                 'Control identity mismatch')
        if request.opcode == Opcode.BIND:
            _require(result.context_digest == original[40:72] and result.state == 1 and result.held_resources == 0)
            _require(result.flags & 17 == 17 and not result.flags & 2, 'BIND succeeded without qualified boot/clock or reconciliation')
        elif request.opcode == Opcode.ARM:
            _require(result.context_digest == original[8:40] and result.state == 2 and
                     result.armed_until >= int.from_bytes(original[40:48], 'big'))
        else:
            _require(result.state in (0, 3))
        return result
    if request.opcode == Opcode.RETIRE:
        _require(len(p) == 7, 'RETIRE acknowledgment has no receipt')
        return Retired(request.reference)
    _require(type(operation) is Operation and type(simulator_only) is bool,
             'A retained operation and installation evidence mode are required')
    _require(request.reference == operation.reference, 'Request does not identify the retained operation')
    if request.opcode == Opcode.OP:
        _require(request.frame.payload == operation.payload(), 'Request differs from retained compact intent')
    _require(86 <= len(p) <= 118, 'Invalid receipt length')
    v = _RECEIPT.unpack_from(p, 7)
    ref = Reference(*v[:4])
    _require(ref == operation.reference, 'Receipt operation identity mismatch')
    try:
        state = Execution(v[4])
    except ValueError as error:
        raise WireError('Invalid execution state') from error
    cancellation, evidence, verification, held, may, reason, revision = v[5:12]
    queued, started, terminal, result_length = v[12:16]
    _require(cancellation <= 4 and evidence <= 5 and verification <= 3 and may <= 1 and reason <= 12 and revision > 0)
    _require(result_length <= MAX_RESULT and len(p) == 86 + result_length)
    _require(not held & ~operation.resource_mask, 'Receipt claims unrelated resources')
    _require(queued < operation.latest_start and (evidence != 0 or result_length == 0),
             'Admission timestamp violates retained window or NONE evidence carries a result')
    _require(verification != 1 or evidence in (3, 4), 'Verification requires qualified measurement evidence')
    _require(not simulator_only or verification != 1 and evidence in (0, 1, 2, 5), 'Simulation cannot claim physical verification')
    _require(simulator_only or evidence != 5, 'Unexpected simulation evidence')
    _require(cancellation != 4 or state == Execution.CANCELED, 'Confirmed cancellation requires canceled execution')
    _require(state != Execution.CANCELED or cancellation == 4)
    times = [t for t in (queued, started, terminal) if t != ABSENT_TIME]
    _require(times == sorted(times), 'Reversed receipt timestamps')
    if not may:
        _require(started == ABSENT_TIME and result_length == 0 and evidence == 0)
    elif started == ABSENT_TIME:
        _require(reason == 7, 'Missing start timestamp without a clock fault')
    if started != ABSENT_TIME:
        _require(operation.not_before <= started < operation.latest_start, 'Start violates retained timing window')
    if state in (Execution.QUEUED, Execution.RUNNING, Execution.OUTCOME_UNKNOWN):
        _require(held == operation.resource_mask and terminal == ABSENT_TIME, 'Active/unknown receipt lost claims or invented terminal time')
    else:
        _require(terminal != ABSENT_TIME or reason == 7, 'Missing terminal timestamp without a clock fault')
    if state in (Execution.QUEUED, Execution.REJECTED_BEFORE_START):
        _require(not may and verification == 0)
    if state == Execution.QUEUED:
        _require(cancellation == 0 and reason == 0)
    if state == Execution.REJECTED_BEFORE_START or state == Execution.CANCELED and not may:
        _require(held == 0, 'Unstarted terminal work retains claims')
    if state in (Execution.RUNNING, Execution.COMPLETED, Execution.OUTCOME_UNKNOWN):
        _require(may == 1)
    if state == Execution.COMPLETED:
        _require(evidence != 0, 'Completion lacks installed evidence')
        _require(started != ABSENT_TIME and terminal != ABSENT_TIME and
                 terminal < min(operation.latest_completion, operation.lease_until) and
                 terminal - started < operation.max_run_ms,
                 'Completion lacks known timestamps within retained exclusive cutoffs')
        if operation.required_effect == 1:
            # A later contradiction preserves terminal execution and marks the
            # previously qualified evidence DISPUTED. Expose that uncertainty;
            # it is not a new successful verification or permission to retire.
            _require(evidence in (3, 4) and verification in (1, 3),
                     'Required physical effect lacks qualified or disputed measurement evidence')
    return Receipt(ref, state, cancellation, evidence, verification, held, bool(may), reason, revision,
                   queued, None if started == ABSENT_TIME else started,
                   None if terminal == ABSENT_TIME else terminal, p[86:])
