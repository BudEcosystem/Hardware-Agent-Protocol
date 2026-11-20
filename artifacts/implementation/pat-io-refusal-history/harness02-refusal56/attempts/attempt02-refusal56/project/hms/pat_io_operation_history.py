"""Pure operation-ledger fold for the finite, single-actor I/O trial profile.

This checks durable authority history, not authorization, parent control flow,
PAT lowering, board effects, physical outcomes or qualification.
"""
from __future__ import annotations

import re

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, intent_digest, parse_invoke, parse_json
from .pat_io_board_history import IoHistoryError, _Model, _tables, digest
from .pat_io_transcript import IoTranscriptError, ORIGIN, _read
from .resource_topology import ResourceTopologyError


class IoOperationHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_OPERATION_' + code
        super().__init__(self.code)


def require(value, code):
    if not value:
        raise IoOperationHistoryError(code)


def closed(value, keys, code):
    require(type(value) is dict and set(value) == set(keys), code)


def integer(value, low=0):
    require(type(value) is int and low <= value <= SAFE_INTEGER, 'INTEGER')
    return value


def uuid(value, prefix=''):
    require(type(value) is str and re.fullmatch(re.escape(prefix) + '[0-9a-f]{32}', value) is not None, 'IDENTITY')


TERMINAL = {'completed', 'failed', 'canceled', 'rejected_before_dispatch', 'rejected_before_start'}
EDGES = {'dispatching': {'running', 'completed', 'failed', 'canceled', 'rejected_before_start'},
         'running': {'completed', 'failed', 'canceled'},
         'outcome_unknown': {'running', 'completed', 'failed', 'canceled', 'rejected_before_start'}}
DRIVE = {f'drive:{part}:{end}' for part in ('cycle', 'adapters') for end in ('after', 'after_error')}
ADMIT = {f'drive:{part}:{end}' for part in ('cycle', 'procedure') for end in ('after', 'after_error')}
IMMUTABLE = ('id', 'principal', 'deployment', 'digest', 'intent', 'admission')
DERIVED = ('state', 'cancel_state', 'verification', 'may_have_acted', 'sequence', 'attempt_id', 'owner_epoch')


def _plan(request, model):
    closed(request, {'protocol', 'replayNamespace', 'procedureKey', 'procedure'}, 'PLAN')
    require(request['protocol'] == 'hms.procedure/0.1', 'PLAN')
    identifier(request['replayNamespace']); identifier(request['procedureKey'])
    document = request['procedure']
    closed(document, {'profile', 'timing', 'steps'}, 'PLAN')
    require(document['profile'] == 'hms.bound-sequence/0.1', 'PLAN')
    timing = document['timing']
    closed(timing, {'notBeforeUnixMs', 'latestStartUnixMs', 'latestCompletionUnixMs'}, 'PLAN')
    require(integer(timing['notBeforeUnixMs']) <= integer(timing['latestStartUnixMs']) <= integer(timing['latestCompletionUnixMs']), 'PLAN')
    require(type(document['steps']) is list and 1 <= len(document['steps']) <= 16, 'PLAN')
    ids, keys = set(), {request['procedureKey']}
    for ordinal, step in enumerate(document['steps']):
        closed(step, {'stepId', 'request'}, 'PLAN')
        identifier(step['stepId'])
        child = parse_invoke(canonical(step['request']))
        require(step['stepId'] not in ids and child['operationKey'] not in keys and
                child['replayNamespace'] == request['replayNamespace'], 'PLAN')
        ids.add(step['stepId']); keys.add(child['operationKey'])
        model.intent(child['intent'])
        window = child['intent']['timing']
        require(window['notBeforeUnixMs'] >= timing['notBeforeUnixMs'] and
                window['latestCompletionUnixMs'] <= timing['latestCompletionUnixMs'] and
                (ordinal != 0 or window['latestStartUnixMs'] <= timing['latestStartUnixMs']), 'PLAN')
    return digest(b'HMS-PROCEDURE-JCS-SHA256-v0.1', request)


