"""Acquired recovery histories and rehashed attacks on fault/cause composition."""
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
from hms.pat_io_authorized_history import inspect_authorized_history
from hms.pat_io_board_history import inspect_board_history
from hms.pat_io_operation_history import inspect_operation_history
from hms.pat_io_recovery_history import inspect_recovery_history
from hms.pat_io_transcript import _read
import test_pat_io_configuration_history as configuration_tests
from test_pat_io_authorized_history import terminal

FIXTURES=Path(__file__).parent/'data/io-recovery'
GPIO='test_unknown_gpio_acceptance_stops_without_running_remaining_step'
PWM='test_unknown_pwm_acceptance_stops_all_claimed_outputs'
DUE='test_unknown_pending_at_due_time_stops_instead_of_completing'
WITHDRAW='test_unknown_pending_recovery_survives_invocation_withdrawal'
CANCEL='test_cancel_request_does_not_relabel_unknown_pending_recovery'
FINISH='test_pending_finish_failure_keeps_output_active_until_recovery'
STOP_FAIL='test_failed_recovery_stop_retains_active_output_and_claims'
SETTLE_LOSS='test_recovery_stop_survives_authority_reconciliation_reply_loss'
METHODS=(GPIO,PWM,DUE,WITHDRAW,CANCEL,FINISH,STOP_FAIL,SETTLE_LOSS)


def load(name=GPIO):
    with patch.object(configuration_tests,'FIXTURES',FIXTURES):
        case=configuration_tests.load(name)
    fixture,=[f for f in json.loads((FIXTURES/'index.json').read_bytes())['fixtures'] if f['method']==name]
    case['expected_faults']=fixture['expectedFaults']
    return case


def rewrite(name=GPIO, **changes):
    with patch.object(configuration_tests,'FIXTURES',FIXTURES):
        case=configuration_tests.rewrite(name,**changes)
    case['expected_faults']=load(name)['expected_faults']
    return case


def at(value, phase, suffix='after'):
    return (value['phase'],value['label'])==(phase,'drive:adapters:'+suffix)


