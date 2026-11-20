"""Sealed real captures, coherently rehashed attacks and pure-reader boundaries."""
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
from hms.pat_io_clock_semantics import inspect_clock_challenge, _contexts
from hms.pat_io_clock_history import inspect_clock_transcript
from hms.pat_io_configuration_history import _configuration, inspect_configuration_history
from hms.pat_io_board_history import _reduce
from hms.pat_io_operation_history import _fold
from hms.pat_io_transcript import _read
from test_pat_io_conflict_history import rewrite

FIXTURES = Path(__file__).parent/'data/io-clock'
DELAY = 'guard_delay_excludes_equal_due'
WALL = 'wall_regression_reopens_retained_state'
MAPPING = 'invalid_mapping_stays_invalid_until_reopen'


def load(scenario=DELAY, primitive='gpio'):
    directory = FIXTURES/('test_' + primitive + '_' + scenario)
    manifest = json.loads((directory/'manifest.json').read_bytes())
    requested = json.loads((directory/'requested-case.json').read_bytes())
    return dict(references=manifest['records'],
        files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']},
        configuration=manifest['configuration'],
        configuration_files={r['path']:(directory/'configuration'/r['path']).read_bytes()
                             for r in manifest['configuration']['records']},
        expected_setup=requested['expectedSetup'], expected_authority=requested['expectedAuthority'],
        expected_case=requested['case'])


def decoded(case):
    transcript = _read(case['references'], case['files'], case['expected_setup'], clock_profile=True)
    snapshots = _configuration(transcript, case['references'], case['files'],
                                case['configuration'], case['configuration_files'])
    return transcript, snapshots


def rows(table, change):
    def edit(doc):
        if doc['kind'] != 'table_page' or doc['value']['table'] != table: return
        columns = doc['value']['columns']
        for cells in doc['value']['rows']:
            row = {k:c['value'] for k, c in zip(columns, cells)}
            change(row)
            for k, c in zip(columns, cells): c['value'] = row[k]
    return edit


def receipt_attack(case, change):
    """Keep receipt digests and event references coherent after changing content."""
    mapping = {}; documents = {}
    for raw in case['files'].values():
        doc = json.loads(raw)
        if doc['kind'] != 'table_page' or doc['value']['table'] not in {
                'io_receipts', 'io_receipt_versions', 'io_authority_receipts'}: continue
        for cells in doc['value']['rows']:
            row = {k:c['value'] for k, c in zip(doc['value']['columns'], cells)}
            value = json.loads(row['document']); change(value)
            body = canonical(value)
            sha = 'sha256:' + hashlib.sha256(b'HMS-SYNTHETIC-IO-RECEIPT-v1\0' + body).hexdigest()
            mapping[row['digest']] = sha; documents[row['document']] = body.decode()
    def edit(doc):
        if doc['kind'] != 'table_page': return
        table = doc['value']['table']
        if table in {'io_receipts', 'io_receipt_versions', 'io_authority_receipts'}:
            def change_row(row):
                row['document'] = documents[row['document']]; row['digest'] = mapping[row['digest']]
            rows(table, change_row)(doc)
        elif table == 'events':
            def event(row):
                value = json.loads(row['payload'])
                evidence = value.get('evidence')
                if evidence:
                    old = 'sha256:' + evidence['reference'].removeprefix('io-receipt:')
                    evidence['reference'] = 'io-receipt:' + mapping[old].removeprefix('sha256:')
                    row['payload'] = canonical(value).decode()
            rows(table, event)(doc)
    return rewrite(case, edit)


def rollback_failed_table(case, table, *, configuration=False):
    files=case['configuration_files'] if configuration else case['files']
    kind='snapshot' if configuration else 'checkpoint'
    baseline=next(json.loads(raw)['value'] for raw in files.values()
                  if json.loads(raw)['kind']==kind and json.loads(raw)['value']['label']=='baseline')
    entry=next(t for t in baseline['tables'] if t['table']==table)
    def edit(doc):
        if doc['kind']==kind and doc['value']['label']=='drive:adapters:after_error':
            doc['value']['tables']=[copy.deepcopy(entry) if t['table']==table else t for t in doc['value']['tables']]
    return rewrite(case,edit)


