"""Independent trusted-fault and pending-output recovery history composition.

Pure retained-data inspection for one immutable simulation installation. The fault
schedule is separately trusted; producer fault summaries never authorize a cause.
This is not physical stopping, complete fault coverage or PAT qualification.
"""
from __future__ import annotations

from .contracts import ContractError, canonical, parse_json
from .pat_io_authorized_history import IoAuthorizedHistoryError, _guards, _receipts
from .pat_io_board_history import IoHistoryError, _reduce as _board, _tables
from .pat_io_configuration_history import IoConfigurationError, _validated_configuration_history
from .pat_io_correspondence import IoCorrespondenceError, _inspect as _correspondence
from .pat_io_operation_history import IoOperationHistoryError, _fold as _operations
from .pat_io_procedure_history import IoProcedureHistoryError, _fold as _procedures
from .pat_io_transcript import IoTranscriptError

POINTS = {
    'board.begin.after_commit':'injected:io_begin_reply_loss',
    'board.finish.before_commit':'injected:io_finish_before_commit',
    'journal.reconcile.before_commit':'injected:io_recovery_authority_reply_loss',
}
BOARD_TABLES = ('io_meta','io_resources','io_owners','io_fences','io_receipts','io_receipt_versions','io_effects')


class IoRecoveryHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_RECOVERY_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoRecoveryHistoryError(code)


def _faults(value):
    require(type(value) is dict and set(value)=={'profile','faults'} and
            value['profile']=='hms.pat.io-trusted-fault-plan/0.1', 'TRUSTED_PLAN')
    faults=value['faults']; require(type(faults) is list and 1<=len(faults)<=16, 'TRUSTED_PLAN')
    result={}; last=0
    for fault in faults:
        require(type(fault) is dict and set(fault)=={'phase','label','point','exception','code','occurrences'}, 'TRUSTED_PLAN')
        phase=fault['phase']; point=fault['point']
        require(type(phase) is int and last<phase<=2048 and fault['label']=='drive:adapters' and
                type(point) is str and point in POINTS and fault['exception']=='JournalError' and
                fault['code']==POINTS[point] and type(fault['occurrences']) is int and fault['occurrences']==1, 'TRUSTED_PLAN')
        last=phase; result[phase]=fault
    return result


def _one(values, code):
    require(len(values)==1,code)
    return values[0]


def _interruptions(transcript, faults):
    require(len(transcript['opened'])==1,'REOPEN_UNSUPPORTED')
    calls={c['phase']:c for c in transcript['calls']}
    require(set(faults)<=set(calls),'UNUSED_FAULT')
    for phase,call in calls.items():
        fault=faults.get(phase)
        if fault is None:
            require(call['returned'],'UNPLANNED_FAILURE')
        else:
            require(call['label']==fault['label'],'FAULT_PHASE')
            if fault['point']=='board.begin.after_commit':
                require(call['returned'] and call['outcome']['result'] is None,'FAULT_RETURN')
            else:
                require(not call['returned'] and call['outcome']['exception']==fault['exception'] and
                        call['outcome']['code']==fault['code'],'FAULT_RETURN')
    before={}; seen_unknown=set(); unknowns={}; expected_unknowns={}
    recovery={}; consumed=set(); observations=[]; settlements=[]
    for cp in transcript['checkpoints']:
        value=cp['value']; phase,label=value['phase'],value['label']; current=_tables(transcript,cp)
        for event in current['events']:
            if event['kind'] not in {'outcome_unknown','recovery_unknown'}: continue
            key=(event['operation_id'],event['sequence'])
            if key in seen_unknown: continue
            require(event['kind']=='outcome_unknown' and phase in faults and
                    label in {'drive:adapters:after','drive:adapters:after_error'},'UNKNOWN_PHASE')
            require(phase not in unknowns,'UNKNOWN_EVENT')
            unknowns[phase]=(event['operation_id'],parse_json(event['payload']))
            seen_unknown.add(key)
        if label in {'drive:adapters:before','drive:cycle:before'}:
            before[phase]=current
            continue
        if label not in {'drive:adapters:after','drive:adapters:after_error','drive:cycle:after','drive:cycle:after_error'}:
            continue
        prior=before.pop(phase); old_ops={r['id']:r for r in prior['operations']}
        new_ops={r['id']:r for r in current['operations']}; old_receipts=_receipts(prior); new_receipts=_receipts(current)
        fault=faults.get(phase); selected=None
        if fault is not None:
            point=fault['point']; consumed.add(phase)
            if point=='board.begin.after_commit':
                selected=_one([op for op,row in old_ops.items() if row['state']=='accepted' and op not in old_receipts],'FAULT_TARGET')
            elif point=='board.finish.before_commit':
                selected=_one([op for op,row in old_ops.items() if row['state'] in {'running','outcome_unknown'} and
                               op in old_receipts and old_receipts[op]['state']=='pending'],'FAULT_TARGET')
            else:
                selected=_one([op for op,row in old_ops.items() if row['state']=='outcome_unknown' and
                               op in old_receipts and old_receipts[op]['state'] in {'pending','completed','canceled'}],'FAULT_TARGET')
            require(selected in new_ops and selected in new_receipts,'FAULT_RESULT')
            old,new=old_ops[selected],new_ops[selected]; receipt=new_receipts[selected]
            claims_before=[r for r in prior['claims'] if r['operation_id']==selected]
            claims_after=[r for r in current['claims'] if r['operation_id']==selected]
            require(claims_before and claims_before==claims_after,'FAULT_CLAIMS')
            require(new['state']=='outcome_unknown','FAULT_AUTHORITY')
            if point=='board.begin.after_commit':
                require(old['may_have_acted']==0 and new['may_have_acted']==1 and receipt['state']=='pending' and
                        receipt['sequence']==1 and all(r['operation']!=selected for r in current['io_authority_receipts']), 'BEGIN_LOSS')
                expected_unknowns[phase]=(selected,{'reason':'io_acceptance_unknown'})
            elif point=='board.finish.before_commit':
                require(all(current[k]==prior[k] for k in BOARD_TABLES),'UNCOMMITTED_BOARD_CHANGED')
                recovery[cp['record'],selected]=(old['state'],'pending',None)
                if old['state']=='running':
                    expected_unknowns[phase]=(selected,{'reason':'io_completion_unknown'})
                else:
                    require(current['operations']==prior['operations'] and current['events']==prior['events'],'UNCOMMITTED_AUTHORITY_CHANGED')
            else:
                require(current['operations']==prior['operations'] and current['events']==prior['events'],'UNCOMMITTED_AUTHORITY_CHANGED')
                if old_receipts[selected]['state']=='pending':
                    recovery[cp['record'],selected]=('outcome_unknown','canceled','reconciliation_stop')
                # Retention precedes attempted authority settlement. It must be
                # the exact current terminal board receipt, not a claimed result.
                require(receipt['state'] in {'completed','canceled'},'RECONCILIATION_BOARD')
                retained=_one([r for r in current['io_authority_receipts'] if r['operation']==selected and
                               r['sequence']==receipt['sequence']], 'RECONCILIATION_RECEIPT')
                require(retained['document']==canonical(receipt),'RECONCILIATION_RECEIPT')
            observations.append({'phase':phase,'point':point,'operationId':selected,
                'boardState':receipt['state'],'authorityState':new['state'],'heldClaims':len(claims_after)})
        for op_id,old in old_ops.items():
            if old['state']!='outcome_unknown' or op_id not in old_receipts: continue
            if op_id==selected and fault is not None and fault['point'] in {'board.finish.before_commit','journal.reconcile.before_commit'}:
                continue
            require(op_id in new_receipts and op_id in new_ops,'RECOVERY_RESULT')
            receipt=new_receipts[op_id]
            if old_receipts[op_id]['state']=='pending':
                recovery[cp['record'],op_id]=('outcome_unknown','canceled','reconciliation_stop')
            require(receipt['state'] in {'completed','canceled'},'RECOVERY_RESULT')
            state='completed' if receipt['state']=='completed' else 'canceled' if receipt['result']['reason'] in {
                'client_cancel','board_owner_reopened'} else 'failed'
            require(new_ops[op_id]['state']==state and all(r['operation_id']!=op_id for r in current['claims']), 'SETTLEMENT_REQUIRED')
            retained=_one([r for r in current['io_authority_receipts'] if r['operation']==op_id and
                           r['sequence']==receipt['sequence']], 'SETTLEMENT_RECEIPT')
            require(retained['document']==canonical(receipt),'SETTLEMENT_RECEIPT')
            settlements.append({'phase':phase,'operationId':op_id,'state':state,'claimsReleased':True})
    require(not before and consumed==set(faults),'UNUSED_FAULT')
    require(unknowns==expected_unknowns,'UNKNOWN_CAUSE')
    return recovery,observations,settlements


