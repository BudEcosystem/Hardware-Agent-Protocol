"""Original Journal/Registry admission integration; no Runtime/provider effects."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.demo import object_schema, type_bundle
from hms.journal import Context, Journal, JournalError
from hms.registry import Registry, RegistryPolicy
from hms.resource_catalog import ResourceCatalog, control_generation
from hms.resource_topology import binding_proof
from io_fixtures import topology, generations, node, pin

HERE = Path(__file__).resolve().parent
EVIDENCE_DIRECTORY = None


def definitions(topology):
    """New typed I/O descriptions; never reuse a fan primitive or handler."""
    result = {}
    for instance in sorted({row['instanceId'] for row in topology['consumers']}):
        combined, resource_map = None, {}
        for consumer in (row for row in topology['consumers'] if row['instanceId'] == instance):
            action = consumer['actionId']
            access = topology['nodes'][topology['aliases'][consumer['rootAliases'][0]]['node']]['kind']
            if access == 'gpio_access':
                properties = {'level': {'type': 'integer', 'minimum': 0, 'maximum': 1},
                              'durationMs': {'type': 'integer', 'minimum': 1, 'maximum': 5000}}
                effect = 'synthetic_gpio_pulse'
            elif access == 'pwm_access':
                properties = {'frequencyHz': {'type': 'integer', 'minimum': 100, 'maximum': 10000},
                    'dutyPermille': {'type': 'integer', 'minimum': 0, 'maximum': 1000},
                    'resolutionBits': {'type': 'integer', 'const': 8},
                    'durationMs': {'type': 'integer', 'minimum': 1, 'maximum': 5000}}
                effect = 'synthetic_pwm_burst'
            else:
                properties = {'frequencyHz': {'type': 'integer', 'minimum': 100, 'maximum': 10000}}
                effect = 'synthetic_timer_configuration'
            roles = [action + ':root:' + str(i) for i in range(len(consumer['rootAliases']))]
            bundle = type_bundle('io-' + instance.replace(':', '-'), action, object_schema(properties),
                {'type': 'integer', 'minimum': 0, 'maximum': 10000}, unit='1', effect=effect, resource=roles[0])
            bundle['execution']['actions'][action]['resources'] = roles
            bundle['execution']['actions'][action]['preconditions'] = []
            bundle['execution']['capabilities'] = ['sim:synthetic-io-admission']
            bundle['td']['description'] = 'Original admission-only fixture; no executor or physical I/O installed.'
            if combined is None:
                combined = bundle
            else:
                combined['execution']['actions'].update(bundle['execution']['actions'])
                combined['td']['actions'].update(bundle['td']['actions'])
            resource_map.update(zip(roles, consumer['rootAliases']))
        result[instance] = (combined, resource_map)
    return result


class IoResourceAdmissionTests(unittest.TestCase):
    def tearDown(self):
        if EVIDENCE_DIRECTORY is None:
            return
        target = EVIDENCE_DIRECTORY / self._testMethodName
        target.mkdir(exist_ok=True)
        with sqlite3.connect(target / 'authority.db') as connection:
            self.journal._db.backup(connection)
        snapshot = {}
        for table in ('operations', 'claims', 'resource_floors', 'rc_catalog', 'rc_generations',
                      'rc_tokens', 'rc_proofs', 'reg_binding_history', 'reg_resource_requirements', 'reg_resource_instances'):
            if self.journal._db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                snapshot[table] = [{key: value.decode() if type(value) is bytes else value for key, value in dict(row).items()}
                                   for row in self.journal._db.execute('SELECT * FROM ' + table)]
        (target / 'rows.json').write_text(json.dumps(snapshot, indent=2) + '\n')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'authority.db'
        self.clock = 1000
        self.owner = Context('owner', 'simulation:io-hub')
        self.value = topology()
        self.value['consumers'].append({'instanceId': 'sim:gpio5:other-route', 'actionId': 'pulse',
                                      'rootAliases': ['alias:gpio5'], 'requires': []})
        self._setup_catalog()

    def _setup_catalog(self, *, create=True, attach=True, policy_options=None):
        self.support_calls = []
        self.policy = RegistryPolicy(installed_support=self.support, installed_plan_support=self.support,
                                     **(policy_options or {}))
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.clock, create=create)
        self.addCleanup(self.journal.close)
        self.registry = Registry(self.journal, monotonic_ms=lambda: self.clock,
                                 bootstrap_owner=self.owner if create else None)
        self.policy.attach(self.registry)
        if create:
            self.initial = generations(self.value)
            instances = sorted({row['instanceId'] for row in self.value['consumers']})
            self.routes = {'profile': 'hms.resource-route-inventory/0.1', 'adapters': {
                'io:routeA': [item for item in instances if item not in {'sim:gpio6', 'sim:gpio5:other-route'}],
                'io:routeB': [item for item in instances if item in {'sim:gpio6', 'sim:gpio5:other-route'}]}}
            self.docs = definitions(self.value)
            self.catalog = ResourceCatalog(self.journal, self.registry, create=True, owner=self.owner,
                topology=self.value, generations=self.initial, routes=self.routes)
            for instance, (bundle, resource_map) in self.docs.items():
                digest = self.registry.publish_type(self.owner, canonical(bundle))
                self.registry.enroll(self.owner, instance, digest, identity_kind='simulation', identity_ref=instance)
                proof = binding_proof(self.value, self.initial, instance)
                adapter = next(key for key, values in self.routes['adapters'].items() if instance in values)
                binding = {'profile': 'hms.binding/0.1', 'instanceId': instance, 'generation': proof['bindingGeneration'],
                    'typeDigest': digest, 'calibrationRevision': 'synthetic:io:1', 'controlGeneration': control_generation(proof),
                    'mode': 'simulation', 'adapterId': adapter, 'resourceMap': resource_map,
                    'argumentSchemas': {key: action['inputSchema'] for key, action in bundle['execution']['actions'].items()}}
                self.catalog.bind(self.owner, binding)
            self.namespace = self.journal.issue_namespace(self.owner, 100000)['token']
        else:
            self.catalog = ResourceCatalog(self.journal, self.registry)
        if attach:
            self.policy.attach_resource_resolver(self.catalog.resolve)
        self.presence()

    def presence(self):
        for instance in self.docs:
            binding, active = self.registry._binding(instance)
            if active:
                self.registry.report_presence(instance, adapter_id=binding['adapterId'], endpoint_session='session:io:1', ttl_ms=60000)

    def support(self, intent, binding, resources):
        # A declared admission-only fixture, not an installed execution backend.
        self.support_calls.append((intent['instanceId'], resources))
        expected = binding_proof(self.value, self.initial, intent['instanceId'])['expandedClaims'][intent['actionId']]
        if tuple(expected) != resources or intent['instanceId'] not in self.docs:
            raise JournalError('FIXTURE_SUPPORT_REFUSED')

    def request(self, instance='sim:gpio5', action=None, key='operation:1'):
        binding, _ = self.registry._binding(instance)
        action = action or next(iter(self.docs[instance][0]['execution']['actions']))
        args = {'frequencyHz': 1000}
        schema = binding['argumentSchemas'][action]['properties']
        if 'level' in schema:
            args = {'level': 1, 'durationMs': 100}
        elif 'dutyPermille' in schema:
            args = {'frequencyHz': 1000, 'dutyPermille': 500, 'resolutionBits': 8, 'durationMs': 100}
        return {'protocol': 'hms.invoke/0.1', 'replayNamespace': self.namespace, 'operationKey': key,
            'intent': {'instanceId': instance, 'actionId': action, 'endpointSession': 'session:io:1',
                'descriptionDigest': binding['typeDigest'], 'bindingGeneration': binding['generation'],
                'controlGeneration': binding['controlGeneration'], 'calibrationRevision': binding['calibrationRevision'],
                'arguments': args, 'requiredEffect': 'capability_completion', 'timing': {
                    'notBeforeUnixMs': 1000, 'latestStartUnixMs': 10000, 'maxRunMs': 500,
                    'latestCompletionUnixMs': 12000}}}

    def submit(self, *args, **kwargs):
        return self.journal.submit(self.owner, canonical(self.request(*args, **kwargs)))

    def counts(self):
        return {table: self.journal._db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in ('operations', 'claims', 'replay_keys', 'resource_floors', 'rc_generations', 'rc_proofs', 'reg_binding_history')}

    def publish(self, *, new='generation:2', expected='generation:1', revision=1):
        return self.catalog.publish_generation(self.owner, 'svcA', expected, new, expected_revision=revision)

    def test_gpio_pwm_conflict_is_atomic_and_independent_pad_admits(self):
        first = self.submit()
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_BUSY'):
            self.submit('sim:pwm5', key='pwm:busy')
        self.assertEqual(before, self.counts())
        independent = self.submit('sim:gpio6', key='gpio6:free')
        self.assertEqual(first['admission']['resources'], ['atom:pin5'])
        self.assertEqual(independent['admission']['resources'], ['atom:pin6'])
        self.assertEqual(self.support_calls[-1][1], ('atom:pin6',))
        self.assertIsNotNone(self.journal.claim_dispatch(independent['id']))

    def test_multi_atom_pwm_claims_and_cross_route_fences_share_canonical_pad(self):
        first = self.submit('sim:pwm5', key='pwm:1')
        self.assertEqual([row['resource'] for row in first['claims']], ['atom:chan0', 'atom:pin5', 'atom:timer0'])
        with self.assertRaisesRegex(JournalError, 'RESOURCE_BUSY'):
            self.submit('sim:gpio5:other-route', key='routeB:busy')
        self.journal.request_cancel(self.owner, first['id'])  # Accepted; no handoff occurred.
        second = self.submit('sim:gpio5:other-route', key='routeB:next')
        self.assertEqual(second['claims'], [{'resource': 'atom:pin5', 'fence': 2}])
        self.assertEqual(second['admission']['resources'], ['atom:pin5'])

    def test_persisted_requirement_survives_reopen_without_resolver_or_inventory(self):
        self.journal.close()
        self._setup_catalog(create=False, attach=False)
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_RESOLVER_REQUIRED'):
            self.submit()
        self.assertEqual(before, self.counts())
        self.journal.close()
        self._setup_catalog(create=False, attach=False, policy_options={'managed_resource_adapters': []})
        with self.assertRaisesRegex(JournalError, 'RESOURCE_RESOLVER_REQUIRED'):
            self.submit()

    def test_missing_catalog_and_missing_proof_never_fall_back_to_flat_aliases(self):
        self.journal._db.execute('DELETE FROM rc_proofs WHERE instance=?', ('sim:gpio5',))
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_PROOF_REQUIRED'):
            self.submit()
        self.assertEqual(before, self.counts())
        self.journal._db.execute('DROP TABLE rc_catalog')
        with self.assertRaisesRegex(JournalError, 'RESOURCE_CATALOG_REQUIRED'):
            self.submit('sim:gpio6', key='missing:catalog')
        self.assertTrue(self.journal._db.execute('SELECT 1 FROM reg_resource_requirements').fetchone())

    def test_tampered_proof_and_binding_history_refuse_before_claims(self):
        self.journal._db.execute("UPDATE rc_proofs SET document=? WHERE instance=?", (b'{}', 'sim:gpio5'))
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_PROOF_INVALID'):
            self.submit()
        self.assertEqual(before, self.counts())
        self.journal._db.execute("UPDATE reg_binding_history SET digest='wrong' WHERE instance=?", ('sim:gpio6',))
        with self.assertRaisesRegex(JournalError, 'RESOURCE_BINDING_HISTORY_INVALID'):
            self.submit('sim:gpio6', key='bad:binding')

    def test_generation_publication_changes_bindings_and_retains_historical_proof(self):
        old_request = self.request()
        old_generation = old_request['intent']['bindingGeneration']
        old = self.catalog.history(self.owner, 'sim:gpio5', old_generation)
        result = self.publish()
        self.assertEqual(result['publicationKind'], 'quiescent_configuration')
        self.assertIs(result['driverEffectExecuted'], False)
        self.assertEqual(old, self.catalog.history(self.owner, 'sim:gpio5', old_generation))
        with self.assertRaisesRegex(JournalError, 'BINDING_CHANGED'):
            self.journal.submit(self.owner, canonical(old_request))
        self.presence()
        current = self.submit(key='after:publication')
        self.assertNotEqual(current['intent']['bindingGeneration'], old_generation)
        self.assertEqual(current['admission']['resources'], ['atom:pin5'])

    def test_exact_operation_replay_precedes_current_generation_and_resolver(self):
        request = self.request(); first = self.journal.submit(self.owner, canonical(request))
        self.journal.request_cancel(self.owner, first['id'])
        self.publish()
        self.policy._resource_resolver = None  # Trusted setup failure: replay must remain historical.
        repeated = self.journal.submit(self.owner, canonical(request))
        self.assertEqual(first['id'], repeated['id'])
        self.assertEqual(repeated['state'], 'canceled')
        changed = copy.deepcopy(request); changed['intent']['arguments']['level'] = 0
        with self.assertRaisesRegex(JournalError, 'KEY_CONFLICT'):
            self.journal.submit(self.owner, canonical(changed))

    def test_fresh_recheck_rejects_missing_proof_and_keeps_accepted_claims(self):
        op = self.submit()
        self.journal._db.execute('DELETE FROM rc_proofs WHERE instance=?', ('sim:gpio5',))
        with self.assertRaisesRegex(JournalError, 'RESOURCE_PROOF_REQUIRED'):
            self.journal.claim_dispatch(op['id'])
        retained = self.journal.status(self.owner, op['id'])
        self.assertEqual(retained['state'], 'accepted')
        self.assertEqual(retained['claims'], op['claims'])

    def test_unknown_handoff_and_claims_block_publication_across_reopen(self):
        op = self.submit(); ticket = self.journal.claim_dispatch(op['id'])
        self.journal.mark_unknown(ticket, 'synthetic:lost-handoff')
        before = self.catalog.snapshot(self.owner)
        with self.assertRaisesRegex(JournalError, 'RESOURCE_CLAIMS_UNRESOLVED'):
            self.publish()
        self.assertEqual(before, self.catalog.snapshot(self.owner))
        self.journal.close(); self._setup_catalog(create=False)
        retained = self.journal.status(self.owner, op['id'])
        self.assertEqual(retained['state'], 'outcome_unknown')
        self.assertEqual(retained['claims'], op['claims'])
        with self.assertRaisesRegex(JournalError, 'RESOURCE_CLAIMS_UNRESOLVED'):
            self.publish()

    def test_token_nonreuse_and_revision_cas_are_persistent(self):
        self.publish()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_GENERATION_CONFLICT'):
            self.publish(new='generation:3')
        with self.assertRaisesRegex(JournalError, 'RESOURCE_GENERATION_REUSED'):
            self.publish(new='generation:1', expected='generation:2', revision=2)
        self.journal.close(); self._setup_catalog(create=False)
        with self.assertRaisesRegex(JournalError, 'RESOURCE_GENERATION_REUSED'):
            self.publish(new='generation:1', expected='generation:2', revision=2)

    def test_atomic_multi_binding_publication_rolls_back_all_business_rows(self):
        before = self.catalog.snapshot(self.owner)
        history = self.counts(); original = self.registry._bind_in_tx; calls = []
        def fail_second(owner, binding):
            calls.append(binding['instanceId'])
            original(owner, binding)
            if len(calls) == 2:
                raise RuntimeError('injected after second binding write')
        with patch.object(self.registry, '_bind_in_tx', fail_second), self.assertRaisesRegex(RuntimeError, 'injected'):
            self.publish()
        self.assertEqual(len(calls), 2)
        self.assertEqual(before, self.catalog.snapshot(self.owner))
        self.assertEqual(history, self.counts())
        self.assertFalse(self.journal._db.execute("SELECT 1 FROM rc_tokens WHERE generation='generation:2'").fetchone())

    def test_authorization_precedes_proof_lookup_and_management_requires_admin(self):
        user = Context('pad-user', self.owner.deployment)
        self.journal._db.execute('DELETE FROM rc_proofs WHERE instance=?', ('sim:gpio5',))
        request = self.request()
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.policy.validate_bound(user, request['intent'], self.clock)
        self.registry.grant(self.owner, user.principal, 'sim:gpio6', 'read')
        self.registry.grant(self.owner, user.principal, 'sim:gpio6', 'invoke:pulse')
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.catalog.publish_generation(user, 'svcA', 'generation:1', 'generation:2', expected_revision=1)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.catalog.snapshot(user)

    def test_bound_planning_uses_same_atoms_and_rejects_malformed_resolver_output(self):
        request = self.request('sim:pwm5')
        _, _, resources = self.policy.validate_bound(self.owner, request['intent'], self.clock)
        self.assertEqual(resources, ('atom:chan0', 'atom:pin5', 'atom:timer0'))
        for bad in (['atom:pin5'], (), ('atom:pin5', 'atom:pin5'), ('z', 'a')):
            with patch.object(self.policy, '_resource_resolver', lambda *args, **kwargs: bad), self.assertRaisesRegex(JournalError, 'RESOURCE_INVALID_RESOLUTION'):
                self.policy.validate_bound(self.owner, request['intent'], self.clock)

    def test_unregistered_root_map_cannot_create_catalog_binding(self):
        binding, _ = self.registry._binding('sim:gpio5')
        binding['resourceMap']['pulse:root:0'] = 'alias:gpio6'
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_ROOT_MISMATCH'):
            self.catalog.bind(self.owner, binding)
        self.assertEqual(before, self.counts())

    def test_plain_registry_rebind_cannot_escape_managed_instance_requirement(self):
        binding, _ = self.registry._binding('sim:gpio5')
        binding.update(generation='attempted:flat-migration', adapterId='io:unregistered')
        binding['resourceMap']['pulse:root:0'] = 'raw:pin5'
        self.registry.bind(self.owner, canonical(binding))
        self.presence()
        for inventory in (None, []):
            self.journal.close()
            options = None if inventory is None else {'managed_resource_adapters': inventory}
            self._setup_catalog(create=False, attach=False, policy_options=options)
            before = self.counts()
            with self.assertRaisesRegex(JournalError, 'RESOURCE_ROUTE_MISMATCH'):
                self.submit(key='flat:migration')
            self.assertEqual(before, self.counts())
            self.assertTrue(self.journal._db.execute('SELECT 1 FROM reg_resource_instances WHERE instance=?', ('sim:gpio5',)).fetchone())

    def test_missing_route_requirement_with_retained_instance_refuses(self):
        self.journal._db.execute("DELETE FROM reg_resource_requirements WHERE adapter='io:routeA'")
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_ROUTE_UNREGISTERED'):
            self.submit()
        self.assertEqual(before, self.counts())

    def test_retained_proof_from_older_dependencies_refuses_fresh_resolution(self):
        old_binding, _ = self.registry._binding('sim:gpio5')
        self.publish()
        # Deliberately restore only the current binding pointer to a genuine
        # historical row; catalog dependencies remain at revision 2.
        self.journal._db.execute('UPDATE reg_bindings SET generation=?, document=? WHERE instance=?',
            (old_binding['generation'], canonical(old_binding), 'sim:gpio5'))
        self.presence()
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_DEPENDENCY_CHANGED'):
            self.submit(key='old:proof')
        self.assertEqual(before, self.counts())

    def test_clock_refusal_precedes_generation_or_binding_writes(self):
        before = self.counts()
        saved = self.catalog.snapshot(self.owner)
        self.clock = 999
        with self.assertRaisesRegex(JournalError, 'CLOCK_REGRESSION'):
            self.publish()
        self.assertEqual(before, self.counts())
        self.assertEqual(saved, self.catalog.snapshot(self.owner))
        binding, _ = self.registry._binding('sim:gpio5')
        with self.assertRaisesRegex(JournalError, 'CLOCK_REGRESSION'):
            self.catalog.bind(self.owner, binding)
        self.assertEqual(before, self.counts())

    def test_missing_generation_history_and_detached_snapshot_outputs(self):
        snapshot = self.catalog.snapshot(self.owner)
        snapshot['routes']['adapters']['io:routeA'].clear()
        snapshot['generations']['nodes']['svcA'] = 'forged:token'
        self.assertEqual(self.catalog.snapshot(self.owner)['generations']['nodes']['svcA'], 'generation:1')
        self.journal._db.execute('DELETE FROM rc_generations WHERE revision=1')
        before = self.counts()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_GENERATION_HISTORY_MISSING'):
            self.submit()
        self.assertEqual(before, self.counts())

    @staticmethod
    def original_registry_module():
        spec = importlib.util.spec_from_file_location('hms.retained_original_registry', HERE / 'baseline/hms/registry.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_original_registry_refuses_activated_storage_on_isolated_database(self):
        original = self.original_registry_module()
        cloned = Path(self.temp.name) / 'old-binary.db'
        with sqlite3.connect(cloned) as connection:
            self.journal._db.backup(connection)
        old_policy = original.RegistryPolicy()
        with Journal(cloned, old_policy, clock_ms=lambda: self.clock, create=False) as old_journal:
            with self.assertRaisesRegex(JournalError, 'UNSUPPORTED_REGISTRY'):
                original.Registry(old_journal, monotonic_ms=lambda: self.clock)
        self.assertEqual(self.registry._meta('version'), 'hms.registry/resource-roots/0.1')
        self.assertIsNotNone(self.submit(key='new:aware')['id'])

    def test_activation_version_and_all_requirements_rollback_together(self):
        path = Path(self.temp.name) / 'activation.db'
        policy = RegistryPolicy()
        with Journal(path, policy, clock_ms=lambda: self.clock, create=True) as journal:
            registry = Registry(journal, bootstrap_owner=self.owner, monotonic_ms=lambda: self.clock)
            policy.attach(registry)
            tables = {row[0] for row in journal._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(any(name.startswith('rc_') or name.startswith('reg_resource') for name in tables))
            with patch.object(ResourceCatalog, '_insert_generations', side_effect=RuntimeError('activation:injected')):
                with self.assertRaisesRegex(RuntimeError, 'activation:injected'):
                    ResourceCatalog(journal, registry, create=True, owner=self.owner,
                        topology=self.value, generations=self.initial, routes=self.routes)
            self.assertEqual(registry._meta('version'), 'hms.registry/0.1')
            self.assertEqual(tables, {row[0] for row in journal._db.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        # New code merely reopening legacy storage must leave its profile and
        # table inventory unchanged; exact original Registry can still open it.
        with Journal(path, RegistryPolicy(), clock_ms=lambda: self.clock, create=False) as journal:
            registry = Registry(journal, monotonic_ms=lambda: self.clock)
            self.assertEqual(registry._meta('version'), 'hms.registry/0.1')
            self.assertEqual(tables, {row[0] for row in journal._db.execute("SELECT name FROM sqlite_master WHERE type='table'")})
            self.assertEqual(self.original_registry_module().Registry(journal)._meta('version'), 'hms.registry/0.1')

    def test_partial_activated_storage_refuses_registry_reopen(self):
        self.journal._db.execute('DROP TABLE rc_tokens')
        self.journal.close()
        with self.assertRaisesRegex(JournalError, 'RESOURCE_STORAGE_PARTIAL'):
            self._setup_catalog(create=False, attach=False)

    def test_mixed_legacy_route_requires_catalog_validation_then_original_flat_mapping(self):
        legacy = 'sim:legacy-pad8'
        bundle = copy.deepcopy(self.docs['sim:gpio6'][0])
        digest = self.registry.publish_type(self.owner, canonical(bundle))
        self.registry.enroll(self.owner, legacy, digest, identity_kind='simulation', identity_ref=legacy)
        binding, _ = self.registry._binding('sim:gpio6')
        binding.update(instanceId=legacy, generation='legacy:binding1', adapterId='io:legacy',
                       resourceMap={'pulse:root:0': 'legacy:pad8'})
        self.registry.bind(self.owner, canonical(binding))
        self.docs[legacy] = (bundle, binding['resourceMap'])
        self.presence()
        def legacy_support(intent, bound, resources):
            self.assertEqual(intent['instanceId'], legacy)
            self.assertEqual(resources, ('legacy:pad8',))
        with patch.object(self.policy, '_installed_support', legacy_support):
            admitted = self.submit(legacy, key='legacy:accepted')
        self.assertEqual(admitted['admission']['resources'], ['legacy:pad8'])
        self.journal.request_cancel(self.owner, admitted['id'])
        # A partial inventory is not permission to choose legacy flat fallback.
        self.journal._db.execute("DELETE FROM reg_resource_instances WHERE instance='sim:gpio5'")
        with self.assertRaisesRegex(JournalError, 'RESOURCE_REQUIREMENT_MISSING'):
            self.submit(legacy, key='legacy:refused')
        self.policy._resource_resolver = None
        with self.assertRaisesRegex(JournalError, 'RESOURCE_RESOLVER_REQUIRED'):
            self.submit(legacy, key='legacy:no-resolver')

    def test_sibling_action_claim_blocks_full_instance_generation_publication(self):
        self.journal.close()
        self.path = Path(self.temp.name) / 'multi-action.db'
        self.value = topology()
        self.value['consumers'][0].update(instanceId='sim:combined', actionId='primary')
        self.value['consumers'][1].update(instanceId='sim:combined', actionId='sibling')
        # Retain a distinct unrelated instance and route so publication must not
        # serialize the entire hub or invalidate that instance's binding.
        self.value['nodes']['pin7'] = pin()
        self.value['nodes']['gpio7'] = node('gpio_access', {'pin': 'pin7'}, requires=('driverB',))
        self.value['atoms']['atom:pin7'] = {'node': 'pin7', 'purpose': 'exclusive_hardware'}
        self.value['aliases']['alias:gpio7'] = {'node': 'gpio7', 'includes': ['atom:pin7']}
        self.value['consumers'].append({'instanceId': 'sim:gpio6', 'actionId': 'pulse', 'rootAliases': ['alias:gpio7'], 'requires': []})
        self._setup_catalog()
        sibling = self.submit('sim:combined', action='sibling', key='sibling:active')
        unrelated = self.submit('sim:gpio6', key='unrelated:active')
        original_unrelated = self.registry._binding('sim:gpio6')
        with self.assertRaisesRegex(JournalError, 'RESOURCE_CLAIMS_UNRESOLVED'):
            self.publish()
        self.journal.request_cancel(self.owner, sibling['id'])
        published = self.publish()
        self.assertIn({'instanceId': 'sim:combined', 'actionId': 'sibling'}, published['scope']['affectedConsumers'])
        self.assertEqual(original_unrelated, self.registry._binding('sim:gpio6'))
        self.assertEqual(self.journal.status(self.owner, unrelated['id'])['state'], 'accepted')
        self.assertIsNotNone(self.journal.claim_dispatch(unrelated['id']))

    def test_extracted_registry_bind_transaction_body_is_ast_identical(self):
        before = ast.parse((HERE / 'baseline/hms/registry.py').read_text())
        after = ast.parse((HERE / 'staged/hms/registry.py').read_text())
        def method(tree, name):
            cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == 'Registry')
            return next(item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name == name)
        old = next(item for item in method(before, 'bind').body if isinstance(item, ast.With)).body
        new = method(after, '_bind_in_tx').body[-len(old):]
        self.assertEqual([ast.dump(item, include_attributes=False) for item in old],
                         [ast.dump(item, include_attributes=False) for item in new])
