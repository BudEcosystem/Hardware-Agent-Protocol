"""Twenty acquired lifecycle cases and rehashed independent-history adversaries."""
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
from hms.pat_io_lifecycle_semantics import inspect_lifecycle_challenge
from hms.pat_io_lifecycle_history import inspect_lifecycle_transcript
from hms.pat_io_outcome_history import inspect_trial_outcome
from hms.pat_io_configuration_history import inspect_configuration_history
from test_pat_io_conflict_history import rewrite
from test_pat_io_clock_semantics import rows,receipt_attack

FIXTURES=Path(__file__).parent/'data/io-lifecycle'


def load(name='completion_reply_lost',primitive='gpio'):
    d=FIXTURES/('test_'+primitive+'_'+name)
    m=json.loads((d/'trial-manifest.json').read_bytes());r=json.loads((d/'requested-case.json').read_bytes())
    return dict(references=m['records'],files={v['path']:(d/'trial-0/records'/v['path']).read_bytes() for v in m['records']},
        configuration=m['configuration'],configuration_files={v['path']:(d/'trial-0/configuration'/v['path']).read_bytes() for v in m['configuration']['records']},
        expected_setup=r['expectedSetup'],expected_case=r['case'],expected_authority=r['expectedAuthority'],expected_faults=r['expectedFaults'])


def structural(case):
    return inspect_lifecycle_transcript(**{k:v for k,v in case.items() if k!='expected_faults'})


def event_payload(kind,change):
    def edit(r):
        if r['kind']==kind:
            v=json.loads(r['payload']);change(v);r['payload']=canonical(v).decode()
    return rows('events',edit)


def clear_table(table):
    def edit(doc):
        if doc['kind']=='table_page' and doc['value']['table']==table:
            doc['value']['rows']=[];doc['value']['totalRows']=0
        elif doc['kind']=='checkpoint':
            for t in doc['value']['tables']:
                if t['table']==table:t['rowCount']=0
    return edit


