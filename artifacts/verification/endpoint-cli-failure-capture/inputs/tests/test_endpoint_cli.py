"""SIGKILL/reopen of the real CLI against the original native C simulator.

The external test launcher owns a Unix byte relay and the endpoint lifetime.
It gates an actual OP reply to place host death after endpoint admission but
before the host receives that reply. The fixture uses its real monotonic clock;
there is no deterministic control FD, physical port, or hardware evidence.
"""
import contextlib
import copy
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
import traceback
import unittest
from unittest.mock import patch

from hms.client import Client
from hms.contracts import canonical
from hms.endpoint_wire import Execution, Opcode, Operation, Receipt, Request, decode_response
from protocol.serial.frame import Decoder, encode
from tests.sqlite_observer import admission_snapshot, readonly_rows

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'
LAST_REPORT = {'schema': 'hms-endpoint-cli-observer-tests/1', 'cases': {}}


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
        self.daemon = self.relay = self.fixture = self.host_wire = None
        self._setup_sockets = []
        self.report = {'passed': False, 'observerReads': [], 'scenarios': [],
                       'cliCalls': [], 'processOutput': [], 'daemonStarts': [],
                       'scope': 'Original compact CLI identity/reconciliation integration; bounded read-only observer retries only, no core availability or timing guarantee.'}
        LAST_REPORT['cases'][self.id()] = self.report
        self.directory = tempfile.TemporaryDirectory(prefix='hms-compact-cli-')
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.state = self.base / 'state'
        self.addCleanup(self._finalize_report)
        self.addCleanup(self.cleanup)
        self.addCleanup(self._retain_test_failure)
        self.assertTrue(BINARY.is_file(), 'Build the original fixture with scripts/check_endpoint_scenarios.py first')
        self.socket_path = self.base / 'hctl.sock'
        self.host_wire, relay_host = socket.socketpair()
        self._setup_sockets.extend((self.host_wire, relay_host))
        relay_native, native_wire = socket.socketpair()
        self._setup_sockets.extend((relay_native, native_wire))
        self.fixture = subprocess.Popen([str(BINARY), '--boot', '73'],
            stdin=native_wire, stdout=native_wire, stderr=subprocess.PIPE)
        native_wire.close()
        self.relay = ReplyGate(relay_host, relay_native)
        self.start_daemon(create=True)
        self.client = Client(self.socket_path)

    @staticmethod
    def _times():
        return {'wallUnixMs': time.time_ns() // 1_000_000,
                'monotonicMs': time.monotonic_ns() // 1_000_000}

    def _failures(self):
        # The pinned unittest runner records setup/test/subtest outcomes before
        # public addCleanup callbacks run. Do not infer success from the mutable
        # _Outcome.success flag while a cleanup itself is executing.
        result = getattr(getattr(self, '_outcome', None), 'result', None)
        return [(test, detail) for test, detail in
                [*getattr(result, 'failures', []), *getattr(result, 'errors', [])]
                if test is self or getattr(test, 'test_case', None) is self]

    def _retain_failure(self, reason, *, stage):
        self.report.setdefault('failureDetails', []).append({'stage': stage, 'detail': reason,
                                                            'time': self._times()})
        if not self.report.get('failureArtifacts'):
            try:
                # Lazy import avoids a discovery-time dependency through ReplyGate.
                from test_multi_cli import retain_transport_failure
                retain_transport_failure(self.report, self.id(), self.state, reason,
                                         base=self.base, relay=self.relay)
            except Exception as error:
                self.report.setdefault('failureCaptureErrors', []).append(
                    {'stage': stage, 'error': repr(error)})

    def _retain_test_failure(self):
        failures = self._failures()
        if failures:
            self._retain_failure('\n'.join(detail for _, detail in failures), stage='before-cleanup')

    def _finalize_report(self):
        self.report['passed'] = not self._failures()
        if self.report.get('failureArtifacts'):
            # Lazy import keeps the reply-gate module independent while tests
            # importing it are still being discovered.
            from test_multi_cli import finish_transport_failure
            finish_transport_failure(self.report)

    def cleanup(self):
        try:
            self._cleanup_processes()
        except BaseException:
            self._retain_failure(traceback.format_exc(), stage='cleanup')
            raise

    def _cleanup_processes(self):
        if self.daemon is not None:
            daemon, self.daemon = self.daemon, None
            if daemon.poll() is None:
                daemon.terminate()
            try:
                output, error = daemon.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                daemon.kill()
                output, error = daemon.communicate(timeout=3)
                self.report['processOutput'].append({'process': 'daemon', 'stdoutHex': output.hex(),
                    'stderrHex': error.hex(), 'exitCode': daemon.returncode, 'stopTimedOut': True,
                    'time': self._times()})
                self.fail(f'CLI did not quiesce on termination: {error!r}')
            self.report['processOutput'].append({'process': 'daemon', 'stdoutHex': output.hex(),
                'stderrHex': error.hex(), 'exitCode': daemon.returncode, 'stopTimedOut': False,
                'time': self._times()})
            self.assertEqual(daemon.returncode, 0, error.decode(errors='replace'))
        if self.host_wire is not None:
            self.host_wire.close()
        if self.relay is not None:
            self.relay.close()
        for stream in self._setup_sockets:
            stream.close()
        if self.fixture is None:
            return
        try:
            _, error = self.fixture.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.fixture.kill()
            _, error = self.fixture.communicate(timeout=3)
            self.report['processOutput'].append({'process': 'fixture', 'stderrHex': error.hex(),
                'exitCode': self.fixture.returncode, 'stopTimedOut': True, 'time': self._times()})
            self.fail(f'Native fixture did not exit on launcher socket close: {error!r}')
        self.report['processOutput'].append({'process': 'fixture', 'stderrHex': error.hex(),
            'exitCode': self.fixture.returncode, 'stopTimedOut': False, 'time': self._times()})
        self.assertEqual(self.fixture.returncode, 0, error.decode(errors='replace'))

    def start_daemon(self, *, create=False):
        args = [sys.executable, '-B', '-m', 'hms', 'serve', '--socket', str(self.socket_path),
                '--state-dir', str(self.state), '--endpoint-fd', str(self.host_wire.fileno())]
        if create:
            args.append('--init-compact-simulation')
        entry = {'command': args, 'started': self._times()}
        self.report['daemonStarts'].append(entry)
        self.daemon = subprocess.Popen(args, cwd=ROOT, pass_fds=(self.host_wire.fileno(),),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ready, _, _ = select.select([self.daemon.stdout], [], [], 8)
        self.assertTrue(ready, 'CLI did not produce a bounded readiness response')
        line = self.daemon.stdout.readline()
        entry.update(readinessHex=line.hex(), readinessRead=self._times())
        if not line:
            output, error = self.daemon.communicate(timeout=3)
            self.report['processOutput'].append({'process': 'daemon', 'stdoutHex': output.hex(),
                'stderrHex': error.hex(), 'exitCode': self.daemon.returncode,
                'readinessFailed': True, 'time': self._times()})
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
        output, error = daemon.communicate(timeout=3)
        self.report['processOutput'].append({'process': 'daemon', 'stdoutHex': output.hex(),
            'stderrHex': error.hex(), 'exitCode': daemon.returncode, 'signal': 'SIGKILL',
            'time': self._times()})
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
        command = [sys.executable, '-B', '-m', 'hms', '--socket', str(self.socket_path), *args]
        entry = {'arguments': list(args), 'started': self._times()}
        self.report['cliCalls'].append(entry)
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=10)
            entry.update(exitCode=result.returncode, stdoutHex=result.stdout.hex(), stderrHex=result.stderr.hex())
        except BaseException as error:
            entry['error'] = repr(error)
            raise
        finally:
            entry['finished'] = self._times()
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        body = json.loads(result.stdout)
        entry['result'] = copy.deepcopy(body)
        return body

    def database(self, query, params=()):
        entry = {}
        self.report['observerReads'].append(entry)
        try:
            return readonly_rows(self.state / 'authority.db', query, params, report=entry)
        except sqlite3.Error as error:
            try:
                from test_multi_cli import retain_transport_failure
                retain_transport_failure(self.report, self.id(), self.state,
                    'Read-only observer error: ' + repr(error), base=self.base, relay=self.relay)
                if self.report.get('failureArtifacts'):
                    error.add_note('Observer failure evidence: ' + ', '.join(self.report['failureArtifacts']))
            except Exception as capture_error:
                self.report.setdefault('failureCaptureErrors', []).append(
                    {'stage': 'observer', 'error': repr(capture_error)})
            raise

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
            scenario = {'instanceId': instance, 'actionId': action,
                        'operationKey': f'cli-retained-{index}', 'expectedValue': value, 'passed': False}
            self.report['scenarios'].append(scenario)
            now = time.time_ns() // 1_000_000
            scenario.update(arguments=copy.deepcopy(arguments), replayNamespace=namespace,
                            prepareStarted=self._times(), requestedNotBeforeUnixMs=now)
            prepared = self.client.request('prepare', {'instanceId': instance, 'actionId': action,
                'arguments': arguments, 'operationKey': f'cli-retained-{index}', 'replayNamespace': namespace,
                'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': now,
                'latestStartUnixMs': now + 5000, 'maxRunMs': 2000, 'latestCompletionUnixMs': now + 10000}})
            request = prepared['request']
            scenario['request'] = copy.deepcopy(request)
            request_file = self.base / f'request-{index}.json'
            request_file.write_bytes(canonical(request))
            self.relay.arm()
            admitted = self.client.request('invoke', {'request': request})
            scenario.update(operationId=admitted['operationId'], requestDigest=admitted['requestDigest'])
            scenario.update(request=copy.deepcopy(request), admitted=copy.deepcopy(admitted),
                            admittedObserved=self._times())
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
            scenario.update(gatedRequestHex=original_wire.hex(), gatedReplyHex=self.relay.gated_reply[1].hex())
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
            scenario.update(firstReplay=copy.deepcopy(replay), firstReplayObserved=self._times())
            self.assertEqual(replay['operationId'], admitted['operationId'])
            self.assertEqual(replay['requestDigest'], admitted['requestDigest'])
            completed = self.settled(admitted['operationId'])
            scenario.update(completedResult=copy.deepcopy(completed['result']), completed=copy.deepcopy(completed),
                            completedObserved=self._times())
            self.assertEqual(completed['effectVerification'], 'unverified')
            self.assertEqual(completed['result']['evidenceKind'], 'simulation')
            self.assertEqual(completed['result']['output']['value'], value)
            self.assertTrue(completed['result']['output']['effectCommitted'])
            with self.relay.lock:
                recovered_frames = [frame for frame, _ in self.relay.requests[request_count_before_restart:]]
            self.assertTrue(any(frame.payload == operation.reference.payload(Opcode.QUERY)
                                for frame in recovered_frames), 'Recovery must query the original endpoint receipt')
            again = self.cli('invoke', '--request-file', str(request_file))
            scenario.update(secondReplay=copy.deepcopy(again), secondReplayObserved=self._times())
            self.assertEqual(again['operationId'], admitted['operationId'])
            self.assertEqual(again['result'], completed['result'])
            self.assertEqual(self.database('SELECT payload, tx_sequence FROM ep_commands WHERE operation_id=?',
                                           (admitted['operationId'],)), before)
            self.assertEqual(len(self.relay.op_frames()), index)
            self.assertEqual(self.relay.op_frames()[-1][1], original_wire)
            observed = self.cli('observe', instance, 'value', '--max-age-ms', '10000', '--evidence-kind', 'simulation')
            scenario.update(observation=copy.deepcopy(observed), observationObserved=self._times())
            self.assertEqual(observed['value'], value)
            self.assertEqual(observed['acquisition']['ticksMs'], completed['result']['output']['sampleTick'])
            scenario.update(passed=True, executionState=completed['executionState'],
                completedResult=completed['result'], observedValue=observed['value'],
                replayOperationId=again['operationId'], forwardedOpCount=len(self.relay.op_frames()))
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


class ReadOnlyObserverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hms-observer-lock-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'observer.db'
        with contextlib.closing(sqlite3.connect(self.path)) as database:
            database.execute('CREATE TABLE value(number INTEGER NOT NULL)')
            database.execute('INSERT INTO value VALUES (37)')
            database.commit()

    def test_real_exclusive_lock_retries_read_then_closes_every_connection(self):
        writer = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.addCleanup(writer.close)
        writer.execute('BEGIN EXCLUSIVE')
        observed_busy = threading.Event()
        opened, closed, writer_errors = [], [], []
        original_connect = sqlite3.connect

        class ObservedConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, *args):
                try:
                    return self.connection.execute(*args)
                except sqlite3.OperationalError as error:
                    if error.sqlite_errorcode & 0xff == sqlite3.SQLITE_BUSY:
                        observed_busy.set()
                    raise

            def close(self):
                self.connection.close()
                closed.append(self)

        def connect(*args, **kwargs):
            connection = ObservedConnection(original_connect(*args, **kwargs))
            opened.append(connection)
            return connection

        def release_writer():
            try:
                if not observed_busy.wait(2):
                    raise AssertionError('reader did not encounter the controlled writer lock')
                writer.execute('ROLLBACK')
            except BaseException as error:
                writer_errors.append(error)

        thread = threading.Thread(target=release_writer)
        thread.start()
        try:
            report = {}
            with patch.object(sqlite3, 'connect', connect):
                self.assertEqual(readonly_rows(self.path, 'SELECT number FROM value', report=report), [(37,)])
        finally:
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(writer_errors, [])
        self.assertGreaterEqual(report['busyRetries'], 1)
        self.assertEqual(report['attempts'], len(opened))
        self.assertEqual(closed, opened)

    def test_unreleased_real_lock_exhausts_observer_budget_as_original_busy_error(self):
        with contextlib.closing(sqlite3.connect(self.path, isolation_level=None)) as writer:
            writer.execute('BEGIN EXCLUSIVE')
            report = {}
            try:
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    readonly_rows(self.path, 'SELECT number FROM value', timeout=.05, report=report)
                self.assertEqual(caught.exception.sqlite_errorcode & 0xff, sqlite3.SQLITE_BUSY)
                self.assertFalse(report['succeeded'])
                self.assertGreaterEqual(report['elapsedSeconds'], .05)
            finally:
                writer.execute('ROLLBACK')
        self.assertEqual(readonly_rows(self.path, 'SELECT number FROM value'), [(37,)])

    def test_other_sql_errors_propagate_and_observer_cannot_write(self):
        for query, expected in [('SELECT number FROM missing_table', sqlite3.SQLITE_ERROR),
                                ('UPDATE value SET number=99', sqlite3.SQLITE_READONLY)]:
            with self.subTest(query=query):
                report = {}
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    readonly_rows(self.path, query, report=report)
                self.assertEqual(caught.exception.sqlite_errorcode & 0xff, expected)
                self.assertEqual(report['attempts'], 1)
                self.assertEqual(report['busyRetries'], 0)
        self.assertEqual(readonly_rows(self.path, 'SELECT number FROM value'), [(37,)])

    def test_locked_error_is_not_treated_as_busy(self):
        error = sqlite3.OperationalError('controlled SQLITE_LOCKED')
        error.sqlite_errorcode = sqlite3.SQLITE_LOCKED
        report = {}
        with patch.object(sqlite3, 'connect', side_effect=error) as connect:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                readonly_rows(self.path, 'SELECT number FROM value', report=report)
        self.assertIs(caught.exception, error)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(report['busyRetries'], 0)

    def test_admission_counts_and_key_use_one_snapshot_during_writer_commit(self):
        # WAL permits the writer to commit while this SELECT retains its read
        # snapshot. A view pauses after reading an operations row and before
        # the remaining count/key subqueries; no production code is involved.
        tables = ('operation_rows', 'claims', 'ep_commands', 'pr_procedures', 'pr_keys')
        with contextlib.closing(sqlite3.connect(self.path)) as database:
            self.assertEqual(database.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
            for table in tables:
                database.execute('CREATE TABLE ' + table + '(number INTEGER NOT NULL)')
                database.execute('INSERT INTO ' + table + ' VALUES (1)')
            database.execute('CREATE TABLE replay_keys(namespace TEXT, caller_key TEXT)')
            database.execute('CREATE VIEW operations AS SELECT number FROM operation_rows WHERE hold_reader(number)=1')
            database.commit()
        reader_paused, writer_committed = threading.Event(), threading.Event()
        writer_errors = []
        original_connect = sqlite3.connect

        def hold_reader(number):
            if not reader_paused.is_set():
                reader_paused.set()
                if not writer_committed.wait(2):
                    raise AssertionError('controlled writer did not commit during the SELECT')
            return 1

        def connect(*args, **kwargs):
            database = original_connect(*args, **kwargs)
            database.create_function('hold_reader', 1, hold_reader)
            return database

        def write_after_reader_pauses():
            try:
                if not reader_paused.wait(2):
                    raise AssertionError('reader did not reach the operations subquery')
                with contextlib.closing(original_connect(self.path)) as database:
                    for table in tables:
                        database.execute('INSERT INTO ' + table + ' VALUES (2)')
                    database.execute('INSERT INTO replay_keys VALUES (?,?)', ('namespace', 'key'))
                    database.commit()
                writer_committed.set()
            except BaseException as error:
                writer_errors.append(error)

        thread = threading.Thread(target=write_after_reader_pauses)
        thread.start()
        try:
            with patch.object(sqlite3, 'connect', connect):
                report = {}
                self.assertEqual(admission_snapshot(self.path, 'namespace', 'key', procedures=True, report=report),
                                 ((1, 1, 1, 1, 1), False))
                self.assertTrue(writer_committed.is_set())
                self.assertEqual(report['attempts'], 1)
                self.assertEqual(admission_snapshot(self.path, 'namespace', 'key', procedures=True),
                                 ((2, 2, 2, 2, 2), True))
                self.assertEqual(admission_snapshot(self.path, 'namespace', 'key'), ((2, 2, 2), True))
        finally:
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(writer_errors, [])


if __name__ == '__main__':
    unittest.main()
