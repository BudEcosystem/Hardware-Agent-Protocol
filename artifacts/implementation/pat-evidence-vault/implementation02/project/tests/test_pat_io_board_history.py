"""Original retained model histories and structurally valid semantic mutations."""
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
from hms.pat_io_board_history import IoHistoryError, inspect_board_history
from hms.pat_io_transcript import inspect_transcript
from test_pat_io_transcript import FIXTURES, GPIO, REOPEN, SIXTEEN, load

PWM = 'test_pwm_active_and_idle_states_are_retained'
CANCEL = 'test_cancel_pending_preserves_activation_and_proves_idle'
LOST = 'test_committed_cycle_survives_lost_reply_and_single_step_reopen'


def digest(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def tables_at(entries, label):
    docs = dict(entries)
    cp = next(d['value'] for _, d in entries if d['kind'] == 'checkpoint' and d['value']['label'] == label)
    return decode_tables(docs, cp)


def decode_tables(docs, cp):
    tables = {}
    for table in cp['tables']:
        pages = [docs[r['path']]['value'] for r in table['pages']]
        columns = pages[0]['columns']
        tables[table['table']] = [dict(zip(columns, (cell['value'] for cell in row))) for p in pages for row in p['rows']]
    return tables


def rewrite(name, mutate=lambda cp, tables: None, edit_record=lambda doc: None):
    """Rebuild canonical pages and all references/accounting after a mutation.

    This data-only writer does not call the producer, provider or history reader.
    Unchanged pages are deduplicated; row order and table counts are reconstructed.
    """
    original_refs, original_files, entries, setup = load(name)
    docs, files, refs, cache = dict(entries), {}, [], {}
    written = 0
    def add(doc, reuse=False):
        nonlocal written
        body = canonical(doc); sha = hashlib.sha256(body).hexdigest()
        if reuse and sha in cache:
            return copy.deepcopy(cache[sha])
        name = '%06d.json' % len(refs)
        ref = {'path': name, 'bytes': len(body), 'sha256': sha}
        refs.append(ref); files[name] = body; written += len(body)
        if reuse:
            cache[sha] = ref
        return copy.deepcopy(ref)
    for _, original in entries:
        if original['kind'] == 'table_page':
            continue
        doc = copy.deepcopy(original)
        edit_record(doc)
        if doc['kind'] == 'checkpoint':
            cp = doc['value']; tables = decode_tables(docs, original['value'])
            mutate(cp, tables)
            for table in cp['tables']:
                old_page = docs[table['pages'][0]['path']]['value']
                columns = old_page['columns']
                # All columns have stable SQLite types; nullable keys are derived
                # from the retained source schema rather than provider calls.
                from hms.pat_io_transcript import SCHEMAS
                types = SCHEMAS[table['store']][table['table']][1].split()
                rows = tables[table['table']]
                def sort_key(row):
                    return tuple((0, 0) if row[c] is None else (1, row[c]) if type(row[c]) is int else
                                 (3 if t.startswith('b') else 2, row[c].encode('utf-8')) for c, t in zip(columns, types))
                rows.sort(key=sort_key)
                table['rowCount'] = len(rows); table['pages'] = []
                for offset in range(0, max(1, len(rows)), 8):
                    encoded = []
                    for row in rows[offset:offset + 8]:
                        encoded.append([{'type': 'null' if row[c] is None else {'t': 'text', 'i': 'integer', 'b': 'blob-utf8'}[t[0]],
                                         'value': row[c]} for c, t in zip(columns, types)])
                    value = {'store': table['store'], 'table': table['table'], 'columns': columns,
                             'first': offset, 'totalRows': len(rows), 'rows': encoded}
                    table['pages'].append(add({'profile': doc['profile'], 'kind': 'table_page', 'value': value}, reuse=True))
        elif doc['kind'] == 'trial_observation':
            doc['value']['evidenceRecords'] = len(refs); doc['value']['evidenceBytes'] = written
        add(doc)
    return refs, files, setup


def edit_receipts(tables, change, *, stores=('io_receipt_versions', 'io_receipts', 'io_authority_receipts')):
    for table in stores:
        for row in tables[table]:
            value = json.loads(row['document'])
            change(value)
            row['document'] = canonical(value).decode()
            row['digest'] = digest(b'HMS-SYNTHETIC-IO-RECEIPT-v1', value)
            if table == 'io_receipts':
                row['state'] = value['state']


class IoBoardHistoryTests(unittest.TestCase):
    def rejected(self, name, mutate, code, *, edit_record=lambda doc: None):
        refs, files, setup = rewrite(name, mutate, edit_record)
        # A malformed envelope/page/phase must not stand in for semantic refusal.
        self.assertTrue(inspect_transcript(refs, files, expected_setup=setup)['serializationChecked'])
        with self.assertRaises(IoHistoryError) as caught:
            inspect_board_history(refs, files, expected_setup=setup)
        self.assertEqual(caught.exception.code, code)

    def test_eighteen_actual_coherent_histories_and_one_unresolved_corruption(self):
        catalog = json.loads((FIXTURES / 'index.json').read_bytes())
        total = [0, 0, 0]; accepted = 0
        for fixture in catalog['fixtures']:
            with self.subTest(method=fixture['method']):
                refs, files, _, setup = load(fixture['method'])
                if fixture['method'] == 'test_missing_current_receipt_remains_unresolved':
                    with self.assertRaisesRegex(IoHistoryError, 'PAT_IO_HISTORY_RECEIPT_INVENTORY'):
                        inspect_board_history(refs, files, expected_setup=setup)
                    continue
                result = inspect_board_history(refs, files, expected_setup=setup); accepted += 1
                self.assertTrue(result['boardHistoryChecked']); self.assertTrue(result['modeledBoardIdle'])
                self.assertFalse(result['authoritySemanticsChecked']); self.assertFalse(result['qualificationPassed'])
                for row in result['instances']:
                    for i, key in enumerate(['activations', 'completedCycles', 'canceledActivations']):
                        total[i] += row[key]
        self.assertEqual(accepted, 18); self.assertEqual(total, [29, 26, 3])

    def test_rewriter_preserves_original_gpio_bytes_without_mutation(self):
        refs, files, _, setup = load(GPIO); new_refs, new_files, new_setup = rewrite(GPIO)
        self.assertEqual((new_refs, new_files, new_setup), (refs, files, setup))

    def test_completion_precedes_authority_settlement_after_lost_reply(self):
        refs, files, _, setup = load(LOST)
        result = inspect_board_history(refs, files, expected_setup=setup)
        transition, = [v for v in result['transitions'] if v['state'] == 'completed']
        self.assertEqual(transition['authorityStateAtCapture'], 'outcome_unknown')
        self.assertEqual(transition['authorityClaimsAtCapture'], 1)
        self.assertEqual(transition['clock'], 1000020)

    def test_reopen_cancellation_preserves_activation_and_no_completed_cycle(self):
        refs, files, _, setup = load(REOPEN)
        result = inspect_board_history(refs, files, expected_setup=setup)
        row = next(r for r in result['instances'] if r['instanceId'] == 'sim:gpio5')
        self.assertEqual((row['activations'], row['completedCycles'], row['canceledActivations']), (1, 0, 1))

    def test_later_owner_does_not_invalidate_historical_idle_receipt(self):
        refs, files, _, setup = load(GPIO)
        result = inspect_board_history(refs, files, expected_setup=setup)
        self.assertEqual([t['state'] for t in result['transitions']], ['pending', 'completed', 'pending', 'completed'])
        self.assertEqual([t['clock'] for t in result['transitions']], [1000000, 1000020, 1000020, 1000040])

    def test_balanced_but_false_counters_refuse(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                row = next(r for r in t['io_effects'] if r['instance'] == 'sim:gpio5')
                row['activations'] += 1; row['completed'] += 1
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_COUNTERS')

    def test_unrelated_instance_counters_are_checked(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                row = next(r for r in t['io_effects'] if r['instance'] == 'sim:gpio6')
                row['activations'] = row['completed'] = 1
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_COUNTERS')

    def test_missing_current_receipt_refuses_without_repair(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['io_receipts'].pop()
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_RECEIPT_INVENTORY')

    def test_historical_version_cannot_disappear(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['io_receipt_versions'].pop(0)
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_VERSION_CHANGED')

    def test_terminal_receipt_cannot_change_immutable_start_time(self):
        def mutate(cp, t):
            def change(v):
                if v['sequence'] == 2: v['startedMonoMs'] += 1; v['dueMonoMs'] += 1
            edit_receipts(t, change)
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_IMMUTABLE_RECEIPT')

    def test_cancellation_cannot_erase_committed_activation(self):
        def mutate(cp, t):
            edit_receipts(t, lambda v: v['result'].update(activationCommitted=False) if v['sequence'] == 2 else None)
        self.rejected(CANCEL, mutate, 'PAT_IO_HISTORY_FLAGS')

    def test_early_cancel_cannot_be_relabelled_completed(self):
        def mutate(cp, t):
            def change(v):
                if v['sequence'] == 2:
                    v['state'] = 'completed'; v['result'].update(cycleCompleted=True, reason=None)
            edit_receipts(t, change)
            for row in t['io_effects']:
                row['completed'] += row['canceled']; row['canceled'] = 0
        self.rejected(CANCEL, mutate, 'PAT_IO_HISTORY_COMPLETION_TIME')

    def test_run_deadline_equality_cannot_be_relabelled_completed(self):
        def mutate(cp, t):
            def change(v):
                if v['sequence'] == 2:
                    v['state'] = 'completed'; v['result'].update(cycleCompleted=True, reason=None)
            edit_receipts(t, change)
            for row in t['io_effects']:
                row['completed'] += row['canceled']; row['canceled'] = 0
        self.rejected('test_run_deadline_equality_cancels_instead_of_claiming_completion', mutate, 'PAT_IO_HISTORY_COMPLETION_TIME')

    def test_client_cancel_requires_captured_cancel_request(self):
        def mutate(cp, t):
            def change(v):
                if v['sequence'] == 2:
                    v['state'] = 'canceled'; v['result'].update(cycleCompleted=False, reason='client_cancel')
            edit_receipts(t, change)
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_CANCEL_CAUSE')

    def test_forged_receipt_idle_state_refuses(self):
        def mutate(cp, t):
            edit_receipts(t, lambda v: v['idleState']['atom:pin5'].update(mode='push_pull_output', level=1))
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_DERIVED_STATE')

    def test_pwm_active_state_is_derived_from_exact_arguments(self):
        def mutate(cp, t):
            edit_receipts(t, lambda v: v['activeState']['atom:timer0'].update(frequencyHz=2000))
            for r in t['io_resources']:
                if r['resource'] == 'atom:timer0':
                    value = json.loads(r['state'])
                    if value['enabled']: value['frequencyHz'] = 2000
                    r['state'] = canonical(value).decode()
        self.rejected(PWM, mutate, 'PAT_IO_HISTORY_DERIVED_STATE')

    def test_unowned_pad_must_be_idle(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                row = next(r for r in t['io_resources'] if r['resource'] == 'atom:pin6')
                row['state'] = canonical({'kind': 'pin', 'mode': 'push_pull_output', 'level': 1}).decode()
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_RESOURCES')

    def test_pending_owner_cannot_be_omitted(self):
        def mutate(cp, t):
            if t['io_owners']: t['io_owners'].pop()
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_OWNERS')

    def test_pending_owner_identity_cannot_be_swapped(self):
        def mutate(cp, t):
            if t['io_owners']: t['io_owners'][0]['operation'] = 'op:unrelated'
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_OWNERS')

    def test_pending_owner_fence_cannot_change(self):
        def mutate(cp, t):
            if t['io_owners']: t['io_owners'][0]['fence'] += 1
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_OWNERS')

    def test_persistent_board_floor_cannot_disappear(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['io_fences'].clear()
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_FENCES')

    def test_unexplained_board_floor_increment_refuses(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['io_fences'][0]['fence'] += 1
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_FENCES')

    def test_latest_receipt_cannot_point_back_to_pending(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final':
                row = t['io_receipts'][0]
                prior = next(v for v in t['io_receipt_versions'] if v['operation'] == row['operation'] and v['sequence'] == 1)
                row.update(prior); row['state'] = 'pending'
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_CURRENT_RECEIPT')

    def test_receipt_stored_digest_is_verified_inside_rehashed_pages(self):
        def mutate(cp, t):
            if t['io_receipt_versions']: t['io_receipt_versions'][0]['digest'] = 'sha256:' + '0' * 64
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_RECEIPT_DIGEST')

    def test_provider_session_must_match_historical_owner_epoch(self):
        def mutate(cp, t):
            edit_receipts(t, lambda v: v.update(providerSession='io-session:foreign'))
        self.rejected(REOPEN, mutate, 'PAT_IO_HISTORY_RECEIPT_SESSION')

    def test_receipt_clock_epoch_cannot_be_swapped(self):
        def mutate(cp, t):
            edit_receipts(t, lambda v: v.update(clockEpoch='foreign:1'))
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_RECEIPT_SESSION')

    def test_dispatch_attempt_is_joined_to_operation_and_event(self):
        def mutate(cp, t):
            for row in t['io_dispatch_links']:
                value = json.loads(row['document']); value['attemptId'] = 'attempt:foreign'
                row['document'] = canonical(value).decode(); row['digest'] = digest(b'HMS-SYNTHETIC-IO-DISPATCH-v1', value)
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_DISPATCH')

    def test_authority_receipt_must_equal_a_retained_board_version(self):
        def mutate(cp, t):
            edit_receipts(t, lambda v: v['result'].update(safeIdle=not v['result']['safeIdle']), stores=('io_authority_receipts',))
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_AUTHORITY_RECEIPT')

    def test_authority_receipt_history_cannot_disappear(self):
        def mutate(cp, t):
            if cp['label'] == 'test_final': t['io_authority_receipts'].pop()
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_AUTHORITY_RECEIPT')

    def test_pending_board_work_requires_matching_authority_claims(self):
        def mutate(cp, t):
            if t['io_owners']: t['claims'].clear()
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_AUTHORITY_CLAIMS')

    def test_effect_cannot_appear_in_before_call_checkpoint(self):
        _, _, entries, _ = load(PWM)
        after = tables_at(entries, 'drive:adapters:after')
        def mutate(cp, t):
            if cp['label'] == 'drive:adapters:before':
                t.clear(); t.update(copy.deepcopy(after))
        self.rejected(PWM, mutate, 'PAT_IO_HISTORY_EFFECT_PHASE')

    def test_rehashed_proof_claims_must_match_trusted_topology(self):
        def mutate(cp, t):
            row = next(r for r in t['rc_proofs'] if r['instance'] == 'sim:gpio5')
            value = json.loads(row['document']); value['expandedClaims']['gpio_pulse'] = ['atom:pin6']
            row['document'] = canonical(value).decode(); row['digest'] = digest(b'HMS-RESOURCE-BINDING-PROOF-v0.1', value)
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_PROOF')

    def test_same_fence_cannot_be_reused_for_a_later_activation(self):
        _, _, entries, _ = load(GPIO)
        final = tables_at(entries, 'test_final')
        second = next(r['operation_id'] for r in final['pr_steps'] if r['ordinal'] == 1)
        def mutate(cp, t):
            def change(v):
                if v['operationId'] == second:
                    for claim in v['claims']: claim['fence'] = 1
            edit_receipts(t, change)
            for row in t['io_dispatch_links']:
                value = json.loads(row['document']); change(value)
                row['document'] = canonical(value).decode(); row['digest'] = digest(b'HMS-SYNTHETIC-IO-DISPATCH-v1', value)
            for table, field in [('io_owners', 'operation'), ('io_fences', 'operation'), ('claims', 'operation_id')]:
                for row in t[table]:
                    if row[field] == second: row['fence'] = 1
        self.rejected(GPIO, mutate, 'PAT_IO_HISTORY_FENCE_REUSE')

    def test_producer_parent_status_does_not_define_board_completion(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation' and doc['value']['procedure']:
                doc['value']['procedure']['executionState'] = 'completed'
        refs, files, setup = rewrite(CANCEL, edit_record=edit)
        result = inspect_board_history(refs, files, expected_setup=setup)
        self.assertEqual(sum(r['completedCycles'] for r in result['instances']), 0)
        self.assertFalse(result['qualificationPassed'])

    def test_pure_inspection_does_not_call_io_or_provider_validators(self):
        refs, files, _, setup = load(PWM)
        path = Path(__file__).parents[1] / 'hms/pat_io_board_history.py'
        imports = {n.module for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imports, {'__future__', 'contracts', 'pat_io_transcript', 'resource_topology'})
        before = copy.deepcopy((refs, files, setup))
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), \
             patch.object(Path, 'open', side_effect=AssertionError('path')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('sqlite')), \
             patch.object(time, 'time', side_effect=AssertionError('clock')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            result = inspect_board_history(refs, files, expected_setup=setup)
        self.assertTrue(result['boardHistoryChecked'])
        self.assertEqual((refs, files, setup), before)