def inspect_recovery_history(references, files, configuration, configuration_files, *, expected_setup, expected_authority, expected_faults):
    """Validate trusted fault schedules and exact retained recovery histories.

The private interruption/cause handoffs are derived here, never supplied by the
caller. Unknown pending state at a failed cut remains unresolved; an observed
unfailed recovery phase must settle its existing receipt and release claims.
"""
    try:
        faults=_faults(expected_faults)
        transcript,snapshots,permissions,denied,config=_validated_configuration_history(
            references,files,configuration,configuration_files,
            expected_setup=expected_setup,expected_authority=expected_authority)
        correspondence=_correspondence(transcript,expected_setup)
        recovery,interruptions,settlements=_interruptions(transcript,faults)
        causes,guards=_guards(transcript,snapshots,permissions,denied,recovery=recovery)
        board=_board(transcript,expected_setup,checked_causes=causes)
        operations=_operations(transcript,expected_setup); procedures=_procedures(transcript)
        result={'profile':'hms.pat.io-recovery-history-inspection/0.1','trustedFaultPlanMatched':True,
            'pendingRecoveryChecked':True,'configurationHistoryChecked':True,'trustedGrantPlanMatched':True,
            'patCorrespondenceChecked':True,'boardHistoryChecked':True,'operationHistoryChecked':True,'procedureHistoryChecked':True,
            'faultsChecked':interruptions,'settlementsChecked':settlements,'guardsChecked':guards,
            'recoveryStopsChecked':sum(c=='reconciliation_stop' for c in causes.values()),
            'configuration':config,'correspondence':correspondence,'board':board,'operations':operations,'procedures':procedures,
            'configurationAttested':False,'compilerIdentityAttested':False,'observationSampleSemanticsChecked':False,
            'staticTimingPolicyChecked':False,'allFaultScenariosChecked':False,'independentOutcomeChecked':False,'qualificationPassed':False}
        canonical(result); return result
    except (IoRecoveryHistoryError,IoAuthorizedHistoryError,IoConfigurationError,IoCorrespondenceError,IoHistoryError,
            IoOperationHistoryError,IoProcedureHistoryError,IoTranscriptError):
        raise
    except (ContractError,KeyError,TypeError,ValueError,IndexError,UnicodeError,RecursionError) as error:
        raise IoRecoveryHistoryError('SHAPE') from error
