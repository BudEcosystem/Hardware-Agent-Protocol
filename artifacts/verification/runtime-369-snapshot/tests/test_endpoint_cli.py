"""SIGKILL/reopen of the real CLI against the original native C simulator.

The external test launcher owns a Unix byte relay and the endpoint lifetime.
It gates an actual OP reply to place host death after endpoint admission but
before the host receives that reply. The fixture uses its real monotonic clock;
there is no deterministic control FD, physical port, or hardware evidence.
"""
import json
import os
from pathlib import Path
import select
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from hms.client import Client
from hms.contracts import canonical
from hms.endpoint_wire import Execution, Opcode, Operation, Receipt, Request, decode_response
from protocol.serial.frame import Decoder, encode

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'


class ReplyGate:
    """Forward exact original frames; hold replies at one externally chosen OP."""

    def __init__(self, host, native):
        self.host, self.native = host, native
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.gated = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.armed = False
        self.pending = []
        self.requests = []
        self.responses = []
        self.gated_reply = None
        self.error = None
        self.thread = threading.Thread(target=self.run, name='hms-cli-test-relay')
        self.thread.start()

    def arm(self):
        with self.lock:
            if self.pending or not self.release.is_set():
                raise AssertionError('Previous reply gate has not drained')
            self.gated.clear()
            self.gated_reply = None
            self.release.clear()
            self.armed = True

    def run(self):
        decoders = {self.host: Decoder(), self.native: Decoder()}
        buffers = {self.host: bytearray(), self.native: bytearray()}
        try:
            while not self.stop.is_set():
                with self.lock:
                    if self.release.is_set() and self.pending:
                        for raw in self.pending:
                            self.host.sendall(raw)
                        self.pending.clear()
                ready, _, _ = select.select([self.host, self.native], [], [], 0.002)
                for source in ready:
                    block = source.recv(4096)
                    if not block:
                        return
                    for byte in block:
                        buffers[source].append(byte)
                        event = decoders[source].feed(byte)
                        if event is None:
                            continue
                        if event[0] != 'frame':
                            raise AssertionError(f'Unexpected native stream error: {event}')
                        frame, raw = event[1], bytes(buffers[source])
                        buffers[source].clear()
                        if encode(frame) != raw:
                            raise AssertionError('Relay must preserve the complete original frame')
                        with self.lock:
                            if source is self.host:
                                self.native.sendall(raw)
                                self.requests.append((frame, raw))
                            else:
                                self.responses.append((frame, raw))
                                if self.armed and frame.payload[1] == (Opcode.OP | 0x80):
                                    self.armed = False
                                    self.gated_reply = (frame, raw)
                                    self.pending.append(raw)
                                    self.gated.set()
                                elif self.pending and not self.release.is_set():
                                    self.pending.append(raw)
                                else:
                                    self.host.sendall(raw)
        except BaseException as error:
            if not self.stop.is_set():
                self.error = error
        finally:
            self.host.close()
            self.native.close()

    def op_frames(self):
        with self.lock:
            return [(frame, raw) for frame, raw in self.requests if frame.payload[1] == Opcode.OP]

    def close(self):
        self.stop.set()
        self.thread.join(3)
        if self.thread.is_alive():
            raise AssertionError('External relay failed to stop')
        if self.error is not None:
            raise self.error


@unittest.skipUnless(sys.platform == 'linux' and hasattr(socket, 'SO_PEERCRED'),
                     'Linux inherited Unix socket and peer credentials required')
class CompactCliRestartTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(BINARY.is_file(), 'Build the original fixture with scripts/check_endpoint_scenarios.py first')
        self.directory = tempfile.TemporaryDirectory(prefix='hms-compact-cli-')
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.state = self.base / 'state'
        self.socket_path = self.base / 'hctl.sock'
        self.host_wire, relay_host = socket.socketpair()
        relay_native, native_wire = socket.socketpair()
        self.daemon = None
        self.relay = None
        self.fixture = subprocess.Popen([str(BINARY), '--boot', '73'],
            stdin=native_wire, stdout=native_wire, stderr=subprocess.PIPE)
        native_wire.close()
        self.addCleanup(self.cleanup)
        self.relay = ReplyGate(relay_host, relay_native)
        self.start_daemon(create=True)
        self.client = Client(self.socket_path)

    def cleanup(self):
        if self.daemon is not None:
            daemon, self.daemon = self.daemon, None
            if daemon.poll() is None:
                daemon.terminate()
            try:
                _, error = daemon.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                daemon.kill()
                _, error = daemon.communicate(timeout=3)
                self.fail(f'CLI did not quiesce on termination: {error!r}')
            self.assertEqual(daemon.returncode, 0, error.decode(errors='replace'))
        self.host_wire.close()
        if self.relay is not None:
            self.relay.close()
        try:
            _, error = self.fixture.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.fixture.kill()
            _, error = self.fixture.communicate(timeout=3)
            self.fail(f'Native fixture did not exit on launcher socket close: {error!r}')
        self.assertEqual(self.fixture.returncode, 0, error.decode(errors='replace'))

    def start_daemon(self, *, create=False):
        args = [sys.executable, '-B', '-m', 'hms', 'serve', '--socket', str(self.socket_path),
                '--state-dir', str(self.state), '--endpoint-fd', str(self.host_wire.fileno())]
        if create:
            args.append('--init-compact-simulation')
        self.daemon = subprocess.Popen(args, cwd=ROOT, pass_fds=(self.host_wire.fileno(),),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ready, _, _ = select.select([self.daemon.stdout], [], [], 8)
        self.assertTrue(ready, 'CLI did not produce a bounded readiness response')
        line = self.daemon.stdout.readline()
        if not line:
            _, error = self.daemon.communicate(timeout=3)
            self.fail(f'CLI exited before readiness: {self.daemon.returncode}: {error!r}')
        self.assertEqual(json.loads(line)['deployment'], 'simulation:compact')
        self.assertTrue(json.loads(line)['ready'])
        info = self.socket_path.lstat()
        self.socket_identity = (info.st_dev, info.st_ino)
        self.assertTrue(stat.S_ISSOCK(info.st_mode))
        self.assertIsNone(self.fixture.poll(), 'Endpoint lifetime must be independent of the daemon')

    def kill_daemon(self):
        daemon, self.daemon = self.daemon, None
        daemon.kill()
        _, error = daemon.communicate(timeout=3)
        self.assertEqual(daemon.returncode, -signal.SIGKILL, error.decode(errors='replace'))
        self.assertIsNone(self.fixture.poll(), 'SIGKILL of host must not terminate native endpoint')
        # Production IPC deliberately refuses stale paths. Only this launcher,
        # after reaping its own daemon and checking the original socket inode,
        # removes that daemon's known stale pathname before reopening it.
        info = self.socket_path.lstat()
        self.assertTrue(stat.S_ISSOCK(info.st_mode))
        self.assertEqual((info.st_dev, info.st_ino), self.socket_identity)
        self.socket_path.unlink()

    def cli(self, *args):
        result = subprocess.run([sys.executable, '-B', '-m', 'hms', '--socket', str(self.socket_path), *args],
                                cwd=ROOT, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return json.loads(result.stdout)

    def database(self, query, params=()):
        with sqlite3.connect(f'file:{self.state / "authority.db"}?mode=ro', uri=True, timeout=1) as db:
            return db.execute(query, params).fetchall()

    def settled(self, operation_id):
        deadline = time.monotonic() + 5
        status = None
        while time.monotonic() < deadline:
            if self.relay.error is not None:
                raise self.relay.error
            status = self.client.request('operation', {'operationId': operation_id})
            if status['executionState'] == 'completed' and not status['resourceClaims']:
                rows = self.database('SELECT retired FROM ep_commands WHERE operation_id=?', (operation_id,))
                if rows == [(1,)]:
                    return status
            if status['executionState'] in {'failed', 'canceled', 'rejected_before_start'}:
                self.fail(f'Unexpected terminal outcome: {status}')
            time.sleep(0.01)
        self.fail(f'Operation did not reconcile and retire: {status}')

    def test_three_native_scenarios_reconcile_after_SIGKILL_without_replaying_OP(self):
        namespace = self.client.request('namespace', {'expiresUnixMs': time.time_ns() // 1_000_000 + 60000})['token']
        cases = [('sim:home-fan', 'set_level', {'level': 25, 'unit': 'percent'}, 25),
                 ('sim:microscope', 'move_absolute', {'position': 42, 'unit': 'um', 'frame': 'sim:microscope'}, 42),
                 ('sim:inspection-cell', 'inspect', {'recipe': 1, 'partId': 'part:α'}, 1)]
        for index, (instance, action, arguments, value) in enumerate(cases, 1):
            now = time.time_ns() // 1_000_000
            prepared = self.client.request('prepare', {'instanceId': instance, 'actionId': action,
                'arguments': arguments, 'operationKey': f'cli-retained-{index}', 'replayNamespace': namespace,
                'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': now,
                'latestStartUnixMs': now + 5000, 'maxRunMs': 2000, 'latestCompletionUnixMs': now + 10000}})
            request = prepared['request']
            request_file = self.base / f'request-{index}.json'
            request_file.write_bytes(canonical(request))
            self.relay.arm()
            admitted = self.client.request('invoke', {'request': request})
            self.assertIn(admitted['executionState'], {'accepted', 'dispatching'})
            if not self.relay.gated.wait(3):
                state = json.loads(self.database('SELECT document FROM ep_state')[0][0])
                self.fail(str({'relayError': repr(self.relay.error),
                    'endpointState': {key: state.get(key) for key in ('fault', 'boot', 'call', 'tx', 'rx', 'clockAnchor')},
                    'operation': self.client.request('operation', {'operationId': admitted['operationId']}),
                    'forwardedOpFrames': len(self.relay.op_frames())}))
            self.kill_daemon()
            self.assertEqual(len(self.relay.op_frames()), index)
            op_frame, original_wire = self.relay.op_frames()[-1]
            operation = Operation.parse(op_frame.payload)
            reply_frame, _ = self.relay.gated_reply
            native_receipt = decode_response(reply_frame, Request(op_frame), operation=operation, simulator_only=True)
            self.assertIsInstance(native_receipt, Receipt)
            self.assertIn(native_receipt.execution, {Execution.QUEUED, Execution.RUNNING})
            self.assertEqual(op_frame.session, 73)
            self.assertEqual(operation.reference.intent_digest.hex(), admitted['requestDigest'][7:])
            before = self.database('SELECT payload, tx_sequence FROM ep_commands WHERE operation_id=?',
                                   (admitted['operationId'],))
            self.assertEqual(before, [(op_frame.payload, op_frame.sequence)])
            self.assertEqual(self.database('SELECT receipt FROM ep_commands WHERE operation_id=?',
                                           (admitted['operationId'],)), [(None,)])
            with self.relay.lock:
                request_count_before_restart = len(self.relay.requests)
            # The original reply remains queued for the new host. It cannot
            # satisfy that host's new HELLO correlation; recovery uses QUERY.
            self.relay.release.set()
            self.start_daemon()
            replay = self.cli('invoke', '--request-file', str(request_file))
            self.assertEqual(replay['operationId'], admitted['operationId'])
            self.assertEqual(replay['requestDigest'], admitted['requestDigest'])
            completed = self.settled(admitted['operationId'])
            self.assertEqual(completed['effectVerification'], 'unverified')
            self.assertEqual(completed['result']['evidenceKind'], 'simulation')
            self.assertEqual(completed['result']['output']['value'], value)
            self.assertTrue(completed['result']['output']['effectCommitted'])
            with self.relay.lock:
                recovered_frames = [frame for frame, _ in self.relay.requests[request_count_before_restart:]]
            self.assertTrue(any(frame.payload == operation.reference.payload(Opcode.QUERY)
                                for frame in recovered_frames), 'Recovery must query the original endpoint receipt')
            again = self.cli('invoke', '--request-file', str(request_file))
            self.assertEqual(again['operationId'], admitted['operationId'])
            self.assertEqual(again['result'], completed['result'])
            self.assertEqual(self.database('SELECT payload, tx_sequence FROM ep_commands WHERE operation_id=?',
                                           (admitted['operationId'],)), before)
            self.assertEqual(len(self.relay.op_frames()), index)
            self.assertEqual(self.relay.op_frames()[-1][1], original_wire)
            observed = self.cli('observe', instance, 'value', '--max-age-ms', '10000', '--evidence-kind', 'simulation')
            self.assertEqual(observed['value'], value)
            self.assertEqual(observed['acquisition']['ticksMs'], completed['result']['output']['sampleTick'])
        retained = []
        for (raw,) in self.database("SELECT wire FROM ep_packets WHERE direction='tx' ORDER BY id"):
            decoder = Decoder()
            for byte in raw:
                event = decoder.feed(byte)
                if event is not None:
                    self.assertEqual(event[0], 'frame')
                    if event[1].payload[1] == Opcode.OP:
                        retained.append(raw)
        self.assertEqual(retained, [raw for _, raw in self.relay.op_frames()])
        self.assertEqual(len(retained), 3)
        self.assertFalse((self.state / 'simulated-plant.db').exists(), 'This test must use the actual native fixture')


if __name__ == '__main__':
    unittest.main()
