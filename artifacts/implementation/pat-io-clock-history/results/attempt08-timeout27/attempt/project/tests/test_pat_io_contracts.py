"""Original pure timing/planning checks; no Runtime or qualification execution."""
import copy
from contextlib import ExitStack
import itertools
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import SAFE_INTEGER, canonical
from hms.pat_compiler import compile_pat
from hms.pat_contracts import PatError
from hms.pat_io_contracts import IoSequencePolicy, CLOCK_POLICY, decode_case_input
from hms.synthetic_io_installation import DRIVER, definitions, installation_digest, normalize_installation
from test_io_synthetic_provider import installation
from test_resource_topology import generations

BASE = json.loads((Path(__file__).parent / 'fixtures/pat-compiler.json').read_text())


def parameter(lo, hi, unit, enum=None):
    schema = {'type': 'integer', 'minimum': lo, 'maximum': hi}
    if enum is not None:
        schema['enum'] = enum
    return {'valueSchema': schema, 'unit': unit, 'frame': None}


def program(*, pwm=False, count=1, literal=False, action=None):
    value = copy.deepcopy(BASE)
    action = action or ('pwm_burst' if pwm else 'gpio_pulse')
    value.update(name='finite-io-sequence', taskKind='sim.io.sequence', inputProfile='hms.sim.io.sequence/0.1')
    value['parameters'] = {} if literal else {'duration': parameter(1, 100, 'ms')}
    args = {'durationMs': {'literal': 20} if literal else {'parameter': 'duration'}}
    if pwm:
        args.update(frequencyHz={'literal': 1000}, dutyPermille={'literal': 375}, resolutionBits={'literal': 8})
    else:
        args['level'] = {'literal': 1}
    value['roles'] = {'io': {'capabilityFamily': 'sim:finite-gpio-pwm', 'actions': [action], 'driverProfiles': [DRIVER]}}
    value['steps'] = [{'stepId': 'step:' + str(i), 'role': 'io', 'actionId': action,
        'arguments': copy.deepcopy(args), 'timing': {'notBeforeOffsetMs': 0, 'latestStartOffsetMs': 500 if i == 0 else 9000,
            'maxRunMs': 500, 'latestCompletionOffsetMs': 10000}} for i in range(count)]
    value['timingBudget'] = {'latestStartOffsetMs': 500, 'latestCompletionOffsetMs': 10000, 'maxRunSumMs': count * 500}
    value['effectBudget']['maxInvocations'] = count
    value['outcomeContract']['requiredCompletedSteps'] = [s['stepId'] for s in value['steps']]
    return value


def descriptor(document, *, pwm=False, action=None):
    instance = 'sim:pwm5' if pwm else 'sim:gpio5'
    action = action or ('pwm_burst' if pwm else 'gpio_pulse')
    expected = definitions(document)[instance]
    units = ({'frequencyHz': 'Hz', 'dutyPermille': 'permille', 'resolutionBits': 'bit', 'durationMs': 'ms'}
             if pwm else {'level': '1', 'durationMs': 'ms'})
    fields = {key: {'profile': 'hms.pat.argument.fixed-schema-unit/0.1', 'unit': unit,
                    'frame': None, 'unitArgument': None, 'frameArgument': None} for key, unit in units.items()}
    return {'type': expected['type'], 'binding': expected['binding'], 'endpointSession': 'session:pure-fixture',
            'driverProfile': DRIVER, 'driverDigest': document['driverDigest'],
            'installationDigest': installation_digest(document), 'argumentMetadata': {action: fields}}


class IoContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = normalize_installation(installation())
        cls.policy = IoSequencePolicy(cls.document)
        cls.gpio = descriptor(cls.document)
        cls.pwm = descriptor(cls.document, pwm=True)

    def qualify(self, value, *, pwm=False, chosen=None):
        return self.policy.qualify(value, chosen if chosen is not None else (self.pwm if pwm else self.gpio))

    def refuses(self, value, code, **options):
        with self.assertRaises(PatError) as caught:
            self.qualify(value, **options)
        self.assertEqual(caught.exception.code, code)

    def test_gpio_and_pwm_have_explicit_semantics_and_no_qualification_claim(self):
        for pwm, primitive in [(False, 'gpio_pulse'), (True, 'pwm_burst')]:
            result = self.qualify(program(pwm=pwm), pwm=pwm)
            self.assertEqual(result['primitive'], primitive)
            self.assertEqual(result['schedule']['profile'], CLOCK_POLICY)
            self.assertEqual(result['schedule']['steps'][0]['finishMaxOffsetMs'], 100)
            self.assertIs(result['qualificationPassed'], False)
            self.assertIs(result['schedule']['hostTimingGuaranteed'], False)

    def test_action_spelling_does_not_define_the_primitive(self):
        document = copy.deepcopy(self.document)
        for row in document['topology']['consumers']:
            if row['instanceId'] == 'sim:gpio5':
                row['actionId'] = 'opaque_write'
        for row in document['handlers']:
            if row['instanceId'] == 'sim:gpio5':
                row['actionId'] = 'opaque_write'
        document['initialGenerations'] = generations(document['topology'])
        document = normalize_installation(document)
        result = IoSequencePolicy(document).qualify(program(action='opaque_write'), descriptor(document, action='opaque_write'))
        self.assertEqual(result['primitive'], 'gpio_pulse')
        self.assertEqual(result['actionId'], 'opaque_write')

    def test_duration_4999_fits_but_5000_does_not(self):
        value = program()
        value['parameters']['duration'] = parameter(1, 4999, 'ms')
        value['steps'][0]['timing']['maxRunMs'] = 5000
        value['timingBudget']['maxRunSumMs'] = 5000
        self.assertEqual(self.qualify(value)['schedule']['steps'][0]['finishMaxOffsetMs'], 4999)
        value['parameters']['duration']['valueSchema']['maximum'] = 5000
        self.refuses(value, 'PAT_IO_DURATION_BUDGET')

    def test_applicability_cannot_repair_declared_duration_or_schema(self):
        for maximum, code in [(5000, 'PAT_IO_DURATION_BUDGET'), (5001, 'PAT_ARGUMENT_DOMAIN')]:
            value = program()
            value['parameters']['duration'] = parameter(1, maximum, 'ms')
            value['steps'][0]['timing']['maxRunMs'] = 5000
            value['timingBudget']['maxRunSumMs'] = 5000
            value['applicability']['all'].append({'field': 'parameters.duration', 'op': 'equals', 'literal': 1})
            self.refuses(value, code)

    def test_sparse_enum_uses_accepted_extrema_and_keeps_declared_schema(self):
        value = program()
        value['parameters']['duration'] = parameter(1, 5000, 'ms', [4999, 1])
        value['steps'][0]['timing']['maxRunMs'] = 5000
        value['timingBudget']['maxRunSumMs'] = 5000
        result = self.qualify(value)
        self.assertEqual(result['schedule']['steps'][0]['durationMaxMs'], 4999)
        self.assertEqual(result['declaredDomains']['duration']['maximum'], 5000)
        self.assertEqual(result['declaredDomains']['duration']['enum'], [1, 4999])

    def test_literal_duration_has_the_same_strict_budget(self):
        value = program(literal=True)
        value['steps'][0]['arguments']['durationMs']['literal'] = 500
        self.refuses(value, 'PAT_IO_DURATION_BUDGET')
        value['steps'][0]['arguments']['durationMs']['literal'] = 499
        self.assertEqual(self.qualify(value)['schedule']['steps'][0]['durationMinMs'], 499)

    def test_empty_exclusive_start_window_is_refused(self):
        value = program()
        value['steps'][0]['timing'].update(notBeforeOffsetMs=500, latestStartOffsetMs=500)
        self.refuses(value, 'PAT_IO_START_WINDOW')

    def test_later_step_start_checks_whole_predecessor_range(self):
        value = program(count=2)
        value['steps'][1]['timing']['latestStartOffsetMs'] = 100
        self.refuses(value, 'PAT_IO_START_WINDOW')
        value['steps'][1]['timing']['latestStartOffsetMs'] = 101
        result = self.qualify(value)['schedule']['steps'][1]
        self.assertEqual((result['admissionMinOffsetMs'], result['admissionMaxOffsetMs']), (1, 100))

    def test_sequential_completion_equality_is_refused(self):
        value = program(count=2)
        for step in value['steps']:
            step['timing']['maxRunMs'] = 101
        value['timingBudget']['maxRunSumMs'] = 202
        value['steps'][1]['timing'].update(latestStartOffsetMs=150, latestCompletionOffsetMs=200)
        self.refuses(value, 'PAT_IO_COMPLETION_WINDOW')
        value['steps'][1]['timing']['latestCompletionOffsetMs'] = 201
        self.assertEqual(self.qualify(value)['schedule']['steps'][1]['finishMaxOffsetMs'], 200)

    def test_wait_before_start_consumes_lease(self):
        value = program(literal=True)
        value['steps'][0]['arguments']['durationMs']['literal'] = 1
        value['steps'][0]['timing'].update(notBeforeOffsetMs=59999, latestStartOffsetMs=60001,
                                          maxRunMs=2, latestCompletionOffsetMs=70000)
        value['timingBudget'] = {'latestStartOffsetMs': 60001, 'latestCompletionOffsetMs': 70000, 'maxRunSumMs': 2}
        self.refuses(value, 'PAT_IO_LEASE_WINDOW')
        value['steps'][0]['timing']['notBeforeOffsetMs'] = 59998
        row = self.qualify(value)['schedule']['steps'][0]
        self.assertEqual(row['admissionMaxOffsetMs'], 0)
        self.assertEqual(row['finishMaxOffsetMs'], 59999)
        self.assertEqual(row['earliestLeaseExpiryOffsetMs'], 60000)

    def test_correlated_lease_enclosure_is_explicitly_conservative(self):
        value = program(count=2)
        for step in value['steps']:
            step['timing']['maxRunMs'] = 101
        value['steps'][1]['timing'].update(notBeforeOffsetMs=59999, latestStartOffsetMs=60000,
                                          latestCompletionOffsetMs=70000)
        value['timingBudget'].update(latestCompletionOffsetMs=70000, maxRunSumMs=202)
        # Actual lease residence is 59999 for every shared duration; independent
        # interval extrema deliberately reject this correlation in policy v0.1.
        self.assertTrue(all((59999 + duration) - duration < 60000 for duration in range(1, 101)))
        self.refuses(value, 'PAT_IO_LEASE_WINDOW')

    def test_small_domains_enclose_exhaustive_sequential_schedules(self):
        value = program(count=3)
        value['parameters'] = {'a': parameter(1, 3, 'ms'), 'b': parameter(1, 3, 'ms', [1, 3])}
        for step, name, start in zip(value['steps'], ['a', 'b', 'a'], [0, 2, 5]):
            step['arguments']['durationMs'] = {'parameter': name}
            step['timing']['notBeforeOffsetMs'] = start
        envelope = self.qualify(value)['schedule']['steps']
        for a, b in itertools.product(range(1, 4), [1, 3]):
            now = 0
            for index, duration in enumerate([a, b, a]):
                row = envelope[index]
                self.assertLessEqual(row['admissionMinOffsetMs'], now)
                self.assertLessEqual(now, row['admissionMaxOffsetMs'])
                while now < [0, 2, 5][index]:
                    now += 1
                self.assertLessEqual(row['startMinOffsetMs'], now)
                self.assertLessEqual(now, row['startMaxOffsetMs'])
                for _ in range(duration):
                    now += 1
                self.assertLessEqual(row['finishMinOffsetMs'], now)
                self.assertLessEqual(now, row['finishMaxOffsetMs'])

    def test_exact_integer_origin_bound_agrees_with_compiler(self):
        value = program(); result = self.qualify(value)
        origin = result['schedule']['maxOriginMs']
        options = dict(origin_ms=origin, caller_deadline_ms=SAFE_INTEGER, replay_namespace='replay:test',
                       procedure_key='parent:test', operation_keys={'step:0': 'child:test'},
                       context={'taskKind': value['taskKind'], 'inputProfile': value['inputProfile'],
                                'evidenceMode': 'simulation', 'deployment': 'simulation:io-hub'})
        plan = compile_pat(value, {'duration': 1}, {'io': self.gpio}, **options)
        self.assertEqual(plan['request']['procedure']['timing']['latestCompletionUnixMs'], SAFE_INTEGER)
        options['origin_ms'] += 1
        with self.assertRaisesRegex(PatError, 'PAT_TIME_BOUNDS'):
            compile_pat(value, {'duration': 1}, {'io': self.gpio}, **options)

    def test_units_and_frames_must_match_trusted_numeric_semantics(self):
        for field, wrong in [('unit', '1'), ('unit', 'seconds'), ('frame', 'world')]:
            value = program(); value['parameters']['duration'][field] = wrong
            self.refuses(value, 'PAT_SEMANTICS_MISMATCH')
        wrong = copy.deepcopy(self.gpio)
        wrong['argumentMetadata']['gpio_pulse']['durationMs']['unit'] = '1'
        self.refuses(program(), 'PAT_IO_UNSUPPORTED_SEMANTICS', chosen=wrong)

    def test_literal_boolean_and_integral_float_cannot_become_integer(self):
        for wrong in [True, 20.0]:
            value = program(literal=True); value['steps'][0]['arguments']['durationMs']['literal'] = wrong
            with self.assertRaises(PatError):
                self.qualify(value)
        value = program(); value['parameters']['duration']['valueSchema']['maximum'] = 100.0
        with self.assertRaises(PatError):
            self.qualify(value)

    def test_three_declared_axes_refuse_even_if_applicability_collapses_one(self):
        value = program(pwm=True)
        for key, lo, hi, unit in [('frequencyHz', 100, 10000, 'Hz'), ('dutyPermille', 0, 1000, 'permille')]:
            value['parameters'][key] = parameter(lo, hi, unit)
            value['steps'][0]['arguments'][key] = {'parameter': key}
        value['applicability']['all'].append({'field': 'parameters.dutyPermille', 'op': 'equals', 'literal': 500})
        self.refuses(value, 'PAT_IO_PARAMETER_AXIS_LIMIT', pwm=True)

    def test_singleton_parameter_does_not_add_a_varying_axis(self):
        value = program(pwm=True)
        value['parameters']['resolution'] = parameter(8, 8, 'bit')
        value['steps'][0]['arguments']['resolutionBits'] = {'parameter': 'resolution'}
        self.assertEqual(self.qualify(value, pwm=True)['nominalParameters']['resolution'], 8)

    def test_pwm_frequency_envelope_and_resolution_are_preserved(self):
        for field, wrong in [('frequencyHz', 99), ('frequencyHz', 10001), ('resolutionBits', 7), ('dutyPermille', 1001)]:
            value = program(pwm=True); value['steps'][0]['arguments'][field]['literal'] = wrong
            self.refuses(value, 'PAT_ARGUMENT_DOMAIN', pwm=True)

    def test_changed_installed_identity_or_binding_is_refused(self):
        for field in ['driverDigest', 'installationDigest']:
            wrong = copy.deepcopy(self.gpio); wrong[field] = 'sha256:' + 'f' * 64
            self.refuses(program(), 'PAT_IO_INSTALLATION_MISMATCH', chosen=wrong)
        wrong = copy.deepcopy(self.gpio); wrong['binding']['controlGeneration'] = 'changed:control'
        self.refuses(program(), 'PAT_IO_INSTALLATION_MISMATCH', chosen=wrong)

    def test_changed_source_identity_refuses_during_setup(self):
        wrong = copy.deepcopy(self.document); wrong['driverDigest'] = 'sha256:' + 'f' * 64
        with self.assertRaisesRegex(PatError, 'PAT_IO_INVALID_INSTALLATION'):
            IoSequencePolicy(wrong)

    def test_multiple_roles_and_mixed_actions_are_not_eligible(self):
        value = program(count=2)
        value['roles']['other'] = copy.deepcopy(value['roles']['io'])
        value['steps'][1]['role'] = 'other'
        self.refuses(value, 'PAT_IO_UNSUPPORTED_PROGRAM')
        value = program(count=2)
        value['roles']['io']['actions'].append('pwm_burst')
        value['steps'][1]['actionId'] = 'pwm_burst'
        value['steps'][1]['arguments'] = {'durationMs': {'parameter': 'duration'},
            'frequencyHz': {'literal': 1000}, 'dutyPermille': {'literal': 500}, 'resolutionBits': {'literal': 8}}
        self.refuses(value, 'PAT_IO_UNSUPPORTED_PROGRAM')

    def test_sixteen_ordered_steps_fit_and_seventeen_refuse(self):
        value = program(count=16)
        self.assertEqual(len(self.qualify(value)['schedule']['steps']), 16)
        with self.assertRaises(PatError):
            self.qualify(program(count=17))

    def test_empty_applicability_and_enum_hole_selection_refuse(self):
        value = program(); value['parameters']['duration'] = parameter(1, 100, 'ms', [1, 100])
        value['applicability']['all'].append({'field': 'parameters.duration', 'op': 'equals', 'literal': 50})
        self.refuses(value, 'PAT_INVALID_PREDICATE')
        value['applicability']['all'][-1] = {'field': 'parameters.duration', 'op': 'range', 'minimum': 50, 'maximum': 50}
        self.refuses(value, 'PAT_IO_EMPTY_APPLICABILITY')

    def test_matrix_sparse_boundaries_holes_and_applicability_remain_distinct(self):
        value = program(); value['parameters']['duration'] = parameter(1, 100, 'ms', [1, 20, 100])
        value['applicability']['all'].append({'field': 'parameters.duration', 'op': 'range', 'minimum': 20, 'maximum': 100})
        matrix = self.policy.generate_cases(value, self.gpio)
        positives = [decode_case_input(c['input'])['parameters']['duration'] for c in matrix['cases'] if c['expected']['staticOutcome'] == 'applicable']
        self.assertEqual(set(positives), {20, 100})
        by_coverage = {label: case for case in matrix['cases'] for label in case['coverage']}
        self.assertEqual(by_coverage['enum_hole:duration']['expected']['errorCode'], 'PAT_PARAMETER_OUT_OF_DOMAIN')
        self.assertEqual(by_coverage['outside_applicability:duration']['expected']['staticOutcome'], 'not_applicable')
        self.assertFalse(matrix['coverage']['faultTrialsIncluded'])
        self.assertTrue(matrix['coverage']['requiresCombinedFaultBudgetCheck'])

    def test_matrix_tags_preserve_boolean_and_integral_number_negatives(self):
        matrix = self.policy.generate_cases(program(), self.gpio)
        cases = {label: case for case in matrix['cases'] for label in case['coverage']}
        self.assertIs(type(decode_case_input(cases['boolean_type:duration']['input'])['parameters']['duration']), bool)
        self.assertIs(type(decode_case_input(cases['integral_number_type:duration']['input'])['parameters']['duration']), float)
        self.assertNotEqual(cases['boolean_type:duration']['caseId'], cases['integral_number_type:duration']['caseId'])

    def test_every_static_case_agrees_with_actual_compiler(self):
        for pwm in [False, True]:
            value = program(pwm=pwm, count=2); chosen = self.pwm if pwm else self.gpio
            matrix = self.policy.generate_cases(value, chosen)
            for case in matrix['cases']:
                data = decode_case_input(case['input']); expected = case['expected']
                options = dict(origin_ms=1000, caller_deadline_ms=11000, replay_namespace='replay:matrix',
                    procedure_key='parent:matrix', operation_keys={'step:0': 'child:zero', 'step:1': 'child:one'},
                    context={key: data[key] for key in ('taskKind', 'inputProfile', 'evidenceMode')} | {'deployment': 'simulation:io-hub'})
                if expected['staticOutcome'] == 'applicable':
                    plan = compile_pat(value, data['parameters'], {'io': chosen}, **options)
                    self.assertEqual([s['request']['intent']['arguments'] for s in plan['request']['procedure']['steps']], expected['arguments'])
                else:
                    with self.assertRaises(PatError) as caught:
                        compile_pat(value, data['parameters'], {'io': chosen}, **options)
                    self.assertEqual(caught.exception.code, 'PAT_NOT_APPLICABLE' if expected['staticOutcome'] == 'not_applicable' else expected['errorCode'])

    def test_two_axis_matrix_includes_all_cartesian_boundaries(self):
        value = program(pwm=True)
        value['parameters']['frequency'] = parameter(100, 10000, 'Hz')
        value['steps'][0]['arguments']['frequencyHz'] = {'parameter': 'frequency'}
        matrix = self.policy.generate_cases(value, self.pwm)
        points = {(data['parameters']['duration'], data['parameters']['frequency'])
                  for case in matrix['cases'] if case['expected']['staticOutcome'] == 'applicable'
                  for data in [decode_case_input(case['input'])]}
        self.assertEqual(points, set(itertools.product([1, 50, 100], [100, 5050, 10000])))

    def test_constant_program_has_one_positive_boundary_and_typed_negatives(self):
        matrix = self.policy.generate_cases(program(literal=True), self.gpio)
        positives = [c for c in matrix['cases'] if c['expected']['staticOutcome'] == 'applicable']
        self.assertEqual(len(positives), 1)
        self.assertEqual(positives[0]['categories'], ['boundary', 'positive'])
        self.assertEqual(matrix['plannedChildOperations'], 1)

    def test_case_and_effect_limits_refuse_without_partial_plan(self):
        for limits, code in [({'maxCases': 1, 'maxChildOperations': 512}, 'PAT_IO_CASE_LIMIT'),
                             ({'maxCases': 32, 'maxChildOperations': 1}, 'PAT_IO_EFFECT_LIMIT')]:
            with self.assertRaisesRegex(PatError, code):
                self.policy.generate_cases(program(), self.gpio, limits=limits)
        for limits in [{'maxCases': 33, 'maxChildOperations': 512}, {'maxCases': True, 'maxChildOperations': 512}, {}]:
            with self.assertRaises(PatError):
                self.policy.generate_cases(program(), self.gpio, limits=limits)

    def test_reordered_inputs_are_deterministic_and_outputs_are_detached(self):
        value = program(); chosen = copy.deepcopy(self.gpio)
        original = canonical(value), canonical(chosen)
        first = self.policy.generate_cases(value, chosen)
        digest = self.policy.matrix_digest(value, chosen)
        self.assertEqual(digest, self.policy.matrix_digest(dict(reversed(list(value.items()))), chosen))
        first['contract']['declaredDomains']['duration']['maximum'] = 1
        first['cases'].clear()
        self.assertEqual(digest, self.policy.matrix_digest(value, chosen))
        self.assertEqual((canonical(value), canonical(chosen)), original)

    def test_planning_after_setup_uses_no_files_clock_database_or_provider(self):
        value = program(); chosen = copy.deepcopy(self.gpio)
        with ExitStack() as stack:
            for target in ['pathlib.Path.read_text', 'pathlib.Path.read_bytes', 'builtins.open',
                           'sqlite3.connect', 'time.time', 'time.monotonic',
                           'hms.synthetic_io_runtime.IoRuntime.__init__', 'hms.synthetic_io_board.SyntheticIoBoard.begin',
                           'hms.synthetic_io_board.SyntheticIoBoard.finish', 'hms.synthetic_io_adapter.IoRouteAdapter.tick']:
                stack.enter_context(patch(target, side_effect=AssertionError('impure planning call')))
            self.assertEqual(self.qualify(value, chosen=chosen)['primitive'], 'gpio_pulse')
            matrix = self.policy.generate_cases(value, chosen)
            self.assertGreater(len(matrix['cases']), 1)
            self.assertTrue(self.policy.matrix_digest(value, chosen).startswith('sha256:'))
