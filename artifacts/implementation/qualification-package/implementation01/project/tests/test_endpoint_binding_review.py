"""Independent adversarial recovery probes over the retained original C fixture."""
import struct
import unittest
from unittest.mock import patch

import test_endpoint_binding as support
from hms.endpoint_transport import LocalEndpointStream
from hms.endpoint_wire import Execution, Opcode, Operation, Request, decode_response
from hms.journal import JournalError
from protocol.serial.frame import Frame


class EndpointBindingReviewTests(unittest.TestCase):
    def open_harness(self):
        # Composition avoids rediscovering the parent's implementation tests.
        h = support.CompactBindingTests()
        self.h = h
        self.addCleanup(h.doCleanups)
        h.setUp()
        return h

    def offer(self, h, op, *, execution=None, cancellation=None, reason=None, verification=None, bump=True):
        backend = h.runtime.compact
        row = backend._row(op['operationId'])
        operation = Operation.parse(row['payload'])
        payload = bytearray(row['receipt'])
        if execution is not None:
            payload[49] = execution
        if cancellation is not None:
            payload[50] = cancellation
        if reason is not None:
            payload[55:57] = struct.pack('>H', reason)
        if verification is not None:
            payload[52] = verification
        if bump:
            payload[57:61] = struct.pack('>I', int.from_bytes(payload[57:61], 'big') + 1)
        if execution == Execution.COMPLETED:
            sample = int.from_bytes(payload[69:77], 'big') + 1
            payload[51] = 5
            payload[77:85] = struct.pack('>Q', sample)
            payload[85] = 12
            payload[86:] = struct.pack('>QI', sample, 25)
        elif execution == Execution.FAILED:
            payload[51] = 5
            payload[77:85] = struct.pack('>Q', int.from_bytes(payload[69:77], 'big') + 1)
        opcode = Opcode(payload[1] & 127)
        request = Request(Frame(1, 0, 42, int.from_bytes(payload[2:6], 'big'), operation.reference.payload(opcode)))
        frame = Frame(2, 0, 42, 1000, bytes(payload))
        # The fabricated peer snapshot must first pass the stateless codec;
        # the expected refusal is specifically against durable prior evidence.
        receipt = decode_response(frame, request, operation=operation, simulator_only=True)
        backend._settle(op['operationId'], receipt, frame)
        return receipt

    def running(self, h):
        op = h.invoke()
        h.runtime.tick()
        h.advance(100)
        self.assertEqual(h.status(op)['executionState'], 'running')
        return op

    def test_endpoint_unknown_cannot_resume_running_or_complete(self):
        h = self.open_harness()
        op = self.running(h)
        self.offer(h, op, execution=Execution.OUTCOME_UNKNOWN, reason=9)
        for state in (Execution.RUNNING, Execution.COMPLETED):
            with self.subTest(state=state):
                with self.assertRaisesRegex(JournalError, 'ENDPOINT_EXECUTION_REGRESSION'):
                    self.offer(h, op, execution=state, reason=0)
        status = h.status(op)
        self.assertEqual(status['executionState'], 'outcome_unknown')
        self.assertTrue(status['resourceClaims'])
        self.assertIsNone(status['result'])

    def cancellation_regression(self, initial):
        h = self.open_harness()
        op = self.running(h)
        h.call('cancel', operationId=op['operationId'])
        self.offer(h, op, cancellation=initial)
        prior = h.status(op)
        for value in (0, 1):
            with self.subTest(cancellation=value):
                with self.assertRaisesRegex(JournalError, 'ENDPOINT_CANCELLATION_REGRESSION'):
                    self.offer(h, op, cancellation=value)
        self.assertEqual(h.status(op), prior)

    def test_cancel_ack_cannot_return_to_none_or_requested(self):
        self.cancellation_regression(2)

    def test_cancel_rejection_cannot_return_to_none_or_requested(self):
        self.cancellation_regression(3)

    def test_equal_revision_changed_receipt_is_not_a_duplicate(self):
        h = self.open_harness()
        op = self.running(h)
        with self.assertRaisesRegex(JournalError, 'ENDPOINT_RECEIPT_CONFLICT'):
            self.offer(h, op, reason=9, bump=False)
        self.assertEqual(h.status(op)['executionState'], 'running')
        self.assertTrue(h.status(op)['resourceClaims'])

    def test_terminal_failed_verification_is_not_silently_dropped(self):
        h = self.open_harness()
        op = self.running(h)
        self.offer(h, op, execution=Execution.FAILED, verification=2, reason=8)
        status = h.status(op)
        self.assertEqual(status['executionState'], 'failed')
        self.assertEqual(status['effectVerification'], 'failed')
        self.assertTrue(status['resourceClaims'])
        self.assertIsNone(status['result'])
        events = h.call('events', operationId=op['operationId'])
        self.assertIn('verification_failed', events['events'][-1]['payload']['hms_qualification.evidence']['assertions'])

    def test_active_verification_claim_is_refused_without_losing_claims(self):
        h = self.open_harness()
        op = self.running(h)
        before = h.status(op)
        with self.assertRaises(JournalError):
            self.offer(h, op, verification=2)
        self.assertEqual(h.status(op), before)

    def test_disputed_result_invalidates_observation_and_cannot_be_republished(self):
        h = self.open_harness()
        op = self.running(h)
        h.advance(100)
        before = h.call('observe', instanceId='sim:home-fan', property='value', maxAgeMs=1000, evidenceKind='simulation')
        self.assertEqual(before['quality'], 'valid')
        self.offer(h, op, verification=3)
        self.assertEqual(h.status(op)['effectVerification'], 'disputed')
        self.assertTrue(h.status(op)['resourceClaims'])
        for restore in (False, True):
            with self.subTest(restore=restore):
                if restore:
                    h.runtime.compact._restore_samples()
                with self.assertRaises(JournalError):
                    h.call('observe', instanceId='sim:home-fan', property='value', maxAgeMs=1000, evidenceKind='simulation')

    def test_stalled_endpoint_clock_cannot_refresh_qualification(self):
        h = self.open_harness()
        h.wall += 300
        h.mono += 300
        with self.assertRaisesRegex(JournalError, 'ENDPOINT_CLOCK_RATE_LOST'):
            h.runtime.compact.refresh(force=True)
        self.assertIsNone(h.runtime.compact.witness)
        with self.assertRaises(JournalError):
            h.prepare()
        self.assertEqual(h.packet_count(Opcode.OP), 0)

    def test_forward_endpoint_clock_jump_cannot_redefine_offset(self):
        h = self.open_harness()
        h.control_call(1, h.mono + 300)
        with self.assertRaisesRegex(JournalError, 'ENDPOINT_CLOCK_RATE_LOST'):
            h.runtime.compact.refresh(force=True)
        self.assertIsNone(h.runtime.compact.witness)
        self.assertEqual(h.packet_count(Opcode.OP), 0)

    def test_clock_qualification_loss_still_records_failure_and_quiescence(self):
        h = self.open_harness()
        op = self.running(h)
        # Qualified boot + simulator only, with clock qualification removed.
        h.control_call(3, 9)
        try:
            h.runtime.compact.refresh(force=True)
        except JournalError:
            pass
        h.advance(1, tick=False)
        try:
            h.runtime.tick()
        except JournalError:
            pass
        status = h.status(op)
        self.assertEqual(status['executionState'], 'failed')
        self.assertTrue(status['mayHaveActed'])
        self.assertFalse(status['resourceClaims'])
        self.assertIsNone(status['result'])
        self.assertEqual(h.packet_count(Opcode.OP), 1)
        self.assertEqual(h.control_call(5), 0)

    def test_lost_bind_ack_recovers_exact_desired_context_without_rebinding(self):
        original = LocalEndpointStream.exchange
        dropped = []
        def lose_bind(stream, request, receive):
            response = original(stream, request, receive)
            if request.opcode == Opcode.BIND and not dropped:
                dropped.append(True)
                raise JournalError('ENDPOINT_IO_TIMEOUT')
            return response
        with patch.object(LocalEndpointStream, 'exchange', lose_bind):
            with self.assertRaisesRegex(JournalError, 'ENDPOINT_IO_TIMEOUT'):
                self.open_harness()
        h = self.h
        h.open()
        description = h.call('describe', instanceId='sim:home-fan')
        self.assertTrue(description['bindingActive'])
        self.assertEqual(h.packet_count(Opcode.BIND), 1)
        self.assertEqual(h.packet_count(Opcode.OP), 0)

    def test_lost_arm_ack_has_no_op_and_hello_resolves_pending_control(self):
        h = self.open_harness()
        op = h.invoke()
        original = h.runtime.compact.stream.exchange
        dropped = []
        def lose_arm(request, receive):
            response = original(request, receive)
            if request.opcode == Opcode.ARM and not dropped:
                dropped.append(True)
                raise JournalError('ENDPOINT_IO_TIMEOUT')
            return response
        h.runtime.compact.stream.exchange = lose_arm
        with self.assertRaisesRegex(JournalError, 'ENDPOINT_IO_TIMEOUT'):
            h.runtime.tick()
        h.runtime.compact.stream.exchange = original
        self.assertEqual(h.packet_count(Opcode.OP), 0)
        self.assertFalse(h.status(op)['mayHaveActed'])
        h.runtime.compact.refresh(force=True)
        self.assertIsNone(h.runtime.compact._state()['armPending'])
        self.assertEqual(h.packet_count(Opcode.ARM), 1)

    def test_lost_retire_ack_resolves_by_query_without_retransmission(self):
        h = self.open_harness()
        op = self.running(h)
        h.advance(100)
        self.assertEqual(h.status(op)['executionState'], 'completed')
        original = h.runtime.compact.stream.exchange
        dropped = []
        def lose_retire(request, receive):
            response = original(request, receive)
            if request.opcode == Opcode.RETIRE and not dropped:
                dropped.append(True)
                raise JournalError('ENDPOINT_IO_TIMEOUT')
            return response
        h.runtime.compact.stream.exchange = lose_retire
        with self.assertRaisesRegex(JournalError, 'ENDPOINT_IO_TIMEOUT'):
            h.advance(100)
        h.runtime.compact.stream.exchange = original
        durable = h.status(op)
        self.assertFalse(durable['resourceClaims'])
        self.assertEqual(h.packet_count(Opcode.RETIRE), 1)
        queries = h.packet_count(Opcode.QUERY)
        h.runtime.tick()
        self.assertEqual(h.packet_count(Opcode.RETIRE), 1)
        self.assertEqual(h.packet_count(Opcode.QUERY), queries + 1)
        self.assertEqual(h.runtime.compact._row(op['operationId'])['retired'], 1)
        self.assertEqual(h.status(op), durable)
        self.assertEqual(h.packet_count(Opcode.OP), 1)
        self.assertEqual(h.control_call(5), 1)

    def test_receipt_commit_before_projection_crash_recovers_original_sample(self):
        h = self.open_harness()
        op = self.running(h)
        original = h.runtime.compact._publish
        def fail_value(instance, property_id, value, sample_tick):
            if property_id == 'value':
                raise OSError('synthetic crash after receipt commit')
            return original(instance, property_id, value, sample_tick)
        h.runtime.compact._publish = fail_value
        with self.assertRaises(OSError):
            h.advance(100)
        committed = h.status(op)['result']['output']
        h.reopen()
        sample = h.call('observe', instanceId='sim:home-fan', property='value', maxAgeMs=1000, evidenceKind='simulation')
        self.assertEqual(sample['acquisition']['ticksMs'], committed['sampleTick'])
        self.assertEqual(sample['value'], committed['value'])
        h.advance(100)
        sample2 = h.call('observe', instanceId='sim:home-fan', property='value', maxAgeMs=1000, evidenceKind='simulation')
        self.assertEqual(sample2['acquisition']['ticksMs'], committed['sampleTick'])
        self.assertGreaterEqual(sample2['ageUpperBoundMs'], sample['ageUpperBoundMs'] + 100)
        self.assertEqual(h.packet_count(Opcode.OP), 1)


if __name__ == '__main__':
    unittest.main()
