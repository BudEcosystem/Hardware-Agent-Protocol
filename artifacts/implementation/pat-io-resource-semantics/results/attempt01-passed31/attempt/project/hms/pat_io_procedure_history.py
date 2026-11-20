"""Independent parent-sequence semantics over the finite I/O trial transcript.

Uses the independent operation fold, never the runtime, procedure manager or
provider. This does not independently lower PATs or grant qualification.
"""
from __future__ import annotations

from .contracts import ContractError, canonical, intent_digest, parse_json
from .pat_io_board_history import _tables
from .pat_io_operation_history import IoOperationHistoryError, _fold as _operations
from .pat_io_transcript import IoTranscriptError, _read


class IoProcedureHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_PROCEDURE_' + code
        super().__init__(self.code)


def require(value, code):
    if not value:
        raise IoProcedureHistoryError(code)


ACTIVE = {'accepted', 'running'}
FINAL = {'completed', 'failed', 'canceled', 'expired'}
CHILD_FINAL = {'completed', 'failed', 'canceled', 'rejected_before_dispatch', 'rejected_before_start'}
FIELDS = ('state', 'reason', 'cursor', 'cancel_requested', 'cancel_delivery', 'sequence')


def _child_view(tables):
    counts = {}
    for claim in tables['claims']:
        key = claim['operation_id']; counts[key] = counts.get(key, 0) + 1
    return {row['id']: row | {'claimsHeld': counts.get(row['id'], 0)} for row in tables['operations']}


def _success(op):
    # The prerequisite operation checker restricts every child to simulation /
    # capability_completion with unverified evidence. No physical claim follows.
    return op is not None and op['state'] == 'completed' and op['verification'] == 'unverified' and op['claimsHeld'] == 0


