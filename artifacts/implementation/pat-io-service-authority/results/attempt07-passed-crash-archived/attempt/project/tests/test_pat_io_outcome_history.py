"""Independent whole-domain policy and single-trial outcomes over actual captures."""
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
from hms.pat_io_outcome_history import inspect_static_policy, inspect_trial_outcome
from hms.pat_io_refusal_history import inspect_refusal_history
from hms.pat_io_transcript import _read
import test_pat_io_configuration_history as config
import test_pat_io_authorized_history as active
import test_pat_io_recovery_history as recovery

PARENT = 'test_configuration_revoked_grant_prevents_parent_admission'
PWM = 'test_configuration_pwm_retains_typed_bindings_and_routes'
SIXTEEN = 'test_configuration_sixteen_steps_stay_within_original_shared_limits'


def setup_changed(change):
    setup = config.load()['expected_setup']; change(setup['artifact'])
    artifact = setup['artifact']; contract = setup['static_contract']
    contract['artifactDigest'] = 'sha256:' + hashlib.sha256(b'HMS-PAT-JCS-SHA256-v0.1\0' + canonical(artifact)).hexdigest()
    contract['declaredDomains'] = {key: copy.deepcopy(value['valueSchema']) for key, value in artifact['parameters'].items()}
    for domain in contract['declaredDomains'].values():
        if 'enum' in domain: domain['enum'].sort()
    return setup


def contract_attack(change):
    def edit(doc):
        if doc['kind'] == 'static_contract': change(doc['value'])
    case = config.rewrite(edit=edit)
    case['expected_setup']['static_contract'] = json.loads(case['files'][case['references'][3]['path']])['value']
    return case


