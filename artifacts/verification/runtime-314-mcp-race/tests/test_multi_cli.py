"""Named installation CLI over real Unix sockets and original native fixtures."""
import contextlib
import io
import json
import os
from pathlib import Path
import select
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from hms import cli
from hms.client import Client
from hms.contracts import canonical
from hms.installations import ROLES, manifest_for
from test_multi_adapter import BINARY, ROOT, installation, scenario


class MultiCliTests(unittest.TestCase):
    def test_named_streams_mixed_scenarios_and_offline_reopen(self):
        with tempfile.TemporaryDirectory(prefix='hms-multi-cli-') as temporary:
            base = Path(temporary)
            configs = [installation('cli-local'), installation('cli-c1', compact=True),
                       installation('cli-c2', compact=True)]
            config_path, address = base / 'installations.json', base / 'hctl.sock'
            config_path.write_bytes(canonical(configs))
            sockets, fixtures, daemon = [], [], None
            def stop():
                nonlocal daemon
                if daemon is not None:
                    daemon.terminate()
                    try:
                        output, error = daemon.communicate(timeout=8)
                    except subprocess.TimeoutExpired:
                        daemon.kill()
                        output, error = daemon.communicate()
                        self.fail('daemon failed to stop: ' + error)
                    self.assertEqual(daemon.returncode, 0, (output, error))
                    daemon = None
            def start(create):
                nonlocal daemon
                args = [sys.executable, '-m', 'hms', 'serve', '--socket', str(address),
                        '--state-dir', str(base / 'state')]
                if create:
                    args += ['--init-multi-simulation', '--installations-file', str(config_path)]
                    for config, stream in zip(configs[1:], sockets):
                        args += ['--endpoint-route', config['adapterId'] + '=' + str(stream.fileno())]
                daemon = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, pass_fds=tuple(s.fileno() for s in sockets) if create else ())
                self.assertTrue(select.select([daemon.stdout], [], [], 10)[0], 'daemon ready timeout')
                ready = daemon.stdout.readline()
                self.assertTrue(ready, 'daemon ended before readiness')
                self.assertEqual(json.loads(ready)['deployment'], 'simulation:multi')
            try:
                for config in configs[1:]:
                    host, native = socket.socketpair()
                    sockets.append(host)
                    data, digest = manifest_for(config)
                    manifest = json.loads(data)
                    fixtures.append(subprocess.Popen([str(BINARY), '--manifest', digest,
                        '--incarnation', config['incarnationHex'], '--firmware', manifest['firmwareDigest']],
                        stdin=native, stdout=native, stderr=subprocess.PIPE))
                    native.close()
                start(True)
                result = subprocess.run([sys.executable, '-m', 'hms', 'discover', '--socket', str(address)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(json.loads(result.stdout)['items']), 9)
                client = Client(address)
                def checked(method, params):
                    try:
                        return client.request(method, params)
                    except Exception as error:
                        with sqlite3.connect(base / 'state' / 'authority.db') as db:
                            observations = [(r[0], r[1], json.loads(r[2])) for r in db.execute(
                                'SELECT instance,property,document FROM reg_observations WHERE property=?', ('ready',))]
                            states = [(r[0], {k:v for k,v in json.loads(r[1]).items() if k in ('fault','lastTick','clockAnchor')})
                                      for r in db.execute('SELECT adapter, document FROM ep_state')]
                        self.fail(repr({'method': method, 'instance': params.get('instanceId'), 'error': str(error),
                                        'observations': observations, 'endpointStates': states,
                                        'monoNow': time.monotonic_ns() // 1000000}))
                namespace = client.request('namespace', {'expiresUnixMs': time.time_ns() // 1000000 + 30000})['token']
                records = []
                for config in configs:
                    for role in ROLES:
                        instance, action, arguments = scenario(config, role)
                        now = time.time_ns() // 1000000
                        request = checked('prepare', {'instanceId': instance, 'actionId': action,
                            'arguments': arguments, 'operationKey': instance, 'replayNamespace': namespace,
                            'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': now,
                            'latestStartUnixMs': now + 5000, 'maxRunMs': 500, 'latestCompletionUnixMs': now + 5500}})['request']
                        accepted = checked('invoke', {'request': request})
                        deadline = time.monotonic() + 6
                        while time.monotonic() < deadline:
                            state = client.request('operation', {'operationId': accepted['operationId']})
                            if state['executionState'] == 'completed' and not state['resourceClaims']:
                                break
                            time.sleep(.02)
                        self.assertEqual(state['executionState'], 'completed', state)
                        self.assertFalse(state['resourceClaims'])
                        self.assertEqual(state['result']['evidenceKind'], 'simulation')
                        records.append((request, state))
                stop()
                start(False)  # Stored catalog, no compact streams supplied.
                for request, completed in records:
                    replay = client.request('invoke', {'request': request})
                    self.assertEqual(replay['operationId'], completed['operationId'])
                    status = client.request('operation', {'operationId': replay['operationId']})
                    self.assertEqual(status['result'], completed['result'])
                    self.assertEqual(status['executionState'], 'completed')
            finally:
                stop()
                for stream in sockets:
                    stream.close()
                for fixture in fixtures:
                    try:
                        _, error = fixture.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        fixture.kill()
                        _, error = fixture.communicate()
                    self.assertEqual(fixture.returncode, 0, error)

    def test_invalid_cli_installation_inputs_do_not_create_authority(self):
        cases = [(['--init-multi-simulation'], 'INVALID_ENDPOINT_INITIALIZATION'),
                 (['--init-simulation', '--endpoint-route', 'a=3'], 'INVALID_ENDPOINT_INITIALIZATION'),
                 (['--endpoint-route', 'a=-1'], 'INVALID_ENDPOINT_ROUTES'),
                 (['--endpoint-route', 'a=3', '--endpoint-route', 'a=4'], 'DUPLICATE_ENDPOINT_ROUTE')]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for options, expected in cases:
                with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(cli.main(['serve', '--socket', str(base/'s'), '--state-dir', str(base/'state'), *options]), 1)
                    self.assertEqual(json.loads(error.getvalue())['error']['code'], expected)
                    self.assertFalse((base/'state').exists())
