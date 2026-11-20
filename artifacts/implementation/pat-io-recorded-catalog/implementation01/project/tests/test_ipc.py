"""Exercise real local sockets and CLI projection without replacing the runtime owner."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hms import cli, ipc
from hms.contracts import canonical, MAX_BYTES
from hms.journal import JournalError


class StubRuntime:
    deployment = 'simulation:local'

    def __init__(self):
        self.calls = []

    def request(self, context, method, params):
        self.calls.append((context, method, params))
        if method == 'denied':
            raise JournalError('NOT_AUTHORIZED')
        if method == 'broken':
            raise RuntimeError('private filesystem path and secret')
        if method == 'large':
            return 'x' * MAX_BYTES
        return {'method': method, 'params': params}


@unittest.skipUnless(os.name == 'posix' and hasattr(socket, 'SO_PEERCRED'), 'Linux peer credentials required')
class LocalIpc(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hms-ipc-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'control.sock'
        self.runtime = StubRuntime()
        self.server = ipc.Server(self.runtime, self.path)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.close()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(connection.close)
        connection.settimeout(3)
        connection.connect(str(self.path))
        return connection

    def raw(self, data):
        connection = self.connect()
        connection.sendall(data)
        connection.shutdown(socket.SHUT_WR)
        result = bytearray()
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            result.extend(chunk)
        return json.loads(result)

    def request(self, **overrides):
        return {'protocol': ipc.PROTOCOL, 'requestId': 'test-request', 'method': 'discover',
                'params': {}, **overrides}

    def test_peer_uid_is_the_principal_and_socket_is_private(self):
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        result = ipc.call(self.path, 'discover', {'limit': 1})
        self.assertEqual(result, {'method': 'discover', 'params': {'limit': 1}})
        context, method, _ = self.runtime.calls[0]
        self.assertEqual(context.principal, f'posix:{os.getuid()}')
        self.assertEqual(context.deployment, self.runtime.deployment)
        self.assertEqual(method, 'discover')

    def test_caller_identity_cannot_be_overridden_in_envelope(self):
        response = self.raw(canonical(self.request(principal='posix:0')) + b'\n')
        self.assertEqual(response['requestId'], 'test-request')
        self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
        self.assertEqual(self.runtime.calls, [])

    def test_duplicate_keys_truncation_and_multiple_frames_never_dispatch(self):
        cases = [
            (b'{"requestId":"one","requestId":"two"}\n', 'INVALID_REQUEST'),
            (b'{"incomplete":', 'TRUNCATED_FRAME'),
            (canonical(self.request()) + b'\n{}\n', 'MULTIPLE_FRAMES'),
        ]
        for body, code in cases:
            with self.subTest(code=code):
                self.assertEqual(self.raw(body)['error']['code'], code)
        self.assertEqual(self.runtime.calls, [])

    def test_oversized_frame_and_response_are_bounded(self):
        response = self.raw(b' ' * (MAX_BYTES + 1))
        self.assertEqual(response['error']['code'], 'FRAME_TOO_LARGE')
        self.assertEqual(self.runtime.calls, [])
        with self.assertRaisesRegex(ipc.IpcError, 'RESPONSE_TOO_LARGE'):
            ipc.call(self.path, 'large', {})

    def test_domain_codes_survive_but_internal_messages_do_not(self):
        for method, code in [('denied', 'NOT_AUTHORIZED'), ('broken', 'INTERNAL_ERROR')]:
            with self.subTest(method=method):
                response = self.raw(canonical(self.request(method=method)) + b'\n')
                self.assertEqual(response, {'protocol': ipc.PROTOCOL, 'requestId': 'test-request',
                                            'error': {'code': code}})
                with self.assertRaisesRegex(ipc.IpcError, code):
                    ipc.call(self.path, method, {})

    def test_existing_paths_and_public_parent_are_refused(self):
        with self.assertRaisesRegex(ipc.IpcError, 'SOCKET_PATH_EXISTS'):
            ipc.Server(self.runtime, self.path)
        self.assertEqual(ipc.call(self.path, 'discover', {})['method'], 'discover')
        other = self.path.with_name('existing')
        other.write_text('retain me')
        with self.assertRaisesRegex(ipc.IpcError, 'SOCKET_PATH_EXISTS'):
            ipc.Server(self.runtime, other)
        self.assertEqual(other.read_text(), 'retain me')
        public = self.path.parent / 'public'
        public.mkdir(mode=0o755)
        with self.assertRaisesRegex(ipc.IpcError, 'UNSAFE_SOCKET_DIRECTORY'):
            ipc.Server(self.runtime, public / 'control.sock')

    def test_symlink_path_and_changed_socket_permissions_are_refused(self):
        linked = self.path.with_name('linked')
        linked.symlink_to(self.path)
        with self.assertRaisesRegex(ipc.IpcError, 'UNSAFE_SOCKET_PATH'):
            ipc.call(linked, 'discover', {})
        self.path.chmod(0o666)
        with self.assertRaisesRegex(ipc.IpcError, 'UNSAFE_SOCKET_PATH'):
            ipc.call(self.path, 'discover', {})
        self.path.chmod(0o600)

    def test_client_checks_server_credentials(self):
        with patch.object(ipc, '_peer_uid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ipc.IpcError, 'SERVER_IDENTITY_MISMATCH'):
                ipc.call(self.path, 'discover', {})
        self.assertEqual(self.runtime.calls, [])

    def test_unsigned_peer_uid_does_not_become_a_negative_principal(self):
        from unittest.mock import Mock
        connection = Mock()
        connection.getsockopt.return_value = ipc._CREDENTIALS.pack(123, 2**32 - 2, 2**32 - 2)
        self.assertEqual(ipc._peer_uid(connection), 2**32 - 2)

    def test_close_drains_partial_requests_and_preserves_replacement_inode(self):
        connection = self.connect()
        connection.sendall(b'{')
        self.path.unlink()
        self.path.write_text('replacement')
        self.stop()
        self.assertEqual(self.path.read_text(), 'replacement')
        self.assertEqual(self.runtime.calls, [])

    def test_slow_input_uses_one_deadline_not_a_fresh_timeout_per_chunk(self):
        with patch.object(ipc, 'IO_TIMEOUT', 0.12):
            connection = self.connect()
            started = time.monotonic()
            for _ in range(10):
                try:
                    connection.sendall(b' ')
                except OSError:
                    break
                time.sleep(0.03)
            self.assertEqual(connection.recv(1), b'')
            self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(self.runtime.calls, [])

    def test_worker_count_is_bounded_and_a_released_slot_makes_progress(self):
        clients = [self.connect() for _ in range(ipc.MAX_CONNECTIONS)]
        deadline = time.monotonic() + 1
        while len(self.server._workers) != ipc.MAX_CONNECTIONS and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(self.server._workers), ipc.MAX_CONNECTIONS)
        queued = self.connect()
        queued.sendall(canonical(self.request()) + b'\n')
        self.assertEqual(self.runtime.calls, [])
        clients[0].close()
        reply = json.loads(queued.recv(MAX_BYTES))
        self.assertEqual(reply['result']['method'], 'discover')
        self.assertLessEqual(len(self.server._workers), ipc.MAX_CONNECTIONS)


class CliProjection(unittest.TestCase):
    def test_serve_initialization_is_explicit_and_cleanup_closes_transport_first(self):
        for initialize in (False, True):
            events = []
            instances = []
            class Runtime:
                deployment = 'simulation:local'

                def __init__(self, state_dir, *, create=False, owner=None, endpoint_fd=None,
                             installations=None, endpoint_fds=None, io_simulation=False, io_installation=None):
                    instances.append((state_dir, create, owner, endpoint_fd, io_simulation, io_installation))

                def start(self):
                    events.append('runtime-start')

                def close(self):
                    events.append('runtime-close')

            class Server:
                path = Path('/private/control.sock')

                def __init__(self, runtime, path):
                    events.append('bind')

                def serve_forever(self):
                    events.append('serve')

                def close(self):
                    events.append('transport-close')

            with self.subTest(initialize=initialize), patch.dict('sys.modules', {'hms.runtime': SimpleNamespace(open_runtime=Runtime)}):
                with patch.object(cli, 'Server', Server), contextlib.redirect_stdout(io.StringIO()) as output:
                    args = ['serve', '--state-dir', '/private/state', '--socket', '/private/control.sock']
                    self.assertEqual(cli.main(args + (['--init-simulation'] if initialize else [])), 0)
                self.assertEqual(events, ['bind', 'runtime-start', 'serve', 'transport-close', 'runtime-close'])
                self.assertEqual(instances[0][:2], (Path('/private/state'), initialize))
                self.assertIsNone(instances[0][3])
                self.assertEqual(instances[0][4:], (False, None))
                if initialize:
                    self.assertEqual(instances[0][2].principal, f'posix:{os.getuid()}')
                else:
                    self.assertIsNone(instances[0][2])
                self.assertTrue(json.loads(output.getvalue())['ready'])

    def test_command_arguments_reach_the_matching_rpc(self):
        cases = [
            (['discover', '--capability', 'axis', '--limit', '2', '--cursor', 'next'], 'discover',
             {'capability': 'axis', 'limit': 2, 'cursor': 'next'}),
            (['describe', 'axis', '--digest', 'sha256:known'], 'describe', {'instanceId': 'axis', 'digest': 'sha256:known'}),
            (['observe', 'axis', 'position', '--max-age-ms', '20', '--evidence-kind', 'simulation'], 'observe',
             {'instanceId': 'axis', 'property': 'position', 'maxAgeMs': 20, 'evidenceKind': 'simulation'}),
            (['namespace', '--expires-unix-ms', '1234'], 'namespace', {'expiresUnixMs': 1234}),
            (['operation', 'op-1'], 'operation', {'operationId': 'op-1'}),
            (['events', 'op-1', '--after', '3', '--limit', '5'], 'events', {'operationId': 'op-1', 'after': 3, 'limit': 5}),
            (['cancel', 'op-1'], 'cancel', {'operationId': 'op-1'}),
        ]
        for arguments, method, params in cases:
            with self.subTest(method=method), patch.object(cli.Client, 'request', return_value={'ok': True}) as call:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(cli.main(['--socket', '/private/control.sock', *arguments]), 0)
                call.assert_called_once_with(method, params)
                self.assertEqual(json.loads(output.getvalue()), {'ok': True})

    def test_domain_failure_has_nonzero_exit_and_json_code(self):
        with patch.object(cli.Client, 'request', side_effect=ipc.IpcError('NOT_AUTHORIZED')):
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                self.assertEqual(cli.main(['discover', '--socket', '/private/control.sock']), 1)
            self.assertEqual(json.loads(error.getvalue()), {'error': {'code': 'NOT_AUTHORIZED'}})

    def test_invocation_file_must_pass_full_host_parser_before_transmission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invoke.json'
            path.write_text('{"intent":{}}')
            with patch.object(cli.Client, 'request') as call, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['--socket', '/private/control.sock', 'invoke', '--request-file', str(path)]), 1)
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