class _Sequence:
    def __init__(self, row, now, namespace_expiry):
        self.id, self.digest = row['id'], row['digest']
        self.request = parse_json(row['request'])
        self.steps = self.request['procedure']['steps']
        self.timing = self.request['procedure']['timing']
        require(now < self.timing['latestStartUnixMs'] and now < namespace_expiry and
                self.timing['latestCompletionUnixMs'] <= namespace_expiry, 'SUBMISSION_TIME')
        self.links = [None] * len(self.steps)
        self.events = []
        self.state, self.reason, self.cursor, self.cancel = 'accepted', None, 0, 0
        self.delivery = {'operationId': None, 'status': 'no_active_child', 'code': None}
        self.event(now, 'accepted', {'requestDigest': self.digest, 'stepCount': len(self.steps)})

    def event(self, now, kind, payload):
        require(len(self.events) < 1024, 'EVENT_LIMIT')
        self.events.append({'procedure_id': self.id, 'sequence': len(self.events) + 1, 'time_ms': now,
                            'clock_status': 'unqualified_host_clock', 'kind': kind, 'payload': canonical(payload)})

    def change(self, now, state, reason):
        if (self.state, self.reason) != (state, reason):
            self.state, self.reason = state, reason
            self.event(now, 'state_changed', {'state': state, 'reason': reason})

    def successful_prefix(self, operations):
        cursor = 0
        while cursor < len(self.links) and _success(operations.get(self.links[cursor])):
            cursor += 1
        return cursor

    def advance(self, now, operations, current, *, after_adapters):
        if self.state not in ACTIVE:
            return
        require(self.cancel == 0, 'CANCELED_ACTIVE')
        prefix = self.successful_prefix(operations)
        require(prefix >= self.cursor, 'PREFIX_REGRESSION')
        if prefix != self.cursor:
            self.cursor = prefix; self.event(now, 'cursor_advanced', {'cursor': prefix})
        if prefix == len(self.links):
            self.change(now, 'completed', None)
            return
        op = operations.get(self.links[prefix])
        if op is not None and op['state'] in CHILD_FINAL - {'completed'}:
            self.change(now, 'failed', 'CHILD_' + op['state'].upper())
            return
        if op is not None and op['state'] == 'outcome_unknown':
            self.change(now, 'interrupted', 'CHILD_OUTCOME_UNKNOWN')
            return
        if now >= self.timing['latestCompletionUnixMs'] or (
                prefix == 0 and op is None and now >= self.timing['latestStartUnixMs']):
            self.change(now, 'expired', 'PROCEDURE_DEADLINE')
            return
        if now < self.timing['notBeforeUnixMs'] or op is not None:
            return
        # The supported profile has one parent and no auxiliary/resource-conflict
        # actor. Policy refusals without retained authority/configuration causes
        # are not silently accepted as a valid missing admission.
        expected = current['pr_steps'][prefix]['operation_id']
        require(expected is not None and expected not in self.links, 'ADMISSION_MISSING')
        child = next((r for r in current['operations'] if r['id'] == expected), None)
        require(child is not None, 'ADMISSION_MISSING')
        if after_adapters:
            require(child['state'] == 'accepted' and child['sequence'] == 1 and child['attempt_id'] is None,
                    'ADMISSION_ORDER')
        self.links[prefix] = expected
        self.state, self.reason = 'running', None
        self.event(now, 'child_admitted', {'stepId': self.steps[prefix]['stepId'], 'ordinal': prefix, 'operationId': expected})

    def cancel_at(self, now, before, after):
        if not self.cancel:
            self.cancel = 1; self.event(now, 'cancel_requested', {})
        if self.state not in FINAL:
            self.change(now, 'canceled', 'CLIENT_CANCEL')
        active = self.links[self.cursor] if self.cursor < len(self.links) else None
        delivery = {'operationId': active, 'status': 'no_active_child', 'code': None}
        if active is not None:
            op = before[active]
            if op['state'] in CHILD_FINAL:
                delivery['status'] = 'already_terminal'
            else:
                # Permission-denied delivery needs separately retained policy
                # attestation. This component supports the actual owner profile.
                expected_cancel = 'confirmed' if op['state'] == 'accepted' else 'requested'
                require(after[active]['cancel_state'] == expected_cancel, 'CANCEL_DELIVERY')
                delivery['status'] = 'recorded'
        if delivery != self.delivery:
            self.delivery = delivery; self.event(now, 'cancel_delivery', delivery)

    def resume_error(self, now, operations, session):
        if self.state != 'interrupted' or self.cancel:
            return 'PROCEDURE_NOT_RESUMABLE'
        if now >= self.timing['latestCompletionUnixMs']:
            return 'PROCEDURE_DEADLINE'
        if any(not _success(operations.get(op)) for op in self.links[:self.cursor]):
            return 'PROCEDURE_DEPENDENCY_UNRESOLVED'
        for i in range(self.cursor, len(self.links)):
            op = operations.get(self.links[i])
            if op is not None and not _success(op) and op['state'] != 'accepted':
                return 'PROCEDURE_DEPENDENCY_UNRESOLVED'
            intent = self.steps[i]['request']['intent']
            if op is None or op['state'] == 'accepted':
                if now >= intent['timing']['latestStartUnixMs'] or (op is not None and now >= parse_json(op['admission'])['lease_expires_ms']):
                    return 'START_DEADLINE'
                if intent['endpointSession'] != session:
                    return 'IO_SESSION_CHANGED'
        return None

    def check(self, t):
        require(len(t['pr_procedures']) == 1, 'PARENT_INVENTORY')
        row = t['pr_procedures'][0]
        expected = (self.state, self.reason, self.cursor, self.cancel, canonical(self.delivery), len(self.events))
        require(tuple(row[k] for k in FIELDS) == expected, 'ROW')
        require([r['operation_id'] for r in t['pr_steps']] == self.links, 'LINKS')
        require(t['pr_events'] == self.events, 'EVENTS')

    def status(self, operations):
        children, unresolved, acted = [], [], False
        for i, (step, op_id) in enumerate(zip(self.steps, self.links)):
            op = operations.get(op_id)
            if op is not None:
                acted = acted or bool(op['may_have_acted'])
                if op['state'] not in CHILD_FINAL or op['claimsHeld']:
                    unresolved.append(op_id)
            children.append({'stepId': step['stepId'], 'ordinal': i,
                'requestDigest': intent_digest(step['request']['intent']), 'operationId': op_id,
                'executionState': op['state'] if op else 'unstarted',
                'cancellationState': op['cancel_state'] if op else 'not_requested',
                'effectVerification': 'unverified', 'mayHaveActed': bool(op['may_have_acted']) if op else False,
                'heldResources': op['claimsHeld'] if op else 0, 'eventSequence': op['sequence'] if op else 0})
        return {'protocol': 'hms.procedure-status/0.1', 'procedureId': self.id, 'requestDigest': self.digest,
                'profile': 'hms.bound-sequence/0.1', 'timing': self.timing, 'executionState': self.state,
                'reason': self.reason, 'cancelRequested': bool(self.cancel), 'cancelBlockedCode': None,
                'cursor': self.cursor, 'stepCount': len(self.steps), 'eventSequence': len(self.events),
                'mayHaveActed': acted, 'aggregateVerification': 'unverified',
                'unresolvedOperations': unresolved, 'steps': children}

    def cancel_result(self):
        return {'protocol': 'hms.procedure-cancel/0.1', 'procedureId': self.id, 'executionState': self.state,
                'cancelRequested': bool(self.cancel), 'cancelBlockedCode': None, 'eventSequence': len(self.events),
                'delivery': self.delivery}


