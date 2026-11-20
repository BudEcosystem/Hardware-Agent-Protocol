"""Independent finite PAT-to-request correspondence over retained I/O trials.

Does not import the compiler, PAT policy/parser, registry, runtime or worker.
Historical identity consistency is distinct from current implementation attestation.
"""
from __future__ import annotations

import hashlib
import re

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, parse_json
from .pat_io_board_history import IoHistoryError, _Model, _tables, digest
from .pat_io_transcript import IoTranscriptError, ORIGIN, _read
from .resource_topology import ResourceTopologyError


class IoCorrespondenceError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_CORRESPONDENCE_' + code
        super().__init__(self.code)


def require(value, code):
    if not value:
        raise IoCorrespondenceError(code)


def closed(value, fields, code='ARTIFACT'):
    require(type(value) is dict and set(value) == set(fields), code)


def integer(value, low=0, high=SAFE_INTEGER):
    require(type(value) is int and low <= value <= high, 'INTEGER')
    return value


def same(left, right):
    return canonical(left) == canonical(right)


def plain_digest(value):
    return 'sha256:' + hashlib.sha256(canonical(value)).hexdigest()


def _contains(domain, value):
    return type(value) is int and domain['minimum'] <= value <= domain['maximum'] and (
        'enum' not in domain or value in domain['enum'])


