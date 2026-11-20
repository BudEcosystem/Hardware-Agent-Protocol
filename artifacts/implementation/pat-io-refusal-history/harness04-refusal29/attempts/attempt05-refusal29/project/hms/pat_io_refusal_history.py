"""Derive pre-effect permission refusals and compose complete retained histories.

This finite simulation profile requires separately trusted grants and retains
read authority. It does not promote PATs or establish a physical outcome.
"""
from __future__ import annotations

from .contracts import canonical, parse_json
from .pat_io_authorized_history import _guards
from .pat_io_board_history import _reduce as _board, _tables
from .pat_io_configuration_history import _validated_configuration_history
from .pat_io_correspondence import _inspect as _correspondence
from .pat_io_observation_history import _samples
from .pat_io_operation_history import _fold as _operations
from .pat_io_procedure_history import _fold as _procedures
from .pat_io_recovery_history import BOARD_TABLES, _faults, _interruptions


class IoRefusalHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_REFUSAL_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoRefusalHistoryError(code)


def _one(rows, code):
    require(len(rows) == 1, code)
    return rows[0]


def _parent_can_dispatch(tables, operation, now):
    parent = _one(tables['pr_procedures'], 'PARENT_CONTEXT')
    step = _one([s for s in tables['pr_steps'] if s['operation_id'] == operation], 'PARENT_CONTEXT')
    require(step['procedure_id'] == parent['id'] and step['ordinal'] == parent['cursor'], 'PARENT_CONTEXT')
    timing = parse_json(parent['request'])['procedure']['timing']
    if parent['state'] not in {'accepted', 'running'} or parent['cancel_requested'] or not (
            timing['notBeforeUnixMs'] <= now < timing['latestCompletionUnixMs']):
        return False
    operations = {row['id']: row for row in tables['operations']}
    held = {row['operation_id'] for row in tables['claims']}
    for previous in tables['pr_steps']:
        if previous['ordinal'] >= step['ordinal']: continue
        child = operations.get(previous['operation_id'])
        if child is None or child['state'] != 'completed' or child['verification'] != 'unverified' or child['id'] in held:
            return False
    return True


