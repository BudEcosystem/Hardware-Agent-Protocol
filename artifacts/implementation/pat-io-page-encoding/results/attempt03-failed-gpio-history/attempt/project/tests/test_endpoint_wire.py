"""Independent retained-vector and contradictory receipt probes; no physical I/O."""
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import struct
import unittest

from hms.endpoint_wire import (ABSENT_TIME, MAX_HORIZON, Control, Execution, Hello, Opcode,
                               Operation, Receipt, Reference, Refusal, Request, Retired,
                               Status, WireError, arm, bind, decode_response, hello, revoke)
from protocol.serial.frame import Decoder, Frame, encode

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / 'protocol/endpoint/vectors.json').read_text())
FRAMES = {v['name']: Frame(**v['frame'], payload=bytes.fromhex(v['payload_hex']))
          for v in VECTORS['wireVectors']}
OP = Operation.parse(FRAMES['op_scaled_pair'].payload)


def changed(frame, offset, value):
    """Mutate bytes by published offsets, independently of production structs."""
    payload = bytearray(frame.payload)
    value = bytes([value]) if isinstance(value, int) else value
    payload[offset:offset + len(value)] = value
    return replace(frame, payload=bytes(payload))


def response_request(frame, name='query_request'):
    return Request(replace(FRAMES[name], sequence=int.from_bytes(frame.payload[2:6], 'big')))