class IoLifecycleSemanticsTests(unittest.TestCase):
    def checked(self,name,primitive):
        case=load(name,primitive);r=inspect_lifecycle_challenge(**case);h=r['history'];o=r['outcome']
        for k in ('completeHistoryChecked','expectedResponseVerified','independentOutcomeChecked',
                  'staticTimingPolicyChecked','wholeDeclaredDomainChecked','trustedFaultPlanMatched','exactControlScheduleChecked'):
            self.assertTrue(r[k])
        for k in ('configurationAttested','compilerIdentityAttested','physicalMeasurementChecked',
                  'requiredMatrixCoverageChecked','allFaultScenariosChecked','actualAggregateStorageEnforced','qualificationPassed'):
            self.assertFalse(r[k])
        e=case['expected_case']['definition']['expected']
        self.assertEqual(o['contractStatus'],'satisfied' if name=='permission_after_completion' else 'failed')
        self.assertTrue(o['settledAndQuiescent']);self.assertEqual(o['unresolvedOperationIds'],[])
        self.assertEqual(tuple(o[k]for k in ('activations','completedCycles','canceledActivations')),
            tuple(e[k]for k in ('activations','completedCycles','canceledActivations')))
        self.assertEqual(h['operations']['operationsChecked'],0 if name=='permission_before_parent' else 1)
        self.assertEqual(h['board']['receiptVersionsChecked'],2 if e['activations'] else 0)
        self.assertEqual(len(h['faultsChecked']),len(case['expected_faults']))
        self.assertEqual(len(h['settlementsChecked']),1 if name in {'pending_reply_lost','completion_reply_lost','permission_after_completion','reopen_pending'} else 0)
        ticks=structural(case)['schedulerTicks'];reopen=name in {'reopen_accepted','reopen_pending','completion_reply_lost'}
        self.assertEqual(h['sampling']['driveSampleBatches'],ticks)
        self.assertEqual(h['sampling']['samplesProduced'],8*(1+ticks+int(reopen)))
        self.assertEqual(h['configuration']['configurationSnapshots'],h['sampling']['snapshotsChecked'])
        if name=='completion_reply_lost':
            self.assertEqual(o['actualParentState'],'canceled');self.assertEqual(o['requiredCompletedSteps'],['step:0','step:1'])
            self.assertFalse(o['nominalCompletionSatisfied'])
        if name=='permission_after_completion':self.assertTrue(o['nominalCompletionSatisfied'])
        return r

    def test_gpio_cancel_accepted(self):self.checked('cancel_accepted','gpio')
    def test_pwm_cancel_accepted(self):self.checked('cancel_accepted','pwm')
    def test_gpio_cancel_pending(self):self.checked('cancel_pending','gpio')
    def test_pwm_cancel_pending(self):self.checked('cancel_pending','pwm')
    def test_gpio_reopen_accepted(self):self.checked('reopen_accepted','gpio')
    def test_pwm_reopen_accepted(self):self.checked('reopen_accepted','pwm')
    def test_gpio_reopen_pending(self):self.checked('reopen_pending','gpio')
    def test_pwm_reopen_pending(self):self.checked('reopen_pending','pwm')
    def test_gpio_completion_reply_lost(self):self.checked('completion_reply_lost','gpio')
    def test_pwm_completion_reply_lost(self):self.checked('completion_reply_lost','pwm')
    def test_gpio_pending_reply_lost(self):self.checked('pending_reply_lost','gpio')
    def test_pwm_pending_reply_lost(self):self.checked('pending_reply_lost','pwm')
    def test_gpio_permission_before_parent(self):self.checked('permission_before_parent','gpio')
    def test_pwm_permission_before_parent(self):self.checked('permission_before_parent','pwm')
    def test_gpio_permission_before_dispatch(self):self.checked('permission_before_dispatch','gpio')
    def test_pwm_permission_before_dispatch(self):self.checked('permission_before_dispatch','pwm')
    def test_gpio_permission_pending(self):self.checked('permission_pending','gpio')
    def test_pwm_permission_pending(self):self.checked('permission_pending','pwm')
    def test_gpio_permission_after_completion(self):self.checked('permission_after_completion','gpio')
    def test_pwm_permission_after_completion(self):self.checked('permission_after_completion','pwm')

    def rejected(self,case,*,structure=True):
        if structure:self.assertTrue(structural(case)['exactControlScheduleChecked'])
        with self.assertRaises(ValueError):inspect_lifecycle_challenge(**case)

    def altered(self,edit,name='completion_reply_lost'):
        self.rejected(rewrite(load(name),edit))

    def test_completion_loss_requires_separate_trusted_fault(self):
        case=load();case['expected_faults']=[];self.rejected(case)

    def test_pending_loss_requires_separate_trusted_fault(self):
        case=load('pending_reply_lost');case['expected_faults']=[];self.rejected(case)

    def test_normal_cancel_cannot_accept_an_extra_fault(self):
        case=load('cancel_pending');case['expected_faults']=load()['expected_faults'];self.rejected(case)

    def test_trusted_fault_phase_is_exact(self):
        case=load();case['expected_faults'][0]['phase']=4;self.rejected(case)

    def test_trusted_fault_point_is_exact(self):
        case=load();case['expected_faults'][0]['point']='board.finish.before_commit';self.rejected(case)

    def test_trusted_fault_occurrence_is_exact_integer(self):
        for value in (0,2,True):
            case=load();case['expected_faults'][0]['occurrences']=value;self.rejected(case)

    def test_fault_plan_cannot_include_producer_operation_identifier(self):
        case=load();case['expected_faults'][0]['operationId']='op:injected';self.rejected(case)

    def test_completion_loss_cannot_use_acceptance_unknown_cause(self):
        self.altered(event_payload('outcome_unknown',lambda v:v.update(reason='io_acceptance_unknown')))

    def test_pending_loss_cannot_use_completion_unknown_cause(self):
        self.altered(event_payload('outcome_unknown',lambda v:v.update(reason='io_completion_unknown')),'pending_reply_lost')

    def test_reopen_unknown_cannot_claim_a_lost_reply(self):
        self.altered(event_payload('recovery_unknown',lambda v:v.update(reason='io_completion_unknown')),'reopen_pending')

    def test_normal_phase_cannot_invent_an_unknown_event(self):
        def change(r):
            if r['kind']=='execution_evidence':r.update(kind='outcome_unknown',payload=canonical({'reason':'io_completion_unknown'}).decode())
        self.altered(rows('events',change),'cancel_pending')

    def test_unknown_cannot_release_all_claims(self):self.altered(clear_table('claims'))

    def test_unknown_claims_cannot_change_fence(self):self.altered(rows('claims',lambda r:r.update(fence=2)))

    def test_completed_receipt_cannot_erase_its_completed_cycle(self):
        self.rejected(receipt_attack(load(),lambda r:r['result'].update(cycleCompleted=False) if r['state']=='completed' else None))

    def test_completed_receipt_cannot_be_relabelled_as_cancellation(self):
        self.rejected(receipt_attack(load(),lambda r:r['result'].update(reason='client_cancel') if r['state']=='completed' else None))

    def test_pending_recovery_cannot_claim_client_cancellation(self):
        self.rejected(receipt_attack(load('pending_reply_lost'),lambda r:r['result'].update(reason='client_cancel') if r['state']=='canceled' else None))

    def test_new_owner_stop_cannot_claim_in_place_reconciliation(self):
        self.rejected(receipt_attack(load('reopen_pending'),lambda r:r['result'].update(reason='reconciliation_stop') if r['state']=='canceled' else None))

    def test_old_receipt_cannot_claim_new_owner(self):
        self.rejected(receipt_attack(load(),lambda r:r.update(ownerEpoch=2)))

    def test_completed_prefix_cannot_report_completed_parent(self):
        def edit(doc):
            if doc['kind']=='trial_observation':doc['value']['procedure']['executionState']='completed'
        self.altered(edit)

    def test_hidden_independent_effect_cannot_be_added(self):
        self.altered(rows('io_effects',lambda r:r.update(activations=1) if r['instance']=='sim:gpio6' else None))

    def test_final_report_cannot_hide_possible_effect(self):
        def edit(doc):
            if doc['kind']=='trial_observation':doc['value']['procedure']['mayHaveActed']=False
        self.altered(edit,'cancel_pending')

    def test_sample_cannot_claim_future_activation(self):
        def edit(r):
            d=json.loads(r['document'])
            if r['property']=='value':d['value']+=1;r['document']=canonical(d).decode()
        self.altered(rows('reg_observations',edit))

    def test_sample_clock_cannot_be_shifted(self):
        def edit(r):
            d=json.loads(r['document']);d['receipt']['ticksMs']+=1;r['document']=canonical(d).decode()
        self.altered(rows('reg_observations',edit))

    def test_binding_document_cannot_change_calibration(self):
        def edit(r):
            d=json.loads(r['document']);d['calibrationRevision']='changed';r['document']=canonical(d).decode()
        self.altered(rows('reg_bindings',edit))

    def test_admission_policy_revision_is_derived(self):
        def edit(r):
            d=json.loads(r['admission']);d['policy_revision']='registry:14';r['admission']=canonical(d).decode()
        self.altered(rows('operations',edit))

    def test_resource_floor_cannot_disappear(self):self.altered(clear_table('resource_floors'),'reopen_accepted')

    def test_old_intent_cannot_be_rebound_to_current_session(self):
        case=load();opened=[json.loads(v)['value']for v in case['files'].values() if json.loads(v)['kind']=='runtime_opened']
        def edit(r):
            d=json.loads(r['intent']);d['endpointSession']=opened[1]['session'];r['intent']=canonical(d).decode()
        self.rejected(rewrite(case,rows('operations',edit)))

    def test_pending_cancel_delivery_is_checked(self):
        def edit(doc):
            if doc['kind']=='call_returned' and doc['value']['label']=='cancel':
                doc['value']['result']['delivery']['status']='already_terminal'
        self.altered(edit,'cancel_pending')

    def test_terminal_authority_receipt_cannot_be_missing(self):
        def edit(doc):
            v=doc['value']
            if doc['kind']=='table_page' and v['table']=='io_authority_receipts' and v['totalRows']==2:
                index=v['columns'].index('sequence');v['rows']=[r for r in v['rows'] if r[index]['value']==1];v['totalRows']=1
            elif doc['kind']=='checkpoint':
                for t in v['tables']:
                    if t['table']=='io_authority_receipts' and t['rowCount']==2:t['rowCount']=1
        self.altered(edit)

    def test_active_board_owners_cannot_disappear(self):self.altered(clear_table('io_owners'),'cancel_pending')

    def test_second_step_cannot_alias_the_first_child(self):
        case=load();op=next(json.loads(v)['value']['operationIds'][0]for v in case['files'].values()if json.loads(v)['kind']=='trial_observation')
        self.rejected(rewrite(case,rows('pr_steps',lambda r:r.update(operation_id=op) if r['ordinal']==1 else None)))

    def test_declined_parent_cannot_allocate_resource_floor(self):
        case=load('permission_before_parent');deployment=case['expected_setup']['installation']['topology']['deployment']
        def edit(doc):
            v=doc['value']
            if doc['kind']=='table_page' and v['table']=='resource_floors':
                v['rows']=[[dict(type='text',value=deployment),dict(type='text',value='atom:pin5'),dict(type='integer',value=1)]];v['totalRows']=1
            elif doc['kind']=='checkpoint':
                for t in v['tables']:
                    if t['table']=='resource_floors':t['rowCount']=1
        self.rejected(rewrite(case,edit))

    def test_installed_binding_must_remain_active(self):
        self.altered(rows('reg_bindings',lambda r:r.update(active=0)))

    def test_old_generic_reader_still_refuses_unplanned_pending_recovery(self):
        case=load('pending_reply_lost')
        with self.assertRaisesRegex(ValueError,'PENDING_RECOVERY_UNSUPPORTED'):
            inspect_trial_outcome(**{k:v for k,v in case.items()if k not in {'expected_case','expected_faults'}})

    def test_old_configuration_reader_still_refuses_active_withdrawal(self):
        case=load('permission_pending')
        with self.assertRaisesRegex(ValueError,'ACTIVE_REVOCATION_UNSUPPORTED'):
            inspect_configuration_history(**{k:v for k,v in case.items()if k not in {'expected_case','expected_faults'}})

    def test_source_imports_only_independent_history_components(self):
        p=Path(__file__).parents[1]/'hms/pat_io_lifecycle_semantics.py';tree=ast.parse(p.read_bytes())
        imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertTrue(all(isinstance(n,ast.ImportFrom) and n.level==1 for n in imports))
        self.assertTrue(all(n.module=='contracts' or n.module.startswith('pat_io_') and not any(v in n.module for v in
            ('capture','worker','trials','bindings','contracts','combined_matrix')) for n in imports))

    def test_complete_reader_performs_no_io_or_clock_reads(self):
        case=load('permission_after_completion','pwm')
        def veto(*args,**kwargs):raise AssertionError('semantic checker performed I/O or sampled time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_lifecycle_challenge(**case)['expectedResponseVerified'])
