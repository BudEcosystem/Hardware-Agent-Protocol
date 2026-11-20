"""Exact standing-single version-2 payload codec over original serial Frame.

Pure encoding/validation only: no I/O, enrollment, authentication, persistence,
clock conversion, evidence promotion, retry policy, or authority decisions.
Pages are independent samples. Raw canonical bytes remain available to a host
which owns durable collection, request continuity, and installation admission.
"""
from dataclasses import dataclass
from enum import IntEnum
import struct

from protocol.serial.frame import Frame

VERSION = 2
PREFIX_SIZE = 66
STATE_SIZE = 124
MAX_RESPONSE = 190
ABSENT_TIME = (1 << 64) - 1


class WireError(ValueError):
    """Invalid or uncorrelated packet; never establishes absence of effects."""


class Opcode(IntEnum):
    DESCRIBE = 0x01
    BIND = 0x10
    REVOKE = 0x12
    OPEN = 0x40
    START = 0x41
    RENEW = 0x42
    STATUS = 0x43
    ACK = 0x44
    ACKNOWLEDGE = 0x44
    SUSPEND = 0x45
    RESUME = 0x46
    STOP = 0x47
    RETIRE = 0x48


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
    BAD_REVISION = 23
    ACK_PENDING = 24
    BAD_PAGE = 25
    SOURCE_INVALID = 26


class Lifecycle(IntEnum):
    NONE = 0
    PREPARED = 1
    ACTIVE = 2
    DRAINING = 3
    SUSPENDED_QUIESCENT = 4
    STOPPED_QUIESCENT = 5
    FAULT_UNKNOWN = 6


_MUTATIONS = frozenset((Opcode.START, Opcode.RENEW, Opcode.ACK, Opcode.SUSPEND,
                        Opcode.RESUME, Opcode.STOP, Opcode.RETIRE))
_REFERENCE = struct.Struct('>BBIHI32s')
_CONFIGURATION = struct.Struct('>4i6H4B')
_PREFIX = struct.Struct('>BBIBBIHI32s4I')


def _require(condition, message='Invalid standing packet'):
    if not condition:
        raise WireError(message)


def _uint(value, bits, *, positive=False):
    _require(type(value) is int and int(positive) <= value < (1 << bits),
             'Invalid unsigned standing integer')
    return value


def _bytes(value, length, *, nonzero=False):
    _require(type(value) is bytes and len(value) == length and (not nonzero or any(value)),
             'Invalid standing byte field')
    return value


def _tick(value):
    _uint(value, 64)
    _require(value != ABSENT_TIME, 'Absent-time sentinel is not a deadline')
    return value


def _opcode(value):
    _require(type(value) in (int, Opcode), 'Invalid opcode type')
    try:
        return Opcode(value)
    except ValueError as error:
        raise WireError('Unknown standing opcode') from error


def _u16(data, at):
    return int.from_bytes(data[at:at + 2], 'big')


def _u32(data, at):
    return int.from_bytes(data[at:at + 4], 'big')


def _u64(data, at):
    return int.from_bytes(data[at:at + 8], 'big')


def _i32(data, at):
    return int.from_bytes(data[at:at + 4], 'big', signed=True)


@dataclass(frozen=True)
class Reference:
    generation: int
    handle: int
    standing_number: int
    intent_digest: bytes

    def __post_init__(self):
        _uint(self.generation, 32, positive=True)
        _uint(self.handle, 16, positive=True)
        _uint(self.standing_number, 32, positive=True)
        _bytes(self.intent_digest, 32, nonzero=True)

    def payload(self, opcode):
        op = _opcode(opcode)
        _require(op == Opcode.OPEN or op == Opcode.STATUS or op in _MUTATIONS,
                 'Expected standing record opcode')
        return _REFERENCE.pack(VERSION, op, self.generation, self.handle,
                               self.standing_number, self.intent_digest)

    @classmethod
    def parse(cls, payload):
        _require(type(payload) is bytes and len(payload) >= 44 and payload[0] == VERSION)
        op = _opcode(payload[1])
        _require(op == Opcode.OPEN or op == Opcode.STATUS or op in _MUTATIONS)
        return cls(*_REFERENCE.unpack_from(payload)[2:])


# Lower-case constructor is convenient for callers assembling durable packets.
def reference(generation, handle, standing_number, intent_digest):
    return Reference(generation, handle, standing_number, intent_digest)