def _structure(t, request, model, namespace, previous_parent, previous_steps, label):
    require(t['pr_meta'] == [{'key': 'version', 'value': 'hms.bound-sequence/0.1'}], 'PROCEDURE_META')
    parents = t['pr_procedures']
    require(len(parents) <= 1 and (previous_parent is None or bool(parents)), 'PARENT_CHANGED')
    if not parents:
        require(not t['pr_steps'] and not t['pr_keys'] and not t['operations'] and not t['pr_events'], 'STEP_INVENTORY')
        return None, {}, []
    require(request is not None and namespace is not None, 'PLAN')
    parent = parents[0]; uuid(parent['id'], 'procedure:')
    request_digest = _plan(request, model)
    require(parent['principal'] == 'pat-io-trial-worker' and parent['deployment'] == model.deployment and
            parent['request'] == canonical(request) and parent['digest'] == request_digest and
            request['replayNamespace'] == namespace['token'], 'PARENT_IDENTITY')
    identity = tuple(parent[k] for k in ('id', 'principal', 'deployment', 'digest', 'request'))
    require(previous_parent is None or identity == previous_parent, 'PARENT_CHANGED')
    if previous_parent is None:
        require(label in {'submit:after', 'submit:after_error'}, 'PARENT_PHASE')
    children = request['procedure']['steps']
    rows = sorted(t['pr_steps'], key=lambda r: r['ordinal'])
    require(len(rows) == len(children), 'STEP_INVENTORY')
    expected_keys = {(namespace['token'], request['procedureKey'], parent['id'], None)}
    associations, immutable, expected_replay = [], {}, set()
    gap = False
    for ordinal, (row, child) in enumerate(zip(rows, children)):
        req = child['request']
        require((row['procedure_id'], row['ordinal'], row['step_id'], row['request'], row['digest']) ==
                (parent['id'], ordinal, child['stepId'], canonical(req), intent_digest(req['intent'])), 'STEP_REQUEST')
        expected_keys.add((namespace['token'], req['operationKey'], parent['id'], child['stepId']))
        op = row['operation_id']
        if op is None:
            gap = True
        else:
            require(not gap and op not in [a[0] for a in associations], 'STEP_LINK')
            associations.append((op, req['intent']))
            expected_replay.add((namespace['token'], req['operationKey'], op))
        immutable[ordinal] = op
        require(previous_steps.get(ordinal) is None or previous_steps[ordinal] == op, 'STEP_LINK')
    require({tuple(r[k] for k in ('namespace', 'caller_key', 'procedure_id', 'step_id')) for r in t['pr_keys']} == expected_keys,
            'RESERVATIONS')
    require({tuple(r[k] for k in ('namespace', 'caller_key', 'operation_id')) for r in t['replay_keys']} == expected_replay,
            'REPLAY')
    require({r['id'] for r in t['operations']} == {a[0] for a in associations}, 'STEP_LINK')
    return identity, immutable, associations


