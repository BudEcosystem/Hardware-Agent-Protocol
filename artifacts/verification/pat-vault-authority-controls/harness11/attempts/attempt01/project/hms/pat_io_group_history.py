"""Independent complete finite-I/O group inspection over a bounded byte archive.

Trusted setup is supplied separately and must be retained before worker release.
No worker, compiler, planner, runtime, filesystem, database or clock is called.
Archive agreement does not attest a run, enforce a disk quota or promote a PAT.
"""
import hashlib
import re

from .contracts import canonical, parse_json
from .pat_io_authority_semantics import inspect_authority_challenge
from .pat_io_clock_semantics import inspect_clock_challenge
from .pat_io_conflict_history import inspect_conflict_history
from .pat_io_correspondence import _Program
from .pat_io_lifecycle_semantics import inspect_lifecycle_challenge
from .pat_io_outcome_history import _static, _outcome
from .pat_io_resource_semantics import inspect_resource_challenge
from .pat_io_timing_history import inspect_timing_challenge
from .pat_io_transcript import _read

TIMING = frozenset(('not_before_boundary', 'latest_start_before', 'latest_start_equal',
    'run_completion_equal', 'wall_completion_equal', 'lease_wait_before', 'lease_wait_equal', 'late_parent_reporting'))
CLOCK = frozenset(('start_run_equal', 'wall_clock_regression', 'clock_epoch_mismatch'))
LIFECYCLE = frozenset(('cancel_accepted', 'cancel_pending', 'reopen_accepted', 'reopen_pending',
    'completion_reply_lost', 'pending_reply_lost', 'permission_before_parent', 'permission_before_dispatch',
    'permission_pending', 'permission_after_completion'))
AUTHORITY = frozenset(('binding_before_dispatch', 'binding_pending', 'full_authority_withdrawal'))
CEILINGS = dict(maxCases=32, maxChildOperations=512, maxSchedulerTicks=2048, maxProducerBytes=16*1024*1024,
    maxRecords=4096, maxDocumentBytes=65536, maxDerivedBytes=20*1024*1024, maxWallMs=60000)
INPUTS = ('candidate', 'installation', 'descriptor', 'bindings', 'matrix', 'implementation')


class IoGroupHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_GROUP_HISTORY_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoGroupHistoryError(code)


def closed(value, keys, code):
    require(type(value) is dict and set(value) == set(keys), code)


def integer(value, low, high, code):
    require(type(value) is int and low <= value <= high, code)
    return value


def strict(value):
    require(type(value) in (dict, list, str, int, bool, type(None)), 'SCALAR')
    if type(value) is dict:
        require(all(type(k) is str for k in value), 'SCALAR')
        for v in value.values(): strict(v)
    elif type(value) is list:
        for v in value: strict(v)


def snapshot(value):
    raw = canonical(value)
    strict(value)
    return parse_json(raw)


def same(left, right):
    return type(left) is type(right) and (
        set(left) == set(right) and all(same(left[k], right[k]) for k in left) if type(left) is dict else
        len(left) == len(right) and all(same(a, b) for a, b in zip(left, right)) if type(left) is list else left == right)


