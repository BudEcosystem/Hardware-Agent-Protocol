"""Parent semantics adversaries that still pass operation-history inspection."""
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
from hms.pat_io_operation_history import inspect_operation_history
from hms.pat_io_procedure_history import IoProcedureHistoryError, inspect_procedure_history
from test_pat_io_transcript import FIXTURES, GPIO, REOPEN, SIXTEEN, load
from test_pat_io_board_history import CANCEL, LOST, PWM, rewrite
from test_pat_io_operation_history import ACCEPTED, MISSING, REPLAY


class IoProcedureHistoryTests(unittest.TestCase):
    def inspect(self, name):
        refs, files, _, setup = load(name)
        return inspect_procedure_history(refs, files, expected_setup=setup)

    def rejected(self, name, mutate=lambda cp, t: None, code='ROW', *, edit=lambda d: None):
        refs, files, setup = rewrite(name, mutate, edit)
        # These histories pass both structural and full child-operation checks.
        self.assertTrue(inspect_operation_history(refs, files, expected_setup=setup)['operationHistoryChecked'])
        with self.assertRaises(IoProcedureHistoryError) as caught:
            inspect_procedure_history(refs, files, expected_setup=setup)
        self.assertEqual(caught.exception.code, 'PAT_IO_PROCEDURE_' + code)

    def test_all_nineteen_actual_histories_and_statuses_match(self):
        counts = {}; events = 0; absent = 0
        for fixture in json.loads((FIXTURES / 'index.json').read_bytes())['fixtures']:
            with self.subTest(method=fixture['method']):
                result = self.inspect(fixture['method']); status = result['derivedProcedure']
                self.assertTrue(result['procedureHistoryChecked']); self.assertTrue(result['operationHistoryChecked'])
                for field in ('boardHistoryChecked', 'patCorrespondenceChecked', 'liveAuthorizationChecked',
                              'allFailureCausesChecked', 'independentOutcomeChecked', 'qualificationPassed'):
                    self.assertFalse(result[field])
                events += result['procedureEventsChecked']
                self.assertGreater(result['observationsChecked'], 0)
                if status is None: absent += 1
                else: counts[status['executionState']] = counts.get(status['executionState'], 0) + 1
        self.assertEqual((absent, events), (1, 105))
        self.assertEqual(counts, {'completed': 9, 'canceled': 5, 'running': 1, 'accepted': 2, 'failed': 1})

    def test_sixteen_step_sequence_advances_only_after_each_child_settles(self):
        result = self.inspect(SIXTEEN); status = result['derivedProcedure']
        self.assertEqual((status['cursor'], status['stepCount'], status['eventSequence']), (16, 16, 34))
        self.assertEqual(status['unresolvedOperations'], [])
        self.assertTrue(all(s['executionState'] == 'completed' and s['heldResources'] == 0 for s in status['steps']))

    def test_parent_cancellation_and_child_effect_are_distinct(self):
        unstarted = self.inspect(ACCEPTED)['derivedProcedure']; started = self.inspect(CANCEL)['derivedProcedure']
        self.assertEqual(unstarted['executionState'], started['executionState'])
        self.assertFalse(unstarted['mayHaveActed']); self.assertTrue(started['mayHaveActed'])
        self.assertEqual((unstarted['cursor'], started['cursor']), (0, 0))

    def test_lost_completion_reply_resumes_historical_success_without_new_child(self):
        status = self.inspect(LOST)['derivedProcedure']
        self.assertEqual((status['executionState'], status['stepCount'], status['cursor']), ('completed', 1, 1))
        self.assertEqual(status['unresolvedOperations'], [])

    def test_missing_receipt_preserves_running_parent_and_unresolved_child(self):
        status = self.inspect(MISSING)['derivedProcedure']
        self.assertEqual((status['executionState'], status['cursor']), ('running', 0))
        self.assertEqual(status['unresolvedOperations'], [status['steps'][0]['operationId']])
        self.assertEqual(status['steps'][0]['heldResources'], 1)

    def test_forged_completed_parent_cannot_hide_running_child(self):
        def mutate(cp, t):
            if any(r['state'] == 'running' for r in t['operations']):
                p = t['pr_procedures'][0]
                p.update(state='completed', reason=None, cursor=1, sequence=4)
                for seq, kind, value in [(3, 'cursor_advanced', {'cursor': 1}), (4, 'state_changed', {'state': 'completed', 'reason': None})]:
                    t['pr_events'].append({'procedure_id': p['id'], 'sequence': seq, 'time_ms': cp['wallMs'],
                        'clock_status': 'unqualified_host_clock', 'kind': kind, 'payload': canonical(value).decode()})
        def edit(doc):
            if doc['kind'] == 'trial_observation':
                p = doc['value']['procedure']
                if p: p.update(executionState='completed', cursor=1, eventSequence=4)
        self.rejected(MISSING, mutate, edit=edit)

    def test_completed_child_with_held_claim_cannot_advance_parent(self):
        def mutate(cp, t):
            releases = [e for e in t['events'] if e['kind'] == 'resources_released']
            if releases:
                op = t['operations'][0]
                t['events'] = [e for e in t['events'] if e['kind'] != 'resources_released']; op['sequence'] -= 1
                t['claims'] = [{'deployment': op['deployment'], 'resource': 'atom:pin5', 'operation_id': op['id'], 'fence': 1}]
        self.rejected(REPLAY, mutate)

    def test_parent_cursor_cannot_skip_first_running_step(self):
        def mutate(cp, t):
            if t['operations'] and t['pr_procedures'][0]['cursor'] == 0: t['pr_procedures'][0]['cursor'] = 1
        self.rejected(GPIO, mutate)

    def test_terminal_failure_cannot_be_reported_as_completed(self):
        def mutate(cp, t):
            for row in t['pr_procedures']:
                if row['state'] == 'failed': row.update(state='completed', reason=None)
        self.rejected('test_run_deadline_equality_cancels_instead_of_claiming_completion', mutate)

    def test_parent_reason_is_derived_not_trusted(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['pr_procedures'][0]['reason'] = 'PROCEDURE_DEADLINE'
        self.rejected(GPIO, mutate)

    def test_parent_cancel_flag_cannot_disappear(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['pr_procedures'][0]['cancel_requested'] = 0
        self.rejected(CANCEL, mutate)

    def test_parent_sequence_cannot_claim_unrecorded_events(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['pr_procedures'][0]['sequence'] += 1
        self.rejected(GPIO, mutate)

    def test_huge_parent_sequence_is_rejected_without_range_expansion(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['pr_procedures'][0]['sequence'] = 9007199254740991
        self.rejected(GPIO, mutate)

    def test_child_admitted_event_cannot_disappear(self):
        def mutate(cp, t):
            t['pr_events'] = [e for e in t['pr_events'] if e['kind'] != 'child_admitted']
        self.rejected(GPIO, mutate, 'EVENTS')

    def test_child_admitted_event_cannot_identify_another_operation(self):
        def mutate(cp, t):
            for e in t['pr_events']:
                if e['kind'] == 'child_admitted':
                    v = json.loads(e['payload']); v['operationId'] = 'op:' + '0' * 32; e['payload'] = canonical(v).decode()
        self.rejected(GPIO, mutate, 'EVENTS')

    def test_accepted_event_step_count_is_independently_derived(self):
        def mutate(cp, t):
            for e in t['pr_events']:
                if e['kind'] == 'accepted':
                    v = json.loads(e['payload']); v['stepCount'] += 1; e['payload'] = canonical(v).decode()
        self.rejected(GPIO, mutate, 'EVENTS')

    def test_historical_event_payload_cannot_change(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['pr_events'][0]['payload'] = '{}'
        self.rejected(GPIO, mutate, 'EVENTS')

    def test_event_timestamp_must_equal_its_phase_clock(self):
        def mutate(cp, t):
            for e in t['pr_events']: e['time_ms'] += 1
        self.rejected(GPIO, mutate, 'EVENTS')

    def test_event_clock_quality_cannot_be_relabelled(self):
        def mutate(cp, t):
            for e in t['pr_events']: e['clock_status'] = 'physical_verified'
        self.rejected(GPIO, mutate, 'EVENTS')

    def test_reopen_requires_interruption_of_active_parent(self):
        def mutate(cp, t):
            if cp['label'] == 'after_reopen': t['pr_procedures'][0].update(state='running', reason=None)
        self.rejected(REOPEN, mutate)

    def test_resume_failure_code_must_match_retained_dependency(self):
        def edit(doc):
            if doc['kind'] == 'call_failed' and doc['value']['label'] == 'resume': doc['value']['code'] = 'IO_SESSION_CHANGED'
        self.rejected(REOPEN, code='RESUME_CAUSE', edit=edit)

    def test_stale_session_resume_refusal_is_derived_from_remaining_intent(self):
        def edit(doc):
            if doc['kind'] == 'call_failed' and doc['value']['label'] == 'resume': doc['value']['code'] = 'PROCEDURE_DEPENDENCY_UNRESOLVED'
        self.rejected('test_reopen_accepted_refuses_stale_session_without_rebinding', code='RESUME_CAUSE', edit=edit)

    def test_failed_resume_cannot_be_forged_as_success(self):
        def edit(doc):
            v = doc['value']
            if doc['kind'] == 'call_failed' and v['label'] == 'resume':
                doc['kind'] = 'call_returned'; doc['value'] = {k: v[k] for k in ('phase', 'label', 'clock')}; doc['value']['result'] = {}
            elif doc['kind'] == 'checkpoint' and v['label'] == 'resume:after_error': v['label'] = 'resume:after'
        self.rejected(REOPEN, code='RESUME_CAUSE', edit=edit)

    def test_cancel_delivery_uses_pre_cancel_child_state(self):
        def mutate(cp, t):
            for row in t['pr_procedures']:
                v = json.loads(row['cancel_delivery'])
                if v['status'] == 'recorded': v['status'] = 'already_terminal'; row['cancel_delivery'] = canonical(v).decode()
            for e in t['pr_events']:
                if e['kind'] == 'cancel_delivery':
                    v = json.loads(e['payload']); v['status'] = 'already_terminal'; e['payload'] = canonical(v).decode()
        def edit(doc):
            if doc['kind'] == 'call_returned' and doc['value']['label'] == 'cancel':
                doc['value']['result']['delivery']['status'] = 'already_terminal'
        self.rejected(ACCEPTED, mutate, 'CALL_PROJECTION', edit=edit)

    def test_cancel_reply_cannot_change_child_identity(self):
        def edit(doc):
            if doc['kind'] == 'call_returned' and doc['value']['label'] == 'cancel':
                doc['value']['result']['delivery']['operationId'] = 'op:' + '0' * 32
        self.rejected(CANCEL, code='CALL_PROJECTION', edit=edit)

    def test_replay_reply_cannot_hide_child_event_sequence(self):
        def edit(doc):
            if doc['kind'] == 'call_returned' and doc['value']['label'] == 'submit':
                for step in doc['value']['result']['steps']:
                    if step['operationId']: step['eventSequence'] = 0
        self.rejected(REPLAY, code='CALL_PROJECTION', edit=edit)

    def test_resume_reply_cannot_claim_physical_verification(self):
        def edit(doc):
            if doc['kind'] == 'call_returned' and doc['value']['label'] == 'resume':
                doc['value']['result']['aggregateVerification'] = 'verified'
        self.rejected(LOST, code='CALL_PROJECTION', edit=edit)

    def test_drive_return_cannot_invent_a_success_report(self):
        def edit(doc):
            if doc['kind'] == 'call_returned' and doc['value']['label'].startswith('drive:'): doc['value']['result'] = {'passed': True}
        self.rejected(GPIO, code='CALL_PROJECTION', edit=edit)

    def test_final_status_cannot_claim_completion_for_running_parent(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation': doc['value']['procedure']['executionState'] = 'completed'
        self.rejected(MISSING, code='OBSERVATION', edit=edit)

    def test_final_unresolved_list_cannot_discard_held_claim(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation': doc['value']['unresolvedOperations'] = []
        self.rejected(MISSING, code='OBSERVATION', edit=edit)

    def test_final_operation_order_is_admission_order(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation': doc['value']['operationIds'].reverse()
        self.rejected(GPIO, code='OBSERVATION', edit=edit)

    def test_final_step_projection_cannot_erase_possible_effect(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation':
                for step in doc['value']['procedure']['steps']: step['mayHaveActed'] = False
        self.rejected(CANCEL, code='OBSERVATION', edit=edit)

    def test_final_status_extra_success_flag_is_rejected(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation': doc['value']['procedure']['qualified'] = True
        self.rejected(GPIO, code='OBSERVATION', edit=edit)

    def test_pure_inspection_imports_no_producer_and_does_not_mutate_input(self):
        refs, files, _, setup = load(PWM)
        source = Path(__file__).parents[1] / 'hms/pat_io_procedure_history.py'
        imports = {n.module for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imports, {'__future__', 'contracts', 'pat_io_board_history', 'pat_io_operation_history', 'pat_io_transcript'})
        before = copy.deepcopy((refs, files, setup))
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), \
             patch.object(Path, 'open', side_effect=AssertionError('path')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('sqlite')), \
             patch.object(time, 'time', side_effect=AssertionError('clock')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            result = inspect_procedure_history(refs, files, expected_setup=setup)
        self.assertTrue(result['procedureHistoryChecked']); self.assertEqual((refs, files, setup), before)
