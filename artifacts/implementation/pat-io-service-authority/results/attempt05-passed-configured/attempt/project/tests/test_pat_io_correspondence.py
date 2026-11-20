"""PAT/input mutations beyond internally consistent operation/parent histories."""
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
from hms.pat_io_correspondence import IoCorrespondenceError, inspect_pat_correspondence
from hms.pat_io_procedure_history import inspect_procedure_history
from test_pat_io_transcript import FIXTURES, GPIO, REOPEN, load
from test_pat_io_board_history import PWM, digest, rewrite

NEGATIVE = 'test_negative_lowering_retains_type_and_never_admits_work'


def plan_edit(change):
    def edit(doc):
        if doc['kind'] == 'compiled_plan': change(doc['value'])
        elif doc['kind'] == 'call_returned' and doc['value']['label'] == 'lower': change(doc['value']['result'])
    return edit


def input_edit(change):
    def edit(doc):
        if doc['kind'] == 'lower_input': change(doc['value'])
    return edit


def revised_artifact(name, change):
    """Change trusted PAT bytes and all associated PAT hashes, not its output.

    This models a coherent executed history being attributed to another intended
    program. It is generated adversarial data, not a new simulator execution.
    """
    _, _, _, setup = load(name); artifact = copy.deepcopy(setup['artifact']); change(artifact)
    artifact['outcomeContract']['requiredCompletedSteps'] = [s['stepId'] for s in artifact['steps']]
    sha = digest(b'HMS-PAT-JCS-SHA256-v0.1', artifact)
    def edit(doc):
        if doc['kind'] == 'artifact': doc['value'] = copy.deepcopy(artifact)
        elif doc['kind'] == 'static_contract': doc['value']['artifactDigest'] = sha
        elif doc['kind'] == 'runtime_opened':
            for field in ('originalEnvironment', 'workerEnvironment'): doc['value'][field]['patDigest'] = sha
        else: plan_edit(lambda v: v.update(patDigest=sha))(doc)
    return edit


