"""One-call topology reuse with exact baseline references and bounded timings."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import statistics
import tempfile
import time
import unittest
from unittest.mock import patch

from hms import resource_topology as graph
from hms import synthetic_io_installation as module
from hms.contracts import canonical
from _reference_definition_build import reference_binding_proof, reference_definitions
from test_io_synthetic_provider import installation
from test_pat_io_installation_reuse import calls_to
from test_resource_topology import generations, topology, with_bus


def outcome(function, value):
    try: return ('returned', function(value))
    except Exception as error:
        return ('refused', type(error), getattr(error, 'code', None), str(error))


class ProofBatchTests(unittest.TestCase):
    def setUp(self):
        self.document = module.normalize_installation(installation())

    def test_exact_build_with_one_validation_and_four_separate_proofs(self):
        functions=(graph.parse_topology.__wrapped__,graph._generations,graph._atom_index,
                   graph._alias_closures,graph._binding_proof_from_validated)
        before=canonical(self.document)
        with calls_to(*functions) as old:
            expected=reference_definitions(self.document)
        with calls_to(*functions) as new:
            actual=module.definitions(self.document)
        self.assertEqual(canonical(actual),canonical(expected))
        self.assertEqual(canonical(self.document),before)
        self.assertEqual([old[f.__code__] for f in functions],[4,4,8,8,4])
        self.assertEqual([new[f.__code__] for f in functions],[1,1,2,2,4])

    def test_public_proof_matches_original_body_for_gpio_pwm_bus_and_generations(self):
        for document in (topology(),with_bus()):
            current=generations(document)
            for revision in (1,2):
                current['revision']=revision
                current['nodes']['pin5']='generation:'+str(revision)
                for instance in sorted({row['instanceId'] for row in document['consumers']}):
                    with self.subTest(instance=instance,revision=revision):
                        expected=reference_binding_proof(document,current,instance)
                        self.assertEqual(canonical(graph.binding_proof(document,current,instance)),canonical(expected))

    def test_invalid_inputs_preserve_original_first_refusal(self):
        cases=[]
        for field in ('handlers','topology','initialGenerations','routes'):
            value=copy.deepcopy(self.document);del value[field];cases.append(value)
        value=copy.deepcopy(self.document);value['handlers']=[];cases.append(value)
        value=copy.deepcopy(self.document);value['handlers'][0]['actionId']='unknown';del value['initialGenerations'];cases.append(value)
        value=copy.deepcopy(self.document);del value['initialGenerations']['nodes']['pin5'];cases.append(value)
        value=copy.deepcopy(self.document);value['initialGenerations']['revision']=True;cases.append(value)
        value=copy.deepcopy(self.document);value['initialGenerations']['topologyDigest']='sha256:'+'0'*64;cases.append(value)
        value=copy.deepcopy(self.document);value['topology']['nodes']['pin5']['properties']['electrical']['nominalMilliVolt']=3300.0;cases.append(value)
        value=copy.deepcopy(self.document);value['topology']['aliases']['alias:gpio5']['includes']=[];cases.append(value)
        value=copy.deepcopy(self.document);value['routes']['adapters']={};cases.append(value)
        value=copy.deepcopy(self.document);value['handlers'].append(dict(instanceId='zz:missing',actionId='pulse',primitive='gpio_pulse'));cases.append(value)
        value=copy.deepcopy(self.document);value['topology']['nodes']['pin5']['properties'].clear();value['initialGenerations']['revision']=False;cases.append(value)
        for i,value in enumerate(cases):
            with self.subTest(case=i):self.assertEqual(outcome(module.definitions,value),outcome(reference_definitions,value))

    def test_each_call_observes_changed_generation_and_topology(self):
        original=module.definitions(self.document)
        self.document['initialGenerations']['revision']=2
        self.document['initialGenerations']['nodes']['pin5']='generation:2'
        changed=module.definitions(self.document)
        self.assertEqual(changed,reference_definitions(self.document))
        self.assertNotEqual(original['sim:gpio5'],changed['sim:gpio5'])
        self.assertEqual(original['sim:gpio6'],changed['sim:gpio6'])
        self.document['topology']['nodes']['pin5']['properties']['electrical']['nominalMilliVolt']=3000
        self.document['initialGenerations']=generations(self.document['topology'])
        current=module.definitions(self.document)
        self.assertEqual(current,reference_definitions(self.document))
        self.assertNotEqual(changed['sim:gpio5']['proof']['closureDigest'],current['sim:gpio5']['proof']['closureDigest'])

    def test_returned_mutations_do_not_alias_other_instances_or_future_calls(self):
        before=canonical(self.document);expected=reference_definitions(self.document)
        actual=module.definitions(self.document)
        actual['sim:gpio5']['proof']['dependencies'].clear()
        actual['sim:gpio5']['proof']['expandedClaims']['gpio_pulse'].clear()
        actual['sim:gpio5']['binding']['argumentSchemas'].clear()
        self.assertEqual(actual['sim:pwm5'],expected['sim:pwm5'])
        self.assertEqual(canonical(self.document),before)
        self.assertEqual(module.definitions(self.document),expected)

    def test_public_handler_calls_never_use_private_build_snapshot(self):
        function=graph.parse_topology.__wrapped__
        with patch.object(graph,'_BindingProofBuild',side_effect=AssertionError('public snapshot reuse')):
            with calls_to(function) as counts:
                first=module.handler_details(self.document,'sim:gpio5','gpio_pulse')
                self.document['initialGenerations']['nodes']['pin5']='generation:2'
                second=module.handler_details(self.document,'sim:gpio5','gpio_pulse')
        self.assertEqual(counts[function.__code__],2)
        self.assertEqual(first,second)

    def test_replaced_public_proof_helper_keeps_original_call_path(self):
        expected=reference_definitions(self.document);original=module.binding_proof
        with patch.object(module,'binding_proof',wraps=original) as observed, \
             patch.object(graph,'_BindingProofBuild',side_effect=AssertionError('bypassed helper')):
            actual=module.definitions(self.document)
        self.assertEqual(actual,expected);self.assertEqual(observed.call_count,4)

    def test_concurrent_builds_keep_distinct_static_inputs(self):
        documents=[]
        for revision in range(1,5):
            value=copy.deepcopy(self.document);value['initialGenerations']['revision']=revision
            value['initialGenerations']['nodes']['pin5']='generation:'+str(revision);documents.append(value)
        expected=[reference_definitions(value) for value in documents]
        with ThreadPoolExecutor(max_workers=4) as executor:
            actual=list(executor.map(module.definitions,documents))
        self.assertEqual(actual,expected)
        self.assertEqual(len({value['sim:gpio5']['proof']['bindingGeneration'] for value in actual}),4)

    def test_untrusted_topology_value_refuses_without_copy_hook(self):
        called=[]
        class Invalid:
            def __deepcopy__(self,memo):called.append(True);raise AssertionError('untrusted copy')
        self.document['topology']['nodes']['hub']['properties']=Invalid()
        self.assertEqual(outcome(module.definitions,self.document),outcome(reference_definitions,self.document))
        self.assertEqual(called,[])

