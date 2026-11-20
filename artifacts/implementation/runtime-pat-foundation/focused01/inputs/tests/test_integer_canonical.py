"""Public canonical carrier bytes remain identical to the reference encoder."""
import copy
import json
import random
import unittest
from unittest.mock import patch

from hms import contracts
from hms._vendor import rfc8785


class IntegerCanonicalTests(unittest.TestCase):
    def test_unicode_key_order_uses_utf16_and_preserves_escapes(self):
        value = {'\ue000': 1, '\U0001f600': 2, 'a': '\x00\b\t\n\f\r"\\/'}
        expected = b'{"a":"\\u0000\\b\\t\\n\\f\\r\\"\\\\/","\xf0\x9f\x98\x80":2,"\xee\x80\x80":1}'
        self.assertEqual(contracts.canonical(value), expected)
        self.assertEqual(expected, rfc8785.dumps(value))

    def test_fixed_generated_trees_match_reference_without_mutating_inputs(self):
        rng = random.Random(20261109)
        scalars = [None, True, False, 0, -1, contracts.SAFE_INTEGER,
                   -contracts.SAFE_INTEGER, '', '\x00', '\ue000', '\U0001f600']
        def tree(depth):
            if depth == 0 or rng.randrange(3) == 0:
                return rng.choice(scalars)
            children = [tree(depth - 1) for _ in range(rng.randrange(5))]
            return children if rng.randrange(2) else {
                str(i) + rng.choice(['a', '\ue000', '\U0001f600']): child
                for i, child in enumerate(children)}
        for _ in range(300):
            value = tree(4)
            before = copy.deepcopy(value)
            self.assertEqual(contracts.canonical(value), rfc8785.dumps(value))
            self.assertEqual(value, before)

    def test_nested_float_uses_reference_for_entire_value(self):
        value = {'integer': 1, 'nested': [0.1, -0.0, 1e-7, 1e-20]}
        expected = rfc8785.dumps(value)
        with patch.object(rfc8785, 'dumps', wraps=rfc8785.dumps) as reference:
            self.assertEqual(contracts.canonical(value), expected)
        reference.assert_called_once_with(value)

    def test_float_bytes_match_reference_without_changed_helpers(self):
        for number in (0.1, -0.0, 1.0, 1e-7, 1e-6, 1.2345678901234567):
            value = {'number': [number]}
            self.assertEqual(contracts.canonical(value), rfc8785.dumps(value))

    def test_integer_fast_path_is_used_only_with_unchanged_dependencies(self):
        self.assertTrue(contracts._fast_allowed())
        with patch.object(json.encoder, 'c_make_encoder', None):
            self.assertFalse(contracts._fast_allowed())
            self.assertEqual(contracts.canonical({'a': 1}), b'{"a":1}')
        with patch.object(contracts, 'MAX_BYTES', contracts.MAX_BYTES - 1):
            self.assertFalse(contracts._fast_allowed())
            self.assertEqual(contracts.canonical({'a': 1}), b'{"a":1}')
        self.assertTrue(contracts._fast_allowed())

    def test_replaced_encoder_bypasses_fast_path(self):
        class UnexpectedEncoder:
            def __init__(self, **kwargs):
                raise AssertionError('changed encoder must not be used')
        with patch.object(json, 'JSONEncoder', UnexpectedEncoder):
            self.assertFalse(contracts._fast_allowed())
            self.assertEqual(contracts.canonical({'a': 1}), b'{"a":1}')

    def test_reference_function_code_change_disables_fast_path(self):
        function = rfc8785.dumps
        original = function.__code__
        def changed(value):
            return b'changed reference'
        try:
            function.__code__ = changed.__code__
            self.assertFalse(contracts._fast_allowed())
            self.assertEqual(contracts.canonical({'a': 1}), b'changed reference')
        finally:
            function.__code__ = original
        self.assertTrue(contracts._fast_allowed())

    def test_invalid_values_and_encoded_size_still_refuse(self):
        cycle = []; cycle.append(cycle)
        for value in (contracts.SAFE_INTEGER + 1, float('nan'), float('inf'),
                      '\ud800', {1: 'non-string key'}, cycle,
                      '\x00' * (contracts.MAX_BYTES // 6 + 1)):
            with self.subTest(kind=type(value).__name__), self.assertRaises(contracts.ContractError):
                contracts.canonical(value)

    def test_custom_objects_are_rejected_without_invoking_hooks(self):
        calls = []
        class Custom(str):
            def encode(self, *args, **kwargs):
                calls.append('encode')
                raise AssertionError('custom hook')
        with self.assertRaises(contracts.ContractError):
            contracts.canonical({'value': Custom('not a built-in string')})
        self.assertEqual(calls, [])