class IoCorrespondenceTests(unittest.TestCase):
    def rewritten(self, name, edit):
        refs, files, _ = rewrite(name, edit_record=edit)
        setup = {v['kind']: v['value'] for v in (json.loads(files[r['path']]) for r in refs[:4])}
        return refs, files, setup

    def rejected(self, edit, code, *, name=GPIO):
        refs, files, setup = self.rewritten(name, edit)
        # Every adversary here still passes structural, operation and parent
        # validation. New refusal must be about correspondence, not stale hashes.
        self.assertTrue(inspect_procedure_history(refs, files, expected_setup=setup)['procedureHistoryChecked'])
        with self.assertRaises(IoCorrespondenceError) as caught:
            inspect_pat_correspondence(refs, files, expected_setup=setup)
        self.assertEqual(caught.exception.code, 'PAT_IO_CORRESPONDENCE_' + code)

    def test_all_nineteen_actual_lowerings_match_or_truthfully_refuse(self):
        totals = [0, 0, 0]
        for fixture in json.loads((FIXTURES / 'index.json').read_bytes())['fixtures']:
            with self.subTest(method=fixture['method']):
                refs, files, _, setup = load(fixture['method'])
                result = inspect_pat_correspondence(refs, files, expected_setup=setup)
                self.assertTrue(result['patCorrespondenceChecked']); self.assertTrue(result['historicalIdentityConsistencyChecked'])
                for key in ('compilerIdentityAttested', 'staticTimingPolicyChecked', 'liveConfigurationAttested',
                            'operationHistoryChecked', 'procedureHistoryChecked', 'boardHistoryChecked', 'independentOutcomeChecked', 'qualificationPassed'):
                    self.assertFalse(result[key])
                if result['parameterOutcome'] == 'refused':
                    self.assertEqual(result['refusalCode'], 'PAT_PARAMETER_OUT_OF_DOMAIN'); totals[1] += 1
                    self.assertIsNone(result['requestDigest'])
                else:
                    totals[0] += 1; totals[2] += result['stepsChecked']
        self.assertEqual(totals, [18, 1, 35])

    def test_changed_parameter_cannot_reuse_old_consistent_execution(self):
        self.rejected(input_edit(lambda v: v['parameters']['duration'].update(value=21)), 'REQUEST')

    def test_declared_boundary_value_still_requires_its_own_instructions(self):
        self.rejected(input_edit(lambda v: v['parameters']['duration'].update(value=100)), 'REQUEST')

    def test_boolean_cannot_be_coerced_into_an_integer_parameter(self):
        self.rejected(input_edit(lambda v: v['parameters']['duration'].update(type='boolean', value=True)), 'REFUSAL')

    def test_integral_number_tag_cannot_be_coerced_to_integer(self):
        self.rejected(input_edit(lambda v: v['parameters']['duration'].update(type='number')), 'REFUSAL')

    def test_missing_parameter_requires_invalid_parameters_refusal(self):
        self.rejected(input_edit(lambda v: v['parameters'].clear()), 'REFUSAL')

    def test_extra_parameter_is_not_silently_ignored(self):
        self.rejected(input_edit(lambda v: v['parameters'].update(extra={'type': 'integer', 'value': 1})), 'REFUSAL')

    def test_parameter_above_declared_domain_cannot_lower(self):
        self.rejected(input_edit(lambda v: v['parameters']['duration'].update(value=101)), 'REFUSAL')

    def test_wrong_task_kind_cannot_reuse_matching_physical_arguments(self):
        self.rejected(input_edit(lambda v: v['context'].update(taskKind='other:task')), 'REFUSAL')

    def test_wrong_input_profile_is_not_applicable(self):
        self.rejected(input_edit(lambda v: v['context'].update(inputProfile='other:input')), 'REFUSAL')

    def test_physical_context_cannot_be_relabelled_simulation(self):
        self.rejected(input_edit(lambda v: v['context'].update(evidenceMode='physical')), 'REFUSAL')

    def test_unknown_context_field_is_not_silently_ignored(self):
        self.rejected(input_edit(lambda v: v['context'].update(unapproved=True)), 'REFUSAL')

    def test_worker_deployment_override_is_explicit_and_deterministic(self):
        refs, files, setup = self.rewritten(GPIO, input_edit(lambda v: v['context'].update(deployment='ignored:caller-value')))
        result = inspect_pat_correspondence(refs, files, expected_setup=setup)
        self.assertEqual(result['parameterOutcome'], 'lowered'); self.assertFalse(result['liveConfigurationAttested'])

    def test_negative_integral_number_cannot_be_relabelled_valid_integer(self):
        self.rejected(input_edit(lambda v: v['parameters']['duration'].update(type='integer')), 'REFUSAL', name=NEGATIVE)

    def test_negative_refusal_code_is_derived_from_input(self):
        def edit(doc):
            if doc['kind'] == 'call_failed' and doc['value']['label'] == 'lower': doc['value']['code'] = 'PAT_NOT_APPLICABLE'
        self.rejected(edit, 'REFUSAL', name=NEGATIVE)

    def test_negative_refusal_cannot_be_arbitrary_exception(self):
        def edit(doc):
            if doc['kind'] == 'call_failed' and doc['value']['label'] == 'lower': doc['value']['exception'] = 'RuntimeError'
        self.rejected(edit, 'REFUSAL', name=NEGATIVE)

    def test_literal_gpio_value_is_independent_of_observed_history(self):
        edit = revised_artifact(GPIO, lambda a: a['steps'][0]['arguments']['level'].update(literal=0))
        self.rejected(edit, 'REQUEST')

    def test_literal_pwm_frequency_is_independent_of_observed_history(self):
        edit = revised_artifact(PWM, lambda a: a['steps'][0]['arguments']['frequencyHz'].update(literal=2000))
        self.rejected(edit, 'REQUEST', name=PWM)

    def test_child_step_identity_must_come_from_pat(self):
        self.rejected(revised_artifact(GPIO, lambda a: a['steps'][1].update(stepId='step:changed')), 'REQUEST')

    def test_instruction_count_must_match_pat(self):
        self.rejected(revised_artifact(GPIO, lambda a: a['steps'].pop()), 'REQUEST')

    def test_start_offset_must_not_be_silently_changed(self):
        self.rejected(revised_artifact(GPIO, lambda a: a['steps'][0]['timing'].update(notBeforeOffsetMs=1)), 'REQUEST')

    def test_run_budget_must_come_from_pat(self):
        self.rejected(revised_artifact(GPIO, lambda a: a['steps'][0]['timing'].update(maxRunMs=499)), 'REQUEST')

    def test_request_digest_is_recomputed(self):
        self.rejected(plan_edit(lambda v: v.update(requestDigest='sha256:' + '0' * 64)), 'PLAN_METADATA')

    def test_plan_pat_digest_cannot_be_swapped(self):
        self.rejected(plan_edit(lambda v: v.update(patDigest='sha256:' + '0' * 64)), 'PLAN_METADATA')

    def test_run_binding_digest_binds_fresh_session(self):
        self.rejected(plan_edit(lambda v: v.update(runBindingDigest='sha256:' + '0' * 64)), 'PLAN_METADATA')

    def test_plan_compiler_identity_must_match_captured_environments(self):
        self.rejected(plan_edit(lambda v: v.update(compilerDigest='sha256:' + '0' * 64)), 'PLAN_METADATA')

    def test_dependency_metadata_digest_is_recomputed(self):
        self.rejected(plan_edit(lambda v: v['dependencies'][0].update(metadataDigest='sha256:' + '0' * 64)), 'PLAN_METADATA')

    def test_dependency_driver_identity_cannot_change(self):
        self.rejected(plan_edit(lambda v: v['dependencies'][0].update(driverDigest='sha256:' + '0' * 64)), 'PLAN_METADATA')

    def test_rehashed_environment_cannot_change_deployment(self):
        def change(v):
            v['evaluationEnvironment']['deployment'] = 'simulation:other'
            v['environmentDigest'] = digest(b'HMS-PAT-ENVIRONMENT-v0.1', v['evaluationEnvironment'])
        self.rejected(plan_edit(change), 'PLAN_METADATA')

    def test_lowering_report_cannot_claim_admission(self):
        self.rejected(plan_edit(lambda v: v['report'].update(admitted=True)), 'PLAN_METADATA')

    def test_lowering_report_cannot_claim_physical_verification(self):
        self.rejected(plan_edit(lambda v: v['report'].update(physicalObjectiveVerified=True)), 'PLAN_METADATA')

    def test_hidden_unit_conversion_is_not_allowed(self):
        self.rejected(plan_edit(lambda v: v['report']['unitConversions'].append({'from': 's', 'to': 'ms'})), 'PLAN_METADATA')

    def test_worker_environment_must_use_reopened_session(self):
        def edit(doc):
            if doc['kind'] == 'runtime_opened' and not doc['value']['create']:
                doc['value']['workerEnvironment']['dependencies'][0]['endpointSession'] = 'session:stale'
        self.rejected(edit, 'ENVIRONMENT', name=REOPEN)

    def test_original_environment_binding_digest_is_recomputed(self):
        def edit(doc):
            if doc['kind'] == 'runtime_opened': doc['value']['originalEnvironment']['dependencies'][0]['bindingDigest'] = 'sha256:' + '0' * 64
        self.rejected(edit, 'ENVIRONMENT')

    def test_static_contract_must_be_associated_with_trusted_descriptor(self):
        def edit(doc):
            if doc['kind'] == 'static_contract': doc['value']['descriptorDigest'] = 'sha256:' + '0' * 64
        self.rejected(edit, 'STATIC_ASSOCIATION')

    def test_consistent_historical_compiler_label_is_not_current_attestation(self):
        _, _, entries, setup = load(GPIO); compiler = 'sha256:' + 'a' * 64
        opening = next(d['value'] for _, d in entries if d['kind'] == 'runtime_opened')
        def environment(v):
            v['compilerDigest'] = compiler; v['evaluationEnvironment']['compilerDigest'] = compiler
            v['environmentDigest'] = digest(b'HMS-PAT-ENVIRONMENT-v0.1', v['evaluationEnvironment'])
        def plan(v):
            environment(v)
            bound = setup['original_descriptor'] | {'endpointSession': opening['session']}
            v['runBindingDigest'] = digest(b'HMS-PAT-RUN-BINDING-v0.1', {'bindings': {'io': bound},
                'compilerDigest': compiler, 'targetProfile': setup['artifact']['targetProfile']})
        def edit(doc):
            if doc['kind'] == 'runtime_opened':
                for field in ('originalEnvironment', 'workerEnvironment'): environment(doc['value'][field])
            else: plan_edit(plan)(doc)
        refs, files, setup = self.rewritten(GPIO, edit)
        result = inspect_pat_correspondence(refs, files, expected_setup=setup)
        self.assertTrue(result['historicalIdentityConsistencyChecked'])
        self.assertFalse(result['compilerIdentityAttested']); self.assertFalse(result['qualificationPassed'])

    def test_pure_inspection_has_no_compiler_import_io_or_input_mutation(self):
        refs, files, _, setup = load(PWM)
        source = Path(__file__).parents[1] / 'hms/pat_io_correspondence.py'
        imports = {n.module for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imports, {'__future__', 'contracts', 'pat_io_board_history', 'pat_io_transcript', 'resource_topology'})
        before = copy.deepcopy((refs, files, setup))
        with patch.object(builtins, 'open', side_effect=AssertionError('file')), \
             patch.object(Path, 'open', side_effect=AssertionError('path')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('sqlite')), \
             patch.object(time, 'time', side_effect=AssertionError('clock')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            result = inspect_pat_correspondence(refs, files, expected_setup=setup)
        self.assertTrue(result['patCorrespondenceChecked']); self.assertEqual((refs, files, setup), before)
