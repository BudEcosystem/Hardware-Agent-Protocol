"""Original isolated Runtime/SQLite worker trials; no external controller."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.installations import installation_digest, legacy_installation
from hms.journal import Context, JournalError
from hms.pat_compiler import evaluation_environment
from hms.pat_contracts import PatError
from hms.pat_simulation_contracts import CEILINGS, FAN_METADATA, generate_cases, matrix_digest
from hms.pat_simulation_worker import (FAULTS, make_capsule, parse_capsule, run_worker,
    simulation_identities)
from hms import pat_simulation_worker as worker
from hms.runtime import Runtime
from hms.simulator import SimulatedPlant

ARTIFACT = json.loads((Path(__file__).parent / 'fixtures/pat-simulation-fan-artifact.json').read_text())
LAST_REPORT = {'profile': 'hms-pat-worker-tests/0.1', 'cases': []}
RETAIN_OUTPUT_ROOT = None


def fixture(*, alias=False, constant=False, limits=None, rebind=False):
    """Capture real installed descriptor data, with no live operation to copy."""
    limits = dict(CEILINGS if limits is None else limits)
    identities = simulation_identities(limits)
    installation = legacy_installation()
    deployment, layout = 'simulation:local', 'legacy'
    if alias:
        installation['adapterId'] = 'sqlite:west'
        installation['instances'] = {role: 'west:' + role for role in ('fan', 'focus', 'inspection')}
        installation['resources'] = {role: 'west:resource:' + role for role in ('fan', 'focus', 'inspection')}
        deployment, layout = 'simulation:multi', 'multi'
    artifact = copy.deepcopy(ARTIFACT)
    if constant:
        artifact['parameters'] = {}
        for index, step in enumerate(artifact['steps']):
            step['arguments']['level'] = {'literal': 17 + index}
    owner = Context('fixture-owner', deployment)
    with tempfile.TemporaryDirectory() as directory:
        runtime = Runtime(directory, create=True, owner=owner, wall_clock_ms=lambda: 1000,
            monotonic_ms=lambda: 1000, **({'installations': [installation]} if alias else {}))
        try:
            fan = installation['instances']['fan']
            binding, _ = runtime.registry._binding(fan)
            if rebind:
                binding.update(generation='binding:reviewed:7', controlGeneration='control:reviewed:9',
                               calibrationRevision='synthetic:reviewed:3')
                binding['argumentSchemas']['set_level']['properties']['level']['maximum'] = 50
                runtime.registry.bind(owner, canonical(binding))
                runtime.adapters[installation['adapterId']].refresh(force=True)
            descriptor = {'type': runtime.registry._type(binding['typeDigest']), 'binding': binding,
                'endpointSession': runtime.adapters[installation['adapterId']].plant.session,
                'driverProfile': 'sqlite-simulation', 'driverDigest': identities['driverDigest'],
                'installationDigest': 'sha256:' + installation_digest(installation),
                'argumentMetadata': copy.deepcopy(FAN_METADATA)}
        finally:
            runtime.close()
    return make_capsule(artifact, installation, {'fan': descriptor}, deployment=deployment,
        runtime_layout=layout, configuration={'revision': 1, 'digest': 'sha256:' + '1' * 64},
        attempt_id='attempt:original-worker', limits=limits)


def replan(capsule):
    capsule = copy.deepcopy(capsule)
    descriptor = capsule['bindings']['fan']
    env = evaluation_environment(capsule['artifact'], capsule['bindings'],
                                deployment=capsule['evaluationEnvironment']['deployment'])
    capsule['evaluationEnvironment'], capsule['environmentDigest'] = env['evaluationEnvironment'], env['environmentDigest']
    capsule['caseMatrix'] = generate_cases(capsule['artifact'], descriptor, limits=capsule['limits'])
    capsule['matrixDigest'] = matrix_digest(capsule['artifact'], descriptor, limits=capsule['limits'])
    return capsule


def evidence(directory, result):
    records = []
    total = 0
    for page in result['evidencePages']:
        data = (Path(directory) / page['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == page['sha256']
        assert len(data) == page['bytes']
        value = json.loads(data)
        assert value['kind'] == 'evidence_index'
        total += len(data)
        for record in value['value']['records']:
            content = (Path(directory) / record['path']).read_bytes()
            assert hashlib.sha256(content).hexdigest() == record['sha256']
            assert len(content) == record['bytes']
            assert canonical(json.loads(content)) == content
            records.append(json.loads(content))
            total += len(content)
    assert total == result['outputBytes']
    return records


class SimulationWorkerTests(unittest.TestCase):
    def execute(self, capsule):
        if RETAIN_OUTPUT_ROOT is None:
            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            path = Path(directory.name)
        else:
            path = Path(RETAIN_OUTPUT_ROOT) / ('case-%02d' % len(LAST_REPORT['cases']))
            path.mkdir(mode=0o700)
        result = run_worker(capsule, path)
        report = {key: result[key] for key in ('attemptId', 'outcome', 'reason',
            'plannedCases', 'completedCases', 'childOperations', 'schedulerTicks', 'outputBytes',
            'scratchBytes', 'unresolvedEffects')}
        if RETAIN_OUTPUT_ROOT is not None:
            (path / 'test-return.json').write_bytes(canonical(result))
            report['retainedOutput'] = str(path)
        LAST_REPORT['cases'].append(report)
        return path, result

    def test_full_matrix_and_five_actual_lifecycle_trials(self):
        capsule = fixture()
        directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'passed', result)
        self.assertEqual(result['completedCases'], 27)
        self.assertEqual(result['childOperations'], 25)
        self.assertEqual(result['unresolvedEffects'], 0)
        self.assertFalse(result['totalDiskQuotaEnforced'])
        self.assertEqual(result['totalDiskBytes'], result['outputBytes'] + result['scratchBytes'])
        records = evidence(directory, result)
        cases = [row['value'] for row in records if row['kind'] == 'trial_result']
        self.assertEqual({row['caseId'] for row in cases if row['caseId'].startswith('lifecycle:')},
                         {'lifecycle:' + value for value in FAULTS})
        losses = [event for case in cases for event in case['events'] if event['event'] == 'modeled_completion_evidence_loss']
        self.assertEqual(len(losses), 1)
        self.assertFalse(losses[0]['realProcessCrash'])
        starts = [row['value'] for row in records if row['kind'] == 'trial_started']
        self.assertTrue(all(row['originalDependencies'][0]['endpointSession'] !=
                            row['workerDependencies'][0]['endpointSession'] for row in starts))
        self.assertTrue(all(row['environmentDigest'] == capsule['environmentDigest'] for row in starts))
        checkpoints = [row['value'] for row in records if row['kind'] == 'checkpoint']
        self.assertTrue(any(row['label'] == 'after_reopen' and row['procedure']['executionState'] == 'interrupted'
                            for row in checkpoints))
        canonical(result)

    def test_alias_and_noninitial_binding_are_preserved_without_cloning_authority(self):
        capsule = fixture(alias=True, constant=True, rebind=True)
        before = copy.deepcopy(capsule)
        directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'passed', result)
        self.assertEqual(result['completedCases'], 10)
        self.assertEqual(result['childOperations'], 9)
        self.assertEqual(capsule, before)
        records = evidence(directory, result)
        starts = [row['value'] for row in records if row['kind'] == 'trial_started']
        for start in starts:
            dependency = start['workerDependencies'][0]
            self.assertEqual(dependency['instanceId'], 'west:fan')
            self.assertEqual(dependency['bindingGeneration'], 'binding:reviewed:7')
            self.assertEqual(dependency['controlGeneration'], 'control:reviewed:9')
            self.assertEqual(dependency['calibrationRevision'], 'synthetic:reviewed:3')
            self.assertTrue(all(value['value'] == 0 and value['effectCount'] == 0 for value in start['baseline'].values()))
        self.assertTrue(all(row['value']['plan']['request']['replayNamespace'].startswith('replay:')
                            for row in records if row['kind'] == 'compiled_request'))

    def test_closed_capsule_and_identity_tampering_refuse_before_runtime(self):
        original = fixture(constant=True)
        mutations = [lambda c: c.update(authorityPath='/outside/authority.db'),
            lambda c: c.update(endpointFd=7), lambda c: c.update(command=['anything']),
            lambda c: c['configuration'].update(revision=True),
            lambda c: c['identities'].update(driverDigest='sha256:' + 'f' * 64),
            lambda c: c['caseMatrix']['cases'].pop(),
            lambda c: c.update(environmentDigest='sha256:' + 'a' * 64),
            lambda c: c.update(runtimeLayout='unknown'),
            lambda c: c['installation'].update(driver='compact-simulation')]
        with patch('hms.pat_simulation_worker.Runtime', side_effect=AssertionError('unexpected runtime')):
            for mutate in mutations:
                capsule = copy.deepcopy(original); mutate(capsule)
                with self.subTest(mutate=mutate), self.assertRaises(JournalError):
                    parse_capsule(capsule)

    def test_case_and_operation_lifecycle_reservations_refuse_no_truncation(self):
        for limits, code in ((dict(CEILINGS, maxCases=26), 'PAT_SIM_CASE_LIMIT'),
                             (dict(CEILINGS, maxChildOperations=24), 'PAT_SIM_EFFECT_LIMIT')):
            with self.subTest(code=code), self.assertRaises(PatError) as caught:
                fixture(limits=limits)
            self.assertEqual(caught.exception.code, code)

    def test_policy_identity_commits_to_lower_limits(self):
        normal = simulation_identities()
        lowered = simulation_identities(dict(CEILINGS, maxSchedulerTicks=1000))
        self.assertNotEqual(normal['policyDigest'], lowered['policyDigest'])
        for key in ('workerDigest', 'driverDigest', 'compilerDigest'):
            self.assertEqual(normal[key], lowered[key])

    def test_matrix_bool_and_integral_float_substitution_is_rejected(self):
        original = fixture(constant=True)
        for field, replacement in (('plannedChildOperations', 2.0), ('qualificationPassed', 0)):
            capsule = copy.deepcopy(original)
            capsule['caseMatrix'][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(PatError, 'PAT_SIM_MATRIX_MISMATCH'):
                parse_capsule(capsule)
        for replacement in (False, 0.0):
            capsule = copy.deepcopy(original)
            capsule['caseMatrix']['cases'][1]['expected']['plannedChildOperations'] = replacement
            with self.subTest(replacement=replacement), self.assertRaisesRegex(PatError, 'PAT_SIM_MATRIX_MISMATCH'):
                parse_capsule(capsule)

    def test_evidence_readback_detects_changed_written_bytes(self):
        capsule = fixture(constant=True)
        original = worker._Evidence.write
        corrupted = []

        def corrupt_once(writer, kind, value):
            record = original(writer, kind, value)
            if not corrupted:
                path = writer.directory / Path(record['path']).name
                data = path.read_bytes()
                path.write_bytes(b' ' + data[1:])
                corrupted.append(record['path'])
            return record

        with patch.object(worker._Evidence, 'write', corrupt_once):
            _directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertEqual(result['reason'], 'PAT_SIM_EVIDENCE_CHANGED')
        self.assertFalse(result['qualificationPassed'])

    def test_deadline_is_fail_closed_at_checked_boundary(self):
        capsule = fixture(constant=True, limits=dict(CEILINGS, workerDeadlineMs=1))
        ticks = iter((0.0, 0.1, 0.2, 0.3, 0.4))
        with patch.object(worker.time, 'monotonic', side_effect=lambda: next(ticks)):
            _directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertEqual(result['reason'], 'PAT_SIM_WORKER_DEADLINE')
        self.assertEqual(result['childOperations'], 0)
        self.assertIsNone(result['unresolvedEffects'])

    def test_tick_budget_preserves_pending_receipt_and_reports_unresolved(self):
        capsule = fixture(constant=True, limits=dict(CEILINGS, maxSchedulerTicks=1))
        directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertFalse(result['qualificationPassed'])
        self.assertEqual(result['reason'], 'PAT_SIM_TICK_LIMIT')
        self.assertEqual(result['unresolvedEffects'], 1)
        self.assertEqual(result['schedulerTicks'], 1)
        plant = directory / 'work/trial-00/simulated-plant.db'
        with sqlite3.connect('file:' + str(plant) + '?mode=ro', uri=True) as db:
            self.assertEqual(db.execute('SELECT state FROM receipts').fetchone()[0], 'pending')
            self.assertEqual(db.execute('SELECT sum(effects) FROM devices').fetchone()[0], 0)

    def test_output_budget_never_truncates_or_claims_success(self):
        capsule = fixture(constant=True, limits=dict(CEILINGS, maxOutputBytes=1))
        directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertEqual(result['reason'], 'PAT_SIM_OUTPUT_LIMIT')
        self.assertEqual(result['outputBytes'], 0)
        self.assertEqual(result['completedCases'], 0)
        self.assertEqual(list((directory / 'hms_qualification.evidence').iterdir()), [])
        self.assertIsNone(result['unresolvedEffects'])

    def test_original_timing_bounds_are_not_widened_for_behavioral_success(self):
        capsule = fixture(constant=True)
        for step in capsule['artifact']['steps']:
            step['timing']['maxRunMs'] = 50
        capsule = replan(capsule)
        directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(result['reason'], 'PAT_SIM_ORACLE_FAILED')
        self.assertFalse(result['qualificationPassed'])
        records = evidence(directory, result)
        plans = [row['value']['plan'] for row in records if row['kind'] == 'compiled_request']
        self.assertEqual(plans[0]['request']['procedure']['steps'][0]['request']['intent']['timing']['maxRunMs'], 50)

    def test_actual_extra_effect_is_detected_by_oracle(self):
        capsule = fixture(constant=True)
        original = SimulatedPlant.finish

        def extra(plant, operation_id, **options):
            receipt = original(plant, operation_id, **options)
            if receipt['state'] == 'completed':
                plant.db.execute('UPDATE devices SET effects=effects+1 WHERE id=?',
                                 (receipt['intent']['instanceId'],))
            return receipt

        with patch.object(SimulatedPlant, 'finish', extra):
            directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertIsNone(result['unresolvedEffects'])
        self.assertEqual(result['reason'], 'PAT_SIM_ORACLE_FAILED')
        self.assertIn('fan final state/effect count mismatch',
            [row['value']['detail'] for row in evidence(directory, result) if row['kind'] == 'trial_error'])

    def test_unrelated_device_effect_is_detected_by_oracle(self):
        capsule = fixture(constant=True)
        original = SimulatedPlant.finish

        def unrelated(plant, operation_id, **options):
            result = original(plant, operation_id, **options)
            plant.db.execute('UPDATE devices SET effects=effects+1 WHERE id=?', (plant.installation['instances']['focus'],))
            return result

        with patch.object(SimulatedPlant, 'finish', unrelated):
            directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertIsNone(result['unresolvedEffects'])
        self.assertIn('unrelated installed device changed',
            [row['value']['detail'] for row in evidence(directory, result) if row['kind'] == 'trial_error'])

    def test_receipt_boolean_integer_substitution_cannot_pass_oracle(self):
        capsule = fixture(constant=True)
        original = SimulatedPlant.finish

        def changed_receipt(plant, operation_id, **options):
            receipt = original(plant, operation_id, **options)
            if receipt['state'] == 'completed':
                result = dict(receipt['result'], effectCommitted=1)
                plant.db.execute('UPDATE receipts SET result=? WHERE id=?', (canonical(result), operation_id))
                return plant.receipt(operation_id)
            return receipt

        with patch.object(SimulatedPlant, 'finish', changed_receipt):
            directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertEqual(result['reason'], 'PAT_SIM_ORACLE_FAILED')
        self.assertIsNone(result['unresolvedEffects'])
        self.assertIn('completion oracle mismatch',
            [row['value']['detail'] for row in evidence(directory, result) if row['kind'] == 'trial_error'])

    def test_same_initial_generation_with_changed_document_refuses_reconstruction(self):
        capsule = fixture(constant=True)
        capsule['bindings']['fan']['binding']['controlGeneration'] = 'changed:same-generation'
        capsule = replan(capsule)
        directory, result = self.execute(capsule)
        self.assertEqual(result['outcome'], 'inconclusive')
        self.assertEqual(result['reason'], 'PAT_SIM_UNSUPPORTED_RECONSTRUCTION')
        self.assertEqual(result['childOperations'], 0)

    def test_private_empty_directory_required(self):
        capsule = fixture(constant=True)
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / 'out'; path.mkdir(mode=0o700)
            (path / 'retained').write_text('must not overwrite')
            with self.assertRaisesRegex(PatError, 'PAT_SIM_PRIVATE_DIRECTORY_REQUIRED'):
                run_worker(capsule, path)
            self.assertEqual((path / 'retained').read_text(), 'must not overwrite')


if __name__ == '__main__':
    unittest.main()
