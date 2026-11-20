"""Exact immutable group-input association without repeated matrix construction."""
import copy
import importlib
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy
from hms.pat_io_group_budget import IoGroupBudget
from hms.pat_io_validated_matrix import ValidatedIoMatrix
from test_pat_io_group_worker import GroupFixture
from test_pat_io_contracts import program


class ValidatedIoMatrixTests(GroupFixture, unittest.TestCase):
    def bundle(self):
        options=self.options();plan=ValidatedIoMatrix(**options)
        return plan,dict(options,matrix=plan.matrix())

    def test_repeated_exact_inputs_do_not_reconstruct_policy_or_consult_authority(self):
        plan,inputs=self.bundle()
        with patch('hms.pat_io_validated_matrix.IoCombinedMatrixPolicy',side_effect=AssertionError('policy reconstruction')), \
             patch('pathlib.Path.read_bytes',side_effect=AssertionError('filesystem')), \
             patch('sqlite3.connect',side_effect=AssertionError('authority')):
            for _ in range(25):self.assertEqual(plan.validate_inputs(**inputs),plan.digest)

    def test_digest_and_matrix_match_independent_original_validation(self):
        plan,inputs=self.bundle();policy=IoCombinedMatrixPolicy(inputs['installation'])
        self.assertEqual(plan.digest,policy.validate(inputs['matrix'],inputs['candidate'],inputs['descriptor'],
            inputs['challenge_bindings'],limits=inputs['matrix']['limits']))
        self.assertEqual(inputs['matrix']['totals'],dict(cases=30,childOperations=44,schedulerTicks=1676))

    def test_all_five_input_documents_are_exactly_associated(self):
        plan,inputs=self.bundle()
        for name in inputs:
            changed=copy.deepcopy(inputs);changed[name]['unexpected']=True
            with self.subTest(document=name),self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_MISMATCH'):
                plan.validate_inputs(**changed)

    def test_integral_float_and_bool_cannot_inherit_success_through_json_equivalence(self):
        plan,inputs=self.bundle()
        for field,mutate in [
            ('matrix',lambda d:d['totals'].update(cases=30.0)),
            ('candidate',lambda d:d['steps'][0]['arguments']['level'].update(literal=True)),
            ('candidate',lambda d:d['steps'][0]['arguments']['level'].update(literal=1.0)),
            ('installation',lambda d:d['topology']['nodes']['pin5']['properties']['electrical'].update(nominalMilliVolt=3300.0))]:
            changed=copy.deepcopy(inputs);mutate(changed[field])
            with self.subTest(field=field),self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_MISMATCH'):
                plan.validate_inputs(**changed)

    def test_caller_mutation_and_returned_matrix_do_not_mutate_validated_bundle(self):
        plan,inputs=self.bundle();expected=copy.deepcopy(inputs)
        inputs['matrix']['cases'].clear();inputs['candidate']['steps'].clear()
        self.assertEqual(plan.matrix(),expected['matrix'])
        self.assertEqual(plan.validate_inputs(**expected),plan.digest)
        changed=plan.matrix();changed['limits']['maxWallMs']=60001
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_MISMATCH'):plan.assert_matrix(changed)

    def test_equal_bytes_and_reordered_keys_preserve_detached_reuse(self):
        plan,inputs=self.bundle()
        self.assertEqual(plan.validate_inputs(**{k:canonical(v)for k,v in inputs.items()}),plan.digest)
        self.assertEqual(plan.validate_inputs(**{k:dict(reversed(list(v.items())))for k,v in inputs.items()}),plan.digest)
        inputs['matrix']=b'{"profile":"x","profile":"y"}'
        with self.assertRaises(PatError):plan.validate_inputs(**inputs)

    def test_oversized_or_unsupported_reuse_input_cannot_reach_comparison(self):
        plan,inputs=self.bundle()
        for wrong in ('x'*65537,object()):
            changed=inputs|{'candidate':wrong}
            with self.subTest(kind=type(wrong).__name__),self.assertRaises(PatError):plan.validate_inputs(**changed)

    def test_constructor_preserves_full_preflight_and_original_limits(self):
        options=self.options();options['candidate']=program()
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_COMBINED_LIMIT'):ValidatedIoMatrix(**options)

    def test_budget_rejects_wrong_plan_type_or_mismatched_matrix(self):
        plan,inputs=self.bundle();changed=copy.deepcopy(inputs['matrix']);changed['cases'].reverse()
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_TYPE'):
            IoGroupBudget(inputs['matrix'],started=time.monotonic(),validated_plan=object())
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_MISMATCH'):
            IoGroupBudget(changed,started=time.monotonic(),validated_plan=plan)

    def test_ticket_requires_exact_plan_before_binding_and_cannot_reuse_stale_state(self):
        plan,inputs=self.bundle();matrix=inputs['matrix'];case=matrix['cases'][0]
        b=IoGroupBudget(matrix,started=time.monotonic());t=b.begin(case['caseId'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_REQUIRED'):t.validated_matrix_digest(**inputs)
        b=IoGroupBudget(matrix,started=time.monotonic(),validated_plan=plan);t=b.begin(case['caseId'])
        self.assertEqual(t.validated_matrix_digest(**inputs),plan.digest)
        t.bind(case['programDigest'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_ENGINE_REUSE'):t.validated_matrix_digest(**inputs)
        b.end(t,operation_count=0,scheduler_ticks=0)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_STALE_TICKET'):t.validated_matrix_digest(**inputs)

    def runners(self):
        for module,name,scenario in [('timing_worker','timing','not_before_boundary'),
                ('clock_capture','clock','start_run_equal'),('lifecycle_capture','lifecycle','cancel_accepted'),
                ('authority_capture','authority','binding_before_dispatch'),('resource_capture','resource','shared_resources')]:
            module=importlib.import_module('hms.pat_io_'+module)
            yield module,getattr(module,'run_'+name+'_challenge'),scenario

    def test_all_five_group_runner_families_reject_changed_inputs_before_runtime(self):
        plan,inputs=self.bundle();matrix=inputs['matrix']
        for module,runner,scenario in self.runners():
            b=IoGroupBudget(matrix,started=time.monotonic(),validated_plan=plan)
            for case in matrix['cases']:
                t=b.begin(case['caseId'])
                if case.get('definition',{}).get('scenario')==scenario:break
                if case['plannedChildOperations']:t.bind(case['programDigest'])
                b.end(t,operation_count=0,scheduler_ticks=0)
            changed=copy.deepcopy(inputs);changed['candidate']['name']='changed-name'
            with self.subTest(scenario=scenario),patch.object(module,'IoCombinedMatrixPolicy',side_effect=AssertionError('reconstruction')):
                with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PLAN_MISMATCH'):
                    runner(None,**changed,case_id=case['caseId'],group_budget=t)

    def test_all_five_standalone_runners_still_reconstruct_and_reject_a_changed_plan(self):
        plan,inputs=self.bundle()
        for module,runner,scenario in self.runners():
            changed=copy.deepcopy(inputs);changed['matrix']['totals']['cases']=29
            case=next(c for c in inputs['matrix']['cases']if c.get('definition',{}).get('scenario')==scenario)
            with self.subTest(scenario=scenario),self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                runner(None,**changed,case_id=case['caseId'])
