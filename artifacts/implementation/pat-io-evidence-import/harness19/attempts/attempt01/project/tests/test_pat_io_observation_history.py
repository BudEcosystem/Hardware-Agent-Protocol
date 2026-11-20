"""Independent sample semantics over original captures and rehashed attacks."""
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
from hms.pat_io_recovery_history import inspect_recovery_history
from hms.pat_io_observation_history import inspect_observation_history, inspect_observed_execution_history
from hms.pat_io_transcript import _read
import test_pat_io_configuration_history as config
import test_pat_io_authorized_history as active
import test_pat_io_recovery_history as recovery


def observations(tables, change):
    for row in tables['reg_observations']:
        value = json.loads(row['document'])
        change(row['instance'], row['property'], value)
        row['document'] = canonical(value).decode()


def after(value, phase):
    return value['phase'] > phase or value['phase'] == phase and value['label'].endswith((':after', ':after_error'))


def shift(tables, amount=1, prop=None):
    def change(instance, property_id, value):
        if prop is None or property_id == prop:
            value['sequence'] += amount
    observations(tables, change)


def suppress(phase):
    prior = {}
    def change(value, tables, resolver):
        if value['phase'] == phase:
            if value['label'].endswith(':before'):
                prior.update({k: copy.deepcopy(tables[k]) for k in ('reg_observations', 'reg_presence')})
            elif value['label'].endswith((':after', ':after_error')):
                tables.update(copy.deepcopy(prior))
    return change


