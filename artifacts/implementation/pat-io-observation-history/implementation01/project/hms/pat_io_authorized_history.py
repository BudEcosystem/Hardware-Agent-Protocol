"""Compose independent finite-I/O history checks with trusted permission guards.

This checks retained simulation data, not physical stopping, source attestation,
fault completeness, controller timing qualification or automatic PAT promotion.
No runtime/provider imports, I/O, mutable authority or caller-supplied guard verdict.
"""
from __future__ import annotations

from .contracts import ContractError, canonical, parse_json
from .pat_io_board_history import IoHistoryError, _reduce as _board, _tables
from .pat_io_configuration_history import IoConfigurationError, _validated_configuration_history
from .pat_io_correspondence import IoCorrespondenceError, _inspect as _correspondence
from .pat_io_operation_history import IoOperationHistoryError, _fold as _operations
from .pat_io_procedure_history import IoProcedureHistoryError, _fold as _procedures
from .pat_io_transcript import IoTranscriptError


class IoAuthorizedHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_AUTHORIZED_' + code
        super().__init__(self.code)


def require(condition, code):
    if not condition:
        raise IoAuthorizedHistoryError(code)


def _receipts(tables):
    return {r['operation']:parse_json(r['document']) for r in tables['io_receipts']}


def _guards(transcript, snapshots, permissions, denied, *, recovery=None):
    """Derive each observed adapter phase from its before state and trusted grants.

Unchanged configuration and fresh after-phase observations rule out a substituted
binding/presence failure. Already terminal receipts retain their historical cause.
An unknown outcome with a still-pending receipt needs the separate recovery-stop
profile; this checker refuses it explicitly instead of guessing its stop cause.
"""
    recovery = {} if recovery is None else recovery
    consumed_recovery = set()
    frames = {s['checkpoint']['record']:s for s in snapshots}
    before = {}
    checked_causes = {}
    guards = []
    terminal_receipts = {}
    denied_records = {r for r,_ in denied}
    for cp in transcript['checkpoints']:
        value = cp['value']; phase, label, now = value['phase'],value['label'],value['wallMs']
        current_tables = _tables(transcript,cp)
        for op_id, receipt in _receipts(current_tables).items():
            if op_id in terminal_receipts:
                require(canonical(receipt) == canonical(terminal_receipts[op_id]), 'HISTORICAL_RECEIPT_CHANGED')
            if receipt['state'] != 'pending':
                terminal_receipts[op_id] = receipt
        permission = permissions[cp['record']]
        if cp['record'] in denied_records:
            require(permission['read'], 'READ_WITHDRAWAL_UNSUPPORTED')
        if label in {'drive:adapters:before','drive:cycle:before'}:
            before[phase] = cp
        elif label in {'drive:adapters:after','drive:adapters:after_error','drive:cycle:after','drive:cycle:after_error'}:
            prior = before.pop(phase)
            require(permissions[prior['record']] == permission, 'IN_PHASE_PERMISSION_CHANGE')
            old = _tables(transcript,prior); current = current_tables
            old_receipts, new_receipts = _receipts(old), _receipts(current)
            old_ops = {r['id']:r for r in old['operations']}
            config = frames[cp['record']]['tables']
            presence = {r['instance']:r for r in config['reg_presence']}
            observations = {(r['instance'],r['property']):parse_json(r['document']) for r in config['reg_observations']}
            for op_id, receipt in old_receipts.items():
                require(op_id in new_receipts, 'RECEIPT_MISSING')
                actual = new_receipts[op_id]
                if receipt['state'] != 'pending':
                    require(canonical(actual) == canonical(receipt), 'HISTORICAL_RECEIPT_CHANGED')
                    continue
                operation = old_ops[op_id]
                intent = receipt['intent']; timing = intent['timing']; instance = intent['instanceId']
                require(intent['endpointSession'] == frames[cp['record']]['value']['session'] == presence[instance]['session'] and
                        now < presence[instance]['expires_ms'], 'GUARD_CONTEXT')
                require(all(observations[instance,p]['receipt']['ticksMs'] == now for p in ('ready','value')), 'GUARD_CONTEXT')
                key = (cp['record'],op_id)
                if key in recovery:
                    prior_state, state, reason = recovery[key]
                    require(operation['state'] == prior_state and (prior_state,state,reason) in {
                        ('running','pending',None), ('outcome_unknown','pending',None),
                        ('outcome_unknown','canceled','reconciliation_stop')}, 'RECOVERY_HANDOFF')
                    consumed_recovery.add(key)
                else:
                    require(operation['state'] == 'running', 'PENDING_RECOVERY_UNSUPPORTED')
                    # Cancellation precedes temporal/permission vetoes; the temporal
                    # veto precedes permissions; all vetoes precede due completion.
                    if operation['cancel_state'] == 'requested':
                        reason = 'client_cancel'
                    elif now >= timing['latestCompletionUnixMs'] or now >= receipt['budgetOriginMonoMs'] + timing['maxRunMs']:
                        reason = 'execution_deadline'
                    elif now >= parse_json(operation['admission'])['lease_expires_ms']:
                        reason = 'lease_expired'
                    elif not permission['invokes']:
                        reason = 'authority_or_binding_lost'
                    else:
                        reason = None
                    state = 'canceled' if reason else 'completed' if now >= receipt['dueMonoMs'] else 'pending'
                require(actual['state'] == state and actual['result']['reason'] == reason and
                        actual['sequence'] == (1 if state == 'pending' else 2), 'GUARD_OUTCOME')
                if reason in {'authority_or_binding_lost','reconciliation_stop'}:
                    checked_causes[cp['record'],op_id] = reason
                guards.append({'phase':phase,'operationId':op_id,'clock':now,
                    'invocationPermitted':permission['invokes'],'expectedState':state,'expectedReason':reason})
    require(not before, 'PHASE_PAIRING')
    require(consumed_recovery == set(recovery), 'UNUSED_RECOVERY_HANDOFF')
    return checked_causes, guards


