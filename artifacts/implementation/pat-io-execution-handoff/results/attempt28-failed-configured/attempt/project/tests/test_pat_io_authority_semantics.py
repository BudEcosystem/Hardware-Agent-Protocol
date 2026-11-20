"""Real retained authority histories and coherent attacks on independent semantics."""
import ast
import builtins
import copy
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_io_authority_semantics import inspect_authority_challenge
from hms.pat_io_authority_history import inspect_authority_transcript
from hms.pat_io_transcript import _read
from hms.pat_io_operation_history import _fold as operations
from hms.pat_io_procedure_history import _fold as procedures
from test_pat_io_conflict_history import rewrite
from test_pat_io_clock_semantics import rows, receipt_attack

FIXTURES=Path(__file__).parent/'data/io-authority'
BEFORE='binding_before_dispatch';PENDING='binding_pending_recovery';WITHDRAW='full_authority_withdrawal'


def load(scenario=PENDING, primitive='gpio'):
    d=FIXTURES/('test_'+primitive+'_'+scenario)
    m=json.loads((d/'trial-manifest.json').read_bytes());requested=json.loads((d/'requested-case.json').read_bytes())
    return dict(references=m['records'],files={r['path']:(d/'trial-0/records'/r['path']).read_bytes() for r in m['records']},
        configuration=m['configuration'],configuration_files={r['path']:(d/'trial-0/configuration'/r['path']).read_bytes() for r in m['configuration']['records']},
        expected_setup=requested['expectedSetup'],expected_case=requested['case'],expected_authority_change=requested['expectedAuthorityChange'])


def structural(case):
    return inspect_authority_transcript(**{k:v for k,v in case.items() if k!='expected_authority_change'})


