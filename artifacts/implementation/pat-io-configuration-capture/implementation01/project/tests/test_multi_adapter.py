"""Multiple original simulation routes under one authority; no hardware I/O.

Native fixtures are independently enrolled original C processes. Their external
test-control sockets set synthetic time and count effects; HMS never reads them.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hms.adapter_catalog import AdapterCatalog
from hms.contracts import canonical
from hms.endpoint_binding import ensure_endpoint_schema
from hms.endpoint_wire import Opcode, Operation
from hms.installations import ROLES, legacy_installation, manifest_for, plant_filename
from hms.journal import Context, Journal, JournalError
from hms.registry import Registry, RegistryPolicy
from hms.runtime import Runtime
from hms.simulator import SimulatedPlant
from protocol.serial.frame import Decoder

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'
SNAPSHOT = ROOT / 'artifacts/verification/multi-adapter-design-review'


def installation(name, *, compact=False):
    value = legacy_installation(compact)
    value['adapterId'] = 'test-route:' + name
    value['instances'] = {role: 'sim:' + name + '-' + role for role in ROLES}
    value['resources'] = {role: 'sim-resource:' + name + '-' + role for role in ROLES}
    if compact:
        value['incarnationHex'] = hashlib.sha256(name.encode()).hexdigest()[:32]
    return value


def scenario(config, role):
    instance = config['instances'][role]
    action, arguments = {
        'fan': ('set_level', {'level': 25, 'unit': 'percent'}),
        'focus': ('move_absolute', {'position': 42, 'unit': 'um', 'frame': instance}),
        'inspection': ('inspect', {'recipe': 1, 'partId': 'part:multi-α'}),
    }[role]
    return instance, action, arguments


class NativeEndpoint:
    def __init__(self, config):
        data, digest = manifest_for(config)
        manifest = json.loads(data)
        self.wire, child_wire = socket.socketpair()
        self.control, child_control = socket.socketpair()
        self.control.settimeout(3)
        try:
            self.process = subprocess.Popen([
                str(BINARY), '--test-control-fd', str(child_control.fileno()),
                '--incarnation', config['incarnationHex'], '--manifest', digest,
                '--firmware', manifest['firmwareDigest']], stdin=child_wire, stdout=child_wire,
                stderr=subprocess.PIPE, pass_fds=(child_control.fileno(),))
        finally:
            child_wire.close()
            child_control.close()

    def command(self, opcode, value=0):
        self.control.sendall(struct.pack('>BQ', opcode, value))
        raw = b''
        while len(raw) < 9:
            part = self.control.recv(9 - len(raw))
            if not part:
                raise AssertionError('native fixture closed test-control socket')
            raw += part
        if raw[0] != opcode:
            raise AssertionError(('fixture refused control', opcode, raw.hex()))
        return int.from_bytes(raw[1:], 'big')

    def close(self):
        self.wire.close()
        self.control.close()
        try:
            _, error = self.process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            _, error = self.process.communicate()
        if self.process.returncode != 0:
            raise AssertionError((self.process.returncode, error.decode(errors='replace')))


class MultiHarness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'state'
        self.wall, self.mono = 100000, 1000
        self.owner = Context('multi-owner', 'simulation:multi')
        self.runtime = None
        self.endpoints = {}
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.runtime is not None:
            self.runtime.close()
        for endpoint in self.endpoints.values():
            endpoint.close()

    def open(self, configs=None, *, create=False, online=None):
        if create:
            self.configs = configs
            for config in configs:
                if config['driver'] == 'compact-simulation':
                    self.endpoints[config['adapterId']] = NativeEndpoint(config)
        online = set(self.endpoints) if online is None else set(online)
        self.runtime = Runtime(self.directory, create=create, owner=self.owner if create else None,
            installations=configs, endpoint_fds={key: self.endpoints[key].wire.fileno() for key in online},
            wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        if create:
            self.namespace = self.call('namespace', expiresUnixMs=150000)['token']

    def reopen(self, *, online=None):
        self.runtime.close()
        self.open(online=online)

    def call(self, method, **params):
        return self.runtime.request(self.owner, method, params)

    def prepare(self, config, role='fan', *, key=None, timing=None):
        instance, action, arguments = scenario(config, role)
        return self.call('prepare', instanceId=instance, actionId=action, arguments=arguments,
            operationKey=key or instance, replayNamespace=self.namespace,
            requiredEffect='capability_completion', timing=timing or {
                'notBeforeUnixMs': self.wall, 'latestStartUnixMs': self.wall + 3000,
                'maxRunMs': 1000, 'latestCompletionUnixMs': self.wall + 5000})['request']

    def invoke(self, request):
        return self.call('invoke', request=request)

    def status(self, operation):
        return self.call('operation', operationId=operation['operationId'])

    def advance(self, ms=100, *, tolerate=()):
        self.wall += ms
        self.mono += ms
        for endpoint in self.endpoints.values():
            endpoint.command(1, self.mono)
        try:
            self.runtime.tick()
        except JournalError:
            if not tolerate or set(self.runtime.route_errors) - set(tolerate):
                raise

    def finish(self, operations, *, tolerate=()):
        for _ in range(16):
            self.advance(tolerate=tolerate)
            states = [self.status(op) for op in operations]
            if all(op['executionState'] == 'completed' and not op['resourceClaims'] for op in states):
                return states
        self.fail(str(states))

    def packet_count(self, adapter, opcode=Opcode.OP):
        with self.runtime.journal._mutex:
            rows = self.runtime.journal._db.execute(
                "SELECT wire FROM ep_packets WHERE adapter=? AND direction='tx'", (adapter,)).fetchall()
        count = 0
        for row in rows:
            decoder = Decoder()
            frames = []
            for byte in row[0]:
                event = decoder.feed(byte)
                if event and event[0] == 'frame':
                    frames.append(event[1])
            self.assertEqual(len(frames), 1)
            count += frames[0].payload[1] == opcode
        return count


class MultiLocalTests(MultiHarness):
    def test_two_plants_keep_aliases_effects_and_historical_results_separate(self):
        first, second = installation('local-a'), installation('local-b')
        self.open([first, second], create=True)
        requests = [self.prepare(config, role) for config in (first, second) for role in ROLES]
        operations = [self.invoke(request) for request in requests]
        results = self.finish(operations)
        for index, config in enumerate((first, second)):
            plant = self.runtime.adapters[config['adapterId']].plant
            for role in ROLES:
                self.assertEqual(plant.observe(config['instances'][role])['effectCount'], 1)
            self.assertEqual(results[index * 3 + 1]['result']['output']['frame'], config['instances']['focus'])
        instance = first['instances']['fan']
        binding, _ = self.runtime.registry._binding(instance)
        binding.update(generation='test-binding:changed', adapterId=second['adapterId'])
        self.runtime.registry.bind(self.owner, canonical(binding))
        self.reopen()
        self.assertEqual(self.invoke(requests[0]), results[0])
        self.assertEqual(self.status(operations[0]), results[0])
        self.assertIsNone(self.call('describe', instanceId=instance)['presence'])
        historical = self.runtime.work_items(first['adapterId'], ('completed',), limit=1)
        self.assertEqual(historical[0]['id'], operations[0]['operationId'])
        other = self.runtime.work_items(second['adapterId'], ('completed',))
        self.assertNotIn(operations[0]['operationId'], {op['id'] for op in other})

    def test_shared_resource_conflict_and_fence_floor_remain_global(self):
        first, second = installation('shared-a'), installation('shared-b')
        second['resources']['fan'] = first['resources']['fan']
        self.open([first, second], create=True)
        op = self.invoke(self.prepare(first))
        first_fence = op['resourceClaims'][0]['fence']
        request = self.prepare(second)
        with self.assertRaisesRegex(JournalError, 'RESOURCE_BUSY'):
            self.invoke(request)
        self.finish([op])
        next_op = self.invoke(request)
        self.assertGreater(next_op['resourceClaims'][0]['fence'], first_fence)
        self.finish([next_op])
        for config in (first, second):
            self.assertEqual(self.runtime.adapters[config['adapterId']].plant.observe(
                config['instances']['fan'])['effectCount'], 1)

    def test_route_filter_precedes_limit_and_claim_filter(self):
        first, second = installation('queue-a'), installation('queue-b')
        self.open([first, second], create=True)
        for index in range(65):
            op = self.invoke(self.prepare(first, key='canceled:' + str(index)))
            self.call('cancel', operationId=op['operationId'])
        final = self.invoke(self.prepare(second))
        self.call('cancel', operationId=final['operationId'])
        rows = self.runtime.work_items(second['adapterId'], ('canceled',), limit=1)
        self.assertEqual([row['id'] for row in rows], [final['operationId']])
        active = self.invoke(self.prepare(second, key='active'))
        self.assertEqual([row['id'] for row in self.runtime.work_items(
            second['adapterId'], ('accepted', 'canceled'), limit=1, claims_only=True)],
            [active['operationId']])
        self.finish([active])

    def test_missing_plant_is_route_offline_and_never_recreated(self):
        first, second = installation('missing-a'), installation('missing-b')
        self.open([first, second], create=True)
        self.runtime.close()
        path = self.directory / plant_filename(first)
        path.unlink()
        self.open()
        self.assertEqual(self.runtime.route_errors[first['adapterId']], 'MISSING_SIMULATED_PLANT')
        self.assertFalse(path.exists())
        with self.assertRaises(JournalError):
            self.prepare(first)
        healthy = self.invoke(self.prepare(second))
        self.finish([healthy], tolerate=(first['adapterId'],))
        self.assertFalse(path.exists())

    def test_local_result_rejects_receipt_digest_conflict(self):
        config = installation('receipt')
        self.open([config], create=True)
        op = self.invoke(self.prepare(config))
        self.finish([op])
        plant = self.runtime.adapters[config['adapterId']].plant
        plant.db.execute('UPDATE receipts SET digest=? WHERE id=?', ('sha256:' + '0' * 64, op['operationId']))
        with self.assertRaisesRegex(JournalError, 'SIMULATOR_RECEIPT_CONFLICT'):
            self.status(op)

    def test_corrupt_plant_only_disables_its_route_and_preserves_store_bytes(self):
        first, second = installation('corrupt-a-healthy'), installation('corrupt-b-broken')
        self.open([first, second], create=True)
        self.runtime.close()
        path = self.directory / plant_filename(second)
        path.write_bytes(b'')
        with self.assertRaisesRegex(JournalError, 'INVALID_SIMULATED_PLANT') as caught:
            SimulatedPlant(path, installation=second)
        self.assertIsInstance(caught.exception.__cause__, sqlite3.Error)
        self.open()
        self.assertEqual(self.runtime.route_errors, {second['adapterId']: 'INVALID_SIMULATED_PLANT'})
        self.assertEqual(path.read_bytes(), b'')
        healthy = self.invoke(self.prepare(first))
        self.finish([healthy], tolerate=(second['adapterId'],))
        self.assertEqual(path.read_bytes(), b'')

    def test_grants_do_not_expand_with_another_installed_route(self):
        first, second = installation('auth-a'), installation('auth-b')
        self.open([first, second], create=True)
        user = Context('limited-user', self.owner.deployment)
        self.runtime.registry.grant(self.owner, user.principal, first['instances']['fan'], 'read')
        found = self.runtime.request(user, 'discover', {'limit': 1})
        self.assertEqual([item['instanceId'] for item in found['items']], [first['instances']['fan']])
        self.assertIsNone(found['cursor'])
        op = self.invoke(self.prepare(second))
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.runtime.request(user, 'operation', {'operationId': op['operationId']})

    def test_background_route_failure_does_not_stop_other_worker(self):
        first, second = installation('worker-a-failed'), installation('worker-b-healthy')
        self.open([first, second], create=True)
        op = self.invoke(self.prepare(second))
        failed, running, completed = threading.Event(), threading.Event(), threading.Event()
        healthy = self.runtime.adapters[second['adapterId']]
        original_tick = healthy.tick

        def fail_route():
            failed.set()
            raise JournalError('TEST_ROUTE_FAILURE')

        def observe_healthy_tick():
            original_tick()
            with self.runtime.journal._mutex:
                current = self.runtime.journal._operation(op['operationId'])
                if current['state'] == 'running':
                    running.set()
                if current['state'] == 'completed' and not current['claims']:
                    completed.set()

        self.runtime.adapters[first['adapterId']].tick = fail_route
        healthy.tick = observe_healthy_tick
        self.runtime.start()
        try:
            self.assertTrue(failed.wait(3))
            self.assertTrue(running.wait(3))
            self.wall += 100
            self.mono += 100
            self.assertTrue(completed.wait(3))
            self.assertEqual(self.status(op)['executionState'], 'completed')
            self.assertEqual(self.runtime.route_errors, {first['adapterId']: 'TEST_ROUTE_FAILURE'})
        finally:
            self.runtime.close()

    def test_uninstalled_historical_route_rejects_queued_work_but_keeps_uncertainty(self):
        config = installation('orphan-history')
        self.open([config], create=True)
        registry = self.runtime.registry
        adapter_id = 'test-route:no-longer-installed'
        session = self.runtime.adapters[config['adapterId']].plant.session
        # Recreate retained admissions from a former owner policy that did not
        # require currently installed support. No real effect is performed.
        with patch.object(self.runtime.policy, '_installed_support', None):
            operations = []
            for role in ('fan', 'focus'):
                instance = config['instances'][role]
                binding, _ = registry._binding(instance)
                binding.update(generation='historical:missing-' + role, adapterId=adapter_id)
                registry.bind(self.owner, canonical(binding))
                registry.report_presence(instance, adapter_id=adapter_id, endpoint_session=session, ttl_ms=3000)
                stream = 'historical:ready-' + role
                registry.start_stream(instance, 'ready', adapter_id=adapter_id, endpoint_session=session,
                    binding_generation=binding['generation'], stream_epoch=stream)
                registry.report_observation(instance, 'ready', adapter_id=adapter_id, endpoint_session=session,
                    binding_generation=binding['generation'], stream_epoch=stream, sequence=1,
                    value=True, evidence_kind='simulation', quality='valid',
                    acquisition={'clockDomain': 'test-monotonic', 'clockEpoch': registry.receipt_epoch,
                                 'ticksMs': self.mono},
                    acquisition_latency_bound_ms=0, clock_uncertainty_ms=0,
                    measurement_uncertainty={'absolute': 0, 'unit': '1', 'method': 'synthetic_setup'})
                operations.append(self.invoke(self.prepare(config, role)))
            queued, handed_off = operations
            ticket = self.runtime.journal.claim_dispatch(handed_off['operationId'])
            self.runtime.journal.mark_unknown(ticket, 'historical_handoff_unresolved')
        self.runtime.tick()
        rejected = self.status(queued)
        self.assertEqual(rejected['executionState'], 'rejected_before_dispatch')
        self.assertFalse(rejected['mayHaveActed'])
        self.assertEqual(rejected['resourceClaims'], [])
        unknown = self.status(handed_off)
        self.assertEqual(unknown['executionState'], 'outcome_unknown')
        self.assertTrue(unknown['resourceClaims'])
        self.assertIsNone(unknown['result'])
        plant = self.runtime.adapters[config['adapterId']].plant
        for operation in operations:
            self.assertIsNone(plant.receipt(operation['operationId']))
        for role in ('fan', 'focus'):
            self.assertEqual(plant.observe(config['instances'][role])['effectCount'], 0)
        self.assertEqual(self.invoke(self.prepare(config, 'inspection'))['executionState'], 'accepted')

    def test_invalid_last_snapshot_observation_rolls_back_all_ingress_and_stream_cache(self):
        config = installation('atomic-snapshot')
        self.open([config], create=True)
        adapter = self.runtime.adapters[config['adapterId']]
        tables = ('reg_presence', 'reg_endpoint_sessions', 'reg_session_history',
                  'reg_streams', 'reg_stream_history', 'reg_observations')

        def rows():
            return {table: [tuple(row) for row in self.runtime.journal._db.execute('SELECT * FROM ' + table)]
                    for table in tables}

        before, streams, sampled = rows(), copy.deepcopy(adapter._streams), adapter._last_sample
        original = self.runtime.registry.report_adapter_snapshot

        def invalid_last(adapter_id, **groups):
            groups = copy.deepcopy(groups)
            groups['observations'][-1]['value'] = 'invalid-ready-value'
            return original(adapter_id, **groups)

        self.wall += 100
        self.mono += 100
        with patch.object(adapter.plant, 'session', 'test-session:rejected-snapshot'):
            with patch.object(self.runtime.registry, 'report_adapter_snapshot', invalid_last):
                with self.assertRaisesRegex(JournalError, 'ARGUMENT_SCHEMA_MISMATCH'):
                    adapter.refresh(force=True)
        self.assertEqual(rows(), before)
        self.assertEqual(adapter._streams, streams)
        self.assertEqual(adapter._last_sample, sampled)
        adapter.refresh(force=True)
        self.assertEqual(set(adapter._streams), set(streams))
        for key, (_epoch, sequence) in streams.items():
            self.assertEqual(adapter._streams[key][1], sequence + 1)

    def test_local_observation_age_includes_sampling_and_publication_delay(self):
        config = installation('sample-delay')
        self.open([config], create=True)
        adapter = self.runtime.adapters[config['adapterId']]
        original = adapter.plant.observe
        acquired = self.mono

        def delayed_observe(instance):
            sample = original(instance)
            self.mono += 25
            self.wall += 25
            return sample

        with patch.object(adapter.plant, 'observe', delayed_observe):
            adapter.refresh(force=True)
        for index, role in enumerate(ROLES):
            observation = self.call('observe', instanceId=config['instances'][role], property='value')
            self.assertEqual(observation['acquisition']['ticksMs'], acquired + index * 25)
            self.assertEqual(observation['acquisitionLatencyBoundMs'], 75 - index * 25)
            self.assertEqual(observation['ageUpperBoundMs'], 75 - index * 25)
        with self.assertRaisesRegex(JournalError, 'OBSERVATION_STALE'):
            self.call('observe', instanceId=config['instances']['fan'], property='value', maxAgeMs=0)


class MultiCompactTests(MultiHarness):
    def test_mixed_local_and_two_native_routes_execute_all_three_scenarios(self):
        local = installation('mixed-local')
        first, second = installation('mixed-c1', compact=True), installation('mixed-c2', compact=True)
        self.open([local, first, second], create=True)
        self.assertEqual(self.runtime.route_errors, {})
        self.endpoints[first['adapterId']].command(7, 10)
        self.endpoints[second['adapterId']].command(7, 20)
        operations = [self.invoke(self.prepare(config, role)) for config in (local, first, second) for role in ROLES]
        results = self.finish(operations)
        self.assertEqual(results[2]['result']['output']['count'], 1)
        self.assertEqual(results[5]['result']['output']['value'], 11)
        self.assertEqual(results[8]['result']['output']['value'], 21)
        for config in (first, second):
            adapter = self.runtime.adapters[config['adapterId']]
            self.assertEqual(adapter._state()['call'], 3)
            self.assertEqual(adapter._state()['fences'][:3], [1, 1, 1])
            self.assertEqual(self.packet_count(config['adapterId']), 3)
            self.assertEqual(self.endpoints[config['adapterId']].command(4), 3)
            self.assertEqual(self.endpoints[config['adapterId']].command(5), 3)
            rows = self.runtime.journal._db.execute('SELECT payload,mapping FROM ep_commands WHERE adapter=?',
                                                   (config['adapterId'],)).fetchall()
            for row in rows:
                mapping = json.loads(row['mapping'])
                self.assertIn(mapping['intent']['instanceId'], config['instances'].values())
                self.assertEqual(Operation.parse(row['payload']).reference.intent_digest.hex(),
                                 mapping['intentDigest'][7:])
            observed = self.call('observe', instanceId=config['instances']['focus'], property='value')
            self.assertEqual(observed['value'], 42)
            self.assertEqual(observed['frame'], config['instances']['focus'])
        self.assertNotEqual(self.runtime.adapters[first['adapterId']]._state()['desired']['digest'],
                            self.runtime.adapters[second['adapterId']]._state()['desired']['digest'])

    def test_native_boot_fault_only_invalidates_its_route(self):
        first, second = installation('fault-a', compact=True), installation('fault-b', compact=True)
        self.open([first, second], create=True)
        first_op, second_op = [self.invoke(self.prepare(config)) for config in (first, second)]
        self.runtime.tick()
        self.endpoints[first['adapterId']].command(2, 43)
        self.advance(10, tolerate=(first['adapterId'],))
        self.assertIn(first['adapterId'], self.runtime.route_errors)
        self.assertNotIn(second['adapterId'], self.runtime.route_errors)
        self.assertEqual(self.status(first_op)['executionState'], 'outcome_unknown')
        self.assertTrue(self.status(first_op)['resourceClaims'])
        self.assertNotEqual(self.status(second_op)['executionState'], 'outcome_unknown')
        self.finish([second_op], tolerate=(first['adapterId'],))
        self.assertEqual(self.packet_count(first['adapterId']), 1)
        self.assertEqual(self.packet_count(second['adapterId']), 1)
        self.assertEqual(self.endpoints[second['adapterId']].command(5), 1)

    def test_offline_subset_preserves_replay_results_and_unknown_claims(self):
        first, second = installation('offline-a', compact=True), installation('offline-b', compact=True)
        self.open([first, second], create=True)
        request = self.prepare(first)
        completed = self.invoke(request)
        saved = self.finish([completed])[0]
        pending = self.invoke(self.prepare(first, 'focus'))
        self.runtime.tick()
        payload = bytes(self.runtime.adapters[first['adapterId']]._row(pending['operationId'])['payload'])
        self.reopen(online=(second['adapterId'],))
        self.assertEqual(self.status(completed), saved)
        self.assertEqual(self.invoke(request), saved)
        unknown = self.status(pending)
        self.assertEqual(unknown['executionState'], 'outcome_unknown')
        self.assertTrue(unknown['resourceClaims'])
        self.assertEqual(self.runtime.adapters[first['adapterId']]._row(pending['operationId'])['payload'], payload)
        with self.assertRaises(JournalError):
            self.prepare(first, 'inspection')
        healthy = self.invoke(self.prepare(second))
        self.finish([healthy], tolerate=(first['adapterId'],))
        self.assertEqual(self.packet_count(first['adapterId']), 2)
        self.assertEqual(self.packet_count(second['adapterId']), 1)

    def test_future_queued_operation_does_not_starve_eligible_compact_work(self):
        config = installation('future', compact=True)
        self.open([config], create=True)
        future = self.invoke(self.prepare(config, 'focus', timing={
            'notBeforeUnixMs': self.wall + 1000, 'latestStartUnixMs': self.wall + 3000,
            'maxRunMs': 1000, 'latestCompletionUnixMs': self.wall + 5000}))
        eligible = self.invoke(self.prepare(config))
        self.runtime.tick()
        self.assertEqual(self.status(future)['executionState'], 'accepted')
        self.assertEqual(self.status(eligible)['executionState'], 'dispatching')
        self.assertEqual(self.packet_count(config['adapterId']), 1)
        self.finish([eligible])
        self.assertEqual(self.status(future)['executionState'], 'accepted')
        self.finish([future])
        self.assertEqual(self.packet_count(config['adapterId']), 2)

    def test_swapped_native_fds_do_not_enroll_or_fall_back(self):
        local = installation('swap-local')
        first, second = installation('swap-a', compact=True), installation('swap-b', compact=True)
        for config in (first, second):
            self.endpoints[config['adapterId']] = NativeEndpoint(config)
        self.runtime = Runtime(self.directory, create=True, owner=self.owner, installations=[local, first, second],
            endpoint_fds={first['adapterId']: self.endpoints[second['adapterId']].wire.fileno(),
                          second['adapterId']: self.endpoints[first['adapterId']].wire.fileno()},
            wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.namespace = self.call('namespace', expiresUnixMs=150000)['token']
        self.assertEqual(set(self.runtime.route_errors), {first['adapterId'], second['adapterId']})
        for config in (first, second):
            self.assertFalse(self.runtime.adapters[config['adapterId']]._state()['installed'])
            self.assertEqual(self.packet_count(config['adapterId']), 0)
            self.assertEqual(self.endpoints[config['adapterId']].command(4), 0)
        self.finish([self.invoke(self.prepare(local))], tolerate=(first['adapterId'], second['adapterId']))


class InstallationBoundaryTests(MultiHarness):
    def test_duplicate_descriptors_and_duplicate_open_streams_fail_before_state_creation(self):
        first, second = installation('duplicate-a', compact=True), installation('duplicate-b', compact=True)
        duplicate_instance = copy.deepcopy(second)
        duplicate_instance['instances']['fan'] = first['instances']['fan']
        duplicate_incarnation = copy.deepcopy(second)
        duplicate_incarnation['incarnationHex'] = first['incarnationHex']
        cases = [([first, first], 'DUPLICATE_ADAPTER_INSTALLATION'),
                 ([first, duplicate_instance], 'DUPLICATE_INSTALLED_INSTANCE'),
                 ([first, duplicate_incarnation], 'DUPLICATE_INSTALLED_INCARNATION')]
        for configs, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(JournalError, code):
                Runtime(self.directory, create=True, owner=self.owner, installations=configs)
            self.assertFalse(self.directory.exists())
        wire, peer = socket.socketpair()
        try:
            duplicate = os.dup(wire.fileno())
            try:
                with self.assertRaisesRegex(JournalError, 'DUPLICATE_ENDPOINT_STREAM'):
                    Runtime(self.directory, create=True, owner=self.owner, installations=[first, second],
                            endpoint_fds={first['adapterId']: wire.fileno(), second['adapterId']: duplicate})
                self.assertFalse(self.directory.exists())
            finally:
                os.close(duplicate)
        finally:
            wire.close()
            peer.close()

    def test_changed_descriptor_is_rejected_on_reopen(self):
        config = installation('immutable')
        self.open([config], create=True)
        self.runtime.close()
        changed = copy.deepcopy(config)
        changed['resources']['fan'] = 'sim-resource:replacement'
        with self.assertRaisesRegex(JournalError, 'INSTALLATION_DESCRIPTOR_MISMATCH'):
            Runtime(self.directory, installations=[changed], wall_clock_ms=lambda: self.wall,
                    monotonic_ms=lambda: self.mono)
        self.open()
        self.finish([self.invoke(self.prepare(config))])

    def test_interrupted_initial_provisioning_resumes_without_replacing_plants(self):
        first, second = installation('resume-a'), installation('resume-b')
        original = AdapterCatalog.provision_local_registry

        def interrupted(catalog, config):
            original(catalog, config)
            if config['adapterId'] == second['adapterId']:
                raise SystemExit('synthetic crash after registry provisioning')

        with patch.object(AdapterCatalog, 'provision_local_registry', interrupted):
            with self.assertRaisesRegex(SystemExit, 'synthetic crash'):
                Runtime(self.directory, create=True, owner=self.owner, installations=[first, second],
                        wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        sessions = {}
        for config in (first, second):
            with sqlite3.connect(self.directory / plant_filename(config)) as db:
                sessions[config['adapterId']] = db.execute("SELECT value FROM meta WHERE key='session'").fetchone()[0]
        self.open()
        self.namespace = self.call('namespace', expiresUnixMs=150000)['token']
        self.assertEqual(self.runtime.route_errors, {})
        self.assertTrue(all(self.runtime.catalog.ready.values()))
        for config in (first, second):
            self.assertEqual(self.runtime.adapters[config['adapterId']].plant.session, sessions[config['adapterId']])
        self.finish([self.invoke(self.prepare(config)) for config in (first, second)])

    def test_generated_plant_paths_and_sidecars_reject_symlinks(self):
        config = installation('protected-path')
        self.open([config], create=True)
        self.runtime.close()
        outside = Path(self.temp.name) / 'outside'
        outside.write_bytes(b'external-marker')
        base = self.directory / plant_filename(config)
        for suffix in ('', '.owner', '-journal', '-wal', '-shm'):
            path = Path(str(base) + suffix)
            previous = path.read_bytes() if path.exists() else None
            if path.exists():
                path.unlink()
            path.symlink_to(outside)
            try:
                with self.subTest(suffix=suffix), self.assertRaisesRegex(JournalError, 'UNSAFE_STATE_FILE'):
                    Runtime(self.directory, wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
                self.assertEqual(outside.read_bytes(), b'external-marker')
            finally:
                path.unlink()
                if previous is not None:
                    path.write_bytes(previous)
                    path.chmod(0o600)

    def test_legacy_plant_adoption_requires_exact_descriptor_and_inventory(self):
        path = Path(self.temp.name) / 'legacy-plant.db'
        plant = SimulatedPlant(path, create=True)
        plant.close()
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM meta WHERE key IN ('installation','installation_digest')")
        custom = installation('not-legacy')
        with self.assertRaisesRegex(JournalError, 'SIMULATOR_INSTALLATION_MISMATCH'):
            SimulatedPlant(path, installation=custom)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meta WHERE key='installation'").fetchone()[0], 0)
        plant = SimulatedPlant(path)
        self.assertEqual(json.loads(plant.db.execute("SELECT value FROM meta WHERE key='installation'").fetchone()[0]),
                         legacy_installation())
        plant.close()
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO devices VALUES ('sim:unexpected', '0', 0)")
        with self.assertRaisesRegex(JournalError, 'SIMULATOR_DEVICE_INVENTORY_MISMATCH'):
            SimulatedPlant(path)

    def test_monotonic_sample_compare_and_publication_are_serialized(self):
        sampled, release, contender = threading.Event(), threading.Event(), threading.Event()
        newer_sampled = threading.Event()
        lock = threading.RLock()

        class ObservedMutex:
            def __enter__(self):
                if threading.current_thread().name == 'newer-sample':
                    contender.set()
                lock.acquire()

            def __exit__(self, *_args):
                lock.release()

        def clock():
            if threading.current_thread().name == 'older-sample':
                sampled.set()
                if not release.wait(3):
                    raise AssertionError('sample gate timed out')
                return 1000
            newer_sampled.set()
            return 1100

        registry = Registry.__new__(Registry)
        registry.journal = SimpleNamespace(_mutex=ObservedMutex())
        registry.monotonic_ms, registry._last_monotonic = clock, 0
        registry._monotonic_invalid = False
        results = {}

        def worker(name):
            try:
                results[name] = registry._monotonic()
            except Exception as error:
                results[name] = getattr(error, 'code', type(error).__name__)

        older = threading.Thread(target=worker, args=('older',), name='older-sample')
        newer = threading.Thread(target=worker, args=('newer',), name='newer-sample')
        older.start()
        try:
            self.assertTrue(sampled.wait(2))
            newer.start()
            self.assertTrue(contender.wait(2))
            self.assertFalse(newer_sampled.is_set())
        finally:
            release.set()
            older.join(3)
            if newer.ident is not None:
                newer.join(3)
        self.assertFalse(older.is_alive() or newer.is_alive())
        self.assertEqual(results, {'older': 1000, 'newer': 1100})
        self.assertFalse(registry._monotonic_invalid)


class LegacyMigrationTests(MultiHarness):
    def test_frozen_legacy_compact_store_migrates_exact_packets_receipts_and_counters(self):
        config = legacy_installation(True)
        endpoint = NativeEndpoint(config)
        self.endpoints[config['adapterId']] = endpoint
        # Execute the retained pre-route owner, binding, registry and transport
        # modules, rather than fabricating old SQL rows with the new runtime.
        # Shared contract/schema utilities remain the current unchanged files.
        script = r'''
import hashlib, importlib.util, json, socket, struct, sys
from pathlib import Path
root, snapshot, directory = map(Path, sys.argv[1:4])
wire_fd, control_fd = map(int, sys.argv[4:6])
sys.path.insert(0, str(root))
import hms
review = json.loads((snapshot / 'review.json').read_text())
digests = {entry['path']: entry['sha256'] for entry in review['inputs']}
for name in ('journal', 'registry', 'demo', 'endpoint_transport', 'state_path',
             'simulator', 'endpoint_binding', 'runtime'):
    path = snapshot / 'sources/hms' / (name + '.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digests['hms/' + name + '.py']
    spec = importlib.util.spec_from_file_location('hms.' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['hms.' + name] = module
    spec.loader.exec_module(module)
from hms.journal import Context
from hms.runtime import Runtime
wall, mono = 100000, 1000
owner = Context('legacy-owner', 'simulation:compact')
control = socket.socket(fileno=control_fd)
control.settimeout(3)
runtime = Runtime(directory, create=True, owner=owner, endpoint_fd=wire_fd,
                  wall_clock_ms=lambda: wall, monotonic_ms=lambda: mono)
try:
    namespace = runtime.request(owner, 'namespace', {'expiresUnixMs': 150000})['token']
    request = runtime.request(owner, 'prepare', {
        'instanceId': 'sim:home-fan', 'actionId': 'set_level',
        'arguments': {'level': 25, 'unit': 'percent'}, 'operationKey': 'legacy:one',
        'replayNamespace': namespace, 'requiredEffect': 'capability_completion',
        'timing': {'notBeforeUnixMs': wall, 'latestStartUnixMs': wall+3000,
                   'maxRunMs': 1000, 'latestCompletionUnixMs': wall+5000}})['request']
    op = runtime.request(owner, 'invoke', {'request': request})
    runtime.tick()
    for _ in range(8):
        wall += 100; mono += 100
        control.sendall(struct.pack('>BQ', 1, mono))
        reply = b''
        while len(reply) < 9:
            data = control.recv(9-len(reply))
            assert data
            reply += data
        assert reply == struct.pack('>BQ', 1, mono)
        runtime.tick()
        status = runtime.request(owner, 'operation', {'operationId': op['operationId']})
        if status['executionState'] == 'completed' and not status['resourceClaims']:
            break
    else:
        raise AssertionError(status)
    print(json.dumps({'request': request, 'status': status, 'wall': wall, 'mono': mono}))
finally:
    runtime.close()
    control.close()
'''
        generated = subprocess.run([sys.executable, '-c', script, str(ROOT), str(SNAPSHOT),
            str(self.directory), str(endpoint.wire.fileno()), str(endpoint.control.fileno())],
            pass_fds=(endpoint.wire.fileno(), endpoint.control.fileno()), capture_output=True,
            text=True, timeout=30)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        saved = json.loads(generated.stdout)
        self.wall, self.mono = saved['wall'], saved['mono']
        with sqlite3.connect(self.directory / 'authority.db') as db:
            before_state = db.execute('SELECT singleton,document FROM ep_state').fetchall()
            before_commands = db.execute('SELECT rowid,* FROM ep_commands ORDER BY rowid').fetchall()
            before_packets = db.execute('SELECT * FROM ep_packets ORDER BY id').fetchall()
            self.assertNotIn('adapter', {row[1] for row in db.execute('PRAGMA table_info(ep_commands)')})
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='rt_adapters'").fetchone())
        policy = RegistryPolicy()
        journal = Journal(self.directory / 'authority.db', policy, clock_ms=lambda: self.wall)
        try:
            registry = Registry(journal, monotonic_ms=lambda: self.mono)
            policy.attach(registry)
            catalog = AdapterCatalog(journal, registry)
            ensure_endpoint_schema(journal)
            self.assertEqual(catalog.installations, [config])
            self.assertEqual([tuple(row) for row in journal._db.execute(
                'SELECT singleton,document FROM ep_state WHERE adapter=?', (config['adapterId'],))], before_state)
            self.assertEqual([tuple(row) for row in journal._db.execute(
                'SELECT rowid,operation_id,payload,tx_sequence,mapping,receipt,retired,retire_intent,result '
                'FROM ep_commands WHERE adapter=? ORDER BY rowid', (config['adapterId'],))], before_commands)
            self.assertEqual([tuple(row) for row in journal._db.execute(
                'SELECT id,direction,boot,sequence,wire FROM ep_packets WHERE adapter=? ORDER BY id',
                (config['adapterId'],))], before_packets)
        finally:
            journal.close()
        self.owner = Context('legacy-owner', 'simulation:compact')
        self.runtime = Runtime(self.directory, endpoint_fd=endpoint.wire.fileno(),
                               wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.assertEqual(self.status(saved['status']), saved['status'])
        self.assertEqual(self.invoke(saved['request']), saved['status'])
        self.assertEqual(self.packet_count(config['adapterId']), 1)
        self.assertEqual(endpoint.command(4), 1)
        self.assertEqual(endpoint.command(5), 1)


if __name__ == '__main__':
    unittest.main()