@dataclass(frozen=True)
class Configuration:
    lower_demand: int
    upper_demand: int
    required_improvement: int
    minimum_on_feedback: int
    sample_period: int
    demand_max_age: int
    feedback_max_age: int
    minimum_on_dwell: int
    minimum_off_dwell: int
    feedback_window: int
    off_code: int = 0
    on_code: int = 1
    loss_code: int = 0
    policy: int = 0

    def __post_init__(self):
        for value in (self.lower_demand, self.upper_demand, self.required_improvement, self.minimum_on_feedback):
            _require(type(value) is int and -(1 << 31) <= value < (1 << 31), 'Invalid signed configuration value')
        _require(-100000 <= self.lower_demand < self.upper_demand <= 200000)
        _require(0 <= self.required_improvement <= 300000 and 0 < self.minimum_on_feedback <= 100000)
        for value in (self.sample_period, self.demand_max_age, self.feedback_max_age, self.feedback_window):
            _uint(value, 16, positive=True)
            _require(value <= 60000)
        for value in (self.minimum_on_dwell, self.minimum_off_dwell):
            _uint(value, 16)
            _require(value <= 60000)
        _require(self.sample_period < min(self.demand_max_age, self.feedback_max_age, self.feedback_window))
        for value in (self.off_code, self.on_code, self.loss_code, self.policy):
            _uint(value, 8)
        _require((self.off_code, self.on_code, self.loss_code, self.policy) == (0, 1, 0, 0),
                 'Unsupported installed output/loss policy')

    def payload(self):
        return _CONFIGURATION.pack(self.lower_demand, self.upper_demand, self.required_improvement,
                                   self.minimum_on_feedback, self.sample_period, self.demand_max_age,
                                   self.feedback_max_age, self.minimum_on_dwell, self.minimum_off_dwell,
                                   self.feedback_window, self.off_code, self.on_code, self.loss_code, self.policy)

    @classmethod
    def parse(cls, payload):
        return cls(*_CONFIGURATION.unpack(_bytes(payload, 32)))


@dataclass(frozen=True)
class Open:
    reference: Reference
    configuration: Configuration
    resource_mask: int
    fences: tuple
    lease_until: int
    activation_cap: int
    demand_epoch: int
    feedback_epoch: int
    evidence_mode: int = 0
    kernel_id: int = 1
    outage_policy: int = 0

    def __post_init__(self):
        _require(type(self.reference) is Reference and type(self.configuration) is Configuration)
        _uint(self.resource_mask, 8, positive=True)
        _require(type(self.fences) is tuple and len(self.fences) == 8, 'Eight canonical fence entries required')
        for index, fence in enumerate(self.fences):
            _uint(fence, 32)
            _require(bool(fence) == bool(self.resource_mask & (1 << index)), 'Unused fences must be zero; used fences positive')
        _tick(self.lease_until)
        _uint(self.activation_cap, 32, positive=True)
        _uint(self.demand_epoch, 32, positive=True)
        _uint(self.feedback_epoch, 32, positive=True)
        _uint(self.evidence_mode, 8)
        _uint(self.kernel_id, 16)
        _uint(self.outage_policy, 8)
        _require(self.evidence_mode <= 1 and self.kernel_id == 1 and self.outage_policy == 0,
                 'Unsupported standing profile')

    def payload(self):
        return (self.reference.payload(Opcode.OPEN) + struct.pack('>HB', self.kernel_id, 32) +
                self.configuration.payload() + struct.pack('>B8IQBBIII', self.resource_mask, *self.fences,
                    self.lease_until, self.outage_policy, self.evidence_mode, self.activation_cap,
                    self.demand_epoch, self.feedback_epoch))

    @classmethod
    def parse(cls, payload):
        _bytes(payload, 134)
        _require(payload[:2] == bytes((VERSION, Opcode.OPEN)) and payload[46] == 32)
        return cls(Reference.parse(payload), Configuration.parse(payload[47:79]), payload[79],
                   tuple(_u32(payload, 80 + 4 * i) for i in range(8)), _u64(payload, 112),
                   _u32(payload, 122), _u32(payload, 126), _u32(payload, 130),
                   payload[121], _u16(payload, 44), payload[120])


def open_payload(*args, **kwargs):
    return Open(*args, **kwargs).payload()


def describe(page=0):
    _uint(page, 8)
    _require(page <= 1, 'Invalid descriptor page')
    return bytes((VERSION, Opcode.DESCRIBE, page))