class _Program:
    def __init__(self, setup):
        self.model = model = _Model(setup)
        self.artifact, self.descriptor = a, d = setup['artifact'], setup['original_descriptor']
        closed(a, {'protocol', 'profile', 'name', 'version', 'taskKind', 'inputProfile', 'parameters', 'roles',
                   'applicability', 'targetProfile', 'executionPlacement', 'timingBudget', 'steps', 'effectBudget',
                   'outcomeContract', 'runtimeGuardProfile'})
        require(a['protocol'] == 'hms.pat/0.1' and a['profile'] == 'hms.pat.bound-sequence/0.1' and
                a['targetProfile'] == 'hms.bound-sequence/0.1' and a['executionPlacement'] == 'hms-host-orchestration' and
                a['runtimeGuardProfile'] == 'installed_primitive_guards_only', 'PROFILE')
        for key in ('name', 'version', 'taskKind', 'inputProfile'): identifier(a[key])
        require(type(a['roles']) is dict and len(a['roles']) == 1, 'PROFILE')
        self.role, = a['roles']; identifier(self.role)
        requirement = a['roles'][self.role]
        closed(requirement, {'capabilityFamily', 'actions', 'driverProfiles'})
        self.action = model.target[1]
        require(requirement['capabilityFamily'] == 'sim:finite-gpio-pwm' and requirement['actions'] == [self.action] and
                type(requirement['driverProfiles']) is list and 1 <= len(requirement['driverProfiles']) <= 16 and
                len(set(requirement['driverProfiles'])) == len(requirement['driverProfiles']) and
                d['driverProfile'] in requirement['driverProfiles'], 'PROFILE')
        for value in requirement['driverProfiles']: identifier(value)
        detail = model.details[model.target]
        self.units = {'durationMs': 'ms', 'level': '1'} if detail['primitive'] == 'gpio_pulse' else {
            'durationMs': 'ms', 'frequencyHz': 'Hz', 'dutyPermille': 'permille', 'resolutionBits': 'bit'}
        self.limits = {'durationMs': (1, 5000), 'level': (0, 1)} if detail['primitive'] == 'gpio_pulse' else {
            'durationMs': (1, 5000), 'frequencyHz': (detail['envelope']['minFrequencyHz'], detail['envelope']['maxFrequencyHz']),
            'dutyPermille': (0, 1000), 'resolutionBits': (8, 8)}
        metadata = {key: {'profile': 'hms.pat.argument.fixed-schema-unit/0.1', 'unit': unit,
                          'frame': None, 'unitArgument': None, 'frameArgument': None} for key, unit in self.units.items()}
        require(same(d['argumentMetadata'], {self.action: metadata}), 'UNITS')
        action = d['type']['execution']['actions'][self.action]
        properties = {key: ({'type': 'integer', 'const': lo} if key == 'resolutionBits' else
                           {'type': 'integer', 'minimum': lo, 'maximum': hi}) for key, (lo, hi) in self.limits.items()}
        for schema in (action['inputSchema'], d['binding']['argumentSchemas'][self.action]):
            closed(schema, {'type', 'properties', 'required', 'additionalProperties'}, 'ARGUMENT_SCHEMA')
            require(schema['type'] == 'object' and schema['additionalProperties'] is False and same(schema['properties'], properties) and
                    type(schema['required']) is list and len(schema['required']) == len(properties) and set(schema['required']) == set(properties), 'ARGUMENT_SCHEMA')
        require(type(action['maxRunMs']) is int and action['maxRunMs'] == 5000 and action['effect'] == detail['primitive'] and
                action['completionEvidence'] == ['simulation'] and action['preconditions'] == [], 'ARGUMENT_SCHEMA')
        require(d['binding']['typeDigest'] == digest(b'HMS-TYPE-BUNDLE-v0.1', d['type']), 'TYPE_IDENTITY')
        require(type(a['parameters']) is dict and len(a['parameters']) <= 32, 'PARAMETERS')
        self.domains = {}
        for key, declaration in a['parameters'].items():
            identifier(key); closed(declaration, {'valueSchema', 'unit', 'frame'})
            identifier(declaration['unit']); require(declaration['frame'] is None, 'UNITS')
            domain = declaration['valueSchema']
            require(type(domain) is dict and set(domain) in ({'type', 'minimum', 'maximum'}, {'type', 'minimum', 'maximum', 'enum'}) and
                    domain['type'] == 'integer', 'PARAMETERS')
            integer(domain['minimum'], -SAFE_INTEGER); integer(domain['maximum'], domain['minimum'])
            if 'enum' in domain:
                values = domain['enum']
                require(type(values) is list and 1 <= len(values) <= 64 and all(type(v) is int and domain['minimum'] <= v <= domain['maximum'] for v in values) and
                        len(set(values)) == len(values), 'PARAMETERS')
                domain = domain | {'enum': sorted(values)}
            self.domains[key] = domain
        require(sum((len(v['enum']) if 'enum' in v else v['maximum'] - v['minimum'] + 1) > 1 for v in self.domains.values()) <= 2, 'PARAMETERS')
        budget = a['timingBudget']
        closed(budget, {'latestStartOffsetMs', 'latestCompletionOffsetMs', 'maxRunSumMs'})
        integer(budget['latestStartOffsetMs'], 1, 2**32 - 1)
        integer(budget['latestCompletionOffsetMs'], budget['latestStartOffsetMs'], 2**32 - 1)
        integer(budget['maxRunSumMs'], 1, budget['latestCompletionOffsetMs'])
        require(ORIGIN + budget['latestCompletionOffsetMs'] <= SAFE_INTEGER, 'TIMING')
        require(type(a['steps']) is list and 1 <= len(a['steps']) <= 16, 'STEPS')
        ids, used, run_sum = set(), set(), 0
        for ordinal, step in enumerate(a['steps']):
            closed(step, {'stepId', 'role', 'actionId', 'arguments', 'timing'}); identifier(step['stepId'])
            require(step['stepId'] not in ids and step['role'] == self.role and step['actionId'] == self.action, 'STEPS')
            ids.add(step['stepId']); closed(step['arguments'], self.units, 'ARGUMENTS')
            for argument, expression in step['arguments'].items():
                require(type(expression) is dict and set(expression) in ({'parameter'}, {'literal'}), 'EXPRESSION')
                if 'parameter' in expression:
                    name = expression['parameter']; require(type(name) is str and name in self.domains, 'EXPRESSION')
                    used.add(name); domain = self.domains[name]
                    low, high = (min(domain['enum']), max(domain['enum'])) if 'enum' in domain else (domain['minimum'], domain['maximum'])
                    require(a['parameters'][name]['unit'] == self.units[argument], 'UNITS')
                else:
                    low = high = integer(expression['literal'], -SAFE_INTEGER)
                lo, hi = self.limits[argument]
                require(lo <= low <= high <= hi, 'ARGUMENT_DOMAIN')
            window = step['timing']
            closed(window, {'notBeforeOffsetMs', 'latestStartOffsetMs', 'latestCompletionOffsetMs', 'maxRunMs'})
            integer(window['notBeforeOffsetMs'], 0, 2**32 - 1)
            integer(window['latestStartOffsetMs'], window['notBeforeOffsetMs'], 2**32 - 1)
            integer(window['latestCompletionOffsetMs'], window['latestStartOffsetMs'], budget['latestCompletionOffsetMs'])
            integer(window['maxRunMs'], 1, min(5000, window['latestCompletionOffsetMs'] - window['notBeforeOffsetMs']))
            require(ordinal != 0 or window['latestStartOffsetMs'] <= budget['latestStartOffsetMs'], 'TIMING')
            run_sum += window['maxRunMs']
        require(used == set(self.domains) and run_sum <= budget['maxRunSumMs'], 'STEPS')
        closed(a['effectBudget'], {'maxInvocations', 'scope'})
        integer(a['effectBudget']['maxInvocations'], len(ids), 16)
        require(a['effectBudget']['scope'] == 'simulation_only' and same(a['outcomeContract'], {
            'requiredEffect': 'capability_completion', 'requiredCompletedSteps': [s['stepId'] for s in a['steps']],
            'evidenceMode': 'simulation', 'physicalObjectiveVerified': False}), 'EFFECT')
        closed(a['applicability'], {'phase', 'all'})
        require(a['applicability']['phase'] == 'selection' and type(a['applicability']['all']) is list and len(a['applicability']['all']) <= 32, 'APPLICABILITY')
        for predicate in a['applicability']['all']:
            require(type(predicate) is dict and predicate.get('op') in {'equals', 'range'}, 'APPLICABILITY')
            closed(predicate, {'field', 'op', 'literal'} if predicate['op'] == 'equals' else {'field', 'op', 'minimum', 'maximum'}, 'APPLICABILITY')
            field = predicate['field']; require(type(field) is str, 'APPLICABILITY')
            if field.startswith('parameters.'):
                key = field[len('parameters.'):]; require(key in self.domains, 'APPLICABILITY'); domain = self.domains[key]
                if predicate['op'] == 'equals': require(_contains(domain, predicate['literal']), 'APPLICABILITY')
                else:
                    integer(predicate['minimum'], domain['minimum'], domain['maximum'])
                    integer(predicate['maximum'], predicate['minimum'], domain['maximum'])
            else:
                require(field in {'trigger.taskKind', 'trigger.inputProfile', 'context.evidenceMode'} and predicate['op'] == 'equals' and
                        type(predicate['literal']) is str, 'APPLICABILITY')
        self.pat_digest = digest(b'HMS-PAT-JCS-SHA256-v0.1', a)
        contract = setup['static_contract']
        require(contract['profile'] == 'hms.pat.io-static-contract/0.1' and contract['policy'] == 'hms.pat.eval.sqlite-finite-io-sequence/0.1' and
                contract['artifactDigest'] == self.pat_digest and contract['descriptorDigest'] == digest(b'HMS-PAT-IO-DESCRIPTOR-v0.1', d) and
                contract['installationDigest'] == model.installation_digest and contract['driverDigest'] == d['driverDigest'] and
                (contract['role'], contract['actionId'], contract['primitive']) == (self.role, self.action, detail['primitive']) and
                same(contract['declaredDomains'], self.domains) and contract['qualificationPassed'] is False, 'STATIC_ASSOCIATION')

    def parameters(self, lower):
        tagged, context = lower['parameters'], lower['context']
        if set(tagged) != set(self.domains): return None, 'PAT_INVALID_PARAMETERS'
        values = {}
        for key, domain in self.domains.items():
            tag = tagged[key]
            if tag['type'] != 'integer' or not _contains(domain, tag['value']): return None, 'PAT_PARAMETER_OUT_OF_DOMAIN'
            values[key] = tag['value']
        # The worker fixes deployment from the trusted installation, overriding
        # a supplied deployment field; no other caller context key is ignored.
        if set(context) not in ({'taskKind', 'inputProfile', 'evidenceMode'}, {'taskKind', 'inputProfile', 'evidenceMode', 'deployment'}):
            return None, 'PAT_INVALID_CONTEXT'
        if (context['taskKind'], context['inputProfile'], context['evidenceMode']) != (
                self.artifact['taskKind'], self.artifact['inputProfile'], 'simulation'):
            return None, 'PAT_NOT_APPLICABLE'
        fields = {'trigger.taskKind': context['taskKind'], 'trigger.inputProfile': context['inputProfile'], 'context.evidenceMode': context['evidenceMode']}
        fields.update({'parameters.' + key: value for key, value in values.items()})
        for predicate in self.artifact['applicability']['all']:
            value = fields[predicate['field']]
            if predicate['op'] == 'equals' and not same(value, predicate['literal']): return None, 'PAT_NOT_APPLICABLE'
            if predicate['op'] == 'range' and not predicate['minimum'] <= value <= predicate['maximum']: return None, 'PAT_NOT_APPLICABLE'
        return values, None

    def environment(self, compiler, session):
        d, binding = self.descriptor, self.descriptor['binding']
        dependency = {'role': self.role, 'descriptionDigest': binding['typeDigest'], 'bindingDigest': plain_digest(binding),
            'instanceId': binding['instanceId'], 'bindingGeneration': binding['generation'], 'controlGeneration': binding['controlGeneration'],
            'calibrationRevision': binding['calibrationRevision'], 'endpointSession': session, 'driverProfile': d['driverProfile'],
            'driverDigest': d['driverDigest'], 'installationDigest': d['installationDigest'], 'metadataDigest': plain_digest(d['argumentMetadata'])}
        environment = {'profile': 'hms.pat.environment/0.1', 'deployment': self.model.deployment, 'evidenceMode': 'simulation',
            'compilerDigest': compiler, 'roles': {self.role: {'typeDigest': binding['typeDigest'], 'bindingDigest': dependency['bindingDigest'],
                'installationDigest': d['installationDigest'], 'argumentMetadataDigest': dependency['metadataDigest'],
                'driverProfile': d['driverProfile'], 'driverDigest': d['driverDigest']}}}
        return {'patDigest': self.pat_digest, 'compilerDigest': compiler, 'dependencies': [dependency],
                'evaluationEnvironment': environment, 'environmentDigest': digest(b'HMS-PAT-ENVIRONMENT-v0.1', environment)}

    def request(self, values, namespace, session):
        binding, children = self.descriptor['binding'], []
        for ordinal, step in enumerate(self.artifact['steps']):
            args = {key: values[e['parameter']] if 'parameter' in e else e['literal'] for key, e in step['arguments'].items()}
            window = step['timing']
            intent = {'instanceId': binding['instanceId'], 'actionId': step['actionId'], 'endpointSession': session,
                'controlGeneration': binding['controlGeneration'], 'descriptionDigest': binding['typeDigest'],
                'bindingGeneration': binding['generation'], 'calibrationRevision': binding['calibrationRevision'],
                'arguments': args, 'requiredEffect': 'capability_completion', 'timing': {
                    'notBeforeUnixMs': ORIGIN + window['notBeforeOffsetMs'], 'latestStartUnixMs': ORIGIN + window['latestStartOffsetMs'],
                    'latestCompletionUnixMs': ORIGIN + window['latestCompletionOffsetMs'], 'maxRunMs': window['maxRunMs']}}
            self.model.intent(intent)
            children.append({'stepId': step['stepId'], 'request': {'protocol': 'hms.invoke/0.1', 'replayNamespace': namespace,
                'operationKey': 'trial:child:' + str(ordinal), 'intent': intent}})
        budget = self.artifact['timingBudget']
        return {'protocol': 'hms.procedure/0.1', 'replayNamespace': namespace, 'procedureKey': 'trial:parent',
            'procedure': {'profile': 'hms.bound-sequence/0.1', 'timing': {'notBeforeUnixMs': ORIGIN,
                'latestStartUnixMs': ORIGIN + budget['latestStartOffsetMs'], 'latestCompletionUnixMs': ORIGIN + budget['latestCompletionOffsetMs']}, 'steps': children}}