def _evidence(value, assertion, op, claims, link, t, model):
    closed(value, {'kind', 'source', 'reference', 'assertions'}, 'EVIDENCE')
    require(value['kind'] == 'simulation' and value['source'] == model.routes[op['intent_value']['instanceId']] and
            value['assertions'] == [assertion] and type(value['reference']) is str, 'EVIDENCE')
    sha = 'sha256:' + value['reference'].removeprefix('io-receipt:')
    require(value['reference'].startswith('io-receipt:'), 'EVIDENCE')
    matches = [r for r in t['io_authority_receipts'] if r['operation'] == op['id'] and r['digest'] == sha]
    require(len(matches) == 1 and link is not None, 'EVIDENCE_REFERENCE')
    row = matches[0]; receipt = parse_json(row['document'])
    versions = [r for r in t['io_receipt_versions'] if (r['operation'], r['sequence']) == (op['id'], row['sequence'])]
    require(len(versions) == 1 and versions[0]['document'] == row['document'] and versions[0]['digest'] == sha and
            sha == digest(b'HMS-SYNTHETIC-IO-RECEIPT-v1', receipt), 'EVIDENCE_REFERENCE')
    require(receipt['operationId'] == op['id'] and receipt['digest'] == op['digest'] and
            canonical(receipt['intent']) == op['intent'] and canonical(receipt['claims']) == canonical(claims) and
            type(receipt['sequence']) is int and receipt['sequence'] == row['sequence'] and receipt['profile'] == 'hms.synthetic-io-receipt/1' and
            receipt['boardId'] == model.installation['boardId'] and
            receipt['providerSession'] == op['intent_value']['endpointSession'] and
            all(canonical(receipt[k]) == canonical(link[k]) for k in ('adapterId', 'authorityId', 'ownerEpoch', 'clockEpoch',
                'installationDigest', 'budgetOriginMonoMs')), 'EVIDENCE_IDENTITY')
    result, state = receipt['result'], receipt['state']
    closed(result, {'activationCommitted', 'cycleCompleted', 'reason', 'safeIdle'}, 'EVIDENCE_RESULT')
    # Exact boolean/state correspondence; board transition causes and resource
    # values are independently checked by the separate board-history component.
    if state == 'pending':
        require(result == {'activationCommitted': True, 'cycleCompleted': False, 'reason': None, 'safeIdle': False}, 'EVIDENCE_RESULT')
        allowed = {'running'}
    elif state == 'completed':
        require(result == {'activationCommitted': True, 'cycleCompleted': True, 'reason': None, 'safeIdle': True}, 'EVIDENCE_RESULT')
        allowed = {'completed', 'resources_quiescent'}
    elif state == 'canceled':
        require(result['activationCommitted'] is True and result['cycleCompleted'] is False and result['safeIdle'] is True and
                type(result['reason']) is str and bool(result['reason']), 'EVIDENCE_RESULT')
        allowed = {'resources_quiescent', 'terminated' if result['reason'] in {'client_cancel', 'board_owner_reopened'} else 'failed'}
    else:
        raise IoOperationHistoryError('NO_START_UNIMPLEMENTED')
    require(all(type(result[k]) is bool for k in ('activationCommitted', 'cycleCompleted', 'safeIdle')) and assertion in allowed,
            'EVIDENCE_ASSERTION')


