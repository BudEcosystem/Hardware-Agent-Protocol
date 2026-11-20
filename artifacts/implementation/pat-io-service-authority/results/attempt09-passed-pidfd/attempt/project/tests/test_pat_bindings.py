"""Actual registry joins for deterministic PAT bindings; no physical device I/O."""
import copy
import hashlib
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import ContractError, canonical
from hms.installations import installation_digest
from hms.journal import Context, JournalError
from hms.pat_bindings import RegistryPatBindings
from hms.pat_compiler import compile_pat
from hms.pat_contracts import PatError
from hms.runtime import Runtime
from test_multi_adapter import installation
from test_pat_compiler import artifact, metadata


OWNER = Context('pat-binding-owner', 'simulation:multi')
SCOPED = Context('pat-binding-user', OWNER.deployment)


def registration(runtime, config, *, role='fan', fields=None):
    instance = config['instances'][role]
    bundle, active = runtime.registry._binding(instance)
    assert active
    action = {'fan': 'set_level', 'focus': 'move_absolute', 'inspection': 'inspect'}[role]
    return {'instanceId': instance, 'typeDigest': bundle['typeDigest'],
            'driverProfile': config['driver'],
            'driverDigest': 'sha256:' + hashlib.sha256(b'explicit-test-driver-registration').hexdigest(),
            'installationDigest': 'sha256:' + installation_digest(config),
            'argumentMetadata': {action: fields or {
                'level': metadata('percent', unit_argument='unit'), 'unit': metadata()}}}


class PatBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.configs = [installation('pat-east'), installation('pat-west')]
        self.runtime = Runtime(self.temp.name, create=True, owner=OWNER, installations=self.configs,
                               wall_clock_ms=lambda: self.now, monotonic_ms=lambda: self.now)
        self.addCleanup(self.runtime.close)
        self.registrations = [registration(self.runtime, config) for config in self.configs]
        self.provider = RegistryPatBindings(self.runtime, self.registrations)
        self.program = artifact()

    def resolve(self, context=OWNER, program=None, provider=None):
        with self.runtime.journal._transaction():
            return (provider or self.provider)(context, program or self.program, {})

    def code(self, expected, method, *args):
        with self.assertRaises(JournalError) as caught:
            method(*args)
        self.assertEqual(caught.exception.code, expected)

    def test_exact_current_rows_and_detached_explicit_metadata(self):
        result = self.resolve()
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['assignments']), 2)
        for assignment in result['assignments']:
            item = assignment['fan']
            current, _ = self.runtime.registry._binding(item['binding']['instanceId'])
            self.assertEqual(current, item['binding'])
            self.assertEqual(self.runtime.registry._type(current['typeDigest']), item['type'])
        identity = self.provider.registration_identity
        self.registrations[0]['argumentMetadata']['set_level']['level']['unit'] = 'forged'
        result['assignments'][0]['fan']['binding']['generation'] = 'forged'
        self.assertEqual(identity, self.provider.registration_identity)
        fresh = self.resolve()['assignments'][0]['fan']
        self.assertNotEqual(fresh['binding']['generation'], 'forged')
        self.assertEqual(fresh['argumentMetadata']['set_level']['level']['unit'], 'percent')

    def test_transaction_and_deployment_are_required(self):
        self.code('PAT_BINDING_TRANSACTION_REQUIRED', self.provider, OWNER, self.program, {})
        self.code('ACCESS_DENIED', self.resolve, Context(OWNER.principal, 'other:deployment'))

    def test_nonadmin_action_and_read_authority_filter_complete_inventory(self):
        instance = self.configs[0]['instances']['fan']
        self.assertEqual(self.resolve(SCOPED)['assignments'], [])
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'read')
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'invoke:set_level')
        result = self.resolve(SCOPED)
        self.assertEqual(len(result['assignments']), 1)
        self.assertEqual(result['assignments'][0]['fan']['binding']['instanceId'], instance)
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'read', enabled=False)
        self.assertEqual(self.resolve(SCOPED)['assignments'], [])

    def test_expired_presence_and_held_resources_do_not_manufacture_uniqueness(self):
        instance = self.configs[0]['instances']['fan']
        namespace = self.runtime.request(OWNER, 'namespace', {'expiresUnixMs': 20000})['token']
        request = self.runtime.request(OWNER, 'prepare', {'instanceId': instance,
            'actionId': 'set_level', 'arguments': {'level': 20, 'unit': 'percent'},
            'replayNamespace': namespace, 'operationKey': 'held:binding-test',
            'requiredEffect': 'capability_completion', 'timing': {'notBeforeUnixMs': 1000,
            'latestStartUnixMs': 8000, 'maxRunMs': 500, 'latestCompletionUnixMs': 9000}})['request']
        accepted = self.runtime.request(OWNER, 'invoke', {'request': request})
        self.assertTrue(accepted['resourceClaims'])
        self.now = 5000
        with patch.object(self.runtime.adapters[self.configs[0]['adapterId']], 'refresh',
                          side_effect=AssertionError('resolver must not refresh')):
            result = self.resolve()
        self.assertEqual(len(result['assignments']), 2)
        self.assertEqual(self.runtime.journal._db.execute('SELECT count(*) FROM claims').fetchone()[0], 1)

    def test_unknown_session_is_indeterminate_not_a_reason_to_choose_other_device(self):
        with self.runtime.journal._transaction():
            self.runtime.journal._db.execute('DELETE FROM reg_presence WHERE instance=?',
                                             (self.configs[0]['instances']['fan'],))
        self.code('PAT_BINDING_SESSION_UNKNOWN', self.resolve)

    def test_changed_installation_or_type_registration_refuses(self):
        for field in ('installationDigest', 'typeDigest'):
            values = copy.deepcopy(self.registrations)
            values[0][field] = 'sha256:' + '0' * 64
            provider = RegistryPatBindings(self.runtime, values)
            with self.subTest(field=field):
                self.code('PAT_BINDING_REGISTRATION_CHANGED', lambda: self.resolve(provider=provider))
        values = copy.deepcopy(self.registrations)
        values[0]['driverProfile'] = 'unrelated-driver'
        self.code('PAT_BINDING_REGISTRATION_CHANGED', lambda: self.resolve(
            provider=RegistryPatBindings(self.runtime, values)))

    def test_unregistered_compatible_installed_device_cannot_disappear_from_inventory(self):
        provider = RegistryPatBindings(self.runtime, self.registrations[:1])
        self.code('PAT_BINDING_METADATA_MISSING', lambda: self.resolve(provider=provider))
        instance = self.configs[0]['instances']['fan']
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'read')
        self.runtime.registry.grant(OWNER, SCOPED.principal, instance, 'invoke:set_level')
        # The unregistered west device is outside this caller's authority.
        self.assertEqual(len(self.resolve(SCOPED, provider=provider)['assignments']), 1)

    def test_missing_or_invalid_semantics_are_not_inferred_from_argument_names(self):
        values = copy.deepcopy(self.registrations)
        values[0]['argumentMetadata'] = {'another_action': {}}
        self.code('PAT_BINDING_METADATA_MISSING', lambda: self.resolve(
            provider=RegistryPatBindings(self.runtime, values)))
        values = copy.deepcopy(self.registrations)
        values[0]['argumentMetadata']['set_level']['level']['unit'] = None
        with self.assertRaises(PatError):
            self.resolve(provider=RegistryPatBindings(self.runtime, values))

    def test_complete_cartesian_inventory_over_limit_refuses_without_truncation(self):
        program = copy.deepcopy(self.program)
        for number in range(2, 6):
            role = 'fan' + str(number)
            program['roles'][role] = copy.deepcopy(program['roles']['fan'])
            step = copy.deepcopy(program['steps'][0])
            step.update(role=role, stepId='extra' + str(number))
            step['arguments']['level'] = {'literal': 40}
            program['steps'].append(step)
        program['timingBudget']['maxRunSumMs'] = 3000
        program['timingBudget']['latestCompletionOffsetMs'] = 5000
        program['effectBudget']['maxInvocations'] = len(program['steps'])
        program['outcomeContract']['requiredCompletedSteps'] = [step['stepId'] for step in program['steps']]
        self.code('PAT_BINDING_ENUMERATION_LIMIT', lambda: self.resolve(program=program))

    def test_trusted_qualification_assignment_compiles_exact_registered_environment(self):
        instance = self.configs[1]['instances']['fan']
        with self.runtime.journal._transaction():
            selected = self.provider.for_roles(OWNER, self.program, {'fan': instance})
        compiled = compile_pat(self.program, {'initialLevel': 20, 'finalLevel': 70}, selected,
            origin_ms=1000, caller_deadline_ms=4000, replay_namespace='test:namespace:1',
            procedure_key='test:procedure', operation_keys={'initial': 'test:initial', 'final': 'test:final'},
            context={'taskKind': self.program['taskKind'], 'inputProfile': self.program['inputProfile'],
                     'evidenceMode': 'simulation', 'deployment': OWNER.deployment})
        self.assertEqual(compiled['dependencies'][0]['instanceId'], instance)
        self.assertEqual(compiled['evaluationEnvironment']['roles']['fan']['installationDigest'],
                         self.registrations[1]['installationDigest'])
        self.assertEqual(self.runtime.journal._db.execute('SELECT count(*) FROM pr_procedures').fetchone()[0], 0)

    def test_duplicate_and_unknown_registration_fields_refuse(self):
        with self.assertRaises(ContractError):
            RegistryPatBindings(self.runtime, [self.registrations[0], self.registrations[0]])
        with self.assertRaises(ContractError):
            RegistryPatBindings(self.runtime, [self.registrations[0] | {'runAsRoot': True}])


if __name__ == '__main__':
    unittest.main()