def inspect_authorized_history(references, files, configuration, configuration_files, *, expected_setup, expected_authority):
    """Check independent PAT/configuration/guard/board/operation/parent histories.

Trusted setup and the grant schedule must come from outside the evidence. The
single-actor immutable-installation simulation profile retains explicit read
permission during active invocation withdrawal. Unsupported prior failure and
recovery causes still refuse in their corresponding component.
"""
    try:
        transcript, snapshots, permissions, denied, configuration_result = _validated_configuration_history(
            references,files,configuration,configuration_files,
            expected_setup=expected_setup,expected_authority=expected_authority)
        correspondence = _correspondence(transcript,expected_setup)
        causes, guards = _guards(transcript,snapshots,permissions,denied)
        board = _board(transcript,expected_setup,checked_causes=causes)
        operations = _operations(transcript,expected_setup)
        procedures = _procedures(transcript)
        result = {'profile':'hms.pat.io-authorized-history-inspection/0.1',
            'configurationHistoryChecked':True,'trustedGrantPlanMatched':True,
            'patCorrespondenceChecked':True,'activeRevocationChecked':True,
            'boardHistoryChecked':True,'operationHistoryChecked':True,'procedureHistoryChecked':True,
            'guardsChecked':guards,'permissionStopsChecked':len(causes),
            'configuration':configuration_result,'correspondence':correspondence,
            'board':board,'operations':operations,'procedures':procedures,
            'configurationAttested':False,'compilerIdentityAttested':False,
            'observationSampleSemanticsChecked':False,'staticTimingPolicyChecked':False,
            'allFaultScenariosChecked':False,'independentOutcomeChecked':False,'qualificationPassed':False}
        canonical(result)
        return result
    except (IoAuthorizedHistoryError,IoConfigurationError,IoCorrespondenceError,IoHistoryError,
            IoOperationHistoryError,IoProcedureHistoryError,IoTranscriptError):
        raise
    except (ContractError,KeyError,TypeError,ValueError,IndexError,UnicodeError,RecursionError) as error:
        raise IoAuthorizedHistoryError('SHAPE') from error
