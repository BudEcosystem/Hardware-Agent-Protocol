"""Actual captures plus rehashed attacks on permission/stop/settlement composition."""
import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_io_authorized_history import inspect_authorized_history
from hms.pat_io_board_history import inspect_board_history
from hms.pat_io_configuration_history import inspect_configuration_history
from hms.pat_io_transcript import _read
import test_pat_io_configuration_history as configuration_tests

FIXTURES = Path(__file__).parent/'data/io-active'
GPIO = 'test_active_gpio_revocation_stops_and_prevents_remaining_step'
PWM = 'test_active_pwm_revocation_restores_all_claimed_outputs'
DUE = 'test_active_revocation_at_due_time_precedes_completion'
STOP_LOSS = 'test_committed_revocation_stop_survives_authority_reply_loss'
COMPLETED = 'test_completed_effect_reconciles_after_permission_withdrawal'
CANCEL = 'test_prior_cancel_request_keeps_its_cause_after_revocation'
METHODS = (GPIO,PWM,DUE,STOP_LOSS,COMPLETED,CANCEL)


def load(name=GPIO):
    with patch.object(configuration_tests,'FIXTURES',FIXTURES):
        return configuration_tests.load(name)


def rewrite(name=GPIO, **changes):
    with patch.object(configuration_tests,'FIXTURES',FIXTURES):
        return configuration_tests.rewrite(name,**changes)


def terminal(tables, *, state='canceled', reason='client_cancel'):
    """Rehash altered inner receipts as well as the outer page references."""
    for table in ('io_receipts','io_receipt_versions','io_authority_receipts'):
        for row in tables[table]:
            value = json.loads(row['document'])
            if value['sequence'] != 2: continue
            value['state'] = state
            value['result'].update(cycleCompleted=state=='completed',reason=reason)
            row['document'] = canonical(value).decode()
            row['digest'] = 'sha256:'+hashlib.sha256(b'HMS-SYNTHETIC-IO-RECEIPT-v1\0'+canonical(value)).hexdigest()
            if 'state' in row: row['state'] = state


