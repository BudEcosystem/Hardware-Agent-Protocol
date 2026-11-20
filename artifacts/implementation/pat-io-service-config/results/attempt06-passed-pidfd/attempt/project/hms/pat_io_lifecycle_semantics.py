"""Independent full fixed lifecycle histories; no runtime, I/O or qualification."""
from .contracts import canonical, parse_json
from .pat_io_authorized_history import _guards, _receipts
from .pat_io_board_history import _reduce as _board, _tables
from .pat_io_configuration_history import _validated_configuration_history
from .pat_io_correspondence import _Program, _inspect as _correspondence
from .pat_io_lifecycle_history import inspect_lifecycle_transcript
from .pat_io_observation_history import _samples
from .pat_io_operation_history import _fold as _operations
from .pat_io_outcome_history import _static, _outcome
from .pat_io_procedure_history import _fold as _procedures
from .pat_io_recovery_history import _faults, _interruptions
from .pat_io_refusal_history import _refusals


class IoLifecycleHistoryError(ValueError):
    def __init__(self, code):
        self.code='PAT_IO_LIFECYCLE_HISTORY_'+code
        super().__init__(self.code)


def require(value,code):
    if not value:raise IoLifecycleHistoryError(code)


def _one(rows,code):
    require(len(rows)==1,code)
    return rows[0]


def _trusted_faults(name,supplied):
    expected=[]
    if name in {'pending_reply_lost','completion_reply_lost','permission_after_completion'}:
        begin=name=='pending_reply_lost'
        expected=[dict(phase=4 if begin else 5,label='drive:adapters',
            point='board.begin.after_commit' if begin else 'journal.record_execution.before_commit',
            exception='JournalError',code='injected:io_begin_reply_loss' if begin else
                'injected:io_lifecycle_completion_reply_loss',occurrences=1)]
    require(type(supplied) is list and canonical(supplied)==canonical(expected),'TRUSTED_FAULT_PLAN')
    return expected


