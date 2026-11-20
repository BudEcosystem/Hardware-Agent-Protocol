"""Encoded evidence identity, budget ordering and retained failed writes."""
import copy
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hms import pat_io_trials as trials
from hms import pat_io_configuration_capture as configuration
from hms import resource_topology as graph
from hms.contracts import canonical
from hms.pat_contracts import PatError
from test_resource_topology import topology


class Budget:
    def __init__(self):
        self.events = []
        self.stopped = False

    def check(self):
        self.events.append('check')
        if self.stopped:
            raise PatError('TEST_GROUP_STOPPED')

    def record(self, size):
        self.events.append(('record', size))


class IoEncodingTests(unittest.TestCase):
    def engine(self, configured=False, name='engine'):
        cls = configuration.ConfiguredIoTrialEngine if configured else trials.IoTrialEngine
        engine = object.__new__(cls)
        directory = Path(tempfile.gettempdir()) / self._testMethodName / name
        directory.mkdir(parents=True, mode=0o700)
        engine.record_directory = directory / 'records'
        engine.record_directory.mkdir(mode=0o700)
        engine.records, engine._objects, engine.output_bytes = [], {}, 0
        engine._started = time.monotonic()
        engine._group_budget = Budget()
        if configured:
            engine.configuration_records, engine.configuration_bytes = [], 0
            engine._configuration_cache = {}
            engine._configuration_directory = directory / 'configuration'
            engine._configuration_directory.mkdir(mode=0o700)
        return engine

    def expected(self, engine, kind, value, index=0, profile=None):
        data = canonical(dict(profile=profile or engine._record_profile, kind=kind, value=value))
        return data, dict(path='%06d.json' % index, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def test_base_exact_envelope_reuse_detachment_and_durability(self):
        engine = self.engine()
        value = {'z': [None, True, 3], 'a': 'µ'}
        data, expected = self.expected(engine, 'sample', value)
        with patch.object(trials, 'canonical', wraps=canonical) as encode, \
             patch.object(trials.os, 'fsync', wraps=trials.os.fsync) as sync:
            first = engine._write('sample', value, reuse=True)
            first['path'] = 'caller-mutated'
            second = engine._write('sample', dict(reversed(list(value.items()))), reuse=True)
            self.assertEqual(encode.call_count, 2)
            self.assertEqual(sync.call_count, 1)
        self.assertEqual(second, expected)
        self.assertEqual(engine.records, [expected])
        self.assertEqual(engine.output_bytes, len(data))
        self.assertEqual((engine.record_directory / expected['path']).read_bytes(), data)
        self.assertEqual(engine._group_budget.events, ['check', ('record', len(data)), 'check'])

    def test_configured_writer_encodes_once_and_keeps_both_streams_exact(self):
        engine = self.engine(configured=True)
        engine._record_profile = 'test:inherited-profile'
        data, expected = self.expected(engine, 'sample', {'value': 7})
        with patch.object(configuration, 'canonical', wraps=canonical) as side_encode, \
             patch.object(trials, 'canonical', wraps=canonical) as base_encode:
            self.assertEqual(engine._write('sample', {'value': 7}, reuse=True), expected)
            self.assertEqual(side_encode.call_count, 1)
            self.assertEqual(base_encode.call_count, 0)
        side_data, side_ref = self.expected(engine, 'sample', {'value': 7}, profile=configuration.PROFILE)
        self.assertEqual(engine._configuration_write('sample', {'value': 7}, reuse=True), side_ref)
        self.assertNotEqual(expected['sha256'], side_ref['sha256'])
        self.assertEqual((engine.record_directory / expected['path']).read_bytes(), data)
        self.assertEqual((engine._configuration_directory / side_ref['path']).read_bytes(), side_data)
        self.assertEqual(engine.output_bytes + engine.configuration_bytes, len(data) + len(side_data))
        self.assertEqual(engine._group_budget.events,
                         ['check', ('record', len(data)), 'check', ('record', len(side_data))])

    def test_cached_record_still_checks_group_and_does_not_reserve_again(self):
        engine = self.engine(configured=True)
        ref = engine._write('sample', [1], reuse=True)
        with patch.object(trials, 'MAX_RECORDS', 1):
            self.assertEqual(engine._write('sample', [1], reuse=True), ref)
            engine._group_budget.stopped = True
            with self.assertRaisesRegex(PatError, 'TEST_GROUP_STOPPED'):
                engine._write('sample', [1], reuse=True)
        self.assertEqual(len(engine.records), 1)
        self.assertEqual(engine._group_budget.events, ['check', ('record', ref['bytes']), 'check', 'check'])

    def test_combined_limits_keep_original_precedence_before_clock_check(self):
        engine = self.engine(configured=True)
        engine._configuration_write('side', {'value': 2})
        engine._started -= 61
        for option, value in [('MAX_RECORDS', 1), ('MAX_OUTPUT_BYTES', engine.configuration_bytes)]:
            with self.subTest(option=option), patch.object(trials, option, value):
                with self.assertRaisesRegex(PatError, 'PAT_IO_CONFIGURATION_EVIDENCE_LIMIT'):
                    engine._write('sample', {'value': 1})
        self.assertEqual(engine.records, [])
        self.assertEqual(len(engine._group_budget.events), 2)
        self.assertEqual(list(engine.record_directory.iterdir()), [])

    def test_base_expired_budget_precedes_encoding_and_file_creation(self):
        engine = self.engine()
        engine._started -= 61
        with patch.object(trials, 'canonical', side_effect=AssertionError('encoded after deadline')):
            with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_WALL_LIMIT'):
                engine._write('sample', object())
        self.assertEqual(engine.records, [])
        self.assertEqual(list(engine.record_directory.iterdir()), [])

    def test_exclusive_open_failure_preserves_existing_file_and_group_charge(self):
        engine = self.engine(configured=True)
        path = engine.record_directory / '000000.json'
        path.write_bytes(b'existing retained evidence')
        data, _ = self.expected(engine, 'sample', [1])
        with self.assertRaises(FileExistsError):
            engine._write('sample', [1], reuse=True)
        self.assertEqual(path.read_bytes(), b'existing retained evidence')
        self.assertEqual(engine._group_budget.events, ['check', ('record', len(data))])
        self.assertEqual((engine.records, engine.output_bytes, engine._objects), ([], 0, {}))

    def test_fsync_failure_retains_bytes_without_publishing_reference_or_refund(self):
        engine = self.engine(configured=True)
        data, _ = self.expected(engine, 'sample', [1])
        with patch.object(trials.os, 'fsync', side_effect=OSError('injected sync failure')):
            with self.assertRaisesRegex(OSError, 'injected sync failure'):
                engine._write('sample', [1], reuse=True)
        self.assertEqual((engine.record_directory / '000000.json').read_bytes(), data)
        self.assertEqual(engine._group_budget.events, ['check', ('record', len(data))])
        self.assertEqual((engine.records, engine.output_bytes, engine._objects), ([], 0, {}))

    def test_changed_value_and_nonreusable_write_preserve_original_sequence(self):
        engine = self.engine(configured=True)
        value = {'nested': [1]}
        first = engine._write('sample', value, reuse=True)
        value['nested'][0] = 2
        second = engine._write('sample', value, reuse=True)
        third = engine._write('sample', value, reuse=False)
        self.assertEqual([r['path'] for r in engine.records], ['000000.json', '000001.json', '000002.json'])
        self.assertNotEqual(first['sha256'], second['sha256'])
        self.assertEqual(second['sha256'], third['sha256'])
        self.assertEqual(engine._write('sample', value, reuse=True), second)
        for index, n in enumerate((1, 2, 2)):
            data, expected = self.expected(engine, 'sample', {'nested': [n]}, index)
            self.assertEqual(engine.records[index], expected)
            self.assertEqual((engine.record_directory / expected['path']).read_bytes(), data)

    def test_topology_snapshot_encodes_objects_and_reuses_warm_bytes_and_detaches(self):
        value = topology()
        original = copy.deepcopy(value)
        for carrier in (value, canonical(value)):
            with self.subTest(carrier=type(carrier).__name__), \
                 patch.object(graph, 'canonical', wraps=canonical) as encode:
                result = graph._snapshot(carrier, graph.PROFILE)
                self.assertEqual(encode.call_count, 0 if type(carrier) is bytes else 1)
                self.assertEqual(result, original)
            result['nodes']['pin5']['properties']['electrical']['modes'].clear()
        self.assertEqual(value, original)
        self.assertEqual(graph._snapshot(value, graph.PROFILE), original)
