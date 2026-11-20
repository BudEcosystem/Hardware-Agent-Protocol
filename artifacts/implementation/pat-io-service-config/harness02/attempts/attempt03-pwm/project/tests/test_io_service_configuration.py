"""Trusted configuration joins and one actual configured original worker."""
import builtins
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import pat_digest
from hms.synthetic_io_installation import installation_digest, normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_group_history import authority
from test_io_supervisor_process import IoSupervisorProcessTests
import io_services as service
import supervisor_contracts as contracts


def configuration(document, selected):
    records = []
    for actor in selected.values():
        value = actor['descriptor']
        records.append(dict(instanceId=value['binding']['instanceId'], driverProfile=value['driverProfile'],
            typeDigest=value['binding']['typeDigest'], argumentMetadata=copy.deepcopy(value['argumentMetadata'])))
    return dict(profile=service.CONFIG_PROFILE, policy=service.POLICY, deployment=document['topology']['deployment'],
        evaluatorId='eval:configured-io', revision=1, installationDigest=installation_digest(document),
        initialRegistryRevision=authority(document)['initialRegistryRevision'], groupLimits=dict(service.CEILINGS),
        supervisorLimits=dict(contracts.DEFAULT_LIMITS), registrations=records,
        qualifications=[dict(artifactDigest=pat_digest(program(pwm=pwm, literal=True)),
            roleInstances={'io': selected['pwm' if pwm else 'gpio']['descriptor']['binding']['instanceId']}) for pwm in (False, True)],
        challengeBindings={role: dict(instanceId=row['descriptor']['binding']['instanceId'], actionId=row['actionId'])
            for role, row in selected.items()})


def descriptors(selected):
    return {row['descriptor']['binding']['instanceId']: copy.deepcopy(row['descriptor']) for row in selected.values()}


class IoServiceConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = normalize_installation(installation()); cls.selected = bindings(cls.document)
        cls.config = configuration(cls.document, cls.selected); cls.pin = service.prepare_service_pin(cls.config, cls.document)
        cls.configured = service.ConfiguredIoService(cls.config, cls.document, expected_pin=cls.pin)
        cls.prepared = cls.configured.prepare_run(program(literal=True), 'run:configured', trusted_descriptors=descriptors(cls.selected))

    def parse(self, value=None, **overrides):
        args = dict(expected_pin=self.pin, expected_run_id='run:configured', expected_request_digest=self.prepared['requestDigest'])
        args.update(overrides)
        return service.parse_prepared_run(self.prepared if value is None else value, **args)

    def test_configuration_order_and_mutations_cannot_change_fixed_setup(self):
        config = copy.deepcopy(self.config); original = canonical(config)
        config['registrations'].reverse(); config['qualifications'].reverse()
        self.assertEqual(service.configuration_digest(config), service.configuration_digest(self.config))
        parsed = service.parse_configuration(config); parsed['registrations'].clear()
        self.assertEqual(canonical(self.config), original)
        self.assertEqual(service.configuration_digest(json.dumps(config, indent=2).encode()), service.configuration_digest(config))

    def test_unknown_profiles_and_execution_or_result_fields_refuse(self):
        for key, value in [('command', ['sh']), ('import', 'untrusted.module'), ('url', 'https://example.invalid'),
                           ('passed', True), ('result', {}), ('driverDigest', 'sha256:' + '0' * 64)]:
            for where in ('root', 'registration'):
                config = copy.deepcopy(self.config); target = config if where == 'root' else config['registrations'][0]
                target[key] = value
                with self.assertRaises(service.IoServiceError): service.parse_configuration(config)
        for key in ('policy', 'profile'):
            config = self.config | {key: 'untrusted'}
            with self.assertRaisesRegex(service.IoServiceError, 'POLICY'): service.parse_configuration(config)

    def test_every_limit_rejects_widening_boolean_float_and_missing_values(self):
        for section, bounds in [('groupLimits', service.CEILINGS), ('supervisorLimits', contracts.DEFAULT_LIMITS)]:
            for key, maximum in bounds.items():
                for value in (True, 1.0, 0, maximum + 1):
                    config = copy.deepcopy(self.config); config[section][key] = value
                    with self.subTest(section=section, key=key, value=value), self.assertRaises(service.IoServiceError):
                        service.parse_configuration(config)
            config = copy.deepcopy(self.config); config[section].pop(next(iter(bounds)))
            with self.assertRaises(service.IoServiceError): service.parse_configuration(config)

    def test_duplicate_and_unregistered_maps_refuse_without_silent_selection(self):
        mutations = [lambda x: x['registrations'].append(copy.deepcopy(x['registrations'][0])),
            lambda x: x['qualifications'].append(copy.deepcopy(x['qualifications'][0])),
            lambda x: x['qualifications'][0]['roleInstances'].update(io='missing'),
            lambda x: x['qualifications'][0]['roleInstances'].update(extra='sim:gpio5'),
            lambda x: x['challengeBindings'].pop('alias'),
            lambda x: x['challengeBindings']['alias'].update(instanceId='sim:gpio5')]
        for mutate in mutations:
            config = copy.deepcopy(self.config); mutate(config)
            with self.assertRaises(service.IoServiceError): service.parse_configuration(config)

    def test_configuration_bounds_and_custom_values_refuse_without_callbacks(self):
        class Key(str): pass
        class Value:
            def __deepcopy__(self, memo): raise AssertionError('copy callback')
        config = copy.deepcopy(self.config); config[Key('revision')] = config.pop('revision')
        with patch.object(Key, '__hash__', side_effect=AssertionError('hash callback')), \
             patch.object(Key, '__eq__', side_effect=AssertionError('equality callback')):
            with self.assertRaises(service.IoServiceError): service.parse_configuration(config)
        for value in (b' ' * 65537, self.config | {'revision': Value()}, self.config | {'revision': 1.0}):
            with self.assertRaises(service.IoServiceError): service.parse_configuration(value)

    def test_configuration_parsing_has_no_source_database_clock_or_launch_access(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('file')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('worker')):
            self.assertEqual(service.parse_configuration(self.config), service.parse_configuration(canonical(self.config)))

    def test_pin_is_derived_from_installed_configuration_and_all_execution_sources(self):
        self.assertEqual(self.pin['configurationDigest'], service.configuration_digest(self.config))
        self.assertEqual(self.pin['implementation']['driverDigest'], self.document['driverDigest'])
        self.assertEqual(self.pin['supervisorIdentity'], self.prepared['request']['supervisorIdentity'])
        self.assertIn('io_services.py', contracts.SOURCE_FILES)
        self.assertEqual(service.prepare_service_pin(self.config, self.document), self.pin)

    def test_changed_configuration_revision_or_evaluator_refuses_existing_pin(self):
        for key, value in [('revision', 2), ('evaluatorId', 'eval:changed'), ('initialRegistryRevision', 14)]:
            config = self.config | {key: value}
            with self.assertRaisesRegex(service.IoServiceError, 'PIN_CHANGED'):
                service.ConfiguredIoService(config, self.document, expected_pin=self.pin)

    def test_installation_metadata_and_type_registration_drift_refuse(self):
        changes = [lambda x: x.update(installationDigest='sha256:' + '0' * 64),
            lambda x: x['registrations'][0].update(typeDigest='sha256:' + '0' * 64),
            lambda x: x['registrations'][0].update(argumentMetadata={'fake': {}})]
        for change in changes:
            config = copy.deepcopy(self.config); change(config)
            with self.assertRaises(service.IoServiceError): service.prepare_service_pin(config, self.document)
        changed = copy.deepcopy(self.document); changed['driverDigest'] = 'sha256:' + '0' * 64
        with self.assertRaises(service.IoServiceError): service.prepare_service_pin(self.config, changed)

    def test_descriptor_inventory_is_exact_and_custom_keys_never_run_callbacks(self):
        for missing in (True, False):
            chosen = descriptors(self.selected)
            if missing: chosen.pop(next(iter(chosen)))
            else: chosen['unexpected'] = copy.deepcopy(next(iter(chosen.values())))
            with self.assertRaisesRegex(service.IoServiceError, 'DESCRIPTOR_CLOSURE'):
                self.configured.prepare_run(program(literal=True), 'run:changed', trusted_descriptors=chosen)
        class Key(str): pass
        chosen = descriptors(self.selected); key = next(iter(chosen)); chosen[Key(key)] = chosen.pop(key)
        with patch.object(Key, '__hash__', side_effect=AssertionError('hash')), patch.object(Key, '__eq__', side_effect=AssertionError('eq')):
            with self.assertRaisesRegex(service.IoServiceError, 'DESCRIPTORS'):
                self.configured.prepare_run(program(literal=True), 'run:changed', trusted_descriptors=chosen)

    def test_changed_descriptor_source_binding_metadata_or_session_type_refuses(self):
        mutations = [lambda x: x.update(driverDigest='sha256:' + '0' * 64),
            lambda x: x['binding'].update(generation='changed'),
            lambda x: x.update(argumentMetadata={}), lambda x: x.update(endpointSession=True)]
        for mutate in mutations:
            chosen = descriptors(self.selected); mutate(chosen['sim:gpio5'])
            with self.assertRaises(service.IoServiceError):
                self.configured.prepare_run(program(literal=True), 'run:changed', trusted_descriptors=chosen)

    def test_unconfigured_artifact_and_wrong_role_name_refuse(self):
        artifact = program(literal=True); artifact['name'] += ':changed'
        with self.assertRaisesRegex(service.IoServiceError, 'ARTIFACT_NOT_CONFIGURED'):
            self.configured.prepare_run(artifact, 'run:unknown', trusted_descriptors=descriptors(self.selected))
        config = copy.deepcopy(self.config)
        for row in config['qualifications']:
            row['roleInstances'] = {'different': next(iter(row['roleInstances'].values()))}
        pin = service.prepare_service_pin(config, self.document)
        configured = service.ConfiguredIoService(config, self.document, expected_pin=pin)
        with self.assertRaisesRegex(service.IoServiceError, 'ROLE_MAP'):
            configured.prepare_run(program(literal=True), 'run:wrong-role', trusted_descriptors=descriptors(self.selected))

    def test_gpio_and_pwm_run_inputs_are_bound_to_same_explicit_service(self):
        pwm = self.configured.prepare_run(program(pwm=True, literal=True), 'run:pwm', trusted_descriptors=descriptors(self.selected))
        self.assertEqual(pwm['servicePin'], self.prepared['servicePin'])
        self.assertEqual(pwm['configuration'], self.prepared['configuration'])
        self.assertEqual(len(pwm['bundle']['documents']), 37)
        self.assertEqual(len(json.loads(pwm['bundle']['header'])['caseIds']), 30)
        self.assertNotEqual(pwm['requestDigest'], self.prepared['requestDigest'])
        self.assertEqual(pwm['request']['context']['configurationRevision'], 1)
        self.assertEqual(pwm['request']['groupLimits'], self.config['groupLimits'])
        self.assertEqual(pwm['request']['limits'], self.config['supervisorLimits'])

    def test_logical_run_change_preserves_pin_and_changes_request_association(self):
        value = self.configured.prepare_run(program(literal=True), 'run:different', trusted_descriptors=descriptors(self.selected))
        self.assertEqual(value['servicePin'], self.prepared['servicePin'])
        self.assertNotEqual(value['requestDigest'], self.prepared['requestDigest'])
        with self.assertRaises(service.IoServiceError): self.parse(value)

    def test_historical_parser_never_replans_or_checks_current_sources(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('file')), \
             patch.object(builtins, 'open', side_effect=AssertionError('open')), \
             patch.object(service, 'prepare_service_pin', side_effect=AssertionError('source')), \
             patch.object(service, 'prepare_io_run_bundle', side_effect=AssertionError('planner')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            self.assertEqual(self.parse(), self.prepared)

    def test_historical_context_pin_and_rehashed_request_need_external_anchors(self):
        for overrides in [dict(expected_pin=self.pin | {'configurationRevision': 2}),
                          dict(expected_run_id='run:other'), dict(expected_request_digest='sha256:' + '0' * 64)]:
            with self.assertRaises(service.IoServiceError): self.parse(**overrides)
        changed = copy.deepcopy(self.prepared); changed['request']['limits']['maxStreamBytes'] -= 1
        changed['requestDigest'] = contracts.request_digest(changed['request'])
        with self.assertRaisesRegex(service.IoServiceError, 'REQUEST_DIGEST'): self.parse(changed)
        class Hash(str):
            def __eq__(self, other): raise AssertionError('digest equality')
        changed = copy.deepcopy(self.prepared); changed['requestDigest'] = Hash(changed['requestDigest'])
        with self.assertRaisesRegex(service.IoServiceError, 'DIGEST'): self.parse(changed)

    def test_prepared_document_corruption_or_extra_fields_refuse(self):
        changed = copy.deepcopy(self.prepared); changed['bundle']['documents']['inputs/authority.json'] = b'{}'
        with self.assertRaises(service.IoServiceError): self.parse(changed)
        changed = copy.deepcopy(self.prepared); changed['configuration'] = json.dumps(self.config, indent=2).encode()
        with self.assertRaisesRegex(service.IoServiceError, 'CANONICAL'): self.parse(changed)
        changed = copy.deepcopy(self.prepared); changed['passed'] = True
        with self.assertRaises(service.IoServiceError): self.parse(changed)

    def test_current_implementation_change_refuses_before_bundle_preparation(self):
        identity = self.pin['implementation'] | {'workerDigest': 'sha256:' + '0' * 64}
        with patch.object(service, '_identities', return_value=identity), \
             patch.object(service, 'prepare_io_run_bundle', side_effect=AssertionError('prepared after drift')):
            with self.assertRaisesRegex(service.IoServiceError, 'PIN_CHANGED'):
                self.configured.prepare_run(program(literal=True), 'run:changed', trusted_descriptors=descriptors(self.selected))

    def test_identity_change_at_request_construction_cannot_publish_run(self):
        original = service.prepare_request
        def changed(*args, **kwargs):
            value = original(*args, **kwargs); value['implementation']['workerDigest'] = 'sha256:' + '0' * 64
            return value
        with patch.object(service, 'prepare_request', side_effect=changed):
            with self.assertRaisesRegex(service.IoServiceError, 'REQUEST_CHANGED'):
                self.configured.prepare_run(program(literal=True), 'run:changed', trusted_descriptors=descriptors(self.selected))

    def test_new_session_snapshot_is_used_and_changes_same_key_request_bytes(self):
        chosen = descriptors(self.selected)
        for descriptor in chosen.values(): descriptor['endpointSession'] = 'session:replacement'
        value = self.configured.prepare_run(program(literal=True), 'run:configured', trusted_descriptors=chosen)
        self.assertEqual(value['request']['context'], self.prepared['request']['context'])
        self.assertNotEqual(value['requestDigest'], self.prepared['requestDigest'])
        self.assertEqual(json.loads(value['bundle']['documents']['inputs/descriptor.json'])['endpointSession'], 'session:replacement')
        with self.assertRaisesRegex(service.IoServiceError, 'REQUEST_DIGEST'): self.parse(value)

    def test_reconstruction_detaches_inputs_outputs_without_sql_or_provider_effects(self):
        config = copy.deepcopy(self.config); document = copy.deepcopy(self.document); chosen = descriptors(self.selected)
        with patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('worker')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            configured = service.ConfiguredIoService(config, document, expected_pin=self.pin)
            config['registrations'].clear(); document['handlers'].clear()
            value = configured.prepare_run(program(literal=True), 'run:configured', trusted_descriptors=chosen)
        self.assertEqual(value, self.prepared)
        value['bundle']['documents'].clear(); chosen.clear()
        self.assertEqual(self.parse(), self.prepared)


class IoConfiguredProcessTests(IoSupervisorProcessTests):
    @classmethod
    def setUpClass(cls):
        document = normalize_installation(installation()); selected = bindings(document)
        config = configuration(document, selected); pin = service.prepare_service_pin(config, document)
        configured = service.ConfiguredIoService(config, document, expected_pin=pin)
        cls.prepared = configured.prepare_run(program(literal=True), 'run:configured-owned', trusted_descriptors=descriptors(selected))
        cls.bundle, cls.request = cls.prepared['bundle'], cls.prepared['request']; cls.context = cls.request['context']

    def root(self, label='root'):
        root = super().root(label)
        parent = Path(os.environ['TMPDIR']) / self._testMethodName
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            contracts.write_file(fd, 'service-configuration.json', self.prepared['configuration'])
            contracts.write_file(fd, 'service-pin.json', self.prepared['servicePin'])
            contracts.write_file(fd, 'service-request-digest.json', canonical(dict(requestDigest=self.prepared['requestDigest'])))
        finally: os.close(fd)
        return root

    def test_configured_owned_group_retains_service_identity_and_replays(self):
        IoSupervisorProcessTests.test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays(self)
        parent = Path(os.environ['TMPDIR']) / self._testMethodName
        self.assertEqual((parent / 'service-configuration.json').read_bytes(), self.prepared['configuration'])
        self.assertEqual((parent / 'service-pin.json').read_bytes(), self.prepared['servicePin'])
