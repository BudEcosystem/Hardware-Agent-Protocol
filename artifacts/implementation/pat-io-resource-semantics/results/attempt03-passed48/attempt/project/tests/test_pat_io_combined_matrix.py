"""Closed combined case coverage, topology actors, integrity and global budgets."""
import builtins
import copy
import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy, CEILINGS
from hms.synthetic_io_installation import definitions, normalize_installation, installation_digest, DRIVER
from test_io_synthetic_provider import installation
from test_pat_io_contracts import program
from test_resource_topology import generations

REQUIRED = {
    'cancel_accepted','cancel_pending','reopen_accepted','reopen_pending','completion_reply_lost','pending_reply_lost',
    'not_before_boundary','latest_start_before','latest_start_equal','start_run_equal','run_completion_equal',
    'wall_completion_equal','lease_wait_before','lease_wait_equal','late_parent_reporting','wall_clock_regression',
    'clock_epoch_mismatch','permission_before_parent','permission_before_dispatch','permission_pending',
    'permission_after_completion','full_authority_withdrawal','binding_before_dispatch','binding_pending','shared_resources'}


def bindings(document):
    definitions_by_id = definitions(document); result = {}
    for role,instance in [('gpio','sim:gpio5'),('pwm','sim:pwm5'),('alias','sim:gpio5:other-route'),('independent','sim:gpio6')]:
        definition=definitions_by_id[instance]
        handler,=[h for h in document['handlers'] if h['instanceId']==instance]
        units=({'durationMs':'ms','level':'1'} if handler['primitive']=='gpio_pulse' else
               {'durationMs':'ms','frequencyHz':'Hz','dutyPermille':'permille','resolutionBits':'bit'})
        metadata={key:dict(profile='hms.pat.argument.fixed-schema-unit/0.1',unit=unit,frame=None,unitArgument=None,frameArgument=None)
                  for key,unit in units.items()}
        descriptor=dict(type=definition['type'],binding=definition['binding'],endpointSession='session:trusted-test',
            driverProfile=DRIVER,driverDigest=document['driverDigest'],installationDigest=installation_digest(document),
            argumentMetadata={handler['actionId']:metadata})
        result[role]=dict(actionId=handler['actionId'],descriptor=descriptor)
    return result


class IoCombinedMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=normalize_installation(installation()); cls.policy=IoCombinedMatrixPolicy(cls.document)
        cls.bindings=bindings(cls.document)

    def plan(self, *, pwm=False, count=1, limits=None):
        return self.policy.generate(program(pwm=pwm,count=count,literal=True),
            self.bindings['pwm' if pwm else 'gpio']['descriptor'],self.bindings,limits=limits)

    def test_constant_gpio_and_pwm_include_all_required_cases_and_operations(self):
        for pwm in (False,True):
            plan=self.plan(pwm=pwm)
            self.assertEqual(plan['totals'],dict(cases=30,childOperations=43,schedulerTicks=1676))
            self.assertEqual(len(plan['cases']),30)
            self.assertEqual({c['definition']['scenario'] for c in plan['cases'] if c['kind']!='candidate'},REQUIRED)
            self.assertEqual(sum(c['kind']=='candidate' for c in plan['cases']),5)
            self.assertEqual(sum(c['kind']=='fixed_challenge' for c in plan['cases']),24)
            self.assertEqual(sum(c['kind']=='resource_challenge' for c in plan['cases']),1)
            self.assertEqual(len({c['caseId'] for c in plan['cases']}),30)
            self.assertFalse(plan['qualificationPassed']); self.assertFalse(plan['executionPerformed'])
            self.assertFalse(plan['requiredOutcomesVerified']); self.assertFalse(plan['actualAggregateStorageEnforced'])

    def test_successful_candidate_cases_require_replay_and_conflict_without_extra_admission(self):
        candidates=[c for c in self.plan()['cases'] if c['kind']=='candidate']
        positive,=[c for c in candidates if c['domainCase']['expected']['staticOutcome']=='applicable']
        self.assertEqual(positive['terminalProbes'],['exact_parent_replay','changed_same_key_conflict'])
        self.assertEqual(positive['plannedChildOperations'],1)
        self.assertTrue(all(c['terminalProbes']==[] and c['plannedChildOperations']==0 for c in candidates if c is not positive))

    def test_parameter_only_success_does_not_bypass_combined_case_limit(self):
        with self.assertRaises(PatError) as caught:
            self.policy.generate(program(),self.bindings['gpio']['descriptor'],self.bindings)
        self.assertEqual(caught.exception.code,'PAT_IO_MATRIX_COMBINED_LIMIT')
        self.assertEqual(caught.exception.detail,dict(dimension='cases',required=37,limit=32))

    def test_sixteen_candidate_steps_and_all_challenges_share_one_operation_count(self):
        plan=self.plan(count=16)
        self.assertEqual(plan['totals'],dict(cases=30,childOperations=58,schedulerTicks=1736))
        self.assertEqual(plan['limits']['maxChildOperations'],512)

    def test_lower_case_ceiling_refuses_without_dropping_challenges(self):
        with self.assertRaises(PatError) as caught: self.plan(limits=CEILINGS|{'maxCases':29})
        self.assertEqual(caught.exception.detail,dict(dimension='cases',required=30,limit=29))

    def test_auxiliary_actors_consume_the_global_operation_ceiling(self):
        with self.assertRaises(PatError) as caught: self.plan(limits=CEILINGS|{'maxChildOperations':42})
        self.assertEqual(caught.exception.detail,dict(dimension='childOperations',required=43,limit=42))
        self.assertEqual(self.plan(limits=CEILINGS|{'maxChildOperations':43})['totals']['childOperations'],43)

    def test_tick_reservations_cover_all_trials(self):
        with self.assertRaises(PatError) as caught: self.plan(limits=CEILINGS|{'maxSchedulerTicks':1675})
        self.assertEqual(caught.exception.detail,dict(dimension='schedulerTicks',required=1676,limit=1675))

    def test_limits_cannot_be_widened_or_use_numeric_aliases(self):
        for key,maximum in CEILINGS.items():
            for wrong in (maximum+1,True,float(maximum),0):
                with self.subTest(key=key,wrong=wrong):
                    with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_LIMITS'): self.plan(limits=CEILINGS|{key:wrong})

    def test_limits_are_closed(self):
        for bad in ({},CEILINGS|{'maxHiddenTrials':1}):
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_LIMITS'): self.plan(limits=bad)

    def test_serialized_plan_obeys_lower_document_and_derived_limits(self):
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_DOCUMENT_LIMIT'): self.plan(limits=CEILINGS|{'maxDocumentBytes':100})
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_DERIVED_LIMIT'): self.plan(limits=CEILINGS|{'maxDerivedBytes':100})

    def test_all_cases_reference_complete_deduplicated_artifacts(self):
        plan=self.plan(); artifacts={r['digest']:r['artifact'] for r in plan['programs']}; used=set()
        for case in plan['cases']:
            if case['kind']=='resource_challenge': used.update(a['programDigest'] for a in case['actors'].values())
            else: used.add(case['programDigest'])
        self.assertEqual(used,set(artifacts)); self.assertLess(len(artifacts),len(plan['cases']))
        self.assertEqual(artifacts[plan['artifactDigest']],program(literal=True))

    def test_fixed_timing_challenges_do_not_mutate_or_relabel_candidate(self):
        artifact=program(literal=True); before=copy.deepcopy(artifact)
        plan=self.policy.generate(artifact,self.bindings['gpio']['descriptor'],self.bindings)
        artifacts={r['digest']:r['artifact'] for r in plan['programs']}
        cases={r['definition']['scenario']:r for r in plan['cases'] if r['kind']=='fixed_challenge'}
        lease=artifacts[cases['lease_wait_equal']['programDigest']]
        self.assertEqual(lease['steps'][0]['timing']['notBeforeOffsetMs'],59998)
        self.assertEqual(lease['steps'][0]['arguments']['durationMs'],{'literal':1})
        self.assertEqual(artifact,before); self.assertNotEqual(cases['lease_wait_equal']['programDigest'],plan['artifactDigest'])

    def test_clock_and_full_read_withdrawal_cases_require_worker_extensions(self):
        plan=self.plan(); names={c['definition']['scenario'] for c in plan['cases'] if c['kind']=='fixed_challenge'}
        self.assertTrue({'wall_clock_regression','clock_epoch_mismatch','full_authority_withdrawal'}<=names)
        self.assertTrue({'clock_fault_and_new_epoch','full_read_withdrawal','group_budget_enforcement'}<=set(plan['requiredWorkerFeatures']))
        self.assertFalse(plan['implementationIdentityAttested'])

    def test_late_parent_preserves_completion_but_requires_nominal_timing_failure(self):
        case=next(c for c in self.plan()['cases'] if c.get('definition',{}).get('scenario')=='late_parent_reporting')
        self.assertEqual(case['definition']['expected']['completionContract'],'satisfied')
        self.assertIn('nominal_timing_false',case['definition']['expected']['checks'])

    def test_fault_success_requires_exact_effect_counts_and_zero_unresolved_work(self):
        cases={c['definition']['scenario']:c['definition']['expected'] for c in self.plan()['cases'] if c['kind']=='fixed_challenge'}
        self.assertEqual((cases['cancel_accepted']['activations'],cases['cancel_accepted']['completedCycles']), (0,0))
        self.assertEqual((cases['cancel_pending']['activations'],cases['cancel_pending']['completedCycles'],cases['cancel_pending']['canceledActivations']), (1,0,1))
        self.assertEqual((cases['completion_reply_lost']['activations'],cases['completion_reply_lost']['completedCycles']), (1,1))
        self.assertTrue(all(v['settledAndQuiescent'] and v['unresolvedOperations']==0 for v in cases.values()))

    def test_resource_scenario_declares_both_primitives_cross_route_and_independent_progress(self):
        case=next(c for c in self.plan()['cases'] if c['kind']=='resource_challenge'); a=case['actors']
        self.assertEqual(a['gpio']['claims'],a['alias']['claims']); self.assertNotEqual(a['gpio']['adapterId'],a['alias']['adapterId'])
        self.assertTrue(set(a['gpio']['claims'])<set(a['pwm']['claims']))
        self.assertFalse(set(a['independent']['claims'])&set(a['pwm']['claims']))
        self.assertEqual(case['definition']['actorOrder'],['gpio','independent','alias','pwm'])
        self.assertEqual(case['plannedChildOperations'],5); self.assertEqual(case['definition']['expected']['completedCycles'],4)
        self.assertIn('read_historical_gpio_while_alias_active',case['definition']['control'])
        self.assertEqual(case['definition']['probes'],[dict(name='gpio_while_pwm',actor='gpio',
            operationKey='trial:probe:gpio_busy',expectedError='RESOURCE_BUSY',expectedAdmissions=0,possibleAdmissions=1)])
        self.assertEqual(self.plan()['profile'],'hms.pat.io-combined-matrix/0.2')

    def test_omitted_or_extra_challenge_bindings_refuse(self):
        for bad in ({},self.bindings|{'hidden':self.bindings['gpio']}):
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_BINDINGS'):
                self.policy.generate(program(literal=True),self.bindings['gpio']['descriptor'],bad)

    def test_duplicate_actor_identity_refuses(self):
        bad=copy.deepcopy(self.bindings); bad['alias']=copy.deepcopy(bad['gpio'])
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_BOARD_CONTEXT'):
            self.policy.generate(program(literal=True),self.bindings['gpio']['descriptor'],bad)

    def test_different_endpoint_sessions_cannot_form_one_board_challenge(self):
        bad=copy.deepcopy(self.bindings); bad['alias']['descriptor']['endpointSession']='session:another'
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_BOARD_CONTEXT'):
            self.policy.generate(program(literal=True),self.bindings['gpio']['descriptor'],bad)

    def test_independent_pin_cannot_be_substituted_for_shared_alias(self):
        bad=copy.deepcopy(self.bindings); bad['alias'],bad['independent']=bad['independent'],bad['alias']
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_ALIAS'):
            self.policy.generate(program(literal=True),self.bindings['gpio']['descriptor'],bad)

    def test_same_route_alias_does_not_prove_cross_route_exclusion(self):
        document=copy.deepcopy(self.document)
        document['routes']['adapters']['io:routeB'].remove('sim:gpio5:other-route')
        document['routes']['adapters']['io:routeA'].append('sim:gpio5:other-route')
        document=normalize_installation(document); chosen=bindings(document)
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_ALIAS'):
            IoCombinedMatrixPolicy(document).generate(program(literal=True),chosen['gpio']['descriptor'],chosen)

    def test_target_must_be_the_explicitly_selected_challenge_binding(self):
        with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_TARGET'):
            self.policy.generate(program(literal=True),self.bindings['alias']['descriptor'],self.bindings)

    def test_explicit_cross_route_role_swap_is_supported(self):
        chosen=copy.deepcopy(self.bindings); chosen['gpio'],chosen['alias']=chosen['alias'],chosen['gpio']
        plan=self.policy.generate(program(literal=True),chosen['gpio']['descriptor'],chosen)
        resource=next(c for c in plan['cases'] if c['kind']=='resource_challenge')
        self.assertEqual(resource['actors']['gpio']['instanceId'],'sim:gpio5:other-route')

    def test_opaque_action_names_use_trusted_primitive_mapping(self):
        document=copy.deepcopy(self.document)
        for row in document['handlers']: row['actionId']='opaque_action'
        for row in document['topology']['consumers']: row['actionId']='opaque_action'
        document['initialGenerations']=generations(document['topology']); document=normalize_installation(document)
        chosen=bindings(document)
        plan=IoCombinedMatrixPolicy(document).generate(program(literal=True,action='opaque_action'),chosen['gpio']['descriptor'],chosen)
        resource=next(c for c in plan['cases'] if c['kind']=='resource_challenge')
        self.assertEqual(resource['actors']['pwm']['primitive'],'pwm_burst')
        self.assertEqual(resource['actors']['pwm']['actionId'],'opaque_action')

    def test_plan_integrity_rejects_rehashed_omissions_effects_and_success_flags(self):
        original=self.plan()
        changes=[lambda p:p['cases'].pop(),lambda p:p['cases'].reverse(),
                 lambda p:p['cases'][-1]['actors']['gpio']['claims'].clear(),
                 lambda p:p['cases'][-1]['definition']['expected'].update(activations=0),
                 lambda p:p['totals'].update(childOperations=1),lambda p:p.update(qualificationPassed=True),
                 lambda p:p['requiredWorkerFeatures'].clear(),lambda p:p.update(extra=True)]
        for change in changes:
            plan=copy.deepcopy(original); change(plan)
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                self.policy.validate(plan,program(literal=True),self.bindings['gpio']['descriptor'],self.bindings)

    def test_exact_validation_is_stable_and_input_order_independent(self):
        plan=self.plan(); reversed_bindings=dict(reversed(list(self.bindings.items())))
        same=self.policy.generate(program(literal=True),self.bindings['gpio']['descriptor'],reversed_bindings)
        self.assertEqual(plan,same)
        digest=self.policy.validate(plan,program(literal=True),self.bindings['gpio']['descriptor'],self.bindings)
        self.assertRegex(digest,'^sha256:[0-9a-f]{64}$')
        self.assertEqual(digest,self.policy.validate(same,program(literal=True),self.bindings['gpio']['descriptor'],reversed_bindings))

    def test_changed_candidate_or_limits_invalidate_old_plan(self):
        plan=self.plan()
        for value,limits in [(program(literal=True,count=2),None),(program(literal=True),CEILINGS|{'maxCases':31})]:
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                self.policy.validate(plan,value,self.bindings['gpio']['descriptor'],self.bindings,limits=limits)

    def test_returned_plan_cannot_mutate_cached_topology_or_next_generation(self):
        baseline=self.plan(); altered=self.plan()
        altered['cases'][-1]['actors']['gpio']['claims'].clear()
        altered['cases'][-1]['definition']['control'].clear(); altered['programs'][0]['artifact']['steps'].clear()
        self.assertEqual(self.plan(),baseline)

    def test_planning_and_validation_are_pure_after_trusted_construction(self):
        artifact=program(literal=True); chosen=copy.deepcopy(self.bindings); before=copy.deepcopy((artifact,chosen))
        with patch.object(builtins,'open',side_effect=AssertionError('file I/O')), \
             patch.object(sqlite3,'connect',side_effect=AssertionError('SQL')), \
             patch.object(time,'time',side_effect=AssertionError('wall clock')), \
             patch.object(time,'monotonic',side_effect=AssertionError('monotonic clock')):
            plan=self.policy.generate(artifact,chosen['gpio']['descriptor'],chosen)
            self.policy.validate(plan,artifact,chosen['gpio']['descriptor'],chosen)
        self.assertEqual((artifact,chosen),before)

    def test_plan_is_bounded_json_and_never_claims_runtime_enforcement(self):
        plan=self.plan(); encoded=canonical(plan)
        self.assertLessEqual(len(encoded),65536); self.assertEqual(json.loads(encoded),plan)
        self.assertTrue(plan['caseCountIncludesFixedChallenges']); self.assertFalse(plan['hiddenAuxiliaryActorsAllowed'])
        self.assertIn('group_wall_deadline',plan['runtimeBudgetEnforcementRequired'])
        self.assertIn('derived_closure_bytes',plan['runtimeBudgetEnforcementRequired'])
