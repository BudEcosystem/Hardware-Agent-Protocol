"""STAGING: immutable evidence reduction/storage, not an installed PAT service.

Import/acquisition may read files. Eligibility reads only a supplied SQLite
transaction, with a FUTURE authorizer permitting built-in typeof and length.
The current live catalog forbids those functions, so this is not mountable yet.
Historical producer identities are explicit trusted pins, never current-code
attestation. Imports of the copied compiler read source/schema identity files;
exported reduction/verification calls perform no filesystem or Runtime I/O.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path

from hms.contracts import canonical, parse_json, intent_digest, ContractError
from hms.journal import JournalError
from hms.pat_contracts import PatError, pat_digest, name
from hms.pat_compiler import compile_pat, evaluation_environment, compiler_digest
from hms.pat_simulation_contracts import (POLICY, generate_cases, matrix_digest,
    qualify_fan_contract, decode_case_input)
from hms.api_contracts import validate_result

PROFILE = 'hms.pat.sqlite-fan-evidence-group/0.1'
CASE_PROFILE = 'hms.pat.sqlite-fan-evidence-case/0.1'
TRUST_PROFILE = 'hms.pat.sqlite-fan-evidence-trust/0.1'
WORKER_INPUT = 'hms.pat.sqlite-fan-worker-input/0.1'
WORKER_RESULT = 'hms.pat.sqlite-fan-worker-result/0.1'
RECORD_PROFILE = 'hms.pat.sqlite-fan-evidence/0.1'
FAULTS = ('cancel_accepted', 'cancel_running', 'reopen_accepted',
          'reopen_pending', 'completion_evidence_loss')
CHECKS = tuple(('fan:' + category, category) for category in ('positive', 'boundary', 'negative', 'fault'))
MAX_DOCUMENT = 65536
MAX_RECORDS = 4096
MAX_GROUP_DOCUMENTS = MAX_RECORDS + 34  # records + result + <=32 cases + manifest
MAX_GROUP_BYTES = 20 * 1024 * 1024      # producer output AND every derived document
MAX_STORE_BYTES = 64 * 1024 * 1024
MAX_STORE_DOCUMENTS = 16384
LIMITATIONS = [
    'Finite boundary trials are not exhaustive or physical objective verification.',
    'Replay/conflict and SQL floor/key checks without emitted raw rows remain assertions of the pinned producer.',
    'Historical source and service-supplied run binding are trusted inputs, not worker authentication or current qualification.',
    'No supervisor, attempt admission, process lifecycle, current configuration or filesystem quota is implemented here.'
]


class EvidenceError(JournalError):
    pass


def require(condition, code='PAT_EVIDENCE_INVALID'):
    if not condition:
        raise EvidenceError(code)


def exact(value, fields):
    require(type(value) is dict and set(value) == set(fields))


def integer(value, lo=0, hi=2**53 - 1):
    require(type(value) is int and lo <= value <= hi)
    return value


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def digest(body):
    require(type(body) is bytes and 0 < len(body) <= MAX_DOCUMENT)
    return 'sha256:' + hashlib.sha256(body).hexdigest()


def hash_document(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _sha(value):
    require(type(value) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', value) is not None)
    return value


def document(body):
    require(type(body) is bytes and 0 < len(body) <= MAX_DOCUMENT)
    try:
        result = parse_json(body)
        require(canonical(result) == body)
        return result
    except (ContractError, ValueError, TypeError, RecursionError) as error:
        raise EvidenceError('PAT_EVIDENCE_INVALID') from error


def _validated(function):
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except EvidenceError:
            raise
        except (ContractError, PatError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
            raise EvidenceError('PAT_EVIDENCE_INVALID') from error
    return checked


@_validated
def trusted_binding(value):
    """Detach explicit setup pins; supplying this JSON does not authenticate it."""
    # Canonicalization after type-sensitive checks avoids converting float 1.0.
    exact(value, {'profile', 'deployment', 'runId', 'evaluator', 'input'})
    require(value['profile'] == TRUST_PROFILE)
    for key in ('deployment', 'runId'):
        name(value[key], 'PAT_EVIDENCE_INVALID')
    evaluator = value['evaluator']
    exact(evaluator, {'evaluatorId', 'implementationDigest', 'policyDigest', 'requiredChecks', 'evidenceProfile'})
    name(evaluator['evaluatorId'], 'PAT_EVIDENCE_INVALID')
    _sha(evaluator['implementationDigest']); _sha(evaluator['policyDigest'])
    require(evaluator['evidenceProfile'] == PROFILE and same(evaluator['requiredChecks'],
        [{'id': key, 'category': category} for key, category in CHECKS]))
    cap = value['input']
    exact(cap, {'profile', 'policy', 'attemptId', 'configuration', 'identities', 'runtimeLayout',
        'artifact', 'installation', 'bindings', 'evaluationEnvironment', 'environmentDigest',
        'caseMatrix', 'matrixDigest', 'limits'})
    require(cap['profile'] == WORKER_INPUT and cap['policy'] == POLICY)
    name(cap['attemptId'], 'PAT_EVIDENCE_INVALID')
    exact(cap['configuration'], {'revision', 'digest'})
    integer(cap['configuration']['revision'], 1); _sha(cap['configuration']['digest'])
    exact(cap['identities'], {'compilerDigest', 'workerDigest', 'driverDigest', 'policyDigest'})
    for identity in cap['identities'].values():
        _sha(identity)
    require(cap['identities']['compilerDigest'] == compiler_digest(), 'PAT_EVIDENCE_VALIDATOR_CHANGED')
    require(cap['evaluationEnvironment']['deployment'] == value['deployment'])
    require(cap['runtimeLayout'] in ('legacy', 'multi') and cap['installation']['driver'] == 'sqlite-simulation')
    require(type(cap['bindings']) is dict and len(cap['bindings']) == 1)
    role, descriptor = next(iter(cap['bindings'].items()))
    contract = qualify_fan_contract(cap['artifact'], descriptor)
    require(role == contract['role'] and descriptor['driverDigest'] == cap['identities']['driverDigest'])
    require(descriptor['binding']['instanceId'] == cap['installation']['instances']['fan'])
    env = evaluation_environment(cap['artifact'], cap['bindings'], deployment=value['deployment'])
    require(same(env['evaluationEnvironment'], cap['evaluationEnvironment']) and
            env['environmentDigest'] == cap['environmentDigest'])
    require(same(generate_cases(cap['artifact'], descriptor, limits=cap['limits']), cap['caseMatrix']) and
            matrix_digest(cap['artifact'], descriptor, limits=cap['limits']) == cap['matrixDigest'])
    require(len(cap['caseMatrix']['cases']) + 5 <= cap['limits']['maxCases'])
    require(cap['caseMatrix']['plannedChildOperations'] + 2 * len(cap['artifact']['steps']) + 3 <= cap['limits']['maxChildOperations'])
    # Trusted capsule bytes must already preserve exact scalar types.
    detached = document(canonical(value))
    require(same(value, detached))
    return detached


def _read_file(directory_fd, name, remaining):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                0 < info.st_size <= min(MAX_DOCUMENT, remaining), 'PAT_EVIDENCE_READ_BOUND')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            body = stream.read(info.st_size + 1)
        require(len(body) == info.st_size, 'PAT_EVIDENCE_CHANGED')
        return body
    finally:
        os.close(fd)


def read_retained_attempt(trusted_directory):
    """Acquisition only, never called by eligibility. Scratch DBs are diagnostic.

    Root directory ancestry is trusted setup. O_NOFOLLOW protects the selected
    root, evidence directory and final files; fixed names prevent traversal.
    """
    root = os.open(trusted_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    evidence = None
    try:
        result = _read_file(root, 'test-return.json', MAX_DOCUMENT)
        evidence = os.open('evidence', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        # Iterate with a hard item cap instead of materializing an unbounded list.
        names = []
        with os.scandir(evidence) as entries:
            for entry in entries:
                require(len(names) < MAX_RECORDS, 'PAT_EVIDENCE_READ_BOUND')
                require(re.fullmatch(r'[0-9]{6}\.json', entry.name) is not None)
                names.append(entry.name)
        require(sorted(names) == ['%06d.json' % i for i in range(len(names))])
        files, remaining = [], 16 * 1024 * 1024
        for item in sorted(names):
            body = _read_file(evidence, item, remaining)
            remaining -= len(body)
            files.append({'path': 'evidence/' + item, 'body': body})
        return {'result': result, 'files': files}
    finally:
        if evidence is not None:
            os.close(evidence)
        os.close(root)


def _reference(value):
    exact(value, {'path', 'bytes', 'sha256', 'kind'})
    require(type(value['path']) is str and re.fullmatch(r'evidence/[0-9]{6}\.json', value['path']) is not None)
    integer(value['bytes'], 1, MAX_DOCUMENT)
    _sha('sha256:' + value['sha256'])
    require(type(value['kind']) is str)


def _records(result, files):
    require(type(files) is list and 1 <= len(files) <= MAX_RECORDS)
    mapping = {}
    for index, item in enumerate(files):
        exact(item, {'path', 'body'})
        require(item['path'] == 'evidence/%06d.json' % index)
        mapping[item['path']] = item['body']
    require(len(files) == result['evidenceRecordCount'])
    require(sum(len(item['body']) for item in files) == result['outputBytes'])
    pages, refs = result['evidencePages'], []
    require(type(pages) is list and 1 <= len(pages) <= 41)
    def verify(ref):
        _reference(ref)
        body = mapping[ref['path']]
        require(len(body) == ref['bytes'] and digest(body) == 'sha256:' + ref['sha256'])
        row = document(body)
        exact(row, {'profile', 'kind', 'value'})
        require(row['profile'] == RECORD_PROFILE and row['kind'] == ref['kind'])
        return row
    for page in pages:
        row = verify(page)
        require(row['kind'] == 'evidence_index')
        exact(row['value'], {'first', 'records'})
        require(type(row['value']['first']) is int and row['value']['first'] == len(refs))
        require(type(row['value']['records']) is list and 1 <= len(row['value']['records']) <= 100)
        refs.extend(row['value']['records'])
    require(len(refs) + len(pages) == len(files))
    require([r['path'] for r in [*refs, *pages]] == [item['path'] for item in files])
    rows = [verify(ref) for ref in refs]
    require(all(row['kind'] != 'evidence_index' for row in rows))
    return rows, refs


def _plants(value, expected_instances):
    require(type(value) is dict and set(value) == set(expected_instances))
    for state in value.values():
        exact(state, {'effectCount', 'value', 'ready'})
        integer(state['effectCount']); require(type(state['ready']) is bool)
        # All three current original simulation devices expose integral values.
        integer(state['value'])


def _one(rows, kind):
    found = [r['value'] for r in rows if r['kind'] == kind]
    require(len(found) == 1)
    return found[0]


def _events(rows, kind, identity, head):
    pages = [r['value']['page'] for r in rows if r['kind'] == kind and
             (kind == 'procedure_events' or r['value']['operationId'] == identity)]
    require(bool(pages))
    seq, events, last_time = 0, [], -1
    for page in pages:
        keys = {'events', 'gap', 'head', 'next'}
        if kind == 'procedure_events':
            keys |= {'protocol', 'procedureId'}
            require(page['protocol'] == 'hms.procedure-events/0.1' and page['procedureId'] == identity)
        exact(page, keys)
        require(page['gap'] is False and type(page['head']) is int and page['head'] == head)
        require(type(page['events']) is list and 1 <= len(page['events']) <= 100)
        for event in page['events']:
            idfield = 'procedure_id' if kind == 'procedure_events' else 'operation_id'
            exact(event, {'clock_status', 'kind', idfield, 'payload', 'sequence', 'time_ms'})
            seq += 1
            require(event[idfield] == identity and type(event['sequence']) is int and event['sequence'] == seq)
            integer(event['time_ms'], last_time if last_time >= 0 else 0)
            last_time = event['time_ms']
            require(event['clock_status'] == 'unqualified_host_clock')
            require(type(event['kind']) is str and type(event['payload']) is dict)
            events.append(event)
        require(type(page['next']) is int and page['next'] == seq)
    require(seq == head)
    return events


def _check_checkpoint(cp, operations, request, cap, baseline):
    exact(cp, {'trial', 'label', 'clock', 'plants', 'claims', 'receiptCount', 'procedure'})
    integer(cp['clock'], 1000000)
    _plants(cp['plants'], baseline)
    integer(cp['receiptCount'], 0, len(operations))
    require(type(cp['claims']) is list and len(cp['claims']) <= 16)
    if request is None:
        require(not operations and cp['procedure'] is None and not cp['claims'] and cp['receiptCount'] == 0)
        require(same(cp['plants'], baseline))
        return
    status = cp['procedure']
    validate_result('procedure_submit', status, {'request': request})
    require(cp['receiptCount'] == sum(row['receipt'] is not None for row in operations))
    expected_claims = []
    resource = cap['installation']['resources']['fan']
    for index, row in enumerate(operations):
        op, receipt = row['operation'], row['receipt']
        exact(row, {'trial', 'label', 'operation', 'receipt'})
        exact(op, {'admission', 'attempt_id', 'cancel_state', 'claims', 'deployment', 'digest', 'id',
            'intent', 'may_have_acted', 'owner_epoch', 'principal', 'sequence', 'state', 'verification'})
        exact(op['admission'], {'lease_expires_ms', 'policy_revision', 'resources'})
        integer(op['admission']['lease_expires_ms']); integer(op['sequence'], 1)
        integer(op['owner_epoch'], 1); require(type(op['may_have_acted']) is bool)
        intended = request['procedure']['steps'][index]['request']['intent']
        require(same(op['intent'], intended) and op['digest'] == intent_digest(intended))
        require(op['deployment'] == cap['evaluationEnvironment']['deployment'] and op['principal'] == 'pat-simulation-worker')
        require(op['admission']['resources'] == [resource])
        step = status['steps'][index]
        require(step['operationId'] == op['id'] and step['executionState'] == op['state'] and
                step['eventSequence'] == op['sequence'] and step['cancellationState'] == op['cancel_state'] and
                step['mayHaveActed'] is op['may_have_acted'] and step['effectVerification'] == op['verification'] and
                step['heldResources'] == len(op['claims']))
        for claim in op['claims']:
            exact(claim, {'resource', 'fence'})
            require(same(claim, {'resource': resource, 'fence': index + 1}))
            expected_claims.append({'deployment': op['deployment'], 'operation_id': op['id'], **claim})
        if receipt is not None:
            exact(receipt, {'id', 'digest', 'intent', 'claims', 'state', 'result'})
            require(receipt['id'] == op['id'] and receipt['digest'] == op['digest'] and same(receipt['intent'], intended))
            require(same(receipt['claims'], [{'resource': resource, 'fence': index + 1}]))
            if receipt['state'] == 'completed':
                require(same(receipt['result'], {'effectCommitted': True, 'level': intended['arguments']['level'], 'unit': 'percent'}))
            elif receipt['state'] == 'canceled':
                require(type(receipt['result']) is dict and receipt['result'].get('effectCommitted') is False)
                require(set(receipt['result']) <= {'effectCommitted', 'reason', 'startExcluded'})
                require(type(receipt['result'].get('reason')) is str)
            else:
                require(receipt['state'] == 'pending' and receipt['result'] is None)
    require([s['operationId'] for s in status['steps']] ==
            [row['operation']['id'] for row in operations] + [None] * (len(status['steps']) - len(operations)))
    require(same(sorted(cp['claims'], key=lambda x: x['operation_id']), sorted(expected_claims, key=lambda x: x['operation_id'])))
    # Every checkpoint carries emitted committed receipts, including completion
    # evidence lost before host settlement. Attribute effects from those receipts.
    committed = [row for row in operations if row['receipt'] and row['receipt']['state'] == 'completed']
    fan = cap['installation']['instances']['fan']
    target = committed[-1]['operation']['intent']['arguments']['level'] if committed else baseline[fan]['value']
    require(cp['plants'][fan]['value'] == target and
            cp['plants'][fan]['effectCount'] - baseline[fan]['effectCount'] == len(committed) and
            cp['plants'][fan]['ready'] is baseline[fan]['ready'])
    require(all(same(cp['plants'][key], before) for key, before in baseline.items() if key != fan))


def _trial(cap, trial, case, rows, refs):
    fault = case if type(case) is str else None
    case_id = 'lifecycle:' + fault if fault else case['caseId']
    expected = {'staticOutcome': 'applicable'} if fault else case['expected']
    allowed = {'trial_started', 'compiled_request', 'checkpoint', 'operation', 'operation_events', 'procedure_events', 'trial_result'}
    require(all(row['kind'] in allowed and type(row['value']['trial']) is int and row['value']['trial'] == trial for row in rows))
    require(rows[0]['kind'] == 'trial_started' and rows[-1]['kind'] == 'trial_result')
    start, result = _one(rows, 'trial_started'), _one(rows, 'trial_result')
    exact(start, {'trial', 'caseId', 'baseline', 'originalDependencies', 'workerDependencies', 'environmentDigest'})
    exact(result, {'trial', 'caseId', 'passed', 'events'})
    require(start['caseId'] == result['caseId'] == case_id and result['passed'] is True)
    baseline = start['baseline']; _plants(baseline, cap['installation']['instances'].values())
    role, descriptor = next(iter(cap['bindings'].items()))
    original = evaluation_environment(cap['artifact'], cap['bindings'], deployment=cap['evaluationEnvironment']['deployment'])
    require(same(start['originalDependencies'], original['dependencies']) and start['environmentDigest'] == cap['environmentDigest'])
    require(type(start['workerDependencies']) is list and len(start['workerDependencies']) == 1)
    session = start['workerDependencies'][0]['endpointSession']
    name(session, 'PAT_EVIDENCE_INVALID')
    worker_bindings = copy.deepcopy(cap['bindings']); worker_bindings[role]['endpointSession'] = session
    worker = evaluation_environment(cap['artifact'], worker_bindings, deployment=cap['evaluationEnvironment']['deployment'])
    require(same(start['workerDependencies'], worker['dependencies']))
    inputs = decode_case_input(case['input']) if not fault else {
        'parameters': qualify_fan_contract(cap['artifact'], descriptor)['nominalParameters'],
        'taskKind': cap['artifact']['taskKind'], 'inputProfile': cap['artifact']['inputProfile'], 'evidenceMode': 'simulation'}
    plans = [r['value'] for r in rows if r['kind'] == 'compiled_request']
    if expected['staticOutcome'] == 'applicable':
        require(len(plans) == 1); exact(plans[0], {'trial', 'plan'})
        request = plans[0]['plan']['request']
        ns = request['replayNamespace']
    else:
        require(not plans); request = None; ns = 'negative:validation'
    try:
        plan = compile_pat(cap['artifact'], inputs['parameters'], worker_bindings, origin_ms=1000000,
            replay_namespace=ns, procedure_key='trial:%d:parent' % trial,
            operation_keys={step['stepId']: 'trial:%d:step:%d' % (trial, i) for i, step in enumerate(cap['artifact']['steps'])},
            caller_deadline_ms=1000000 + cap['artifact']['timingBudget']['latestCompletionOffsetMs'],
            context={k: inputs[k] for k in ('taskKind', 'inputProfile', 'evidenceMode')} | {'deployment': cap['evaluationEnvironment']['deployment']})
    except PatError as error:
        wanted = 'PAT_NOT_APPLICABLE' if expected['staticOutcome'] == 'not_applicable' else expected.get('errorCode')
        require(request is None and error.code == wanted)
        require(same(result['events'], [{'event': 'static_refusal', 'code': wanted}]))
    else:
        require(request is not None and same(plans[0]['plan'], plan))
    checkpoints = [r['value'] for r in rows if r['kind'] == 'checkpoint']
    labels = ['negative_refusal'] if request is None else (
        ['before_reopen', 'after_reopen', 'final'] if fault in FAULTS[2:] else ['final'])
    require([cp['label'] for cp in checkpoints] == labels)
    all_ops = [r['value'] for r in rows if r['kind'] == 'operation']
    require(all(row['label'] in labels for row in all_ops))
    snapshots = {}
    for cp in checkpoints:
        ops = [row for row in all_ops if row['label'] == cp['label']]
        require(len(ops) <= len(cap['artifact']['steps']) and len({row['operation']['id'] for row in ops}) == len(ops))
        _check_checkpoint(cp, ops, request, cap, baseline)
        snapshots[cp['label']] = (cp, ops)
    final, ops = snapshots[labels[-1]]
    if request is None:
        require(not any(r['kind'] in {'operation_events', 'procedure_events'} for r in rows))
        return {'profile': CASE_PROFILE, 'trial': trial, 'caseId': case_id, 'categories': case['categories'],
                'expected': expected, 'observed': {'operationIds': [], 'procedureId': None, 'committedEffects': 0,
                 'finalFanLevel': final['plants'][cap['installation']['instances']['fan']]['value']}, 'records': refs}
    canceled = fault in {'cancel_accepted', 'cancel_running', 'reopen_pending'}
    count = 1 if canceled else len(cap['artifact']['steps'])
    require(len(ops) == count and not final['claims'])
    state = 'canceled' if canceled else 'completed'
    require(final['procedure']['executionState'] == state and not final['procedure']['unresolvedOperations'])
    require(all(row['operation']['state'] == state and not row['operation']['claims'] and
                row['operation']['verification'] not in {'failed', 'disputed'} for row in ops))
    for row in ops:
        op, receipt = row['operation'], row['receipt']
        if receipt is None:
            require(fault == 'cancel_accepted' and op['cancel_state'] == 'confirmed' and op['may_have_acted'] is False)
        else:
            require(receipt['state'] == state)
        if canceled:
            require(op['cancel_state'] == 'confirmed')
    if fault in {'cancel_running', 'reopen_pending'}:
        require(ops[0]['receipt']['result']['reason'] == ('client_cancel' if fault == 'cancel_running' else 'simulator_owner_reopened'))
    procedure_id = final['procedure']['procedureId']
    opids = [row['operation']['id'] for row in ops]
    event_opids = {r['value']['operationId'] for r in rows if r['kind'] == 'operation_events'}
    require(event_opids == set(opids))
    for row in ops:
        op = row['operation']
        events = _events(rows, 'operation_events', op['id'], op['sequence'])
        require(events[0]['kind'] == 'accepted' and events[0]['payload'] == {'digest': op['digest']})
        states = [event['payload'].get('state') for event in events if event['kind'] in {'execution_evidence', 'reconciled'}]
        if state == 'completed':
            require('completed' in states)
        require(not any(event['kind'] in {'evidence_dispute', 'verification_failed'} for event in events))
    pevents = _events(rows, 'procedure_events', procedure_id, final['procedure']['eventSequence'])
    require(pevents[0]['kind'] == 'accepted' and pevents[0]['payload'] == {'requestDigest': plan['requestDigest'], 'stepCount': len(cap['artifact']['steps'])})
    admitted = [event['payload'] for event in pevents if event['kind'] == 'child_admitted']
    require(same(admitted, [{'operationId': row['operation']['id'], 'ordinal': i, 'stepId': request['procedure']['steps'][i]['stepId']} for i, row in enumerate(ops)]))
    log = [{'event': 'submitted', 'procedureId': procedure_id, 'requestDigest': plan['requestDigest']}]
    if not fault:
        log += [{'event': 'exact_replay_and_conflict', 'children': 0}, {'event': 'exact_replay_and_conflict', 'children': count}]
    elif fault in FAULTS[2:]:
        before, bops = snapshots['before_reopen']; after, aops = snapshots['after_reopen']
        require(before['procedure']['procedureId'] == after['procedure']['procedureId'] == procedure_id)
        require(after['procedure']['executionState'] == 'interrupted' and before['clock'] == after['clock'])
        require(len(bops) == len(aops) == 1 and bops[0]['operation']['id'] == aops[0]['operation']['id'] == opids[0])
        require(same(before['plants'], after['plants']))
        if fault == 'reopen_accepted':
            require(bops[0]['operation']['state'] == aops[0]['operation']['state'] == 'accepted' and bops[0]['receipt'] is None and aops[0]['receipt'] is None)
        else:
            require(bops[0]['operation']['state'] == 'running' and aops[0]['operation']['state'] == 'outcome_unknown')
            require(same(bops[0]['receipt'], aops[0]['receipt']))
            require(bops[0]['receipt']['state'] == ('completed' if fault == 'completion_evidence_loss' else 'pending'))
        if fault == 'completion_evidence_loss':
            log += [{'event': 'modeled_completion_evidence_loss', 'operationId': opids[0], 'realProcessCrash': False}]
        log += [{'event': 'owner_reopened', 'clock': before['clock']}]
        if fault != 'reopen_pending':
            log += [{'event': 'exact_replay_and_conflict', 'children': count}]
            require(any(event['kind'] == 'resumed' for event in pevents))
    if fault:
        log += [{'event': fault, 'passed': True}]
    require(same(result['events'], log))
    return {'profile': CASE_PROFILE, 'trial': trial, 'caseId': case_id,
        'categories': ['fault'] if fault else case['categories'], 'expected': expected,
        'observed': {'operationIds': opids, 'procedureId': procedure_id, 'committedEffects': 0 if canceled else count,
            'finalFanLevel': final['plants'][cap['installation']['instances']['fan']]['value']}, 'records': refs}


@_validated
def reduce_attempt(trust, result_bytes, files):
    """Pure validation/reduction of actual canonical records into bounded closure."""
    trust = trusted_binding(trust); cap = trust['input']; result = document(result_bytes)
    exact(result, {'profile', 'attemptId', 'outcome', 'qualificationPassed', 'reason', 'unresolvedEffects',
        'environmentDigest', 'matrixDigest', 'identities', 'configuration', 'plannedCases', 'completedCases',
        'schedulerTicks', 'childOperations', 'outputBytes', 'scratchBytes', 'totalDiskBytes',
        'totalDiskQuotaEnforced', 'evidenceRecordCount', 'evidencePages', 'scope'})
    require(result['profile'] == WORKER_RESULT)
    for key in ('attemptId', 'environmentDigest', 'matrixDigest', 'identities', 'configuration'):
        require(same(result[key], cap[key]))
    require(result['outcome'] == 'passed' and result['qualificationPassed'] is True and result['reason'] is None,
            'PAT_EVIDENCE_NOT_PASSED')
    require(type(result['unresolvedEffects']) is int and result['unresolvedEffects'] == 0)
    cases = [*cap['caseMatrix']['cases'], *FAULTS]
    for key in ('plannedCases', 'completedCases'):
        require(type(result[key]) is int and result[key] == len(cases))
    for key, maximum in [('schedulerTicks', cap['limits']['maxSchedulerTicks']), ('childOperations', cap['limits']['maxChildOperations']),
                         ('outputBytes', cap['limits']['maxOutputBytes']), ('evidenceRecordCount', MAX_RECORDS)]:
        integer(result[key], 1, maximum)
    integer(result['scratchBytes']); integer(result['totalDiskBytes'])
    require(result['totalDiskBytes'] == result['outputBytes'] + result['scratchBytes'] and result['totalDiskQuotaEnforced'] is False)
    require(result['scope'] == 'Finite original SQLite fan trials from fresh synthetic state; no physical objective or live configuration attestation.')
    rows, refs = _records(result, files)
    require(rows[0]['kind'] == 'input' and same(rows[0]['value'], cap))
    require(rows[-1]['kind'] == 'storage_boundaries' and sum(r['kind'] == 'input' for r in rows) == 1)
    groups, group_refs = [[] for _ in cases], [[] for _ in cases]
    prior = 0
    for row, ref in zip(rows[1:-1], refs[1:-1]):
        index = row['value']['trial']; integer(index, 0, len(cases)-1)
        require(index >= prior and index <= prior + 1); prior = index
        groups[index].append(row)
        group_refs[index].append({'path': ref['path'], 'digest': 'sha256:' + ref['sha256']})
    capsules = [_trial(cap, i, case, group, rr) for i, (case, group, rr) in enumerate(zip(cases, groups, group_refs))]
    all_ids = [op for case in capsules for op in case['observed']['operationIds']]
    require(len(set(all_ids)) == len(all_ids) == result['childOperations'])
    categories = {category for case in capsules for category in case['categories']}
    require({'positive', 'boundary', 'negative', 'fault'} <= categories)
    storage = rows[-1]['value']; exact(storage, {'boundaries', 'scratchBytes', 'totalDiskQuotaEnforced'})
    require(storage['scratchBytes'] == result['scratchBytes'] and storage['totalDiskQuotaEnforced'] is False)
    require(type(storage['boundaries']) is list and len(storage['boundaries']) == len(cases))
    cumulative, boundaries, last_scratch = len(files[0]['body']), [], 0
    for index, group in enumerate(groups):
        cumulative += sum(ref['bytes'] for ref in refs if ref['path'] in {r['path'] for r in group_refs[index]})
        boundary = storage['boundaries'][index]
        exact(boundary, {'completedCases', 'evidenceBytes', 'scratchBytes'})
        require(type(boundary['completedCases']) is int and boundary['completedCases'] == index + 1)
        require(type(boundary['evidenceBytes']) is int and boundary['evidenceBytes'] == cumulative)
        integer(boundary['scratchBytes'], last_scratch); last_scratch = boundary['scratchBytes']
    require(last_scratch == result['scratchBytes'])
    docs = {digest(item['body']): item['body'] for item in files}
    require(len(docs) == len(files))
    docs[digest(result_bytes)] = result_bytes
    case_refs = []
    for case in capsules:
        body = canonical(case); key = digest(body); docs[key] = body
        case_refs.append({'caseId': case['caseId'], 'digest': key})
    manifest = {'profile': PROFILE, 'trustDigest': hash_document(b'HMS-PAT-EVIDENCE-TRUST-v0.1', trust),
        'binding': {'deployment': trust['deployment'], 'runId': trust['runId'], 'evaluator': trust['evaluator'],
            'attemptId': cap['attemptId'], 'configuration': cap['configuration'], 'identities': cap['identities'],
            'artifactDigest': pat_digest(cap['artifact']), 'environmentDigest': cap['environmentDigest'], 'matrixDigest': cap['matrixDigest']},
        'inputDigest': digest(files[0]['body']), 'resultDigest': digest(result_bytes),
        'evidencePages': [{'path': ref['path'], 'digest': 'sha256:' + ref['sha256']} for ref in result['evidencePages']],
        'cases': case_refs, 'recordCount': len(files), 'producerBytes': result['outputBytes'],
        'closureDocuments': len(docs) + 1, 'closureBytes': 0, 'limitations': LIMITATIONS}
    # Include manifest's own bytes in the closure quota without a self hash.
    base = sum(map(len, docs.values()))
    for _ in range(8):
        size = base + len(canonical(manifest))
        if manifest['closureBytes'] == size:
            break
        manifest['closureBytes'] = size
    require(manifest['closureBytes'] == base + len(canonical(manifest)))
    body = canonical(manifest); group_digest = digest(body); docs[group_digest] = body
    require(len(docs) <= MAX_GROUP_DOCUMENTS and sum(map(len, docs.values())) <= MAX_GROUP_BYTES, 'PAT_EVIDENCE_CLOSURE_LIMIT')
    return {'profile': PROFILE, 'groupDigest': group_digest, 'documents': docs}


def _evaluation_result(group_digest):
    return {'checks': [{'id': key, 'category': category, 'outcome': 'passed', 'evidenceDigest': group_digest}
                       for key, category in CHECKS], 'unresolvedEffects': 0, 'limitations': LIMITATIONS}


_DDL = (
    'CREATE TABLE se_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
    'CREATE TABLE se_documents (digest TEXT PRIMARY KEY, byte_count INTEGER NOT NULL, body BLOB NOT NULL)',
    'CREATE TABLE se_runs (deployment TEXT NOT NULL, evaluator TEXT NOT NULL, run_id TEXT NOT NULL, group_digest TEXT NOT NULL, PRIMARY KEY(deployment,evaluator,run_id))',
)


class EvidenceStore:
    """Staged one-connection immutable logical retention, not disk accounting.

    Import owns BEGIN IMMEDIATE. Verification requires the authority's existing
    transaction and never installs/replaces its authorizer. The trusted owner
    must not override typeof/length or mutate the connection concurrently.
    Quotas cap retained logical bytes/documents, not SQLite/WAL allocation.
    """
    def __init__(self, connection, trust, *, byte_quota=MAX_STORE_BYTES, document_quota=MAX_STORE_DOCUMENTS):
        self.db = connection; self.trust = trusted_binding(trust)
        self.byte_quota = integer(byte_quota, 1, MAX_STORE_BYTES)
        self.document_quota = integer(document_quota, 1, MAX_STORE_DOCUMENTS)
        require(not self.db.in_transaction, 'PAT_EVIDENCE_TRANSACTION_ACTIVE')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            expected = {'se_meta', 'se_documents', 'se_runs'}
            present = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('se_meta','se_documents','se_runs')")}
            require(not present or present == expected, 'PAT_EVIDENCE_PARTIAL_STORE')
            if not present:
                for statement in _DDL:
                    self.db.execute(statement)
                self.db.execute("INSERT INTO se_meta VALUES ('version', ?)", (PROFILE,))
            version = self.db.execute("SELECT value FROM se_meta WHERE key='version'").fetchone()
            require(version is not None and version[0] == PROFILE, 'PAT_EVIDENCE_STORE_VERSION')
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise

    def _read(self, key, budget):
        _sha(key)
        # typeof first: length(TEXT) can itself load unbounded text, and NUL
        # undercounts it. No caller/row supplied count authorizes fetching bytes.
        row = self.db.execute('SELECT typeof(body), typeof(byte_count) FROM se_documents WHERE digest=?', (key,)).fetchone()
        require(row is not None, 'PAT_EVIDENCE_MISSING')
        require(tuple(row) == ('blob', 'integer'), 'PAT_EVIDENCE_STORAGE_TYPE')
        actual, declared = self.db.execute('SELECT length(body), byte_count FROM se_documents WHERE digest=?', (key,)).fetchone()
        integer(actual, 1, MAX_DOCUMENT); integer(declared, 1, MAX_DOCUMENT)
        require(actual == declared and budget[0] + actual <= MAX_GROUP_BYTES, 'PAT_EVIDENCE_READ_BOUND')
        budget[0] += actual
        body = self.db.execute('SELECT body FROM se_documents WHERE digest=?', (key,)).fetchone()[0]
        require(type(body) is bytes and len(body) == actual and digest(body) == key, 'PAT_EVIDENCE_CHANGED')
        return body

    def _load(self, key):
        require(self.db.in_transaction, 'PAT_EVIDENCE_TRANSACTION_REQUIRED')
        budget, docs = [0], {}
        def read(key):
            _sha(key)
            require(key not in docs, 'PAT_EVIDENCE_DUPLICATE_REFERENCE')
            require(len(docs) < MAX_GROUP_DOCUMENTS, 'PAT_EVIDENCE_READ_BOUND')
            docs[key] = self._read(key, budget)
            return document(docs[key])
        manifest = read(key)
        exact(manifest, {'profile', 'trustDigest', 'binding', 'inputDigest', 'resultDigest', 'evidencePages',
            'cases', 'recordCount', 'producerBytes', 'closureDocuments', 'closureBytes', 'limitations'})
        require(manifest['profile'] == PROFILE and manifest['trustDigest'] == hash_document(b'HMS-PAT-EVIDENCE-TRUST-v0.1', self.trust))
        integer(manifest['closureDocuments'], 1, MAX_GROUP_DOCUMENTS); integer(manifest['closureBytes'], 1, MAX_GROUP_BYTES)
        integer(manifest['recordCount'], 1, MAX_RECORDS)
        result = read(manifest['resultDigest'])
        require(type(manifest['evidencePages']) is list and 1 <= len(manifest['evidencePages']) <= 41)
        files, pages = [], []
        for ref in manifest['evidencePages']:
            exact(ref, {'path', 'digest'})
            page = read(ref['digest']); exact(page, {'profile', 'kind', 'value'})
            require(page['profile'] == RECORD_PROFILE and page['kind'] == 'evidence_index')
            exact(page['value'], {'first', 'records'})
            require(type(page['value']['records']) is list and 1 <= len(page['value']['records']) <= 100)
            for item in page['value']['records']:
                _reference(item)
                raw_key = 'sha256:' + item['sha256']; read(raw_key)
                files.append({'path': item['path'], 'body': docs[raw_key]})
            pages.append({'path': ref['path'], 'body': docs[ref['digest']]})
        files += pages
        require(type(manifest['cases']) is list and 1 <= len(manifest['cases']) <= 32)
        for case in manifest['cases']:
            exact(case, {'caseId', 'digest'}); read(case['digest'])
        rebuilt = reduce_attempt(self.trust, docs[manifest['resultDigest']], files)
        require(rebuilt['groupDigest'] == key and rebuilt['documents'] == docs, 'PAT_EVIDENCE_CLOSURE_MISMATCH')
        require(len(docs) == manifest['closureDocuments'] and budget[0] == manifest['closureBytes'])
        return rebuilt

    @_validated
    def import_bundle(self, bundle):
        exact(bundle, {'profile', 'groupDigest', 'documents'})
        require(bundle['profile'] == PROFILE and type(bundle['documents']) is dict)
        require(1 <= len(bundle['documents']) <= MAX_GROUP_DOCUMENTS)
        docs = dict(bundle['documents']); group = bundle['groupDigest']; _sha(group)
        require(group in docs)
        for key, body in docs.items():
            require(digest(body) == key)
        require(sum(map(len, docs.values())) <= MAX_GROUP_BYTES, 'PAT_EVIDENCE_CLOSURE_LIMIT')
        require(not self.db.in_transaction, 'PAT_EVIDENCE_TRANSACTION_ACTIVE')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            key = (self.trust['deployment'], self.trust['evaluator']['evaluatorId'], self.trust['runId'])
            prior = self.db.execute('SELECT group_digest FROM se_runs WHERE deployment=? AND evaluator=? AND run_id=?', key).fetchone()
            require(prior is None or prior[0] == group, 'PAT_EVIDENCE_RUN_CONFLICT')
            # Import is outside the catalog callback. Count/size validation is
            # bounded by quota+1 and checks actual BLOB type/length before data.
            rows = self.db.execute('SELECT digest, typeof(body), typeof(byte_count) FROM se_documents LIMIT ?',
                                   (self.document_quota + 1,)).fetchall()
            require(len(rows) <= self.document_quota, 'PAT_EVIDENCE_RETENTION_QUOTA')
            total, existing = 0, set()
            for stored, kind, countkind in rows:
                _sha(stored); require(kind == 'blob' and countkind == 'integer')
                size, count = self.db.execute('SELECT length(body), byte_count FROM se_documents WHERE digest=?', (stored,)).fetchone()
                integer(size, 1, MAX_DOCUMENT); require(type(count) is int and count == size)
                total += size; existing.add(stored)
            fresh = set(docs) - existing
            require(len(existing | set(docs)) <= self.document_quota and
                    total + sum(len(docs[k]) for k in fresh) <= self.byte_quota, 'PAT_EVIDENCE_RETENTION_QUOTA')
            for digest_key, body in docs.items():
                if digest_key in existing:
                    require(self._read(digest_key, [0]) == body, 'PAT_EVIDENCE_CONTENT_CONFLICT')
                else:
                    self.db.execute('INSERT INTO se_documents VALUES (?, ?, ?)', (digest_key, len(body), body))
            # Validate inside the same transaction before recording any run link.
            rebuilt = self._load(group)
            require(rebuilt['documents'] == docs, 'PAT_EVIDENCE_CLOSURE_MISMATCH')
            if prior is None:
                self.db.execute('INSERT INTO se_runs VALUES (?, ?, ?, ?)', (*key, group))
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise
        return _evaluation_result(group)

    @_validated
    def verify_evidence(self, context, receipt):
        require(self.db.in_transaction, 'PAT_EVIDENCE_TRANSACTION_REQUIRED')
        require(context.deployment == self.trust['deployment'])
        exact(receipt, {'protocol', 'runId', 'artifactDigest', 'artifactDomainDigest', 'evaluator', 'environment',
            'environmentDigest', 'outcome', 'result', 'evaluatorError', 'physicalObjectiveVerified'})
        cap = self.trust['input']
        require(receipt['protocol'] == 'hms.pat-evaluation/0.1' and receipt['runId'] == self.trust['runId'] and
            receipt['artifactDigest'] == pat_digest(cap['artifact']) and
            receipt['artifactDomainDigest'] == hash_document(b'HMS-PAT-DOMAIN-v0.1', cap['artifact']) and
            same(receipt['evaluator'], self.trust['evaluator']) and same(receipt['environment'], cap['evaluationEnvironment']) and
            receipt['environmentDigest'] == cap['environmentDigest'] and receipt['outcome'] == 'passed' and
            receipt['evaluatorError'] is None and receipt['physicalObjectiveVerified'] is False)
        checks = receipt['result']['checks']; require(type(checks) is list and len(checks) == 4)
        group = _sha(checks[0]['evidenceDigest'])
        require(same(receipt['result'], _evaluation_result(group)))
        row = self.db.execute('SELECT group_digest FROM se_runs WHERE deployment=? AND evaluator=? AND run_id=?',
            (self.trust['deployment'], self.trust['evaluator']['evaluatorId'], self.trust['runId'])).fetchone()
        require(row is not None and row[0] == group, 'PAT_EVIDENCE_RUN_MISSING')
        self._load(group)
        return True
