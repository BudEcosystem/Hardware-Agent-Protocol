"""Test-only launcher: independent C lifetime, exact byte relay and host SIGKILL.

ReplyGate is copied from the original HMS tests/test_endpoint_cli.py; this file
adds bounded JSON control for Harness tests. It never invokes an HMS action.
"""
from contextlib import closing
import json
import os
import select
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT, BINARY, BASE = map(Path, sys.argv[1:4])
sys.path.insert(0, str(ROOT))
from hms.endpoint_wire import Execution, Opcode, Operation, Receipt, Request, decode_response
from protocol.serial.frame import Decoder, encode

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


class Launcher:
    def __init__(self):
        self.state, self.socket = BASE / 'state', BASE / 'hctl.sock'
        self.host_wire, relay_host = socket.socketpair()
        relay_native, native_wire = socket.socketpair()
        self.daemon = None
        self.crashes = {}
        self.fixture = subprocess.Popen([str(BINARY), '--boot', '73'],
            stdin=native_wire, stdout=native_wire, stderr=subprocess.PIPE)
        native_wire.close()
        self.relay = ReplyGate(relay_host, relay_native)

    def database(self, query, params=(), *, deadline=None):
        """Bound only read-only evidence contention; never replay an HMS request."""
        assert query.lstrip().upper().startswith('SELECT ')
        deadline = time.monotonic() + 5 if deadline is None else deadline
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, 'Read-only evidence deadline expired'
            try:
                with closing(sqlite3.connect(f'file:{self.state / "authority.db"}?mode=ro',
                                             uri=True, timeout=min(remaining, 0.1))) as db:
                    return db.execute(query, params).fetchall()
            except sqlite3.OperationalError as error:
                if error.sqlite_errorcode not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                    raise
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))

    def start(self, create=False):
        assert self.daemon is None
        args = [sys.executable, '-B', '-m', 'hms', 'serve', '--socket', str(self.socket),
                '--state-dir', str(self.state), '--endpoint-fd', str(self.host_wire.fileno())]
        if create:
            args.append('--init-compact-simulation')
        self.daemon = subprocess.Popen(args, cwd=ROOT, pass_fds=(self.host_wire.fileno(),),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ready, _, _ = select.select([self.daemon.stdout], [], [], 8)
        assert ready, 'No bounded daemon readiness'
        line = self.daemon.stdout.readline()
        assert line, 'Daemon exited before readiness'
        result = json.loads(line)
        assert result['ready'] and result['deployment'] == 'simulation:compact'
        info = self.socket.lstat()
        assert stat.S_ISSOCK(info.st_mode)
        self.socket_identity = (info.st_dev, info.st_ino)
        assert self.fixture.poll() is None
        return dict(socket=str(self.socket), deployment=result['deployment'], endpointPid=self.fixture.pid)

    def crash(self, operation_id):
        assert self.relay.gated.wait(3), 'Endpoint did not answer OP'
        assert self.relay.error is None
        frame, wire = self.relay.op_frames()[-1]
        operation = Operation.parse(frame.payload)
        reply, reply_wire = self.relay.gated_reply
        receipt = decode_response(reply, Request(frame), operation=operation, simulator_only=True)
        assert isinstance(receipt, Receipt) and receipt.execution in {Execution.QUEUED, Execution.RUNNING}
        daemon, self.daemon = self.daemon, None
        daemon.kill()
        _, error = daemon.communicate(timeout=3)
        assert daemon.returncode == -signal.SIGKILL, repr(error)
        assert self.fixture.poll() is None, 'Endpoint died with host'
        assert self.database('SELECT payload,tx_sequence,receipt FROM ep_commands WHERE operation_id=?',
                             (operation_id,)) == [(frame.payload, frame.sequence, None)]
        info = self.socket.lstat()
        assert stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self.socket_identity
        self.socket.unlink()  # Only our reaped daemon's verified stale inode.
        with self.relay.lock:
            request_count = len(self.relay.requests)
        result = dict(operationId=operation_id, endpointPid=self.fixture.pid, endpointAlive=True,
            nativeExecution=receipt.execution.name.lower(), receiptAbsent=True,
            opWireHex=wire.hex(), replyWireHex=reply_wire.hex(), sequence=frame.sequence,
            requestDigest='sha256:'+operation.reference.intent_digest.hex(), requestCount=request_count)
        self.crashes[operation_id] = result
        return result

    def evidence(self, operation_id):
        deadline = time.monotonic() + 8
        while self.database('SELECT retired FROM ep_commands WHERE operation_id=?', (operation_id,), deadline=deadline) != [(1,)]:
            assert time.monotonic() < deadline, 'No bounded endpoint retirement'
            assert self.relay.error is None
            time.sleep(0.01)
        rows = self.database('SELECT payload,tx_sequence FROM ep_commands WHERE operation_id=?', (operation_id,), deadline=deadline)
        assert len(rows) == 1
        payload, sequence = rows[0]
        operation = Operation.parse(payload)
        with self.relay.lock:
            requests, responses = list(self.relay.requests), list(self.relay.responses)
        matches = [(f, raw) for f, raw in requests if f.payload == payload]
        assert len(matches) == 1 and matches[0][0].sequence == sequence
        op_frames = [(f, raw) for f, raw in requests if f.payload[1] == Opcode.OP]
        retained = []
        for (raw,) in self.database("SELECT wire FROM ep_packets WHERE direction='tx' ORDER BY id", deadline=deadline):
            decoder = Decoder()
            for octet in raw:
                event = decoder.feed(octet)
                if event is not None:
                    assert event[0] == 'frame'
                    if event[1].payload[1] == Opcode.OP:
                        retained.append(raw)
        assert retained == [raw for _, raw in op_frames], 'Actual OP handoffs differ from durable reservation packets'
        by_sequence = {f.sequence: f for f, _ in requests}
        completed = None
        for frame, raw in responses:
            request = by_sequence.get(int.from_bytes(frame.payload[2:6], 'big'))
            if request is None or request.payload not in (payload, operation.reference.payload(Opcode.QUERY)):
                continue
            receipt = decode_response(frame, Request(request), operation=operation, simulator_only=True)
            if isinstance(receipt, Receipt) and receipt.execution == Execution.COMPLETED:
                assert receipt.evidence_kind == 5 and receipt.verification == 0
                assert len(receipt.result) == 12
                completed = dict(execution='completed', evidenceKind='simulation', verification='unverified',
                    heldResources=receipt.held_resources, sampleTick=int.from_bytes(receipt.result[:8], 'big'),
                    value=int.from_bytes(receipt.result[8:], 'big'), resultHex=receipt.result.hex(), wireHex=raw.hex())
        assert completed is not None and completed['heldResources'] == 0
        assert not (self.state / 'simulated-plant.db').exists()
        crash = self.crashes.get(operation_id)
        queried = crash is not None and any(f.payload == operation.reference.payload(Opcode.QUERY)
                    for f, _ in requests[crash['requestCount']:])
        if crash is not None:
            assert queried and matches[0][1].hex() == crash['opWireHex']
        return dict(operationId=operation_id, requestDigest='sha256:'+operation.reference.intent_digest.hex(),
            endpointPid=self.fixture.pid, endpointAlive=self.fixture.poll() is None, totalOpFrames=len(op_frames),
            operationOpFrames=len(matches), retainedEqualsForwarded=True, retired=True, noSQLitePlant=True,
            queriedAfterRestart=queried, opWireHex=matches[0][1].hex(), sequence=sequence,
            nativeReceipt=completed, crash=crash,
            frames=dict(requests=[raw.hex() for _, raw in requests], responses=[raw.hex() for _, raw in responses]))

    def diagnostics(self):
        """Read-only failure evidence; no refresh, command, admission or replay."""
        before = dict(monotonicNs=time.monotonic_ns(), unixNs=time.time_ns())
        deadline = time.monotonic() + 5
        result = dict(before=before, endpointPid=self.fixture.pid,
                      endpointExit=self.fixture.poll(), daemonPid=self.daemon.pid if self.daemon else None,
                      daemonExit=self.daemon.poll() if self.daemon else None)
        queries = {
            'endpointState': 'SELECT document FROM ep_state',
            'presence': 'SELECT instance,session,expires_ms,adapter FROM reg_presence',
            'commands': 'SELECT operation_id,tx_sequence,retired,retire_intent,receipt IS NULL FROM ep_commands',
            'operations': 'SELECT id,state FROM operations',
        }
        for name, query in queries.items():
            try:
                rows = self.database(query, deadline=deadline)
                result[name] = [json.loads(row[0]) for row in rows] if name == 'endpointState' else rows
            except Exception as error:
                result[name] = dict(readError=type(error).__name__, message=str(error))
        with self.relay.lock:
            result['frames'] = dict(requests=[raw.hex() for _, raw in self.relay.requests[-64:]],
                                   responses=[raw.hex() for _, raw in self.relay.responses[-64:]])
            result['relayError'] = repr(self.relay.error) if self.relay.error else None
        for name, process in [('daemonStderr', self.daemon), ('endpointStderr', self.fixture)]:
            chunks = []
            if process is not None:
                while select.select([process.stderr], [], [], 0)[0]:
                    block = os.read(process.stderr.fileno(), 4096)
                    if not block:
                        break
                    chunks.append(block)
                    if sum(map(len, chunks)) >= 65536:
                        break
            result[name] = b''.join(chunks).decode('utf-8', errors='replace')
        result['after'] = dict(monotonicNs=time.monotonic_ns(), unixNs=time.time_ns())
        return result

    def close(self):
        self.relay.release.set()
        errors = []
        if self.daemon is not None:
            daemon, self.daemon = self.daemon, None
            if daemon.poll() is None:
                daemon.terminate()
            try:
                _, error = daemon.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                daemon.kill()
                _, error = daemon.communicate(timeout=3)
                errors.append('Daemon did not quiesce')
            if daemon.returncode != 0:
                errors.append(f'Daemon exit {daemon.returncode}: {error!r}')
        self.host_wire.close()
        self.relay.close()
        try:
            _, error = self.fixture.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.fixture.kill()
            _, error = self.fixture.communicate(timeout=3)
            errors.append('Native fixture did not exit on socket close')
        if self.fixture.returncode != 0:
            errors.append(f'Endpoint exit {self.fixture.returncode}: {error!r}')
        assert not errors, errors
        return dict(daemonClosed=True, endpointExit=self.fixture.returncode)


def main():
    launcher = Launcher()
    closed = False
    try:
        print(json.dumps({'ready': launcher.start(create=True)}), flush=True)
        for line in sys.stdin:
            command = json.loads(line)
            try:
                method = command['method']
                if method == 'arm':
                    launcher.relay.arm()
                    result = {'armed': True}
                elif method == 'crash':
                    result = launcher.crash(command['operationId'])
                elif method == 'restart':
                    launcher.relay.release.set()
                    result = launcher.start()
                elif method == 'evidence':
                    result = launcher.evidence(command['operationId'])
                elif method == 'diagnostics':
                    result = launcher.diagnostics()
                elif method == 'close':
                    result = launcher.close()
                    closed = True
                else:
                    raise ValueError('Unknown test command')
                print(json.dumps({'result': result}), flush=True)
                if closed:
                    break
            except BaseException as error:
                traceback.print_exc(file=sys.stderr)
                print(json.dumps({'error': str(error)}), flush=True)
    finally:
        if not closed:
            launcher.close()


if __name__ == '__main__':
    main()