def _fold(transcript, setup, *, checked_refusals=None):
    checked_refusals = {} if checked_refusals is None else checked_refusals
    consumed_refusals = set()
    model = _Model(setup)
    openings = [(i, d['value']) for i, d in enumerate(transcript['records']) if d['kind'] == 'runtime_opened']
    plans = [(i, d['value']['request']) for i, d in enumerate(transcript['records']) if d['kind'] == 'compiled_plan']
    namespace = parent = None
    previous_steps, states, identities, event_history, floors, held = {}, {}, {}, {}, {}, {}
    previous_links, previous_receipts, transitions = {}, {}, []
    last_clock = ORIGIN
    for cp in transcript['checkpoints']:
        now, label = cp['value']['wallMs'], cp['value']['label']
        opened = next(value for pos, value in reversed(openings) if pos < cp['record'])
        t = _tables(transcript, cp)
        meta = {r['key']: r['value'] for r in t['meta']}
        require(set(meta) == {'version', 'authority', 'owner_epoch', 'last_clock'} and
                meta['version'] == 'hms-ledger/0.1' and meta['authority'] == opened['authorityId'] and
                meta['owner_epoch'] == str(opened['ownerEpoch']), 'META')
        require(re.fullmatch('0|[1-9][0-9]*', meta['last_clock']) is not None, 'CLOCK')
        stamp = int(meta['last_clock'])
        require(last_clock <= stamp <= now, 'CLOCK'); last_clock = stamp
        namespaces = t['namespaces']
        require(len(namespaces) <= 1 and (namespace is None or namespaces == [namespace]), 'NAMESPACE_CHANGED')
        if namespaces:
            ns = namespaces[0]
            expiry = ORIGIN + setup['artifact']['timingBudget']['latestCompletionOffsetMs'] + 1
            require(ns['principal'] == 'pat-io-trial-worker' and ns['deployment'] == model.deployment and
                    ns['epoch'] == 1 and ns['expires_ms'] == expiry, 'NAMESPACE')
            uuid(ns['token'], 'replay:' + opened['authorityId'] + ':1:')
            if namespace is None:
                require(label in {'lower:after', 'lower:after_error'} and now < expiry, 'NAMESPACE_PHASE')
            namespace = ns
            expected_series = [{'principal': ns['principal'], 'deployment': ns['deployment'], 'next_epoch': 2,
                                'floor': 1, 'last_expiry': expiry}]
        else:
            expected_series = []
        require(t['series'] == expected_series, 'SERIES')
        request = next((value for pos, value in reversed(plans) if pos < cp['record']), None)
        parent, previous_steps, associations = _structure(t, request, model, namespace, parent, previous_steps, label)
        if parent is None:
            require(not t['replay_keys'], 'REPLAY')
        operations = {r['id']: r for r in t['operations']}
        require(set(identities) <= set(operations), 'OPERATION_CHANGED')
        require(sum(op not in states for op in operations) <= 1, 'ADMISSION_BATCH')
        links = {r['operation']: r for r in t['io_dispatch_links']}
        receipts = {(r['operation'], r['sequence']): r for r in t['io_authority_receipts']}
        require(all(links.get(k) == v for k, v in previous_links.items()), 'LINK_CHANGED')
        require(all(receipts.get(k) == v for k, v in previous_receipts.items()), 'RECEIPT_CHANGED')
        require(set(links) <= set(operations) and all(k[0] in links for k in receipts), 'LINK_INVENTORY')
        events = {(r['operation_id'], r['sequence']): r for r in t['events']}
        require(all(events.get(k) == v for k, v in event_history.items()), 'EVENT_CHANGED')
        require(all(k[0] in operations for k in events), 'EVENT_INVENTORY')
        if label == 'after_reopen':
            for op_id, old in states.items():
                if old['state'] in {'dispatching', 'running'}:
                    require(events.get((op_id, old['sequence'] + 1), {}).get('kind') == 'recovery_unknown', 'RECOVERY')
        for op_id, intended in associations:
            raw = operations[op_id]; uuid(op_id, 'op:')
            identity = tuple(raw[k] for k in IMMUTABLE)
            require(op_id not in identities or identity == identities[op_id], 'OPERATION_CHANGED')
            identities[op_id] = identity
            op = raw | {'intent_value': parse_json(raw['intent']), 'admission_value': parse_json(raw['admission'])}
            detail, _ = model.intent(op['intent_value'])
            require(raw['principal'] == 'pat-io-trial-worker' and raw['deployment'] == model.deployment and
                    raw['intent'] == canonical(intended) and raw['digest'] == intent_digest(intended), 'OPERATION_IDENTITY')
            admission, timing = op['admission_value'], intended['timing']
            closed(admission, {'resources', 'lease_expires_ms', 'policy_revision'}, 'ADMISSION')
            require(admission['resources'] == detail['claims'] and type(admission['policy_revision']) is str and
                    re.fullmatch('registry:[1-9][0-9]*', admission['policy_revision']) is not None, 'ADMISSION')
            integer(admission['lease_expires_ms'])
            seq = integer(raw['sequence'], 1)
            require(seq <= 1024, 'EVENT_SEQUENCE')
            rows = sorted((e for e in t['events'] if e['operation_id'] == op_id), key=lambda e: e['sequence'])
            require([r['sequence'] for r in rows] == list(range(1, seq + 1)), 'EVENT_SEQUENCE')
            st = states.get(op_id)
            for event in rows:
                key = (op_id, event['sequence'])
                if key in event_history:
                    continue
                kind, data = event['kind'], parse_json(event['payload'])
                require(event['time_ms'] == now and event['clock_status'] == 'unqualified_host_clock' and now <= stamp, 'EVENT_CLOCK')
                if st is None:
                    require(kind == 'accepted' and event['sequence'] == 1 and label in ADMIT, 'ADMISSION_PHASE')
                    require(data == {'digest': raw['digest']} and now < timing['latestStartUnixMs'] and namespace is not None and
                            now < namespace['expires_ms'] and admission['lease_expires_ms'] == min(now + 60000, timing['latestCompletionUnixMs']) and
                            now < admission['lease_expires_ms'] and intended['endpointSession'] == opened['session'], 'ADMISSION')
                    allocated = []
                    for atom in detail['claims']:
                        require(atom not in held, 'RESOURCE_BUSY')
                        floors[atom] = floors.get(atom, 0) + 1; integer(floors[atom], 1)
                        held[atom] = (op_id, floors[atom]); allocated.append({'resource': atom, 'fence': floors[atom]})
                    st = {'state': 'accepted', 'cancel_state': 'not_requested', 'verification': 'unverified',
                          'may_have_acted': 0, 'sequence': 1, 'attempt_id': None, 'owner_epoch': opened['ownerEpoch'],
                          'claims': allocated, 'held': True, 'link': None}
                    states[op_id] = st
                else:
                    require(event['sequence'] == st['sequence'] + 1, 'EVENT_SEQUENCE')
                    state = st['state']
                    if kind == 'dispatch_claimed':
                        closed(data, {'attemptId', 'ownerEpoch'}, 'DISPATCH')
                        uuid(data['attemptId'])
                        require(state == 'accepted' and st['held'] and label in DRIVE and
                                data['ownerEpoch'] == opened['ownerEpoch'] and intended['endpointSession'] == opened['session'] and
                                timing['notBeforeUnixMs'] <= now < timing['latestStartUnixMs'] and now < admission['lease_expires_ms'], 'DISPATCH')
                        require(op_id in links, 'DISPATCH_LINK')
                        row = links[op_id]; link = parse_json(row['document'])
                        expected = {'profile': 'hms.synthetic-io-dispatch/1', 'operationId': op_id, 'digest': raw['digest'],
                            'intent': intended, 'claims': st['claims'], 'adapterId': model.routes[intended['instanceId']],
                            'authorityId': opened['authorityId'], 'attemptId': data['attemptId'], 'ownerEpoch': opened['ownerEpoch'],
                            'checkpoint': now, 'budgetOriginMonoMs': now, 'clockEpoch': cp['value']['clockEpoch'],
                            'installationDigest': model.installation_digest}
                        require(canonical(link) == canonical(expected) and row['digest'] == digest(b'HMS-SYNTHETIC-IO-DISPATCH-v1', expected), 'DISPATCH_LINK')
                        st.update(state='dispatching', may_have_acted=1, attempt_id=data['attemptId'], owner_epoch=opened['ownerEpoch'], link=link)
                    elif kind in {'execution_evidence', 'reconciled'}:
                        closed(data, {'state', 'evidence'}, 'TRANSITION')
                        target = data['state']
                        require(label in DRIVE and target in EDGES.get(state, set()) and
                                ((state == 'outcome_unknown') == (kind == 'reconciled')), 'TRANSITION')
                        assertion = {'running': 'running', 'completed': 'completed', 'failed': 'failed',
                                     'canceled': 'terminated', 'rejected_before_start': 'start_excluded'}[target]
                        _evidence(data['evidence'], assertion, op, st['claims'], st['link'], t, model)
                        st.update(state=target, owner_epoch=opened['ownerEpoch'])
                        if target == 'canceled': st['cancel_state'] = 'confirmed'
                    elif kind == 'resources_released':
                        closed(data, {'evidence'}, 'RELEASE')
                        require(state in TERMINAL and st['held'] and label in DRIVE, 'RELEASE')
                        _evidence(data['evidence'], 'resources_quiescent', op, st['claims'], st['link'], t, model)
                        st['held'] = False
                    elif kind in {'outcome_unknown', 'recovery_unknown'}:
                        allowed = {'owner_reopened'} if kind == 'recovery_unknown' else {'io_acceptance_unknown', 'io_completion_unknown'}
                        require(state in {'dispatching', 'running'} and set(data) == {'reason'} and data['reason'] in allowed and
                                (label == 'after_reopen' and st['owner_epoch'] < opened['ownerEpoch'] if kind == 'recovery_unknown' else label in DRIVE), 'UNKNOWN')
                        st['state'] = 'outcome_unknown'
                    elif kind == 'cancel_requested':
                        require(state not in TERMINAL | {'accepted'} and st['cancel_state'] == 'not_requested' and data == {} and
                                label in {'cancel:after', 'cancel:after_error'}, 'CANCEL')
                        st['cancel_state'] = 'requested'
                    elif kind == 'canceled_before_dispatch':
                        require(state == 'accepted' and data == {'proof': 'exclusive_accepted_state'} and
                                label in {'cancel:after', 'cancel:after_error'}, 'CANCEL')
                        st.update(state='canceled', cancel_state='confirmed', held=False)
                    elif kind == 'rejected_before_dispatch':
                        refusal_key = (cp['record'], op_id)
                        if refusal_key in checked_refusals:
                            require(checked_refusals[refusal_key] == 'ACCESS_DENIED' and state == 'accepted' and
                                    st['held'] and st['attempt_id'] is None and label in DRIVE and
                                    data == {'reason': 'ACCESS_DENIED'} and
                                    timing['notBeforeUnixMs'] <= now < timing['latestStartUnixMs'] and
                                    now < admission['lease_expires_ms'], 'PREDISPATCH_CAUSE')
                            consumed_refusals.add(refusal_key)
                        else:
                            require(state == 'accepted' and label in DRIVE and data == {'reason': 'start_or_lease_expired'} and
                                    (now >= timing['latestStartUnixMs'] or now >= admission['lease_expires_ms']), 'PREDISPATCH_CAUSE')
                        st.update(state='rejected_before_dispatch', held=False)
                    else:
                        raise IoOperationHistoryError('EVENT_UNSUPPORTED')
                    st['sequence'] = event['sequence']
                    if not st['held']:
                        for atom in detail['claims']:
                            require(held.get(atom) == (op_id, next(c['fence'] for c in st['claims'] if c['resource'] == atom)), 'RELEASE')
                            del held[atom]
                event_history[key] = event
                transitions.append({'operationId': op_id, 'sequence': event['sequence'], 'kind': kind, 'clock': now,
                                    'state': st['state'], 'claimsHeld': len(st['claims']) if st['held'] else 0})
            require(tuple(raw[k] for k in DERIVED) == tuple(st[k] for k in DERIVED), 'STATE')
            for receipt in t['io_authority_receipts']:
                if receipt['operation'] == op_id:
                    value = parse_json(receipt['document'])
                    assertion = 'running' if value['state'] == 'pending' else 'completed' if value['state'] == 'completed' else 'resources_quiescent'
                    _evidence({'kind': 'simulation', 'source': model.routes[intended['instanceId']],
                               'reference': 'io-receipt:' + receipt['digest'].removeprefix('sha256:'), 'assertions': [assertion]},
                              assertion, op, st['claims'], st['link'], t, model)
        require(set(links) == {op for op, st in states.items() if st['link'] is not None}, 'LINK_INVENTORY')
        require(len({st['attempt_id'] for st in states.values() if st['attempt_id'] is not None}) == len(links), 'DISPATCH')
        require({(r['deployment'], r['resource'], r['fence']) for r in t['resource_floors']} ==
                {(model.deployment, atom, fence) for atom, fence in floors.items()}, 'FLOORS')
        require({(r['deployment'], r['resource'], r['operation_id'], r['fence']) for r in t['claims']} ==
                {(model.deployment, atom, op, fence) for atom, (op, fence) in held.items()}, 'CLAIMS')
        previous_links, previous_receipts = links, receipts
    require(consumed_refusals == set(checked_refusals), 'UNUSED_REFUSAL')
    return {'profile': 'hms.pat.io-operation-history-inspection/0.1', 'operationHistoryChecked': True,
            'checkpointsChecked': len(transcript['checkpoints']), 'operationsChecked': len(states),
            'eventsChecked': len(event_history), 'transitions': transitions,
            'unresolvedOperationIds': sorted(op for op, st in states.items() if st['held'] or st['state'] not in TERMINAL),
            'heldClaims': len(held), 'resourceFloors': [{'resource': a, 'fence': f} for a, f in sorted(floors.items())],
            'boardHistoryChecked': False, 'procedureSemanticsChecked': False, 'liveAuthorizationChecked': False,
            'patCorrespondenceChecked': False, 'independentOutcomeChecked': False, 'qualificationPassed': False}


def inspect_operation_history(references, files, *, expected_setup):
    """Fold acquired data without importing or calling the runtime/provider."""
    try:
        result = _fold(_read(references, files, expected_setup), expected_setup)
        canonical(result)
        return result
    except (IoOperationHistoryError, IoTranscriptError):
        raise
    except (IoHistoryError, ContractError, ResourceTopologyError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
        raise IoOperationHistoryError('SHAPE') from error
