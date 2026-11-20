"""Original local PAT composition; trusted test evaluation, no model/hardware.

The evaluator below supplies synthetic qualification receipts for contract
tests. It is not a learned synthesizer or full-domain production evaluator.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hms.contracts import canonical
from hms.installations import installation_digest, legacy_installation
from hms.journal import Context, JournalError
from hms.pat_bindings import RegistryPatBindings
from hms.pat_catalog import Evaluator, PatCatalog
from hms.pat_compiler import compile_pat, compiler_digest
from hms.pat_contracts import PatError, pat_digest
from hms.pat_execution import PatExecutionStore, parse_run
from hms.runtime import Runtime
from test_pat_catalog import CHECKS, digest, result
import test_pat_compiler as compiler_fixtures
from test_pat_compiler import artifact, metadata


OWNER = Context('pat-execution-owner', 'simulation:local')


class Fixture:
    def __init__(self, directory, *, create=True, clock=None):
        self.clock = clock if clock is not None else [1000]
        self.runtime = Runtime(directory, create=create, owner=OWNER if create else None,
            wall_clock_ms=lambda: self.clock[0], monotonic_ms=lambda: self.clock[0])
        self.program = artifact()
        self.params = {'initialLevel': 12, 'finalLevel': 73}
        self.bindings, self.environments = {}, {}
        self.calls = 0
        self.enabled = True
        self.spec = Evaluator('execution-fixture', digest('execution-fixture'), digest('execution-policy'),
            CHECKS, lambda program, environment: result(), lambda: self.enabled)
        self.catalog = PatCatalog(self.runtime.journal, compiler_digest=compiler_digest,
            environment=lambda context, program: copy.deepcopy(self.environments[pat_digest(program)]),
            evaluators=(self.spec,))
        self.store = PatExecutionStore(self.runtime.journal, self.catalog, self.runtime.procedures,
                                      resolver=self.resolve)
        if create:
            self.namespace = self.runtime.request(OWNER, 'namespace', {'expiresUnixMs': 100000})['token']

    def close(self):
        self.runtime.close()

    def request(self, key='run:1'):
        return {'protocol': 'hms.pat-run/0.1', 'replayNamespace': self.namespace, 'runKey': key,
            'taskKind': self.program['taskKind'], 'inputProfile': self.program['inputProfile'],
            'parameters': copy.deepcopy(self.params), 'evidenceMode': 'simulation',
            'originUnixMs': self.clock[0], 'latestCompletionUnixMs': self.clock[0] + 3000}

    def descriptor(self):
        description = self.runtime.request(OWNER, 'describe', {'instanceId': 'sim:home-fan'})
        config = self.runtime.adapters['simulator:local'].installation
        return {'type': description['type'], 'binding': description['binding'],
            'endpointSession': description['presence']['session'], 'driverProfile': config['driver'],
            'driverDigest': 'sha256:' + hashlib.sha256((ROOT/'hms/local_adapter.py').read_bytes()).hexdigest(),
            'installationDigest': 'sha256:' + installation_digest(config),
            'argumentMetadata': {'set_level': {'level': metadata('percent', unit_argument='unit'), 'unit': metadata()}}}

    def resolve(self, context, program, request):
        self.calls += 1
        return {'complete': True, 'assignments': copy.deepcopy(self.bindings[pat_digest(program)])}

    def activate(self, program=None, bindings=None):
        program = copy.deepcopy(program or self.program)
        key = pat_digest(program)
        bound = bindings or {'fan': self.descriptor()}
        compiled = self.store._compile(OWNER, self.request(), program, key, bound)
        self.bindings[key] = [copy.deepcopy(bound)]
        self.environments[key] = compiled['evaluationEnvironment']
        self.catalog.publish(OWNER, program)
        self.catalog.evaluate(OWNER, key, self.spec.evaluator_id, 'eval:' + str(self.catalog._revision(OWNER.deployment)))
        self.catalog.transition(OWNER, key, expected_revision=self.catalog._revision(OWNER.deployment), target='active')
        return key

    def counts(self):
        tables = ('px_instances', 'px_triggers', 'pr_procedures', 'pr_steps', 'pr_keys', 'operations', 'replay_keys')
        return tuple(self.runtime.journal._db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in tables)


class PatExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixture = Fixture(self.directory.name)
        self.addCleanup(lambda: self.fixture.close())
        self.program_id = self.fixture.activate()

    def code(self, code, callback, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_exact_run_replay_has_one_atomic_instance_and_procedure(self):
        f = self.fixture
        request = f.request()
        first = f.store.run(OWNER, request)
        self.assertEqual(first, f.store.run(OWNER, request))
        self.assertEqual(f.calls, 1)
        self.assertEqual(f.counts(), (1, 1, 1, 2, 3, 0, 0))
        row = f.store._row(first['instanceId'])
        self.assertEqual(json.loads(row['request']), request)
        self.assertEqual(json.loads(row['parameters']), request['parameters'])
        self.assertEqual(json.loads(row['compiled_request']), json.loads(row['compilation'])['request'])
        self.assertEqual(json.loads(row['evaluation'])['environment'], json.loads(row['environment']))
        self.assertEqual(row['compiled_digest'], first['procedure']['requestDigest'])
        changed = copy.deepcopy(request); changed['parameters']['finalLevel'] = 72
        self.code('KEY_CONFLICT', f.store.run, OWNER, changed)
        self.assertEqual(f.counts(), (1, 1, 1, 2, 3, 0, 0))

    def test_strict_run_shape_and_integral_float_cannot_alias_accepted_replay(self):
        f = self.fixture
        request = f.request(); f.store.run(OWNER, request)
        for changed in [request | {'bindings': {}}, request | {'originUnixMs': 1000.0},
                        request | {'parameters': {'initialLevel': 12.0, 'finalLevel': 73}},
                        request | {'parameters': {'initialLevel': [], 'finalLevel': 73}}]:
            with self.subTest(changed=changed), self.assertRaises(PatError):
                f.store.run(OWNER, changed)
        self.assertEqual(f.calls, 1)

    def test_no_match_and_parameter_domains_reserve_nothing(self):
        f = self.fixture
        for request in [f.request() | {'taskKind': 'novel:task'},
                        f.request() | {'parameters': {'initialLevel': 101, 'finalLevel': 73}}]:
            self.code('PAT_NO_MATCH', f.store.run, OWNER, request)
        self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))

    def test_ambiguity_is_not_resolved_by_busy_resources(self):
        f = self.fixture
        other = copy.deepcopy(f.program); other['version'] = '2'
        f.activate(other)
        raw = f.runtime.request(OWNER, 'prepare', {'instanceId': 'sim:home-fan', 'actionId': 'set_level',
            'arguments': {'level': 1, 'unit': 'percent'}, 'operationKey': 'busy', 'replayNamespace': f.namespace,
            'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': 1000,
                'latestStartUnixMs': 10000, 'maxRunMs': 500, 'latestCompletionUnixMs': 11000}})['request']
        f.runtime.request(OWNER, 'invoke', {'request': raw})
        before = f.counts()
        self.code('PAT_AMBIGUOUS', f.store.run, OWNER, f.request())
        self.assertEqual(before, f.counts())

    def test_missing_or_stale_presence_does_not_change_static_selection(self):
        f = self.fixture
        with f.runtime.journal._transaction():
            f.runtime.journal._db.execute('DELETE FROM reg_presence')
        run = f.store.run(OWNER, f.request())
        self.assertEqual(run['procedure']['executionState'], 'accepted')
        # The later child admission is the live boundary and refuses no presence.
        f.runtime.procedures.tick()
        state = f.store.status(OWNER, run['instanceId'])
        self.assertEqual(state['procedure']['executionState'], 'failed')
        self.assertIsNone(state['procedure']['steps'][0]['operationId'])

    def test_scoped_nonadmin_can_compose_only_existing_action_authority(self):
        f = self.fixture
        user = Context('pat-scoped', OWNER.deployment)
        registry = f.runtime.registry
        for target, verb in (('*', 'namespace'), ('sim:home-fan', 'read'), ('sim:home-fan', 'invoke:set_level')):
            registry.grant(OWNER, user.principal, target, verb)
        namespace = f.runtime.request(user, 'namespace', {'expiresUnixMs': 100000})['token']
        request = f.request() | {'replayNamespace': namespace}
        run = f.store.run(user, request)
        self.code('ACCESS_DENIED', f.catalog.publish, user, f.program)
        registry.grant(OWNER, user.principal, 'sim:home-fan', 'invoke:set_level', enabled=False)
        self.assertEqual(run, f.store.run(user, request))
        self.code('PAT_NO_MATCH', f.store.run, user, request | {'runKey': 'run:denied'})
        registry.grant(OWNER, user.principal, 'sim:home-fan', 'read', enabled=False)
        self.code('ACCESS_DENIED', f.store.run, user, request)
        self.assertTrue(f.store.cancel(user, run['instanceId'])['procedure']['cancelRequested'])

    def test_provider_invalid_incomplete_duplicate_and_overflow_fail_before_writes(self):
        f = self.fixture
        good = {'fan': f.descriptor()}
        bad = copy.deepcopy(good); del bad['fan']['argumentMetadata']
        variants = [None, {'complete': False, 'assignments': []},
            {'complete': True, 'assignments': [good, good]},
            {'complete': True, 'assignments': [good] * 17},
            {'complete': True, 'assignments': [bad]}]
        for value in variants:
            with self.subTest(value=value), patch.object(f.store, 'resolver', return_value=value):
                with self.assertRaises(JournalError):
                    f.store.run(OWNER, f.request())
            self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))
        with patch.object(f.store, 'resolver', side_effect=RuntimeError('provider unavailable')):
            self.code('PAT_BINDINGS_UNAVAILABLE', f.store.run, OWNER, f.request())

    def test_compiled_environment_must_equal_current_passed_evaluation(self):
        f = self.fixture
        f.bindings[self.program_id][0]['fan']['driverDigest'] = digest('changed-driver')
        self.code('PAT_NO_MATCH', f.store.run, OWNER, f.request())
        self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))
        f.bindings[self.program_id][0]['fan']['driverDigest'] = f.descriptor()['driverDigest']
        f.environments[self.program_id]['roles']['fan']['driverDigest'] = digest('changed-current')
        self.code('PAT_NO_MATCH', f.store.run, OWNER, f.request())

    def test_exact_replay_bypasses_suspension_resolver_clock_and_reopen(self):
        f = self.fixture
        request = f.request(); run = f.store.run(OWNER, request)
        f.catalog.transition(OWNER, self.program_id, expected_revision=f.catalog._revision(OWNER.deployment), target='suspended')
        f.clock[0] = True
        with patch.object(f.store, 'resolver', side_effect=AssertionError('no replay resolution')):
            self.assertEqual(run, f.store.run(OWNER, request))
        f.clock[0] = 1000
        f.close()
        self.fixture = Fixture(self.directory.name, create=False)
        restored = self.fixture.store.run(OWNER, request)
        self.assertEqual(restored['instanceId'], run['instanceId'])
        self.assertEqual(restored['procedure']['executionState'], 'interrupted')
        self.assertEqual(self.fixture.calls, 0)
        resumed = self.fixture.store.resume(OWNER, run['instanceId'])
        self.assertEqual(resumed['procedure']['executionState'], 'accepted')

    def test_evaluator_revocation_blocks_new_run_but_not_pinned_run(self):
        f = self.fixture
        first = f.store.run(OWNER, f.request())
        f.enabled = False
        self.code('PAT_NO_MATCH', f.store.run, OWNER, f.request('run:2'))
        self.assertEqual(first, f.store.run(OWNER, f.request()))

    def test_unavailable_evaluator_cannot_manufacture_a_unique_match(self):
        f = self.fixture
        failed = [False]
        def enabled():
            if failed[0]:
                raise RuntimeError('evaluator health unavailable')
            return True
        second = Evaluator('other-evaluator', digest('other-evaluator'), digest('other-policy'),
                           CHECKS, lambda p, e: result(), enabled)
        catalog = PatCatalog(f.runtime.journal, compiler_digest=compiler_digest,
            environment=lambda c, p: f.environments[pat_digest(p)], evaluators=(f.spec, second))
        program = copy.deepcopy(f.program); program['version'] = 'other'
        key = pat_digest(program)
        bound = {'fan': f.descriptor()}
        f.bindings[key] = [bound]
        f.environments[key] = f.store._compile(OWNER, f.request(), program, key, bound)['evaluationEnvironment']
        catalog.publish(OWNER, program)
        catalog.evaluate(OWNER, key, second.evaluator_id, 'unavailable-test')
        catalog.transition(OWNER, key, expected_revision=catalog._revision(OWNER.deployment), target='active')
        f.store.catalog = catalog
        failed[0] = True
        self.code('PAT_EVALUATOR_UNAVAILABLE', f.store.run, OWNER, f.request())
        self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))

    def test_malformed_live_environment_is_not_filtered_into_a_unique_match(self):
        f = self.fixture
        other = copy.deepcopy(f.program); other['version'] = '2'
        other_id = f.activate(other)
        f.environments[other_id]['profile'] = 'invalid-profile'
        self.code('PAT_ENVIRONMENT_UNSUPPORTED', f.store.run, OWNER, f.request())
        self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))

    def test_pruned_namespace_cannot_revive_retained_run(self):
        f = self.fixture
        request = f.request(); run = f.store.run(OWNER, request)
        f.clock[0] = 100001
        f.runtime.journal.prune_expired_namespaces(OWNER)
        with self.assertRaises(JournalError):
            f.store.run(OWNER, request)
        self.assertEqual(f.store.status(OWNER, run['instanceId'])['instanceId'], run['instanceId'])
        self.assertEqual(f.counts()[:3], (1, 1, 1))

    def test_accidental_resolver_mutation_rolls_back_instead_of_joining_admission(self):
        f = self.fixture
        before = f.runtime.registry._meta('revision')
        def mutating(context, program, request):
            f.runtime.registry._bump()
            return f.resolve(context, program, request)
        with patch.object(f.store, 'resolver', mutating):
            self.code('PAT_RESOLVER_IMPURE', f.store.run, OWNER, f.request())
        self.assertEqual(f.runtime.registry._meta('revision'), before)
        self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))

    def test_raw_or_plain_procedure_key_cannot_be_adopted(self):
        f = self.fixture
        request = f.request()
        compiled = f.store._compile(OWNER, request, f.program, self.program_id, {'fan': f.descriptor()})
        f.runtime.procedures.submit(OWNER, compiled['request'])
        before = f.counts()
        self.code('KEY_CONFLICT', f.store.run, OWNER, request)
        self.assertEqual(before, f.counts())

    def test_link_corruption_refuses_without_replacement(self):
        f = self.fixture
        request = f.request(); run = f.store.run(OWNER, request)
        with f.runtime.journal._transaction():
            f.runtime.journal._db.execute('DELETE FROM pr_keys WHERE namespace=? AND caller_key=?',
                (f.namespace, request['runKey']))
        self.code('PAT_LINK_INVALID', f.store.run, OWNER, request)
        self.assertEqual(f.counts()[:3], (1, 1, 1))

    def test_concurrent_identical_and_conflicting_runs_have_one_identity(self):
        f = self.fixture
        barrier = threading.Barrier(6)
        def submit(index):
            request = f.request(); request['parameters']['finalLevel'] = 70 + index % 2
            barrier.wait()
            try:
                return f.store.run(OWNER, request)['instanceId']
            except JournalError as error:
                return error.code
        with ThreadPoolExecutor(6) as pool:
            values = list(pool.map(submit, range(6)))
        identities = {value for value in values if value != 'KEY_CONFLICT'}
        self.assertEqual(len(identities), 1)
        self.assertEqual(values.count('KEY_CONFLICT'), 3)
        self.assertEqual(f.counts()[:3], (1, 1, 1))

    def test_trigger_write_failure_rolls_back_procedure_and_all_keys(self):
        f = self.fixture
        with f.runtime.journal._transaction():
            f.runtime.journal._db.execute("CREATE TRIGGER reject_px BEFORE INSERT ON px_triggers BEGIN SELECT RAISE(ABORT,'test fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            f.store.run(OWNER, f.request())
        self.assertEqual(f.counts(), (0, 0, 0, 0, 0, 0, 0))

    def test_partial_schema_and_missing_version_fail_closed(self):
        f = self.fixture
        with f.runtime.journal._transaction():
            f.runtime.journal._db.execute('DELETE FROM px_meta')
        self.code('UNSUPPORTED_PAT_EXECUTION', PatExecutionStore, f.runtime.journal, f.catalog,
                  f.runtime.procedures, resolver=f.resolve)
        with f.runtime.journal._transaction():
            f.runtime.journal._db.execute('DROP TABLE px_triggers')
        self.code('INCOMPLETE_PAT_EXECUTION', PatExecutionStore, f.runtime.journal, f.catalog,
                  f.runtime.procedures, resolver=f.resolve)

    def test_procedure_private_seam_requires_active_transaction(self):
        f = self.fixture
        compiled = f.store._compile(OWNER, f.request(), f.program, self.program_id, {'fan': f.descriptor()})
        self.code('PROCEDURE_TRANSACTION_REQUIRED', f.runtime.procedures._submit_in_tx,
                  OWNER, compiled['request'], compiled['requestDigest'])


class PatExecutionInstalledTests(unittest.TestCase):
    def test_inaccessible_evaluated_alias_does_not_block_authorized_alias_or_hide_ambiguity(self):
        owner = Context('alias-owner', 'simulation:multi')
        user = Context('west-only', owner.deployment)
        configs = []
        for alias in ('east', 'west'):
            config = legacy_installation()
            config['adapterId'] = 'scoped:' + alias
            config['instances'] = {role: 'sim:' + alias + ':' + role for role in config['instances']}
            config['resources'] = {role: 'resource:' + alias + ':' + role for role in config['resources']}
            configs.append(config)
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(directory, create=True, owner=owner, installations=configs,
                              wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)
            try:
                programs = [artifact(), artifact()]
                programs[1]['version'] = 'west'
                registrations, assignments, calls = [], {}, []
                for program, config in zip(programs, configs):
                    instance = config['instances']['fan']
                    description = runtime.request(owner, 'describe', {'instanceId': instance})
                    registrations.append({'instanceId': instance, 'typeDigest': description['descriptionDigest'],
                        'driverProfile': config['driver'], 'driverDigest': digest('local-original'),
                        'installationDigest': 'sha256:' + installation_digest(config),
                        'argumentMetadata': {'set_level': {'level': metadata('percent', unit_argument='unit'), 'unit': metadata()}}})
                    assignments[pat_digest(program)] = {'fan': instance}
                provider = RegistryPatBindings(runtime, registrations)
                namespace = runtime.request(owner, 'namespace', {'expiresUnixMs': 100000})['token']
                request = {'protocol': 'hms.pat-run/0.1', 'replayNamespace': namespace, 'runKey': 'scoped:run',
                    'taskKind': programs[0]['taskKind'], 'inputProfile': programs[0]['inputProfile'],
                    'parameters': {'initialLevel': 12, 'finalLevel': 73}, 'evidenceMode': 'simulation',
                    'originUnixMs': 1000, 'latestCompletionUnixMs': 4000}
                def environment(context, program):
                    calls.append((context.principal, pat_digest(program)))
                    bound = provider.for_roles(context, program, assignments[pat_digest(program)])
                    return store._compile(context, request, program, pat_digest(program), bound)['evaluationEnvironment']
                evaluator = Evaluator('alias-evaluator', digest('eval'), digest('policy'), CHECKS, lambda p, e: result())
                catalog = PatCatalog(runtime.journal, compiler_digest=compiler_digest,
                    environment=environment, evaluators=(evaluator,))
                store = PatExecutionStore(runtime.journal, catalog, runtime.procedures, resolver=provider)
                for index, program in enumerate(programs):
                    key = catalog.publish(owner, program)['artifactDigest']
                    catalog.evaluate(owner, key, evaluator.evaluator_id, 'alias-eval:' + str(index))
                    catalog.transition(owner, key, expected_revision=catalog._revision(owner.deployment), target='active')
                west = configs[1]['instances']['fan']
                busy = runtime.request(owner, 'prepare', {'instanceId': west, 'actionId': 'set_level',
                    'arguments': {'level': 1, 'unit': 'percent'}, 'operationKey': 'busy:west', 'replayNamespace': namespace,
                    'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': 1000,
                        'latestStartUnixMs': 10000, 'maxRunMs': 500, 'latestCompletionUnixMs': 15000}})['request']
                runtime.request(owner, 'invoke', {'request': busy})
                with self.assertRaisesRegex(PatError, 'PAT_AMBIGUOUS'):
                    store.run(owner, request)
                for target, verb in (('*', 'namespace'), (west, 'read'), (west, 'invoke:set_level')):
                    runtime.registry.grant(owner, user.principal, target, verb)
                user_namespace = runtime.request(user, 'namespace', {'expiresUnixMs': 100000})['token']
                calls.clear()
                run = store.run(user, request | {'replayNamespace': user_namespace})
                self.assertEqual(run['artifactDigest'], pat_digest(programs[1]))
                self.assertNotIn((user.principal, pat_digest(programs[0])), calls)
                self.assertEqual(run['resolverIdentity'], provider.registration_identity)
                self.assertEqual(run['procedure']['executionState'], 'accepted')
                self.assertTrue(all(step['operationId'] is None for step in run['procedure']['steps']))
            finally:
                runtime.close()

    def test_three_families_across_two_aliases_use_registry_provider_without_inference(self):
        clock = [1000]
        owner = Context('installed-pat-owner', 'simulation:multi')
        configs = []
        for alias in ('east', 'west'):
            config = legacy_installation()
            config['adapterId'] = 'pat-installed:' + alias
            config['instances'] = {role: 'sim:' + alias + ':' + role for role in config['instances']}
            config['resources'] = {role: 'resource:' + alias + ':' + role for role in config['resources']}
            configs.append(config)
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(directory, create=True, owner=owner, installations=configs,
                wall_clock_ms=lambda: clock[0], monotonic_ms=lambda: clock[0])
            try:
                registrations, records = [], []
                for index, config in enumerate(configs):
                    for role in ('fan', 'focus', 'inspection'):
                        instance = config['instances'][role]
                        program, params, fields = compiler_fixtures.PatCompilerTests._family(role, instance, index)
                        program['taskKind'], program['inputProfile'] = 'task:' + role, 'input:' + role
                        desc = runtime.request(owner, 'describe', {'instanceId': instance})
                        action = program['roles']['fan']['actions'][0]
                        registrations.append({'instanceId': instance, 'typeDigest': desc['descriptionDigest'],
                            'driverProfile': config['driver'], 'driverDigest': digest('original-local-driver'),
                            'installationDigest': 'sha256:' + installation_digest(config), 'argumentMetadata': {action: fields}})
                        records.append((config, role, instance, program, params))
                provider = RegistryPatBindings(runtime, registrations)
                environments = {}
                evaluator = Evaluator('installed-fixture', digest('evaluator'), digest('policy'), CHECKS,
                    lambda program, environment: result())
                catalog = PatCatalog(runtime.journal, compiler_digest=compiler_digest,
                    environment=lambda context, program: environments[pat_digest(program)], evaluators=(evaluator,))
                store = PatExecutionStore(runtime.journal, catalog, runtime.procedures, resolver=provider)
                namespace = runtime.request(owner, 'namespace', {'expiresUnixMs': 100000})['token']
                reused, active_role = {}, {}
                for index, (config, role, instance, program, params) in enumerate(records):
                    request = {'protocol': 'hms.pat-run/0.1', 'replayNamespace': namespace, 'runKey': 'installed:' + str(index),
                        'taskKind': program['taskKind'], 'inputProfile': program['inputProfile'], 'parameters': params,
                        'evidenceMode': 'simulation', 'originUnixMs': clock[0], 'latestCompletionUnixMs': clock[0] + 3000}
                    with runtime.journal._transaction():
                        bindings = provider.for_roles(owner, program, {'fan': instance})
                    compiled = store._compile(owner, request, program, pat_digest(program), bindings)
                    if role in active_role and active_role[role] != pat_digest(program):
                        # Two differently calibrated focus artifacts with the
                        # same structured task would otherwise be ambiguous.
                        catalog.transition(owner, active_role[role],
                            expected_revision=catalog._revision(owner.deployment), target='suspended')
                    environments[pat_digest(program)] = compiled['evaluationEnvironment']
                    catalog.publish(owner, program)
                    catalog.evaluate(owner, pat_digest(program), evaluator.evaluator_id, 'installed-eval:' + str(index))
                    catalog.transition(owner, pat_digest(program), expected_revision=catalog._revision(owner.deployment), target='active')
                    active_role[role] = pat_digest(program)
                    run = store.run(owner, request)
                    for _ in range(12):
                        runtime.tick()
                        current = store.status(owner, run['instanceId'])
                        if current['procedure']['executionState'] == 'completed':
                            break
                        clock[0] += 100
                    self.assertEqual(current['procedure']['executionState'], 'completed', current)
                    self.assertEqual(runtime.adapters[config['adapterId']].plant.observe(instance)['effectCount'], 2)
                    self.assertEqual(store.run(owner, request)['instanceId'], run['instanceId'])
                    self.assertEqual(runtime.adapters[config['adapterId']].plant.observe(instance)['effectCount'], 2)
                    if role in ('fan', 'inspection'):
                        self.assertEqual(reused.setdefault(role, run['artifactDigest']), run['artifactDigest'])
                    # Focus pins each calibrated frame explicitly; it does not
                    # claim one artifact silently converts frames across aliases.
            finally:
                runtime.close()


class KillConnection:
    def __init__(self, connection, phase):
        self.connection, self.phase = connection, phase
        self.linked = False

    def __getattr__(self, key):
        return getattr(self.connection, key)

    def execute(self, sql, *args, **kwargs):
        value = self.connection.execute(sql, *args, **kwargs)
        if sql.startswith('INSERT INTO px_triggers'):
            self.linked = True
            if self.phase == 'before_commit':
                os._exit(61)
        if self.phase == 'after_commit' and self.linked and sql == 'COMMIT':
            os._exit(62)
        return value


def crash_worker(directory, phase):
    fixture = Fixture(directory)
    fixture.activate()
    request = fixture.request()
    print(json.dumps(request), flush=True)
    journal = fixture.runtime.journal
    journal._db = KillConnection(journal._db, phase)
    # Store/registry refer to the same SQLite connection directly. Its writes
    # are observed here only at the explicit trigger link insertion seam.
    fixture.store._db = journal._db
    fixture.store.run(OWNER, request)
    os._exit(63)


class PatExecutionCrashTests(unittest.TestCase):
    def test_process_loss_before_and_after_linked_commit_preserves_atomicity(self):
        for phase, exit_code, count in [('before_commit', 61, 0), ('after_commit', 62, 1)]:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                child = subprocess.run([sys.executable, __file__, '--crash', directory, phase],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(child.returncode, exit_code, child.stderr)
                request = json.loads(child.stdout)
                fixture = Fixture(directory, create=False)
                try:
                    self.assertEqual(fixture.counts()[:3], (count, count, count))
                    self.assertEqual(fixture.counts()[3:5], (count * 2, count * 3))
                    self.assertEqual(fixture.runtime.plant.observe('sim:home-fan')['effectCount'], 0)
                    if count:
                        with patch.object(fixture.store, 'resolver', side_effect=AssertionError('replay resolver')):
                            run = fixture.store.run(OWNER, request)
                        self.assertEqual(run['procedure']['executionState'], 'interrupted')
                        self.assertEqual(fixture.counts()[:3], (1, 1, 1))
                finally:
                    fixture.close()


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--crash':
        crash_worker(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
