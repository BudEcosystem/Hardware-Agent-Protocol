"""Pure normalization reuse: exact inputs, fresh identity, isolated results."""
from collections import OrderedDict
from contextlib import contextmanager
import copy
import json
import sys
import threading
import unittest
from unittest.mock import patch

from hms import resource_topology as graph
from hms import synthetic_io_installation as module
from hms.contracts import ContractError, canonical
from hms.journal import JournalError
from test_io_synthetic_provider import installation


@contextmanager
def calls_to(*functions):
    # Observe original functions without replacing any validation dependency.
    counts = {function.__code__: 0 for function in functions}
    previous = sys.getprofile()
    def observe(frame, event, arg):
        if event == 'call' and frame.f_code in counts:
            counts[frame.f_code] += 1
    sys.setprofile(observe)
    try:
        yield counts
    finally:
        sys.setprofile(previous)


class InstallationReuseTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('_NORMALIZATION_MEMO', OrderedDict()), ('_NORMALIZATION_KEY_BYTES', 0)):
            change = patch.object(module, name, value)
            change.start(); self.addCleanup(change.stop)
        self.value = installation()

    def test_identical_object_and_bytes_reuse_semantics_but_check_source_each_time(self):
        with calls_to(module._normalize_validated, module.implementation_digest) as counts:
            expected = module.normalize_installation(self.value)
            self.assertEqual(module.normalize_installation(self.value), expected)
            self.assertEqual(module.normalize_installation(canonical(self.value)), expected)
        self.assertEqual(counts[module._normalize_validated.__code__], 1)
        self.assertEqual(counts[module.implementation_digest.__code__], 3)
        self.assertEqual(len(module._NORMALIZATION_MEMO), 1)

    def test_returned_nested_mutation_never_changes_caller_or_later_results(self):
        original = canonical(self.value)
        expected = module.normalize_installation(self.value)
        changed = module.normalize_installation(self.value)
        changed['topology']['nodes']['pin5']['properties']['electrical']['modes'].clear()
        changed['routes']['adapters'].clear(); changed['handlers'].clear()
        self.assertEqual(canonical(self.value), original)
        self.assertEqual(module.normalize_installation(self.value), expected)
        self.value['handlers'][0]['primitive'] = 'unsupported'
        with self.assertRaisesRegex(JournalError, 'IO_HANDLER_UNSUPPORTED'):
            module.normalize_installation(self.value)
        self.assertEqual(len(module._NORMALIZATION_MEMO), 1)

    def test_integral_float_in_object_or_json_refuses_before_lookup(self):
        module.normalize_installation(self.value)
        self.value['topology']['nodes']['pin5']['properties']['electrical']['nominalMilliVolt'] = 3300.0
        with patch.object(module, '_cached_normalization', side_effect=AssertionError('lookup')):
            for value in (self.value, json.dumps(self.value).encode()):
                with self.assertRaisesRegex(JournalError, 'IO_INTEGER_CONFIGURATION_REQUIRED'):
                    module.normalize_installation(value)

    def test_custom_values_and_keys_refuse_without_callbacks_or_lookup(self):
        called = []
        class Key(str):
            def __hash__(self): called.append('hash'); return super().__hash__()
            def __eq__(self, other): called.append('equal'); return super().__eq__(other)
        class Value:
            def __deepcopy__(self, memo): called.append('copy'); raise AssertionError('copy')
            def __iter__(self): called.append('iter'); raise AssertionError('iter')
        keyed = copy.deepcopy(self.value); keyed[Key('boardId')] = keyed.pop('boardId')
        valued = copy.deepcopy(self.value); valued['boardId'] = Value()
        called.clear()
        with patch.object(module, '_cached_normalization', side_effect=AssertionError('lookup')):
            for value in (keyed, valued):
                with self.assertRaises(ContractError): module.normalize_installation(value)
        self.assertEqual(called, []); self.assertFalse(module._NORMALIZATION_MEMO)

    def test_changed_current_source_refuses_even_with_warm_exact_input(self):
        module.normalize_installation(self.value)
        with patch.object(module, 'implementation_digest', return_value='sha256:' + '0' * 64) as identity, \
             patch.object(module, '_cached_normalization', side_effect=AssertionError('lookup')):
            with self.assertRaisesRegex(JournalError, 'IO_DRIVER_CHANGED'):
                module.normalize_installation(self.value)
            identity.assert_called_once_with()

    def test_changed_helper_bypasses_warm_result_and_runs_original_validation(self):
        module.normalize_installation(self.value)
        with patch.object(graph, '_dag', side_effect=JournalError('HELPER_CHANGED')) as helper:
            with self.assertRaisesRegex(JournalError, 'HELPER_CHANGED'):
                module.normalize_installation(self.value)
            helper.assert_called_once()
        self.assertFalse(module._NORMALIZATION_MEMO)
        self.assertEqual(module._NORMALIZATION_KEY_BYTES, 0)

    def test_replaced_topology_or_generation_validator_refuses_warm_input(self):
        class Reject:
            def iter_errors(self, value): return iter([object()])
        for profile in (graph.PROFILE, graph.GENERATION_PROFILE):
            module.normalize_installation(self.value)
            with patch.dict(graph._VALIDATORS, {profile: Reject()}):
                with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_INVALID_DOCUMENT'):
                    module.normalize_installation(self.value)
            self.assertFalse(module._NORMALIZATION_MEMO)

    def test_dependency_changed_during_validation_prevents_publication(self):
        class Reject:
            def iter_errors(self, value): return iter([object()])
        original = graph._VALIDATORS[graph.PROFILE]
        previous = sys.getprofile(); changed = []
        def swap(frame, event, arg):
            if frame.f_code is module._normalize_validated.__code__ and event == 'return':
                graph._VALIDATORS[graph.PROFILE] = Reject(); changed.append(True)
        sys.setprofile(swap)
        try:
            result = module.normalize_installation(self.value)
        finally:
            sys.setprofile(previous)
        try:
            self.assertEqual(changed, [True]); self.assertEqual(result['boardId'], 'board')
            self.assertFalse(module._NORMALIZATION_MEMO)
            with self.assertRaisesRegex(graph.ResourceTopologyError, 'RESOURCE_INVALID_DOCUMENT'):
                module.normalize_installation(self.value)
        finally:
            graph._VALIDATORS[graph.PROFILE] = original

    def test_in_place_primitive_configuration_change_uses_current_validation(self):
        module.normalize_installation(self.value)
        with patch.dict(module.PRIMITIVES, {'gpio_pulse': 'pwm_access'}):
            with self.assertRaisesRegex(JournalError, 'IO_HANDLER_TYPE_MISMATCH'):
                module.normalize_installation(self.value)
        self.assertFalse(module._NORMALIZATION_MEMO)

    def test_private_schema_and_keyword_changes_disable_reuse(self):
        expected = module.normalize_installation(self.value)
        validator = graph._VALIDATORS[graph.PROFILE]
        # These private mutations test memo bypass only. Existing graph snapshot
        # caching does not promise revalidation after in-place schema mutation.
        with patch.dict(validator.schema, {'title': 'diagnostic change'}), \
             calls_to(module._normalize_validated) as counts:
            self.assertEqual(module.normalize_installation(self.value), expected)
            self.assertFalse(module._NORMALIZATION_MEMO)
        self.assertEqual(counts[module._normalize_validated.__code__], 1)
        module.normalize_installation(self.value)
        original = type(validator).VALIDATORS['type']
        def keyword(*args, **kwargs): return original(*args, **kwargs)
        with patch.dict(type(validator).VALIDATORS, {'type': keyword}), \
             calls_to(module._normalize_validated) as counts:
            self.assertEqual(module.normalize_installation(self.value), expected)
            self.assertFalse(module._NORMALIZATION_MEMO)
        self.assertEqual(counts[module._normalize_validated.__code__], 1)

    def test_ninth_valid_input_evicts_oldest_with_fixed_key_and_entry_bounds(self):
        variants = []
        for number in range(9):
            value = copy.deepcopy(self.value)
            value['topology']['topologyId'] = 'topology:reuse:' + str(number)
            value['initialGenerations']['topologyDigest'] = graph.topology_digest(value['topology'])
            variants.append(value)
            module.normalize_installation(value)
        self.assertEqual(len(module._NORMALIZATION_MEMO), 8)
        self.assertLessEqual(module._NORMALIZATION_KEY_BYTES, 8 * 65536)
        self.assertEqual(module._NORMALIZATION_KEY_BYTES, sum(map(len, module._NORMALIZATION_MEMO)))
        self.assertNotIn(canonical(variants[0]), module._NORMALIZATION_MEMO)
        with calls_to(module._normalize_validated) as counts:
            module.normalize_installation(variants[0])
        self.assertEqual(counts[module._normalize_validated.__code__], 1)
        pending = list(module._NORMALIZATION_MEMO.values())
        while pending:
            value = pending.pop()
            self.assertIn(type(value), (tuple, str, int, bool, float, type(None), type))
            if type(value) is tuple: pending.extend(value)

    def test_noncanonical_bytes_share_key_but_duplicate_or_oversized_json_refuses(self):
        with calls_to(module._normalize_validated, module.implementation_digest) as counts:
            expected = module.normalize_installation(self.value)
            self.assertEqual(module.normalize_installation(json.dumps(self.value, indent=2).encode()), expected)
        self.assertEqual(counts[module._normalize_validated.__code__], 1)
        self.assertEqual(counts[module.implementation_digest.__code__], 2)
        with patch.object(module, '_cached_normalization', side_effect=AssertionError('lookup')):
            for value in (b' ' * 65537, b'{"profile":1,"profile":2}'):
                with self.assertRaises(ContractError): module.normalize_installation(value)

    def test_reuse_never_opens_authority_launches_provider_or_reads_clock(self):
        expected = module.normalize_installation(self.value)
        with patch('sqlite3.connect', side_effect=AssertionError('authority')), \
             patch('subprocess.Popen', side_effect=AssertionError('provider')), \
             patch('time.monotonic', side_effect=AssertionError('clock')), \
             calls_to(module._normalize_validated, module.implementation_digest) as counts:
            self.assertEqual(module.normalize_installation(self.value), expected)
        self.assertEqual(counts[module._normalize_validated.__code__], 0)
        self.assertEqual(counts[module.implementation_digest.__code__], 1)

    def test_concurrent_calls_keep_one_entry_and_detached_results(self):
        barrier = threading.Barrier(2, timeout=5)
        results, failures = [], []
        def normalize():
            try:
                barrier.wait(); results.append(module.normalize_installation(self.value))
            except BaseException as error: failures.append(error)
        threads = [threading.Thread(target=normalize) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, []); self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1]); self.assertIsNot(results[0], results[1])
        results[0]['handlers'].clear()
        self.assertTrue(results[1]['handlers'])
        self.assertEqual(module.normalize_installation(self.value), results[1])
        self.assertEqual(len(module._NORMALIZATION_MEMO), 1)