class IoClockSemanticsTests(unittest.TestCase):
    def checked(self, scenario, primitive):
        case = load(scenario, primitive); result = inspect_clock_challenge(**case)
        for key in ('exactClockControlScheduleChecked', 'expectedResponseVerified', 'completeHistoryChecked',
                    'independentOutcomeChecked', 'staticTimingPolicyChecked', 'wholeDeclaredDomainChecked'):
            self.assertTrue(result[key])
        for key in ('configurationAttested', 'compilerIdentityAttested', 'requiredMatrixCoverageChecked',
                    'allFaultScenariosChecked', 'actualAggregateStorageEnforced', 'physicalMeasurementChecked', 'qualificationPassed'):
            self.assertFalse(result[key])
        outcome = result['outcome']; history = result['history']
        self.assertEqual(outcome['contractStatus'], 'failed'); self.assertTrue(outcome['settledAndQuiescent'])
        self.assertEqual(outcome['unresolvedOperationIds'], []); self.assertFalse(outcome['physicalObjectiveVerified'])
        self.assertEqual(tuple(outcome[k] for k in ('activations', 'completedCycles', 'canceledActivations')),
                         (0, 0, 0) if scenario == DELAY else (1, 0, 1))
        self.assertEqual(history['operations']['operationsChecked'], 1)
        self.assertEqual(len(history['clockFailuresChecked']), 0 if scenario == DELAY else 1 if scenario == WALL else 2)
        if scenario == DELAY:
            events = history['operations']['transitions']
            self.assertEqual([e['clock'] for e in events if e['kind'] == 'dispatch_claimed'], [1000000])
            self.assertEqual([e['clock'] for e in events if e['kind'] == 'execution_evidence'], [1000099])
            self.assertEqual(history['board']['instances'][0]['completedCycles'], 0)
        return result

    def rejected(self, case, code=None):
        # Hashes, pages, joins and closed clock/call schedule must still pass.
        inspect_clock_transcript(case['references'], case['files'], case['configuration'], case['configuration_files'],
                                 expected_setup=case['expected_setup'], expected_case=case['expected_case'])
        with self.assertRaises(ValueError) as caught: inspect_clock_challenge(**case)
        if code: self.assertEqual(caught.exception.code, code)

    def test_gpio_duration_equality_excludes_start(self): self.checked(DELAY, 'gpio')
    def test_pwm_duration_equality_excludes_start(self): self.checked(DELAY, 'pwm')
    def test_gpio_wall_fault_retains_then_settles(self): self.checked(WALL, 'gpio')
    def test_pwm_wall_fault_retains_then_settles(self): self.checked(WALL, 'pwm')
    def test_gpio_mapping_fault_remains_latched(self): self.checked(MAPPING, 'gpio')
    def test_pwm_mapping_fault_remains_latched(self): self.checked(MAPPING, 'pwm')

    def test_false_no_start_cause_with_coherent_receipt_references(self):
        self.rejected(receipt_attack(load(), lambda r:r['result'].update(reason='execution_deadline')), 'PAT_IO_CLOCK_HISTORY_NO_START')

    def test_no_start_cannot_claim_activation(self):
        self.rejected(receipt_attack(load(), lambda r:r['result'].update(activationCommitted=True)), 'PAT_IO_HISTORY_FLAGS')

    def test_no_start_cannot_claim_completion(self):
        self.rejected(receipt_attack(load(), lambda r:r['result'].update(cycleCompleted=True)), 'PAT_IO_HISTORY_FLAGS')

    def test_no_start_cannot_claim_nonidle(self):
        self.rejected(receipt_attack(load(), lambda r:r['result'].update(safeIdle=False)), 'PAT_IO_HISTORY_FLAGS')

    def test_no_start_cannot_replace_absent_timestamps(self):
        # Cell storage classes stay unchanged: timestamps are inside receipt JSON.
        self.rejected(receipt_attack(load(), lambda r:r.update(startedMonoMs=1000099)), 'PAT_IO_HISTORY_FLAGS')

    def test_no_start_authority_may_have_acted_is_false(self):
        self.rejected(rewrite(load(), rows('operations', lambda r:r.update(may_have_acted=1)
            if r['state']=='rejected_before_start' else None)), 'PAT_IO_CLOCK_HISTORY_NO_START')

    def test_hidden_activation_counter_is_rejected(self):
        self.rejected(rewrite(load(), rows('io_effects', lambda r:r.update(activations=1)
            if r['instance']=='sim:gpio5' else None)))

    def test_dispatch_event_cannot_be_clamped_to_finish_clock(self):
        self.rejected(rewrite(load(), rows('events', lambda r:r.update(time_ms=1000099)
            if r['kind']=='dispatch_claimed' else None)), 'PAT_IO_HISTORY_DISPATCH_EVENT')

    def test_wall_floor_cannot_be_rewritten_downward(self):
        self.rejected(rewrite(load(WALL), rows('meta', lambda r:r.update(value='999999')
            if r['key']=='last_clock' else None)), 'PAT_IO_CLOCK_HISTORY_CLOCK_FLOOR')

    def test_mapping_fault_cannot_retire_pending_operation(self):
        self.rejected(rewrite(load(MAPPING), rows('operations', lambda r:r.update(state='canceled')
            if r['state']=='running' else None)), 'PAT_IO_CLOCK_HISTORY_PENDING_CONTEXT')

    def test_failed_phase_cannot_mutate_paired_configuration(self):
        self.rejected(rollback_failed_table(load(MAPPING),'reg_observations',configuration=True),
                      'PAT_IO_CLOCK_HISTORY_FAILED_CLOCK_MUTATION')

    def test_failed_phase_cannot_release_authority_claims(self):
        self.rejected(rollback_failed_table(load(WALL),'claims'), 'PAT_IO_CLOCK_HISTORY_FAILED_CLOCK_MUTATION')

    def test_failed_phase_cannot_remove_committed_activation(self):
        self.rejected(rollback_failed_table(load(MAPPING),'io_effects'), 'PAT_IO_CLOCK_HISTORY_FAILED_CLOCK_MUTATION')

    def test_cached_observations_cannot_be_reticked_on_regression(self):
        def change(row):
            value=json.loads(row['document'])
            if value['receipt']['ticksMs']==1000000:
                value['receipt']['ticksMs']=999999;value['acquisition']['ticksMs']=999999
                row['document']=canonical(value).decode()
        self.rejected(rewrite(load(MAPPING), rows('reg_observations',change)))

    def test_old_clock_event_cannot_be_retimed_after_reopen(self):
        self.rejected(rewrite(load(WALL), rows('events',lambda r:r.update(time_ms=1000001)
            if r['kind']=='accepted' else None)), 'PAT_IO_OPERATION_EVENT_CLOCK')

    def test_reopen_stop_cannot_claim_due_completion(self):
        self.rejected(receipt_attack(load(WALL), lambda r:r['result'].update(reason='execution_deadline')
            if r['state']=='canceled' else None), 'PAT_IO_CLOCK_HISTORY_REOPEN_STOP')

    def test_reopen_cannot_discard_unknown_state(self):
        self.rejected(rewrite(load(MAPPING),rows('operations',lambda r:r.update(state='running')
            if r['state']=='outcome_unknown' else None)), 'PAT_IO_CLOCK_HISTORY_REOPEN_OWNERSHIP')

    def test_reopen_receipt_retains_original_owner_epoch(self):
        self.rejected(receipt_attack(load(MAPPING),lambda r:r.update(ownerEpoch=2)
            if r['state']=='canceled' else None), 'PAT_IO_CLOCK_HISTORY_REOPEN_STOP')

    def test_reopen_cannot_create_new_replay_key(self):
        self.rejected(rewrite(load(WALL), rows('replay_keys',lambda r:r.update(caller_key='new:child'))))

    def test_historical_floors_cannot_be_reset(self):
        self.rejected(rewrite(load(MAPPING), rows('resource_floors',lambda r:r.update(fence=2))), 'PAT_IO_OPERATION_FLOORS')

    def test_clock_controls_cannot_substitute_for_invoke_permission(self):
        case=load(WALL);case['expected_authority']['initialGrants']=[]
        self.rejected(case)

    def test_final_parent_cancellation_cannot_be_fabricated(self):
        self.rejected(rewrite(load(MAPPING),rows('pr_procedures',lambda r:r.update(state='running')
            if r.get('state')=='canceled' else None)))

    def test_old_public_profiles_do_not_accept_clock_evidence(self):
        case=load(MAPPING)
        with self.assertRaises(ValueError): _read(case['references'],case['files'],case['expected_setup'])
        args={k:v for k,v in case.items() if k!='expected_case'}
        with self.assertRaises(ValueError): inspect_configuration_history(**args)

    def test_private_folds_need_independently_derived_clock_context(self):
        case=load();transcript,_=decoded(case)
        with self.assertRaisesRegex(ValueError,'NO_START_CAUSE_UNIMPLEMENTED'): _reduce(transcript,case['expected_setup'])
        with self.assertRaisesRegex(ValueError,'EVENT_CLOCK'): _fold(transcript,case['expected_setup'])
        case=load(WALL);transcript,_=decoded(case)
        with self.assertRaisesRegex(ValueError,'PAT_IO_OPERATION_CLOCK'): _fold(transcript,case['expected_setup'])

    def test_unused_handoffs_are_rejected(self):
        case=load();transcript,snapshots=decoded(case);ctx=_contexts(transcript,snapshots,'start_run_equal')
        with self.assertRaisesRegex(ValueError,'UNUSED_NO_START'):
            _reduce(transcript,case['expected_setup'],checked_no_starts=ctx['board_no_starts']|{(-1,'unknown'):'duration_budget_excluded'})
        with self.assertRaisesRegex(ValueError,'UNUSED_CLOCK_CONTEXT'):
            _fold(transcript,case['expected_setup'],checked_event_times=ctx['times']|{(-1,'unknown',1):1000000},checked_no_starts=ctx['no_starts'])

    def test_pure_checker_performs_no_io_or_clock_read(self):
        case=load(MAPPING)
        def veto(*args,**kwargs): raise AssertionError('pure checker attempted I/O or a live clock')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),\
             patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_clock_challenge(**case)['expectedResponseVerified'])

    def test_semantic_module_has_no_runtime_or_producer_import(self):
        source=Path(__file__).parent.parent/'hms/pat_io_clock_semantics.py'
        tree=ast.parse(source.read_bytes())
        modules=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        self.assertFalse(any('capture' in name or name in {'runtime','synthetic_io_board','journal','registry','pat_io_trials'}
                             for name in modules))
