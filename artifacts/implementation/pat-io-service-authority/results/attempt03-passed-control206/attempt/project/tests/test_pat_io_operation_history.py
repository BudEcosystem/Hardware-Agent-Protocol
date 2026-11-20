"""Actual authority histories and fully rehashed semantic adversaries."""
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
from hms.pat_io_operation_history import IoOperationHistoryError, inspect_operation_history
from hms.pat_io_transcript import inspect_transcript
from test_pat_io_transcript import FIXTURES, GPIO, REOPEN, load
from test_pat_io_board_history import CANCEL, LOST, PWM, digest, rewrite, tables_at

ACCEPTED = 'test_cancel_accepted_has_no_board_effect_but_retains_authority_floor'
MISSING = 'test_missing_current_receipt_remains_unresolved'
REPLAY = 'test_exact_parent_replay_does_not_repeat_effect_or_admission'


def payload(row, change):
    value = json.loads(row['payload']); change(value)
    row['payload'] = canonical(value).decode()


class IoOperationHistoryTests(unittest.TestCase):
    def rejected(self, name, mutate, code):
        refs, files, setup = rewrite(name, mutate)
        self.assertTrue(inspect_transcript(refs, files, expected_setup=setup)['serializationChecked'])
        with self.assertRaises(IoOperationHistoryError) as caught:
            inspect_operation_history(refs, files, expected_setup=setup)
        self.assertEqual(caught.exception.code, 'PAT_IO_OPERATION_' + code)

    def inspect(self, name):
        refs, files, _, setup = load(name)
        return inspect_operation_history(refs, files, expected_setup=setup)

    def test_all_nineteen_actual_authority_histories_preserve_one_unresolved(self):
        catalog = json.loads((FIXTURES / 'index.json').read_bytes()); totals = [0, 0, 0, 0]
        for fixture in catalog['fixtures']:
            with self.subTest(method=fixture['method']):
                result = self.inspect(fixture['method'])
                self.assertTrue(result['operationHistoryChecked'])
                for key in ('boardHistoryChecked', 'procedureSemanticsChecked', 'liveAuthorizationChecked',
                            'patCorrespondenceChecked', 'independentOutcomeChecked', 'qualificationPassed'):
                    self.assertFalse(result[key])
                totals[0] += result['operationsChecked']; totals[1] += result['eventsChecked']
                totals[2] += result['heldClaims']; totals[3] += len(result['unresolvedOperationIds'])
        self.assertEqual(totals, [32, 156, 1, 1])

    def test_accepted_cancel_keeps_fence_without_dispatch_or_release_event(self):
        result = self.inspect(ACCEPTED)
        self.assertEqual([r['kind'] for r in result['transitions']], ['accepted', 'canceled_before_dispatch'])
        self.assertEqual(result['resourceFloors'], [{'resource': 'atom:pin5', 'fence': 1}])
        self.assertEqual(result['heldClaims'], 0)

    def test_missing_board_current_receipt_does_not_clear_authority_claim(self):
        result = self.inspect(MISSING)
        self.assertEqual((result['heldClaims'], len(result['unresolvedOperationIds'])), (1, 1))
        self.assertEqual(result['transitions'][-1]['state'], 'running')
        self.assertFalse(result['independentOutcomeChecked'])

    def test_historical_completion_can_reconcile_after_owner_reopen(self):
        result = self.inspect(LOST)
        kinds = [r['kind'] for r in result['transitions']]
        self.assertIn('outcome_unknown', kinds); self.assertIn('reconciled', kinds)
        completed = next(r for r in result['transitions'] if r['kind'] == 'reconciled')
        self.assertEqual((completed['state'], completed['claimsHeld']), ('completed', 1))
        self.assertEqual(result['transitions'][-1]['claimsHeld'], 0)

    def test_exact_parent_replay_adds_no_operation_or_fence(self):
        result = self.inspect(REPLAY)
        self.assertEqual(result['operationsChecked'], 1)
        self.assertEqual(result['resourceFloors'], [{'resource': 'atom:pin5', 'fence': 1}])

    def test_lease_cannot_be_extended_with_rehashed_admission(self):
        def mutate(cp, t):
            for row in t['operations']:
                value = json.loads(row['admission']); value['lease_expires_ms'] += 1
                row['admission'] = canonical(value).decode()
        self.rejected(GPIO, mutate, 'ADMISSION')

    def test_admission_footprint_cannot_omit_a_pwm_timer(self):
        def mutate(cp, t):
            for row in t['operations']:
                value = json.loads(row['admission']); value['resources'].pop()
                row['admission'] = canonical(value).decode()
        self.rejected(PWM, mutate, 'ADMISSION')

    def test_operation_principal_must_match_trial_owner(self):
        def mutate(cp, t):
            for row in t['operations']: row['principal'] = 'other:principal'
        self.rejected(GPIO, mutate, 'OPERATION_IDENTITY')

    def test_terminal_row_without_events_cannot_claim_verified(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['operations'][0]['verification'] = 'verified'
        self.rejected(GPIO, mutate, 'STATE')

    def test_forged_owner_epoch_is_not_inferred_from_current_runtime(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['operations'][0]['owner_epoch'] += 1
        self.rejected(REOPEN, mutate, 'STATE')

    def test_canceled_before_dispatch_cannot_claim_possible_effect(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['operations'][0]['may_have_acted'] = 1
        self.rejected(ACCEPTED, mutate, 'STATE')

    def test_pending_claim_cannot_disappear(self):
        def mutate(cp, t):
            if any(r['state'] == 'running' for r in t['operations']): t['claims'] = []
        self.rejected(GPIO, mutate, 'CLAIMS')

    def test_claim_cannot_survive_completed_release(self):
        _, _, entries, _ = load(GPIO)
        final = tables_at(entries, 'test_final'); op = next(r['operation_id'] for r in final['pr_steps'] if r['ordinal'] == 1)
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                t['claims'] = [{'deployment': 'simulation:io-hub', 'resource': 'atom:pin5', 'operation_id': op, 'fence': 2}]
        self.rejected(GPIO, mutate, 'CLAIMS')

    def test_authority_floor_cannot_rollback_after_unstarted_cancel(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['resource_floors'] = []
        self.rejected(ACCEPTED, mutate, 'FLOORS')

    def test_extra_unrelated_floor_is_rejected(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                t['resource_floors'].append({'deployment': 'simulation:io-hub', 'resource': 'atom:pin6', 'fence': 1})
        self.rejected(GPIO, mutate, 'FLOORS')

    def test_fabricated_fence_two_at_first_admission_is_rejected(self):
        def mutate(cp, t):
            for table in ('claims', 'resource_floors'):
                for row in t[table]: row['fence'] += 1
        self.rejected(GPIO, mutate, 'FLOORS')

    def test_replay_mapping_cannot_disappear(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['replay_keys'].pop()
        self.rejected(GPIO, mutate, 'REPLAY')

    def test_replay_caller_key_cannot_be_replaced(self):
        def mutate(cp, t):
            for row in t['replay_keys']: row['caller_key'] = 'other:key'
        self.rejected(REPLAY, mutate, 'REPLAY')

    def test_unadmitted_suffix_keys_are_already_reserved(self):
        def mutate(cp, t):
            if t['pr_keys']: t['pr_keys'].pop()
        self.rejected(GPIO, mutate, 'RESERVATIONS')

    def test_step_request_cannot_change_independently_of_compiled_plan(self):
        def mutate(cp, t):
            if t['pr_steps']:
                row = t['pr_steps'][0]; value = json.loads(row['request']); value['operationKey'] = 'other:key'
                row['request'] = canonical(value).decode()
        self.rejected(GPIO, mutate, 'STEP_REQUEST')

    def test_linked_step_cannot_revert_to_unadmitted(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['pr_steps'][0]['operation_id'] = None
        self.rejected(GPIO, mutate, 'STEP_LINK')

    def test_namespace_expiry_is_independent_of_producer_claim(self):
        def mutate(cp, t):
            for row in t['namespaces']: row['expires_ms'] += 1
            for row in t['series']: row['last_expiry'] += 1
        self.rejected(GPIO, mutate, 'NAMESPACE')

    def test_namespace_epoch_floor_cannot_be_forged(self):
        def mutate(cp, t):
            for row in t['series']: row['floor'] = 2
        self.rejected(GPIO, mutate, 'SERIES')

    def test_authority_clock_cannot_be_in_the_future(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                next(r for r in t['meta'] if r['key'] == 'last_clock')['value'] = str(cp['wallMs'] + 1)
        self.rejected(GPIO, mutate, 'CLOCK')

    def test_event_timestamp_must_match_first_capture_clock(self):
        def mutate(cp, t):
            for row in t['events']: row['time_ms'] += 1
        self.rejected(GPIO, mutate, 'EVENT_CLOCK')

    def test_historical_event_payload_cannot_change(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['events'][0]['payload'] = '{}'
        self.rejected(GPIO, mutate, 'EVENT_CHANGED')

    def test_event_sequence_must_cover_the_operation_row(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['operations'][0]['sequence'] += 1
        self.rejected(GPIO, mutate, 'EVENT_SEQUENCE')

    def test_orphan_event_is_rejected(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                row = dict(t['events'][0]); row['operation_id'] = 'op:' + '0' * 32; t['events'].append(row)
        self.rejected(GPIO, mutate, 'EVENT_INVENTORY')

    def test_start_cannot_be_claimed_as_reconciliation(self):
        def mutate(cp, t):
            for row in t['events']:
                if row['kind'] == 'execution_evidence': row['kind'] = 'reconciled'
        self.rejected(GPIO, mutate, 'TRANSITION')

    def test_release_cannot_replace_running_evidence(self):
        def mutate(cp, t):
            for row in t['events']:
                if row['kind'] == 'execution_evidence' and json.loads(row['payload'])['state'] == 'running':
                    value = json.loads(row['payload']); row['kind'] = 'resources_released'
                    row['payload'] = canonical({'evidence': value['evidence']}).decode()
        self.rejected(GPIO, mutate, 'RELEASE')

    def test_completed_assertion_cannot_use_pending_receipt(self):
        def mutate(cp, t):
            for row in t['events']:
                value = json.loads(row['payload'])
                if row['kind'] == 'execution_evidence' and value['state'] == 'completed':
                    receipt = next(r for r in t['io_authority_receipts'] if r['operation'] == row['operation_id'] and r['sequence'] == 1)
                    value['evidence']['reference'] = 'io-receipt:' + receipt['digest'].removeprefix('sha256:')
                    row['payload'] = canonical(value).decode()
        self.rejected(GPIO, mutate, 'EVIDENCE_ASSERTION')

    def test_simulation_cannot_assert_physical_verification(self):
        def mutate(cp, t):
            for row in t['events']:
                if row['kind'] == 'execution_evidence':
                    payload(row, lambda v: v['evidence']['assertions'].append('physical_verified'))
        self.rejected(GPIO, mutate, 'EVIDENCE')

    def test_receipt_reference_cannot_be_invented(self):
        def mutate(cp, t):
            for row in t['events']:
                if row['kind'] == 'execution_evidence':
                    payload(row, lambda v: v['evidence'].update(reference='io-receipt:' + '0' * 64))
        self.rejected(GPIO, mutate, 'EVIDENCE_REFERENCE')

    def test_dispatch_link_cannot_forge_its_fence_with_a_fresh_digest(self):
        def mutate(cp, t):
            for row in t['io_dispatch_links']:
                value = json.loads(row['document']); value['claims'][0]['fence'] += 1
                row['document'] = canonical(value).decode(); row['digest'] = digest(b'HMS-SYNTHETIC-IO-DISPATCH-v1', value)
        self.rejected(GPIO, mutate, 'DISPATCH_LINK')

    def test_reopen_must_record_unknown_for_previously_running_operation(self):
        def mutate(cp, t):
            if cp['label'] == 'after_reopen':
                t['events'] = [e for e in t['events'] if e['kind'] != 'recovery_unknown']
                t['operations'][0]['sequence'] -= 1; t['operations'][0]['state'] = 'running'
        self.rejected(REOPEN, mutate, 'RECOVERY')

    def test_canceled_state_requires_prior_cancel_event_or_matching_receipt(self):
        def mutate(cp, t):
            for row in t['events']:
                if row['kind'] == 'execution_evidence' and json.loads(row['payload'])['state'] == 'completed':
                    def change(value):
                        value['state'] = 'canceled'; value['evidence']['assertions'] = ['terminated']
                    payload(row, change)
        self.rejected(GPIO, mutate, 'EVIDENCE_ASSERTION')

    def test_false_producer_parent_status_does_not_settle_authority(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation' and doc['value']['procedure']:
                doc['value']['procedure']['executionState'] = 'completed'
        refs, files, setup = rewrite(MISSING, edit_record=edit)
        result = inspect_operation_history(refs, files, expected_setup=setup)
        self.assertEqual(result['heldClaims'], 1); self.assertFalse(result['procedureSemanticsChecked'])

    def test_pure_inspection_has_no_io_runtime_import_or_input_mutation(self):
        refs, files, _, setup = load(PWM)
        source = Path(__file__).parents[1] / 'hms/pat_io_operation_history.py'
        imports = {n.module for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imports, {'__future__', 'contracts', 'pat_io_board_history', 'pat_io_transcript', 'resource_topology'})
        before = copy.deepcopy((refs, files, setup))
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), \
             patch.object(Path, 'open', side_effect=AssertionError('path')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('sqlite')), \
             patch.object(time, 'time', side_effect=AssertionError('clock')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            result = inspect_operation_history(refs, files, expected_setup=setup)
        self.assertTrue(result['operationHistoryChecked']); self.assertEqual((refs, files, setup), before)