def bind(generation, handle, manifest_digest, context_digest):
    return struct.pack('>BBIH32s32s', VERSION, Opcode.BIND,
                       _uint(generation, 32, positive=True), _uint(handle, 16, positive=True),
                       _bytes(manifest_digest, 32, nonzero=True), _bytes(context_digest, 32, nonzero=True))


def revoke(generation, handle):
    return struct.pack('>BBIHH', VERSION, Opcode.REVOKE,
                       _uint(generation, 32, positive=True), _uint(handle, 16, positive=True), 6)


def status(ref, page=0, cursor=0):
    _require(type(ref) is Reference)
    _uint(page, 8)
    _uint(cursor, 32)
    _require(page <= 2 and ((page == 2 and cursor > 0) or (page != 2 and cursor == 0)),
             'Invalid status page/cursor')
    return ref.payload(Opcode.STATUS) + struct.pack('>BI', page, cursor)


def mutation(ref, opcode, mutation_sequence, expected_revision, *, lease_until=0, ack_watermark=0, reason=0):
    _require(type(ref) is Reference)
    op = _opcode(opcode)
    _require(op in _MUTATIONS, 'Expected lifecycle mutation')
    _uint(mutation_sequence, 32, positive=True)
    _uint(expected_revision, 32, positive=True)
    _uint(lease_until, 64)
    _uint(ack_watermark, 32)
    _uint(reason, 16)
    if op in (Opcode.RENEW, Opcode.RESUME):
        _tick(lease_until)
    else:
        _require(lease_until == 0, 'Reserved mutation lease')
    _require(op in (Opcode.ACK, Opcode.RETIRE) or ack_watermark == 0, 'Reserved mutation ACK')
    _require(reason == {Opcode.SUSPEND: 2, Opcode.STOP: 1}.get(op, 0), 'Invalid mutation reason')
    return ref.payload(op) + struct.pack('>IIQIH', mutation_sequence, expected_revision, lease_until, ack_watermark, reason)


@dataclass(frozen=True)
class Request:
    frame: Frame

    def __post_init__(self):
        f = self.frame
        _require(type(f) is Frame and type(f.kind) is int and f.kind == 1 and type(f.channel) is int and f.channel == 0)
        _uint(f.session, 64)
        _uint(f.sequence, 32)
        p = f.payload
        _require(type(p) is bytes and 2 <= len(p) <= 192 and p[0] == VERSION)
        op = _opcode(p[1])
        if op == Opcode.DESCRIBE:
            _require(len(p) == 3 and f.session == 0 and describe(p[2]) == p, 'Invalid discovery request')
            return
        _require(f.session > 0 and f.sequence > 0, 'Missing qualified boot/request correlation')
        if op == Opcode.OPEN:
            Open.parse(p)
        elif op == Opcode.BIND:
            _require(len(p) == 72, 'Invalid BIND length')
            _require(bind(_u32(p, 2), _u16(p, 6), p[8:40], p[40:72]) == p)
        elif op == Opcode.REVOKE:
            _require(len(p) == 10, 'Invalid REVOKE length')
            _require(revoke(_u32(p, 2), _u16(p, 6)) == p)
        elif op == Opcode.STATUS:
            _require(len(p) == 49, 'Invalid STATUS length')
            _require(status(Reference.parse(p), p[44], _u32(p, 45)) == p)
        else:
            _require(len(p) == 66, 'Invalid mutation length')
            _require(mutation(Reference.parse(p), op, _u32(p, 44), _u32(p, 48),
                              lease_until=_u64(p, 52), ack_watermark=_u32(p, 60), reason=_u16(p, 64)) == p)

    @property
    def opcode(self):
        return Opcode(self.frame.payload[1])

    @property
    def reference(self):
        return Reference.parse(self.frame.payload) if self.opcode >= Opcode.OPEN else None


def _decode_prefix(p):
    values = _PREFIX.unpack(p[:PREFIX_SIZE])
    names = ('version', 'response_opcode', 'request_sequence', 'status', 'page', 'generation',
             'handle', 'standing_number', 'intent_digest', 'revision', 'mutation_sequence',
             'activation_high_water', 'ack_watermark')
    result = dict(zip(names, values))
    _require(result['status'] in Status._value2member_map_, 'Unknown response status')
    identity = (result['generation'], result['handle'], result['standing_number'], any(result['intent_digest']))
    _require(all(identity) or not any(identity), 'Partial record identity')
    _require(result['ack_watermark'] <= result['activation_high_water'], 'ACK exceeds activation high-water')
    if not any(identity):
        _require(not any(values[9:]), 'Counters without record identity')
    if result['revision'] == 0:
        _require(result['mutation_sequence'] == 0 and result['activation_high_water'] == 0 and result['ack_watermark'] == 0,
                 'Absent record retains live counters')
    return result


