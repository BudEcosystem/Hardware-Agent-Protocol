"""Differential checks for one-call pure instance-proof reuse."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from hms import synthetic_io_installation as module
from hms.contracts import canonical
from hms.synthetic_io_installation import (handler_details, type_bundle, argument_schema,
    validate_type_bundle, binding_proof, control_generation)
from test_io_synthetic_provider import installation
from test_resource_topology import generations
from test_pat_io_installation_reuse import calls_to

def _legacy_definitions(document):
    """Return original I/O type bundles and proof-derived exact bindings."""
    result = {}
    instances = sorted({row['instanceId'] for row in document['handlers']})
    for instance in instances:
        bundle = None; resources = {}
        for row in (item for item in document['handlers'] if item['instanceId'] == instance):
            action = row['actionId']; detail = handler_details(document, instance, action)
            role = 'io-root:' + action
            part = type_bundle('finite-io-' + hashlib.sha256(instance.encode()).hexdigest()[:16], action,
                argument_schema(detail), {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991},
                unit='1', effect=detail['primitive'], resource=role)
            part['execution']['actions'][action]['preconditions'] = []
            part['execution']['capabilities'] = ['sim:finite-gpio-pwm']
            part['td']['description'] = 'Original finite synthetic I/O; value counts activations, not measured electrical state.'
            if bundle is None:
                bundle = part
            else:
                bundle['execution']['actions'].update(part['execution']['actions'])
                bundle['td']['actions'].update(part['td']['actions'])
            resources[role] = detail['root']
        digest = validate_type_bundle(bundle)
        proof = binding_proof(document['topology'], document['initialGenerations'], instance)
        adapter = next(key for key, values in document['routes']['adapters'].items() if instance in values)
        binding = {'profile': 'hms.binding/0.1', 'instanceId': instance, 'generation': proof['bindingGeneration'],
            'typeDigest': digest, 'calibrationRevision': 'synthetic:finite-io:1', 'controlGeneration': control_generation(proof),
            'mode': 'simulation', 'adapterId': adapter, 'resourceMap': resources,
            'argumentSchemas': {key: copy.deepcopy(item['inputSchema']) for key, item in bundle['execution']['actions'].items()}}
        result[instance] = {'type': bundle, 'binding': binding, 'proof': proof}
    return result


class DefinitionBuildTests(unittest.TestCase):
    def setUp(self):
        self.document = module.normalize_installation(installation())

    def test_original_bundles_bindings_and_proofs_match_with_half_the_derivations(self):
        function = module._topology._binding_proof_from_validated
        before = canonical(self.document)
        with calls_to(function) as old_calls:
            expected = _legacy_definitions(self.document)
        with calls_to(function) as new_calls:
            actual = module.definitions(self.document)
        self.assertEqual(canonical(actual), canonical(expected))
        self.assertEqual(canonical(self.document), before)
        self.assertEqual(old_calls[function.__code__], 8)
        self.assertEqual(new_calls[function.__code__], 4)
        target = Path(tempfile.gettempdir()) / self._testMethodName
        target.mkdir(mode=0o700)
        (target / 'derivation-counts.json').write_text(json.dumps(dict(instances=4, actions=4,
            legacyDerivations=8, candidateDerivations=4, exactCanonicalOutputEqual=True,
            currentAuthorityRead=False, workerExecuted=False, performanceGuarantee=False), indent=2) + '\n')

    def test_multiple_actions_share_only_their_own_instance_proof(self):
        document = copy.deepcopy(self.document)
        original = next(row for row in document['topology']['consumers'] if row['instanceId'] == 'sim:gpio5')
        for action in ('pulse_alternate', 'pulse_auxiliary'):
            document['topology']['consumers'].append(original | {'actionId': action})
            document['handlers'].append(dict(instanceId='sim:gpio5', actionId=action, primitive='gpio_pulse'))
        document['initialGenerations'] = generations(document['topology'])
        document = module.normalize_installation(document)
        function = module._topology._binding_proof_from_validated
        with calls_to(function) as old_calls:
            expected = _legacy_definitions(document)
        with calls_to(function) as new_calls:
            actual = module.definitions(document)
        self.assertEqual(canonical(actual), canonical(expected))
        self.assertEqual(old_calls[function.__code__], 10)
        self.assertEqual(new_calls[function.__code__], 4)
        self.assertEqual(set(actual['sim:gpio5']['proof']['expandedClaims']), {'gpio_pulse', 'pulse_alternate', 'pulse_auxiliary'})

    def test_changed_generations_are_rederived_on_each_build(self):
        first = module.definitions(self.document)
        self.document['initialGenerations']['revision'] = 2
        self.document['initialGenerations']['nodes']['pin5'] = 'generation:2'
        function = module._topology._binding_proof_from_validated
        with calls_to(function) as counts:
            changed = module.definitions(self.document)
        self.assertEqual(counts[function.__code__], 4)
        self.assertEqual(changed, _legacy_definitions(self.document))
        self.assertNotEqual(first['sim:gpio5']['binding']['generation'], changed['sim:gpio5']['binding']['generation'])
        self.assertEqual(first['sim:gpio6'], changed['sim:gpio6'])

    def test_returned_mutation_changes_neither_input_nor_later_builds(self):
        expected = _legacy_definitions(self.document)
        before = canonical(self.document)
        changed = module.definitions(self.document)
        changed['sim:gpio5']['proof']['expandedClaims']['gpio_pulse'].clear()
        changed['sim:pwm5']['type']['execution']['actions'].clear()
        changed['sim:gpio6']['binding']['resourceMap'].clear()
        self.assertEqual(canonical(self.document), before)
        self.assertEqual(module.definitions(self.document), expected)

    def test_invalid_proof_inputs_keep_original_refusal_type_and_code(self):
        values = []
        value = copy.deepcopy(self.document); del value['initialGenerations']['nodes']['pin5']; values.append(value)
        value = copy.deepcopy(self.document); value['initialGenerations']['revision'] = True; values.append(value)
        value = copy.deepcopy(self.document); value['topology']['nodes']['pin5']['properties']['electrical']['nominalMilliVolt'] = 3300.0; values.append(value)
        def refused(function, value):
            try:
                function(value)
            except Exception as error:
                return type(error), getattr(error, 'code', None), str(error)
            self.fail('Invalid proof accepted')
        for value in values:
            with self.subTest(value=value['initialGenerations']['revision']):
                self.assertEqual(refused(module.definitions, value), refused(_legacy_definitions, value))

    def test_public_handler_details_still_derives_a_fresh_proof_per_call(self):
        function = module.binding_proof.__wrapped__
        with calls_to(function) as counts:
            first = module.handler_details(self.document, 'sim:gpio5', 'gpio_pulse')
            second = module.handler_details(self.document, 'sim:gpio5', 'gpio_pulse')
        self.assertEqual(counts[function.__code__], 2)
        self.assertEqual(first, second)
        first['claims'].clear()
        self.assertEqual(second['claims'], ['atom:pin5'])

    def test_build_is_pure_and_does_not_read_authority_or_current_sources(self):
        expected = _legacy_definitions(self.document)
        denied = AssertionError('Unexpected external access during pure definition build')
        with (patch.object(Path, 'read_bytes', side_effect=denied),
              patch.object(sqlite3, 'connect', side_effect=denied),
              patch.object(time, 'monotonic', side_effect=denied),
              patch.object(time, 'time', side_effect=denied),
              patch.object(module, 'implementation_digest', side_effect=denied)):
            self.assertEqual(module.definitions(self.document), expected)