class IoRecoveryHistoryTests(unittest.TestCase):
    def rejected(self, case, code):
        _read(case['references'],case['files'],case['expected_setup'])
        with self.assertRaises(ValueError) as caught: inspect_recovery_history(**case)
        self.assertEqual(caught.exception.code,code)

    def test_all_eight_actual_recoveries_match_trusted_faults_and_full_histories(self):
        totals=[0,0,0]; faults=stops=settlements=guards=0; parents={}
        for name in METHODS:
            with self.subTest(method=name):
                result=inspect_recovery_history(**load(name))
                for key in ('trustedFaultPlanMatched','pendingRecoveryChecked','configurationHistoryChecked','trustedGrantPlanMatched',
                            'patCorrespondenceChecked','boardHistoryChecked','operationHistoryChecked','procedureHistoryChecked'):
                    self.assertTrue(result[key])
                for key in ('configurationAttested','compilerIdentityAttested','observationSampleSemanticsChecked',
                            'staticTimingPolicyChecked','allFaultScenariosChecked','independentOutcomeChecked','qualificationPassed'):
                    self.assertFalse(result[key])
                self.assertTrue(result['board']['modeledBoardIdle'])
                self.assertEqual(result['operations']['operationsChecked'],1)
                self.assertEqual(result['operations']['unresolvedOperationIds'],[])
                self.assertEqual(result['operations']['heldClaims'],0)
                for row in result['board']['instances']:
                    for i,key in enumerate(('activations','completedCycles','canceledActivations')):totals[i]+=row[key]
                faults+=len(result['faultsChecked']);stops+=result['recoveryStopsChecked']
                settlements+=len(result['settlementsChecked']);guards+=len(result['guardsChecked'])
                state=result['procedures']['derivedProcedure']['executionState'];parents[state]=parents.get(state,0)+1
        self.assertEqual(totals,[8,0,8]);self.assertEqual((faults,stops,settlements,guards),(10,8,8,10))
        self.assertEqual(parents,dict(failed=7,canceled=1))

    def test_rewriter_preserves_all_eight_actual_streams(self):
        for name in METHODS:self.assertEqual(load(name),rewrite(name))

    def test_standalone_apis_cannot_accept_unjoined_recovery(self):
        for name in METHODS:
            case=load(name);case.pop('expected_faults')
            with self.assertRaisesRegex(ValueError,'PAT_IO_AUTHORIZED_PENDING_RECOVERY_UNSUPPORTED'):
                inspect_authorized_history(**case)
            with self.assertRaisesRegex(ValueError,'PAT_IO_HISTORY_CAUSE_UNSUPPORTED'):
                inspect_board_history(case['references'],case['files'],expected_setup=case['expected_setup'])

    def test_fault_plan_requires_closed_typed_bounded_supported_schedule(self):
        original=load(STOP_FAIL)
        changes=[lambda p:p.update(profile='untrusted'),lambda p:p.update(extra=True),lambda p:p.update(faults=[]),
            lambda p:p.update(faults=p['faults']*9),lambda p:p['faults'].reverse(),
            lambda p:p['faults'][1].update(phase=4),lambda p:p['faults'][0].update(phase=True),
            lambda p:p['faults'][0].update(phase=2049),lambda p:p['faults'][0].update(occurrences=2),
            lambda p:p['faults'][0].update(occurrences=True),lambda p:p['faults'][0].update(label='drive:cycle'),
            lambda p:p['faults'][0].update(point='unreviewed:point'),lambda p:p['faults'][0].update(code='unreviewed:code'),
            lambda p:p['faults'][0].update(exception='ValueError'),lambda p:p['faults'][0].update(extra=True)]
        for i,change in enumerate(changes):
            with self.subTest(case=i):
                case=copy.deepcopy(original);change(case['expected_faults']);self.rejected(case,'PAT_IO_RECOVERY_TRUSTED_PLAN')

    def test_omitted_activation_loss_is_not_inferred_from_reported_unknown(self):
        case=load(STOP_FAIL);case['expected_faults']['faults'].pop(0)
        self.rejected(case,'PAT_IO_RECOVERY_UNKNOWN_PHASE')

    def test_unused_future_fault_cannot_silently_pass(self):
        case=load();case['expected_faults']['faults'][0]['phase']=999
        self.rejected(case,'PAT_IO_RECOVERY_UNUSED_FAULT')

    def test_fault_cannot_be_attached_to_a_different_call(self):
        case=load();case['expected_faults']['faults'][0]['phase']=3
        self.rejected(case,'PAT_IO_RECOVERY_FAULT_PHASE')

    def test_swallowed_begin_fault_must_retain_the_actual_engine_return(self):
        def edit(doc):
            if doc['kind']=='call_returned' and doc['value']['phase']==4:doc['value']['result']={'invented':True}
        self.rejected(rewrite(edit=edit),'PAT_IO_RECOVERY_FAULT_RETURN')

    def test_failed_stop_must_retain_the_scheduled_error(self):
        def edit(doc):
            if doc['kind']=='call_failed':doc['value']['code']='injected:wrong_failure'
        self.rejected(rewrite(STOP_FAIL,edit=edit),'PAT_IO_RECOVERY_FAULT_RETURN')

    def test_unplanned_error_cannot_excuse_a_recovery_phase(self):
        def edit(doc):
            v=doc['value']
            if doc['kind']=='call_returned' and v['phase']==5:
                doc['kind']='call_failed';v.pop('result');v.update(exception='JournalError',code='injected:unplanned')
            elif doc['kind'] in {'checkpoint','snapshot'} and at(v,5):v['label']='drive:adapters:after_error'
        self.rejected(rewrite(edit=edit),'PAT_IO_RECOVERY_UNPLANNED_FAILURE')

    def test_unknown_reason_must_match_the_trusted_interruption_point(self):
        def change(v,t):
            for row in t['events']:
                if row['kind']=='outcome_unknown':row['payload']=canonical({'reason':'io_completion_unknown'}).decode()
        self.rejected(rewrite(legacy=change),'PAT_IO_RECOVERY_UNKNOWN_CAUSE')

    def test_missing_unknown_event_cannot_be_reconstructed_from_state(self):
        self.rejected(rewrite(legacy=lambda v,t:t.update(events=[r for r in t['events'] if r['kind']!='outcome_unknown'])),
                      'PAT_IO_RECOVERY_UNKNOWN_CAUSE')

    def test_lost_activation_reply_still_requires_its_pending_board_receipt(self):
        self.rejected(rewrite(legacy=lambda v,t:t.update(io_receipts=[]) if at(v,4) else None),'PAT_IO_RECOVERY_FAULT_RESULT')

    def test_begin_reply_loss_cannot_claim_authority_already_retained_the_receipt(self):
        def change(v,t):
            if at(v,4):t['io_authority_receipts']=copy.deepcopy(t['io_receipt_versions'])
        self.rejected(rewrite(legacy=change),'PAT_IO_RECOVERY_BEGIN_LOSS')

    def test_activation_loss_must_keep_original_authority_claims(self):
        self.rejected(rewrite(legacy=lambda v,t:t.update(claims=[]) if at(v,4) else None),'PAT_IO_RECOVERY_FAULT_CLAIMS')

    def test_failed_finish_cannot_change_board_state_or_effect_counts(self):
        def change(v,t):
            if at(v,5,'after_error'):t['io_effects'][0]['activations']+=1
        self.rejected(rewrite(STOP_FAIL,legacy=change),'PAT_IO_RECOVERY_UNCOMMITTED_BOARD_CHANGED')

    def test_failed_finish_cannot_release_authority_claims(self):
        self.rejected(rewrite(FINISH,legacy=lambda v,t:t.update(claims=[]) if at(v,5,'after_error') else None),
                      'PAT_IO_RECOVERY_FAULT_CLAIMS')

    def test_repeated_unknown_during_failed_recovery_is_not_another_activation_loss(self):
        def change(v,t):
            if at(v,5,'after_error'):
                row=copy.deepcopy(next(r for r in t['events'] if r['kind']=='outcome_unknown'))
                row['sequence']+=1;t['events'].append(row);t['operations'][0]['sequence']+=1
        self.rejected(rewrite(STOP_FAIL,legacy=change),'PAT_IO_RECOVERY_UNCOMMITTED_AUTHORITY_CHANGED')

    def test_reconciliation_failure_cannot_claim_authority_settlement(self):
        self.rejected(rewrite(SETTLE_LOSS,legacy=lambda v,t:t['operations'][0].update(state='failed') if at(v,5,'after_error') else None),
                      'PAT_IO_RECOVERY_FAULT_AUTHORITY')

    def test_reconciliation_failure_cannot_release_claims_early(self):
        self.rejected(rewrite(SETTLE_LOSS,legacy=lambda v,t:t.update(claims=[]) if at(v,5,'after_error') else None),
                      'PAT_IO_RECOVERY_FAULT_CLAIMS')

    def test_reconciliation_failure_requires_retained_terminal_authority_receipt(self):
        self.rejected(rewrite(SETTLE_LOSS,legacy=lambda v,t:t.update(io_authority_receipts=[]) if at(v,5,'after_error') else None),
                      'PAT_IO_RECOVERY_RECONCILIATION_RECEIPT')

    def test_successful_recovery_cannot_leave_an_event_valid_unknown_state(self):
        remembered={}
        def change(v,t):
            if at(v,5,'before'):
                remembered.update({k:copy.deepcopy(t[k]) for k in ('operations','events','claims')})
            elif remembered:
                for k,rows in remembered.items():t[k]=copy.deepcopy(rows)
        case=rewrite(legacy=change)
        self.assertTrue(inspect_operation_history(case['references'],case['files'],expected_setup=case['expected_setup'])['operationHistoryChecked'])
        self.rejected(case,'PAT_IO_RECOVERY_SETTLEMENT_REQUIRED')

    def test_successful_recovery_cannot_omit_the_authority_receipt(self):
        self.rejected(rewrite(legacy=lambda v,t:t.update(io_authority_receipts=[]) if at(v,5) else None),
                      'PAT_IO_RECOVERY_SETTLEMENT_RECEIPT')

    def test_successful_recovery_cannot_leave_the_output_pending(self):
        remembered={}
        def change(v,t):
            if at(v,5,'before'):remembered.update({k:copy.deepcopy(t[k]) for k in t if k.startswith('io_') and k not in {'io_dispatch_links','io_authority_receipts'}})
            elif at(v,5):t.update(copy.deepcopy(remembered))
        self.rejected(rewrite(legacy=change),'PAT_IO_RECOVERY_RECOVERY_RESULT')

    def test_due_time_does_not_change_recovery_into_completion(self):
        def change(v,t):
            terminal(t,state='completed',reason=None)
            for row in t['operations']:
                if row['state']=='failed':row['state']='completed'
        self.rejected(rewrite(DUE,legacy=change),'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_client_cancel_request_cannot_relabel_the_recovery_stop(self):
        def change(v,t):
            terminal(t,reason='client_cancel')
            for row in t['operations']:
                if row['state']=='failed':row['state']='canceled'
        self.rejected(rewrite(CANCEL,legacy=change),'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_invocation_withdrawal_cannot_relabel_the_recovery_stop(self):
        self.rejected(rewrite(WITHDRAW,legacy=lambda v,t:terminal(t,reason='authority_or_binding_lost')),
                      'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_recovery_cannot_hide_a_second_activation_in_effect_counters(self):
        def change(v,t):
            if v['label']=='test_final':next(r for r in t['io_effects'] if r['activations'])['activations']+=1
        self.rejected(rewrite(legacy=change),'PAT_IO_HISTORY_COUNTERS')

    def test_pwm_recovery_must_restore_every_claimed_output(self):
        def change(v,t):
            receipts=[json.loads(r['document']) for r in t['io_receipts'] if r['state']=='canceled']
            if receipts:
                states=receipts[0]['activeState'];row=next(r for r in t['io_resources'] if r['resource'] in states)
                row['state']=canonical(states[row['resource']]).decode()
        self.rejected(rewrite(PWM,legacy=change),'PAT_IO_HISTORY_RESOURCES')

    def test_parent_cancellation_cannot_be_reported_as_child_success(self):
        self.rejected(rewrite(CANCEL,legacy=lambda v,t:t['pr_procedures'][0].update(state='completed',reason=None) if v['label']=='test_final' else None),
                      'PAT_IO_PROCEDURE_ROW')

    def test_full_read_withdrawal_remains_explicitly_unsupported(self):
        def change(v,t,r):
            if v['phase']>=5:
                t['reg_grants']=[];next(row for row in t['reg_meta'] if row['key']=='revision')['value']='14'
        case=rewrite(WITHDRAW,mutate=change);case['expected_authority']['grantChanges'][0]['grants']=[]
        self.rejected(case,'PAT_IO_AUTHORIZED_READ_WITHDRAWAL_UNSUPPORTED')

    def test_inspection_has_no_io_and_preserves_inputs(self):
        case=load(SETTLE_LOSS);before=copy.deepcopy(case)
        with patch.object(builtins,'open',side_effect=AssertionError('file')),patch.object(Path,'read_bytes',side_effect=AssertionError('file')),patch.object(sqlite3,'connect',side_effect=AssertionError('SQL')),patch.object(time,'monotonic',side_effect=AssertionError('clock')):
            self.assertTrue(inspect_recovery_history(**case)['pendingRecoveryChecked'])
        self.assertEqual(case,before)

    def test_imports_are_only_contracts_and_independent_readers(self):
        tree=ast.parse((Path(__file__).parents[1]/'hms/pat_io_recovery_history.py').read_text())
        self.assertEqual({n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)},
            {'__future__','contracts','pat_io_authorized_history','pat_io_board_history','pat_io_configuration_history',
             'pat_io_correspondence','pat_io_operation_history','pat_io_procedure_history','pat_io_transcript'})
        self.assertFalse(any(isinstance(n,ast.Import) for n in ast.walk(tree)))