def _decode_capabilities(b, session):
    result = {'generation': _u32(b, 0), 'handle': _u16(b, 4), 'context_digest': b[6:38],
              'now': _u64(b, 38), 'platform_flags': _u16(b, 46), 'common_state': b[48],
              'resource_count': b[49], 'slot_kind': b[50], 'installed_mask': b[51],
              'kernel_id': _u16(b, 52), 'input_count': b[54], 'ledger_capacity': b[55],
              'config_size': b[56], 'feature_bits': b[57], 'maximum_lease': _u32(b, 58),
              'maximum_on_ms': _u32(b, 62), 'cleanup_budget': _u16(b, 66),
              'epochs': (_u32(b, 68), _u32(b, 72)), 'standing_high_water': _u32(b, 76),
              'finite_high_water': _u32(b, 80), 'fence_floors': tuple(_u32(b, 84 + 4 * i) for i in range(8)), 'raw': b}
    f = result['platform_flags']
    _require(result['generation'] > 0 and result['now'] != ABSENT_TIME and f < 128 and b[48] <= 4)
    _require(bool(f & 1) == bool(session) and not (f & 4 and f & 8), 'Invalid platform qualification encoding')
    _require(bool(result['handle']) == bool(any(result['context_digest'])), 'Partial common context')
    _require(1 <= b[49] <= 8 and b[50] <= 2 and 0 < b[51] < (1 << b[49]))
    _require(result['kernel_id'] == 1 and b[54:58] == bytes((2, 2, 32, 1)), 'Unsupported standing capabilities')
    _require(0 < result['maximum_lease'] <= 60000 and result['maximum_on_ms'] > 0 and 0 < result['cleanup_budget'] <= 60000)
    _require(all(value == 0 for value in result['fence_floors'][b[49]:]), 'Unused capability fences nonzero')
    return result


def _decode_witness(b, valid):
    result = {'valid': valid, 'source_index': b[0], 'quality': b[1], 'evidence': b[2], 'verification': b[3],
              'source_sequence': _u32(b, 4), 'acquired_at': _u64(b, 8), 'value': _i32(b, 16),
              'settled_output': b[20], 'raw': b}
    _require(b[21] == 0 and b[0] <= 1 and b[1] <= 1 and b[2] <= 5 and b[3] <= 3 and b[20] <= 1,
             'Invalid aggregate witness encoding')
    if valid:
        _require(b[0:2] == bytes((1, 1)) and result['source_sequence'] > 0 and result['acquired_at'] != ABSENT_TIME)
        _require(result['value'] == 0 and b[20] == 0 and (b[2], b[3]) in ((5, 0), (4, 1)),
                 'Invalid installed aggregate witness')
    else:
        # A source counter overflow after a loss sample can leave candidate
        # bytes present while WITNESS_VALID stays clear. Expose without approval.
        _require((b[2], b[3]) in ((0, 0), (5, 0), (4, 1)))
    return result


