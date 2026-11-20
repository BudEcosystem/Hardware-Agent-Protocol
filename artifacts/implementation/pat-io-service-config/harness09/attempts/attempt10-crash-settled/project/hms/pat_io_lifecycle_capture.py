"""Fixed lifecycle and retained-read trial schedules, not a qualification API."""
import copy

from .contracts import canonical
from .journal import JournalError
from .pat_contracts import require, snapshot
from .pat_io_combined_matrix import IoCombinedMatrixPolicy
from .pat_io_configuration_capture import ConfiguredIoTrialEngine
from .pat_io_trials import ORIGIN, MAX_RECORDS, MAX_OUTPUT_BYTES


SCENARIOS = frozenset(('cancel_accepted','cancel_pending','reopen_accepted','reopen_pending',
    'completion_reply_lost','pending_reply_lost','permission_before_parent',
    'permission_before_dispatch','permission_pending','permission_after_completion'))
COMPLETION_LOSS = 'injected:io_lifecycle_completion_reply_loss'
BEGIN_LOSS = 'injected:io_begin_reply_loss'


def _refused(function, code):
    try: function()
    except JournalError as error:
        require(error.code == code, 'PAT_IO_LIFECYCLE_UNEXPECTED_FAILURE')
        return
    require(False, 'PAT_IO_LIFECYCLE_REFUSAL_MISSING')


def _withdraw(engine):
    target = engine.original_descriptor['binding']['instanceId']
    engine.runtime.registry.grant(engine.owner,engine.owner.principal,target,'read')
    engine.runtime.registry.grant(engine.owner,engine.owner.principal,'*','admin',enabled=False)


def _lose_once(engine, point, injected):
    """Run the original boundary once, restoring it even when capture fails."""
    begin = point == 'board.begin.after_commit'
    obj = engine.runtime.io_board if begin else engine.runtime.journal
    attribute = 'begin' if begin else 'record_execution'
    original = getattr(obj,attribute)
    code = BEGIN_LOSS if begin else COMPLETION_LOSS
    def wrapped(*args, **kwargs):
        if begin:
            receipt = original(*args,**kwargs)
            operation_id = receipt['operationId']
            require(receipt['state']=='pending','PAT_IO_LIFECYCLE_FAULT_CONTEXT')
        else:
            ticket,state,evidence = args
            if state != 'completed':return original(*args,**kwargs)
            operation_id = ticket.operation_id
        require(not injected,'PAT_IO_LIFECYCLE_FAULT_REPEATED')
        injected.append(dict(phase=engine.phase,label='drive:adapters',point=point,
            exception='JournalError',code=code,operationId=operation_id,occurrences=1))
        raise JournalError(code)
    setattr(obj,attribute,wrapped)
    try:
        if begin:engine.drive('adapters')
        else:_refused(lambda:engine.drive('adapters'),code)
        require(len(injected)==1,'PAT_IO_LIFECYCLE_FAULT_MISSING')
    finally:setattr(obj,attribute,original)


def run_lifecycle_challenge(directory, *, matrix, candidate, installation, descriptor,
                            challenge_bindings, case_id, group_budget=None):
    if group_budget is not None: group_budget.assert_case(case_id)
    matrix = snapshot(matrix,'PAT_IO_LIFECYCLE_MATRIX')
    if group_budget is None:
        matrix_digest = IoCombinedMatrixPolicy(installation).validate(
            matrix,candidate,descriptor,challenge_bindings,limits=matrix.get('limits'))
    else:
        matrix_digest = group_budget.validated_matrix_digest(matrix=matrix,candidate=candidate,
            installation=installation,descriptor=descriptor,challenge_bindings=challenge_bindings)
    require(type(case_id) is str,'PAT_IO_LIFECYCLE_CASE')
    cases = [c for c in matrix['cases'] if c['caseId']==case_id]
    require(len(cases)==1,'PAT_IO_LIFECYCLE_CASE');case=cases[0]
    require(case['kind']=='fixed_challenge' and case['definition']['scenario'] in SCENARIOS,
        'PAT_IO_LIFECYCLE_UNSUPPORTED_CASE')
    artifact = next(p['artifact'] for p in matrix['programs'] if p['digest']==case['programDigest'])
    engine = ConfiguredIoTrialEngine(directory,artifact,installation,descriptor,group_budget=group_budget)
    scenario = case['definition']['scenario'];injected=[]
    try:
        engine.lower({})
        if scenario=='permission_before_parent':
            _withdraw(engine);_refused(engine.submit,'ACCESS_DENIED')
        else:
            engine.submit();engine.drive('procedure')
            if scenario=='cancel_accepted':
                engine.cancel();engine.drive()
            elif scenario=='reopen_accepted':
                engine.reopen();_refused(engine.resume,'IO_SESSION_CHANGED');engine.cancel();engine.drive()
            elif scenario=='permission_before_dispatch':
                _withdraw(engine);engine.drive('adapters');engine.drive('procedure')
            elif scenario=='pending_reply_lost':
                _lose_once(engine,'board.begin.after_commit',injected)
                engine.drive('adapters');engine.drive('procedure')
            else:
                engine.drive('adapters')
                if scenario=='cancel_pending':
                    engine.cancel();engine.drive()
                elif scenario=='reopen_pending':
                    engine.reopen();engine.drive('adapters')
                    _refused(engine.resume,'PROCEDURE_DEPENDENCY_UNRESOLVED');engine.cancel();engine.drive()
                elif scenario=='permission_pending':
                    _withdraw(engine);engine.drive('adapters');engine.drive('procedure')
                else:
                    engine.advance_to(ORIGIN+10)
                    _lose_once(engine,'journal.record_execution.before_commit',injected)
                    if scenario=='completion_reply_lost':
                        engine.reopen();engine.drive('adapters')
                        _refused(engine.resume,'IO_SESSION_CHANGED');engine.cancel();engine.drive()
                    else:
                        require(scenario=='permission_after_completion','PAT_IO_LIFECYCLE_CASE')
                        _withdraw(engine);engine.drive('adapters');engine.drive('procedure')
        engine.capture('test_final');report=engine.report()
        require(report['schedulerTicks']<=case['schedulerTickCeiling'],'PAT_IO_LIFECYCLE_TICK_RESERVATION')
        manifest = dict(profile='hms.pat.io-lifecycle-trial/0.1',caseId=case_id,matrixDigest=matrix_digest,
            programDigest=case['programDigest'],records=copy.deepcopy(engine.records),
            configuration=engine.configuration_manifest(),report=report,injectedFaults=injected,
            closed=False,executionPerformed=True,childOperationReservation=case['plannedChildOperations'],
            schedulerTickReservation=case['schedulerTickCeiling'],requiredMatrixCoverageChecked=False,
            independentOutcomeChecked=False,qualificationPassed=False,actualAggregateStorageEnforced=False)
    finally:engine.close()
    manifest['closed']=True;encoded=canonical(manifest)
    require(len(encoded)<=65536 and manifest['configuration']['combinedRecords']+1<=MAX_RECORDS and
        manifest['configuration']['combinedBytes']+len(encoded)<=MAX_OUTPUT_BYTES,'PAT_IO_LIFECYCLE_MANIFEST_LIMIT')
    return manifest
