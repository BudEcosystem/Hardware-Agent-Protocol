"""Independent adversarial review probes; no external SDK or hardware required."""
import fcntl
import json
import os
from pathlib import Path
import queue
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hms.client import Client
from hms.contracts import ContractError, MAX_BYTES
from hms.ipc import Server
from hms.journal import Context
from hms.mcp import MODERN, PREFIX, MAX_CALLS, Projection, TransportClosed, dumps
from hms.mcp_stdio import _Outbox, serve
from hms.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
META = {PREFIX + 'protocolVersion': MODERN, PREFIX + 'clientCapabilities': {}}


def wire(identifier, method='server/discover', params=None):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': {**(params or {}), '_meta': dict(META)}}


class ReviewBoundaries(unittest.TestCase):
    def process(self):
        process = subprocess.Popen([sys.executable, '-m', 'hms.mcp', '--socket', '/nonexistent/hms.sock'],
                                   cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def close():
            if not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        self.addCleanup(close)
        return process

    def exchange(self, process, payload):
        process.stdin.write(payload + b'\n')
        process.stdin.flush()
        self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'response timed out')
        return json.loads(process.stdout.readline())

    def test_malformed_metadata_does_not_kill_actual_stdio_process(self):
        process = self.process()
        malformed = [
            {**META, PREFIX + 'logLevel': value} for value in ({}, [], None, 7, True)
        ] + [{**META, PREFIX + 'clientCapabilities': value} for value in (
            [], False, None, {'sampling': []}, {'elicitation': False},
            {'extensions': {'com.example/foo': 2}}, {'sampling': {'tools': []}},
            {'extensions': {'unprefixed': {}}})] + [
            {**META, PREFIX + 'clientInfo': {'name': 'probe', 'version': '1', 'icons': [{}]}},
            {**META, PREFIX + 'clientInfo': {'name': 'probe', 'version': '1', 'title': []}},
            {**META, 'progressToken': {}}, {**META, 'bad/key/shape': 'value'},
        ]
        for index, meta in enumerate(malformed):
            with self.subTest(meta=meta):
                value = wire(index)
                value['params']['_meta'] = meta
                reply = self.exchange(process, dumps(value).encode())
                self.assertEqual(reply['id'], index)
                self.assertEqual(reply['error']['code'], -32602)
        value = wire(100)
        value['params']['_meta'][PREFIX + 'clientCapabilities'] = {
            'extensions': {'com.example/unknown': {'setting': 1}}, 'unknownFutureCapability': {'opaque': True}}
        value['params']['_meta'][PREFIX + 'clientInfo'] = {
            'name': 'posix:0', 'version': 'claimed-authority', 'unknownFutureField': {'opaque': True}}
        good = self.exchange(process, dumps(value).encode())
        self.assertEqual(good['result']['supportedVersions'][0], MODERN)
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(process.stderr.read(), b'')

    def test_malformed_json_does_not_reach_hardware_or_break_framing(self):
        process = self.process()
        for payload in (b'{"jsonrpc":"2.0","id":1,"id":2}', b'{"id":NaN}', b'\xff', b'{"x":-0}',
                        b'{"nested":{"duplicate":1,"duplicate":2}}', b'{"x":1e999}', b'[' * 35 + b']' * 35):
            reply = self.exchange(process, payload)
            self.assertEqual(reply['error']['code'], -32700)
            self.assertNotIn('Traceback', dumps(reply))
        self.assertIn('result', self.exchange(process, dumps(wire(99)).encode()))

    def test_missing_modern_metadata_is_not_inferred_after_valid_request(self):
        messages = queue.Queue()
        projection = Projection(None, messages.put_nowait)
        self.addCleanup(projection.close)
        for value in (wire(1), {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                      {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list', 'params': {'_meta': {}}}):
            projection.receive(dumps(value).encode())
        self.assertIn('result', messages.get_nowait())
        for identifier in (2, 3):
            reply = messages.get_nowait()
            self.assertEqual(reply['id'], identifier)
            self.assertEqual(reply['error']['code'], -32602)

    def test_original_float_integer_is_rejected_before_checked_client_transport(self):
        with patch('hms.client.call') as transport:
            with self.assertRaises(ContractError):
                Client('/nonexistent/hms.sock').request('discover', {'limit': 1.0})
        transport.assert_not_called()

    def test_duplicate_inflight_id_and_worker_bound_never_repeat_dispatch(self):
        entered, release = queue.Queue(), threading.Event()
        messages = queue.Queue()
        calls = []
        class Blocked:
            def request(self, method, params):
                calls.append(method)
                entered.put_nowait(True)
                release.wait(5)
                return {'items': [], 'cursor': None, 'registryRevision': 1}
        projection = Projection(Blocked(), messages.put_nowait, clock=lambda: 1.0)
        self.addCleanup(projection.close)
        self.addCleanup(release.set)
        first = wire(1, 'tools/call', {'name': 'hardware_discover', 'arguments': {}})
        projection.receive(dumps(first).encode())
        entered.get(timeout=2)
        with self.assertRaises(TransportClosed):
            projection.receive(dumps(first).encode())
        for identifier in range(2, MAX_CALLS + 1):
            value = wire(identifier, 'tools/call', {'name': 'hardware_discover', 'arguments': {}})
            projection.receive(dumps(value).encode())
            entered.get(timeout=2)
        projection.receive(dumps(wire(99, 'tools/call', {'name': 'hardware_discover', 'arguments': {}})).encode())
        self.assertEqual(messages.get(timeout=2)['error']['code'], 1001)
        self.assertEqual(calls, ['discover'] * MAX_CALLS)
        projection.close()
        release.set()
        deadline = time.monotonic() + 2
        while projection.calls and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(projection.calls)
        self.assertTrue(messages.empty())

    def test_oversized_and_stalled_frames_close_actual_process_without_traceback(self):
        for payload in (b'{' + b' ' * MAX_BYTES, b'{'):
            with self.subTest(size=len(payload)):
                process = self.process()
                process.stdin.write(payload)
                process.stdin.flush()
                self.assertEqual(process.wait(timeout=5), 2)
                self.assertEqual(process.stderr.read(), b'')

    def test_unread_stdout_times_out_actual_process(self):
        process = self.process()
        # Explicitly constrain the pipe; Linux defaults vary across environments.
        # Do not read stdout until exit, so the transport must time out writes.
        fcntl.fcntl(process.stdout.fileno(), fcntl.F_SETPIPE_SZ, 4096)
        process.stdin.write(dumps(wire(1, 'tools/list')).encode() + b'\n')
        process.stdin.flush()
        self.assertEqual(process.wait(timeout=5), 2)
        self.assertEqual(process.stderr.read(), b'')

    def test_outbox_bounds_and_write_deadline_fail_closed(self):
        read, write = socket.socketpair()
        self.addCleanup(read.close)
        self.addCleanup(write.close)
        write.setblocking(False)
        for constant, limit, message in (('MAX_OUTPUT_BYTES', 10, {'value': 'x' * 30}),
                                         ('MAX_QUEUED_BYTES', 10, {'value': 'x' * 30}),
                                         ('MAX_QUEUED_MESSAGES', 0, {})):
            with self.subTest(constant=constant), patch('hms.mcp_stdio.' + constant, limit):
                outbox = _Outbox(write)
                outbox.emit(message)
                with self.assertRaises(TransportClosed):
                    outbox.check()
        outbox = _Outbox(write)
        with patch('hms.mcp_stdio.time.monotonic', return_value=10):
            outbox.emit({'pending': True})
        with patch('hms.mcp_stdio.time.monotonic', return_value=13):
            with self.assertRaises(TransportClosed):
                outbox.check()


class ReviewTransportLoss(unittest.TestCase):
    def test_pipe_eof_after_admission_does_not_cancel_or_repeat_simulated_effect(self):
        with tempfile.TemporaryDirectory(prefix='hms-mcp-review-') as temporary:
            directory = Path(temporary)
            runtime = Runtime(directory / 'state', create=True,
                              owner=Context(f'posix:{os.getuid()}', 'simulation:local'))
            self.addCleanup(runtime.close)
            server = Server(runtime, directory / 'control.sock')
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            def stop_server():
                server.close()
                server_thread.join(3)
            self.addCleanup(stop_server)
            runtime.start()
            client = Client(directory / 'control.sock')
            now = time.time_ns() // 1_000_000
            namespace = client.request('namespace', {'expiresUnixMs': now + 60000})['token']
            retained = client.request('prepare', {
                'instanceId': 'sim:home-fan', 'actionId': 'set_level', 'arguments': {'level': 46, 'unit': 'percent'},
                'replayNamespace': namespace, 'operationKey': 'review:eof', 'requiredEffect': 'capability_completion',
                'timing': {'notBeforeUnixMs': now, 'latestStartUnixMs': now + 20000,
                           'maxRunMs': 5000, 'latestCompletionUnixMs': now + 30000}})['request']
            entered, release, drained = threading.Event(), threading.Event(), threading.Event()
            self.addCleanup(release.set)
            accepted, methods = [], []
            class Gated:
                def request(self, method, arguments):
                    methods.append(method)
                    value = client.request(method, arguments)
                    accepted.append(value)
                    entered.set()
                    release.wait(5)
                    drained.set()
                    return value
            input_read, input_write = os.pipe()
            output_read, output_write = os.pipe()
            for fd in (input_read, output_read, output_write):
                self.addCleanup(os.close, fd)
            exit_codes = []
            transport = threading.Thread(target=lambda: exit_codes.append(serve(Gated(), input_fd=input_read, output_fd=output_write)))
            transport.start()
            os.write(input_write, dumps(wire(1, 'tools/call', {'name': 'hardware_invoke', 'arguments': {'request': retained}})).encode() + b'\n')
            try:
                self.assertTrue(entered.wait(3))
            finally:
                os.close(input_write)
            transport.join(3)
            self.assertFalse(transport.is_alive())
            self.assertEqual(exit_codes, [0])
            release.set()
            self.assertTrue(drained.wait(3))
            operation = accepted[0]['operationId']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = client.request('operation', {'operationId': operation})
                if state['executionState'] == 'completed':
                    break
                time.sleep(0.02)
            self.assertEqual(state['executionState'], 'completed')
            self.assertEqual(state['cancellationState'], 'not_requested')
            self.assertEqual(methods, ['invoke'])
            self.assertEqual(select.select([output_read], [], [], 0)[0], [])
            self.assertEqual(client.request('invoke', {'request': retained})['operationId'], operation)
            self.assertEqual(runtime.plant.observe('sim:home-fan')['effectCount'], 1)


if __name__ == '__main__':
    unittest.main()