def _decode_state(b, prefix):
    result = {'slot_kind': b[0], 'revision': _u32(b, 1), 'mutation_sequence': _u32(b, 5),
              'last_comparison': b[9:29], 'lease_until': _u64(b, 29), 'activation_high_water': _u32(b, 37),
              'ack_watermark': _u32(b, 41), 'next_service_tick': _u64(b, 45), 'first_loss_tick': _u64(b, 53),
              'cleanup_deadline': _u64(b, 61), 'quiescence_tick': _u64(b, 69), 'epochs': (_u32(b, 77), _u32(b, 81)),
              'accounted_on_ms': _u32(b, 85), 'lifecycle': b[89], 'drain_target': b[90], 'service_phase': b[91],
              'owned_mask': b[92], 'quiescent_mask': b[93], 'loss_reason': _u16(b, 94), 'flags': _u16(b, 96),
              'ledger_head': b[98], 'ledger_count': b[99], 'pending_slot': b[100], 'loss_command': b[101], 'raw': b}
    _require(b[0] == 2 and result['revision'] > 0 and all(result[key] == prefix[key] for key in
             ('revision', 'mutation_sequence', 'activation_high_water', 'ack_watermark')), 'State/prefix counters disagree')
    _require(1 <= b[89] <= 6 and b[90] in (0, 4, 5, 6) and b[91] <= 2 and b[92] > 0 and not b[93] & ~b[92])
    _require(result['flags'] < (1 << 13) and result['loss_reason'] <= 16 and b[98] <= 1 and b[99] <= 2 and
             b[100] in (0, 1, 255) and b[101] <= 4, 'Invalid state enum/reserved fields')
    _require(result['activation_high_water'] - result['ack_watermark'] == b[99], 'Ledger count/high-water mismatch')
    _require(result['lease_until'] != ABSENT_TIME and all(result['epochs']), 'Invalid retained lease/epochs')
    comparison = result['last_comparison']
    if result['mutation_sequence'] == 0:
        _require(not any(comparison), 'Unexpected retained mutation comparison')
    else:
        _require(comparison[0] == VERSION and comparison[1] in _MUTATIONS and _u32(comparison, 2) > 0,
                 'Invalid retained mutation comparison')
        _require(_u32(comparison, 2) < result['revision'], 'Retained comparison revision did not advance')
        # Validate the comparison using the same canonical typed body rules.
        mutation(Reference(prefix['generation'], prefix['handle'], prefix['standing_number'], prefix['intent_digest']),
                 comparison[1], result['mutation_sequence'], _u32(comparison, 2), lease_until=_u64(comparison, 6),
                 ack_watermark=_u32(comparison, 14), reason=_u16(comparison, 18))
    valid = bool(result['flags'] & 128)
    witness = _decode_witness(b[102:124], valid)
    result['witness'] = witness
    if valid:
        _require(result['quiescence_tick'] != ABSENT_TIME and result['quiescence_tick'] >= witness['acquired_at'] and
                 result['quiescent_mask'] == result['owned_mask'] and result['loss_command'] == 3,
                 'Incomplete aggregate settlement encoding')
    else:
        _require(result['quiescence_tick'] == ABSENT_TIME, 'Private handoff tick exposed as quiescence')
    return result


def _decode_observation(b, channel):
    result = {'value': _i32(b, 0), 'acquired_at': _u64(b, 4), 'source_sequence': _u32(b, 12),
              'source_epoch': _u32(b, 16), 'quality': b[20], 'continuity': b[21], 'pending_evaluation': b[22], 'raw': b}
    _require(b[23] == 0 and b[20] <= 1 and b[21] <= 1 and b[22] <= 1, 'Invalid observation fields')
    if b[20] == 0:
        _require(not any(b), 'Absent observation is not canonical zero')
    else:
        _require(b[21] == 1 and result['source_sequence'] > 0 and result['source_epoch'] > 0 and result['acquired_at'] != ABSENT_TIME)
        lower, upper = (-100000, 200000) if channel == 0 else (0, 100000)
        _require(lower <= result['value'] <= upper, 'Out-of-range observation')
    return result


def _decode_activation(b, cursor, prefix):
    state, verification, evidence = b[40] & 7, (b[40] >> 4) & 3, b[41] & 7
    result = {'activation_id': _u32(b, 0), 'dispatch_tick': _u64(b, 4), 'demand_sequence': _u32(b, 12),
              'demand_value': _i32(b, 16), 'demand_age': _u16(b, 20), 'feedback_sequence': _u32(b, 22),
              'feedback_acquired_at': _u64(b, 26), 'feedback_value': _i32(b, 34), 'previous_output': b[38],
              'requested_output': b[39], 'state_flags': b[40], 'evidence_quality': b[41], 'state': state,
              'possibly_acted': bool(b[40] & 8), 'verification': verification, 'evidence': evidence,
              'good_quality': bool(b[41] & 8), 'reason': _u16(b, 42), 'raw': b}
    _require(result['activation_id'] == cursor and prefix['ack_watermark'] < cursor <= prefix['activation_high_water'])
    _require(b[40] < 64 and b[41] < 16 and 1 <= state <= 5 and evidence <= 5 and b[38] <= 1 and b[39] <= 1)
    _require(b[38] != b[39] and result['possibly_acted'] and result['reason'] <= 16 and
             result['dispatch_tick'] != ABSENT_TIME and result['demand_sequence'] > 0 and result['feedback_sequence'] > 0)
    _require(-100000 <= result['demand_value'] <= 200000 and result['demand_age'] < 60000)
    if result['feedback_acquired_at'] == ABSENT_TIME:
        _require(b[41] == 0 and result['feedback_value'] == 0 and verification == 0,
                 'Pre-dispatch source floor is not feedback evidence')
    else:
        _require(result['feedback_acquired_at'] > result['dispatch_tick'] and result['good_quality'] and
                 evidence in (4, 5) and 0 <= result['feedback_value'] <= 100000,
                 'Invalid post-dispatch feedback evidence')
    _require(verification != 1 or (state == 2 and evidence == 4), 'Invalid physical verification claim')
    _require(evidence != 5 or verification == 0, 'Simulation cannot claim physical verification')
    if state == 2:
        _require(result['feedback_acquired_at'] != ABSENT_TIME and result['reason'] == 0)
    if state in (1, 4, 5):
        _require(verification == 0)
    return result


