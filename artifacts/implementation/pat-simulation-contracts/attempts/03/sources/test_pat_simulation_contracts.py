"""Original pure staged tests. Never instantiate Runtime or execute a worker."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hms.contracts import canonical, SAFE_INTEGER
from hms.pat_contracts import PatError, matches_static, pat_digest, validate_parameters
from pat_simulation_contracts import (CEILINGS, CONFIG_PROFILE, FAN_METADATA, POLICY,
    config_digest, decode_case_input, generate_cases, matrix_digest,
    parse_service_config, qualification_registration, qualify_fan_contract)

HERE = Path(__file__).resolve().parent
ARTIFACT = json.loads((HERE / 'fixtures/fan-artifact.json').read_text())
DESCRIPTOR = json.loads((HERE / 'fixtures/fan-descriptor.json').read_text())


def configuration():
    return {'profile': CONFIG_PROFILE, 'policy': POLICY, 'limits': dict(CEILINGS),
        'registrations': [{'instanceId': 'sim:home-fan', 'driverProfile': 'sqlite-simulation',
            'typeDigest': DESCRIPTOR['binding']['typeDigest'],
            'installationDigest': DESCRIPTOR['installationDigest'], 'argumentMetadata': copy.deepcopy(FAN_METADATA)}],
        'qualifications': [{'artifactDigest': pat_digest(ARTIFACT), 'roleInstances': {'fan': 'sim:home-fan'}}]}


def check_matrix(test, artifact, matrix):
    test.assertFalse(matrix['qualificationPassed'])
    test.assertFalse(matrix['coverage']['exhaustiveBehavior'])
    test.assertFalse(matrix['coverage']['faultTrialsIncluded'])
    ids = [case['caseId'] for case in matrix['cases']]
    test.assertEqual(len(ids), len(set(ids)))
    for case in matrix['cases']:
        data = decode_case_input(case['input'])
        expected = case['expected']
        try:
            result = matches_static(artifact, data['parameters'], task_kind=data['taskKind'],
                input_profile=data['inputProfile'], evidence_mode=data['evidenceMode'])
        except PatError as error:
            test.assertEqual(expected['staticOutcome'], 'refused', case)
            test.assertEqual(error.code, expected['errorCode'], case)
        else:
            test.assertEqual(expected['staticOutcome'], 'applicable' if result else 'not_applicable', case)
            test.assertIsNone(expected['errorCode'])
        if expected['staticOutcome'] == 'applicable':
            validate_parameters(artifact, data['parameters'])
            levels = [data['parameters'][step['arguments']['level']['parameter']]
                if 'parameter' in step['arguments']['level'] else step['arguments']['level']['literal']
                for step in artifact['steps']]
            test.assertEqual(expected['levels'], levels)
            test.assertEqual(expected['finalLevel'], levels[-1])
            test.assertEqual(expected['plannedChildOperations'], len(artifact['steps']))
        else:
            test.assertEqual(expected['plannedChildOperations'], 0)


class ServiceConfigTests(unittest.TestCase):
    def test_closed_config_detaches_and_resolves_explicit_map_only(self):
        value = configuration(); parsed = parse_service_config(value)
        selected = qualification_registration(parsed, ARTIFACT)
        self.assertEqual(selected['instanceId'], 'sim:home-fan')
        value['registrations'][0]['argumentMetadata']['set_level']['level']['unit'] = 'volts'
        self.assertEqual(parsed['registrations'][0]['argumentMetadata'], FAN_METADATA)
        selected['instanceId'] = 'changed'
        self.assertEqual(qualification_registration(parsed, ARTIFACT)['instanceId'], 'sim:home-fan')
        changed = copy.deepcopy(ARTIFACT); changed['name'] += '-different'
        with self.assertRaises(PatError) as caught:
            qualification_registration(parsed, changed)
        self.assertEqual(caught.exception.code, 'PAT_SIM_QUALIFICATION_NOT_CONFIGURED')

    def test_order_independent_config_identity_and_lowered_limits(self):
        first = configuration(); other = copy.deepcopy(first['registrations'][0]); other['instanceId'] = 'sim:west'
        first['registrations'].append(other)
        first['qualifications'].append({'artifactDigest': 'sha256:' + 'c' * 64, 'roleInstances': {'fan': 'sim:west'}})
        second = copy.deepcopy(first)
        second['registrations'].reverse(); second['qualifications'].reverse()
        self.assertEqual(config_digest(first), config_digest(second))
        second['limits']['maxCases'] -= 1
        self.assertNotEqual(config_digest(first), config_digest(second))

    def test_no_import_command_url_result_or_supplied_code_attestation(self):
        for field, value in [('import', 'outside.module'), ('command', ['sh']), ('url', 'https://example.invalid'),
                             ('passed', True), ('result', {}), ('driverDigest', 'sha256:' + 'd' * 64)]:
            for where in ('root', 'registration'):
                with self.subTest(field=field, where=where):
                    config = configuration(); target = config if where == 'root' else config['registrations'][0]
                    target[field] = value
                    with self.assertRaises(PatError): parse_service_config(config)

    def test_unknown_drivers_metadata_and_maps_refuse(self):
        changes = [lambda x: x.update(policy='untrusted'),
            lambda x: x['registrations'][0].update(driverProfile='compact-simulation'),
            lambda x: x['registrations'][0]['argumentMetadata']['set_level']['level'].update(unit='volts'),
            lambda x: x['qualifications'][0]['roleInstances'].update(fan='unregistered'),
            lambda x: x['qualifications'][0]['roleInstances'].update(other='sim:home-fan'),
            lambda x: x['registrations'].append(copy.deepcopy(x['registrations'][0])),
            lambda x: x['qualifications'].append(copy.deepcopy(x['qualifications'][0]))]
        for change in changes:
            with self.subTest(change=change):
                value = configuration(); change(value)
                with self.assertRaises(PatError): parse_service_config(value)
        value = configuration(); value['qualifications'][0]['roleInstances'] = {'different': 'sim:home-fan'}
        with self.assertRaises(PatError) as caught: qualification_registration(value, ARTIFACT)
        self.assertEqual(caught.exception.code, 'PAT_SIM_INVALID_ROLE_MAP')

    def test_numeric_types_and_all_limits_fail_closed(self):
        for key, ceiling in CEILINGS.items():
            for wrong in (True, 1.0, 0, -1, ceiling + 1, None, [], {}):
                with self.subTest(key=key, wrong=wrong):
                    value = configuration(); value['limits'][key] = wrong
                    with self.assertRaises(PatError): parse_service_config(value)
        value = canonical(configuration()).replace(b'"maxCases":32', b'"maxCases":32.0')
        with self.assertRaises(PatError): parse_service_config(value)

    def test_malformed_json_fields_are_structured_refusals(self):
        paths = [('profile',), ('policy',), ('limits',), ('registrations',), ('qualifications',),
            ('registrations',0,'instanceId'), ('registrations',0,'typeDigest'),
            ('registrations',0,'argumentMetadata'), ('qualifications',0,'roleInstances')]
        for path in paths:
            for wrong in (None, [], {}, True, 1.0):
                with self.subTest(path=path, wrong=wrong):
                    value = configuration(); target = value
                    for key in path[:-1]: target = target[key]
                    target[path[-1]] = wrong
                    with self.assertRaises(PatError): parse_service_config(value)
        with self.assertRaises(PatError): parse_service_config(b'{"profile":1,"profile":2}')
        with self.assertRaises(PatError): parse_service_config({'x':'a' * 65536})


class FanPolicyTests(unittest.TestCase):
    def test_two_axis_matrix_is_deterministic_and_independently_checks_every_case(self):
        source = copy.deepcopy(ARTIFACT); descriptor = copy.deepcopy(DESCRIPTOR)
        matrix = generate_cases(source, descriptor)
        check_matrix(self, source, matrix)
        applicable = [decode_case_input(case['input'])['parameters'] for case in matrix['cases']
                      if case['expected']['staticOutcome'] == 'applicable']
        self.assertEqual(len(applicable), 9)
        self.assertEqual({tuple(row[key] for key in ('initialLevel','finalLevel')) for row in applicable},
                         {(left,right) for left in (0,50,100) for right in (0,50,100)})
        self.assertEqual(matrix['plannedChildOperations'], 18)
        self.assertEqual(len(matrix['cases']), 22)
        first = matrix_digest(source, descriptor)
        source['parameters'] = dict(reversed(list(source['parameters'].items())))
        self.assertEqual(matrix_digest(source, descriptor), first)
        self.assertEqual(ARTIFACT, source)
        self.assertEqual(DESCRIPTOR, descriptor)
        matrix['cases'].clear()
        self.assertEqual(len(generate_cases(source, descriptor)['cases']), 22)

    def test_static_ranges_and_equalities_intersect_exactly(self):
        value = copy.deepcopy(ARTIFACT)
        value['applicability']['all'] += [
            {'field':'parameters.initialLevel','op':'range','minimum':20,'maximum':80},
            {'field':'parameters.initialLevel','op':'range','minimum':40,'maximum':90},
            {'field':'parameters.finalLevel','op':'equals','literal':73}]
        contract = qualify_fan_contract(value, DESCRIPTOR)
        self.assertEqual(contract['applicableDomains']['initialLevel'], {'type':'integer','minimum':40,'maximum':80})
        self.assertEqual(contract['nominalParameters'], {'finalLevel':73,'initialLevel':60})
        self.assertEqual(contract['declaredDomains']['initialLevel']['minimum'], 0)
        matrix = generate_cases(value, DESCRIPTOR)
        check_matrix(self, value, matrix)
        self.assertEqual(sum(case['expected']['staticOutcome']=='applicable' for case in matrix['cases']), 3)
        self.assertTrue(any(case['expected']['staticOutcome']=='not_applicable' and
            'outside_applicability:initialLevel' in case['coverage'] for case in matrix['cases']))
        self.assertEqual({decode_case_input(case['input'])['parameters']['initialLevel']
            for case in matrix['cases'] if 'outside_applicability:initialLevel' in case['coverage']}, {39,81})
        self.assertEqual({decode_case_input(case['input'])['parameters']['finalLevel']
            for case in matrix['cases'] if 'outside_applicability:finalLevel' in case['coverage']}, {72,74})

    def test_enum_holes_intersection_and_sparse_safe_integer_extremes_are_bounded(self):
        value = copy.deepcopy(ARTIFACT)
        value['parameters']['initialLevel']['valueSchema'] = {'type':'integer','minimum':-SAFE_INTEGER,
            'maximum':SAFE_INTEGER,'enum':[100,0,50]}
        value['applicability']['all'].append({'field':'parameters.initialLevel','op':'range','minimum':10,'maximum':80})
        matrix = generate_cases(value, DESCRIPTOR)
        self.assertEqual(matrix['applicableDomains']['initialLevel']['enum'], [50])
        check_matrix(self, value, matrix)
        self.assertTrue(any('enum_hole:initialLevel' in case['coverage'] for case in matrix['cases']))
        self.assertLessEqual(len(matrix['cases']), 32)

    def test_empty_parameter_and_context_intersections_refuse(self):
        for predicates in ([{'field':'parameters.initialLevel','op':'equals','literal':10},
                            {'field':'parameters.initialLevel','op':'equals','literal':20}],
                           [{'field':'trigger.taskKind','op':'equals','literal':'other'}],
                           [{'field':'context.evidenceMode','op':'equals','literal':'physical'}]):
            with self.subTest(predicates=predicates):
                value = copy.deepcopy(ARTIFACT); value['applicability']['all'] += predicates
                with self.assertRaises(PatError) as caught: generate_cases(value, DESCRIPTOR)
                self.assertEqual(caught.exception.code, 'PAT_SIM_EMPTY_APPLICABILITY')
        value = copy.deepcopy(ARTIFACT)
        value['parameters']['initialLevel']['valueSchema']['enum'] = [0,100]
        value['applicability']['all'].append({'field':'parameters.initialLevel','op':'range','minimum':10,'maximum':90})
        with self.assertRaises(PatError) as caught: generate_cases(value, DESCRIPTOR)
        self.assertEqual(caught.exception.code, 'PAT_SIM_EMPTY_APPLICABILITY')

    def test_applicability_cannot_repair_overbroad_whole_declared_domain(self):
        value = copy.deepcopy(ARTIFACT)
        value['parameters']['initialLevel']['valueSchema']['maximum'] = 101
        value['applicability']['all'].append({'field':'parameters.initialLevel','op':'range','minimum':0,'maximum':100})
        with self.assertRaises(PatError) as caught: generate_cases(value, DESCRIPTOR)
        self.assertEqual(caught.exception.code, 'PAT_ARGUMENT_DOMAIN')
        descriptor = copy.deepcopy(DESCRIPTOR)
        descriptor['binding']['argumentSchemas']['set_level']['properties']['level']['maximum'] = 50
        with self.assertRaises(PatError) as caught: qualify_fan_contract(ARTIFACT, descriptor)
        self.assertEqual(caught.exception.code, 'PAT_ARGUMENT_DOMAIN')

    def test_integral_float_negative_survives_canonical_round_trip(self):
        matrix = json.loads(canonical(generate_cases(ARTIFACT, DESCRIPTOR)))
        for case in matrix['cases']:
            if 'integral_number_type:initialLevel' in case['coverage']:
                raw = decode_case_input(case['input'])
                self.assertIs(type(raw['parameters']['initialLevel']), float)
                self.assertEqual(case['expected']['errorCode'], 'PAT_PARAMETER_OUT_OF_DOMAIN')
                with self.assertRaises(PatError): validate_parameters(ARTIFACT, raw['parameters'])
                break
        else: self.fail('typed integral-float negative omitted')
        check_matrix(self, ARTIFACT, matrix)

    def test_fixed_and_zero_parameter_programs_deduplicate_degenerate_domain_coverage(self):
        fixed = copy.deepcopy(ARTIFACT)
        for declaration in fixed['parameters'].values(): declaration['valueSchema'].update(minimum=25, maximum=25)
        matrix = generate_cases(fixed, DESCRIPTOR); check_matrix(self, fixed, matrix)
        positive = [case for case in matrix['cases'] if case['expected']['staticOutcome']=='applicable']
        self.assertEqual(len(positive), 1)
        self.assertEqual(positive[0]['categories'], ['boundary','positive'])
        value = copy.deepcopy(ARTIFACT); value['parameters'] = {}
        for step in value['steps']: step['arguments']['level'] = {'literal':25}
        matrix = generate_cases(value, DESCRIPTOR); check_matrix(self, value, matrix)
        self.assertEqual(len(matrix['cases']), 5)
        self.assertEqual(matrix['cases'][0]['categories'], ['boundary','positive'])
        self.assertIn('constant_domain', matrix['cases'][0]['coverage'])

    def test_case_and_effect_caps_refuse_instead_of_truncating(self):
        for key, maximum, code in [('maxCases',21,'PAT_SIM_CASE_LIMIT'),
                                   ('maxChildOperations',17,'PAT_SIM_EFFECT_LIMIT')]:
            limits = dict(CEILINGS); limits[key] = maximum
            with self.assertRaises(PatError) as caught: generate_cases(ARTIFACT, DESCRIPTOR, limits=limits)
            self.assertEqual(caught.exception.code, code)
        exact = dict(CEILINGS, maxCases=22, maxChildOperations=18)
        self.assertEqual(len(generate_cases(ARTIFACT, DESCRIPTOR, limits=exact)['cases']), 22)

    def test_one_and_sixteen_steps_are_supported_but_seventeen_refuses(self):
        for count in (1, 16, 17):
            with self.subTest(count=count):
                value = copy.deepcopy(ARTIFACT)
                value['parameters'] = {}
                value['steps'] = []
                for index in range(count):
                    step = copy.deepcopy(ARTIFACT['steps'][0])
                    step['stepId'] = 'level:' + str(index)
                    step['arguments']['level'] = {'literal': index}
                    step['timing'].update(latestStartOffsetMs=(index+1)*500,
                                          latestCompletionOffsetMs=(index+2)*500)
                    value['steps'].append(step)
                value['timingBudget'].update(maxRunSumMs=count*500, latestCompletionOffsetMs=(count+1)*500)
                value['effectBudget']['maxInvocations'] = count
                value['outcomeContract']['requiredCompletedSteps'] = [step['stepId'] for step in value['steps']]
                if count == 17:
                    with self.assertRaises(PatError): generate_cases(value, DESCRIPTOR)
                else:
                    matrix = generate_cases(value, DESCRIPTOR)
                    check_matrix(self, value, matrix)
                    self.assertEqual(matrix['plannedChildOperations'], count)
                    self.assertEqual(matrix['cases'][0]['expected']['levels'], list(range(count)))

    def test_policy_rejects_third_varying_axis_and_unsupported_parameters(self):
        value = copy.deepcopy(ARTIFACT)
        value['parameters']['third'] = copy.deepcopy(value['parameters']['initialLevel'])
        step = copy.deepcopy(value['steps'][0]); step['stepId']='third'; step['arguments']['level']={'parameter':'third'}
        value['steps'].append(step); value['outcomeContract']['requiredCompletedSteps'].append('third')
        value['effectBudget']['maxInvocations']=3; value['timingBudget']['maxRunSumMs']=1500
        with self.assertRaises(PatError) as caught: generate_cases(value, DESCRIPTOR)
        self.assertEqual(caught.exception.code, 'PAT_SIM_PARAMETER_AXIS_LIMIT')
        for change in ({'unit':'volts'}, {'frame':'frame:other'}):
            value = copy.deepcopy(ARTIFACT); value['parameters']['initialLevel'].update(change)
            with self.assertRaises(PatError): generate_cases(value, DESCRIPTOR)
        value = copy.deepcopy(ARTIFACT)
        value['parameters']['initialLevel']={'valueSchema':{'type':'boolean'},'unit':None,'frame':None}
        with self.assertRaises(PatError): generate_cases(value, DESCRIPTOR)

    def test_policy_refuses_other_driver_action_role_and_dynamic_guards(self):
        descriptor = copy.deepcopy(DESCRIPTOR); descriptor['driverProfile']='compact-simulation'
        with self.assertRaises(PatError): generate_cases(ARTIFACT, descriptor)
        for change in (lambda x: x.update(runtimeGuardProfile='dynamic'),
            lambda x: x['roles']['fan'].update(capabilityFamily='sim:microscope'),
            lambda x: x['steps'][0]['arguments'].update(unit={'literal':'volts'}),
            lambda x: x['steps'][0].update(branch='anything')):
            value = copy.deepcopy(ARTIFACT); change(value)
            with self.assertRaises(PatError): generate_cases(value, DESCRIPTOR)
        for wrong in (None, [], 1, 1.0, 'descriptor', {}):
            with self.subTest(wrong=wrong):
                with self.assertRaises(PatError): generate_cases(ARTIFACT, wrong)

    def test_pure_calls_do_not_open_database_process_network_clock_or_files(self):
        config = configuration()
        with ExitStack() as patches:
            for target in ('builtins.open','pathlib.Path.open','sqlite3.connect','subprocess.Popen',
                           'socket.socket','time.time','time.monotonic'):
                patches.enter_context(patch(target, side_effect=AssertionError('unexpected effect: '+target)))
            parse_service_config(config)
            qualify_fan_contract(ARTIFACT, DESCRIPTOR)
            matrix = generate_cases(ARTIFACT, DESCRIPTOR)
            self.assertEqual(len(matrix['cases']),22)

    def test_case_decoder_rejects_malformed_or_ambiguous_typed_values(self):
        case = generate_cases(ARTIFACT, DESCRIPTOR)['cases'][0]['input']
        for bad in ({'type':'integer','value':1.0}, {'type':'integer','value':True},
                    {'type':'number','value':True}, {'type':{},'value':1},
                    {'type':'object','value':{}}, {'type':'integer','value':1,'extra':1}):
            value = copy.deepcopy(case); value['parameters']['initialLevel']=bad
            with self.subTest(bad=bad):
                with self.assertRaises(PatError): decode_case_input(value)


if __name__ == '__main__':
    unittest.main()
