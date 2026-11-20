"""Pure checks of actual retained trials and rehashed adversarial transcripts."""
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
from hms.pat_io_transcript import IoTranscriptError, inspect_transcript

FIXTURES = Path(__file__).parent / 'data/io-transcript'
GPIO = 'test_gpio_sequence_drains_progress_before_advancing_time'
SIXTEEN = 'test_sixteen_steps_retain_all_receipt_versions_within_bounds'
REOPEN = 'test_reopen_pending_cancels_once_and_reconciles_historical_receipt'


def load(name):
    root = FIXTURES / name
    manifest = json.loads((root / 'engine-0.json').read_bytes())
    refs = manifest['records']
    files = {r['path']: (root / 'trial-0/records' / r['path']).read_bytes() for r in refs}
    docs = [(r['path'], json.loads(files[r['path']])) for r in refs]
    setup = {d['kind']: d['value'] for _, d in docs[:4]}
    return refs, files, docs, setup


def pack(entries, *, observation_edit=None):
    """Recompute every record/reference, including page refs and byte accounting.

    Mutations target consistency checks, not merely stale envelope hashes.
    Original record names identify references while deleted records are omitted.
    """
    refs, files, mapping, size = [], {}, {}, 0
    def references(value):
        if type(value) is dict:
            if set(value) == {'path', 'bytes', 'sha256'}:
                return copy.deepcopy(mapping.get(value['path'], value))
            return {key: references(v) for key, v in value.items()}
        if type(value) is list:
            return [references(v) for v in value]
        return value
    for original, raw in entries:
        doc = references(raw)
        if doc['kind'] == 'trial_observation':
            doc['value']['evidenceRecords'] = len(refs)
            doc['value']['evidenceBytes'] = size
            if observation_edit:
                observation_edit(doc['value'])
        body = canonical(doc)
        name = '%06d.json' % len(refs)
        ref = {'path': name, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
        mapping[original] = ref
        refs.append(ref); files[name] = body; size += len(body)
    return refs, files


class IoTranscriptTests(unittest.TestCase):
    def fresh(self, name=GPIO):
        refs, files, entries, setup = load(name)
        return entries, setup

    def refused(self, entries, setup, code=None, **options):
        refs, files = pack(entries, **options)
        # Verify all recomputed envelopes before asking the independent reader.
        self.assertEqual(set(files), {r['path'] for r in refs})
        for ref in refs:
            self.assertEqual(hashlib.sha256(files[ref['path']]).hexdigest(), ref['sha256'])
        with self.assertRaises(IoTranscriptError) as caught:
            inspect_transcript(refs, files, expected_setup=setup)
        if code:
            self.assertEqual(caught.exception.code, code)

    def find(self, entries, kind, predicate=lambda value: True):
        return next(d['value'] for _, d in entries if d['kind'] == kind and predicate(d['value']))

    def test_all_nineteen_actual_trials_are_structurally_complete(self):
        catalog = json.loads((FIXTURES / 'index.json').read_bytes())
        counts = []
        for row in catalog['fixtures']:
            with self.subTest(method=row['method']):
                refs, files, entries, setup = load(row['method'])
                result = inspect_transcript(refs, files, expected_setup=setup)
                counts.append(result)
                self.assertEqual(result['recordCount'], row['records'])
                self.assertTrue(result['serializationChecked'])
                self.assertFalse(result['independentOutcomeChecked'])
                self.assertFalse(result['qualificationPassed'])
        self.assertEqual(len(counts), 19)
        self.assertEqual(sum(r['recordCount'] for r in counts), 2619)
        self.assertEqual(sum(r['checkpointCount'] for r in counts), 352)
        self.assertEqual(sum(r['callCount'] for r in counts), 153)

    def test_missing_receipt_is_not_promoted_by_structural_acceptance(self):
        refs, files, _, setup = load('test_missing_current_receipt_remains_unresolved')
        result = inspect_transcript(refs, files, expected_setup=setup)
        self.assertEqual(len(result['producerReportedUnresolved']), 1)
        self.assertFalse(result['qualificationPassed'])

    def test_inspection_has_no_file_clock_database_or_provider_calls(self):
        refs, files, _, setup = load(GPIO)
        source = (Path(__file__).parents[1] / 'hms/pat_io_transcript.py').read_text()
        imports = [n.module for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)]
        self.assertEqual(set(imports), {'__future__', 'contracts'})
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), \
             patch.object(Path, 'open', side_effect=AssertionError('path')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('sqlite')), \
             patch.object(time, 'time', side_effect=AssertionError('clock')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            result = inspect_transcript(refs, files, expected_setup=setup)
        self.assertEqual(result['lastClock'], 1000040)

    def test_setup_must_match_separately_supplied_expectation(self):
        entries, setup = self.fresh(); setup = copy.deepcopy(setup)
        setup['installation']['boardId'] = 'board:wrong'
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_SETUP')

    def test_missing_or_extra_acquired_file_refuses(self):
        refs, files, _, setup = load(GPIO)
        for bad in [dict(list(files.items())[:-1]), files | {'extra.json': b'{}'}]:
            with self.assertRaisesRegex(IoTranscriptError, 'PAT_IO_TRANSCRIPT_INVENTORY'):
                inspect_transcript(refs, bad, expected_setup=setup)

    def test_record_hash_cannot_replace_actual_bytes(self):
        refs, files, _, setup = load(GPIO); files[refs[0]['path']] += b' '
        with self.assertRaisesRegex(IoTranscriptError, 'PAT_IO_TRANSCRIPT_HASH'):
            inspect_transcript(refs, files, expected_setup=setup)

    def test_noncanonical_record_refuses_even_with_recomputed_hash(self):
        refs, files, _, setup = load(GPIO); first = refs[0]
        files[first['path']] += b' '; first['bytes'] += 1
        first['sha256'] = hashlib.sha256(files[first['path']]).hexdigest()
        with self.assertRaisesRegex(IoTranscriptError, 'PAT_IO_TRANSCRIPT_CANONICAL'):
            inspect_transcript(refs, files, expected_setup=setup)

    def test_path_traversal_is_never_resolved(self):
        refs, files, _, setup = load(GPIO); refs[0]['path'] = '../000000.json'
        with self.assertRaisesRegex(IoTranscriptError, 'PAT_IO_TRANSCRIPT_INVENTORY'):
            inspect_transcript(refs, files, expected_setup=setup)

    def test_extra_record_field_refuses(self):
        entries, setup = self.fresh(); entries[8][1]['extra'] = True
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_SHAPE')

    def test_unknown_record_kind_refuses(self):
        entries, setup = self.fresh(); entries[-1][1]['kind'] = 'qualification_passed'
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_KIND')

    def test_missing_table_refuses(self):
        entries, setup = self.fresh(); self.find(entries, 'checkpoint')['tables'].pop()
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_TABLES')

    def test_duplicate_table_refuses(self):
        entries, setup = self.fresh(); cp = self.find(entries, 'checkpoint')
        cp['tables'][-1] = copy.deepcopy(cp['tables'][0])
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_TABLES')

    def test_wrong_columns_refuse(self):
        entries, setup = self.fresh(); p = self.find(entries, 'table_page')
        p['columns'].reverse()
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_COLUMNS')

    def test_page_gap_refuses(self):
        entries, setup = self.fresh(SIXTEEN)
        p = self.find(entries, 'table_page', lambda p: p['first'] == 8)
        p['first'] = 7
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PAGES')

    def test_omitted_page_refuses(self):
        entries, setup = self.fresh(SIXTEEN)
        cp = self.find(entries, 'checkpoint', lambda v: v['label'] == 'test_final')
        table = next(t for t in cp['tables'] if t['table'] == 'io_receipt_versions')
        self.assertEqual(len(table['pages']), 4); table['pages'].pop(1)
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PAGES')

    def test_duplicate_page_reference_refuses(self):
        entries, setup = self.fresh(SIXTEEN)
        cp = self.find(entries, 'checkpoint', lambda v: v['label'] == 'test_final')
        table = next(t for t in cp['tables'] if t['table'] == 'io_receipt_versions')
        table['pages'][1] = copy.deepcopy(table['pages'][0])
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PAGES')

    def test_forward_page_reference_refuses(self):
        entries, setup = self.fresh(); refs, _ = pack(entries)
        first_cp = self.find(entries, 'checkpoint')
        later = next(i for i, (_, d) in enumerate(entries) if d['kind'] == 'table_page' and d['value']['table'] == 'operations' and d['value']['rows'])
        table = next(t for t in first_cp['tables'] if t['table'] == 'operations')
        table['rowCount'] = 1; table['pages'] = [refs[later]]
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_REFERENCE')

    def test_unsorted_rows_refuse(self):
        entries, setup = self.fresh(); p = self.find(entries, 'table_page', lambda v: v['table'] == 'io_resources')
        p['rows'].reverse()
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_ROW_ORDER')

    def test_duplicate_primary_key_with_different_body_refuses(self):
        entries, setup = self.fresh(); p = self.find(entries, 'table_page', lambda v: v['table'] == 'io_resources')
        p['rows'][1][0] = copy.deepcopy(p['rows'][0][0]); p['rows'][1][1]['value'] = '{}'
        p['rows'].sort(key=lambda row: (row[0]['value'], row[1]['value']))
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PRIMARY_KEY')

    def test_boolean_is_not_an_integer_cell(self):
        entries, setup = self.fresh(); p = self.find(entries, 'table_page', lambda v: v['table'] == 'io_effects')
        p['rows'][0][1]['value'] = False
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_SHAPE')

    def test_blob_cannot_be_retagged_as_text(self):
        entries, setup = self.fresh(); p = self.find(entries, 'table_page', lambda v: v['table'] == 'io_resources')
        p['rows'][0][1]['type'] = 'text'
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_CELL')

    def test_embedded_blob_document_must_remain_canonical(self):
        entries, setup = self.fresh(); p = self.find(entries, 'table_page', lambda v: v['table'] == 'io_resources')
        p['rows'][0][1]['value'] += ' '
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_CANONICAL')

    def test_unreferenced_page_is_not_silently_ignored(self):
        entries, setup = self.fresh(); raw = copy.deepcopy(next(d for _, d in entries if d['kind'] == 'table_page'))
        raw['value']['rows'][0][1]['value'] = 'unused'
        entries.insert(-2, ('unused', raw))
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_INCOMPLETE')

    def test_duplicate_page_body_refuses(self):
        entries, setup = self.fresh(); raw = copy.deepcopy(next(d for _, d in entries if d['kind'] == 'table_page'))
        entries.insert(-2, ('duplicate', raw))
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_DUPLICATE_PAGE')

    def test_call_without_start_refuses(self):
        entries, setup = self.fresh(); pos = next(i for i, (_, d) in enumerate(entries) if d['kind'] == 'call_started')
        entries.pop(pos)
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PHASE')

    def test_swapped_call_result_phase_refuses(self):
        entries, setup = self.fresh(); self.find(entries, 'call_returned')['phase'] += 1
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PHASE')

    def test_missing_after_checkpoint_refuses(self):
        entries, setup = self.fresh(); pos = next(i for i, (_, d) in enumerate(entries) if d['kind'] == 'checkpoint' and d['value']['label'] == 'lower:after')
        entries.pop(pos)
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PLAN')

    def test_clock_change_during_call_refuses(self):
        entries, setup = self.fresh(); self.find(entries, 'call_returned')['clock'] += 1
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PHASE')

    def test_clock_regression_refuses(self):
        entries, setup = self.fresh(); advance = self.find(entries, 'clock_advanced'); advance['to'] = advance['from'] - 1
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_SHAPE')

    def test_checkpoint_epoch_swap_refuses(self):
        entries, setup = self.fresh(); self.find(entries, 'checkpoint')['clockEpoch'] = 'unrelated:1'
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_CLOCK')

    def test_reopen_requires_fresh_session(self):
        entries, setup = self.fresh(REOPEN); opens = [d['value'] for _, d in entries if d['kind'] == 'runtime_opened']
        opens[1]['session'] = opens[0]['session']
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_SESSION')

    def test_reopen_cannot_skip_owner_epoch(self):
        entries, setup = self.fresh(REOPEN); opens = [d['value'] for _, d in entries if d['kind'] == 'runtime_opened']
        opens[1]['ownerEpoch'] += 1
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_REOPEN')

    def test_compiled_plan_cannot_differ_from_lower_return(self):
        entries, setup = self.fresh(); self.find(entries, 'compiled_plan')['request']['procedureKey'] = 'different'
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PLAN')

    def test_number_tag_is_preserved_for_integral_float_negative(self):
        refs, files, entries, setup = load('test_negative_lowering_retains_type_and_never_admits_work')
        tagged = self.find(entries, 'lower_input')['parameters']['duration']
        self.assertEqual(tagged, {'type': 'number', 'value': 20})
        self.assertTrue(inspect_transcript(refs, files, expected_setup=setup)['serializationChecked'])
        tagged['value'] = True
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_PARAMETER_TAG')

    def test_producer_cannot_insert_qualification_success(self):
        entries, setup = self.fresh()
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_OBSERVATION', observation_edit=lambda v: v.update(qualificationPassed=True))

    def test_evidence_accounting_cannot_omit_a_record(self):
        entries, setup = self.fresh()
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_OBSERVATION', observation_edit=lambda v: v.update(evidenceRecords=v['evidenceRecords'] - 1))

    def test_truncated_final_observation_refuses(self):
        entries, setup = self.fresh(); entries.pop()
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_INCOMPLETE')

    def test_records_after_final_report_refuse(self):
        entries, setup = self.fresh(); entries.append(('trailing', copy.deepcopy(entries[-1][1])))
        self.refused(entries, setup, 'PAT_IO_TRANSCRIPT_TRAILING')

    def test_record_and_byte_bounds_are_checked_before_parsing(self):
        refs, files, _, setup = load(GPIO)
        with patch('hms.pat_io_transcript.MAX_RECORDS', len(refs) - 1):
            with self.assertRaisesRegex(IoTranscriptError, 'PAT_IO_TRANSCRIPT_BOUNDS'):
                inspect_transcript(refs, files, expected_setup=setup)
        with patch('hms.pat_io_transcript.MAX_BYTES', sum(r['bytes'] for r in refs) - 1):
            with self.assertRaisesRegex(IoTranscriptError, 'PAT_IO_TRANSCRIPT_BOUNDS'):
                inspect_transcript(refs, files, expected_setup=setup)
