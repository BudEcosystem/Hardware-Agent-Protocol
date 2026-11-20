"""Real CLI/daemon integration against durable synthetic state, without hardware."""
import json
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import unittest

from hms.contracts import intent_digest
from test_multi_cli import finish_transport_failure, retain_transport_failure
from tests.sqlite_observer import readonly_rows

ROOT = Path(__file__).resolve().parents[1]
LAST_REPORT = {'schema': 'hms-runtime-ipc-transport-tests/1', 'cases': {}}


@unittest.skipUnless(sys.platform == 'linux' and hasattr(socket, 'SO_PEERCRED'), 'Linux local transport required')
class RuntimeIpc(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hms-runtime-ipc-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.state = self.path / 'state'
        self.socket = self.path / 'control.sock'
        self.process = None
        self.report = {'passed':False,'commands':[],'processOutput':[],'readiness':[], 'observerReads':[]}
        LAST_REPORT['cases'][self.id()] = self.report
        self.addCleanup(lambda: finish_transport_failure(self.report))
        self.addCleanup(self.stop_server)
        self.addCleanup(self._retain_test_failure)

    def _retain_test_failure(self):
        result = self._outcome.result
        failures = [(test, text) for test, text in [*result.failures, *result.errors]
                    if test is self or getattr(test, 'test_case', None) is self]
        self.report['passed'] = not failures
        if failures:
            retain_transport_failure(self.report, self.id(), self.state,
                                     '\n'.join(text for _, text in failures), base=self.path)

    def command(self, *arguments, check=True):
        entry = {'arguments':list(arguments),'check':check}
        self.report['commands'].append(entry)
        completed = subprocess.run([sys.executable, '-m', 'hms', '--socket', str(self.socket), *arguments],
                                   cwd=ROOT, text=True, capture_output=True, timeout=15)
        entry.update(exitCode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        if check:
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, '')
            return json.loads(completed.stdout)
        return completed

    def start_server(self, *, initialize=False):
        self.assertIsNone(self.process)
        arguments = [sys.executable, '-m', 'hms', 'serve', '--state-dir', str(self.state), '--socket', str(self.socket)]
        if initialize:
            arguments.append('--init-simulation')
        self.process = subprocess.Popen(arguments, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        readable, _, _ = select.select([self.process.stdout], [], [], 15)
        self.assertTrue(readable, 'daemon did not report readiness')
        line = self.process.stdout.readline()
        if not line:
            process, self.process = self.process, None
            output, error = process.communicate(timeout=5)
            self.report['processOutput'].append({'stdout':output,'stderr':error,
                'exitCode':process.returncode,'readinessFailed':True})
            self.fail('daemon failed before readiness: ' + error)
        ready = json.loads(line)
        self.report['readiness'].append(ready)
        self.assertEqual(ready['protocol'], 'hctl.local/0.1')
        self.assertTrue(ready['ready'])
        self.assertEqual(ready['deployment'], 'simulation:local')
        self.assertEqual(Path(ready['socket']), self.socket)

    def stop_server(self):
        if self.process is None:
            return
        process, self.process = self.process, None
        try:
            if process.poll() is None:
                process.terminate()
            try:
                output, error = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                output, error = process.communicate(timeout=5)
                self.report['processOutput'].append({'stdout':output,'stderr':error,
                    'exitCode':process.returncode,'stopTimedOut':True})
                self.fail('daemon did not drain on SIGTERM')
            self.report['processOutput'].append({'stdout':output,'stderr':error,
                'exitCode':process.returncode,'stopTimedOut':False})
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(output, '')
            self.assertEqual(error, '')
            self.assertFalse(self.socket.exists(), 'clean shutdown left its socket behind')
        except BaseException:
            retain_transport_failure(self.report, self.id() + '-cleanup', self.state,
                                     traceback.format_exc(), base=self.path)
            raise
        finally:
            finish_transport_failure(self.report)

    def prepare(self, instance, action, arguments, namespace, key, *, delay_ms=0, effect='capability_completion'):
        now = time.time_ns() // 1_000_000
        params = {
            'instanceId': instance, 'actionId': action, 'arguments': arguments,
            'replayNamespace': namespace, 'operationKey': key, 'requiredEffect': effect,
            'timing': {'notBeforeUnixMs': now + delay_ms, 'latestStartUnixMs': now + 60000,
                       'maxRunMs': 5000, 'latestCompletionUnixMs': now + 120000},
        }
        params_path = self.path / f'{key}.prepare.json'
        params_path.write_text(json.dumps(params) + '\n')
        prepared = self.command('prepare', '--params-file', str(params_path))
        self.assertFalse(prepared['admitted'])
        self.assertEqual(prepared['requestDigest'], intent_digest(prepared['request']['intent']))
        request_path = self.path / f'{key}.invoke.json'
        request_path.write_text(json.dumps(prepared['request']) + '\n')
        return request_path, prepared

    def settled(self, operation_id):
        deadline = time.monotonic() + 15
        while True:
            status = self.command('operation', operation_id)
            if status['executionState'] in {'completed', 'failed', 'canceled', 'rejected_before_dispatch'}:
                return status
            if time.monotonic() >= deadline:
                self.fail(f'operation failed to settle: {status}')
            time.sleep(0.02)

    def plant_rows(self):
        # Verify persisted world state independently of the CLI's self-report.
        entry = {'database': 'simulated-plant.db'}
        self.report['observerReads'].append(entry)
        rows = readonly_rows(self.state / 'simulated-plant.db', 'SELECT id,value,effects FROM devices', report=entry)
        return {instance: (json.loads(value), effects) for instance, value, effects in rows}

    def test_three_scenarios_prepare_invoke_replay_and_clean_reopen(self):
        self.start_server(initialize=True)
        first = self.command('discover', '--limit', '1')
        self.assertEqual(len(first['items']), 1)
        self.assertIsNotNone(first['cursor'])
        rest = self.command('discover', '--limit', '10', '--cursor', first['cursor'])
        self.assertEqual(len(rest['items']), 2)
        self.assertIsNone(rest['cursor'])
        self.assertEqual({item['instanceId'] for item in first['items'] + rest['items']},
                         {'sim:home-fan', 'sim:microscope', 'sim:inspection-cell'})
        namespace = self.command('namespace', '--expires-unix-ms', str(time.time_ns() // 1_000_000 + 180000))['token']
        cases = [
            ('sim:home-fan', 'set_level', {'level': 37, 'unit': 'percent'}, 37),
            ('sim:microscope', 'move_absolute', {'position': 12.5, 'unit': 'um', 'frame': 'sim:microscope'}, 12.5),
            ('sim:inspection-cell', 'inspect', {'recipe': 2, 'partId': 'synthetic-part'}, 1),
        ]
        records = []
        for ordinal, (instance, action, arguments, expected) in enumerate(cases):
            with self.subTest(instance=instance):
                description = self.command('describe', instance)
                self.assertEqual(description['instance']['identity_kind'], 'simulation')
                self.assertFalse(description['type']['td']['hms:commissioned'])
                request_path, prepared = self.prepare(instance, action, arguments, namespace, f'case-{ordinal}')
                self.assertEqual(prepared['request']['intent']['descriptionDigest'], description['descriptionDigest'])
                submitted = self.command('invoke', '--request-file', str(request_path))
                operation_id = submitted['operationId']
                complete = self.settled(operation_id)
                self.assertEqual(complete['executionState'], 'completed', complete)
                self.assertEqual(complete['result']['evidenceKind'], 'simulation')
                self.assertTrue(complete['result']['output']['effectCommitted'])
                self.assertEqual(complete['resourceClaims'], [])
                replayed = self.command('invoke', '--request-file', str(request_path))
                self.assertEqual(replayed['operationId'], operation_id)
                if ordinal == 0:
                    changed = json.loads(request_path.read_text())
                    changed['intent']['arguments']['level'] = 38
                    changed_path = self.path / 'changed-intent.json'
                    changed_path.write_text(json.dumps(changed) + '\n')
                    refusal = self.command('invoke', '--request-file', str(changed_path), check=False)
                    self.assertEqual(refusal.returncode, 1)
                    self.assertEqual(json.loads(refusal.stderr), {'error': {'code': 'KEY_CONFLICT'}})
                    unsupported = json.loads((self.path / 'case-0.prepare.json').read_text())
                    unsupported['requiredEffect'] = 'physical_verified'
                    unsupported['operationKey'] = 'unsupported-physical-evidence'
                    unsupported_path = self.path / 'physical.prepare.json'
                    unsupported_path.write_text(json.dumps(unsupported) + '\n')
                    refusal = self.command('prepare', '--params-file', str(unsupported_path), check=False)
                    self.assertEqual(refusal.returncode, 1)
                    self.assertEqual(json.loads(refusal.stderr), {'error': {'code': 'PHYSICAL_EVIDENCE_UNAVAILABLE'}})
                observed = self.command('observe', instance, 'value', '--max-age-ms', '1000', '--evidence-kind', 'simulation')
                self.assertEqual(observed['value'], expected)
                self.assertEqual(observed['quality'], 'valid')
                events = self.command('events', operation_id, '--after', '0', '--limit', '100')
                self.assertFalse(events['gap'])
                self.assertEqual(events['next'], complete['eventSequence'])
                self.assertEqual([item['sequence'] for item in events['events']], list(range(1, events['head'] + 1)))
                records.append((request_path, operation_id, complete['requestDigest']))
        self.stop_server()
        expected_rows = {instance: (expected, 1) for instance, _, _, expected in cases}
        self.assertEqual(self.plant_rows(), expected_rows)
        self.start_server()
        for request_path, operation_id, digest in records:
            with self.subTest(reopened_operation=operation_id):
                replay = self.command('invoke', '--request-file', str(request_path))
                self.assertEqual(replay['operationId'], operation_id)
                self.assertEqual(replay['requestDigest'], digest)
                self.assertEqual(replay['executionState'], 'completed')
        self.stop_server()
        self.assertEqual(self.plant_rows(), expected_rows)

    def test_cancel_before_dispatch_and_replay_does_not_create_effect(self):
        self.start_server(initialize=True)
        namespace = self.command('namespace', '--expires-unix-ms', str(time.time_ns() // 1_000_000 + 180000))['token']
        path, _ = self.prepare('sim:home-fan', 'set_level', {'level': 50, 'unit': 'percent'}, namespace,
                               'cancel-before-start', delay_ms=30000)
        accepted = self.command('invoke', '--request-file', str(path))
        self.assertEqual(accepted['executionState'], 'accepted')
        canceled = self.command('cancel', accepted['operationId'])
        self.assertEqual(canceled['executionState'], 'canceled')
        self.assertFalse(canceled['mayHaveActed'])
        replay = self.command('invoke', '--request-file', str(path))
        self.assertEqual(replay['operationId'], accepted['operationId'])
        self.assertEqual(replay['executionState'], 'canceled')
        self.stop_server()
        self.assertEqual(self.plant_rows()['sim:home-fan'], (0, 0))

    def test_missing_state_is_not_initialized_by_ordinary_startup(self):
        completed = self.command('serve', '--state-dir', str(self.state), check=False)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn('error', json.loads(completed.stderr))
        self.assertFalse((self.state / 'authority.db').exists())
        self.assertFalse(self.socket.exists())


if __name__ == '__main__':
    unittest.main()