class IoAuthorizedHistoryTests(unittest.TestCase):
    def rejected(self, case, code):
        # Attacks must survive serialization and checkpoint association first.
        _read(case['references'],case['files'],case['expected_setup'])
        with self.assertRaises(ValueError) as caught:
            inspect_authorized_history(**case)
        self.assertEqual(caught.exception.code,code)

    def test_all_six_actual_histories_compose_without_qualification(self):
        totals=[0,0,0]; causes=guards=0; parents={}
        for name in METHODS:
            with self.subTest(method=name):
                result=inspect_authorized_history(**load(name))
                for key in ('configurationHistoryChecked','trustedGrantPlanMatched','patCorrespondenceChecked',
                            'activeRevocationChecked','boardHistoryChecked','operationHistoryChecked','procedureHistoryChecked'):
                    self.assertTrue(result[key])
                for key in ('configurationAttested','compilerIdentityAttested','observationSampleSemanticsChecked',
                            'staticTimingPolicyChecked','allFaultScenariosChecked','independentOutcomeChecked','qualificationPassed'):
                    self.assertFalse(result[key])
                self.assertTrue(result['board']['modeledBoardIdle'])
                self.assertEqual(result['operations']['heldClaims'],0)
                self.assertEqual(result['operations']['unresolvedOperationIds'],[])
                self.assertEqual(result['operations']['operationsChecked'],1)
                for instance in result['board']['instances']:
                    for i,key in enumerate(('activations','completedCycles','canceledActivations')): totals[i]+=instance[key]
                causes+=result['permissionStopsChecked']; guards+=len(result['guardsChecked'])
                state=result['procedures']['derivedProcedure']['executionState']; parents[state]=parents.get(state,0)+1
        self.assertEqual(totals,[6,1,5]); self.assertEqual((causes,guards),(4,6))
        self.assertEqual(parents,dict(failed=4,completed=1,canceled=1))

    def test_ordinary_gpio_pwm_reopen_and_sixteen_steps_still_compose(self):
        for name in (configuration_tests.GPIO,'test_configuration_pwm_retains_typed_bindings_and_routes',
                     configuration_tests.REOPEN,'test_configuration_sixteen_steps_stay_within_original_shared_limits'):
            with self.subTest(method=name):
                result=inspect_authorized_history(**configuration_tests.load(name))
                self.assertEqual(result['permissionStopsChecked'],0)
                self.assertTrue(result['boardHistoryChecked'])

    def test_rewriter_preserves_all_six_actual_streams(self):
        for name in METHODS:
            self.assertEqual(load(name),rewrite(name))

    def test_standalone_configuration_api_still_refuses_active_withdrawal(self):
        for name in METHODS:
            with self.assertRaisesRegex(ValueError,'PAT_IO_CONFIGURATION_ACTIVE_REVOCATION_UNSUPPORTED'):
                inspect_configuration_history(**load(name))

    def test_standalone_board_api_cannot_trust_an_unjoined_permission_cause(self):
        for name in (GPIO,PWM,DUE,STOP_LOSS):
            case=load(name)
            with self.assertRaisesRegex(ValueError,'PAT_IO_HISTORY_CAUSE_UNSUPPORTED'):
                inspect_board_history(case['references'],case['files'],expected_setup=case['expected_setup'])

    def test_reported_permission_stop_requires_actual_trusted_permission_loss(self):
        grants=load()['expected_authority']['initialGrants']
        def change(v,t,r):
            t['reg_grants']=copy.deepcopy(grants)
            next(row for row in t['reg_meta'] if row['key']=='revision')['value']='13'
        case=rewrite(mutate=change);case['expected_authority']['grantChanges']=[]
        self.assertTrue(inspect_configuration_history(**case)['configurationHistoryChecked'])
        self.rejected(case,'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_due_time_does_not_override_permission_veto(self):
        self.rejected(rewrite(DUE,legacy=lambda v,t:terminal(t,state='completed',reason=None)),
                      'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_permission_loss_cannot_be_relabelled_as_client_cancel(self):
        self.rejected(rewrite(legacy=lambda v,t:terminal(t)), 'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_prior_client_cancel_has_precedence_over_permission_loss(self):
        self.rejected(rewrite(CANCEL,legacy=lambda v,t:terminal(t,reason='authority_or_binding_lost')),
                      'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_terminal_completion_cannot_be_rewritten_after_withdrawal(self):
        self.rejected(rewrite(COMPLETED,legacy=lambda v,t:terminal(t,reason='authority_or_binding_lost') if v['phase']>=6 else None),
                      'PAT_IO_AUTHORIZED_HISTORICAL_RECEIPT_CHANGED')

    def test_suppressed_stop_cannot_leave_a_pending_receipt(self):
        def change(v,t):
            if v['phase']<5: return
            for row in t['io_receipts']:
                pending=next(r for r in t['io_receipt_versions'] if r['operation']==row['operation'] and r['sequence']==1)
                row.update(sequence=1,state='pending',document=pending['document'],digest=pending['digest'])
        self.rejected(rewrite(legacy=change),'PAT_IO_AUTHORIZED_GUARD_OUTCOME')

    def test_lost_reply_does_not_justify_early_authority_claim_release(self):
        self.rejected(rewrite(STOP_LOSS,legacy=lambda v,t:t.update(claims=[]) if v['label']=='drive:adapters:after_error' else None),
                      'PAT_IO_OPERATION_CLAIMS')

    def test_pwm_stop_must_restore_every_claimed_resource(self):
        def change(v,t):
            receipts=[json.loads(r['document']) for r in t['io_receipts'] if r['state']=='canceled']
            if receipts:
                states=receipts[0]['activeState'];row=next(r for r in t['io_resources'] if r['resource'] in states)
                row['state']=canonical(states[row['resource']]).decode()
        self.rejected(rewrite(PWM,legacy=change),'PAT_IO_HISTORY_RESOURCES')

    def test_safe_idle_receipt_cannot_hide_retained_board_ownership(self):
        held=[]
        def change(v,t):
            if t['io_owners']: held[:]=copy.deepcopy(t['io_owners'])
            elif held and any(r['state']=='canceled' for r in t['io_receipts']): t['io_owners']=copy.deepcopy(held)
        self.rejected(rewrite(legacy=change),'PAT_IO_HISTORY_OWNERS')

    def test_canceled_activation_cannot_increment_completed_counter(self):
        def change(v,t):
            for row in t['io_effects']:
                if row['canceled']: row.update(completed=row['completed']+row['canceled'],canceled=0)
        self.rejected(rewrite(legacy=change),'PAT_IO_HISTORY_COUNTERS')

    def test_failed_child_cannot_report_a_completed_parent(self):
        self.rejected(rewrite(legacy=lambda v,t:t['pr_procedures'][0].update(state='completed',reason=None) if v['label']=='test_final' else None),
                      'PAT_IO_PROCEDURE_ROW')

    def test_stale_refresh_cannot_supply_a_guard_context(self):
        def change(v,t,r):
            if v['wallMs']!=1000020 or v['label']=='drive:adapters:before' and v['phase']==5: return
            for row in t['reg_observations']:
                value=json.loads(row['document'])
                value['receipt']['ticksMs']=value['acquisition']['ticksMs']=1000019
                row['document']=canonical(value).decode()
            for row in t['reg_presence']: row['expires_ms']=1003019
        self.rejected(rewrite(DUE,mutate=change),'PAT_IO_AUTHORIZED_GUARD_CONTEXT')

    def test_unknown_pending_recovery_is_explicitly_unsupported(self):
        self.rejected(rewrite(legacy=lambda v,t:t['operations'][0].update(state='outcome_unknown') if (v['phase'],v['label'])==(5,'drive:adapters:before') else None),
                      'PAT_IO_AUTHORIZED_PENDING_RECOVERY_UNSUPPORTED')

    def test_composed_inspection_has_no_io_or_input_mutation(self):
        case=load(STOP_LOSS); before=copy.deepcopy(case)
        with patch.object(builtins,'open',side_effect=AssertionError('file')), patch.object(Path,'read_bytes',side_effect=AssertionError('file')), patch.object(sqlite3,'connect',side_effect=AssertionError('SQL')), patch.object(time,'monotonic',side_effect=AssertionError('clock')):
            self.assertEqual(inspect_authorized_history(**case)['permissionStopsChecked'],1)
        self.assertEqual(case,before)

    def test_composed_checker_imports_only_contracts_and_independent_readers(self):
        tree=ast.parse((Path(__file__).parents[1]/'hms/pat_io_authorized_history.py').read_text())
        self.assertEqual({n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)},
            {'__future__','contracts','pat_io_board_history','pat_io_configuration_history','pat_io_correspondence',
             'pat_io_operation_history','pat_io_procedure_history','pat_io_transcript'})
        self.assertFalse(any(isinstance(n,ast.Import) for n in ast.walk(tree)))
