"""Finite GPIO/PWM static contracts and case plans; no execution qualification.

Trusted construction validates the full installation and reads its source pins.
Subsequent qualification/planning methods use detached snapshots only. Their
zero-latency virtual schedule is not a bound on host or physical execution.
"""
from __future__ import annotations

import copy
from functools import wraps
import hashlib
import itertools

from .contracts import ContractError, SAFE_INTEGER, canonical
from .journal import JournalError
from .pat_compiler import _binding, _validate_static_step
from .pat_contracts import (PatError, closed, equal, integer, matches_static,
                            parse_pat, pat_digest, require, snapshot)
from .pat_simulation_contracts import decode_case_input
from .synthetic_io_installation import (DRIVER, definitions, installation_digest,
                                        normalize_installation)

POLICY = 'hms.pat.eval.sqlite-finite-io-sequence/0.1'
CLOCK_POLICY = 'hms.pat.io-clock.zero-latency/0.1'
CONTRACT_PROFILE = 'hms.pat.io-static-contract/0.1'
MATRIX_PROFILE = 'hms.pat.io-domain-matrix/0.1'
CEILINGS = {'maxCases': 32, 'maxChildOperations': 512}
_UNITS = {'gpio_pulse': {'level': '1', 'durationMs': 'ms'},
          'pwm_burst': {'frequencyHz': 'Hz', 'dutyPermille': 'permille',
                        'resolutionBits': 'bit', 'durationMs': 'ms'}}