def digest(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _opening(value, compiler, case):
    original, current = value['originalEnvironment'], value['workerEnvironment']
    if case['kind'] == 'resource_challenge':
        require(value['create'] is True, 'ACTOR_ENVIRONMENTS')
        for environments in (original, current):
            closed(environments, ('gpio', 'pwm', 'alias', 'independent'), 'ACTOR_ENVIRONMENTS')
            require(all(type(e) is dict and e.get('compilerDigest') == compiler
                for e in environments.values()), 'COMPILER_ASSOCIATION')
        # The resource inspector checks each actor's complete environment.
        return
    require(type(original) is dict and original['compilerDigest'] == compiler, 'COMPILER_ASSOCIATION')
    if current is None:
        require(case['kind'] == 'fixed_challenge' and case['definition']['scenario'] in
            {'full_authority_withdrawal', 'binding_pending'} and value['create'] is False and
            same(value['bindingResolution'], dict(status='unavailable', exception='PatError',
                code='PAT_BINDING_NOT_APPLICABLE')), 'RESOLUTION_ABSENCE')
        # The complete authority inspector must independently prove this cause.
    else:
        require(type(current) is dict and current['compilerDigest'] == compiler, 'COMPILER_ASSOCIATION')


def _candidate(manifest, data, expected):
    case, setup = expected['expected_case'], expected['expected_setup']
    program = _Program(setup); static = _static(program, setup['static_contract'])
    raw = case['domainCase']['input']
    lower = dict(parameters=raw['parameters'], context={k: v for k, v in raw.items() if k != 'parameters'})
    values, error = program.parameters(lower)
    outcome = 'applicable' if error is None else 'not_applicable' if error == 'PAT_NOT_APPLICABLE' else 'refused'
    declared = case['domainCase']['expected']
    require(declared['staticOutcome'] == outcome and declared['errorCode'] == (None if outcome != 'refused' else error), 'DOMAIN_OUTCOME')
    if error is not None:
        closed(manifest, ('profile', 'caseId', 'programDigest', 'staticOutcome', 'errorCode', 'executionPerformed',
            'operationIds', 'schedulerTicks', 'qualificationPassed'), 'NEGATIVE_MANIFEST')
        require(same(manifest, dict(profile='hms.pat.io-negative-capture/0.1', caseId=case['caseId'],
            programDigest=case['programDigest'], staticOutcome=outcome, errorCode=error, executionPerformed=False,
            operationIds=[], schedulerTicks=0, qualificationPassed=False)), 'NEGATIVE_MANIFEST')
        return dict(profile='hms.pat.io-negative-inspection/0.1', caseId=case['caseId'], staticOutcome=outcome,
            errorCode=error, independentOutcomeChecked=True, expectedResponseVerified=True,
            staticTimingPolicyChecked=True, wholeDeclaredDomainChecked=True, staticContract=static,
            executionEvidencePresent=False, qualificationPassed=False), None, None
    require(manifest['executionPerformed'] is True, 'CANDIDATE_EXECUTION')
    closed(manifest, ('profile', 'caseId', 'programDigest', 'records', 'configuration', 'report',
        'executionPerformed', 'closed', 'qualificationPassed'), 'CANDIDATE_MANIFEST')
    require(manifest['profile'] == 'hms.pat.io-candidate-capture/0.1' and
        manifest['programDigest'] == program.pat_digest == case['programDigest'], 'CANDIDATE_MANIFEST')
    history = inspect_conflict_history(**data, expected_setup=setup, expected_authority=expected['expected_authority'])
    trace = _read(data['references'], data['files'], setup, conflict_profile=True)
    lowers = [r['value'] for r in trace['records'] if r['kind'] == 'lower_input']
    require(same(lowers, [lower]), 'DOMAIN_INPUT')
    arguments = [{k: values[e['parameter']] if 'parameter' in e else e['literal'] for k, e in s['arguments'].items()}
        for s in program.artifact['steps']]
    require(same(declared['arguments'], arguments), 'DOMAIN_ARGUMENTS')
    result = _outcome(trace, program, history)
    require(result['nominalCompletionSatisfied'] is True and result['settledAndQuiescent'] and
        result['unresolvedOperationIds'] == [], 'NOMINAL_COMPLETION')
    inspection = dict(profile='hms.pat.io-candidate-inspection/0.1', caseId=case['caseId'],
        staticTimingPolicyChecked=True, wholeDeclaredDomainChecked=True, completeHistoryChecked=True,
        independentOutcomeChecked=True, expectedResponseVerified=True, staticContract=static, outcome=result, history=history,
        configurationAttested=False, implementationIdentityAttested=False, qualificationPassed=False)
    return inspection, history, result


def _inspect_io_group(files, *, expected_inputs, expected_cases):
    """Return bounded summary and separate case inspection documents, or refuse.

files includes the exact retained group tree, including result and closed state
bytes. State bytes are inventoried, not interpreted as physical-effect proof.
No elapsed time or worker-identity claim becomes independently attested here.
"""
    require(type(files) is dict and 1 <= len(files) <= 8192, 'ARCHIVE_LIMIT')
    require(all(type(k) is str and len(k) <= 256 and re.fullmatch(r'[a-zA-Z0-9_.\-/]+', k) and
        all(part not in ('', '.', '..') for part in k.split('/')) and type(v) is bytes and len(v) <= 16*1024*1024
        for k, v in files.items()), 'ARCHIVE_SHAPE')
    require(sum(map(len, files.values())) <= CEILINGS['maxDerivedBytes'], 'ARCHIVE_LIMIT')
    files = dict(files); used = set(); documents = {}
    def load(name, reference=None):
        require(name in files and 0 < len(files[name]) <= 65536, 'DOCUMENT')
        raw = files[name]
        if reference is not None:
            closed(reference, ('path', 'bytes', 'sha256'), 'REFERENCE')
            integer(reference['bytes'], 1, 65536, 'REFERENCE')
            require(reference['bytes'] == len(raw) and reference['sha256'] == hashlib.sha256(raw).hexdigest(), 'REFERENCE')
        if name not in documents:
            value = parse_json(raw); strict(value)
            require(canonical(value) == raw, 'CANONICAL')
            documents[name] = value
        used.add(name)
        return documents[name]
    closed(expected_inputs, INPUTS, 'SETUP_INPUTS')
    expected_inputs = {k: snapshot(v) for k, v in expected_inputs.items()}
    require(type(expected_cases) is list and 1 <= len(expected_cases) <= 32, 'SETUP_CASES')
    expected_cases = [snapshot(v) for v in expected_cases]
    matrix = expected_inputs['matrix']; limits = matrix['limits']
    require(matrix['profile'] == 'hms.pat.io-combined-matrix/0.3', 'MATRIX_PROFILE')
    closed(limits, CEILINGS, 'LIMITS')
    for key, high in CEILINGS.items(): integer(limits[key], 1, high, 'LIMITS')
    cases = matrix['cases']
    require(type(cases) is list and len(cases) == len(expected_cases) <= limits['maxCases'], 'CASE_INVENTORY')
    ids = [c['caseId'] for c in cases]
    require(len(set(ids)) == len(ids) and [e['expected_case'] for e in expected_cases] == cases, 'CASE_INVENTORY')
    fixed = [c['definition']['scenario'] for c in cases if c['kind'] == 'fixed_challenge']
    require(len(fixed) == 24 and set(fixed) == TIMING | CLOCK | LIFECYCLE | AUTHORITY and
        sum(c['kind'] == 'resource_challenge' for c in cases) == 1 and
        any(c['kind'] == 'candidate' for c in cases), 'REQUIRED_CHALLENGES')
    matrix_digest = digest(b'HMS-PAT-IO-COMBINED-MATRIX-v0.1', matrix)
    result = load('result.json')
    closed(result, ('profile', 'status', 'matrixDigest', 'artifactDigest', 'identities', 'inputs', 'cases', 'error',
        'accounting', 'allMatrixCasesCaptured', 'requiredMatrixCoverageChecked', 'independentOutcomeChecked',
        'configurationAttested', 'implementationIdentityAttested', 'serializedEvidenceBudgetEnforced',
        'actualAggregateStorageEnforced', 'qualificationPassed', 'physicalMeasurementChecked'), 'RESULT')
    require(result['profile'] == 'hms.pat.io-group-capture/0.1' and result['status'] == 'captured' and
        result['error'] is None and result['allMatrixCasesCaptured'] is True and
        result['serializedEvidenceBudgetEnforced'] is True, 'INCOMPLETE')
    for key in ('requiredMatrixCoverageChecked', 'independentOutcomeChecked', 'configurationAttested',
            'implementationIdentityAttested', 'actualAggregateStorageEnforced', 'qualificationPassed', 'physicalMeasurementChecked'):
        require(result[key] is False, 'PRODUCER_CLAIM')
    require(result['matrixDigest'] == matrix_digest and result['artifactDigest'] == matrix['artifactDigest'] and
        same(result['identities'], expected_inputs['implementation']), 'IDENTITY')
    identity = expected_inputs['implementation']
    require(identity['driverDigest'] == expected_inputs['installation']['driverDigest'] == matrix['driverDigest'] and
        identity['storageProfile'] == 'hms.sqlite.compact/0.1', 'IDENTITY')
    require(type(result['inputs']) is list and [r['path'] for r in result['inputs']] == [k + '.json' for k in INPUTS], 'INPUTS')
    for key, ref in zip(INPUTS, result['inputs']):
        require(same(load(key + '.json', ref), expected_inputs[key]), 'INPUT_ASSOCIATION')
    require(type(result['cases']) is list and [r['caseId'] for r in result['cases']] == ids, 'CASE_INVENTORY')
    manifests = []
    for index, (case, entry) in enumerate(zip(cases, result['cases'])):
        closed(entry, ('caseId', 'kind', 'manifest', 'retainedStateBytes', 'operationCount', 'schedulerTicks'), 'CASE_ENTRY')
        name = 'case-%02d/manifest.json' % index
        require(entry['kind'] == case['kind'] and entry['manifest']['path'] == name, 'CASE_ENTRY')
        manifest = load(name, entry['manifest'])
        require(manifest['caseId'] == case['caseId'] and manifest['qualificationPassed'] is False, 'CASE_MANIFEST')
        manifests.append(manifest)
    programs = {p['digest']: p['artifact'] for p in matrix['programs']}
    require(len(programs) == len(matrix['programs']) and all(
        key == digest(b'HMS-PAT-JCS-SHA256-v0.1', value) for key, value in programs.items()), 'PROGRAM_IDENTITY')
    require(matrix['artifactDigest'] == digest(b'HMS-PAT-JCS-SHA256-v0.1', expected_inputs['candidate']) and
        same(programs[matrix['artifactDigest']], expected_inputs['candidate']), 'PROGRAM_IDENTITY')
    inspections = []; summaries = []; operation_total = tick_total = state_total = 0
    for index, (case, expected, entry, manifest) in enumerate(zip(cases, expected_cases, result['cases'], manifests)):
        prefix = 'case-%02d/' % index; setup = expected['expected_setup']
        require(same(setup['installation'], expected_inputs['installation']), 'SETUP_ASSOCIATION')
        if case['kind'] != 'resource_challenge':
            require(same(setup['artifact'], programs[case['programDigest']]) and
                same(setup['original_descriptor'], expected_inputs['descriptor']), 'SETUP_ASSOCIATION')
        else:
            require(set(expected['expected_actors']) == {'gpio', 'pwm', 'alias', 'independent'}, 'ACTORS')
            for role, actor in expected['expected_actors'].items():
                require(same(actor['artifact'], programs[case['actors'][role]['programDigest']]) and
                    same(actor['original_descriptor'], expected_inputs['bindings'][role]['descriptor']), 'ACTORS')
        executing = case['kind'] != 'candidate' or case['domainCase']['expected']['staticOutcome'] == 'applicable'
        data = None; raw_docs = []; state_bytes = 0
        if executing:
            require(manifest['executionPerformed'] is True and manifest['closed'] is True, 'CASE_CLOSED')
            refs = manifest['records']; cr = manifest['configuration']['records']
            require(type(refs) is list and type(cr) is list and 1 <= len(refs) + len(cr) <= limits['maxRecords'], 'RECORDS')
            record_files = {}; config_files = {}
            for kind, references, output in (('records', refs, record_files), ('configuration', cr, config_files)):
                for n, ref in enumerate(references):
                    require(ref['path'] == '%06d.json' % n, 'REFERENCE_PATH')
                    name = prefix + kind + '/' + ref['path']; doc = load(name, ref); output[ref['path']] = files[name]
                    if kind == 'records':
                        raw_docs.append(doc)
                        if doc['kind'] == 'runtime_opened':
                            _opening(doc['value'], identity['compilerDigest'], case)
            data = dict(references=refs, files=record_files, configuration=manifest['configuration'], configuration_files=config_files)
            board = 'synthetic-io-board-' + hashlib.sha256(setup['installation']['boardId'].encode()).hexdigest() + '.db'
            for filename in ('authority.db', 'authority.db.owner', board, board + '.owner'):
                name = prefix + 'state/' + filename
                require(name in files, 'STATE_INVENTORY')
                raw = files[name]; used.add(name); state_bytes += len(raw)
                require(raw == b'' if filename.endswith('.owner') else len(raw) >= 1024 and len(raw) % 1024 == 0 and
                    raw[:16] == b'SQLite format 3\0' and int.from_bytes(raw[16:18], 'big') == 1024, 'STATE_LAYOUT')
        if case['kind'] == 'candidate':
            inspection, history, outcome = _candidate(manifest, data, expected)
        else:
            name = case['definition']['scenario']
            if case['kind'] == 'resource_challenge':
                require(name == 'shared_resources', 'REQUIRED_CHALLENGES')
                inspector, family = inspect_resource_challenge, 'resource'
            elif name in TIMING: inspector, family = inspect_timing_challenge, 'timing'
            elif name in CLOCK: inspector, family = inspect_clock_challenge, 'clock'
            elif name in LIFECYCLE: inspector, family = inspect_lifecycle_challenge, 'lifecycle'
            elif name in AUTHORITY: inspector, family = inspect_authority_challenge, 'authority'
            else: raise IoGroupHistoryError('REQUIRED_CHALLENGES')
            require(manifest['profile'] == 'hms.pat.io-' + family + '-trial/0.1' and
                manifest['matrixDigest'] == matrix_digest, 'CASE_PROFILE')
            keys = {'profile', 'caseId', 'matrixDigest', 'records', 'configuration', 'report', 'closed',
                'executionPerformed', 'requiredMatrixCoverageChecked', 'independentOutcomeChecked',
                'qualificationPassed', 'actualAggregateStorageEnforced', 'childOperationReservation', 'schedulerTickReservation'}
            if family in {'timing', 'clock', 'lifecycle'}: keys.add('programDigest')
            if family == 'clock': keys.add('clockControls')
            if family == 'lifecycle': keys.add('injectedFaults')
            if family == 'resource': keys.add('operationIds')
            closed(manifest, keys, 'CASE_MANIFEST')
            for flag in ('requiredMatrixCoverageChecked', 'independentOutcomeChecked', 'actualAggregateStorageEnforced'):
                require(manifest[flag] is False, 'PRODUCER_CLAIM')
            if 'programDigest' in manifest: require(manifest['programDigest'] == case['programDigest'], 'PROGRAM_IDENTITY')
            if family == 'clock':
                require(same(manifest['clockControls'], [d['value'] for d in raw_docs if d['kind'] == 'clock_control']), 'CLOCK_CONTROLS')
            require(manifest['childOperationReservation'] == case['plannedChildOperations'] and
                manifest['schedulerTickReservation'] == case['schedulerTickCeiling'], 'CASE_RESERVATION')
            integer(manifest['childOperationReservation'], 0, limits['maxChildOperations'], 'CASE_RESERVATION')
            integer(manifest['schedulerTickReservation'], 0, limits['maxSchedulerTicks'], 'CASE_RESERVATION')
            inspection = inspector(**data, **expected)
            full = inspection['trial'] if family == 'timing' else inspection
            history, outcome = full['history'], full['outcome']
            require(inspection['expectedResponseVerified'] is True and inspection['independentOutcomeChecked'] is True, 'CASE_OUTCOME')
        ops = ticks = 0
        if executing:
            ops = history['operations']['operationsChecked']
            ticks = sum(d['kind'] == 'call_started' and d['value']['label'].startswith('drive:') for d in raw_docs)
            report = manifest['report']
            require(raw_docs[-1]['kind'] == 'trial_observation' and same(raw_docs[-1]['value'], report), 'REPORT')
            ids_seen = {t['operationId'] for t in history['operations']['transitions']}
            require(len(ids_seen) == ops == len(report['operationIds']) and set(report['operationIds']) == ids_seen and
                report['unresolvedOperations'] == [] and report['schedulerTicks'] == ticks, 'REPORT_ACCOUNTING')
            integer(report['schedulerTicks'], 0, limits['maxSchedulerTicks'], 'REPORT_ACCOUNTING')
            require(outcome['settledAndQuiescent'] is True and outcome['unresolvedOperationIds'] == [], 'UNRESOLVED')
            if case['kind'] == 'fixed_challenge' and case['definition']['scenario'] in LIFECYCLE:
                faults = manifest['injectedFaults']
                require(type(faults) is list and all(type(f) is dict and 'operationId' in f and f['operationId'] in ids_seen for f in faults), 'FAULTS')
                require(same([{k: v for k, v in f.items() if k != 'operationId'} for f in faults], expected['expected_faults']), 'FAULTS')
            if case['kind'] == 'resource_challenge':
                closed(manifest['operationIds'], ('gpio', 'pwm', 'alias', 'independent'), 'ACTOR_OPERATIONS')
                require(len(set(manifest['operationIds'].values())) == 4 and set(manifest['operationIds'].values()) == ids_seen, 'ACTOR_OPERATIONS')
                final = [d['value'] for d in raw_docs if d['kind'] == 'checkpoint'][-1]
                table = next(t for t in final['tables'] if t['table'] == 'replay_keys')
                keys = []
                for ref in table['pages']:
                    page = documents[prefix + 'records/' + ref['path']]['value']
                    keys += [dict(zip(page['columns'], [cell['value'] for cell in row])) for row in page['rows']]
                require(manifest['operationIds'] == {role: next(row['operation_id'] for row in keys
                    if row['caller_key'] == 'trial:actor:' + role) for role in manifest['operationIds']}, 'ACTOR_OPERATIONS')
        for field, value in (('operationCount', ops), ('schedulerTicks', ticks), ('retainedStateBytes', state_bytes)):
            integer(entry[field], 0, CEILINGS['maxDerivedBytes'], 'CASE_ACCOUNTING')
            require(entry[field] == value, 'CASE_ACCOUNTING')
        require(ops <= case['plannedChildOperations'] and ticks <= case['schedulerTickCeiling'], 'CASE_LIMIT')
        operation_total += ops; tick_total += ticks; state_total += state_bytes
        encoded = canonical(inspection)
        inspections.append(inspection)
        summaries.append(dict(caseId=case['caseId'], kind=case['kind'], inspectionProfile=inspection['profile'],
            inspectionSha256=hashlib.sha256(encoded).hexdigest(), inspectionBytes=len(encoded),
            operationCount=ops, schedulerTicks=ticks, expectedResponseVerified=True))
    require(used == set(files), 'ARCHIVE_CLOSURE')
    require(all(len(files[name]) <= limits['maxDocumentBytes'] for name in documents), 'DOCUMENT_LIMIT')
    record_count = len(documents)
    producer_bytes = 65536 + sum(len(files[name]) for name in documents if name != 'result.json')
    charged = dict(actualChildOperations=operation_total, completedCases=len(cases), derivedBytes=producer_bytes + state_total,
        observedStateBytes=state_total, producerBytes=producer_bytes, records=record_count,
        reservedChildOperations=sum(c['plannedChildOperations'] for c in cases), schedulerTicks=tick_total)
    require(same(result['accounting'], dict(profile='hms.pat.io-group-budget/0.1', limits=limits, charged=charged,
        nextCase=len(cases), activeCaseId=None, stopped=False, terminal=False, terminalBytesReserved=65536,
        hardAggregateFilesystemQuota=False)), 'GROUP_ACCOUNTING')
    for key, limit in (('actualChildOperations', 'maxChildOperations'), ('reservedChildOperations', 'maxChildOperations'),
            ('schedulerTicks', 'maxSchedulerTicks'), ('records', 'maxRecords'), ('producerBytes', 'maxProducerBytes'),
            ('derivedBytes', 'maxDerivedBytes')):
        require(charged[key] <= limits[limit], 'GROUP_LIMIT')
    inspection_bytes = sum(len(canonical(value)) for value in inspections)
    require(record_count + len(inspections) + 1 <= limits['maxRecords'], 'INSPECTION_LIMIT')
    summary = dict(profile='hms.pat.io-group-history-inspection/0.1', matrixDigest=matrix_digest,
        artifactDigest=matrix['artifactDigest'], cases=summaries, accounting=charged, inspectionBytes=inspection_bytes,
        inspectionRecords=len(inspections) + 1,
        requiredMatrixCoverageChecked=True, independentOutcomeChecked=True, archiveAccountingChecked=True,
        trustedSetupMatched=True, implementationIdentityMatched=True, configurationAttested=False,
        implementationIdentityAttested=False, runAssociationAttested=False, wallDeadlineAttested=False,
        actualAggregateStorageEnforced=False, physicalMeasurementChecked=False, qualificationPassed=False)
    encoded_summary = canonical(summary)
    require(len(encoded_summary) <= limits['maxDocumentBytes'] and
        charged['derivedBytes'] + inspection_bytes + len(encoded_summary) <= limits['maxDerivedBytes'], 'INSPECTION_LIMIT')
    return dict(summary=summary, inspections=inspections)


def inspect_io_group(files, *, expected_inputs, expected_cases):
    """Inspect the complete bounded archive against separately trusted setup."""
    try:
        return _inspect_io_group(files, expected_inputs=expected_inputs, expected_cases=expected_cases)
    except IoGroupHistoryError:
        raise
    except (KeyError, TypeError, IndexError, UnicodeError, RecursionError, StopIteration, ValueError) as error:
        raise IoGroupHistoryError('REJECTED') from error