def decode_response(frame, request):
    """Return structured canonical bytes and typed fields for one exact request.

    Correlation and encoding are checked here. Frame sequence continuity, page
    continuity, installation evidence policy and durable ACK eligibility belong
    to the host. A decoded refusal can describe another occupied record; it is
    never proof that the requested operation had no prior effect.
    """
    _require(type(frame) is Frame and type(request) is Request)
    _require(type(frame.kind) is int and frame.kind == 2 and type(frame.channel) is int and frame.channel == 0)
    _uint(frame.session, 64)
    _uint(frame.sequence, 32, positive=True)
    p = frame.payload
    _require(type(p) is bytes and PREFIX_SIZE <= len(p) <= MAX_RESPONSE, 'Invalid standing response length')
    prefix = _decode_prefix(p)
    op = request.opcode
    _require(p[0] == VERSION and p[1] == (int(op) | 0x80) and prefix['request_sequence'] == request.frame.sequence,
             'Response request correlation mismatch')
    if op != Opcode.DESCRIBE:
        _require(frame.session == request.frame.session, 'Boot changed; reconcile before reuse')
    b = p[PREFIX_SIZE:]
    result = {'opcode': int(op), 'status': prefix['status'], 'page': prefix['page'], 'prefix': prefix,
              'raw_prefix': p[:PREFIX_SIZE], 'raw_body': b, 'raw': p, 'session': frame.session,
              'response_sequence': frame.sequence}
    if prefix['status'] != Status.OK:
        _require(prefix['page'] == 255 and not b, 'Refusal must have no body')
        return result
    ref = request.reference
    if ref is not None:
        _require((prefix['generation'], prefix['handle'], prefix['standing_number'], prefix['intent_digest']) ==
                 (ref.generation, ref.handle, ref.standing_number, ref.intent_digest), 'Successful response identity mismatch')
    page = prefix['page']
    if op == Opcode.RETIRE:
        _require(page == 255 and not b and prefix['revision'] == 0, 'Invalid RETIRE acknowledgment')
        return result
    descriptor = op in (Opcode.DESCRIBE, Opcode.BIND) or (op == Opcode.REVOKE and page == 1)
    if descriptor:
        expected_page = request.frame.payload[2] if op == Opcode.DESCRIBE else 1
        _require(page == expected_page and len(b) == (80 if page == 0 else 116), 'Invalid descriptor page/length')
        if page == 0:
            result['identity'] = {'incarnation': b[:16], 'firmware_digest': b[16:48], 'manifest_digest': b[48:80], 'raw': b}
        else:
            caps = _decode_capabilities(b, frame.session)
            result['capabilities'] = caps
            if op in (Opcode.BIND, Opcode.REVOKE):
                _require(caps['generation'] == _u32(request.frame.payload, 2) + 1 and
                         caps['handle'] == _u16(request.frame.payload, 6), 'Common authority response mismatch')
            if op == Opcode.BIND:
                _require(caps['context_digest'] == request.frame.payload[40:72] and caps['slot_kind'] == 0 and caps['common_state'] == 1)
        return result
    expected_page = request.frame.payload[44] if op == Opcode.STATUS else 0
    _require(page == expected_page and len(b) == {0: 124, 1: 48, 2: 44}[expected_page], 'Invalid state page/length')
    _require(prefix['revision'] > 0, 'Record page without live revision')
    if page == 0:
        result['state'] = _decode_state(b, prefix)
        result['witness'] = result['state']['witness']
    elif page == 1:
        result['observations'] = tuple(_decode_observation(b[i * 24:(i + 1) * 24], i) for i in range(2))
    else:
        result['activation'] = _decode_activation(b, _u32(request.frame.payload, 45), prefix)
    return result
