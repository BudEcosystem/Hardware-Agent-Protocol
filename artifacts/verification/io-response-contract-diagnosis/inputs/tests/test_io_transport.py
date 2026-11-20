"""Real CLI/UDS/MCP processes over the original shared SQLite I/O model.

No native endpoint, acquired controller, physical I/O or virtual clock is used.
Observed host timings establish these executions only, not pulse/stop bounds.
"""
import copy
import hashlib
import json
from pathlib import Path
import select
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import unittest

from hms.api_contracts import METHOD_RESULTS, validate_result
from hms.client import Client
from hms.contracts import canonical, intent_digest
from test_io_synthetic_provider import installation
from test_multi_cli import finish_transport_failure, retain_transport_failure
from tests.sqlite_observer import readonly_rows
from tests.test_endpoint_mcp import LEGACY, MODERN, projection, sdk_available


ROOT = Path(__file__).resolve().parents[1]
LAST_REPORT = {'schema': 'hms-io-transport-tests/1', 'cases': {},
    'scope': 'Real host-clock processes and original SQLite simulation; no physical, autonomous-stop or latency qualification.'}
TERMINAL = {'completed', 'failed', 'canceled', 'rejected_before_start', 'rejected_before_dispatch'}


def bounds(*, delay=0):
    now = time.time_ns() // 1_000_000
    return {'notBeforeUnixMs': now + delay, 'latestStartUnixMs': now + delay + 30000,
            'maxRunMs': 5000, 'latestCompletionUnixMs': now + delay + 60000}


def parameters(instance, namespace, key, timing, *, duration=100):
    pwm = instance == 'sim:pwm5'
    arguments = ({'durationMs': duration, 'frequencyHz': 1000, 'dutyPermille': 500, 'resolutionBits': 8}
                 if pwm else {'durationMs': duration, 'level': 1})
    return {'instanceId': instance, 'actionId': 'pwm_burst' if pwm else 'gpio_pulse',
        'arguments': arguments, 'operationKey': key, 'replayNamespace': namespace,
        'requiredEffect': 'capability_completion', 'timing': copy.deepcopy(timing)}


def sequence(namespace, key, timing, requests):
    return {'protocol': 'hms.procedure/0.1', 'replayNamespace': namespace, 'procedureKey': key,
        'procedure': {'profile': 'hms.bound-sequence/0.1',
            'timing': {name: timing[name] for name in ('notBeforeUnixMs', 'latestStartUnixMs', 'latestCompletionUnixMs')},
            'steps': [{'stepId': 'step:' + str(n), 'request': request} for n, request in enumerate(requests)]}}


def json_value(value):
    if type(value) is bytes:
        try:
            return json.loads(value)
        except (ValueError, UnicodeError):
            return {'hex': value.hex()}
    return value