class IoObservationHistoryTests(unittest.TestCase):
    def rejected(self, case, code, *, prior=None):
        _read(case['references'], case['files'], case['expected_setup'])
        if prior is not None:
            self.assertFalse(prior(**case)['qualificationPassed'])
        with self.assertRaises(ValueError) as caught:
            inspect_observation_history(**case)
        self.assertEqual(caught.exception.code, code)

    def family(self, module, expected):
        catalog = json.loads((module.FIXTURES / 'index.json').read_bytes())
        totals = {}
        for fixture in catalog['fixtures']:
            with self.subTest(method=fixture['method']):
                result = inspect_observation_history(**module.load(fixture['method']))
                self.assertTrue(result['observationSampleSemanticsChecked'])
                for key in ('configurationHistoryChecked', 'trustedGrantPlanMatched', 'patCorrespondenceChecked', 'boardHistoryChecked'):
                    self.assertTrue(result[key])
                for key in ('operationHistoryChecked', 'procedureHistoryChecked', 'configurationAttested',
                            'compilerIdentityAttested', 'physicalMeasurementChecked', 'staticTimingPolicyChecked',
                            'allFaultScenariosChecked', 'independentOutcomeChecked', 'qualificationPassed'):
                    self.assertFalse(result[key])
                self.assertEqual(result['trustedFaultPlanMatched'], module is recovery)
                for key, value in result['sampling'].items(): totals[key] = totals.get(key, 0) + value
        self.assertEqual(totals, expected)

    def test_all_twelve_configuration_trials_have_exact_sample_histories(self):
        self.family(config, dict(snapshotsChecked=206, initialSampleBatches=12, reopenSampleBatches=1,
            driveSampleBatches=64, samplesProduced=616, cachedSnapshots=129, valueReadingsChecked=824, laggingSnapshots=40))

    def test_all_six_active_withdrawal_trials_have_exact_sample_histories(self):
        self.family(active, dict(snapshotsChecked=92, initialSampleBatches=6, reopenSampleBatches=0,
            driveSampleBatches=27, samplesProduced=264, cachedSnapshots=59, valueReadingsChecked=368, laggingSnapshots=14))

    def test_all_eight_pending_recovery_trials_have_exact_sample_histories(self):
        self.family(recovery, dict(snapshotsChecked=136, initialSampleBatches=8, reopenSampleBatches=0,
            driveSampleBatches=43, samplesProduced=408, cachedSnapshots=85, valueReadingsChecked=544, laggingSnapshots=18))

    def test_full_composition_keeps_ordinary_active_and_recovery_semantics(self):
        cases = [config.load(config.REOPEN), active.load(active.COMPLETED), recovery.load(recovery.SETTLE_LOSS)]
        for case in cases:
            result = inspect_observed_execution_history(**case)
            for key in ('observationSampleSemanticsChecked', 'operationHistoryChecked', 'procedureHistoryChecked'):
                self.assertTrue(result[key])
            self.assertFalse(result['qualificationPassed']); self.assertFalse(result['independentOutcomeChecked'])
            self.assertFalse(result['history']['observationSampleSemanticsChecked'])
            self.assertTrue(result['observations']['observationSampleSemanticsChecked'])

    def test_parent_permission_refusal_does_not_become_full_execution_validation(self):
        case = config.load('test_configuration_revoked_grant_prevents_parent_admission')
        self.assertTrue(inspect_observation_history(**case)['observationSampleSemanticsChecked'])
        with self.assertRaisesRegex(ValueError, 'PAT_IO_PROCEDURE_SUBMIT_FAILURE_UNIMPLEMENTED'):
            inspect_observed_execution_history(**case)

    def test_predispatch_permission_refusal_does_not_become_full_execution_validation(self):
        case = config.load(config.REVOKED)
        self.assertTrue(inspect_observation_history(**case)['observationSampleSemanticsChecked'])
        with self.assertRaisesRegex(ValueError, 'PAT_IO_OPERATION_PREDISPATCH_CAUSE'):
            inspect_observed_execution_history(**case)

    def test_monotone_undercount_can_pass_old_history_but_not_sample_semantics(self):
        def change(v, t, r):
            observations(t, lambda i, p, o: o.update(value=0) if i == 'sim:gpio5' and p == 'value' else None)
        self.rejected(config.rewrite(mutate=change), 'PAT_IO_OBSERVATION_SAMPLE_VALUE', prior=inspect_authorized_history)

    def test_recovery_history_cannot_promote_an_undercounted_sample(self):
        def change(v, t, r):
            observations(t, lambda i, p, o: o.update(value=0) if i == 'sim:gpio5' and p == 'value' else None)
        self.rejected(recovery.rewrite(mutate=change), 'PAT_IO_OBSERVATION_SAMPLE_VALUE', prior=inspect_recovery_history)

    def test_same_phase_activation_cannot_be_reported_as_a_prior_sample(self):
        def change(v, t, r):
            # A newly committed activation is visible in board state, but this
            # phase's sample was acquired before it. Propagate the cached lie.
            if v['phase'] == 3 and v['label'].endswith(':after') or v['phase'] == 4 and v['label'].endswith(':before'):
                observations(t, lambda i, p, o: o.update(value=1) if i == 'sim:gpio5' and p == 'value' else None)
        self.rejected(config.rewrite(mutate=change), 'PAT_IO_OBSERVATION_SAMPLE_VALUE', prior=inspect_authorized_history)

    def test_skipped_sequences_cannot_invent_extra_samples(self):
        self.rejected(config.rewrite(mutate=lambda v, t, r: shift(t) if after(v, 3) else None),
                      'PAT_IO_OBSERVATION_SAMPLE_SEQUENCE', prior=inspect_authorized_history)

    def test_ready_and_value_must_both_advance_once_per_refresh(self):
        self.rejected(config.rewrite(mutate=lambda v, t, r: shift(t, prop='value') if after(v, 3) else None),
                      'PAT_IO_OBSERVATION_SAMPLE_SEQUENCE', prior=inspect_authorized_history)

    def test_lowering_cannot_create_an_unrecorded_sample(self):
        self.rejected(config.rewrite(mutate=lambda v, t, r: shift(t) if after(v, 1) else None),
                      'PAT_IO_OBSERVATION_NON_SAMPLE_PHASE', prior=inspect_authorized_history)

    def test_admission_cannot_create_an_unrecorded_sample(self):
        self.rejected(config.rewrite(mutate=lambda v, t, r: shift(t) if after(v, 2) else None),
                      'PAT_IO_OBSERVATION_NON_SAMPLE_PHASE', prior=inspect_authorized_history)

    def test_cancel_cannot_create_an_unrecorded_sample(self):
        self.rejected(active.rewrite(active.CANCEL, mutate=lambda v, t, r: shift(t) if after(v, 5) else None),
                      'PAT_IO_OBSERVATION_NON_SAMPLE_PHASE', prior=inspect_authorized_history)

    def test_before_call_capture_cannot_refresh_inputs(self):
        self.rejected(config.rewrite(mutate=lambda v, t, r: shift(t) if v['phase'] >= 3 else None),
                      'PAT_IO_OBSERVATION_NON_SAMPLE_PHASE', prior=inspect_authorized_history)

    def test_final_capture_cannot_refresh_inputs(self):
        self.rejected(config.rewrite(mutate=lambda v, t, r: shift(t) if v['label'] == 'test_final' else None),
                      'PAT_IO_OBSERVATION_NON_SAMPLE_PHASE', prior=inspect_authorized_history)

    def test_cycle_requires_a_sample_even_when_virtual_time_is_unchanged(self):
        self.rejected(config.rewrite(mutate=suppress(3)), 'PAT_IO_OBSERVATION_SAMPLE_SEQUENCE', prior=inspect_authorized_history)

    def test_procedure_phase_requires_a_sample_even_without_a_board_effect(self):
        self.rejected(active.rewrite(mutate=suppress(3)), 'PAT_IO_OBSERVATION_SAMPLE_SEQUENCE', prior=inspect_authorized_history)

    def test_failed_adapter_phase_still_has_its_pre_fault_sample(self):
        self.rejected(recovery.rewrite(recovery.STOP_FAIL, mutate=suppress(5)),
                      'PAT_IO_OBSERVATION_SAMPLE_SEQUENCE', prior=inspect_recovery_history)

    def test_baseline_sample_time_cannot_precede_runtime_opening(self):
        def change(v, t, r):
            def edit(i, p, o):
                if o['sequence'] == 1:
                    o['acquisition']['ticksMs'] -= 1; o['receipt']['ticksMs'] -= 1
            first = all(json.loads(row['document'])['sequence'] == 1 for row in t['reg_observations'])
            observations(t, edit)
            if first:
                for row in t['reg_presence']: row['expires_ms'] -= 1
        self.rejected(config.rewrite(mutate=change), 'PAT_IO_OBSERVATION_SAMPLE_CLOCK', prior=inspect_authorized_history)

    def test_reopen_samples_retained_activation_count_in_its_new_stream(self):
        def change(v, t, r):
            if v['ownerEpoch'] > 1:
                observations(t, lambda i, p, o: o.update(value=0) if i == 'sim:gpio5' and p == 'value' and o['sequence'] == 1 else None)
        self.rejected(config.rewrite(config.REOPEN, mutate=change), 'PAT_IO_OBSERVATION_SAMPLE_VALUE', prior=inspect_authorized_history)

    def test_sample_value_cannot_validate_a_forged_board_counter(self):
        def change(v, t):
            if v['label'] == 'test_final': next(row for row in t['io_effects'] if row['activations'])['activations'] += 1
        self.rejected(config.rewrite(legacy=change), 'PAT_IO_HISTORY_COUNTERS')

    def test_recovery_samples_do_not_infer_an_omitted_fault_plan(self):
        case = recovery.load(); case.pop('expected_faults')
        self.rejected(case, 'PAT_IO_AUTHORIZED_PENDING_RECOVERY_UNSUPPORTED')

    def test_full_composition_also_rejects_a_sample_lie(self):
        def change(v, t, r):
            observations(t, lambda i, p, o: o.update(value=0) if i == 'sim:gpio5' and p == 'value' else None)
        with self.assertRaisesRegex(ValueError, 'PAT_IO_OBSERVATION_SAMPLE_VALUE'):
            inspect_observed_execution_history(**config.rewrite(mutate=change))

    def test_sample_inspection_is_pure_and_preserves_inputs(self):
        case = recovery.load(recovery.SETTLE_LOSS); before = copy.deepcopy(case)
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), patch.object(Path, 'read_bytes', side_effect=AssertionError('file')), patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            self.assertTrue(inspect_observation_history(**case)['observationSampleSemanticsChecked'])
        self.assertEqual(case, before)

    def test_full_composition_is_pure_and_preserves_inputs(self):
        case = active.load(active.STOP_LOSS); before = copy.deepcopy(case)
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), patch.object(Path, 'read_bytes', side_effect=AssertionError('file')), patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            self.assertTrue(inspect_observed_execution_history(**case)['observationSampleSemanticsChecked'])
        self.assertEqual(case, before)

    def test_imports_are_only_contracts_and_independent_history_readers(self):
        tree = ast.parse((Path(__file__).parents[1] / 'hms/pat_io_observation_history.py').read_text())
        self.assertEqual({n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)},
            {'__future__', 'contracts', 'pat_io_authorized_history', 'pat_io_board_history',
             'pat_io_configuration_history', 'pat_io_correspondence', 'pat_io_recovery_history'})
        self.assertFalse(any(isinstance(n, ast.Import) for n in ast.walk(tree)))
