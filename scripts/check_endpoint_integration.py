#!/usr/bin/env python3
"""Exercise original Python/C codecs through real framed pipes and test-only control.

This deliberately bypasses the host journal to test the endpoint boundary alone.
It is not a commissioned adapter, durable dispatch path, or physical clock bridge.
"""
import argparse
from dataclasses import asdict, replace
import datetime
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hms.endpoint_wire import (Control, Execution, Hello, Opcode, Operation, Receipt,
                               Refusal, Request, Retired, Status, WireError, arm, bind,
                               decode_response, hello, revoke)
from protocol.serial.frame import Decoder, Frame, encode

VECTORS = json.loads((ROOT / 'protocol/endpoint/vectors.json').read_text())
PAYLOADS = {v['name']: bytes.fromhex(v['payload_hex']) for v in VECTORS['wireVectors']}
OP = Operation.parse(PAYLOADS['op_scaled_pair'])
MANIFEST = bytes.fromhex(VECTORS['fixtureDigests']['installedManifest'])
CONTEXT = bytes.fromhex(VECTORS['fixtureDigests']['hostContext'])


def check(condition, message='Endpoint integration invariant failed'):
    if not condition:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_value(value):
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(type(value).__name__)


class Probe:
    def __init__(self, binary, name, traces):
        self.control, child = socket.socketpair()
        self.control.settimeout(5)
        try:
            self.process = subprocess.Popen([str(binary), '--test-control-fd', str(child.fileno())],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, pass_fds=(child.fileno(),), cwd=ROOT)
        finally:
            child.close()
        self.decoder = Decoder()
        self.sequence, self.last_response, self.boot = 1, 0, 42
        self.trace = {'name': name, 'events': []}
        traces.append(self.trace)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.process.stdin.close()
        self.control.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        error = self.process.stderr.read().decode(errors='replace')
        self.process.stdout.close()
        self.process.stderr.close()
        self.trace['process_exit'] = self.process.returncode
        self.trace['stderr'] = error
        if kind is None:
            check(self.process.returncode == 0 and not error, 'Native process failed: ' + error)

    def clock(self, tick):
        self.command(1, tick)

    def command(self, opcode, value=0):
        self.control.sendall(struct.pack('>BQ', opcode, value))
        data = bytearray()
        while len(data) < 9:
            part = self.control.recv(9 - len(data))
            check(part, 'Native test control closed before acknowledgment')
            data.extend(part)
        received, result = struct.unpack('>BQ', data)
        check(received == opcode, 'Native test control refused command')
        if opcode not in (4, 5):
            check(result == value, 'Native test control acknowledgment mismatch')
        self.trace['events'].append({'test_control': opcode, 'value': value, 'acknowledged': result})
        return result

    def counts(self):
        return self.command(4), self.command(5)

    def frame(self, payload, *, boot=None):
        session = 0 if payload == hello() else self.boot if boot is None else boot
        result = Frame(1, 0, session, self.sequence, payload)
        self.sequence += 1
        return result

    def exchange(self, frame, *, operation=OP, decode=True, drop=False):
        request = Request(frame)
        wire = encode(frame)
        # Fragment every request across the framing/header boundary. This is a
        # real process stream, not a direct call into the C application handler.
        for part in (wire[:1], wire[1:19], wire[19:]):
            self.process.stdin.write(part)
            self.process.stdin.flush()
        deadline, response = time.monotonic() + 5, None
        while response is None:
            remaining = deadline - time.monotonic()
            check(remaining > 0 and select.select([self.process.stdout], [], [], remaining)[0], 'Native response timed out')
            data = os.read(self.process.stdout.fileno(), 430)
            check(data, 'Native output closed before response')
            for byte in data:
                event = self.decoder.feed(byte)
                if event:
                    check(event[0] == 'frame' and response is None, 'Invalid/extra native response')
                    response = event[1]
        check(response.sequence > self.last_response, 'Endpoint response counter regressed/reused')
        self.last_response = response.sequence
        event = {'request': {**asdict(frame), 'payload': frame.payload.hex()},
                 'response': {**asdict(response), 'payload': response.payload.hex()}}
        self.trace['events'].append(event)
        if drop:
            event['deliberately_discarded_reply'] = True
            return None
        if not decode:
            event['raw_only'] = True
            return response, request
        result = decode_response(response, request, operation=operation, simulator_only=True)
        event['validated_type'] = type(result).__name__
        event['validated'] = asdict(result)
        return result

    def request(self, payload, **kwargs):
        return self.exchange(self.frame(payload), **kwargs)

    def query(self, operation=OP):
        return self.request(operation.reference.payload(Opcode.QUERY), operation=operation)

    def setup(self):
        state = self.request(hello())
        check(isinstance(state, Hello) and state.boot_epoch == 42 and state.control.flags == 57)
        check(state.manifest_digest == MANIFEST and state.control.call_high_water == 0)
        bound = self.request(bind(1, 7, MANIFEST, CONTEXT))
        check(isinstance(bound, Control) and bound.state == 1 and bound.control_generation == 2)
        armed = self.request(arm(2, 7, CONTEXT, 2000))
        check(armed.state == 2 and armed.armed_until == 2000)