def _boundaries(trace,name,faults):
    """Derive private recovery context and consume every unknown transition."""
    frames={(cp['value']['phase'],cp['value']['label']):cp for cp in trace['checkpoints']}
    def at(phase,label):
        require((phase,label) in frames,'BOUNDARY_MISSING')
        cp=frames[phase,label]
        return cp,_tables(trace,cp)
    expected_unknowns={};observed_unknowns={};seen=set();previous=None
    for cp in trace['checkpoints']:
        v=cp['value'];t=_tables(trace,cp);label=v['label']
        if label.endswith(':before') or label in {'before_reopen','test_final'}:
            require(previous is not None and t==previous,'QUIET_EXECUTION_CHANGED')
        for event in t['events']:
            if event['kind'] not in {'outcome_unknown','recovery_unknown'}:continue
            key=event['operation_id'],event['sequence']
            if key in seen:continue
            seen.add(key)
            observed_unknowns[key]=(cp['record'],event['kind'],parse_json(event['payload']))
        previous=t
    recovery={};interruptions=[];settlements=[]
    if name=='pending_reply_lost':
        recovery,interruptions,settlements=_interruptions(trace,_faults(
            dict(profile='hms.pat.io-trusted-fault-plan/0.1',faults=faults)))
        cp,t=at(4,'drive:adapters:after');op=_one(t['operations'],'FAULT_TARGET')
        expected_unknowns[op['id'],op['sequence']]=(cp['record'],'outcome_unknown',{'reason':'io_acceptance_unknown'})
    elif faults:
        _,old=at(5,'drive:adapters:before');cp,new=at(5,'drive:adapters:after_error')
        prior=_one(old['operations'],'FAULT_TARGET');op=_one(new['operations'],'FAULT_TARGET')
        require(prior['id']==op['id'] and prior['state']=='running' and op['state']=='outcome_unknown', 'COMPLETION_LOSS_AUTHORITY')
        require(old['claims'] and old['claims']==new['claims'],'COMPLETION_LOSS_CLAIMS')
        before=_receipts(old)[op['id']];receipt=_receipts(new)[op['id']]
        require(before['state']=='pending' and receipt['state']=='completed' and receipt['sequence']==2 and
            receipt['result']==dict(activationCommitted=True,cycleCompleted=True,safeIdle=True,reason=None) and
            not new['io_owners'],'COMPLETION_LOSS_BOARD')
        retained=_one([r for r in new['io_authority_receipts'] if r['operation']==op['id'] and r['sequence']==2], 'COMPLETION_RETENTION')
        require(retained['document']==canonical(receipt),'COMPLETION_RETENTION')
        expected_unknowns[op['id'],op['sequence']]=(cp['record'],'outcome_unknown',{'reason':'io_completion_unknown'})
        interruptions.append(dict(phase=5,point=faults[0]['point'],operationId=op['id'],
            boardState='completed',authorityState='outcome_unknown',heldClaims=len(new['claims'])))
        _,settled=at(6,'drive:adapters:after')
        require(_one(settled['operations'],'SETTLEMENT')['state']=='completed' and not settled['claims'] and
            _receipts(settled)[op['id']]==receipt,'COMPLETION_SETTLEMENT')
        settlements.append(dict(phase=6,operationId=op['id'],state='completed',claimsReleased=True))
    if name in {'reopen_accepted','reopen_pending','completion_reply_lost'}:
        phase={'reopen_accepted':3,'reopen_pending':4,'completion_reply_lost':5}[name]
        _,old=at(phase,'before_reopen');cp,new=at(phase,'after_reopen')
        prior=_one(old['operations'],'REOPEN_TARGET');op=_one(new['operations'],'REOPEN_TARGET')
        require(old['claims'] and old['claims']==new['claims'] and not new['io_owners'],'REOPEN_OWNERSHIP')
        require(old['io_authority_receipts']==new['io_authority_receipts'],'REOPEN_RETENTION')
        if name=='reopen_pending':
            require(prior['state']=='running' and op['state']=='outcome_unknown','REOPEN_UNKNOWN')
            before=_receipts(old)[op['id']];receipt=_receipts(new)[op['id']]
            require(before['state']=='pending' and receipt['state']=='canceled' and
                receipt['result']['reason']=='board_owner_reopened','REOPEN_STOP')
            expected_unknowns[op['id'],op['sequence']]=(cp['record'],'recovery_unknown',{'reason':'owner_reopened'})
            _,settled=at(5,'drive:adapters:after')
            require(_one(settled['operations'],'SETTLEMENT')['state']=='canceled' and not settled['claims'] and
                _receipts(settled)[op['id']]==receipt,'REOPEN_SETTLEMENT')
            retained=_one([r for r in settled['io_authority_receipts'] if r['operation']==op['id'] and r['sequence']==2], 'REOPEN_SETTLEMENT')
            require(retained['document']==canonical(receipt),'REOPEN_SETTLEMENT')
            settlements.append(dict(phase=5,operationId=op['id'],state='canceled',claimsReleased=True))
        else:
            require(old['operations']==new['operations'] and old['events']==new['events'] and
                _receipts(old)==_receipts(new),'REOPEN_HISTORY_CHANGED')
            if name=='reopen_accepted':
                require(op['state']=='accepted' and not new['io_receipts'] and not new['io_dispatch_links'] and
                    not new['io_fences'],'ACCEPTED_REOPEN_EFFECT')
    require(observed_unknowns==expected_unknowns,'UNKNOWN_CAUSE')
    return recovery,interruptions,settlements