class IoOutcomeHistoryTests(unittest.TestCase):
    def static_rejected(self, setup, code):
        with self.assertRaises(ValueError) as caught: inspect_static_policy(expected_setup=setup)
        self.assertEqual(caught.exception.code, code)

    def test_all_twenty_six_complete_histories_receive_exact_outcome_classes(self):
        totals = dict(satisfied=0, failed=0, incomplete=0, activations=0, completedCycles=0, canceledActivations=0)
        for module in (config, active, recovery):
            catalog = json.loads((module.FIXTURES/'index.json').read_bytes())
            for fixture in catalog['fixtures']:
                with self.subTest(method=fixture['method']):
                    result = inspect_trial_outcome(**module.load(fixture['method'])); outcome = result['outcome']
                    for key in ('staticTimingPolicyChecked', 'wholeDeclaredDomainChecked', 'completeHistoryChecked', 'simulationOutcomeEvaluated'):
                        self.assertTrue(result[key])
                    for key in ('configurationAttested', 'compilerIdentityAttested', 'physicalMeasurementChecked',
                                'requiredMatrixCoverageChecked', 'allFaultScenariosChecked', 'qualificationPassed'):
                        self.assertFalse(result[key])
                    self.assertEqual(result['independentOutcomeChecked'], outcome['contractStatus'] != 'incomplete')
                    totals[outcome['contractStatus']] += 1
                    for key in ('activations', 'completedCycles', 'canceledActivations'): totals[key] += outcome[key]
        self.assertEqual(totals, dict(satisfied=4, failed=16, incomplete=6, activations=34, completedCycles=20, canceledActivations=14))

    def test_gpio_nominal_children_and_parent_match_exact_zero_lag_schedule(self):
        result = inspect_trial_outcome(**config.load()); outcome = result['outcome']
        self.assertEqual(outcome['contractStatus'], 'satisfied'); self.assertTrue(outcome['nominalCompletionSatisfied'])
        self.assertTrue(outcome['settledAndQuiescent']); self.assertEqual(outcome['unresolvedOperationIds'], [])
        rows = outcome['concreteSchedule']
        self.assertEqual([(r['actualAdmissionMs'], r['actualStartMs'], r['actualBoardCompletionMs'], r['actualAuthorityCompletionMs'])
                         for r in rows], [(1000000, 1000000, 1000001, 1000001), (1000001, 1000001, 1000002, 1000002)])
        self.assertEqual(outcome['parentCompletedAtMs'], 1000002)
        self.assertTrue(outcome['zeroLagChildScheduleMatched']); self.assertTrue(outcome['parentCompletionBeforeDeadline'])

    def test_pwm_completion_is_one_cycle_and_no_cancellation(self):
        outcome = inspect_trial_outcome(**config.load(PWM))['outcome']
        self.assertEqual((outcome['activations'], outcome['completedCycles'], outcome['canceledActivations']), (1, 1, 0))
        self.assertTrue(outcome['nominalCompletionSatisfied']); self.assertFalse(outcome['physicalObjectiveVerified'])

    def test_sixteen_steps_have_exact_prefix_admission_and_completion_times(self):
        outcome = inspect_trial_outcome(**config.load(SIXTEEN))['outcome']
        self.assertEqual(len(outcome['concreteSchedule']), 16)
        self.assertEqual([r['actualStartMs'] for r in outcome['concreteSchedule']], list(range(1000000, 1000016)))
        self.assertEqual(outcome['parentCompletedAtMs'], 1000016); self.assertTrue(outcome['nominalCompletionSatisfied'])

    def test_unstarted_parent_is_incomplete_even_when_board_is_idle(self):
        result = inspect_trial_outcome(**config.load(config.REPEAT)); outcome = result['outcome']
        self.assertEqual(outcome['contractStatus'], 'incomplete'); self.assertEqual(outcome['actualParentState'], 'accepted')
        self.assertTrue(outcome['settledAndQuiescent']); self.assertFalse(result['independentOutcomeChecked'])
        self.assertIsNone(outcome['nominalTimingSatisfied']); self.assertFalse(outcome['nominalCompletionSatisfied'])

    def test_rejected_child_is_failed_without_inventing_parent_advancement(self):
        result = inspect_trial_outcome(**config.load(config.REVOKED)); outcome = result['outcome']
        self.assertEqual(outcome['contractStatus'], 'failed'); self.assertEqual(outcome['actualParentState'], 'running')
        self.assertEqual(outcome['activations'], 0); self.assertTrue(outcome['settledAndQuiescent'])
        self.assertFalse(outcome['nominalCompletionSatisfied']); self.assertTrue(result['independentOutcomeChecked'])

    def test_parent_denial_fails_completion_contract_without_creating_work(self):
        outcome = inspect_trial_outcome(**config.load(PARENT))['outcome']
        self.assertEqual(outcome['contractStatus'], 'failed'); self.assertIsNone(outcome['actualParentState'])
        self.assertEqual(outcome['activations'], 0); self.assertEqual(outcome['concreteSchedule'], [])

    def test_recovery_cancellation_does_not_count_as_completed_cycle(self):
        result = inspect_trial_outcome(**recovery.load(recovery.SETTLE_LOSS)); outcome = result['outcome']
        self.assertEqual(outcome['contractStatus'], 'failed')
        self.assertEqual((outcome['activations'], outcome['completedCycles'], outcome['canceledActivations']), (1, 0, 1))
        self.assertTrue(outcome['settledAndQuiescent']); self.assertTrue(result['history']['trustedFaultPlanMatched'])

    def test_completion_before_withdrawal_preserves_true_completed_outcome(self):
        outcome = inspect_trial_outcome(**active.load(active.COMPLETED))['outcome']
        self.assertEqual(outcome['contractStatus'], 'satisfied'); self.assertEqual(outcome['completedCycles'], 1)
        self.assertTrue(outcome['settledAndQuiescent'])

    def test_reopen_cancellation_is_not_nominal_completion(self):
        outcome = inspect_trial_outcome(**config.load(config.REOPEN))['outcome']
        self.assertEqual(outcome['contractStatus'], 'failed'); self.assertEqual(outcome['completedCycles'], 0)
        self.assertEqual(outcome['canceledActivations'], 1); self.assertFalse(outcome['nominalCompletionSatisfied'])

    def test_old_complete_history_accepts_forged_schedule_but_new_gate_rejects(self):
        case = contract_attack(lambda c: c['schedule']['steps'][1].update(admissionMaxOffsetMs=0))
        self.assertTrue(inspect_refusal_history(**case)['operationHistoryChecked'])
        with self.assertRaisesRegex(ValueError, 'PAT_IO_OUTCOME_STATIC_CONTRACT'): inspect_trial_outcome(**case)

    def test_rehashed_static_contract_cannot_omit_or_forge_policy_fields(self):
        attacks = [lambda c: c['schedule'].update(hostTimingGuaranteed=True),
                   lambda c: c['schedule'].update(dispatchLagMs=1),
                   lambda c: c['schedule'].update(correlationsOverapproximated=False),
                   lambda c: c['schedule'].update(maxOriginMs=c['schedule']['maxOriginMs']+1),
                   lambda c: c['schedule']['steps'].pop(),
                   lambda c: c['schedule']['steps'][0].update(earliestLeaseExpiryOffsetMs=999999),
                   lambda c: c['nominalParameters'].update(duration=1),
                   lambda c: c['applicableDomains']['duration'].update(maximum=1),
                   lambda c: c.update(extraSuccess=True)]
        for attack in attacks:
            case = contract_attack(attack); _read(case['references'], case['files'], case['expected_setup'])
            with self.assertRaisesRegex(ValueError, 'PAT_IO_OUTCOME_STATIC_CONTRACT'): inspect_trial_outcome(**case)

    def test_declared_duration_equality_refuses_before_narrow_applicability(self):
        def change(a):
            a['parameters']['duration']['valueSchema']['maximum'] = 500
            a['applicability']['all'].append(dict(field='parameters.duration', op='equals', literal=1))
        self.static_rejected(setup_changed(change), 'PAT_IO_OUTCOME_DURATION_BUDGET')

    def test_sequential_latest_start_equality_refuses(self):
        self.static_rejected(setup_changed(lambda a: a['steps'][1]['timing'].update(latestStartOffsetMs=100)), 'PAT_IO_OUTCOME_START_WINDOW')

    def test_sequential_completion_window_is_checked_over_whole_domain(self):
        def change(a):
            a['parameters']['duration']['valueSchema']['maximum'] = 70
            a['steps'][1]['timing'].update(latestStartOffsetMs=100, latestCompletionOffsetMs=120, maxRunMs=80)
        self.static_rejected(setup_changed(change), 'PAT_IO_OUTCOME_COMPLETION_WINDOW')

    def test_early_admission_lease_includes_waiting_time(self):
        def change(a):
            a['timingBudget']['latestCompletionOffsetMs'] = 70000
            a['steps'][1]['timing'].update(notBeforeOffsetMs=60000, latestStartOffsetMs=61000, latestCompletionOffsetMs=70000)
        self.static_rejected(setup_changed(change), 'PAT_IO_OUTCOME_LEASE_WINDOW')

    def test_disjoint_applicability_ranges_refuse(self):
        def change(a):
            a['applicability']['all'] += [dict(field='parameters.duration', op='range', minimum=1, maximum=20),
                                        dict(field='parameters.duration', op='range', minimum=30, maximum=40)]
        self.static_rejected(setup_changed(change), 'PAT_IO_OUTCOME_EMPTY_APPLICABILITY')

    def test_applicability_cannot_fill_sparse_enum_holes(self):
        def change(a):
            a['parameters']['duration']['valueSchema']['enum'] = [100, 10, 1]
            a['applicability']['all'].append(dict(field='parameters.duration', op='range', minimum=2, maximum=9))
        self.static_rejected(setup_changed(change), 'PAT_IO_OUTCOME_EMPTY_APPLICABILITY')

    def test_sparse_domain_nominal_is_an_actual_enum_member(self):
        setup = setup_changed(lambda a: a['parameters']['duration']['valueSchema'].update(enum=[100, 9, 1]))
        setup['static_contract']['applicableDomains'] = copy.deepcopy(setup['static_contract']['declaredDomains'])
        setup['static_contract']['nominalParameters']['duration'] = 9
        result = inspect_static_policy(expected_setup=setup)
        self.assertEqual(result['derivedContract']['nominalParameters'], {'duration': 9})
        self.assertEqual(result['derivedContract']['schedule']['steps'][1]['finishMaxOffsetMs'], 200)

    def test_narrowing_applicability_preserves_whole_declared_schedule(self):
        def change(a):
            a['applicability']['all'].append(dict(field='parameters.duration', op='range', minimum=10, maximum=20))
        setup = setup_changed(change)
        setup['static_contract']['applicableDomains']['duration'].update(minimum=10, maximum=20)
        setup['static_contract']['nominalParameters']['duration'] = 15
        result = inspect_static_policy(expected_setup=setup)
        self.assertEqual(result['derivedContract']['schedule']['steps'][1]['finishMaxOffsetMs'], 200)

    def test_static_policy_is_not_an_execution_or_qualification_verdict(self):
        result = inspect_static_policy(expected_setup=config.load()['expected_setup'])
        self.assertTrue(result['staticTimingPolicyChecked'])
        self.assertFalse(result['independentOutcomeChecked']); self.assertFalse(result['qualificationPassed'])

    def test_complete_outcome_still_rejects_a_forged_parent_status(self):
        def edit(doc):
            if doc['kind'] == 'trial_observation': doc['value']['procedure']['executionState'] = 'failed'
        case = config.rewrite(edit=edit)
        with self.assertRaisesRegex(ValueError, 'PAT_IO_PROCEDURE_OBSERVATION'): inspect_trial_outcome(**case)

    def test_static_and_full_apis_are_pure_and_preserve_inputs(self):
        for case in (config.load(), config.load(config.REVOKED), recovery.load(recovery.SETTLE_LOSS)):
            before = copy.deepcopy(case)
            with patch.object(builtins, 'open', side_effect=AssertionError('file I/O')), \
                 patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
                 patch.object(time, 'time', side_effect=AssertionError('wall clock')), \
                 patch.object(time, 'monotonic', side_effect=AssertionError('monotonic clock')):
                self.assertTrue(inspect_static_policy(expected_setup=case['expected_setup'])['staticTimingPolicyChecked'])
                self.assertTrue(inspect_trial_outcome(**case)['completeHistoryChecked'])
            self.assertEqual(case, before)

    def test_module_imports_only_contracts_and_independent_readers(self):
        source = Path(__file__).parents[1]/'hms/pat_io_outcome_history.py'
        tree = ast.parse(source.read_text())
        modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(set(modules), {'__future__', 'contracts', 'pat_io_board_history', 'pat_io_correspondence',
                                      'pat_io_refusal_history', 'pat_io_transcript'})
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))
