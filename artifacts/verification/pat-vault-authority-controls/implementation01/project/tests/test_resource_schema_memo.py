"""Exact schema reuse preserves typed input, detachment and semantic refusals."""
from collections import OrderedDict
import copy
import json
import unittest
from unittest.mock import patch

from hms import resource_topology as graph
from hms.contracts import canonical
from test_resource_topology import topology, generations


class CountingValidator:
    def __init__(self, original):
        self.original=original;self.calls=0
    def iter_errors(self, value):
        self.calls+=1
        return self.original.iter_errors(value)


class ResourceSchemaMemoTests(unittest.TestCase):
    def setUp(self):
        memo=patch.object(graph,'_SCHEMA_MEMO',OrderedDict());memo.start();self.addCleanup(memo.stop)
        self.validator=CountingValidator(graph._VALIDATORS[graph.PROFILE])
        validators=dict(graph._VALIDATORS);validators[graph.PROFILE]=self.validator
        p=patch.object(graph,'_VALIDATORS',validators);p.start();self.addCleanup(p.stop)

    def test_exact_bytes_and_reordered_object_keys_reuse_only_schema_success(self):
        value=topology();before=canonical(value)
        a=graph.parse_topology(value)
        b=graph.parse_topology(dict(reversed(list(value.items()))))
        c=graph.parse_topology(json.dumps(value).encode())
        self.assertEqual(a,b);self.assertEqual(a,c);self.assertEqual(self.validator.calls,1)
        self.assertEqual(canonical(value),before)

    def test_returned_nested_data_cannot_mutate_cache_or_other_results(self):
        value=topology();expected=graph.parse_topology(value)
        result=graph.parse_topology(value);result['nodes']['pin5']['properties']['electrical']['modes'].clear()
        self.assertEqual(graph.parse_topology(value),expected)
        self.assertEqual(self.validator.calls,1)
        self.assertTrue(all(type(key[1])is bytes for key in graph._SCHEMA_MEMO))

    def test_warm_entry_does_not_accept_integral_float_bool_or_duplicate_json_keys(self):
        value=topology();graph.parse_topology(value)
        for wrong in (3300.0,True):
            changed=copy.deepcopy(value);changed['nodes']['pin5']['properties']['electrical']['nominalMilliVolt']=wrong
            with self.subTest(wrong=wrong),self.assertRaises(graph.ResourceTopologyError):graph.parse_topology(changed)
        raw=canonical(value).replace(b'"nominalMilliVolt":3300',b'"nominalMilliVolt":3300.0',1)
        with self.assertRaises(graph.ResourceTopologyError):graph.parse_topology(raw)
        raw=canonical(value).replace(b'"topologyId":',b'"topologyId":"duplicate","topologyId":',1)
        with self.assertRaises(graph.ResourceTopologyError):graph.parse_topology(raw)

    def test_schema_invalid_documents_are_never_cached(self):
        value=topology();value['unexpected']=True
        for _ in range(2):
            with self.assertRaises(graph.ResourceTopologyError):graph.parse_topology(value)
        self.assertEqual(self.validator.calls,2);self.assertEqual(len(graph._SCHEMA_MEMO),0)

    def test_schema_success_does_not_suppress_repeated_graph_failure(self):
        value=topology();value['nodes']['svcA']['requires'].append('driverA')
        for _ in range(2):
            with self.assertRaisesRegex(graph.ResourceTopologyError,'RESOURCE_DEPENDENCY_CYCLE'):graph.parse_topology(value)
        self.assertEqual(self.validator.calls,1)

    def test_exact_changed_footprint_is_revalidated_and_rejected(self):
        value=topology();graph.parse_topology(value)
        value['aliases']['alias:pwm5']['includes']=['atom:pin5']
        for _ in range(2):
            with self.assertRaisesRegex(graph.ResourceTopologyError,'RESOURCE_ALIAS_FOOTPRINT'):graph.parse_topology(value)
        self.assertEqual(self.validator.calls,2)

    def test_schema_replacement_cannot_inherit_cached_success(self):
        value=topology();graph.parse_topology(value)
        class Reject:
            def iter_errors(self, value):return iter([object()])
        graph._VALIDATORS[graph.PROFILE]=Reject()
        with self.assertRaisesRegex(graph.ResourceTopologyError,'RESOURCE_INVALID_DOCUMENT'):graph.parse_topology(value)

    def test_lru_capacity_and_eviction_are_bounded_without_truncating_input(self):
        values=[]
        for i in range(9):
            value=topology();value['topologyId']='fixture:'+str(i);values.append(value)
            graph.parse_topology(value)
        self.assertEqual(len(graph._SCHEMA_MEMO),8);self.assertEqual(self.validator.calls,9)
        self.assertLessEqual(sum(len(key[1])for key in graph._SCHEMA_MEMO),8*65536)
        graph.parse_topology(values[-1]);self.assertEqual(self.validator.calls,9)
        graph.parse_topology(values[0]);self.assertEqual(self.validator.calls,10)

    def test_generations_still_require_exact_current_topology_and_node_closure(self):
        value=topology();current=generations(value)
        graph.parse_generations(value,current);graph.parse_generations(value,current)
        changed=copy.deepcopy(value);changed['topologyId']='changed:topology'
        with self.assertRaisesRegex(graph.ResourceTopologyError,'RESOURCE_TOPOLOGY_CHANGED'):graph.parse_generations(changed,current)
        current=generations(value);del current['nodes']['pin5']
        for _ in range(2):
            with self.assertRaisesRegex(graph.ResourceTopologyError,'RESOURCE_GENERATION_CLOSURE'):graph.parse_generations(value,current)

    def test_binding_identity_tracks_changed_electrical_inputs_after_warmup(self):
        value=topology();before=graph.binding_proof(value,generations(value),'sim:gpio5')
        value['nodes']['pin5']['properties']['electrical']['nominalMilliVolt']=3000
        after=graph.binding_proof(value,generations(value),'sim:gpio5')
        self.assertNotEqual(before['closureDigest'],after['closureDigest'])
        self.assertEqual(before['expandedClaims'],after['expandedClaims'])

    def test_warm_snapshot_remains_pure_and_does_not_consult_caller_copy_hooks(self):
        value=topology();expected=graph.parse_topology(value)
        with patch('pathlib.Path.read_bytes',side_effect=AssertionError('file I/O')), \
             patch('sqlite3.connect',side_effect=AssertionError('authority I/O')), \
             patch('time.monotonic',side_effect=AssertionError('clock')), \
             patch('copy.deepcopy',side_effect=AssertionError('caller copy hook')):
            self.assertEqual(graph.parse_topology(value),expected)
