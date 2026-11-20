"""Named installation CLI over real Unix sockets and original native fixtures."""
import contextlib
import copy
import datetime
import io
import hashlib
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
import traceback
import unittest
import uuid

from hms import cli
from hms.client import Client
from hms.contracts import canonical
from hms.installations import ROLES, manifest_for
from hms.ipc import IpcError
from test_multi_adapter import BINARY, ROOT, installation, scenario
from tests.sqlite_observer import admission_snapshot


LAST_REPORT = None


_BACKUP_FAILURE_DB = r'''
import json, pathlib, sqlite3, sys, time
source, target = map(pathlib.Path, sys.argv[1:])
started = time.monotonic()
def progress(*_):
    if time.monotonic() - started > 1.5:
        raise TimeoutError('bounded diagnostic SQLite backup expired')
def value(item):
    if isinstance(item, bytes):
        try: return json.loads(item)
        except (ValueError, UnicodeError): return {'hex': item.hex()}
    return item
with sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True, timeout=.2) as original:
    with sqlite3.connect(target) as retained:
        original.backup(retained, pages=64, progress=progress, sleep=.01)
        retained.row_factory = sqlite3.Row
        tables = [row[0] for row in retained.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        summary = {'integrity': retained.execute('PRAGMA integrity_check').fetchone()[0], 'tables': {}}
        for table in tables:
            quoted = '"'+table.replace('"','""')+'"'
            rows = retained.execute('SELECT * FROM '+quoted+' LIMIT 4097').fetchall()
            summary['tables'][table] = {'rows': [{key:value(row[key]) for key in row.keys()} for row in rows[:4096]], 'truncated':len(rows)>4096}
        target.with_suffix(target.suffix+'.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n')
'''