class IoAuthoritySemanticsTests(unittest.TestCase):
    def checked(self,scenario,primitive):
        result=inspect_authority_challenge(**load(scenario,primitive));before=scenario==BEFORE;withdraw=scenario==WITHDRAW
        for k in ('completeHistoryChecked','expectedResponseVerified','independentOutcomeChecked','staticTimingPolicyChecked','wholeDeclaredDomainChecked'):
            self.assertTrue(result[k])
        for k in ('configurationAttested','compilerIdentityAttested','requiredMatrixCoverageChecked','allFaultScenariosChecked',
                  'actualAggregateStorageEnforced','physicalMeasurementChecked','qualificationPassed'):
            self.assertFalse(result[k])
        h=result['history'];o=result['outcome'];self.assertEqual(o['contractStatus'],'failed');self.assertTrue(o['settledAndQuiescent'])
        self.assertEqual(o['unresolvedOperationIds'],[])
        self.assertEqual(tuple(o[k] for k in ('activations','completedCycles','canceledActivations')),(0,0,0) if before else (1,0,1))
        self.assertEqual(h['operations']['operationsChecked'],1);self.assertEqual(h['operations']['eventsChecked'],2 if before else 6)
        self.assertEqual(h['board']['receiptVersionsChecked'],0 if before else 2)
        self.assertEqual(h['configuration']['configurationSnapshots'],14 if before else 34 if withdraw else 22)
        self.assertEqual(h['procedures']['derivedProcedure']['executionState'],'failed' if before else 'canceled')
        self.assertEqual(h['sampling']['driveSampleBatches'],3)
        self.assertEqual(h['sampling']['samplesProduced'],28 if before else 40 if withdraw else 36)
        decisions=h['configuration']['publicAndRecoveryDecisions']
        self.assertEqual(sum(r.get('cause')=='ACCESS_DENIED' for r in decisions),8 if withdraw else 0)
        self.assertEqual(sum(r.get('cause')=='BINDING_INACTIVE' for r in decisions),1 if scenario==PENDING else 0)

    def test_gpio_binding_before_dispatch(self):self.checked(BEFORE,'gpio')
    def test_pwm_binding_before_dispatch(self):self.checked(BEFORE,'pwm')
    def test_gpio_binding_pending_recovery(self):self.checked(PENDING,'gpio')
    def test_pwm_binding_pending_recovery(self):self.checked(PENDING,'pwm')
    def test_gpio_full_withdrawal(self):self.checked(WITHDRAW,'gpio')
    def test_pwm_full_withdrawal(self):self.checked(WITHDRAW,'pwm')

    def rejected(self,edit,scenario=PENDING,*,structure_passes=False):
        case=rewrite(load(scenario),edit)
        if structure_passes:self.assertTrue(structural(case)['exactAuthorityScheduleChecked'])
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_inactive_binding_cannot_be_reenabled(self):
        self.rejected(rows('reg_bindings',lambda r:r.update(active=1)),structure_passes=True)

    def test_invalidation_cannot_replace_historical_binding(self):
        def change(r):
            if r['instance']=='sim:gpio5':
                d=json.loads(r['document']);d['calibrationRevision']='synthetic:changed';r['document']=canonical(d).decode()
        self.rejected(rows('reg_binding_history',change),structure_passes=True)

    def test_binding_invalidation_cannot_leave_presence(self):
        case=load();baseline=next(json.loads(v)['value'] for v in case['configuration_files'].values()
            if json.loads(v)['kind']=='table_page' and json.loads(v)['value']['table']=='reg_presence')
        original=next(r for r in baseline['rows'] if r[0]['value']=='sim:gpio5')
        def edit(doc):
            v=doc['value']
            if doc['kind']=='table_page' and v['table']=='reg_presence' and v['totalRows']==3:
                v['rows'].append(copy.deepcopy(original));v['rows'].sort(key=lambda r:r[0]['value']);v['totalRows']=4
            elif doc['kind']=='snapshot':
                for table in v['tables']:
                    if table['table']=='reg_presence' and table['rowCount']==3:table['rowCount']=4
        changed=rewrite(case,edit);self.assertTrue(structural(changed)['exactAuthorityScheduleChecked'])
        with self.assertRaises(ValueError):inspect_authority_challenge(**changed)

    def test_invalidation_revision_must_advance_once(self):
        self.rejected(rows('reg_meta',lambda r:r.update(value='13') if r['key']=='revision' else None),structure_passes=True)

    def test_full_withdrawal_cannot_restore_admin(self):
        case=load(WITHDRAW);baseline=next(json.loads(v)['value'] for v in case['configuration_files'].values()
            if json.loads(v)['kind']=='table_page' and json.loads(v)['value']['table']=='reg_grants' and json.loads(v)['value']['totalRows']==1)
        def edit(doc):
            v=doc['value']
            if doc['kind']=='table_page' and v['table']=='reg_grants' and v['totalRows']==0:
                v['rows']=copy.deepcopy(baseline['rows']);v['totalRows']=1
            elif doc['kind']=='snapshot':
                for table in v['tables']:
                    if table['table']=='reg_grants' and table['rowCount']==0:table['rowCount']=1
        changed=rewrite(case,edit);self.assertTrue(structural(changed)['exactAuthorityScheduleChecked'])
        with self.assertRaises(ValueError):inspect_authority_challenge(**changed)

    def test_full_withdrawal_cannot_invalidate_binding_too(self):
        self.rejected(rows('reg_bindings',lambda r:r.update(active=0) if r['instance']=='sim:gpio5' else None),WITHDRAW,structure_passes=True)

    def test_trusted_change_phase_is_not_inferred_from_capture(self):
        case=load();case['expected_authority_change']['phase']+=1
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_trusted_initial_authority_cannot_be_missing(self):
        case=load(WITHDRAW);case['expected_authority_change']['initialGrants']=[]
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_trusted_revision_must_match_capture(self):
        case=load();case['expected_authority_change']['initialRegistryRevision']+=1
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_cached_inactive_sample_cannot_move_to_new_epoch(self):
        def edit(doc):
            if doc['kind']!='table_page' or doc['value']['table']!='reg_observations':return
            values=[json.loads(r[2]['value']) for r in doc['value']['rows']]
            other=next((o for o in values if o['instanceId']!='sim:gpio5' and o['receipt']['clockEpoch'].endswith(':2')),None)
            if other is None:return
            def change(r):
                if r['instance']=='sim:gpio5':
                    o=json.loads(r['document']);o['endpointSession']=other['endpointSession']
                    for key in ('acquisition','receipt'):o[key]['clockEpoch']=other['receipt']['clockEpoch']
                    r['document']=canonical(o).decode()
            rows('reg_observations',change)(doc)
        self.rejected(edit,structure_passes=True)

    def test_cached_inactive_endpoint_session_cannot_refresh(self):
        def edit(doc):
            if doc['kind']!='table_page' or doc['value']['table']!='reg_endpoint_sessions':return
            rs=doc['value']['rows'];other=next(r[1]['value'] for r in rs if r[0]['value']!='sim:gpio5')
            target=next(r for r in rs if r[0]['value']=='sim:gpio5')
            if target[1]['value']!=other:target[1]['value']=other
        self.rejected(edit,structure_passes=True)

    def test_active_samples_must_include_prior_activation(self):
        def change(r):
            if r['property']=='value':
                o=json.loads(r['document']);o['value']=0;r['document']=canonical(o).decode()
        self.rejected(rows('reg_observations',change),WITHDRAW,structure_passes=True)

    def test_historical_receipt_cannot_hide_activation(self):
        case=receipt_attack(load(),lambda r:r['result'].update(activationCommitted=False))
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_historical_stop_cannot_claim_completed_cycle(self):
        case=receipt_attack(load(WITHDRAW),lambda r:r['result'].update(cycleCompleted=True) if r['state']=='canceled' else None)
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_reopen_stop_cannot_relabel_its_original_owner(self):
        case=receipt_attack(load(),lambda r:r.update(ownerEpoch=2))
        with self.assertRaises(ValueError):inspect_authority_challenge(**case)

    def test_recovery_claim_fence_cannot_change(self):
        self.rejected(rows('claims',lambda r:r.update(fence=2)))

    def test_hidden_instance_effect_is_rejected(self):
        self.rejected(rows('io_effects',lambda r:r.update(activations=r['activations']+1) if r['instance']=='sim:gpio6' else None))

    def test_authority_floor_cannot_be_reset(self):
        self.rejected(rows('resource_floors',lambda r:r.update(fence=0)))

    def test_admission_requires_the_actual_registry_revision(self):
        def change(r):
            a=json.loads(r['admission']);a['policy_revision']='registry:14';r['admission']=canonical(a).decode()
        self.rejected(rows('operations',change),structure_passes=True)

    def test_pre_dispatch_refusal_must_match_binding_cause(self):
        def change(r):
            if r['kind']=='rejected_before_dispatch':r['payload']=canonical(dict(reason='ACCESS_DENIED')).decode()
        self.rejected(rows('events',change),BEFORE,structure_passes=True)

    def test_recovery_event_cannot_hide_owner_reopen(self):
        self.rejected(rows('events',lambda r:r.update(payload=canonical(dict(reason='client_cancel')).decode()) if r['kind']=='recovery_unknown' else None))

    def test_parent_cancel_reply_cannot_claim_new_delivery(self):
        def edit(doc):
            if doc['kind']=='call_returned' and doc['value']['label']=='cancel':doc['value']['result']['delivery']['status']='recorded'
        self.rejected(edit,WITHDRAW,structure_passes=True)

    def test_change_reply_must_not_fabricate_success_payload(self):
        def edit(doc):
            if doc['kind']=='call_returned' and doc['value']['label']=='change:authority':doc['value']['result']={'restored':True}
        self.rejected(edit,WITHDRAW,structure_passes=True)

    def test_final_privileged_observation_cannot_hide_child(self):
        def edit(doc):
            if doc['kind']=='trial_observation':doc['value']['operationIds']=[]
        self.rejected(edit,WITHDRAW,structure_passes=True)

    def test_old_private_folds_do_not_assume_new_refusal_causes(self):
        case=load(BEFORE);trace=_read(case['references'],case['files'],case['expected_setup'],authority_profile=True)
        with self.assertRaisesRegex(ValueError,'PREDISPATCH_CAUSE'):operations(trace,case['expected_setup'])
        case=load(WITHDRAW);trace=_read(case['references'],case['files'],case['expected_setup'],authority_profile=True)
        with self.assertRaisesRegex(ValueError,'SUBMIT_FAILURE_UNIMPLEMENTED'):procedures(trace)

    def test_old_transcript_profiles_refuse_authority_data(self):
        case=load()
        for flags in ({},{'clock_profile':True},{'conflict_profile':True},{'resource_profile':True}):
            with self.assertRaises(ValueError):_read(case['references'],case['files'],case['expected_setup'],**flags)

    def test_semantic_module_has_no_runtime_or_producer_import(self):
        tree=ast.parse((Path(__file__).parents[1]/'hms/pat_io_authority_semantics.py').read_bytes())
        modules={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        self.assertFalse(modules & {'pat_compiler','pat_io_trials','pat_io_authority_capture','pat_io_combined_matrix','journal','registry','synthetic_io_runtime','sqlite3'})
        self.assertEqual({a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names},{'copy'})

    def test_pure_checker_uses_no_io_or_live_time(self):
        case=load(WITHDRAW)
        def veto(*args,**kwargs):raise AssertionError('authority checker used I/O or live time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_authority_challenge(**case)['completeHistoryChecked'])
