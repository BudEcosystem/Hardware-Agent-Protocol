"""Host authority against the original native compact scenario process.

The test-control socket is external to HMS and never used for observations.
It drives deterministic endpoint time and independently counts synthetic effects.
"""
import copy
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest

from hms.contracts import canonical
from hms.endpoint_wire import Opcode, Operation
from hms.journal import Context, JournalError
from hms.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'


class CompactBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.wire, child_wire = socket.socketpair()
        self.control, child_control = socket.socketpair()
        self.control.settimeout(3)
        self.process = subprocess.Popen([str(BINARY), '--test-control-fd', str(child_control.fileno())],
            stdin=child_wire, stdout=child_wire, stderr=subprocess.PIPE, pass_fds=(child_control.fileno(),))
        child_wire.close()
        child_control.close()
        self.addCleanup(self.cleanup_process)
        self.wall, self.mono = 100000, 1000
        self.owner = Context('test-owner', 'simulation:compact')
        self.runtime = None
        self.open(create=True)
        self.namespace = self.call('namespace', expiresUnixMs=150000)['token']

    def cleanup_process(self):
        if self.runtime is not None:
            self.runtime.close()
        self.wire.close()
        self.control.close()
        try:
            _, error = self.process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            _, error = self.process.communicate()
        self.assertEqual(self.process.returncode, 0, error.decode(errors='replace'))

    def open(self, create=False):
        self.runtime = Runtime(self.directory.name, create=create, owner=self.owner if create else None,
            wall_clock_ms=lambda:self.wall, monotonic_ms=lambda:self.mono, endpoint_fd=self.wire.fileno())

    def reopen(self):
        self.runtime.close()
        self.open()

    def control_call(self, opcode, value=0):
        self.control.sendall(struct.pack('>BQ', opcode, value))
        raw = b''
        while len(raw) < 9:
            raw += self.control.recv(9-len(raw))
        self.assertEqual(raw[0], opcode)
        return int.from_bytes(raw[1:], 'big')

    def advance(self, ms=100, *, tick=True):
        self.wall += ms
        self.mono += ms
        self.control_call(1, self.mono)
        if tick:
            self.runtime.tick()

    def call(self, method, **params):
        return self.runtime.request(self.owner, method, params)

    def prepare(self, instance='sim:home-fan', action='set_level', arguments=None, key='one', **changes):
        params = dict(instanceId=instance, actionId=action, arguments=arguments or {'level':25,'unit':'percent'},
            operationKey=key, replayNamespace=self.namespace, requiredEffect='capability_completion',
            timing={'notBeforeUnixMs':self.wall, 'latestStartUnixMs':self.wall+2000,
                    'latestCompletionUnixMs':self.wall+5000, 'maxRunMs':1000})
        params.update(changes)
        return self.call('prepare', **params)['request']

    def invoke(self, request=None):
        return self.call('invoke', request=request or self.prepare())

    def status(self, op):
        return self.call('operation', operationId=op['operationId'])

    def finish(self, op):
        for _ in range(6):
            self.advance()
            status = self.status(op)
            if status['executionState'] == 'completed' and not status['resourceClaims']:
                return status
        self.fail(str(status))

    def packet_count(self, opcode):
        # Exact retained OP payloads, not an inference from a host status.
        return sum(1 for row in self.runtime.journal._db.execute("SELECT wire FROM ep_packets WHERE direction='tx'")
                   if self.decode(row[0]).payload[1] == opcode)

    @staticmethod
    def decode(wire):
        from protocol.serial.frame import Decoder
        decoder = Decoder()
        for byte in wire:
            event = decoder.feed(byte)
            if event and event[0] == 'frame':
                return event[1]
        raise AssertionError('missing retained frame')

    def test_three_scenarios_use_durable_host_binding_and_actual_C_effects(self):
        cases = [('sim:home-fan','set_level',{'level':25,'unit':'percent'},25),
                 ('sim:microscope','move_absolute',{'position':42,'unit':'um','frame':'sim:microscope'},42),
                 ('sim:inspection-cell','inspect',{'recipe':1,'partId':'part:α'},1)]
        for instance, action, arguments, value in cases:
            op = self.invoke(self.prepare(instance,action,arguments,key=instance))
            self.runtime.tick()
            self.assertEqual(self.status(op)['executionState'], 'dispatching')
            status = self.finish(op)
            self.assertEqual(status['result']['output']['value'], value)
            self.assertEqual(status['result']['evidenceKind'], 'simulation')
            self.assertEqual(status['effectVerification'], 'unverified')
            self.call('events', operationId=op['operationId'])
            row = self.runtime.compact._row(op['operationId'])
            mapping = json.loads(row['mapping'])
            self.assertEqual(mapping['intent'], self.runtime.journal._operation(op['operationId'])['intent'])
            self.assertEqual(Operation.parse(row['payload']).reference.intent_digest.hex(), status['requestDigest'][7:])
            self.assertEqual(row['retired'], 1)
        self.assertEqual(self.control_call(4), 3)
        self.assertEqual(self.control_call(5), 3)
        self.assertEqual(self.packet_count(Opcode.OP), 3)

    def test_host_restart_queries_same_command_and_duplicate_has_one_effect(self):
        request = self.prepare()
        op = self.invoke(request)
        self.runtime.tick()
        self.advance(10)
        self.assertEqual(self.status(op)['executionState'], 'running')
        original = bytes(self.runtime.compact._row(op['operationId'])['payload'])
        self.reopen()
        self.assertEqual(self.status(op)['executionState'], 'outcome_unknown')
        result = self.finish(op)
        self.assertEqual(self.invoke(request)['operationId'], op['operationId'])
        self.assertEqual(self.runtime.compact._row(op['operationId'])['payload'], original)
        self.assertEqual(result['result']['output']['value'],25)
        self.assertEqual(self.control_call(5),1)
        self.assertEqual(self.packet_count(Opcode.OP),1)

    def test_reply_loss_after_endpoint_acceptance_never_replays_OP(self):
        op = self.invoke()
        original = self.runtime.compact.stream.exchange
        def lose(request, receive):
            reply = original(request, receive)
            if request.opcode == Opcode.OP:
                raise JournalError('ENDPOINT_IO_TIMEOUT')
            return reply
        self.runtime.compact.stream.exchange = lose
        with self.assertRaisesRegex(JournalError,'ENDPOINT_IO_TIMEOUT'):
            self.runtime.tick()
        self.assertEqual(self.status(op)['executionState'],'outcome_unknown')
        self.runtime.compact.stream.exchange = original
        self.reopen()
        self.finish(op)
        self.assertEqual(self.packet_count(Opcode.OP),1)
        self.assertEqual(self.control_call(5),1)

    def test_crash_after_reservation_before_handoff_remains_unknown(self):
        op = self.invoke()
        original = self.runtime.compact.stream.exchange
        def crash(request, receive):
            if request.opcode == Opcode.OP:
                raise SystemExit('synthetic crash boundary')
            return original(request,receive)
        self.runtime.compact.stream.exchange = crash
        with self.assertRaises(SystemExit):
            self.runtime.tick()
        self.reopen()
        self.runtime.tick()
        self.assertEqual(self.status(op)['executionState'],'outcome_unknown')
        self.assertTrue(self.status(op)['resourceClaims'])
        self.assertEqual(self.control_call(4),0)
        self.assertEqual(self.packet_count(Opcode.OP),1)

    def test_lost_retire_ack_reopens_without_reexecuting(self):
        op = self.invoke()
        self.runtime.tick()
        self.advance(10)
        self.advance(100)
        original = self.runtime.compact.stream.exchange
        def lose(request, receive):
            reply = original(request,receive)
            if request.opcode == Opcode.RETIRE:
                raise JournalError('ENDPOINT_IO_TIMEOUT')
            return reply
        self.runtime.compact.stream.exchange = lose
        with self.assertRaisesRegex(JournalError,'ENDPOINT_IO_TIMEOUT'):
            self.advance(1)
        row = self.runtime.compact._row(op['operationId'])
        self.assertEqual((row['retire_intent'],row['retired']),(1,0))
        self.reopen()
        self.runtime.tick()
        self.assertEqual(self.runtime.compact._row(op['operationId'])['retired'],1)
        self.assertEqual(self.control_call(5),1)

    def test_reset_keeps_old_command_unknown_and_claimed(self):
        op = self.invoke()
        self.runtime.tick()
        self.advance(10)
        self.control_call(2,43)
        self.reopen()
        self.assertEqual(self.status(op)['executionState'],'outcome_unknown')
        self.assertTrue(self.status(op)['resourceClaims'])
        with self.assertRaisesRegex(JournalError,'ENDPOINT_BOOT_CHANGED'):
            self.runtime.tick()
        self.assertEqual(self.packet_count(Opcode.OP),1)

    def test_endpoint_slot_serializes_disjoint_host_resources(self):
        first = self.invoke()
        second = self.invoke(self.prepare('sim:microscope','move_absolute',
            {'position':42,'unit':'um','frame':'sim:microscope'},key='second'))
        self.runtime.tick()
        self.assertEqual(self.status(second)['executionState'],'accepted')
        self.assertEqual(self.packet_count(Opcode.OP),1)
        self.finish(first)
        self.finish(second)
        self.assertEqual(self.control_call(5),2)

    def test_completed_observation_keeps_original_sample_age_on_query_and_restart(self):
        with self.assertRaisesRegex(JournalError,'OBSERVATION_MISSING'):
            self.call('observe',instanceId='sim:home-fan',property='value')
        op = self.invoke()
        self.runtime.tick()
        self.finish(op)
        before = self.call('observe',instanceId='sim:home-fan',property='value')
        self.advance(500)
        self.reopen()
        after = self.call('observe',instanceId='sim:home-fan',property='value')
        self.assertEqual(before['acquisition'],after['acquisition'])
        self.assertGreaterEqual(after['ageUpperBoundMs'],before['ageUpperBoundMs']+500)
        with self.assertRaisesRegex(JournalError,'OBSERVATION_STALE'):
            self.call('observe',instanceId='sim:home-fan',property='value',maxAgeMs=100,evidenceKind='simulation')

    def test_cancel_queued_and_running_require_endpoint_receipt(self):
        op = self.invoke()
        self.runtime.tick()
        requested = self.call('cancel',operationId=op['operationId'])
        self.assertTrue(requested['mayHaveActed'])
        self.runtime.tick()
        status = self.status(op)
        self.assertEqual(status['executionState'],'canceled')
        self.assertFalse(status['mayHaveActed'])
        self.assertFalse(status['resourceClaims'])
        self.assertEqual(self.control_call(5),0)

    def test_mapping_preserves_host_fence_above_uint32(self):
        self.runtime.journal._db.execute('INSERT INTO resource_floors VALUES (?,?,?)',
            (self.owner.deployment,'sim:home-fan:fan-control',2**32+6))
        op = self.invoke()
        self.runtime.tick()
        row = self.runtime.compact._row(op['operationId'])
        self.assertEqual(Operation.parse(row['payload']).fences,(1,))
        self.assertEqual(json.loads(row['mapping'])['fences'][0]['hostFence'],2**32+7)

    def test_compact_authority_cannot_open_as_sqlite_plant(self):
        self.runtime.close()
        with self.assertRaisesRegex(JournalError,'ENDPOINT_STREAM_REQUIRED'):
            Runtime(self.directory.name)
        self.assertFalse((Path(self.directory.name)/'simulated-plant.db').exists())