def _fold(transcript, *, checked_refusals=None, checked_conflicts=None):
    checked_refusals = {} if checked_refusals is None else checked_refusals
    checked_conflicts = {} if checked_conflicts is None else checked_conflicts
    consumed_refusals = set()
    consumed_conflicts = set()
    by_phase = {call['phase']: call for call in transcript['calls']}
    checkpoints = {cp['record']: cp for cp in transcript['checkpoints']}
    sequence = None
    previous = current = None
    session = None
    calls_checked = observations_checked = 0
    for index, record in enumerate(transcript['records']):
        if record['kind'] == 'runtime_opened':
            session = record['value']['session']
        if record['kind'] == 'checkpoint':
            cp = checkpoints[index]; current = _tables(transcript, cp)
            # Explicit ordinal order, independent of physical table row order.
            current['pr_steps'].sort(key=lambda r: r['ordinal'])
            now, label = cp['value']['wallMs'], cp['value']['label']
            before = _child_view(previous) if previous is not None else {}
            after = _child_view(current)
            call = None
            if label.endswith(':after') or label.endswith(':after_error'):
                call = by_phase[cp['value']['phase']]
                operation = call['label']
                if operation == 'submit':
                    if not call['returned']:
                        require(index in checked_refusals, 'SUBMIT_FAILURE_UNIMPLEMENTED')
                        require(checked_refusals[index] == 'ACCESS_DENIED' and sequence is None and
                                call['outcome']['exception'] == 'JournalError' and
                                call['outcome']['code'] == 'ACCESS_DENIED' and current == previous,
                                'SUBMIT_REFUSAL')
                        consumed_refusals.add(index)
                    elif sequence is None:
                        require(len(current['pr_procedures']) == 1 and len(current['namespaces']) == 1, 'PARENT_INVENTORY')
                        sequence = _Sequence(current['pr_procedures'][0], now, current['namespaces'][0]['expires_ms'])
                elif operation == 'submit_conflict':
                    require(index in checked_conflicts and checked_conflicts[index] == 'KEY_CONFLICT' and
                            sequence is not None and not call['returned'] and
                            call['outcome']['exception'] == 'JournalError' and call['outcome']['code'] == 'KEY_CONFLICT' and
                            current == previous, 'CONFLICT_CAUSE')
                    consumed_conflicts.add(index)
                elif operation == 'cancel':
                    require(sequence is not None and call['returned'], 'CANCEL_FAILURE_UNIMPLEMENTED')
                    sequence.cancel_at(now, before, after)
                elif operation == 'resume':
                    require(sequence is not None, 'PARENT_INVENTORY')
                    error = sequence.resume_error(now, before, session)
                    if error is None:
                        require(call['returned'], 'RESUME_CAUSE')
                        sequence.change(now, 'running' if any(sequence.links) else 'accepted', None)
                    else:
                        require(not call['returned'] and call['outcome']['exception'] == 'JournalError' and
                                call['outcome']['code'] == error, 'RESUME_CAUSE')
                elif operation in {'drive:cycle', 'drive:procedure'} and sequence is not None:
                    sequence.advance(now, before, current, after_adapters=False)
                    if operation == 'drive:cycle':
                        sequence.advance(now, after, current, after_adapters=True)
                if call['returned']:
                    if operation in {'submit', 'resume'}:
                        require(canonical(call['outcome']['result']) == canonical(sequence.status(after)), 'CALL_PROJECTION')
                        calls_checked += 1
                    elif operation == 'cancel':
                        require(canonical(call['outcome']['result']) == canonical(sequence.cancel_result()), 'CALL_PROJECTION')
                        calls_checked += 1
                    elif operation.startswith('drive:'):
                        require(call['outcome']['result'] is None, 'CALL_PROJECTION')
                        calls_checked += 1
            elif label == 'after_reopen' and sequence is not None and sequence.state in ACTIVE:
                sequence.change(now, 'interrupted', 'OWNER_REOPENED')
            if sequence is None:
                require(not current['pr_procedures'] and not current['pr_events'], 'PARENT_INVENTORY')
            else:
                sequence.check(current)
            previous = current
        elif record['kind'] == 'trial_observation':
            require(current is not None, 'OBSERVATION')
            ops = _child_view(current)
            status = sequence.status(ops) if sequence is not None else None
            identities = [op for op in sequence.links if op is not None] if sequence is not None else []
            unresolved = [op for op in identities if ops[op]['state'] not in CHILD_FINAL or ops[op]['claimsHeld']]
            observation = record['value']
            require(canonical(observation['procedure']) == canonical(status) and observation['operationIds'] == identities and
                    observation['unresolvedOperations'] == unresolved, 'OBSERVATION')
            observations_checked += 1
    require(consumed_refusals == set(checked_refusals), 'UNUSED_REFUSAL')
    require(consumed_conflicts == set(checked_conflicts), 'UNUSED_CONFLICT')
    status = sequence.status(_child_view(current)) if sequence is not None else None
    return {'profile': 'hms.pat.io-procedure-history-inspection/0.1', 'procedureHistoryChecked': True,
            'operationHistoryChecked': True, 'checkpointsChecked': len(checkpoints),
            'procedureEventsChecked': len(sequence.events) if sequence is not None else 0,
            'callProjectionsChecked': calls_checked, 'observationsChecked': observations_checked,
            'derivedProcedure': status, 'boardHistoryChecked': False, 'patCorrespondenceChecked': False,
            'liveAuthorizationChecked': False, 'allFailureCausesChecked': False,
            'independentOutcomeChecked': False, 'qualificationPassed': False}


def inspect_procedure_history(references, files, *, expected_setup):
    """Validate acquired operation/parent histories and exact status projections."""
    try:
        transcript = _read(references, files, expected_setup)
        _operations(transcript, expected_setup)
        result = _fold(transcript)
        canonical(result)
        return result
    except (IoProcedureHistoryError, IoOperationHistoryError, IoTranscriptError):
        raise
    except (ContractError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
        raise IoProcedureHistoryError('SHAPE') from error