def _no_work(t, model):
    empty = ('operations', 'pr_procedures', 'events', 'pr_events', 'pr_steps', 'pr_keys', 'replay_keys', 'claims', 'resource_floors',
             'io_dispatch_links', 'io_authority_receipts', 'io_receipts', 'io_receipt_versions', 'io_owners', 'io_fences')
    require(all(not t[key] for key in empty), 'LOWERING_ADMITTED_WORK')
    require({r['instance'] for r in t['io_effects']} == set(model.routes) and
            all((r['activations'], r['completed'], r['canceled']) == (0, 0, 0) for r in t['io_effects']), 'LOWERING_EFFECT')
    require(same({r['resource']: parse_json(r['state']) for r in t['io_resources']}, model.idle), 'LOWERING_EFFECT')


def _inspect(transcript, setup):
    program = _Program(setup)
    lower = [r['value'] for r in transcript['records'] if r['kind'] == 'lower_input']
    calls = [c for c in transcript['calls'] if c['label'] == 'lower']
    require(len(lower) == len(calls) == 1, 'LOWER_INVENTORY')
    compiler = transcript['opened'][0]['originalEnvironment']['compilerDigest']
    require(type(compiler) is str and re.fullmatch('sha256:[0-9a-f]{64}', compiler) is not None, 'ENVIRONMENT')
    for opened in transcript['opened']:
        require(same(opened['originalEnvironment'], program.environment(compiler, program.descriptor['endpointSession'])) and
                same(opened['workerEnvironment'], program.environment(compiler, opened['session'])), 'ENVIRONMENT')
    tables = next(_tables(transcript, cp) for cp in transcript['checkpoints'] if cp['value']['label'] in {'lower:after', 'lower:after_error'})
    _no_work(tables, program.model)
    require(len(tables['namespaces']) == 1, 'NAMESPACE')
    ns = tables['namespaces'][0]; opening = transcript['opened'][0]
    require(ns['principal'] == 'pat-io-trial-worker' and ns['deployment'] == program.model.deployment and ns['epoch'] == 1 and
            ns['expires_ms'] == ORIGIN + program.artifact['timingBudget']['latestCompletionOffsetMs'] + 1 and
            re.fullmatch('replay:' + re.escape(opening['authorityId']) + ':1:[0-9a-f]{32}', ns['token']) is not None, 'NAMESPACE')
    values, error = program.parameters(lower[0]); call = calls[0]
    plans = [r['value'] for r in transcript['records'] if r['kind'] == 'compiled_plan']
    if error is not None:
        require(not call['returned'] and call['outcome']['exception'] == 'PatError' and call['outcome']['code'] == error and not plans, 'REFUSAL')
        for cp in transcript['checkpoints']: _no_work(_tables(transcript, cp), program.model)
        request_digest = None
    else:
        require(call['returned'] and len(plans) == 1, 'REFUSAL')
        request = program.request(values, ns['token'], opening['session'])
        plan = plans[0]
        require(same(plan['request'], request), 'REQUEST')
        request_digest = digest(b'HMS-PROCEDURE-JCS-SHA256-v0.1', request)
        bound = program.descriptor | {'endpointSession': opening['session']}
        expected = program.environment(compiler, opening['session']) | {'request': request, 'requestDigest': request_digest,
            'runBindingDigest': digest(b'HMS-PAT-RUN-BINDING-v0.1', {'bindings': {program.role: bound},
                'compilerDigest': compiler, 'targetProfile': program.artifact['targetProfile']}),
            'report': {'targetProfile': 'hms.bound-sequence/0.1', 'stepCount': len(program.artifact['steps']), 'admitted': False,
                'parameterDomainPreserved': True, 'unitConversions': [], 'frameConversions': [], 'unsupported': [],
                'runtimeGuards': 'installed_primitive_guards_only', 'evidenceMode': 'simulation', 'physicalObjectiveVerified': False}}
        require(same(plan, expected), 'PLAN_METADATA')
    return {'profile': 'hms.pat.io-correspondence-inspection/0.1', 'patCorrespondenceChecked': True,
            'parameterOutcome': 'refused' if error else 'lowered', 'refusalCode': error, 'requestDigest': request_digest,
            'stepsChecked': 0 if error else len(program.artifact['steps']), 'runtimeEnvironmentsChecked': len(transcript['opened']),
            'historicalIdentityConsistencyChecked': True, 'compilerIdentityAttested': False,
            'staticTimingPolicyChecked': False, 'liveConfigurationAttested': False,
            'operationHistoryChecked': False, 'boardHistoryChecked': False, 'procedureHistoryChecked': False,
            'independentOutcomeChecked': False, 'qualificationPassed': False}


def inspect_pat_correspondence(references, files, *, expected_setup):
    """Compare exact trusted PAT intent with emitted requests; no execution/I/O."""
    try:
        result = _inspect(_read(references, files, expected_setup), expected_setup)
        canonical(result)
        return result
    except (IoCorrespondenceError, IoTranscriptError):
        raise
    except (IoHistoryError, ResourceTopologyError, ContractError, KeyError, TypeError, ValueError, IndexError, RecursionError, StopIteration) as error:
        raise IoCorrespondenceError('SHAPE') from error
