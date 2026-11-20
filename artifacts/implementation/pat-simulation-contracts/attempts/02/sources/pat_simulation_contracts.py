"""STAGED pure fan qualification contracts; no worker, Runtime or promotion.

Descriptors are explicit trusted snapshots, not attested by this module. The
source-identity, installed-registration join, execution and evidence lifecycle
remain separate required implementation work. Case generation is finite trial
planning, not exhaustive behavioral qualification or an authorization decision.
"""
from __future__ import annotations

import copy
from functools import wraps
import hashlib
import itertools
import re

from hms.contracts import ContractError, SAFE_INTEGER, canonical
from hms.pat_contracts import (PatError, accepts, closed, equal, integer,
    matches_static, name, parse_pat, pat_digest, require, snapshot)
from hms.pat_compiler import _binding, _domain_subset, _fits

POLICY = 'hms.pat.eval.sqlite-fan-sequence/0.1'
CONFIG_PROFILE = 'hms.pat.simulation-services/0.1'
MATRIX_PROFILE = 'hms.pat.fan-domain-matrix/0.1'
CEILINGS = {'maxCases': 32, 'maxChildOperations': 512, 'maxSchedulerTicks': 2048,
            'maxOutputBytes': 16 * 1024 * 1024, 'workerDeadlineMs': 60000}
FAN_METADATA = {'set_level': {
    'level': {'unit': 'percent', 'frame': None, 'unitArgument': 'unit', 'frameArgument': None},
    'unit': {'unit': None, 'frame': None, 'unitArgument': None, 'frameArgument': None}}}


def _errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ContractError, TypeError, ValueError, KeyError, RecursionError) as error:
            raise PatError('PAT_SIM_INVALID_CONTRACT') from error
    return checked


def _digest(value, code='PAT_SIM_INVALID_CONFIG'):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None, code)


