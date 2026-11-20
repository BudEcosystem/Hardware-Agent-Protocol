"""Immutable snapshot reuse preserves input distinctions and current checks."""
from collections import OrderedDict
import copy
import json
import unittest
from unittest.mock import patch

from hms import resource_topology as graph
from hms import synthetic_io_installation as installation_module
from hms.contracts import ContractError, canonical
from hms.journal import JournalError
from test_io_synthetic_provider import installation
from test_resource_schema_memo import CountingValidator
from test_resource_topology import topology, generations


class SnapshotReuseTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(graph, '_SCHEMA_MEMO', OrderedDict()); p.start(); self.addCleanup(p.stop)
        self.validator = CountingValidator(graph._VALIDATORS[graph.PROFILE])
        validators = dict(graph._VALIDATORS); validators[graph.PROFILE] = self.validator
        p = patch.object(graph, '_VALIDATORS', validators); p.start(); self.addCleanup(p.stop)

    def test_warm_canonical_bytes_return_detached_tree_without_parse_or_copy_hooks(self):
        value = topology(); raw = canonical(value); expected = graph._snapshot(raw, graph.PROFILE)
        with patch.object(graph, 'canonical', side_effect=AssertionError('warm encoding')), \
             patch.object(graph, 'parse_json', side_effect=AssertionError('warm parse')), \
             patch('copy.deepcopy', side_effect=AssertionError('copy hook')), \
             patch('pathlib.Path.read_bytes', side_effect=AssertionError('file')), \
             patch('sqlite3.connect', side_effect=AssertionError('authority')), \
             patch('time.monotonic', side_effect=AssertionError('clock')):
            first = graph._snapshot(raw, graph.PROFILE)
            first['nodes']['pin5']['properties']['electrical']['modes'].clear()
            self.assertEqual(graph._snapshot(raw, graph.PROFILE), expected)
        self.assertEqual(self.validator.calls, 1)
        self.assertEqual(canonical(value), raw)

    def test_warm_objects_keep_canonical_bound_and_original_type_check_before_lookup(self):
        value = topology(); expected = graph._snapshot(value, graph.PROFILE)
        with patch.object(graph, 'canonical', wraps=canonical) as encode, \
             patch.object(graph, '_strict_tree', wraps=graph._strict_tree) as strict, \
             patch.object(graph, 'parse_json', side_effect=AssertionError('warm parse')):
            self.assertEqual(graph._snapshot(value, graph.PROFILE), expected)
            self.assertEqual(encode.call_count, 1)
            self.assertGreater(strict.call_count, 1)
        value['nodes']['pin5']['properties']['electrical']['nominalMilliVolt'] = 3300.0
        with patch.object(graph, '_cached_snapshot', side_effect=AssertionError('float reached memo')):
            with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_INVALID_SCALAR'):
                graph._snapshot(value, graph.PROFILE)

    def test_noncanonical_bytes_still_parse_and_check_before_schema_reuse(self):
        value = topology(); expected = graph._snapshot(value, graph.PROFILE)
        raw = json.dumps(value, indent=2).encode()
        self.assertNotEqual(raw, canonical(value))
        with patch.object(graph, 'parse_json', wraps=graph.parse_json) as parse, \
             patch.object(graph, 'canonical', wraps=canonical) as encode:
            self.assertEqual(graph._snapshot(raw, graph.PROFILE), expected)
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(encode.call_count, 1)
        self.assertEqual(self.validator.calls, 1)
        self.assertEqual(len(graph._SCHEMA_MEMO), 1)

    def test_oversized_bytes_refuse_before_memo_key_lookup(self):
        graph._snapshot(topology(), graph.PROFILE)
        with patch.object(graph, '_cached_snapshot', side_effect=AssertionError('unbounded key')):
            with self.assertRaises(ContractError):
                graph._snapshot(b' ' * 65537, graph.PROFILE)

    def test_validator_replacement_refuses_warm_canonical_carrier(self):
        raw = canonical(topology()); graph._snapshot(raw, graph.PROFILE)
        class Reject:
            def iter_errors(self, value): return iter([object()])
        graph._VALIDATORS[graph.PROFILE] = Reject()
        with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_INVALID_DOCUMENT'):
            graph._snapshot(raw, graph.PROFILE)

    def test_validator_replaced_during_validation_does_not_publish_snapshot(self):
        raw = canonical(topology()); original = self.validator.original
        class Reject:
            def iter_errors(self, value): return iter([object()])
        class Swap:
            def iter_errors(self, value):
                graph._VALIDATORS[graph.PROFILE] = Reject()
                return original.iter_errors(value)
        graph._VALIDATORS[graph.PROFILE] = Swap()
        graph._snapshot(raw, graph.PROFILE)
        self.assertEqual(len(graph._SCHEMA_MEMO), 0)
        with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_INVALID_DOCUMENT'):
            graph._snapshot(raw, graph.PROFILE)

    def test_frozen_entry_capacity_eviction_and_no_mutable_tree_references(self):
        raw = []
        for i in range(9):
            value = topology(); value['topologyId'] = 'snapshot:' + str(i)
            raw.append(canonical(value)); graph._snapshot(raw[-1], graph.PROFILE)
        self.assertEqual(len(graph._SCHEMA_MEMO), 8)
        self.assertLessEqual(sum(len(k[1]) for k in graph._SCHEMA_MEMO), 8 * 65536)
        pending = [entry[1] for entry in graph._SCHEMA_MEMO.values()]
        while pending:
            item = pending.pop()
            self.assertIn(type(item), (tuple, str, int, bool, type(None)))
            if type(item) is tuple: pending.extend(item)
        with patch.object(graph, 'parse_json', wraps=graph.parse_json) as parse:
            self.assertEqual(graph._snapshot(raw[0], graph.PROFILE)['topologyId'], 'snapshot:0')
            self.assertEqual(parse.call_count, 1)
        self.assertEqual(self.validator.calls, 10)

    def test_graph_checks_still_execute_on_warm_canonical_snapshot(self):
        value = topology(); raw = canonical(value); expected = graph.parse_topology(raw)
        with patch.object(graph, '_dag', wraps=graph._dag) as dag, \
             patch.object(graph, 'parse_json', side_effect=AssertionError('warm parse')):
            self.assertEqual(graph.parse_topology(raw), expected)
            self.assertEqual(dag.call_count, 2)
        value['nodes']['svcA']['requires'].append('driverA'); raw = canonical(value)
        for _ in range(2):
            with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_DEPENDENCY_CYCLE'):
                graph.parse_topology(raw)

    def test_generation_association_still_checks_current_topology_after_warmup(self):
        value = topology(); current = generations(value); raw = canonical(current)
        graph.parse_generations(value, raw); graph.parse_generations(value, raw)
        value['topologyId'] = 'changed:current'
        with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_TOPOLOGY_CHANGED'):
            graph.parse_generations(value, raw)
        value = topology(); del current['nodes']['pin5']; raw = canonical(current)
        for _ in range(2):
            with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_GENERATION_CLOSURE'):
                graph.parse_generations(value, raw)

    def test_installation_reuses_first_encoding_and_detaches_both_carriers(self):
        value = installation(); original = copy.deepcopy(value)
        expected = installation_module.normalize_installation(value)
        for carrier in (value, canonical(value)):
            with self.subTest(carrier=type(carrier)), \
                 patch.object(installation_module, 'implementation_digest', return_value=value['driverDigest']) as identity, \
                 patch.object(installation_module, 'canonical', wraps=canonical) as encode:
                result = installation_module.normalize_installation(carrier)
                self.assertEqual(result, expected)
                self.assertEqual(encode.call_count, 1)
                identity.assert_called_once_with()
            result['handlers'][0]['actionId'] = 'caller:changed'
            self.assertEqual(value, original)
        self.assertEqual(installation_module.normalize_installation(value), expected)

    def test_installation_source_identity_is_rechecked_after_warm_snapshot(self):
        value = installation(); installation_module.normalize_installation(value)
        with patch.object(installation_module, 'implementation_digest', return_value='sha256:' + '0' * 64) as identity:
            for carrier in (value, canonical(value)):
                with self.assertRaisesRegex(JournalError, 'IO_DRIVER_CHANGED'):
                    installation_module.normalize_installation(carrier)
            self.assertEqual(identity.call_count, 2)

    def test_installation_float_refusal_precedes_identity_or_cached_normalization(self):
        value = installation(); installation_module.normalize_installation(value)
        value['initialGenerations']['revision'] = 1.0
        with patch.object(installation_module, 'implementation_digest', side_effect=AssertionError('float reached identity')):
            for carrier in (value, json.dumps(value).encode()):
                with self.subTest(carrier=type(carrier)), self.assertRaisesRegex(JournalError, 'IO_INTEGER_CONFIGURATION_REQUIRED'):
                    installation_module.normalize_installation(carrier)