def _errors(method):
    @wraps(method)
    def checked(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except PatError:
            raise
        except JournalError as error:
            raise PatError('PAT_IO_INVALID_INSTALLATION', error.code) from error
        except (ContractError, TypeError, ValueError, KeyError, RecursionError) as error:
            raise PatError('PAT_IO_INVALID_CONTRACT') from error
    return checked


def _hash(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _same(left, right):
    pending = [(left, right)]
    while pending:
        left, right = pending.pop()
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            if set(left) != set(right):
                return False
            pending.extend((left[key], right[key]) for key in left)
        elif type(left) is list:
            if len(left) != len(right):
                return False
            pending.extend(zip(left, right))
        elif left != right:
            return False
    return True


def _bounds(domain):
    return (domain['enum'][0], domain['enum'][-1]) if 'enum' in domain else (domain['minimum'], domain['maximum'])


def _size(domain):
    return len(domain['enum']) if 'enum' in domain else domain['maximum'] - domain['minimum'] + 1


def _nominal(domain):
    return domain['enum'][len(domain['enum']) // 2] if 'enum' in domain else (domain['minimum'] + domain['maximum']) // 2


def _schedule(artifact, domains):
    """Sufficient interval enclosure; correlated lease bounds may overreject."""
    rows, admission_lo, admission_hi = [], 0, 0
    parent = artifact['timingBudget']
    require(admission_hi < parent['latestStartOffsetMs'], 'PAT_IO_START_WINDOW')
    for step in artifact['steps']:
        expression = step['arguments']['durationMs']
        low, high = (_bounds(domains[expression['parameter']]) if 'parameter' in expression
                     else (expression['literal'], expression['literal']))
        timing = step['timing']
        require(1 <= low <= high < timing['maxRunMs'], 'PAT_IO_DURATION_BUDGET')
        start_lo = max(admission_lo, timing['notBeforeOffsetMs'])
        start_hi = max(admission_hi, timing['notBeforeOffsetMs'])
        finish_lo, finish_hi = start_lo + low, start_hi + high
        for value in (start_lo, start_hi, finish_lo, finish_hi, admission_lo + 60000):
            integer(value, code='PAT_TIME_BOUNDS')
        require(start_hi < timing['latestStartOffsetMs'], 'PAT_IO_START_WINDOW')
        require(finish_hi < timing['latestCompletionOffsetMs'], 'PAT_IO_COMPLETION_WINDOW')
        require(finish_hi < admission_lo + 60000, 'PAT_IO_LEASE_WINDOW')
        require(finish_hi < parent['latestCompletionOffsetMs'], 'PAT_IO_PARENT_WINDOW')
        rows.append({'stepId': step['stepId'], 'durationMinMs': low, 'durationMaxMs': high,
            'admissionMinOffsetMs': admission_lo, 'admissionMaxOffsetMs': admission_hi,
            'startMinOffsetMs': start_lo, 'startMaxOffsetMs': start_hi,
            'finishMinOffsetMs': finish_lo, 'finishMaxOffsetMs': finish_hi,
            'earliestLeaseExpiryOffsetMs': min(timing['latestCompletionOffsetMs'], admission_lo + 60000)})
        admission_lo, admission_hi = finish_lo, finish_hi
    return {'profile': CLOCK_POLICY, 'dispatchLagMs': 0, 'guardLagMs': 0,
            'pollLagMs': 0, 'settlementLagMs': 0, 'steps': rows,
            'maxOriginMs': SAFE_INTEGER - parent['latestCompletionOffsetMs'],
            'correlationsOverapproximated': True, 'hostTimingGuaranteed': False}


class IoSequencePolicy:
    """Trusted installation setup followed by pure, finite static planning.

    The descriptor must come from the trusted I/O resolver. Matching its shape
    here does not attest live permission, presence, registration or freshness.
    """

    @_errors
    def __init__(self, installation):
        document = normalize_installation(installation)
        self._definitions = definitions(document)
        self._installation_digest = installation_digest(document)
        self._driver_digest = document['driverDigest']
        self._handlers = {(row['instanceId'], row['actionId']): row['primitive']
                          for row in document['handlers']}

    def _contract(self, artifact, descriptor):
        require(len(artifact['roles']) == 1, 'PAT_IO_UNSUPPORTED_PROGRAM')
        role, = artifact['roles']
        requirement = artifact['roles'][role]
        require(requirement['capabilityFamily'] == 'sim:finite-gpio-pwm' and
                len(requirement['actions']) == 1, 'PAT_IO_UNSUPPORTED_PROGRAM')
        _binding(descriptor, requirement)
        action, = requirement['actions']
        instance = descriptor['binding']['instanceId']
        expected = self._definitions.get(instance)
        require(expected is not None and descriptor['driverProfile'] == DRIVER and
                descriptor['driverDigest'] == self._driver_digest and
                descriptor['installationDigest'] == self._installation_digest and
                _same(descriptor['binding'], expected['binding']) and
                _same(descriptor['type'], expected['type']), 'PAT_IO_INSTALLATION_MISMATCH')
        primitive = self._handlers.get((instance, action))
        require(primitive in _UNITS, 'PAT_IO_UNSUPPORTED_PROGRAM')
        metadata = {name: {'profile': 'hms.pat.argument.fixed-schema-unit/0.1',
                    'unit': unit, 'frame': None, 'unitArgument': None, 'frameArgument': None}
                    for name, unit in _UNITS[primitive].items()}
        require(_same(descriptor['argumentMetadata'], {action: metadata}), 'PAT_IO_UNSUPPORTED_SEMANTICS')
        declared = {}
        for name in sorted(artifact['parameters']):
            declaration = artifact['parameters'][name]
            require(declaration['valueSchema']['type'] == 'integer', 'PAT_IO_UNSUPPORTED_PARAMETER')
            domain = copy.deepcopy(declaration['valueSchema'])
            if 'enum' in domain:
                domain['enum'].sort()
            declared[name] = domain
        require(sum(_size(domain) > 1 for domain in declared.values()) <= 2, 'PAT_IO_PARAMETER_AXIS_LIMIT')
        for step in artifact['steps']:
            require(step['role'] == role and step['actionId'] == action and
                    set(step['arguments']) == set(metadata), 'PAT_IO_UNSUPPORTED_PROGRAM')
            require(all('parameter' in expression or type(expression['literal']) is int
                        for expression in step['arguments'].values()), 'PAT_ARGUMENT_DOMAIN')
            _validate_static_step(artifact, step, descriptor)
        # Both schema fit AND the whole declared timing range precede applicability.
        schedule = _schedule(artifact, declared)
        applicable = copy.deepcopy(declared)
        context = {'trigger.taskKind': artifact['taskKind'], 'trigger.inputProfile': artifact['inputProfile'],
                   'context.evidenceMode': 'simulation'}
        for predicate in artifact['applicability']['all']:
            field = predicate['field']
            if not field.startswith('parameters.'):
                require(equal(predicate['literal'], context[field]), 'PAT_IO_EMPTY_APPLICABILITY')
                continue
            domain = applicable[field[len('parameters.'):]]
            lo, hi = ((predicate['literal'], predicate['literal']) if predicate['op'] == 'equals'
                      else (predicate['minimum'], predicate['maximum']))
            domain['minimum'] = max(domain['minimum'], lo)
            domain['maximum'] = min(domain['maximum'], hi)
        for domain in applicable.values():
            require(domain['minimum'] <= domain['maximum'], 'PAT_IO_EMPTY_APPLICABILITY')
            if 'enum' in domain:
                domain['enum'] = [value for value in domain['enum'] if domain['minimum'] <= value <= domain['maximum']]
                require(bool(domain['enum']), 'PAT_IO_EMPTY_APPLICABILITY')
                domain['minimum'], domain['maximum'] = _bounds(domain)
        nominal = {key: _nominal(domain) for key, domain in applicable.items()}
        require(matches_static(artifact, nominal, task_kind=artifact['taskKind'], input_profile=artifact['inputProfile'],
                               evidence_mode='simulation'), 'PAT_IO_EMPTY_APPLICABILITY')
        return {'profile': CONTRACT_PROFILE, 'policy': POLICY, 'artifactDigest': pat_digest(artifact),
            'descriptorDigest': _hash(b'HMS-PAT-IO-DESCRIPTOR-v0.1', descriptor),
            'installationDigest': self._installation_digest, 'driverDigest': self._driver_digest,
            'role': role, 'actionId': action, 'primitive': primitive, 'declaredDomains': declared,
            'applicableDomains': applicable, 'nominalParameters': nominal, 'schedule': schedule,
            'qualificationPassed': False}

    @_errors
    def qualify(self, value, trusted_descriptor):
        """Return static compatibility, never an execution qualification receipt."""
        artifact = parse_pat(value)
        descriptor = snapshot(trusted_descriptor, 'PAT_IO_INVALID_DESCRIPTOR')
        result = self._contract(artifact, descriptor)
        canonical(result)
        return result

    @_errors
    def generate_cases(self, value, trusted_descriptor, *, limits=None):
        """Finite static plan only; a future worker must add bounded fault trials."""
        artifact = parse_pat(value)
        descriptor = snapshot(trusted_descriptor, 'PAT_IO_INVALID_DESCRIPTOR')
        contract = self._contract(artifact, descriptor)
        limits = snapshot(CEILINGS if limits is None else limits, 'PAT_IO_INVALID_LIMITS')
        closed(limits, CEILINGS, 'PAT_IO_INVALID_LIMITS')
        for key, maximum in CEILINGS.items():
            integer(limits[key], 1, maximum, 'PAT_IO_INVALID_LIMITS')
        nominal, domains = contract['nominalParameters'], contract['applicableDomains']
        cases, positions = [], {}

        def add(parameters, categories, coverage, *, outcome='applicable', code=None, context=None):
            def tag(item):
                kind = {int: 'integer', bool: 'boolean', float: 'number'}[type(item)]
                return {'type': kind, 'value': int(item) if type(item) is float else item}
            raw = {'parameters': {key: tag(item) for key, item in sorted(parameters.items())},
                   'taskKind': artifact['taskKind'], 'inputProfile': artifact['inputProfile'], 'evidenceMode': 'simulation'}
            raw.update(context or {})
            expected = {'staticOutcome': outcome, 'errorCode': code, 'plannedChildOperations': 0}
            if outcome == 'applicable':
                arguments = [{key: parameters[expr['parameter']] if 'parameter' in expr else expr['literal']
                              for key, expr in step['arguments'].items()} for step in artifact['steps']]
                expected.update(arguments=arguments, plannedChildOperations=len(arguments))
            identity = _hash(b'HMS-PAT-IO-DOMAIN-CASE-v0.1', {'input': raw, 'expected': expected})
            if identity in positions:
                case = cases[positions[identity]]
                case['categories'] = sorted(set(case['categories']) | set(categories))
                case['coverage'] = sorted(set(case['coverage']) | set(coverage))
                return
            require(len(cases) < limits['maxCases'], 'PAT_IO_CASE_LIMIT')
            positions[identity] = len(cases)
            cases.append({'caseId': identity, 'categories': sorted(categories), 'coverage': sorted(coverage),
                          'input': raw, 'expected': expected})

        add(nominal, ['positive'], ['nominal'])
        keys = sorted(domains)
        axes = [sorted({*_bounds(domains[key]), _nominal(domains[key])}) for key in keys]
        for values in itertools.product(*axes):
            parameters = dict(zip(keys, values))
            boundary = [key for key in keys if parameters[key] in _bounds(domains[key])]
            if boundary or not keys:
                add(parameters, ['boundary'], ['applicable_boundary:' + key for key in boundary] or ['constant_domain'])
        for parameter, declared in contract['declaredDomains'].items():
            negatives = [(False, 'boolean_type'), (float(nominal[parameter]), 'integral_number_type')]
            if declared['minimum'] > -SAFE_INTEGER:
                negatives.append((declared['minimum'] - 1, 'below_declared'))
            if declared['maximum'] < SAFE_INTEGER:
                negatives.append((declared['maximum'] + 1, 'above_declared'))
            for trial, reason in negatives:
                add(dict(nominal, **{parameter: trial}), ['negative'], [reason + ':' + parameter],
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
                outside = ([max(v for v in declared['enum'] if v < domains[parameter]['minimum'])]
                           if any(v < domains[parameter]['minimum'] for v in declared['enum']) else [])
                outside += ([min(v for v in declared['enum'] if v > domains[parameter]['maximum'])]
                            if any(v > domains[parameter]['maximum'] for v in declared['enum']) else [])
            else:
                outside = ([domains[parameter]['minimum'] - 1] if declared['minimum'] < domains[parameter]['minimum'] else [])
                outside += ([domains[parameter]['maximum'] + 1] if declared['maximum'] > domains[parameter]['maximum'] else [])
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
        require(operations <= limits['maxChildOperations'], 'PAT_IO_EFFECT_LIMIT')
        matrix = {'profile': MATRIX_PROFILE, 'policy': POLICY, 'contract': contract, 'limits': limits,
                  'cases': cases, 'plannedChildOperations': operations, 'qualificationPassed': False,
                  'coverage': {'exhaustiveBehavior': False, 'faultTrialsIncluded': False,
                      'requiresCombinedFaultBudgetCheck': True,
                      'note': 'Static nominal/boundary/negative plans only; no execution, replay, recovery or outcome qualification.'}}
        canonical(matrix)
        return matrix

    @_errors
    def matrix_digest(self, value, trusted_descriptor, *, limits=None):
        return _hash(b'HMS-PAT-IO-DOMAIN-MATRIX-v0.1', self.generate_cases(value, trusted_descriptor, limits=limits))