class EndpointPackets(unittest.TestCase):
    def decode(self, frame, request=None, operation=OP, simulator_only=True):
        return decode_response(frame, request or response_request(frame),
                               operation=operation, simulator_only=simulator_only)

    def test_all_retained_frames_cross_independent_framing_fixture(self):
        for vector in VECTORS['wireVectors']:
            with self.subTest(name=vector['name']):
                frame = FRAMES[vector['name']]
                self.assertEqual(encode(frame).hex(), vector['encoded_frame_hex'])
                decoder = Decoder()
                events = [event for byte in bytes.fromhex(vector['encoded_frame_hex'])
                          if (event := decoder.feed(byte))]
                self.assertEqual(events, [('frame', frame)])

    def test_retained_request_encodings_and_maximum_payload(self):
        self.assertEqual(hello(), FRAMES['hello_request'].payload)
        self.assertEqual(bind(1, 7, bytes.fromhex(VECTORS['fixtureDigests']['installedManifest']),
                              bytes.fromhex(VECTORS['fixtureDigests']['hostContext'])), FRAMES['bind_request'].payload)
        self.assertEqual(arm(2, 7, bytes.fromhex(VECTORS['fixtureDigests']['hostContext']), 2000), FRAMES['arm_request'].payload)
        self.assertEqual(revoke(2, 7), FRAMES['revoke_request'].payload)
        for name, opcode in [('query_request', Opcode.QUERY), ('cancel_request', Opcode.CANCEL),
                             ('retire_request', Opcode.RETIRE)]:
            self.assertEqual(OP.reference.payload(opcode), FRAMES[name].payload)
        for name in ('op_scaled_pair', 'op_maximum_192_bytes'):
            payload = FRAMES[name].payload
            self.assertEqual(Operation.parse(payload).payload(), payload)
            self.assertEqual(Request(FRAMES[name]).reference, Operation.parse(payload).reference)
        self.assertEqual(OP.fences, (5, 9))
        self.assertEqual(struct.unpack('>ii', OP.arguments), (1000, -25))
        with self.assertRaises(FrozenInstanceError):
            OP.max_run_ms = 1

    def test_all_request_prefix_truncations_and_extra_bytes_rejected(self):
        for name in ('hello_request', 'bind_request', 'arm_request', 'revoke_request',
                     'op_scaled_pair', 'op_maximum_192_bytes', 'query_request', 'cancel_request', 'retire_request'):
            frame = FRAMES[name]
            Request(frame)
            for size in range(len(frame.payload)):
                with self.subTest(name=name, prefix=size), self.assertRaises(WireError):
                    Request(replace(frame, payload=frame.payload[:size]))
            with self.subTest(name=name, extra=True), self.assertRaises(WireError):
                Request(replace(frame, payload=frame.payload + b'\x00'))

    def test_syntax_failure_is_separate_from_endpoint_eligibility(self):
        malformed = ('op_truncated', 'op_trailing_byte', 'op_argument_length_over_72',
                     'op_reserved_flags', 'op_reserved_word', 'op_zero_call', 'op_invalid_window')
        for name in malformed:
            with self.subTest(name=name), self.assertRaises(WireError):
                Request(FRAMES[name])
        # A codec cannot authenticate a boot or know current slots/floors/leases,
        # installed arguments, commissioning, or whether a prior copy acted.
        eligible_elsewhere = ('op_stale_boot', 'op_unknown_primitive',
                             'op_required_physical_verification_in_simulation',
                             'op_same_digest_changed_arguments', 'op_older_call_after_retirement',
                             'op_new_call_before_terminal_receipt_retired', 'op_stale_resource_fence',
                             'op_start_at_exclusive_deadline', 'op_stale_deadline_after_32_bit_hardware_wrap',
                             'op_operation_lease_past_context_lease', 'op_old_control_after_revoke')
        for name in eligible_elsewhere:
            with self.subTest(name=name):
                Request(FRAMES[name])

    def test_integer_type_bounds_and_exact_u64_are_not_json_numbers(self):
        for value in (True, 1.0, -1, 0, 2**32):
            with self.subTest(value=value), self.assertRaises(WireError):
                replace(OP.reference, call_number=value)
        for field, values in {
                'primitive_id': (0, 2**16, True), 'resource_mask': (0, 256, False),
                'max_run_ms': (0, MAX_HORIZON + 1, 1.0), 'required_effect': (2, True),
                'arguments': (bytearray(8), bytes(73)), 'fences': ([5, 9], (5,), (0, 9), (5, 2**32)),
                'not_before': (ABSENT_TIME, -1, 1100.0)}.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(WireError):
                    replace(OP, **{field: value})
        for opcode in (33.0, True, Opcode.OP):
            with self.assertRaises(WireError):
                OP.reference.payload(opcode)
        high = replace(OP, not_before=2**63 + 1, latest_start=2**63 + 2,
                       latest_completion=2**63 + 3, lease_until=ABSENT_TIME - 1)
        self.assertEqual(Operation.parse(high.payload()), high)
        for transform in (lambda f: replace(f, sequence=True), lambda f: replace(f, session=42.0),
                          lambda f: replace(f, session=0), lambda f: replace(f, channel=1),
                          lambda f: replace(f, kind=True), lambda f: replace(f, sequence=0)):
            with self.assertRaises(WireError):
                Request(transform(FRAMES['op_scaled_pair']))

    def test_control_fields_reserved_bits_and_nonzero_bind_tags(self):
        for name, offset, value in [('bind_request', 2, bytes(4)), ('bind_request', 6, bytes(2)),
                                    ('bind_request', 8, bytes(32)), ('bind_request', 40, bytes(32)),
                                    ('arm_request', 40, ABSENT_TIME.to_bytes(8, 'big')),
                                    ('revoke_request', 8, b'\x00\x05')]:
            with self.subTest(name=name, offset=offset), self.assertRaises(WireError):
                Request(changed(FRAMES[name], offset, value))

    def test_valid_control_and_diagnostic_responses(self):
        discovery = decode_response(FRAMES['hello_qualified_synthetic_response'], Request(FRAMES['hello_request']))
        self.assertIsInstance(discovery, Hello)
        self.assertEqual((discovery.boot_epoch, discovery.control.flags, discovery.resource_count), (42, 57, 8))
        self.assertEqual(discovery.fence_floors, (0,) * 8)
        for request, response, state in [('bind_request', 'bind_success', 1), ('arm_request', 'arm_success', 2),
                                        ('revoke_request', 'revoke_success', 0)]:
            result = decode_response(FRAMES[response], Request(FRAMES[request]))
            self.assertIsInstance(result, Control)
            self.assertEqual(result.state, state)
        self.assertIsInstance(decode_response(FRAMES['retire_success'], Request(FRAMES['retire_request'])), Retired)
        # An unqualified HELLO is diagnostic, never an implicit authority token.
        frame = changed(FRAMES['hello_qualified_synthetic_response'], 126, b'\x00\x38')
        result = decode_response(replace(frame, session=0), Request(FRAMES['hello_request']))
        self.assertEqual(result.boot_epoch, 0)

    def test_refusals_cannot_smuggle_results_or_erase_prior_outcome(self):
        frame = FRAMES['old_or_forgotten_response']
        request = Request(FRAMES['query_after_retirement'])
        for status in list(Status)[1:]:
            refusal = decode_response(changed(frame, 6, status), request)
            self.assertEqual(refusal, Refusal(Opcode.QUERY, status))
            self.assertFalse(hasattr(refusal, 'may_have_acted'))
        for malformed in (changed(frame, 6, 23), replace(frame, payload=frame.payload + b'\x00')):
            with self.assertRaises(WireError):
                decode_response(malformed, request)

    def test_correlations_checked_before_receipt_interpretation(self):
        frame, request = FRAMES['queued_receipt'], Request(FRAMES['op_scaled_pair'])
        mutations = [replace(frame, kind=1), replace(frame, channel=1), replace(frame, sequence=0),
                     replace(frame, sequence=True), replace(frame, session=43), changed(frame, 0, 2),
                     changed(frame, 1, 0xa1), changed(frame, 2, struct.pack('>I', 4)),
                     changed(frame, 7, struct.pack('>I', 3)), changed(frame, 11, b'\x00\x08'),
                     changed(frame, 13, struct.pack('>I', 2)), changed(frame, 17, bytes(32))]
        for malformed in mutations:
            with self.subTest(frame=malformed), self.assertRaises(WireError):
                self.decode(malformed, request)
        with self.assertRaises(WireError):
            self.decode(frame, request, operation=replace(OP, arguments=bytes(8)))
        for kwargs in ({}, {'operation': OP}, {'operation': OP, 'simulator_only': 1}):
            with self.assertRaises(WireError):
                decode_response(frame, request, **kwargs)
        # A new boot's refusal still cannot be interpreted as an old call's outcome.
        mismatch = replace(frame, session=43, payload=frame.payload[:6] + bytes([Status.BOOT_MISMATCH]))
        with self.assertRaises(WireError):
            self.decode(mismatch, request)

    def test_success_response_lengths_are_exact(self):
        pairs = [('hello_request', 'hello_qualified_synthetic_response'), ('bind_request', 'bind_success'),
                 ('arm_request', 'arm_success'), ('revoke_request', 'revoke_success'),
                 ('op_scaled_pair', 'queued_receipt'), ('retire_request', 'retire_success')]
        for req_name, resp_name in pairs:
            frame, request = FRAMES[resp_name], Request(FRAMES[req_name])
            for size in range(len(frame.payload)):
                with self.subTest(response=resp_name, prefix=size), self.assertRaises(WireError):
                    self.decode(replace(frame, payload=frame.payload[:size]), request)
            with self.subTest(response=resp_name, extra=True), self.assertRaises(WireError):
                self.decode(replace(frame, payload=frame.payload + b'\x00'), request)

    def test_receipts_preserve_cancellation_race_and_separate_quiescence(self):
        queued = self.decode(FRAMES['queued_receipt'], Request(FRAMES['op_scaled_pair']))
        self.assertEqual((queued.execution, queued.may_have_acted, queued.held_resources), (Execution.QUEUED, False, 5))
        self.assertIsNone(queued.started_at)
        for name, opcode in [('running_receipt', 'query_request'), ('cancel_requested_receipt', 'cancel_request'),
                             ('completed_still_holds_resources', 'query_request'), ('completed_quiescent_receipt', 'query_request')]:
            frame = FRAMES[name]
            self.assertIsInstance(self.decode(frame, response_request(frame, opcode)), Receipt)
        done = self.decode(FRAMES['completed_still_holds_resources'])
        quiet = self.decode(FRAMES['completed_quiescent_receipt'])
        self.assertEqual((done.execution, done.cancellation, done.held_resources), (Execution.COMPLETED, 2, 5))
        self.assertEqual((quiet.execution, quiet.held_resources, quiet.verification), (Execution.COMPLETED, 0, 0))
        self.assertEqual(int.from_bytes(quiet.result, 'big', signed=True), 975)

    def test_contradictory_receipts_never_become_validated_evidence(self):
        cases = [('queued_receipt', 49, 0), ('queued_receipt', 50, 4), ('queued_receipt', 51, 6),
                 ('queued_receipt', 52, 4), ('queued_receipt', 53, 4), ('queued_receipt', 54, 2),
                 ('queued_receipt', 55, b'\x00\x0d'), ('queued_receipt', 57, bytes(4)),
                 ('queued_receipt', 61, struct.pack('>Q', 1200)),
                 ('queued_receipt', 69, struct.pack('>Q', 1100)),
                 ('queued_receipt', 77, struct.pack('>Q', 1200)),
                 ('running_receipt', 54, 0), ('running_receipt', 53, 0),
                 ('running_receipt', 69, struct.pack('>Q', 1099)),
                 ('running_receipt', 69, struct.pack('>Q', 1200)),
                 ('running_receipt', 69, struct.pack('>Q', ABSENT_TIME)),
                 ('completed_quiescent_receipt', 50, 4), ('completed_quiescent_receipt', 51, 0),
                 ('completed_quiescent_receipt', 77, struct.pack('>Q', 1149)),
                 ('completed_quiescent_receipt', 85, 33), ('completed_quiescent_receipt', 85, 3)]
        for name, offset, value in cases:
            frame = changed(FRAMES[name], offset, value)
            request = response_request(frame, 'op_scaled_pair' if name == 'queued_receipt' else 'query_request')
            with self.subTest(name=name, offset=offset, value=value), self.assertRaises(WireError):
                self.decode(frame, request)

    def test_physical_verification_needs_installation_policy_and_required_evidence(self):
        frame = FRAMES['completed_quiescent_receipt']
        with self.assertRaises(WireError):
            self.decode(FRAMES['invalid_simulation_verified_receipt'])
        with self.assertRaises(WireError):
            self.decode(frame, simulator_only=False)
        required = replace(OP, required_effect=1)
        with self.assertRaises(WireError):
            self.decode(frame, operation=required)
        for evidence in (1, 2, 3, 4, 5):
            verified = changed(changed(frame, 51, evidence), 52, 1)
            if evidence in (3, 4):
                self.assertEqual(self.decode(verified, operation=required, simulator_only=False).verification, 1)
                with self.assertRaises(WireError):
                    self.decode(verified)
            else:
                with self.assertRaises(WireError):
                    self.decode(verified, simulator_only=False)

    def test_clock_fault_unknown_retains_claims_and_absent_terminal(self):
        frame = FRAMES['running_receipt']
        unknown = changed(changed(changed(frame, 49, 7), 55, b'\x00\x07'), 69,
                          struct.pack('>Q', ABSENT_TIME))
        result = self.decode(unknown)
        self.assertEqual((result.execution, result.held_resources, result.may_have_acted),
                         (Execution.OUTCOME_UNKNOWN, 5, True))
        self.assertIsNone(result.started_at)
        self.assertIsNone(result.terminal_at)
        with self.assertRaises(WireError):
            self.decode(changed(unknown, 53, 0))

    def test_later_physical_completion_dispute_remains_visible_without_verification(self):
        frame = FRAMES['completed_still_holds_resources']
        disputed = changed(changed(changed(frame, 51, 3), 52, 3), 55, b'\x00\x08')
        result = self.decode(disputed, operation=replace(OP, required_effect=1), simulator_only=False)
        self.assertEqual((result.execution, result.verification, result.held_resources), (Execution.COMPLETED, 3, 5))
        for verification in (0, 2):
            with self.assertRaises(WireError):
                self.decode(changed(disputed, 52, verification), operation=replace(OP, required_effect=1), simulator_only=False)

    def test_completion_at_cutoff_or_with_unknown_time_cannot_be_verified(self):
        frame = FRAMES['completed_quiescent_receipt']
        for terminal in (1350, 1500, 1600, 1700, ABSENT_TIME):
            with self.subTest(terminal=terminal), self.assertRaises(WireError):
                self.decode(changed(frame, 77, struct.pack('>Q', terminal)))
        unknown = changed(changed(frame, 55, b'\x00\x07'), 69, struct.pack('>QQ', ABSENT_TIME, ABSENT_TIME))
        with self.assertRaises(WireError):
            self.decode(unknown)
        self.assertEqual(self.decode(changed(frame, 77, struct.pack('>Q', 1349))).execution, Execution.COMPLETED)

    def test_successful_binding_and_arming_require_qualified_bounded_context(self):
        unqualified = changed(FRAMES['bind_success'], 46, b'\x00\x29')
        with self.assertRaises(WireError):
            decode_response(unqualified, Request(FRAMES['bind_request']))
        unbounded = changed(FRAMES['arm_success'], 56, struct.pack('>Q', 61001))
        with self.assertRaises(WireError):
            decode_response(unbounded, Request(FRAMES['arm_request']))
        boundary = changed(FRAMES['arm_success'], 56, struct.pack('>Q', 61000))
        self.assertEqual(decode_response(boundary, Request(FRAMES['arm_request'])).armed_until, 61000)
        missing_context = changed(FRAMES['hello_qualified_synthetic_response'], 125, 1)
        with self.assertRaises(WireError):
            decode_response(missing_context, Request(FRAMES['hello_request']))

    def test_control_diagnostics_fail_closed_on_contradictions(self):
        for offset, value in [(87, bytes(4)), (125, 5), (126, b'\x00\xb9'),
                              (126, b'\x00\x3d'), (126, b'\x00\x19'), (128, 9),
                              (129, 73), (130, 33), (131, 2), (132, 0)]:
            with self.subTest(offset=offset, value=value), self.assertRaises(WireError):
                decode_response(changed(FRAMES['hello_qualified_synthetic_response'], offset, value), Request(FRAMES['hello_request']))
        one_resource = changed(FRAMES['hello_qualified_synthetic_response'], 128, 1)
        for offset, value in [(153, 2), (161, 1)]:
            with self.assertRaises(WireError):
                decode_response(changed(one_resource, offset, value), Request(FRAMES['hello_request']))
        for offset, value in [(7, struct.pack('>I', 1)), (11, b'\x00\x08'), (13, bytes(32)),
                              (45, 1), (46, b'\x00\x39'), (56, struct.pack('>Q', 1999))]:
            with self.subTest(offset=offset, value=value), self.assertRaises(WireError):
                decode_response(changed(FRAMES['arm_success'], offset, value), Request(FRAMES['arm_request']))


if __name__ == '__main__':
    unittest.main()