def run(binary):
    traces = []
    with Probe(binary, 'lost_reply_query_and_retirement', traces) as p:
        p.setup()
        p.request(OP.payload(), drop=True)
        queued = p.query()
        check(queued.execution == Execution.QUEUED and not queued.may_have_acted and queued.held_resources == 5)
        p.clock(1150)
        running = p.query()
        check(running.execution == Execution.RUNNING and running.may_have_acted)
        p.clock(1250)
        completed = p.query()
        check(completed.execution == Execution.COMPLETED and completed.held_resources == 5)
        check(completed.verification == 0 and int.from_bytes(completed.result, 'big', signed=True) == 975)
        check(p.request(OP.reference.payload(Opcode.RETIRE)).status == Status.BUSY)
        p.clock(1251)
        quiet = p.query()
        check(quiet.held_resources == 0 and quiet.revision > completed.revision)
        check(isinstance(p.request(OP.reference.payload(Opcode.RETIRE)), Retired))
        check(p.query().status == Status.OLD_OR_FORGOTTEN and p.counts() == (1, 1))
        state = p.request(hello())
        check(state.control.call_high_water == 1 and state.fence_floors == (5, 0, 9, 0, 0, 0, 0, 0))

    with Probe(binary, 'explicit_duplicate_and_changed_bytes_conflict', traces) as p:
        p.setup()
        original = p.frame(OP.payload())
        first = p.exchange(original)
        # Deliberate adversarial duplicate; this is not an adapter retry policy.
        check(p.exchange(original) == first and p.counts() == (0, 0))
        conflict = replace(OP, arguments=struct.pack('>ii', 1001, -25))
        check(p.request(conflict.payload(), operation=conflict).status == Status.CONFLICT)
        p.clock(1150)
        check(p.exchange(original).execution == Execution.RUNNING and p.counts() == (1, 0))

    with Probe(binary, 'future_cancel_is_not_tombstone_then_queued_cancel', traces) as p:
        p.setup()
        check(p.request(OP.reference.payload(Opcode.CANCEL)).status == Status.NOT_SEEN)
        check(p.request(OP.payload()).execution == Execution.QUEUED)
        canceled = p.request(OP.reference.payload(Opcode.CANCEL))
        check(canceled.execution == Execution.CANCELED and canceled.cancellation == 4 and not canceled.may_have_acted)
        check(canceled.held_resources == 0)
        p.clock(1150)
        check(p.counts() == (0, 0) and p.query() == canceled)

    with Probe(binary, 'exclusive_start_cutoff', traces) as p:
        p.setup()
        p.request(OP.payload())
        p.clock(1200)
        rejected = p.query()
        check(rejected.execution == Execution.REJECTED_BEFORE_START and rejected.reason == 1)
        check(not rejected.may_have_acted and rejected.held_resources == 0 and p.counts() == (0, 0))

    with Probe(binary, 'running_cancel_separate_from_quiescence', traces) as p:
        p.setup()
        p.request(OP.payload())
        p.clock(1150)
        requested = p.request(OP.reference.payload(Opcode.CANCEL))
        check(requested.execution == Execution.RUNNING and requested.cancellation == 1 and requested.held_resources == 5)
        p.clock(1151)
        canceled = p.query()
        check(canceled.execution == Execution.CANCELED and canceled.cancellation == 4 and canceled.held_resources == 5)
        p.clock(1152)
        check(p.query().held_resources == 0 and p.counts() == (1, 0))

    with Probe(binary, 'completion_wins_cancellation', traces) as p:
        p.setup()
        p.command(6, 1)
        p.request(OP.payload())
        p.clock(1150)
        p.request(OP.reference.payload(Opcode.CANCEL))
        p.clock(1151)
        done = p.query()
        check(done.execution == Execution.COMPLETED and done.cancellation == 2 and done.held_resources == 5)
        check(p.request(OP.reference.payload(Opcode.CANCEL)) == done and p.counts() == (1, 1))

    with Probe(binary, 'immutable_runtime_cutoff_under_arm_renewal', traces) as p:
        p.setup()
        p.command(6, 6)
        p.request(OP.payload())
        p.clock(1150)
        p.request(arm(2, 7, CONTEXT, 2500))
        p.clock(1350)
        failed = p.query()
        check(failed.execution == Execution.FAILED and failed.reason == 2 and failed.held_resources == 5)
        check(p.request(hello()).control.armed_until == 2500)
        p.clock(1351)
        check(p.query().held_resources == 0 and p.counts() == (1, 0))

    with Probe(binary, 'revoke_drain_retire_rebind_preserves_floors', traces) as p:
        p.setup()
        p.request(OP.payload())
        p.clock(1150)
        revoked = p.request(revoke(2, 7))
        check(revoked.control_generation == 3 and revoked.state == 3 and revoked.held_resources == 5)
        check(p.request(arm(3, 7, CONTEXT, 2500)).status == Status.BAD_STATE)
        p.clock(1151)
        failed = p.query()
        check(failed.execution == Execution.FAILED and failed.reason == 6 and failed.held_resources == 5)
        p.clock(1152)
        check(p.query().held_resources == 0 and p.request(hello()).control.state == 0)
        check(p.request(bind(3, 8, MANIFEST, CONTEXT)).status == Status.BUSY)
        p.request(OP.reference.payload(Opcode.RETIRE))
        bound = p.request(bind(3, 8, MANIFEST, CONTEXT))
        check(bound.control_generation == 4 and bound.call_high_water == 1)
        state = p.request(hello())
        check(state.fence_floors == (5, 0, 9, 0, 0, 0, 0, 0) and p.counts() == (1, 0))

    with Probe(binary, 'qualified_synthetic_reset_loses_receipt_not_effect_history', traces) as p:
        p.setup()
        p.request(OP.payload())
        p.clock(1150)
        p.clock(1250)
        check(p.counts() == (1, 1))
        p.command(2, 43)
        p.last_response = 0
        p.sequence = 1
        state = p.request(hello())
        check(state.boot_epoch == 43 and state.control.state == 0 and state.control.flags & 34 == 34)
        check(state.control.call_high_water == 0 and p.counts() == (1, 1))
        response, request = p.exchange(p.frame(OP.reference.payload(Opcode.QUERY), boot=42), decode=False)
        check(response.session == 43 and response.payload[6] == Status.BOOT_MISMATCH)
        try:
            decode_response(response, request, operation=OP, simulator_only=True)
        except WireError:
            p.trace['old_host_outcome'] = 'unresolved; no host claim release is established by this test'
        else:
            raise AssertionError('Reset mismatch accepted as old receipt')
        p.boot = 43
        check(p.request(bind(1, 7, MANIFEST, CONTEXT)).status == Status.RECONCILIATION_REQUIRED)

    with Probe(binary, 'clock_regression_latches_fault_and_unknown_terminal_time', traces) as p:
        p.setup()
        p.request(OP.payload())
        p.clock(1150)
        p.clock(1100)
        failed = p.query()
        check(failed.execution == Execution.FAILED and failed.reason == 7 and failed.terminal_at is None)
        state = p.request(hello())
        check(state.control.state == 4 and state.control.flags & 32 and not state.control.flags & 16)
        p.command(3, 25)
        check(p.request(hello()).control.state == 4 and p.counts() == (1, 0))

    with Probe(binary, 'maximum_arguments_resources_and_result', traces) as p:
        p.setup()
        operation = Operation.parse(PAYLOADS['op_maximum_192_bytes'])
        check(len(operation.payload()) == 192)
        check(p.request(operation.payload(), operation=operation).held_resources == 255)
        p.clock(1450)
        p.clock(1550)
        done = p.query(operation)
        check(done.execution == Execution.COMPLETED and done.result == bytes(range(32)) and done.held_resources == 255)
        p.clock(1551)
        check(p.query(operation).held_resources == 0 and p.counts() == (1, 1))

    with Probe(binary, 'invalid_driver_evidence_remains_unknown_and_claimed', traces) as p:
        p.setup()
        p.command(6, 4)
        p.request(OP.payload())
        p.clock(1150)
        p.clock(1250)
        unknown = p.query()
        check(unknown.execution == Execution.OUTCOME_UNKNOWN and unknown.held_resources == 5 and unknown.may_have_acted)
        check(unknown.verification != 1 and p.request(hello()).control.state == 4)
        check(p.request(OP.reference.payload(Opcode.RETIRE)).status == Status.BUSY)

    with Probe(binary, 'callback_crosses_cutoff_no_backdated_completion', traces) as p:
        p.setup()
        p.request(OP.payload())
        p.clock(1150)
        p.command(6, 8)
        p.clock(1340)
        unknown = p.query()
        check(unknown.execution == Execution.OUTCOME_UNKNOWN and unknown.reason == 2)
        check(unknown.held_resources == 5 and unknown.may_have_acted and unknown.result == b'')
        check(unknown.terminal_at is None and p.counts() == (1, 1))
        check(p.request(hello()).control.now == 1360)
    return traces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, default=ROOT / 'artifacts/verification/endpoint-native-build/endpoint-pipe')
    parser.add_argument('--build-receipt', type=Path, default=ROOT / 'artifacts/verification/endpoint-native.json')
    args = parser.parse_args()
    binary = args.executable.resolve()
    build_path = args.build_receipt.resolve()
    build_hash = sha(build_path)
    build = json.loads(build_path.read_text())
    check(build['schema'] == 'hms-endpoint-native/1' and build['passed'], 'Missing successful native build receipt')
    build_inputs = {item['path']: item['sha256'] for item in build['files']}
    compiled = [ROOT / 'protocol/serial/frame.c', ROOT / 'protocol/serial/frame.h',
                *sorted((ROOT / 'protocol/endpoint').glob('*.[ch]')),
                ROOT / 'tests/endpoint_fixture.c', ROOT / 'tests/endpoint_fixture.h', ROOT / 'tests/endpoint_pipe.c']
    for path in compiled:
        check(build_inputs.get(str(path.relative_to(ROOT))) == sha(path), 'Native build has stale/unpinned source: ' + str(path))
    for path, expected in build_inputs.items():
        check(sha(ROOT / path) == expected, 'Native build input changed: ' + path)
    binary_hash = sha(binary)
    check(any((ROOT / item['path']).resolve() == binary and item['sha256'] == binary_hash
              for item in build['outputs']), 'Executable is not the binary retained by the native build receipt')
    paths = [Path(__file__).resolve(), ROOT / 'hms/endpoint_wire.py', ROOT / 'tests/test_endpoint_wire.py',
             ROOT / 'protocol/serial/frame.py', ROOT / 'protocol/serial/frame.c', ROOT / 'protocol/serial/frame.h',
             ROOT / 'protocol/endpoint/vectors.json', ROOT / 'spec/11-endpoint-wire.md',
             *sorted((ROOT / 'protocol/endpoint').glob('*.[ch]')), *sorted((ROOT / 'tests').glob('endpoint_*.[ch]'))]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in paths}
    started = time.monotonic()
    traces = run(binary)
    check(hashes == {str(path.relative_to(ROOT)): sha(path) for path in paths}, 'Inputs changed during verification')
    check(sha(binary) == binary_hash and sha(build_path) == build_hash, 'Executable/build receipt changed during verification')
    for path, expected in build_inputs.items():
        check(sha(ROOT / path) == expected, 'Native build input changed during verification: ' + path)
    destination = ROOT / 'artifacts/verification'
    trace_path = destination / 'endpoint-integration-traces.json'
    trace_path.write_text(json.dumps(traces, indent=2, default=json_value) + '\n')
    artifact = {
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'passed': True,
        'argv': [sys.executable, *sys.argv], 'scenarios': len(traces),
        'elapsed_seconds': round(time.monotonic() - started, 6),
        'scope': 'Original Python codec and native C endpoint through real framed pipes; synthetic driver and test-control clock/reset/flags only.',
        'limitations': ['No hardware, UART, target execution, qualified NVM, real commissioning or independent stop',
                       'No durable host mapping, host-runtime adapter, authenticated route, clock translation or host recovery implementation',
                       'Explicit duplicate probes do not authorize automatic command retransmission',
                       'Synthetic dispatch/effect counters are external test observations; no physical atomicity or persistence proof'],
        'files': [{'path': path, 'sha256': digest} for path, digest in hashes.items()],
        'executable': {'path': str(binary), 'sha256': binary_hash},
        'native_build_receipt': {'path': str(build_path), 'sha256': build_hash},
        'outputs': [{'path': str(trace_path.relative_to(ROOT)), 'sha256': sha(trace_path)}],
    }
    (destination / 'endpoint-integration.json').write_text(json.dumps(artifact, indent=2) + '\n')
    print(json.dumps({'passed': True, 'scenarios': len(traces), 'artifact': 'artifacts/verification/endpoint-integration.json'}))


if __name__ == '__main__':
    main()
