#!/usr/bin/env python3
"""Compile and exercise only original installed synthetic scenario primitives.

The wire checks intentionally bypass host admission; Runtime authority and
durability have separate tests. No acquired code, target, peripheral or physical
port is executed. The fixture process is a native simulation, not an MCU emulator.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import shutil
import socket
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hms.endpoint_wire import (Control, Execution, Hello, Opcode, Operation, Reference,
                               Request, Retired, Status, arm, bind, decode_response, hello)
from protocol.serial.frame import Decoder, Frame, encode

BUILD = ROOT / 'artifacts/verification/endpoint-scenarios-build'
CORE = ['protocol/serial/frame.c', 'protocol/endpoint/endpoint.c', 'protocol/endpoint/link.c',
        'protocol/endpoint/scenario_fixture.c', 'tests/endpoint_scenarios_pipe.c']
FILES = CORE + ['protocol/serial/frame.h', 'protocol/serial/frame.py', 'protocol/endpoint/endpoint.h',
               'protocol/endpoint/link.h', 'protocol/endpoint/scenario_fixture.h',
               'protocol/endpoint/scenario-manifest.json', 'hms/endpoint_wire.py',
               'scripts/check_endpoint_scenarios.py']
COMMON = ['-std=c11', '-g', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-Wvla', '-fno-common']
PLAIN = COMMON + ['-O2']
SANITIZED = COMMON + ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
MANIFEST_BYTES = (ROOT / 'protocol/endpoint/scenario-manifest.json').read_bytes()
MANIFEST = json.loads(MANIFEST_BYTES)
MANIFEST_DIGEST = hashlib.sha256(MANIFEST_BYTES).digest()
CONTEXT = hashlib.sha256(b'HMS original scenario checker context v1').digest()


def check(value, message='Scenario invariant failed'):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def operation(primitive=0x1001, arguments=b'\x32', *, call=1, fence=1, now=1000):
    ref = Reference(2, 1, call, hashlib.sha256(struct.pack('>HI', primitive, call) + arguments).digest())
    return Operation(ref, primitive, 1 << (primitive - 0x1001), (fence,), arguments, 0,
                     now, now + 1000, now + 5500, 5000, now + 6000)


class Probe:
    def __init__(self, binary, name, traces, *, duplex=False, deterministic=True):
        self.control = None
        args = [str(binary)]
        passed = ()
        child_control = None
        if deterministic:
            self.control, child_control = socket.socketpair()
            self.control.settimeout(5)
            args += ['--test-control-fd', str(child_control.fileno())]
            passed = (child_control.fileno(),)
        self.wire = None
        child_wire = None
        if duplex:
            self.wire, child_wire = socket.socketpair()
        env = os.environ.copy()
        env['ASAN_OPTIONS'] = 'detect_leaks=1:halt_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        try:
            self.process = subprocess.Popen(args, cwd=ROOT, env=env,
                stdin=child_wire if duplex else subprocess.PIPE,
                stdout=child_wire if duplex else subprocess.PIPE,
                stderr=subprocess.PIPE, pass_fds=passed)
        finally:
            if child_control is not None:
                child_control.close()
            if child_wire is not None:
                child_wire.close()
        self.decoder = Decoder()
        self.sequence, self.response_sequence, self.boot = 1, 0, 42
        self.trace = {'name': name, 'duplex_socket': duplex, 'deterministic': deterministic, 'events': []}
        traces.append(self.trace)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if self.wire is not None:
            self.wire.close()
        else:
            self.process.stdin.close()
        if self.control is not None:
            self.control.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        stderr = self.process.stderr.read().decode('utf-8', 'replace')
        self.process.stderr.close()
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.trace.update(process_exit=self.process.returncode, stderr=stderr)
        if kind is None:
            check(self.process.returncode == 0 and not stderr, 'Native fixture failed: ' + stderr)

    def command(self, command, value=0, *, accepted=True):
        self.control.sendall(struct.pack('>BQ', command, value))
        result = bytearray()
        while len(result) < 9:
            part = self.control.recv(9 - len(result))
            check(part, 'Control closed early')
            result.extend(part)
        kind, answer = struct.unpack('>BQ', result)
        check(kind == (command if accepted else 255))
        if accepted and command not in (4, 5):
            check(answer == value)
        if not accepted:
            check(answer == 1)
        self.trace['events'].append({'control': command, 'argument': value, 'reply': [kind, answer]})
        return answer

    def clock(self, now):
        self.command(1, now)

    def counts(self):
        return self.command(4), self.command(5)

    def request(self, payload, *, op=None, raw=False, boot=None):
        frame = Frame(1, 0, 0 if payload == hello() else self.boot if boot is None else boot,
                      self.sequence, payload)
        self.sequence += 1
        request = None if raw else Request(frame)
        data = encode(frame)
        for part in (data[:1], data[1:13], data[13:]):
            if self.wire is not None:
                self.wire.sendall(part)
            else:
                self.process.stdin.write(part)
                self.process.stdin.flush()
        source = self.wire if self.wire is not None else self.process.stdout
        deadline, response = time.monotonic() + 5, None
        while response is None:
            left = deadline - time.monotonic()
            check(left > 0 and select.select([source], [], [], left)[0], 'Wire response timeout')
            chunk = os.read(source.fileno(), 430)
            check(chunk, 'Wire closed early')
            for byte in chunk:
                event = self.decoder.feed(byte)
                if event:
                    check(event[0] == 'frame' and response is None, 'Malformed/extra response')
                    response = event[1]
        check(response.sequence > self.response_sequence, 'Response sequence reuse')
        self.response_sequence = response.sequence
        self.trace['events'].append({'request': data.hex(), 'response': encode(response).hex()})
        if raw:
            check(response.payload[:2] == bytes([1, payload[1] | 0x80]))
            check(int.from_bytes(response.payload[2:6], 'big') == frame.sequence)
            return response
        return decode_response(response, request, operation=op, simulator_only=True)

    def setup(self):
        state = self.request(hello())
        check(isinstance(state, Hello) and state.boot_epoch == 42)
        check(state.incarnation.hex() == MANIFEST['incarnationHex'])
        check(state.firmware_digest.hex() == MANIFEST['firmwareDigest'])
        check(state.manifest_digest == MANIFEST_DIGEST and state.resource_count == 3)
        check(state.control.flags == 57 and state.control.call_high_water == 0)
        bound = self.request(bind(1, 1, MANIFEST_DIGEST, CONTEXT))
        check(isinstance(bound, Control) and bound.control_generation == 2)
        lease = state.control.now + 10000
        check(self.request(arm(2, 1, CONTEXT, lease)).armed_until == lease)
        return state

    def query(self, op):
        return self.request(op.reference.payload(Opcode.QUERY), op=op)

    def finish(self, op, start=1100):
        check(self.request(op.payload(), op=op).execution == Execution.QUEUED)
        self.clock(start)
        check(self.query(op).execution == Execution.RUNNING)
        self.clock(start + 100)
        done = self.query(op)
        check(done.execution == Execution.COMPLETED and done.held_resources == op.resource_mask)
        check(done.evidence_kind == 5 and done.verification == 0 and len(done.result) == 12)
        check(struct.unpack('>QI', done.result)[0] == start + 100)
        check(self.request(op.reference.payload(Opcode.RETIRE)).status == Status.BUSY)
        self.clock(start + 101)
        quiet = self.query(op)
        check(quiet.held_resources == 0 and quiet.result == done.result and quiet.revision > done.revision)
        check(isinstance(self.request(op.reference.payload(Opcode.RETIRE)), Retired))
        return done


def exercise(binary):
    traces = []
    with Probe(binary, 'three_scenarios_sequential_fixed_results', traces) as p:
        p.setup()
        inputs = [(0x1001, bytes([73]), 73), (0x1002, bytes([41]), 41),
                  (0x1003, b'\x02\x05partA', 1)]
        for i, (primitive, args, expected) in enumerate(inputs):
            op = operation(primitive, args, call=i+1, now=1000+i*300)
            done = p.finish(op, 1100+i*300)
            check(struct.unpack('>QI', done.result)[1] == expected)
        check(p.counts() == (3, 3))

    with Probe(binary, 'invalid_argument_encodings_leave_no_admission', traces) as p:
        p.setup()
        invalid = [(0x1001, b''), (0x1001, b'e'), (0x1001, b'\x01\x02'),
                   (0x1002, b'\xff'), (0x1003, b'\x03\x01x'), (0x1003, b'\x01\x00'),
                   (0x1003, b'\x01\x02x'), (0x1003, b'\x01\x41' + b'x'*65)]
        invalid += [(0x1003, bytes([1, len(bad)]) + bad) for bad in
                    (b'\x80', b'\xc0\x80', b'\xe0\x80\x80', b'\xed\xa0\x80',
                     b'\xf4\x90\x80\x80', b'\xf5\x80\x80\x80', b'\xf0\x9f\x98', b'\xc2x')]
        for primitive, args in invalid:
            op = operation(primitive, args)
            check(p.request(op.payload(), op=op).status == Status.BAD_ARGUMENT)
        check(p.request(hello()).control.call_high_water == 0 and p.counts() == (0, 0))

    with Probe(binary, 'utf8_scalar_and_exact_64_byte_identifiers', traces) as p:
        p.setup()
        for i, text in enumerate(('\U0001f642'*16, '\x00', '\u07ff\u0800\ud7ff\ue000\U0010ffff')):
            part = text.encode('utf-8')
            op = operation(0x1003, bytes([1, len(part)]) + part, call=i+1, fence=i+1, now=1000+i*300)
            check(struct.unpack('>QI', p.finish(op, 1100+i*300).result)[1] == i+1)

    with Probe(binary, 'inspection_limit_checked_before_next_effect', traces) as p:
        p.setup()
        p.command(7, 999999)
        op = operation(0x1003, b'\x01\x01x')
        check(struct.unpack('>QI', p.finish(op).result)[1] == 1000000)
        next_op = operation(0x1003, b'\x01\x01y', call=2, fence=2, now=1300)
        check(p.request(next_op.payload(), op=next_op).status == Status.BAD_STATE)
        check(p.counts() == (1, 1))

    with Probe(binary, 'duplicates_conflicts_and_result_acquisition_tick', traces) as p:
        p.setup(); op = operation()
        queued = p.request(op.payload(), op=op)
        check(p.request(op.payload(), op=op) == queued)
        changed = replace(op, arguments=b'\x33')
        check(p.request(changed.payload(), op=changed).status == Status.CONFLICT)
        p.command(7, 2, accepted=False)
        p.clock(1100); p.clock(1200)
        done = p.query(op); p.clock(1201); p.clock(1400)
        check(p.query(op).result == done.result and struct.unpack('>QI', done.result) == (1200, 50))
        check(p.counts() == (1, 1))

    for queued in (True, False):
        with Probe(binary, 'queued_cancel' if queued else 'running_cancel_separate_quiescence', traces) as p:
            p.setup(); op = operation()
            p.request(op.payload(), op=op)
            if not queued: p.clock(1100)
            canceled = p.request(op.reference.payload(Opcode.CANCEL), op=op)
            if not queued:
                check(canceled.cancellation == 1 and canceled.held_resources == 1)
                p.clock(1101); canceled = p.query(op)
            check(canceled.execution == Execution.CANCELED and not canceled.result and canceled.cancellation == 4)
            check(canceled.held_resources == (0 if queued else 1))
            p.clock(1102)
            check(p.query(op).held_resources == 0 and p.counts() == (0 if queued else 1, 0))

    with Probe(binary, 'completion_wins_cancel', traces) as p:
        p.setup(); p.command(6, 1); op = operation(0x1002, b'\x2a')
        p.request(op.payload(), op=op); p.clock(1100)
        p.request(op.reference.payload(Opcode.CANCEL), op=op); p.clock(1101)
        done = p.query(op)
        check(done.execution == Execution.COMPLETED and done.cancellation == 2)
        check(struct.unpack('>QI', done.result) == (1101, 42) and p.counts() == (1, 1))

    with Probe(binary, 'qualified_synthetic_reset_loses_receipt_not_external_count', traces) as p:
        p.setup(); op = operation(); p.request(op.payload(), op=op)
        p.clock(1100); p.clock(1200); check(p.counts() == (1, 1))
        p.command(2, 43); p.response_sequence = 0; p.boot = 43
        state = p.request(hello())
        check(state.boot_epoch == 43 and state.control.flags & 2 and state.control.held_resources == 0)
        check(p.query(op).status == Status.NOT_SEEN and p.counts() == (1, 1))
        check(p.request(bind(1, 1, MANIFEST_DIGEST, CONTEXT)).status == Status.RECONCILIATION_REQUIRED)

    for mode in (4, 5, 7):
        with Probe(binary, 'malformed_driver_mode_' + str(mode), traces) as p:
            p.setup(); p.command(6, mode); op = operation()
            p.request(op.payload(), op=op); p.clock(1100); p.clock(1200)
            receipt = p.query(op)
            check(receipt.execution == Execution.OUTCOME_UNKNOWN and receipt.verification != 1)
            check(receipt.held_resources == 1 and not receipt.result)

    with Probe(binary, 'late_callback_does_not_publish_backdated_success', traces) as p:
        p.setup(); p.command(6, 8)
        op = replace(operation(), latest_start=1150, latest_completion=1210, lease_until=1300)
        p.request(op.payload(), op=op); p.clock(1100); p.clock(1200)
        receipt = p.query(op)
        check(receipt.execution == Execution.OUTCOME_UNKNOWN and receipt.held_resources == 1)
        check(not receipt.result and p.counts() == (1, 1))

    with Probe(binary, 'runtime_cutoff_without_effect', traces) as p:
        p.setup(); p.command(6, 6); op = replace(operation(), max_run_ms=100)
        p.request(op.payload(), op=op); p.clock(1100); p.clock(1200)
        failed = p.query(op)
        check(failed.execution == Execution.FAILED and failed.reason == 2 and not failed.result)
        check(failed.held_resources == 1 and p.counts() == (1, 0))

    with Probe(binary, 'duplex_socket_normal_clock', traces, duplex=True, deterministic=False) as p:
        state = p.setup(); op = operation(now=state.control.now)
        p.request(op.payload(), op=op)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            receipt = p.query(op)
            if receipt.execution == Execution.COMPLETED and receipt.held_resources == 0: break
            time.sleep(0.01)
        check(receipt.execution == Execution.COMPLETED and receipt.held_resources == 0)
        tick, value = struct.unpack('>QI', receipt.result)
        check(receipt.started_at <= tick <= receipt.terminal_at and value == 50)
        check(isinstance(p.request(op.reference.payload(Opcode.RETIRE)), Retired))
    return traces


def main():
    check(MANIFEST_BYTES == json.dumps(MANIFEST, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())
    check(hashlib.sha256(MANIFEST['firmwareLabel'].encode()).hexdigest() == MANIFEST['firmwareDigest'])
    gcc = shutil.which('gcc')
    check(gcc, 'Trusted native GCC with sanitizers required')
    gcc = str(Path(gcc).resolve())
    before = {name: sha(ROOT / name) for name in FILES}
    BUILD.mkdir(parents=True, exist_ok=True)
    commands, outputs, results = [], [], []
    for name, flags in [('endpoint-scenarios-pipe', PLAIN), ('endpoint-scenarios-pipe-asan', SANITIZED)]:
        binary = BUILD / name
        command = [gcc, *flags, *CORE, '-o', str(binary)]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
        commands.append({'argv': command, 'exit_code': process.returncode,
                         'stdout': process.stdout.decode(), 'stderr': process.stderr.decode()})
        check(process.returncode == 0 and not process.stdout and not process.stderr, str(commands[-1]))
        traces = exercise(binary)
        trace_path = BUILD / (name + '-traces.json')
        trace_path.write_text(json.dumps(traces, indent=2) + '\n')
        outputs.extend((binary, trace_path))
        results.append({'binary': str(binary.relative_to(ROOT)), 'scenarios': len(traces),
                        'names': [t['name'] for t in traces], 'passed': True})
    check(before == {name: sha(ROOT / name) for name in FILES}, 'Sources changed during verification')
    receipt = {'schema': 'hms-endpoint-scenarios/1', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'passed': True, 'scope': 'Original C scenario callbacks through actual native framed pipes/socket, including ASan/UBSan; no host authority or target execution.',
        'files': [{'path': p, 'sha256': h} for p, h in before.items()],
        'outputs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in outputs],
        'compiler': {'path': gcc, 'sha256': sha(Path(gcc)), 'version': subprocess.check_output([gcc, '--version'], text=True).splitlines()[0]},
        'host': platform.platform(), 'plain_flags': PLAIN, 'sanitized_flags': SANITIZED,
        'commands': commands, 'results': results, 'manifest_sha256': MANIFEST_DIGEST.hex(),
        'control_protocol': {'size': 9, 'format': 'u8 command + u64be argument; same-sized acknowledgment',
            'commands': {'1': 'set clock + poll', '2': 'higher qualified synthetic boot; lose receipt, retain external synthetic values/counters',
                '3': 'set synthetic qualification flags; physical/stop flags refused', '4': 'dispatch count', '5': 'effect count',
                '6': 'mode 0..8, matching original fixture fault modes', '7': 'seed inspection count0..1000000 only with EMPTY slot'}},
        'limitations': ['No physical I/O, target binary, MCU emulator, acquired implementation, qualified NVM, independent stop or timing measurement.',
            'Native process CLOCK_MONOTONIC shares the host rate; bounded clock mapping and authority still belong to the host adapter.',
            'State/counters are synthetic process memory. Reset retention is a test observation, never physical durability.',
            'Normal OS writes can block; this fixture is not an embedded service-bound or UART driver qualification.',
            'Fixture tests bypass durable host admission. Runtime/CLI integration and crash recovery require their own receipts.',
            'Firmware digest is an explicit synthetic label; exact executable/source hashes are recorded separately.',
            'Canceled/failed work has no new result; only completed state commits produce the fixed12-byte sampleTick/value result.']}
    path = ROOT / 'artifacts/verification/endpoint-scenarios.json'
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passed': True, 'results': results, 'receipt': str(path.relative_to(ROOT)),
                      'binary': str(outputs[0].relative_to(ROOT)), 'binary_sha256': sha(outputs[0])}))


if __name__ == '__main__':
    main()
