"""Trusted denial causes, exact event folding and structurally valid attacks."""
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
from hms.pat_io_refusal_history import inspect_refusal_history
from hms.pat_io_observation_history import inspect_observed_execution_history
from hms.pat_io_operation_history import _fold as operations, inspect_operation_history
from hms.pat_io_procedure_history import _fold as procedures, inspect_procedure_history
from hms.pat_io_transcript import _read
import test_pat_io_configuration_history as config
import test_pat_io_authorized_history as active
import test_pat_io_recovery_history as recovery

PARENT = 'test_configuration_revoked_grant_prevents_parent_admission'
CHILD = config.REVOKED


def retimed(name, phase, target):
    """Data-only clock insertion with complete reference/accounting rebuild."""
    def legacy(v, tables):
        if v['phase'] >= phase and name == CHILD:
            for row in tables['events']:
                if row['kind'] == 'rejected_before_dispatch': row['time_ms'] = target
            if not v['label'].endswith(':before'):
                next(row for row in tables['meta'] if row['key'] == 'last_clock')['value'] = str(target)
    def configuration(v, tables, resolver):
        if name == CHILD and v['phase'] >= phase and not v['label'].endswith(':before'):
            for row in tables['reg_observations']:
                obs = json.loads(row['document']); obs['receipt']['ticksMs'] = obs['acquisition']['ticksMs'] = target
                row['document'] = canonical(obs).decode()
            for row in tables['reg_presence']: row['expires_ms'] = target + 3000
    def edit(doc):
        value = doc['value']
        if doc['kind'] in {'checkpoint', 'snapshot'} and value['phase'] >= phase:
            value['wallMs'] = value['monotonicMs'] = target
        if doc['kind'].startswith('call_') and value['phase'] >= phase: value['clock'] = target
        if doc['kind'] == 'trial_observation': value['clock'] = target
    case = config.rewrite(name, legacy=legacy, mutate=configuration, edit=edit)
    def remap(value, mapping):
        if type(value) is dict:
            if set(value) == {'path', 'bytes', 'sha256'} and value['path'] in mapping:
                return copy.deepcopy(mapping[value['path']])
            return {k: remap(v, mapping) for k, v in value.items()}
        if type(value) is list: return [remap(v, mapping) for v in value]
        return value
    def writer():
        refs, files = [], {}
        def add(doc):
            raw = canonical(doc); path = '%06d.json' % len(refs)
            ref = dict(path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            files[path] = raw; refs.append(ref); return ref
        return refs, files, add
    refs, files, add = writer(); mapping = {}; inserted = False
    for ref in case['references']:
        doc = json.loads(case['files'][ref['path']])
        if doc['kind'] == 'checkpoint' and doc['value']['phase'] == phase and doc['value']['label'].endswith(':before'):
            assert not inserted
            add(dict(profile=doc['profile'], kind='clock_advanced', value={'from': 1000000, 'to': target})); inserted = True
        doc = remap(doc, mapping)
        if doc['kind'] == 'trial_observation':
            doc['value'].update(evidenceRecords=len(refs), evidenceBytes=sum(r['bytes'] for r in refs))
        mapping[ref['path']] = add(doc)
    assert inserted
    c_refs, c_files, c_add = writer(); c_map = {}; pairs = []
    for ref in case['configuration']['records']:
        original = json.loads(case['configuration_files'][ref['path']]); doc = remap(original, c_map)
        if doc['kind'] == 'header': doc['value']['setupRecords'] = [mapping[r['path']] for r in original['value']['setupRecords']]
        if doc['kind'] == 'snapshot': doc['value']['checkpoint'] = mapping[original['value']['checkpoint']['path']]
        c_map[ref['path']] = c_add(doc)
        if doc['kind'] == 'snapshot': pairs.append(dict(checkpoint=doc['value']['checkpoint'], configuration=c_map[ref['path']]))
    case.update(references=refs, files=files, configuration_files=c_files)
    case['configuration'].update(records=c_refs, snapshots=pairs, configurationBytes=sum(r['bytes'] for r in c_refs),
        combinedRecords=len(refs) + len(c_refs), combinedBytes=sum(r['bytes'] for r in refs + c_refs))
    return case


def retained_admin(name):
    original = config.load(name); grants = original['expected_authority']['initialGrants']
    def mutate(v, tables, resolver):
        tables['reg_grants'] = copy.deepcopy(grants)
        next(row for row in tables['reg_meta'] if row['key'] == 'revision')['value'] = '13'
    case = config.rewrite(name, mutate=mutate); case['expected_authority']['grantChanges'] = []
    return case


class IoRefusalHistoryTests(unittest.TestCase):
    def rejected(self, case, code):
        _read(case['references'], case['files'], case['expected_setup'])
        with self.assertRaises(ValueError) as caught: inspect_refusal_history(**case)
        self.assertEqual(caught.exception.code, code)

    def test_all_twenty_six_configured_histories_compose_with_sampling(self):
        counts = dict(fixtures=0, snapshots=0, samples=0, parentRefusals=0, childRefusals=0)
        for module in (config, active, recovery):
            catalog = json.loads((module.FIXTURES / 'index.json').read_bytes())
            for fixture in catalog['fixtures']:
                with self.subTest(method=fixture['method']):
                    result = inspect_refusal_history(**module.load(fixture['method']))
                    for key in ('trustedGrantPlanMatched', 'configurationHistoryChecked', 'patCorrespondenceChecked',
                                'permissionRefusalCausesChecked', 'observationSampleSemanticsChecked', 'boardHistoryChecked',
                                'operationHistoryChecked', 'procedureHistoryChecked'): self.assertTrue(result[key])
                    for key in ('configurationAttested', 'compilerIdentityAttested', 'physicalMeasurementChecked',
                                'staticTimingPolicyChecked', 'allFaultScenariosChecked', 'independentOutcomeChecked',
                                'qualificationPassed'): self.assertFalse(result[key])
                    counts['fixtures'] += 1; counts['snapshots'] += result['sampling']['snapshotsChecked']
                    counts['samples'] += result['sampling']['samplesProduced']
                    counts['parentRefusals'] += sum(r['kind'] == 'parent_before_acceptance' for r in result['refusalsChecked'])
                    counts['childRefusals'] += sum(r['kind'] == 'child_before_dispatch' for r in result['refusalsChecked'])
        self.assertEqual(counts, dict(fixtures=26, snapshots=434, samples=1288, parentRefusals=1, childRefusals=1))

    def test_parent_refusal_has_no_parent_or_child_or_effect(self):
        result = inspect_refusal_history(**config.load(PARENT))
        self.assertIsNone(result['procedures']['derivedProcedure'])
        self.assertEqual(result['operations']['operationsChecked'], 0)
        self.assertEqual(result['operations']['heldClaims'], 0)
        self.assertEqual(result['operations']['resourceFloors'], [])
        self.assertEqual(result['refusalsChecked'], [dict(phase=2, kind='parent_before_acceptance', code='ACCESS_DENIED')])
        self.assertTrue(all(r['activations'] == 0 for r in result['board']['instances']))

    def test_child_refusal_preserves_floor_and_parent_until_its_next_phase(self):
        result = inspect_refusal_history(**config.load(CHILD))
        self.assertEqual(result['operations']['operationsChecked'], 1)
        self.assertEqual(result['operations']['eventsChecked'], 2)
        self.assertEqual(result['operations']['heldClaims'], 0)
        self.assertEqual(result['operations']['unresolvedOperationIds'], [])
        self.assertEqual(result['operations']['resourceFloors'], [dict(resource='atom:pin5', fence=1)])
        parent = result['procedures']['derivedProcedure']
        self.assertEqual(parent['executionState'], 'running'); self.assertEqual(parent['eventSequence'], 2)
        self.assertEqual(parent['steps'][0]['executionState'], 'rejected_before_dispatch')
        self.assertFalse(parent['mayHaveActed'])
        self.assertTrue(all(r['activations'] == 0 for r in result['board']['instances']))

    def test_standalone_operation_api_still_refuses_unjoined_permission_cause(self):
        case = config.load(CHILD)
        with self.assertRaisesRegex(ValueError, 'PAT_IO_OPERATION_PREDISPATCH_CAUSE'):
            inspect_operation_history(case['references'], case['files'], expected_setup=case['expected_setup'])

    def test_standalone_procedure_api_still_refuses_unjoined_permission_cause(self):
        case = config.load(PARENT)
        with self.assertRaisesRegex(ValueError, 'PAT_IO_PROCEDURE_SUBMIT_FAILURE_UNIMPLEMENTED'):
            inspect_procedure_history(case['references'], case['files'], expected_setup=case['expected_setup'])

    def test_operation_private_handoff_must_be_consumed(self):
        case = config.load(); transcript = _read(case['references'], case['files'], case['expected_setup'])
        with self.assertRaisesRegex(ValueError, 'PAT_IO_OPERATION_UNUSED_REFUSAL'):
            operations(transcript, case['expected_setup'], checked_refusals={(0, 'invented'): 'ACCESS_DENIED'})

    def test_parent_private_handoff_must_be_consumed(self):
        case = config.load(); transcript = _read(case['references'], case['files'], case['expected_setup'])
        with self.assertRaisesRegex(ValueError, 'PAT_IO_PROCEDURE_UNUSED_REFUSAL'):
            procedures(transcript, checked_refusals={0: 'ACCESS_DENIED'})

    def test_operation_private_handoff_cannot_change_the_reason(self):
        case = config.load(CHILD); transcript = _read(case['references'], case['files'], case['expected_setup'])
        cp = next(cp for cp in transcript['checkpoints'] if cp['value']['label'] == 'drive:adapters:after')
        op = next(r['value']['operationIds'][0] for r in transcript['records'] if r['kind'] == 'trial_observation')
        with self.assertRaisesRegex(ValueError, 'PAT_IO_OPERATION_PREDISPATCH_CAUSE'):
            operations(transcript, case['expected_setup'], checked_refusals={(cp['record'], op): 'invented'})

    def test_parent_private_handoff_cannot_change_the_reason(self):
        case = config.load(PARENT); transcript = _read(case['references'], case['files'], case['expected_setup'])
        cp = next(cp for cp in transcript['checkpoints'] if cp['value']['label'] == 'submit:after_error')
        with self.assertRaisesRegex(ValueError, 'PAT_IO_PROCEDURE_SUBMIT_REFUSAL'):
            procedures(transcript, checked_refusals={cp['record']: 'invented'})

    def test_reported_parent_error_does_not_authorize_its_cause(self):
        self.rejected(config.rewrite(PARENT, edit=lambda d: d['value'].update(code='invented') if d['kind'] == 'call_failed' else None),
                      'PAT_IO_CONFIGURATION_PARENT_REFUSAL')

    def test_reported_child_reason_does_not_authorize_its_cause(self):
        def change(v, t):
            for event in t['events']:
                if event['kind'] == 'rejected_before_dispatch': event['payload'] = canonical({'reason': 'invented'}).decode()
        self.rejected(config.rewrite(CHILD, legacy=change), 'PAT_IO_CONFIGURATION_REFUSAL_CAUSE')

    def test_parent_denial_requires_the_actual_trusted_grant_loss(self):
        self.rejected(retained_admin(PARENT), 'PAT_IO_CONFIGURATION_PARENT_REFUSAL')

    def test_child_denial_requires_the_actual_trusted_grant_loss(self):
        self.rejected(retained_admin(CHILD), 'PAT_IO_CONFIGURATION_REFUSAL_CAUSE')

    def test_captured_grant_loss_cannot_replace_the_trusted_schedule(self):
        case = config.load(CHILD); case['expected_authority']['grantChanges'] = []
        self.rejected(case, 'PAT_IO_CONFIGURATION_GRANTS')

    def test_stalled_accepted_history_requires_the_expected_permission_refusal(self):
        remembered = {}; operation = []
        def change(v, t):
            if v['phase'] == 4 and v['label'].endswith(':before'):
                remembered.update({k: copy.deepcopy(t[k]) for k in ('operations', 'events', 'claims')})
                operation[:] = [t['operations'][0]['id']]
            elif remembered:
                t.update(copy.deepcopy(remembered))
        def edit(d):
            if d['kind'] == 'trial_observation':
                v = d['value']; v['unresolvedOperations'] = list(operation)
                v['procedure']['unresolvedOperations'] = list(operation)
                v['procedure']['steps'][0].update(executionState='accepted', eventSequence=1, heldResources=1)
        case = config.rewrite(CHILD, legacy=change, edit=edit)
        self.assertTrue(inspect_observed_execution_history(**case)['operationHistoryChecked'])
        self.rejected(case, 'PAT_IO_REFUSAL_REFUSAL_REQUIRED')

    def test_permission_refusal_cannot_hide_board_effects(self):
        def change(v, t):
            if v['phase'] == 4 and not v['label'].endswith(':before'):
                next(r for r in t['io_effects'] if r['instance'] == 'sim:gpio5')['activations'] = 1
        self.rejected(config.rewrite(CHILD, legacy=change), 'PAT_IO_REFUSAL_REFUSAL_BOARD_EFFECT')

    def test_refused_child_cannot_retain_claims(self):
        saved = []
        def change(v, t):
            if v['phase'] == 4 and v['label'].endswith(':before'): saved[:] = copy.deepcopy(t['claims'])
            elif saved: t['claims'] = copy.deepcopy(saved)
        self.rejected(config.rewrite(CHILD, legacy=change), 'PAT_IO_CONFIGURATION_REFUSAL_EFFECT')

    def test_refused_child_cannot_claim_possible_handoff(self):
        self.rejected(config.rewrite(CHILD, legacy=lambda v, t: t['operations'][0].update(may_have_acted=1)
            if v['phase'] == 4 and not v['label'].endswith(':before') else None), 'PAT_IO_CONFIGURATION_REFUSAL_EFFECT')

    def test_refused_child_still_needs_complete_event_sequence(self):
        def change(v, t):
            if v['phase'] == 4 and not v['label'].endswith(':before'):
                t['operations'][0]['sequence'] = 3
                next(e for e in t['events'] if e['kind'] == 'rejected_before_dispatch')['sequence'] = 3
        self.rejected(config.rewrite(CHILD, legacy=change), 'PAT_IO_OPERATION_EVENT_SEQUENCE')

    def test_parent_refusal_cannot_mutate_unrelated_authority_state(self):
        def change(v, t):
            if v['phase'] == 2 and not v['label'].endswith(':before'):
                t['resource_floors'] = [dict(deployment='simulation:io-hub', resource='atom:pin5', fence=1)]
        self.rejected(config.rewrite(PARENT, legacy=change), 'PAT_IO_REFUSAL_PARENT_REFUSAL_MUTATED_STATE')

    def test_parent_refusal_cannot_report_an_invented_parent(self):
        self.rejected(config.rewrite(PARENT, edit=lambda d: d['value'].update(procedure={}) if d['kind'] == 'trial_observation' else None),
                      'PAT_IO_PROCEDURE_OBSERVATION')

    def test_child_refusal_cannot_advance_parent_without_a_procedure_phase(self):
        self.rejected(config.rewrite(CHILD, legacy=lambda v, t: t['pr_procedures'][0].update(state='failed', reason='CHILD_REJECTED_BEFORE_DISPATCH')
            if v['phase'] == 4 and not v['label'].endswith(':before') else None), 'PAT_IO_PROCEDURE_ROW')

    def test_missing_prior_claim_precedes_permission_denial(self):
        self.rejected(config.rewrite(CHILD, legacy=lambda v, t: t.update(claims=[]) if v['phase'] == 4 and v['label'].endswith(':before') else None),
                      'PAT_IO_REFUSAL_PRE_DISPATCH_OWNERSHIP')

    def test_parent_start_deadline_precedes_permission_denial(self):
        self.rejected(retimed(PARENT, 2, 1000500), 'PAT_IO_REFUSAL_PARENT_TIME_PRECEDENCE')

    def test_namespace_expiry_precedes_permission_denial(self):
        self.rejected(retimed(PARENT, 2, 1010001), 'PAT_IO_REFUSAL_NAMESPACE_PRECEDENCE')

    def test_child_start_deadline_precedes_permission_denial(self):
        self.rejected(retimed(CHILD, 4, 1000500), 'PAT_IO_REFUSAL_TIMING_PRECEDENCE')

    def test_dispatch_refusal_preserves_the_actual_engine_return(self):
        self.rejected(config.rewrite(CHILD, edit=lambda d: d['value'].update(result={'invented': True})
            if d['kind'] == 'call_returned' and d['value']['phase'] == 4 else None), 'PAT_IO_REFUSAL_DISPATCH_CALL')

    def test_inspection_is_pure_and_preserves_inputs(self):
        cases = [config.load(PARENT), config.load(CHILD), recovery.load(recovery.SETTLE_LOSS)]
        for case in cases:
            before = copy.deepcopy(case)
            with patch.object(builtins, 'open', side_effect=AssertionError('file')), patch.object(Path, 'read_bytes', side_effect=AssertionError('file')), patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
                self.assertTrue(inspect_refusal_history(**case)['permissionRefusalCausesChecked'])
            self.assertEqual(case, before)

    def test_imports_are_only_contracts_and_independent_readers(self):
        tree = ast.parse((Path(__file__).parents[1] / 'hms/pat_io_refusal_history.py').read_text())
        self.assertEqual({n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)},
            {'__future__', 'contracts', 'pat_io_authorized_history', 'pat_io_board_history', 'pat_io_configuration_history',
             'pat_io_correspondence', 'pat_io_observation_history', 'pat_io_operation_history', 'pat_io_procedure_history',
             'pat_io_recovery_history'})
        self.assertFalse(any(isinstance(n, ast.Import) for n in ast.walk(tree)))