def inspect_lifecycle_challenge(references,files,configuration,configuration_files,*,
                                  expected_setup,expected_case,expected_authority,expected_faults):
    """Validate one exact policy challenge; trusted inputs are separate from records."""
    partial=inspect_lifecycle_transcript(references,files,configuration,configuration_files,
        expected_setup=expected_setup,expected_case=expected_case,expected_authority=expected_authority)
    name=partial['scenario'];faults=_trusted_faults(name,expected_faults)
    trace,snapshots,permissions,denied,config=_validated_configuration_history(
        references,files,configuration,configuration_files,expected_setup=expected_setup,expected_authority=expected_authority)
    program=_Program(expected_setup);static=_static(program,expected_setup['static_contract'])
    correspondence=_correspondence(trace,expected_setup)
    recovery,interruptions,settlements=_boundaries(trace,name,faults)
    parents,children,refusals=_refusals(trace,snapshots,permissions)
    causes,guards=_guards(trace,snapshots,permissions,denied,recovery=recovery)
    history=dict(configuration=config,correspondence=correspondence,
        board=_board(trace,expected_setup,checked_causes=causes),
        operations=_operations(trace,expected_setup,checked_refusals=children),
        procedures=_procedures(trace,checked_refusals=parents),sampling=_samples(trace,snapshots),
        refusalsChecked=refusals,guardsChecked=guards,faultsChecked=interruptions,settlementsChecked=settlements)
    outcome=_outcome(trace,program,history);expected=expected_case['definition']['expected']
    require(outcome['contractStatus']==expected['completionContract'] and outcome['settledAndQuiescent'] and
        not outcome['unresolvedOperationIds'] and all(outcome[k]==expected[k] for k in
            ('activations','completedCycles','canceledActivations')),'EXPECTED_OUTCOME')
    final=_tables(trace,trace['checkpoints'][-1]);no_parent=name=='permission_before_parent'
    require(len(final['operations'])==len(final['pr_procedures'])==(0 if no_parent else 1) and
        not final['claims'] and not final['io_owners'],'FINAL_INVENTORY')
    if no_parent:
        require(all(not final[k] for k in ('pr_steps','pr_keys','replay_keys','resource_floors','io_receipts','io_dispatch_links','io_fences')),
            'PARENT_REFUSAL_EFFECT')
    else:
        state=('completed' if name=='permission_after_completion' else 'failed' if name in {
            'permission_before_dispatch','permission_pending','pending_reply_lost'} else 'canceled')
        child=('completed' if expected['completedCycles'] else 'failed' if name in {'permission_pending','pending_reply_lost'} else
            'rejected_before_dispatch' if name=='permission_before_dispatch' else 'canceled')
        require(outcome['actualParentState']==state and final['operations'][0]['state']==child,'FINAL_STATE')
        require(len(final['pr_steps'])==len(program.artifact['steps']) and
            all(r['operation_id'] is None for r in final['pr_steps'] if r['ordinal']>0),'NO_SUFFIX')
        require(sorted((r['resource'],r['fence']) for r in final['resource_floors'])==
            [(resource,1) for resource in program.model.details[program.model.target]['claims']],'FINAL_FLOORS')
    if name=='permission_after_completion':
        require(outcome['nominalCompletionSatisfied'] is True,'HISTORICAL_COMPLETION')
    require(config['decisions']==dict(namespaces=1,parents=0 if no_parent else 1,
        parentSteps=0 if no_parent else len(program.artifact['steps']),admissions=0 if no_parent else 1,
        dispatches=expected['activations'],parentRefusals=1 if no_parent else 0,
        dispatchRefusals=1 if name=='permission_before_dispatch' else 0),'AUTHORITY_DECISIONS')
    result=dict(profile='hms.pat.io-lifecycle-challenge-inspection/0.1',scenario=name,caseId=expected_case['caseId'],
        completeHistoryChecked=True,expectedResponseVerified=True,independentOutcomeChecked=True,
        staticTimingPolicyChecked=True,wholeDeclaredDomainChecked=True,trustedFaultPlanMatched=True,
        exactControlScheduleChecked=True,staticContract=static,outcome=outcome,history=history,
        configurationAttested=False,compilerIdentityAttested=False,physicalMeasurementChecked=False,
        requiredMatrixCoverageChecked=False,allFaultScenariosChecked=False,actualAggregateStorageEnforced=False,qualificationPassed=False)
    canonical(result)
    return result
