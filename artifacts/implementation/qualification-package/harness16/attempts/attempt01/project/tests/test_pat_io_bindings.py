"""Original SQLite tests for static finite-I/O PAT joins, not qualification trials."""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, JournalError
from hms.pat_compiler import compile_pat, evaluation_environment
from hms.pat_io_bindings import IoRegistryPatBindings
from hms.synthetic_io_installation import DRIVER, definitions, installation_digest
from hms.synthetic_io_runtime import IoRuntime
from test_io_synthetic_provider import installation
from test_pat_compiler import artifact
from test_resource_topology import generations
from io_evidence_capture import EvidenceWorkspace, close_retaining, snapshot_databases

EVIDENCE_DIRECTORY = None
OWNER = Context('io-pat-owner', 'simulation:io-hub')
SCOPED = Context('io-pat-reader', OWNER.deployment)
UNIT_PROFILE = 'hms.pat.argument.fixed-schema-unit/0.1'


def metadata(unit):
    return {'profile': UNIT_PROFILE, 'unit': unit, 'frame': None,
            'unitArgument': None, 'frameArgument': None}


def registrations(document):
    """Explicit test-author registration, independent of resolver private policy."""
    bundles = definitions(document)
    result = []
    for instance, expected in sorted(bundles.items()):
        fields = {}
        for handler in document['handlers']:
            if handler['instanceId'] != instance:
                continue
            if handler['primitive'] == 'gpio_pulse':
                fields[handler['actionId']] = {'level': metadata('1'), 'durationMs': metadata('ms')}
            else:
                fields[handler['actionId']] = {'frequencyHz': metadata('Hz'), 'dutyPermille': metadata('permille'),
                    'resolutionBits': metadata('bit'), 'durationMs': metadata('ms')}
        result.append({'instanceId': instance, 'typeDigest': expected['binding']['typeDigest'],
            'driverProfile': DRIVER, 'driverDigest': document['driverDigest'],
            'installationDigest': installation_digest(document), 'argumentMetadata': fields})
    return result


def program(*, action='gpio_pulse', pwm=False, roles=1, duration_maximum=100):
    value = artifact()
    value.update(name='finite-io-static-fixture', taskKind='sim.io.static', inputProfile='hms.sim.io.static/0.1')
    value['parameters'] = {'duration': {'valueSchema': {'type': 'integer', 'minimum': 1,
        'maximum': duration_maximum}, 'unit': 'ms', 'frame': None}}
    arguments = {'durationMs': {'parameter': 'duration'}}
    if pwm:
        arguments.update(frequencyHz={'literal': 1000}, dutyPermille={'literal': 375}, resolutionBits={'literal': 8})
    else:
        value['parameters']['level'] = {'valueSchema': {'type': 'integer', 'minimum': 0, 'maximum': 1},
                                        'unit': '1', 'frame': None}
        arguments['level'] = {'parameter': 'level'}
    names = ['io' + str(index) for index in range(roles)]
    value['roles'] = {name: {'capabilityFamily': 'sim:finite-gpio-pwm', 'actions': [action],
                            'driverProfiles': [DRIVER]} for name in names}
    value['steps'] = [{'stepId': 'step:' + name, 'role': name, 'actionId': action,
        'arguments': copy.deepcopy(arguments), 'timing': {'notBeforeOffsetMs': 0,
        'latestStartOffsetMs': 500 if index == 0 else 9000, 'maxRunMs': 500,
        'latestCompletionOffsetMs': 10000}} for index, name in enumerate(names)]
    value['timingBudget'] = {'latestStartOffsetMs': 500, 'latestCompletionOffsetMs': 10000,
                             'maxRunSumMs': 500 * roles}
    value['effectBudget']['maxInvocations'] = roles
    value['outcomeContract']['requiredCompletedSteps'] = [step['stepId'] for step in value['steps']]
    return value


def many_instances(count):
    value = installation()
    consumers = [{'instanceId': 'sim:alias:' + str(index), 'actionId': 'gpio_pulse',
                  'rootAliases': ['alias:gpio5'], 'requires': []} for index in range(count)]
    value['topology']['consumers'] = consumers
    value['initialGenerations'] = generations(value['topology'])
    value['routes']['adapters'] = {'io:routeA': [row['instanceId'] for row in consumers]}
    value['handlers'] = [{'instanceId': row['instanceId'], 'actionId': row['actionId'],
                          'primitive': 'gpio_pulse'} for row in consumers]
    return value


class IoPatBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = EvidenceWorkspace()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.runtime = None
        self._captured = False
        self._capture_number = 0
        self._states = []
        # LIFO: capture while open, then close, then erase only if neither
        # capture/setup nor close failed. Ownership exists before risky setup.
        self.addCleanup(self.close_current)
        self.addCleanup(self.capture)
        try:
            self.replace(installation())
        except BaseException as error:
            self.temp.failed(error, phase='setup')
            raise

    def close_current(self):
        close_retaining(self.temp, self.runtime)
        self.runtime = None

    def replace(self, document):
        self._captured = False
        try:
            self.close_current()
            self.directory = Path(self.temp.name) / ('state-' + str(len(self._states)))
            state = {'directory': self.directory, 'installation': copy.deepcopy(document),
                     'registrationIdentity': None, 'setupComplete': False}
            self._states.append(state)
            self.runtime = IoRuntime(self.directory, create=True, owner=OWNER, installation=document,
                                     wall_clock_ms=lambda: self.now, monotonic_ms=lambda: self.now)
            self.document = copy.deepcopy(self.runtime.catalog.document)
            self.records = registrations(self.document)
            self.provider = IoRegistryPatBindings(self.runtime, self.records)
            state.update(installation=self.document, registrationIdentity=self.provider.registration_identity,
                         setupComplete=True)
        except BaseException as error:
            self.temp.failed(error, phase='replacement-setup')
            raise

    def capture(self):
        if EVIDENCE_DIRECTORY is None or self._captured:
            return
        try:
            target = EVIDENCE_DIRECTORY / self._testMethodName / ('%02d-final' % self._capture_number)
            self._capture_number += 1
            # Every replacement state is retained, including partial setup and
            # the16-instance positive preceding the17-instance refusal fixture.
            for state in self._states:
                if not state['directory'].exists():
                    continue
                snapshot_databases(state['directory'], target / state['directory'].name,
                    {'nowMs': self.now, 'installation': state['installation'],
                     'registrationIdentity': state['registrationIdentity'],
                     'setupComplete': state['setupComplete'],
                     'scope': 'Original SQLite resolver fixture; no pulse/qualification/physical execution.'})
        except BaseException as error:
            self.temp.failed(error, phase='capture')
            raise
        self._captured = True

    def resolve(self, context=OWNER, value=None, provider=None, request=None):
        chosen = provider or self.provider
        value = value or program()
        if self.runtime.journal._db.in_transaction:
            return chosen(context, value, request or {})
        with self.runtime.journal._transaction():
            return chosen(context, value, request or {})

    def code(self, expected, callback):
        with self.assertRaises(JournalError) as caught:
            callback()
        self.assertEqual(caught.exception.code, expected)

    @contextmanager
    def change(self, sql, parameters=()):
        with self.runtime.journal._transaction():
            db = self.runtime.journal._db
            db.execute('SAVEPOINT fixture_damage')
            db.execute(sql, parameters)
            try:
                yield
            finally:
                db.execute('ROLLBACK TO fixture_damage')
                db.execute('RELEASE fixture_damage')

    def grant(self, instance, action='gpio_pulse'):
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'read')
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'invoke:' + action)

    def business(self):
        db = self.runtime.journal._db
        return {'operations': [tuple(row) for row in db.execute('SELECT * FROM operations ORDER BY id')],
                'claims': [tuple(row) for row in db.execute('SELECT * FROM claims ORDER BY resource')],
                'effects': [tuple(row) for row in self.runtime.io_board.db.execute('SELECT * FROM io_effects ORDER BY instance')]}

    def test_exact_gpio_pwm_units_full_installation_and_alias_inventory(self):
        gpio = self.resolve()
        self.assertIs(gpio['complete'], True)
        self.assertEqual([row['io0']['binding']['instanceId'] for row in gpio['assignments']],
                         ['sim:gpio5', 'sim:gpio5:other-route', 'sim:gpio6'])
        pwm = self.resolve(value=program(action='pwm_burst', pwm=True))['assignments'][0]['io0']
        self.assertEqual({key: info['unit'] for key, info in pwm['argumentMetadata']['pwm_burst'].items()},
                         {'durationMs': 'ms', 'frequencyHz': 'Hz', 'dutyPermille': 'permille', 'resolutionBits': 'bit'})
        for descriptor in [row['io0'] for row in gpio['assignments']] + [pwm]:
            self.assertEqual(descriptor['installationDigest'], installation_digest(self.document))
            self.assertEqual(descriptor['driverDigest'], self.document['driverDigest'])
            self.assertNotEqual(descriptor['installationDigest'], 'sha256:' + self.runtime.journal._db.execute(
                'SELECT digest FROM rt_adapters WHERE adapter=?', (descriptor['binding']['adapterId'],)).fetchone()[0])
        self.assertEqual(self.business()['operations'], [])

    def test_explicit_metadata_and_results_are_detached_without_identity_change(self):
        identity = self.provider.registration_identity
        original = self.resolve()
        self.records[0]['argumentMetadata']['gpio_pulse']['durationMs']['unit'] = 's'
        original['assignments'][0]['io0']['type']['execution']['capabilities'] = []
        original['assignments'][0]['io0']['argumentMetadata']['gpio_pulse']['durationMs']['unit'] = 'changed'
        self.assertEqual(self.provider.registration_identity, identity)
        self.assertEqual(self.resolve()['assignments'][0]['io0']['argumentMetadata']['gpio_pulse']['durationMs']['unit'], 'ms')

    def test_closed_registration_inputs_and_bounds_refuse_before_caller_hooks(self):
        class HostObject:
            def __deepcopy__(self, memo):
                raise AssertionError('caller hook must not run')
        bad = [[], self.records * 33, [self.records[0], self.records[0]],
               [self.records[0] | {'extra': True}], [self.records[0] | {'instanceId': 'sim:unknown'}],
               [self.records[0] | {'argumentMetadata': HostObject()}]]
        for values in bad:
            with self.subTest(values=type(values).__name__), self.assertRaises(JournalError):
                IoRegistryPatBindings(self.runtime, values)
        for field in ('instanceId', 'driverProfile', 'typeDigest', 'driverDigest', 'installationDigest'):
            for wrong in (True, 1, 1.0, None):
                values = copy.deepcopy(self.records); values[0][field] = wrong
                with self.subTest(field=field, wrong=wrong), self.assertRaises(JournalError):
                    IoRegistryPatBindings(self.runtime, values)

    def test_trusted_source_or_full_installation_registration_changes_refuse(self):
        for field in ('driverDigest', 'installationDigest', 'typeDigest'):
            values = copy.deepcopy(self.records); values[0][field] = 'sha256:' + '0' * 64
            provider = IoRegistryPatBindings(self.runtime, values)
            self.code('PAT_BINDING_REGISTRATION_CHANGED', lambda: self.resolve(provider=provider))
        values = copy.deepcopy(self.records); values[0]['driverProfile'] = 'sqlite-simulation'
        self.code('PAT_BINDING_REGISTRATION_CHANGED', lambda: self.resolve(provider=IoRegistryPatBindings(self.runtime, values)))

    def test_caller_transaction_and_deployment_are_required(self):
        self.code('PAT_BINDING_TRANSACTION_REQUIRED', lambda: self.provider(OWNER, program(), {}))
        self.code('ACCESS_DENIED', lambda: self.resolve(Context(OWNER.principal, 'simulation:wrong')))

    def test_another_threads_transaction_does_not_qualify_after_mutex_wait(self):
        entered, done = threading.Event(), threading.Event()
        errors = []
        def caller():
            entered.set()
            try:
                self.provider(OWNER, program(), {})
            except BaseException as error:
                errors.append(error)
            finally:
                done.set()
        thread = threading.Thread(target=caller)
        try:
            with self.runtime.journal._transaction():
                thread.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(done.wait(0.02))
            self.assertTrue(done.wait(2))
        finally:
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([error.code for error in errors], ['PAT_BINDING_TRANSACTION_REQUIRED'])

    def test_global_inventory_is_checked_even_when_role_driver_would_not_match(self):
        value = program(); value['roles']['io0']['driverProfiles'] = ['unrelated-driver']
        with self.change('DELETE FROM rt_adapters WHERE adapter=?', ('io:routeB',)):
            self.code('PAT_BINDING_INVENTORY_INVALID', lambda: self.resolve(value=value))
        with self.change("UPDATE rt_catalog SET profile='hms.adapter-catalog/1'"):
            self.code('PAT_BINDING_STORAGE_PROFILE', lambda: self.resolve(value=value))

    def test_only_valid_inactive_retired_or_unauthorized_instances_are_excluded(self):
        self.assertEqual(self.resolve(SCOPED)['assignments'], [])
        self.grant('sim:gpio5')
        self.assertEqual(len(self.resolve(SCOPED)['assignments']), 1)
        for sql in ("UPDATE reg_bindings SET active=0 WHERE instance='sim:gpio5'",
                    "UPDATE reg_instances SET retired=1 WHERE id='sim:gpio5'"):
            with self.change(sql):
                self.assertEqual(self.resolve(SCOPED)['assignments'], [])
        with self.change("UPDATE reg_bindings SET active=2 WHERE instance='sim:gpio5'"):
            self.code('PAT_BINDING_STORAGE', lambda: self.resolve(SCOPED))
        self.runtime.registry.grant(OWNER, SCOPED.principal, 'sim:gpio5', 'read', enabled=False)
        self.assertEqual(self.resolve(SCOPED)['assignments'], [])

    def test_missing_authorized_instance_is_indeterminate_not_false_uniqueness(self):
        self.grant('sim:gpio5'); self.grant('sim:gpio6')
        with self.change("UPDATE reg_instances SET identity_ref='damaged' WHERE id='sim:gpio6'"):
            self.code('PAT_BINDING_INSTANCE_CHANGED', lambda: self.resolve(SCOPED))
        with self.change("DELETE FROM reg_bindings WHERE instance='sim:gpio6'"):
            self.code('PAT_BINDING_CURRENT_MISSING', lambda: self.resolve(SCOPED))
        with self.change("DELETE FROM reg_capabilities WHERE instance='sim:gpio6'"):
            db = self.runtime.journal._db
            for table in ('reg_bindings', 'reg_presence', 'reg_observations'):
                db.execute('DELETE FROM ' + table + ' WHERE instance=?', ('sim:gpio6',))
            db.execute('DELETE FROM reg_instances WHERE id=?', ('sim:gpio6',))
            self.code('PAT_BINDING_INSTANCE_MISSING', lambda: self.resolve(SCOPED))

    def test_missing_metadata_is_indeterminate_only_for_authorized_candidate(self):
        provider = IoRegistryPatBindings(self.runtime, [row for row in self.records if row['instanceId'] != 'sim:gpio6'])
        self.code('PAT_BINDING_METADATA_MISSING', lambda: self.resolve(provider=provider))
        self.grant('sim:gpio5')
        self.assertEqual(len(self.resolve(SCOPED, provider=provider)['assignments']), 1)
        self.grant('sim:gpio6')
        self.code('PAT_BINDING_METADATA_MISSING', lambda: self.resolve(SCOPED, provider=provider))

    def test_expired_presence_and_held_claims_do_not_reduce_alias_choices(self):
        namespace = self.runtime.journal.issue_namespace(OWNER, 20000)['token']
        request = self.runtime.request(OWNER, 'prepare', {'instanceId': 'sim:gpio5', 'actionId': 'gpio_pulse',
            'arguments': {'level': 1, 'durationMs': 20}, 'requiredEffect': 'capability_completion',
            'replayNamespace': namespace, 'operationKey': 'held:resolver', 'timing': {'notBeforeUnixMs': 1000,
                'latestStartUnixMs': 8000, 'maxRunMs': 500, 'latestCompletionUnixMs': 9000}})['request']
        self.runtime.journal.submit(OWNER, canonical(request))
        before = self.business(); self.assertTrue(before['claims'])
        self.now = 5000
        with patch.object(self.runtime.io_board, 'observe', side_effect=AssertionError('board observation')), \
             patch.object(self.runtime.adapters['io:routeA'], 'refresh', side_effect=AssertionError('refresh')):
            self.assertEqual(len(self.resolve()['assignments']), 3)
        self.assertEqual(before, self.business())

    def test_missing_or_contradictory_session_refuses_with_another_alias_present(self):
        mutations = ["DELETE FROM reg_presence WHERE instance='sim:gpio6'",
                     "UPDATE reg_presence SET adapter='io:wrong' WHERE instance='sim:gpio6'",
                     "UPDATE reg_endpoint_sessions SET session='session:wrong' WHERE instance='sim:gpio6'",
                     "DELETE FROM reg_session_history WHERE instance='sim:gpio6'"]
        for index, sql in enumerate(mutations):
            with self.subTest(index=index), self.change(sql):
                self.code('PAT_BINDING_SESSION_UNKNOWN' if index == 0 else 'PAT_BINDING_SESSION_CHANGED', self.resolve)

    def test_unready_authorized_route_is_not_an_inventory_filter(self):
        with self.change("UPDATE rt_adapters SET ready=0 WHERE adapter='io:routeB'"):
            self.code('PAT_BINDING_INSTALLATION_UNAVAILABLE', self.resolve)
        self.grant('sim:gpio5')
        with self.change("UPDATE rt_adapters SET ready=0 WHERE adapter='io:routeB'"):
            self.assertEqual(len(self.resolve(SCOPED)['assignments']), 1)

    def test_relevant_generation_change_refuses_immutable_provider_support(self):
        self.runtime.catalog.resources.publish_generation(OWNER, 'driverA', 'generation:1', 'generation:2', expected_revision=1)
        self.code('PAT_BINDING_INSTALLATION_UNSUPPORTED', self.resolve)
        self.assertEqual(self.business()['operations'], [])

    def test_unrelated_generation_change_preserves_exact_scoped_binding(self):
        self.grant('sim:gpio5')
        before = self.resolve(SCOPED)
        self.runtime.catalog.resources.publish_generation(OWNER, 'driverB', 'generation:1', 'generation:2', expected_revision=1)
        after = self.resolve(SCOPED)
        self.assertEqual(after, before)
        self.assertEqual(self.runtime.catalog.resources._load()['revision'], 2)

    def test_wrong_storage_types_and_oversized_metadata_refuse_before_body_fetch(self):
        db = self.runtime.journal._db
        mutations = [
            ("UPDATE rt_io_installation SET document=?", (b'x' * 65537,)),
            ("UPDATE rt_adapters SET digest=? WHERE adapter='io:routeA'", ('x' * 129,)),
            ("UPDATE reg_presence SET session=? WHERE instance='sim:gpio5'", ('\u00e9' * 65,)),
            ("UPDATE reg_bindings SET active=? WHERE instance='sim:gpio5'", (b'1',)),
            ("UPDATE reg_instances SET retired=? WHERE id='sim:gpio5'", (1.5,)),
            ("UPDATE reg_meta SET value=? WHERE key='version'", (b'hms.registry/resource-roots/0.1',))]
        for sql, args in mutations:
            with self.subTest(sql=sql), self.change(sql, args):
                original = db.row_factory; bodies = []; trace = []
                def checked(cursor, values):
                    for value in values:
                        if type(value) is type(args[0]) and value == args[0]:
                            bodies.append(True)
                    return original(cursor, values)
                db.row_factory = checked; db.set_trace_callback(trace.append)
                try:
                    self.code('PAT_BINDING_STORAGE', self.resolve)
                finally:
                    db.row_factory = original; db.set_trace_callback(None)
                self.assertFalse(bodies, trace)
                self.assertTrue(any('typeof(' in statement for statement in trace))

    def test_oversized_type_document_cannot_be_read_by_legacy_type_helper(self):
        digest = self.runtime.catalog.definitions['sim:gpio5']['binding']['typeDigest']
        with self.change('UPDATE reg_types SET document=? WHERE digest=?', (b'x' * 65537, digest)), \
             patch.object(self.runtime.registry, '_type', side_effect=AssertionError('indirect unbounded type read')):
            self.code('PAT_BINDING_STORAGE', self.resolve)

    def test_history_foreign_type_pointer_refuses_before_indirect_helper(self):
        binding = copy.deepcopy(self.runtime.catalog.definitions['sim:gpio5']['binding'])
        binding['typeDigest'] = 'sha256:' + 'f' * 64
        wire = canonical(binding)
        with self.change('UPDATE reg_binding_history SET document=?,digest=? WHERE instance=?',
                         (wire, hashlib.sha256(wire).hexdigest(), 'sim:gpio5')), \
             patch.object(self.runtime.registry, '_type', side_effect=AssertionError('foreign type follow')):
            self.code('PAT_BINDING_HISTORY_CHANGED', self.resolve)

    def test_proof_future_revision_missing_history_and_tokens_refuse(self):
        cases = [('UPDATE rc_proofs SET revision=2 WHERE instance=?', ('sim:gpio5',), 'PAT_BINDING_PROOF_CHANGED'),
                 ('DELETE FROM reg_binding_history WHERE instance=?', ('sim:gpio5',), 'PAT_BINDING_HISTORY_MISSING'),
                 ('DELETE FROM rc_tokens WHERE node=?', ('driverA',), 'RESOURCE_GENERATION_HISTORY_INVALID')]
        for sql, args, code in cases:
            with self.subTest(sql=sql), self.change(sql, args):
                self.code(code, self.resolve)

    def test_current_binding_identity_and_canonical_bytes_are_required(self):
        with self.change("UPDATE reg_bindings SET generation='generation:wrong' WHERE instance='sim:gpio5'"):
            self.code('PAT_BINDING_CURRENT_CHANGED', self.resolve)
        binding = self.runtime.catalog.definitions['sim:gpio5']['binding']
        noncanonical = json.dumps(binding, indent=2).encode()
        with self.change('UPDATE reg_bindings SET document=? WHERE instance=?', (noncanonical, 'sim:gpio5')):
            self.code('PAT_BINDING_CURRENT_CHANGED', self.resolve)

    def test_global_extra_route_and_missing_managed_requirement_refuse(self):
        with self.change("INSERT INTO rt_adapters SELECT 'io:extra',document,digest,ready FROM rt_adapters LIMIT 1"):
            self.code('PAT_BINDING_INVENTORY_INVALID', self.resolve)
        with self.change("DELETE FROM reg_resource_instances WHERE instance='sim:gpio6'"):
            self.code('RESOURCE_REQUIREMENT_MISSING', self.resolve)

    def test_metadata_units_profiles_frames_and_scalar_aliases_are_exact(self):
        for wrong in ('s', '1', True, 1, 1.0, None):
            values = copy.deepcopy(self.records)
            values[0]['argumentMetadata']['gpio_pulse']['durationMs']['unit'] = wrong
            provider = IoRegistryPatBindings(self.runtime, values)
            with self.subTest(wrong=wrong):
                self.code('PAT_BINDING_METADATA_CHANGED', lambda: self.resolve(provider=provider))
        for changes in ({'profile': 'unknown'}, {'frame': 'fixture:frame'}, {'unitArgument': 'unit'}, {'extra': None}):
            values = copy.deepcopy(self.records)
            values[0]['argumentMetadata']['gpio_pulse']['durationMs'].update(changes)
            self.code('PAT_BINDING_METADATA_CHANGED', lambda: self.resolve(provider=IoRegistryPatBindings(self.runtime, values)))

    def test_opaque_action_names_use_installed_primitive_not_spelling(self):
        value = installation()
        for row in value['handlers']:
            row['actionId'] = 'opaque.q7' if row['primitive'] == 'gpio_pulse' else 'opaque.q9'
        for row in value['topology']['consumers']:
            row['actionId'] = 'opaque.q9' if row['instanceId'] == 'sim:pwm5' else 'opaque.q7'
        value['initialGenerations'] = generations(value['topology'])
        self.replace(value)
        self.assertEqual(len(self.resolve(value=program(action='opaque.q7'))['assignments']), 3)
        result = self.resolve(value=program(action='opaque.q9', pwm=True))['assignments'][0]['io0']
        self.assertEqual(result['argumentMetadata']['opaque.q9']['frequencyHz']['unit'], 'Hz')

    def test_exact_sixteen_choices_and_seventeen_refusal_without_truncation(self):
        self.replace(many_instances(16))
        self.assertEqual(len(self.resolve()['assignments']), 16)
        self.replace(many_instances(17))
        self.code('PAT_BINDING_ENUMERATION_LIMIT', self.resolve)
        self.assertEqual(self.business()['operations'], [])

    def test_call_local_cache_has_one_base_descriptor_per_instance(self):
        before = self.business()
        with patch.object(self.provider, '_descriptor', wraps=self.provider._descriptor) as build:
            result = self.resolve(value=program(roles=2))
        self.assertEqual(len(result['assignments']), 9)
        self.assertEqual(build.call_count, 3)
        self.assertEqual(len({call.args[0] for call in build.call_args_list}), 3)
        result['assignments'][0]['io0']['binding']['generation'] = 'changed'
        self.assertNotEqual(result['assignments'][0]['io1']['binding']['generation'], 'changed')
        self.assertEqual(before, self.business())

    def test_assignment_carrier_limit_refuses_instead_of_partial_result(self):
        value = many_instances(1)
        for index in range(1, 5):
            value['topology']['consumers'].append({'instanceId': 'sim:alias:0', 'actionId': 'extra:' + str(index),
                'rootAliases': ['alias:gpio5'], 'requires': []})
            value['handlers'].append({'instanceId': 'sim:alias:0', 'actionId': 'extra:' + str(index), 'primitive': 'gpio_pulse'})
        value['initialGenerations'] = generations(value['topology'])
        self.replace(value)
        self.assertEqual(len(self.resolve()['assignments']), 1)
        self.code('PAT_BINDING_OUTPUT_LIMIT', lambda: self.resolve(value=program(roles=16)))
        self.assertEqual(self.business()['operations'], [])

    def test_selection_is_select_only_with_no_files_clocks_or_provider_calls(self):
        value = program()
        db = self.runtime.journal._db; before = self.business()
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        denied = []
        def authorize(action, first, second, database, trigger):
            if action not in allowed:
                denied.append((action, first, second))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        with self.runtime.journal._transaction():
            changes = db.total_changes
            db.set_authorizer(authorize)
            try:
                with patch('pathlib.Path.read_bytes', side_effect=AssertionError('filesystem read')), \
                     patch('pathlib.Path.read_text', side_effect=AssertionError('filesystem read')), \
                     patch('sqlite3.connect', side_effect=AssertionError('new connection')), \
                     patch.object(self.runtime.journal, '_now', side_effect=AssertionError('clock')), \
                     patch.object(self.runtime.registry, '_monotonic', side_effect=AssertionError('clock')), \
                     patch.object(self.runtime.io_board, 'supports_binding', side_effect=AssertionError('board')), \
                     patch.object(self.runtime.io_board, 'validate_admission', side_effect=AssertionError('provider')):
                    self.assertEqual(len(self.resolve(value=value)['assignments']), 3)
                self.assertTrue(db.in_transaction)
                self.assertEqual(db.total_changes, changes)
            finally:
                db.set_authorizer(None)
        self.assertEqual(denied, [])
        self.assertEqual(before, self.business())

    def test_explicit_roles_are_trusted_assignment_not_request_inventory_control(self):
        with self.runtime.journal._transaction():
            exact = self.provider.for_roles(OWNER, program(), {'io0': 'sim:gpio6'})
        self.assertEqual(exact['io0']['binding']['instanceId'], 'sim:gpio6')
        self.assertEqual(len(self.resolve(request={'roleInstances': {'io0': 'sim:gpio6'}})['assignments']), 3)
        with self.runtime.journal._transaction():
            self.code('PAT_BINDING_NOT_REGISTERED', lambda: self.provider.for_roles(OWNER, program(), {'io0': 'sim:missing'}))
            oversized = {'role:' + str(index): 'sim:gpio5' for index in range(17)}
            with patch('hms.pat_io_bindings.set', side_effect=AssertionError('keys materialized before count'), create=True):
                self.code('PAT_INVALID_BINDING_REGISTRATION', lambda: self.provider.for_roles(OWNER, program(), oversized))

    def test_environment_retains_installed_duration_domain_without_execution_claim(self):
        value = program(duration_maximum=5000)
        with self.runtime.journal._transaction():
            bindings = self.provider.for_roles(OWNER, value, {'io0': 'sim:gpio5'})
        env = evaluation_environment(value, bindings, deployment=OWNER.deployment)
        compiled = compile_pat(value, {'duration': 5000, 'level': 1}, bindings,
            origin_ms=1000, caller_deadline_ms=12000, replay_namespace='fixture:namespace',
            procedure_key='fixture:parent', operation_keys={'step:io0': 'fixture:child'},
            context={'taskKind': value['taskKind'], 'inputProfile': value['inputProfile'],
                     'evidenceMode': 'simulation', 'deployment': OWNER.deployment})
        self.assertEqual(env['evaluationEnvironment'], compiled['evaluationEnvironment'])
        request = compiled['request']['procedure']['steps'][0]['request']
        self.assertEqual(request['operationKey'], 'fixture:child')
        self.assertEqual(request['intent']['arguments'], {'durationMs': 5000, 'level': 1})
        self.assertEqual(request['intent']['timing']['notBeforeUnixMs'], 1000)
        self.assertEqual(bindings['io0']['binding']['argumentSchemas']['gpio_pulse']['properties']['durationMs']['maximum'], 5000)
        self.assertEqual(self.business()['operations'], [])


if __name__ == '__main__':
    unittest.main()