def _hash(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _limits(value):
    value = snapshot(value, 'PAT_SIM_INVALID_LIMITS')
    closed(value, CEILINGS, 'PAT_SIM_INVALID_LIMITS')
    for key, maximum in CEILINGS.items():
        integer(value[key], 1, maximum, 'PAT_SIM_INVALID_LIMITS')
    return value


@_errors
def parse_service_config(value):
    """Closed trusted setup data. This does not install or attest any code."""
    value = snapshot(value, 'PAT_SIM_INVALID_CONFIG')
    closed(value, {'profile', 'policy', 'limits', 'registrations', 'qualifications'}, 'PAT_SIM_INVALID_CONFIG')
    require(value['profile'] == CONFIG_PROFILE and value['policy'] == POLICY, 'PAT_SIM_UNSUPPORTED_POLICY')
    value['limits'] = _limits(value['limits'])
    registrations, qualifications = value['registrations'], value['qualifications']
    require(type(registrations) is list and 1 <= len(registrations) <= 128, 'PAT_SIM_INVALID_CONFIG')
    require(type(qualifications) is list and 1 <= len(qualifications) <= 128, 'PAT_SIM_INVALID_CONFIG')
    instances = set()
    for record in registrations:
        closed(record, {'instanceId', 'driverProfile', 'typeDigest', 'installationDigest', 'argumentMetadata'},
               'PAT_SIM_INVALID_CONFIG')
        name(record['instanceId'], 'PAT_SIM_INVALID_CONFIG')
        require(record['instanceId'] not in instances, 'PAT_SIM_DUPLICATE_REGISTRATION')
        instances.add(record['instanceId'])
        require(record['driverProfile'] == 'sqlite-simulation', 'PAT_SIM_UNSUPPORTED_DRIVER')
        _digest(record['typeDigest']); _digest(record['installationDigest'])
        require(record['argumentMetadata'] == FAN_METADATA, 'PAT_SIM_UNSUPPORTED_SEMANTICS')
    artifacts = set()
    for assignment in qualifications:
        closed(assignment, {'artifactDigest', 'roleInstances'}, 'PAT_SIM_INVALID_CONFIG')
        _digest(assignment['artifactDigest'])
        require(assignment['artifactDigest'] not in artifacts, 'PAT_SIM_DUPLICATE_QUALIFICATION')
        artifacts.add(assignment['artifactDigest'])
        roles = assignment['roleInstances']
        require(type(roles) is dict and len(roles) == 1, 'PAT_SIM_INVALID_ROLE_MAP')
        for role, instance in roles.items():
            name(role, 'PAT_SIM_INVALID_ROLE_MAP'); name(instance, 'PAT_SIM_INVALID_ROLE_MAP')
            require(instance in instances, 'PAT_SIM_UNREGISTERED_INSTANCE')
    # These arrays describe sets. Canonical ordering makes configuration replay
    # insensitive to registration/map insertion order without altering artifacts.
    value['registrations'] = sorted(registrations, key=lambda row: row['instanceId'])
    value['qualifications'] = sorted(qualifications, key=lambda row: row['artifactDigest'])
    canonical(value)
    return value


@_errors
def config_digest(value):
    return _hash(b'HMS-PAT-SIMULATION-CONFIG-v0.1', parse_service_config(value))


@_errors
def qualification_registration(config, artifact):
    """Resolve only an explicit setup map; never route a caller's PAT run."""
    config, artifact = parse_service_config(config), parse_pat(artifact)
    digest = pat_digest(artifact)
    entry = next((row for row in config['qualifications'] if row['artifactDigest'] == digest), None)
    require(entry is not None, 'PAT_SIM_QUALIFICATION_NOT_CONFIGURED')
    require(set(entry['roleInstances']) == set(artifact['roles']), 'PAT_SIM_INVALID_ROLE_MAP')
    instance, = entry['roleInstances'].values()
    return copy.deepcopy(next(row for row in config['registrations'] if row['instanceId'] == instance))


def _values(domain):
    return domain.get('enum', range(domain['minimum'], domain['maximum'] + 1))


def _size(domain):
    return len(domain['enum']) if 'enum' in domain else domain['maximum'] - domain['minimum'] + 1


def _nominal(domain):
    return domain['enum'][len(domain['enum']) // 2] if 'enum' in domain else (domain['minimum'] + domain['maximum']) // 2


@_errors
def qualify_fan_contract(value, trusted_descriptor):
    """Static compatibility and applicability only; emits no operation keys.

    Reuse the compiler's exact binding and whole-declared-domain validators.
    Narrow applicability never repairs an overbroad declared parameter domain.
    At most two DECLARED integer domains may have more than one accepted value;
    additional singleton integer parameters still consume case/effect bounds.
    """
    artifact = parse_pat(value)
    descriptor = snapshot(trusted_descriptor, 'PAT_SIM_INVALID_DESCRIPTOR')
    require(len(artifact['roles']) == 1, 'PAT_SIM_UNSUPPORTED_PROGRAM')
    role, = artifact['roles']
    requirement = artifact['roles'][role]
    require(requirement['capabilityFamily'] == 'sim:home-fan' and requirement['actions'] == ['set_level'],
            'PAT_SIM_UNSUPPORTED_PROGRAM')
    require(type(descriptor) is dict and descriptor.get('driverProfile') == 'sqlite-simulation', 'PAT_SIM_UNSUPPORTED_DRIVER')
    _binding(descriptor, requirement)
    require(descriptor['argumentMetadata'] == FAN_METADATA, 'PAT_SIM_UNSUPPORTED_SEMANTICS')
    declared = {}
    for parameter in sorted(artifact['parameters']):
        declaration = artifact['parameters'][parameter]
        require(declaration['valueSchema']['type'] == 'integer' and declaration['unit'] == 'percent' and
                declaration['frame'] is None, 'PAT_SIM_UNSUPPORTED_PARAMETER')
        domain = copy.deepcopy(declaration['valueSchema'])
        if 'enum' in domain:
            domain['enum'].sort()
        _domain_subset(domain, {'type': 'integer', 'minimum': 0, 'maximum': 100})
        declared[parameter] = domain
    require(sum(_size(domain) > 1 for domain in declared.values()) <= 2, 'PAT_SIM_PARAMETER_AXIS_LIMIT')
    action = descriptor['type']['execution']['actions']['set_level']
    schemas = (action['inputSchema'], descriptor['binding']['argumentSchemas']['set_level'])
    for step in artifact['steps']:
        require(step['role'] == role and step['actionId'] == 'set_level' and
                set(step['arguments']) == {'level', 'unit'} and
                step['arguments']['unit'] == {'literal': 'percent'}, 'PAT_SIM_UNSUPPORTED_PROGRAM')
        require(step['timing']['maxRunMs'] <= action['maxRunMs'], 'PAT_TIME_BOUNDS')
        expression = step['arguments']['level']
        for schema in schemas:
            require(set(schema['required']) <= {'level', 'unit'} <= set(schema['properties']), 'PAT_ARGUMENT_DOMAIN')
            require(_fits(schema['properties']['unit'], 'percent'), 'PAT_ARGUMENT_DOMAIN')
            if 'parameter' in expression:
                _domain_subset(declared[expression['parameter']], schema['properties']['level'])
            else:
                require(type(expression['literal']) is int and 0 <= expression['literal'] <= 100 and
                        _fits(schema['properties']['level'], expression['literal']),
                        'PAT_ARGUMENT_DOMAIN')
    applicable = copy.deepcopy(declared)
    context = {'trigger.taskKind': artifact['taskKind'], 'trigger.inputProfile': artifact['inputProfile'],
               'context.evidenceMode': 'simulation'}
    for predicate in artifact['applicability']['all']:
        if not predicate['field'].startswith('parameters.'):
            require(equal(predicate['literal'], context[predicate['field']]), 'PAT_SIM_EMPTY_APPLICABILITY')
            continue
        parameter = predicate['field'][len('parameters.'):]
        domain = applicable[parameter]
        low, high = ((predicate['literal'], predicate['literal']) if predicate['op'] == 'equals'
                     else (predicate['minimum'], predicate['maximum']))
        domain['minimum'], domain['maximum'] = max(domain['minimum'], low), min(domain['maximum'], high)
    for domain in applicable.values():
        require(domain['minimum'] <= domain['maximum'], 'PAT_SIM_EMPTY_APPLICABILITY')
        if 'enum' in domain:
            domain['enum'] = [value for value in domain['enum'] if domain['minimum'] <= value <= domain['maximum']]
            require(bool(domain['enum']), 'PAT_SIM_EMPTY_APPLICABILITY')
            domain['minimum'], domain['maximum'] = domain['enum'][0], domain['enum'][-1]
    nominal = {key: _nominal(domain) for key, domain in applicable.items()}
    require(matches_static(artifact, nominal, task_kind=artifact['taskKind'], input_profile=artifact['inputProfile'],
                           evidence_mode='simulation'), 'PAT_SIM_EMPTY_APPLICABILITY')
    return {'profile': 'hms.pat.fan-static-contract/0.1', 'policy': POLICY,
            'artifactDigest': pat_digest(artifact), 'role': role,
            'declaredDomains': declared, 'applicableDomains': applicable, 'nominalParameters': nominal,
            'descriptorDigest': _hash(b'HMS-PAT-SIM-TRUSTED-DESCRIPTOR-v0.1', descriptor),
            'qualificationPassed': False}


def _tag(value):
    kind = {int: 'integer', float: 'number', bool: 'boolean', str: 'string', type(None): 'null'}[type(value)]
    # An explicit number tag preserves an integral-float negative through JCS,
    # which otherwise serializes 1.0 identically to an accepted integer 1.
    return {'type': kind, 'value': int(value) if type(value) is float and value.is_integer() else value}


@_errors
def decode_case_input(value):
    """Decode typed test inputs; this function does not execute their request."""
    value = snapshot(value, 'PAT_SIM_INVALID_CASE')
    closed(value, {'parameters', 'taskKind', 'inputProfile', 'evidenceMode'}, 'PAT_SIM_INVALID_CASE')
    require(type(value['parameters']) is dict and len(value['parameters']) <= 33, 'PAT_SIM_INVALID_CASE')
    for key in ('taskKind', 'inputProfile', 'evidenceMode'):
        name(value[key], 'PAT_SIM_INVALID_CASE')
    result = copy.deepcopy(value)
    result['parameters'] = {}
    for parameter, tagged in value['parameters'].items():
        name(parameter, 'PAT_SIM_INVALID_CASE')
        closed(tagged, {'type', 'value'}, 'PAT_SIM_INVALID_CASE')
        kind, data = tagged['type'], tagged['value']
        require(type(kind) is str, 'PAT_SIM_INVALID_CASE')
        if kind == 'number':
            require(type(data) in {int, float} and abs(data) <= SAFE_INTEGER, 'PAT_SIM_INVALID_CASE')
            data = float(data)
        else:
            expected = {'integer': int, 'boolean': bool, 'string': str, 'null': type(None)}.get(kind)
            require(expected is not None and type(data) is expected, 'PAT_SIM_INVALID_CASE')
        result['parameters'][parameter] = data
    return result


@_errors
def generate_cases(value, trusted_descriptor, *, limits=None):
    """Plan deterministic static-domain trials. Execution/fault checks are deferred."""
    artifact = parse_pat(value)
    contract = qualify_fan_contract(artifact, trusted_descriptor)
    limits = _limits(CEILINGS if limits is None else limits)
    nominal, domains = contract['nominalParameters'], contract['applicableDomains']
    cases, positions = [], {}

    def add(parameters, categories, coverage, *, outcome='applicable', code=None, context=None):
        raw = {'parameters': {key: _tag(item) for key, item in sorted(parameters.items())},
               'taskKind': artifact['taskKind'], 'inputProfile': artifact['inputProfile'], 'evidenceMode': 'simulation'}
        raw.update(context or {})
        expected = {'staticOutcome': outcome, 'errorCode': code}
        if outcome == 'applicable':
            levels = [parameters[step['arguments']['level']['parameter']] if 'parameter' in step['arguments']['level']
                      else step['arguments']['level']['literal'] for step in artifact['steps']]
            expected.update(levels=levels, finalLevel=levels[-1], plannedChildOperations=len(levels))
        else:
            expected['plannedChildOperations'] = 0
        identity = _hash(b'HMS-PAT-SIM-DOMAIN-CASE-v0.1', {'input': raw, 'expected': expected})
        if identity in positions:
            case = cases[positions[identity]]
            case['categories'] = sorted(set(case['categories']) | set(categories))
            case['coverage'] = sorted(set(case['coverage']) | set(coverage))
            return
        require(len(cases) < limits['maxCases'], 'PAT_SIM_CASE_LIMIT')
        positions[identity] = len(cases)
        cases.append({'caseId': identity, 'categories': sorted(categories), 'coverage': sorted(coverage),
                      'input': raw, 'expected': expected})

    add(nominal, ['positive'], ['nominal'])
    keys = sorted(domains)
    axes = [sorted({domain['minimum'], _nominal(domain), domain['maximum']}) for domain in domains.values()]
    for values in itertools.product(*axes):
        parameters = dict(zip(keys, values))
        boundary = [key for key in keys if parameters[key] in {domains[key]['minimum'], domains[key]['maximum']}]
        if boundary:
            add(parameters, ['boundary'], ['applicable_boundary:' + key for key in boundary])
    for parameter, declared in contract['declaredDomains'].items():
        values = list(_values(declared))  # Whole-domain validation already limits fan levels to its concrete schema.
        negatives = [(False, 'boolean_type'), (float(nominal[parameter]), 'integral_number_type')]
        if declared['minimum'] > -SAFE_INTEGER:
            negatives.append((declared['minimum'] - 1, 'below_declared'))
        if declared['maximum'] < SAFE_INTEGER:
            negatives.append((declared['maximum'] + 1, 'above_declared'))
        for trial, reason in negatives:
            parameters = dict(nominal, **{parameter: trial})
            add(parameters, ['negative'], [reason + ':' + parameter],
                outcome='refused', code='PAT_PARAMETER_OUT_OF_DOMAIN')
        if 'enum' in declared:
            hole = declared['minimum']
            for number in declared['enum']:
                if number == hole:
                    hole += 1
                elif number > hole:
                    break
            if hole <= declared['maximum']:
                add(dict(nominal, **{parameter: hole}), ['negative'], ['enum_hole:' + parameter],
                    outcome='refused', code='PAT_PARAMETER_OUT_OF_DOMAIN')
        lower = [number for number in values if number < domains[parameter]['minimum']]
        upper = [number for number in values if number > domains[parameter]['maximum']]
        outside = ([max(lower)] if lower else []) + ([min(upper)] if upper else [])
        for number in outside:
            add(dict(nominal, **{parameter: number}), ['negative'], ['outside_applicability:' + parameter],
                outcome='not_applicable')
    if keys:
        missing = dict(nominal); del missing[keys[0]]
        add(missing, ['negative'], ['missing_parameter'], outcome='refused', code='PAT_INVALID_PARAMETERS')
    extra = 'unexpected'
    while extra in nominal:
        extra += 'x'
    add(dict(nominal, **{extra: 0}), ['negative'], ['extra_parameter'], outcome='refused', code='PAT_INVALID_PARAMETERS')
    for field, other in (('taskKind', 'unsupported:task'), ('inputProfile', 'unsupported:input'), ('evidenceMode', 'physical')):
        if other == artifact.get(field):
            other += ':other'
        add(nominal, ['negative'], ['wrong_' + field], outcome='not_applicable', context={field: other})
    operations = sum(case['expected']['plannedChildOperations'] for case in cases)
    require(operations <= limits['maxChildOperations'], 'PAT_SIM_EFFECT_LIMIT')
    matrix = {'profile': MATRIX_PROFILE, 'policy': POLICY, 'artifactDigest': contract['artifactDigest'],
              'descriptorDigest': contract['descriptorDigest'], 'declaredDomains': contract['declaredDomains'],
              'applicableDomains': domains, 'limits': limits, 'cases': cases,
              'plannedChildOperations': operations, 'qualificationPassed': False,
              'coverage': {'exhaustiveBehavior': False, 'faultTrialsIncluded': False,
                  'note': 'Finite static nominal/boundary/negative plan only; no execution, replay, cancel, restart or outcome qualification.'}}
    canonical(matrix)
    return matrix


@_errors
def matrix_digest(value, trusted_descriptor, *, limits=None):
    return _hash(b'HMS-PAT-SIM-DOMAIN-MATRIX-v0.1', generate_cases(value, trusted_descriptor, limits=limits))