def _refusals(transcript, snapshots, permissions):
    """Return private fold handoffs derived from already validated context."""
    calls = {c['phase']: c for c in transcript['calls']}
    frames = {s['checkpoint']['record']: s for s in snapshots}
    plans = [(i, r['value']['request']) for i, r in enumerate(transcript['records']) if r['kind'] == 'compiled_plan']
    before = {}; parent_refusals = {}; dispatch_refusals = {}; checked = []
    for cp in transcript['checkpoints']:
        value = cp['value']; phase, label, now = value['phase'], value['label'], value['wallMs']
        if label.endswith(':before'):
            before[phase] = cp
            continue
        if not label.endswith((':after', ':after_error')): continue
        prior = before.pop(phase); old = _tables(transcript, prior); current = _tables(transcript, cp)
        call = calls[phase]; permission = permissions[prior['record']]
        require(permission == permissions[cp['record']], 'IN_PHASE_PERMISSION_CHANGE')
        if call['label'] == 'submit' and not call['returned']:
            require(not permission['invokes'] and permission['read'], 'PERMISSION_CONTEXT')
            require(call['outcome']['exception'] == 'JournalError' and call['outcome']['code'] == 'ACCESS_DENIED', 'PARENT_CAUSE')
            plan = _one([p for i, p in plans if i < prior['record']], 'PLAN')
            namespace = _one([n for n in old['namespaces'] if n['token'] == plan['replayNamespace']], 'NAMESPACE')
            series = _one(old['series'], 'NAMESPACE')
            require(namespace['epoch'] >= series['floor'] and now < namespace['expires_ms'], 'NAMESPACE_PRECEDENCE')
            timing = plan['procedure']['timing']
            require(now < timing['latestStartUnixMs'] and timing['latestCompletionUnixMs'] <= namespace['expires_ms'], 'PARENT_TIME_PRECEDENCE')
            require(not old['pr_procedures'] and not old['pr_keys'] and not old['replay_keys'], 'PARENT_REPLAY_UNSUPPORTED')
            require(current == old, 'PARENT_REFUSAL_MUTATED_STATE')
            parent_refusals[cp['record']] = 'ACCESS_DENIED'
            checked.append(dict(phase=phase, kind='parent_before_acceptance', code='ACCESS_DENIED'))
        if call['label'] not in {'drive:adapters', 'drive:cycle'}: continue
        old_ops = {row['id']: row for row in old['operations']}
        new_ops = {row['id']: row for row in current['operations']}
        reported = {op for op, row in new_ops.items() if row['state'] == 'rejected_before_dispatch' and
                    (op not in old_ops or old_ops[op]['state'] != 'rejected_before_dispatch')}
        derived = set()
        for op, row in old_ops.items():
            if row['state'] != 'accepted' or permission['invokes']: continue
            require(permission['read'], 'READ_WITHDRAWAL_UNSUPPORTED')
            intent = parse_json(row['intent']); admission = parse_json(row['admission']); timing = intent['timing']
            if not (timing['notBeforeUnixMs'] <= now < timing['latestStartUnixMs'] and now < admission['lease_expires_ms']):
                require(op not in reported, 'TIMING_PRECEDENCE')
                continue
            if not _parent_can_dispatch(old, op, now):
                require(op not in reported, 'PARENT_PRECEDENCE')
                continue
            claims = [r for r in old['claims'] if r['operation_id'] == op]
            require(sorted(r['resource'] for r in claims) == admission['resources'] and
                    row['attempt_id'] is None and row['may_have_acted'] == 0, 'PRE_DISPATCH_OWNERSHIP')
            frame = frames[cp['record']]
            presence = _one([r for r in frame['tables']['reg_presence'] if r['instance'] == intent['instanceId']], 'LIVE_CONTEXT')
            require(intent['endpointSession'] == frame['value']['session'] == presence['session'] and
                    now < presence['expires_ms'], 'LIVE_CONTEXT')
            require(call['returned'] and call['outcome']['result'] is None, 'DISPATCH_CALL')
            require(op in new_ops and new_ops[op]['state'] == 'rejected_before_dispatch', 'REFUSAL_REQUIRED')
            require(all(current[k] == old[k] for k in BOARD_TABLES), 'REFUSAL_BOARD_EFFECT')
            require(new_ops[op]['attempt_id'] is None and new_ops[op]['may_have_acted'] == 0 and
                    all(r['operation_id'] != op for r in current['claims']) and
                    all(r['operation'] != op for r in current['io_dispatch_links']), 'REFUSAL_EFFECT')
            dispatch_refusals[cp['record'], op] = 'ACCESS_DENIED'; derived.add(op)
            checked.append(dict(phase=phase, kind='child_before_dispatch', operationId=op, code='ACCESS_DENIED'))
        require(reported == derived, 'UNEXPLAINED_DISPATCH_REFUSAL')
    require(not before, 'PHASE_PAIRING')
    return parent_refusals, dispatch_refusals, checked


def inspect_refusal_history(references, files, configuration, configuration_files, *,
                            expected_setup, expected_authority, expected_faults=None):
    """Join trusted refusal causes, sampling, board, operation and parent history.

Caller-supplied fold verdicts are not accepted. Standalone fold APIs continue to
refuse permission causes; only the private, fully consumed handoffs enable them.
"""
    transcript, snapshots, permissions, denied, config = _validated_configuration_history(
        references, files, configuration, configuration_files,
        expected_setup=expected_setup, expected_authority=expected_authority)
    correspondence = _correspondence(transcript, expected_setup)
    recovery = None; faults = []; settlements = []
    if expected_faults is not None:
        recovery, faults, settlements = _interruptions(transcript, _faults(expected_faults))
    parents, children, refusals = _refusals(transcript, snapshots, permissions)
    causes, guards = _guards(transcript, snapshots, permissions, denied, recovery=recovery)
    board = _board(transcript, expected_setup, checked_causes=causes)
    operations = _operations(transcript, expected_setup, checked_refusals=children)
    procedures = _procedures(transcript, checked_refusals=parents)
    result = dict(profile='hms.pat.io-refusal-history-inspection/0.1',
        trustedGrantPlanMatched=True, configurationHistoryChecked=True, patCorrespondenceChecked=True,
        permissionRefusalCausesChecked=True, observationSampleSemanticsChecked=True,
        boardHistoryChecked=True, operationHistoryChecked=True, procedureHistoryChecked=True,
        refusalsChecked=refusals, guardsChecked=guards, trustedFaultPlanMatched=expected_faults is not None,
        faultsChecked=faults, settlementsChecked=settlements, configuration=config, correspondence=correspondence,
        board=board, operations=operations, procedures=procedures, sampling=_samples(transcript, snapshots),
        configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
        staticTimingPolicyChecked=False, allFaultScenariosChecked=False, independentOutcomeChecked=False, qualificationPassed=False)
    canonical(result)
    return result