class IoDaemon:
    def __init__(self, base, report):
        self.base, self.report = base, report
        self.path, self.state = base / 'control.sock', base / 'state'
        self.process = None
        self.configuration = installation()
        self.config_path = base / 'io-installation.json'
        self.config_path.write_bytes(canonical(self.configuration))
        self.board_name = 'synthetic-io-board-' + hashlib.sha256(self.configuration['boardId'].encode()).hexdigest() + '.db'
        self.client = Client(self.path)

    def start(self, *, create=False, with_file=False):
        assert self.process is None
        command = [sys.executable, '-B', '-m', 'hms', 'serve', '--state-dir', str(self.state), '--socket', str(self.path)]
        command += ['--init-io-simulation'] if create else ['--io-simulation']
        if create or with_file:
            command += ['--io-installation-file', str(self.config_path)]
        entry = {'command': command, 'startedUnixMs': time.time_ns() // 1_000_000}
        self.report['daemonStarts'].append(entry)
        self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert select.select([self.process.stdout], [], [], 15)[0], 'I/O daemon readiness timeout'
        line = self.process.stdout.readline(65537)
        if not line:
            process, self.process = self.process, None
            output, error = process.communicate(timeout=5)
            self.report['processOutput'].append({'exitCode': process.returncode,
                'stdoutHex': output.hex(), 'stderrHex': error.hex(), 'readinessFailed': True})
            raise AssertionError('I/O daemon ended before readiness: ' + error.decode(errors='replace'))
        assert line.endswith(b'\n') and len(line) <= 65536
        ready = json.loads(line)
        entry.update(readiness=ready, readyUnixMs=time.time_ns() // 1_000_000)
        assert ready == {'ready': True, 'protocol': 'hctl.local/0.1', 'socket': str(self.path),
                         'deployment': 'simulation:io-hub'}, ready
        info = self.path.lstat()
        assert stat.S_ISSOCK(info.st_mode)
        self.socket_identity = info.st_dev, info.st_ino
        assert [p.name for p in self.state.glob('synthetic-io-board-*.db')] == [self.board_name]
        assert not list(self.state.glob('simulated-plant*.db'))

    def stop(self, *, kill=False):
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            process.kill() if kill else process.terminate()
        try:
            output, error = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, error = process.communicate(timeout=3)
            self.report['processOutput'].append({'exitCode': process.returncode, 'stdoutHex': output.hex(),
                'stderrHex': error.hex(), 'stopTimedOut': True})
            raise AssertionError('I/O daemon shutdown timeout')
        self.report['processOutput'].append({'exitCode': process.returncode, 'stdoutHex': output.hex(),
            'stderrHex': error.hex(), 'stopTimedOut': False})
        assert process.returncode == (-signal.SIGKILL if kill else 0) and not output and not error, (process.returncode, output, error)
        if kill:
            info = self.path.lstat()
            assert stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self.socket_identity
            self.path.unlink()  # Only the reaped launcher-owned stale socket.
        else:
            assert not self.path.exists()

    def call(self, method, **params):
        entry = {'transport': 'checked-uds', 'method': method, 'params': copy.deepcopy(params),
                 'startedUnixMs': time.time_ns() // 1_000_000}
        self.report['calls'].append(entry)
        try:
            result = self.client.request(method, params)
            entry['result'] = copy.deepcopy(result)
            return result
        except BaseException as error:
            entry['error'] = {'type': type(error).__name__, 'code': getattr(error, 'code', None), 'message': str(error)}
            raise
        finally:
            entry['finishedUnixMs'] = time.time_ns() // 1_000_000

    def cli(self, method, params, *, error=None):
        command = [sys.executable, '-B', '-m', 'hms', '--socket', str(self.path), method.replace('_', '-')]
        if method in {'prepare', 'invoke', 'procedure_submit'}:
            path = self.base / ('request-' + str(len(self.report['cliCalls'])) + '.json')
            path.write_bytes(canonical(params if method == 'prepare' else params['request']))
            command += ['--params-file' if method == 'prepare' else '--request-file', str(path)]
        elif method == 'namespace':
            command += ['--expires-unix-ms', str(params['expiresUnixMs'])]
        elif method == 'discover':
            command += ['--limit', str(params.get('limit', 20))]
        elif method == 'describe':
            command += [params['instanceId']]
        elif method == 'observe':
            command += [params['instanceId'], params['property'], '--max-age-ms', str(params['maxAgeMs']),
                        '--evidence-kind', params['evidenceKind']]
        elif method.startswith('procedure_'):
            command += [params['procedureId']]
        else:
            command += [params['operationId']]
        if method in {'events', 'procedure_events'}:
            command += ['--after', str(params.get('after', 0)), '--limit', str(params.get('limit', 100))]
        entry = {'command': command, 'method': method, 'params': copy.deepcopy(params),
                 'startedUnixMs': time.time_ns() // 1_000_000}
        self.report['cliCalls'].append(entry)
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
        except BaseException as failure:
            entry['error'] = {'type': type(failure).__name__, 'message': str(failure)}
            if isinstance(failure, subprocess.TimeoutExpired):
                for field in ('stdout', 'stderr'):
                    partial = getattr(failure, field)
                    entry[field + 'AtTimeout'] = ({'hex': partial.hex()} if type(partial) is bytes else partial)
            raise
        finally:
            entry['finishedUnixMs'] = time.time_ns() // 1_000_000
        entry.update(exitCode=result.returncode, stdout=result.stdout, stderr=result.stderr,
                     finishedUnixMs=time.time_ns() // 1_000_000)
        if error is not None:
            assert result.returncode == 1 and result.stdout == '' and json.loads(result.stderr) == {'error': {'code': error}}
            return None
        assert result.returncode == 0 and result.stderr == '', (result.returncode, result.stdout, result.stderr)
        body = validate_result(method, json.loads(result.stdout), params)
        entry['result'] = copy.deepcopy(body)
        return body

    def rows(self, sql, values=(), *, board=False):
        entry = {'database': self.board_name if board else 'authority.db'}
        self.report['observerReads'].append(entry)
        return readonly_rows(self.state / entry['database'], sql, values, report=entry)

    def wait(self, method, params, predicate, *, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.call(method, **params)
            if predicate(result):
                return result
            time.sleep(.05)
        raise AssertionError(('I/O state did not converge', method, result))

    def settled(self, operation_id):
        return self.wait('operation', {'operationId': operation_id},
                         lambda value: value['executionState'] in TERMINAL and not value['resourceClaims'])

    def snapshot(self, label):
        assert self.process is None, 'Freeze this daemon before a multi-database result snapshot'
        queries = {
            'operations': 'SELECT id,state,may_have_acted,attempt_id,intent FROM operations ORDER BY id LIMIT 129',
            'claims': 'SELECT deployment,resource,operation_id,fence FROM claims ORDER BY resource LIMIT 129',
            'dispatchLinks': 'SELECT operation,document,digest FROM io_dispatch_links ORDER BY operation LIMIT 129',
            'events': 'SELECT operation_id,sequence,kind,payload FROM events ORDER BY operation_id,sequence LIMIT 129',
        }
        board_queries = {
            'effects': 'SELECT instance,activations,completed,canceled FROM io_effects ORDER BY instance LIMIT 129',
            'receipts': 'SELECT operation,state,sequence,digest,document FROM io_receipts ORDER BY operation LIMIT 129',
            'owners': 'SELECT resource,operation,fence FROM io_owners ORDER BY resource LIMIT 129',
            'resources': 'SELECT resource,state FROM io_resources ORDER BY resource LIMIT 129',
            'metadata': "SELECT key,value FROM io_meta WHERE key IN ('authority','board','ownerEpoch','session') ORDER BY key",
        }
        result = {'scope': 'Daemon stopped; retained original SQLite model state, not physical evidence.'}
        for board, group in ((False, queries), (True, board_queries)):
            for name, sql in group.items():
                rows = self.rows(sql, board=board)
                assert len(rows) <= 128, 'Test snapshot bound exceeded'
                result[name] = [[json_value(value) for value in row] for row in rows]
        self.report['snapshots'][label] = result
        return result


@unittest.skipUnless(sys.platform == 'linux' and hasattr(socket, 'SO_PEERCRED'), 'Linux UDS peer credentials required')
class IoTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hms-io-transport-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.harness = None
        self.report = {'passed': False, 'daemonStarts': [], 'processOutput': [], 'calls': [], 'cliCalls': [],
            'observerReads': [], 'snapshots': {}, 'mcpMessages': [], 'mcpClosures': [], 'catalogs': [],
            'validatedToolReplies': 0, 'results': {}}
        LAST_REPORT['cases'][self.id()] = self.report
        self.addCleanup(lambda: finish_transport_failure(self.report))
        self.addCleanup(self.close_daemon)
        self.addCleanup(self.capture_failure)
        self.harness = IoDaemon(self.base, self.report)
        self.harness.start(create=True)

    def capture_failure(self):
        result = self._outcome.result
        failures = [(test, text) for test, text in [*result.failures, *result.errors]
                    if test is self or getattr(test, 'test_case', None) is self]
        self.report['passed'] = not failures
        if failures:
            retain_transport_failure(self.report, self.id(), self.base / 'state',
                '\n'.join(text for _, text in failures), base=self.base)

    def close_daemon(self):
        try:
            if self.harness is not None:
                self.harness.stop()
        except BaseException:
            retain_transport_failure(self.report, self.id() + '-cleanup', self.base / 'state',
                                     traceback.format_exc(), base=self.base)
            raise

    def completed(self, value, primitive):
        self.assertEqual(value['executionState'], 'completed', value)
        self.assertTrue(value['mayHaveActed'])
        self.assertEqual(value['effectVerification'], 'unverified')
        self.assertFalse(value['resourceClaims'])
        self.assertEqual(value['result']['evidenceKind'], 'simulation')
        self.assertEqual(value['result']['output']['primitive'], primitive)
        self.assertEqual(value['result']['output']['result'],
            {'activationCommitted': True, 'cycleCompleted': True, 'safeIdle': True, 'reason': None})

    def assert_counts(self, snapshot, expected):
        actual = {row[0]: tuple(row[1:]) for row in snapshot['effects']}
        self.assertEqual(actual, {instance: expected.get(instance, (0, 0, 0)) for instance in
            ('sim:gpio5', 'sim:gpio6', 'sim:gpio5:other-route', 'sim:pwm5')})
        self.assertFalse(snapshot['claims'])
        self.assertFalse(snapshot['owners'])
        for _atom, state in snapshot['resources']:
            if state['kind'] == 'pin':
                self.assertEqual(state, {'kind': 'pin', 'mode': 'high_impedance', 'level': None})
            else:
                self.assertIs(state['enabled'], False)

    def test_cli_gpio_pwm_procedure_exact_replay_and_clean_reopen(self):
        h = self.harness
        discovered = h.cli('discover', {'limit': 10})
        self.assertEqual({item['instanceId'] for item in discovered['items']},
                         {'sim:gpio5', 'sim:gpio6', 'sim:gpio5:other-route', 'sim:pwm5'})
        h.cli('describe', {'instanceId': 'sim:pwm5'})
        observed = h.cli('observe', {'instanceId': 'sim:gpio5', 'property': 'ready',
                                    'maxAgeMs': 10000, 'evidenceKind': 'simulation'})
        self.assertEqual(observed['quality'], 'valid')
        namespace = h.cli('namespace', {'expiresUnixMs': time.time_ns() // 1_000_000 + 600000})['token']
        retained = []
        for n, instance in enumerate(('sim:gpio5', 'sim:pwm5')):
            prepared = h.cli('prepare', parameters(instance, namespace, 'cli:' + str(n), bounds()))
            self.assertFalse(prepared['admitted'])
            self.assertEqual(prepared['requestDigest'], intent_digest(prepared['request']['intent']))
            request = prepared['request']
            accepted = h.cli('invoke', {'request': request})
            done = h.settled(accepted['operationId'])
            self.completed(done, request['intent']['actionId'])
            self.assertEqual(h.cli('invoke', {'request': request}), done)
            changed = copy.deepcopy(request)
            changed['intent']['arguments']['durationMs'] += 1
            h.cli('invoke', {'request': changed}, error='KEY_CONFLICT')
            events = h.cli('events', {'operationId': done['operationId']})
            self.assertFalse(events['gap'])
            self.assertEqual(events['next'], events['head'])
            retained.append((request, done))
        window = bounds()
        requests = [h.cli('prepare', parameters(instance, namespace, 'cli-child:' + str(n), window))['request']
                    for n, instance in enumerate(('sim:gpio6', 'sim:pwm5'))]
        parent_request = sequence(namespace, 'cli-parent', window, requests)
        parent = h.cli('procedure_submit', {'request': parent_request})
        done = h.wait('procedure_status', {'procedureId': parent['procedureId']},
                      lambda value: value['executionState'] == 'completed')
        self.assertEqual(done['cursor'], 2)
        self.assertFalse(done['unresolvedOperations'])
        children = [h.settled(step['operationId']) for step in done['steps']]
        for request, child in zip(requests, children):
            self.completed(child, request['intent']['actionId'])
            self.assertEqual(h.cli('invoke', {'request': request}), child)
        self.assertEqual(h.cli('procedure_submit', {'request': parent_request}), done)
        h.cli('procedure_events', {'procedureId': done['procedureId']})
        self.report['results'].update(ordinary=[value for _, value in retained], procedure=done, children=children)
        h.stop()
        first = h.snapshot('completed-before-reopen')
        self.assert_counts(first, {'sim:gpio5': (1, 1, 0), 'sim:gpio6': (1, 1, 0), 'sim:pwm5': (2, 2, 0)})
        self.assertEqual(len(first['dispatchLinks']), 4)
        h.start(with_file=True)
        for request, value in retained:
            self.assertEqual(h.cli('invoke', {'request': request}), value)
        self.assertEqual(h.cli('procedure_submit', {'request': parent_request}), done)
        h.stop()
        second = h.snapshot('exact-replay-after-reopen')
        for key in ('effects', 'dispatchLinks', 'receipts', 'operations', 'events'):
            self.assertEqual(first[key], second[key])

    def test_SIGKILL_pending_pulse_reopens_idle_without_second_activation(self):
        h = self.harness
        namespace = h.cli('namespace', {'expiresUnixMs': time.time_ns() // 1_000_000 + 600000})['token']
        prepared = h.cli('prepare', parameters('sim:gpio5', namespace, 'crash:pulse', bounds(), duration=4000))
        request = prepared['request']
        accepted = h.cli('invoke', {'request': request})
        operation_id = accepted['operationId']
        deadline = time.monotonic() + 3
        pending = None
        while time.monotonic() < deadline:
            rows = h.rows("SELECT document FROM io_receipts WHERE operation=? AND state='pending'", (operation_id,), board=True)
            if rows:
                pending = json.loads(rows[0][0])
                break
            time.sleep(.01)
        self.assertIsNotNone(pending, 'The actual pending provider boundary was not observed')
        self.assertTrue(pending['result']['activationCommitted'])
        self.assertFalse(pending['result']['safeIdle'])
        self.report['results']['pendingObserved'] = pending
        h.stop(kill=True)
        killed = h.snapshot('after-SIGKILL')
        self.assertEqual([(row[0], row[1]) for row in killed['receipts']], [(operation_id, 'pending')])
        self.assertEqual(len(killed['dispatchLinks']), 1)
        self.assertEqual(len(killed['claims']), 1)
        self.assertEqual(killed['effects'][0], ['sim:gpio5', 1, 0, 0])
        h.start()
        settled = h.settled(operation_id)
        self.assertEqual(settled['executionState'], 'canceled', settled)
        self.assertTrue(settled['mayHaveActed'])
        self.assertEqual(settled['effectVerification'], 'unverified')
        self.assertEqual(settled['result']['output']['result'],
            {'activationCommitted': True, 'cycleCompleted': False, 'safeIdle': True, 'reason': 'board_owner_reopened'})
        self.assertEqual(h.cli('invoke', {'request': request}), settled)
        self.report['results']['reconciled'] = settled
        h.stop()
        reconciled = h.snapshot('reconciled-after-reopen')
        self.assert_counts(reconciled, {'sim:gpio5': (1, 0, 1)})
        self.assertEqual(reconciled['dispatchLinks'], killed['dispatchLinks'])
        receipt = reconciled['receipts'][0][4]
        for atom, state in reconciled['resources']:
            if atom in receipt['idleState']:
                self.assertEqual(state, receipt['idleState'][atom])
        self.assertNotEqual(dict(killed['metadata'])['session'], dict(reconciled['metadata'])['session'])
        h.start(with_file=True)
        self.assertEqual(h.cli('invoke', {'request': request}), settled)
        h.stop()
        again = h.snapshot('second-reopen-exact-replay')
        for key in ('effects', 'receipts', 'dispatchLinks', 'operations', 'events'):
            self.assertEqual(again[key], reconciled[key])

    def run_mcp(self, protocol):
        import anyio
        h = self.harness

        async def exercise():
            async with projection(protocol, h.path, self.report) as probe:
                self.assertEqual(set(probe.tools), {'hardware_' + method for method in METHOD_RESULTS})
                self.assertEqual(len(probe.tools), 14)
                await probe.call('discover', {'limit': 10})
                await probe.call('describe', {'instanceId': 'sim:pwm5'})
                await probe.call('observe', {'instanceId': 'sim:gpio5', 'property': 'ready',
                    'maxAgeMs': 10000, 'evidenceKind': 'simulation'})
                namespace = (await probe.call('namespace', {'expiresUnixMs': time.time_ns() // 1_000_000 + 600000}))['token']
                request = (await probe.call('prepare', parameters('sim:gpio5', namespace, 'mcp:ordinary', bounds())))['request']
                accepted = await probe.call('invoke', {'request': request})
                done = h.settled(accepted['operationId'])
                self.completed(done, 'gpio_pulse')
                self.assertEqual(await probe.call('operation', {'operationId': done['operationId']}), done)
                self.assertEqual(await probe.call('invoke', {'request': request}), done)
                conflict = copy.deepcopy(request)
                conflict['intent']['arguments']['durationMs'] += 1
                await probe.call('invoke', {'request': conflict}, error='KEY_CONFLICT')
                await probe.call('events', {'operationId': done['operationId'], 'after': 0, 'limit': 100})
                window = bounds()
                requests = [(await probe.call('prepare', parameters(instance, namespace, 'mcp-child:' + str(n), window)))['request']
                            for n, instance in enumerate(('sim:pwm5', 'sim:gpio6'))]
                parent_request = sequence(namespace, 'mcp-parent', window, requests)
                parent = await probe.call('procedure_submit', {'request': parent_request})
                completed = h.wait('procedure_status', {'procedureId': parent['procedureId']},
                                   lambda value: value['executionState'] == 'completed')
                self.assertEqual(completed['cursor'], 2)
                self.assertFalse(completed['unresolvedOperations'])
                self.assertEqual(await probe.call('procedure_status', {'procedureId': parent['procedureId']}), completed)
                self.assertEqual(await probe.call('procedure_submit', {'request': parent_request}), completed)
                await probe.call('procedure_events', {'procedureId': parent['procedureId'], 'after': 0, 'limit': 100})
                children = [h.settled(step['operationId']) for step in completed['steps']]
                for child_request, child in zip(requests, children):
                    self.completed(child, child_request['intent']['actionId'])
                    self.assertEqual(await probe.call('invoke', {'request': child_request}), child)
                future = (await probe.call('prepare', parameters('sim:gpio5', namespace, 'mcp:cancel', bounds(delay=120000))))['request']
                waiting = await probe.call('invoke', {'request': future})
                self.assertEqual(waiting['executionState'], 'accepted')
                blocked = (await probe.call('prepare', parameters('sim:pwm5', namespace, 'mcp:busy', bounds())))['request']
                count_query = ('SELECT (SELECT count(*) FROM operations), (SELECT count(*) FROM claims), '
                               'EXISTS(SELECT 1 FROM replay_keys WHERE namespace=? AND caller_key=?)')
                before_busy = h.rows(count_query, (namespace, blocked['operationKey']))
                await probe.call('invoke', {'request': blocked}, error='RESOURCE_BUSY')
                self.assertEqual(h.rows(count_query, (namespace, blocked['operationKey'])), before_busy)
                self.assertEqual(before_busy[0][2], 0)
                canceled = await probe.call('cancel', {'operationId': waiting['operationId']})
                self.assertEqual(canceled['executionState'], 'canceled')
                self.assertFalse(canceled['mayHaveActed'])
                self.assertFalse(canceled['resourceClaims'])
                later = bounds(delay=120000)
                future_child = (await probe.call('prepare', parameters('sim:gpio6', namespace, 'mcp:future-child', later)))['request']
                future_request = sequence(namespace, 'mcp:future-parent', later, [future_child])
                future_parent = await probe.call('procedure_submit', {'request': future_request})
                self.assertEqual(future_parent['executionState'], 'accepted')
                self.report['results'].update(ordinary=done, procedure=completed, children=children,
                                              canceledBeforeDispatch=canceled, futureProcedure=future_parent)
            self.assertEqual(h.call('procedure_status', procedureId=future_parent['procedureId'])['executionState'], 'accepted')
            h.stop()
            before = h.snapshot('MCP-EOF-before-reopen')
            self.assert_counts(before, {'sim:gpio5': (1, 1, 0), 'sim:pwm5': (1, 1, 0), 'sim:gpio6': (1, 1, 0)})
            self.assertEqual(len(before['dispatchLinks']), 3)
            h.start()
            async with projection(protocol, h.path, self.report) as probe:
                paused = await probe.call('procedure_status', {'procedureId': future_parent['procedureId']})
                self.assertEqual(paused['executionState'], 'interrupted')
                self.assertIsNone(paused['steps'][0]['operationId'])
                self.assertEqual(await probe.call('procedure_submit', {'request': future_request}), paused)
                resumed = await probe.call('procedure_resume', {'procedureId': future_parent['procedureId']})
                self.assertEqual(resumed['executionState'], 'accepted')
                canceled = await probe.call('procedure_cancel', {'procedureId': future_parent['procedureId']})
                self.assertTrue(canceled['cancelRequested'])
                final = await probe.call('procedure_status', {'procedureId': future_parent['procedureId']})
                self.assertEqual(final['executionState'], 'canceled')
                self.assertIsNone(final['steps'][0]['operationId'])
                self.assertEqual(await probe.call('invoke', {'request': request}), done)
                self.report['results'].update(interruptedProcedure=paused, resumedProcedure=resumed,
                                              canceledProcedure=final)
            h.stop()
            after = h.snapshot('MCP-reopen-resume-cancel')
            self.assert_counts(after, {'sim:gpio5': (1, 1, 0), 'sim:pwm5': (1, 1, 0), 'sim:gpio6': (1, 1, 0)})
            self.assertEqual(after['receipts'], before['receipts'])
            self.assertEqual(after['dispatchLinks'], before['dispatchLinks'])
            called = set()
            for message in self.report['mcpMessages']:
                if 'sdkToolCall' in message:
                    called.add(message['sdkToolCall']['name'])
                elif message.get('request', {}).get('method') == 'tools/call':
                    called.add(message['request']['params']['name'])
            self.assertEqual(called, {'hardware_' + method for method in METHOD_RESULTS})
            self.report['calledTools'] = sorted(called)

        anyio.run(exercise)

    def test_modern_MCP_shared_catalog_and_io_procedure(self):
        self.run_mcp(MODERN)

    @unittest.skipUnless(sdk_available(), 'Pinned MCP SDK 1.26.0 client required')
    def test_legacy_MCP_shared_catalog_and_io_procedure(self):
        self.run_mcp(LEGACY)