def finish_transport_failure(report):
    """Finalize only this report's uniquely owned failure artifacts; never raise."""
    for manifest_path in report.get('failureArtifacts', []):
        try:
            path = ROOT / manifest_path
            directory = path.parent
            (directory / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
            files = [{'path': str(item.relative_to(directory)), 'sha256': hashlib.sha256(item.read_bytes()).hexdigest(),
                      'bytes': item.stat().st_size} for item in sorted(directory.rglob('*'))
                     if item.is_file() and item != path]
            path.write_text(json.dumps({'schema': 'hms-transport-failure/1',
                'directory': str(directory.relative_to(ROOT)), 'files': files,
                'scope': 'Failure-only original local simulation evidence. Separate database snapshots; no physical or timing qualification.'},
                indent=2, sort_keys=True) + '\n')
        except Exception as error:
            report.setdefault('failureCaptureErrors', []).append({'stage': 'finalize', 'error': repr(error)})


def retain_transport_failure(report, case, state, reason, *, base=None, relay=None):
    """Best-effort read-only capture before cleanup; never replaces a test failure."""
    report['passed'] = False
    try:
        name = ''.join(c if c.isalnum() or c in '-_' else '-' for c in case)[:80]
        directory = ROOT / 'artifacts/verification/transport-failures' / (name + '-' + uuid.uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        report.setdefault('failureArtifacts', []).append(str((directory / 'manifest.json').relative_to(ROOT)))
        metadata = {'case': case, 'reason': str(reason),
            'capturedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'stage': 'failure-before-cleanup', 'databases': [], 'errors': []}
        if base is not None:
            for source in sorted(Path(base).glob('*.json'))[:32]:
                if source.stat().st_size <= 1048576:
                    target = directory / 'requests' / source.name
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(source.read_bytes())
        for source in sorted(Path(state).glob('*.db'))[:16]:
            item = {'sourceName': source.name, 'snapshotStartedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            metadata['databases'].append(item)
            try:
                if source.stat().st_size > 67108864:
                    raise ValueError('diagnostic database exceeds 64 MiB bound')
                target = directory / 'databases' / source.name
                target.parent.mkdir(exist_ok=True)
                child = subprocess.run([sys.executable, '-B', '-c', _BACKUP_FAILURE_DB, str(source), str(target)],
                                       cwd=ROOT, capture_output=True, text=True, timeout=3)
                item.update(exitCode=child.returncode, stdout=child.stdout, stderr=child.stderr,
                            complete=child.returncode == 0)
            except Exception as error:
                item.update(complete=False, error=repr(error))
        if relay is not None:
            acquired = relay.lock.acquire(timeout=.5)
            try:
                if not acquired:
                    raise TimeoutError('diagnostic relay lock unavailable')
                wires = {'requests': [raw.hex() for _, raw in relay.requests],
                    'responses': [raw.hex() for _, raw in relay.responses],
                    'pendingReplies': [raw.hex() for raw in relay.pending],
                    'error': repr(relay.error) if relay.error else None,
                    'scope': 'Existing external relay original bytes; no independent physical effect evidence.'}
                (directory / 'relay.json').write_text(json.dumps(wires, indent=2, sort_keys=True) + '\n')
            except Exception as error:
                metadata['errors'].append({'stage': 'relay', 'error': repr(error)})
            finally:
                if acquired:
                    relay.lock.release()
        (directory / 'capture.json').write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')
        finish_transport_failure(report)
    except Exception as error:
        report.setdefault('failureCaptureErrors', []).append({'stage': 'capture', 'error': repr(error)})


class MultiCliTests(unittest.TestCase):
    def test_named_streams_mixed_scenarios_and_offline_reopen(self):
        global LAST_REPORT
        LAST_REPORT = {'passed': False, 'refusals': [], 'scenarios': [], 'replayedResults': 0,
                       'attemptedScenarios': [], 'requestHistory': [], 'processOutput': [],
                       'observerReads': [],
                       'scope': 'Mixed CLI functional integration with bounded exact-request retries after confirmed pre-admission freshness refusals; no latency or availability guarantee.'}
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
                        LAST_REPORT['processOutput'].append({'process': 'daemon', 'stdout': output, 'stderr': error,
                            'exitCode': daemon.returncode, 'stopTimedOut': True})
                        self.fail('daemon failed to stop: ' + error)
                    LAST_REPORT['processOutput'].append({'process': 'daemon', 'stdout': output, 'stderr': error,
                        'exitCode': daemon.returncode, 'stopTimedOut': False})
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
                def observed_admission(namespace, key):
                    entry = {'database': 'authority.db'}
                    LAST_REPORT['observerReads'].append(entry)
                    return admission_snapshot(base / 'state' / 'authority.db', namespace, key, report=entry)
                def checked(method, params):
                    LAST_REPORT['requestHistory'].append({'method': method, 'params': copy.deepcopy(params)})
                    wire = canonical(params)
                    envelope = params['request'] if method == 'invoke' else params
                    namespace, key = envelope['replayNamespace'], envelope['operationKey']
                    before, _ = observed_admission(namespace, key)
                    deadline = time.monotonic() + 3
                    while True:
                        self.assertEqual(canonical(params), wire)
                        try:
                            return client.request(method, params)
                        except IpcError as error:
                            if error.code not in {'OBSERVATION_STALE', 'DEVICE_UNAVAILABLE'}:
                                raise
                            # These are fresh admissions, with this test as sole
                            # caller. Verify the refusal left no key, operation,
                            # resource claim or compact dispatch mapping before
                            # resubmitting the identical envelope. Never retry
                            # transport uncertainty or change intent/key/time.
                            after, found = observed_admission(namespace, key)
                            self.assertEqual(after, before)
                            self.assertFalse(found)
                            LAST_REPORT['refusals'].append({'method': method, 'operationKey': key,
                                'code': error.code, 'paramsSha256': hashlib.sha256(wire).hexdigest(),
                                'countsBefore': before, 'countsAfter': after, 'replayKeyAbsent': True})
                            if time.monotonic() >= deadline:
                                self.fail('Freshness did not recover within bounded retry window: ' + repr(LAST_REPORT['refusals']))
                            time.sleep(.05)
                namespace = client.request('namespace', {'expiresUnixMs': time.time_ns() // 1000000 + 30000})['token']
                records = []
                for config in configs:
                    for role in ROLES:
                        instance, action, arguments = scenario(config, role)
                        attempt = {'instanceId': instance, 'actionId': action, 'arguments': copy.deepcopy(arguments)}
                        LAST_REPORT['attemptedScenarios'].append(attempt)
                        now = time.time_ns() // 1000000
                        request = checked('prepare', {'instanceId': instance, 'actionId': action,
                            'arguments': arguments, 'operationKey': instance, 'replayNamespace': namespace,
                            'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': now,
                            'latestStartUnixMs': now + 5000, 'maxRunMs': 500, 'latestCompletionUnixMs': now + 5500}})['request']
                        attempt['request'] = request
                        accepted = checked('invoke', {'request': request})
                        attempt['accepted'] = accepted
                        deadline = time.monotonic() + 6
                        while time.monotonic() < deadline:
                            state = client.request('operation', {'operationId': accepted['operationId']})
                            attempt['lastStatus'] = state
                            if state['executionState'] == 'completed' and not state['resourceClaims']:
                                break
                            time.sleep(.02)
                        self.assertEqual(state['executionState'], 'completed', state)
                        self.assertFalse(state['resourceClaims'])
                        self.assertEqual(state['result']['evidenceKind'], 'simulation')
                        records.append((request, state))
                        LAST_REPORT['scenarios'].append({'request': request, 'accepted': accepted, 'completed': state})
                stop()
                start(False)  # Stored catalog, no compact streams supplied.
                for request, completed in records:
                    replay = client.request('invoke', {'request': request})
                    self.assertEqual(replay['operationId'], completed['operationId'])
                    status = client.request('operation', {'operationId': replay['operationId']})
                    self.assertEqual(status['result'], completed['result'])
                    self.assertEqual(status['executionState'], 'completed')
                    LAST_REPORT['replayedResults'] += 1
                LAST_REPORT['passed'] = True
            except BaseException:
                retain_transport_failure(LAST_REPORT, self.id(), base / 'state', traceback.format_exc(), base=base)
                raise
            finally:
                try:
                    stop()
                    for stream in sockets:
                        stream.close()
                    for fixture in fixtures:
                        try:
                            _, error = fixture.communicate(timeout=3)
                        except subprocess.TimeoutExpired:
                            fixture.kill()
                            _, error = fixture.communicate()
                        LAST_REPORT['processOutput'].append({'process': 'fixture', 'stderrHex': error.hex(),
                            'exitCode': fixture.returncode})
                        self.assertEqual(fixture.returncode, 0, error)
                except BaseException:
                    retain_transport_failure(LAST_REPORT, self.id() + '-cleanup', base / 'state', traceback.format_exc(), base=base)
                    raise
                finally:
                    finish_transport_failure(LAST_REPORT)

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
