"""Independent semantics for fixed binding and complete permission withdrawal.

Trusted setup/change inputs are separate from acquired evidence. No runtime,
producer, provider, filesystem, SQL, live clock or qualification service is used.
"""
import copy

from .contracts import canonical, parse_json
from .pat_io_transcript import _read, ORIGIN, closed, integer
from .pat_io_authority_history import inspect_authority_transcript
from .pat_io_configuration_history import _configuration, _Authority, _Dynamic, _static as _configuration_static, _decisions
from .pat_io_correspondence import _Program, _inspect as _correspondence
from .pat_io_board_history import _tables, _reduce as _board
from .pat_io_operation_history import _fold as _operations
from .pat_io_procedure_history import _fold as _procedures
from .pat_io_authorized_history import _guards
from .pat_io_observation_history import _samples
from .pat_io_outcome_history import _static, _outcome


class IoAuthorityHistoryError(ValueError):
    def __init__(self, code):
        self.code='PAT_IO_AUTHORITY_HISTORY_'+code
        super().__init__(self.code)


def require(value, code):
    if not value:raise IoAuthorityHistoryError(code)


def _trusted(program, scenario, supplied):
    closed(supplied,{'principal','deployment','initialRegistryRevision','initialGrants','action','phase','target'})
    integer(supplied['initialRegistryRevision'],1)
    before=scenario=='binding_before_dispatch';withdraw=scenario=='full_authority_withdrawal'
    expected=dict(principal='pat-io-trial-worker',deployment=program.model.deployment,
        initialRegistryRevision=supplied['initialRegistryRevision'],
        initialGrants=[dict(principal='pat-io-trial-worker',deployment=program.model.deployment,target='*',verb='admin')],
        action='withdraw_all' if withdraw else 'invalidate_binding',phase=4 if before else 5,target=program.model.target[0])
    require(canonical(supplied)==canonical(expected),'TRUSTED_CHANGE')
    return _Authority(dict(profile='hms.pat.io-trusted-authority/0.1',principal=expected['principal'],
        deployment=expected['deployment'],initialRegistryRevision=expected['initialRegistryRevision'],
        initialGrants=expected['initialGrants'],grantChanges=[]),program.model.deployment)


def _configuration_and_decisions(trace, snapshots, program, scenario, change):
    authority=_trusted(program,scenario,change);target=program.model.target[0]
    withdraw=scenario=='full_authority_withdrawal'
    static_config=('reg_types','reg_instances','reg_capabilities','reg_binding_history','reg_resource_requirements','reg_resource_instances')
    static_execution=('rt_catalog','rt_adapters','rt_io_installation','rc_catalog','rc_generations','rc_tokens','rc_proofs')
    calls={c['phase']:c for c in trace['calls']}
    counters=dict(namespaces=0,parents=0,parentSteps=0,admissions=0,dispatches=0,parentRefusals=0,dispatchRefusals=0)
    fixed=dynamic=previous=previous_snapshot=previous_execution=None
    changed=False;inactive=set();inactive_context={};permissions={};binding_refusals={};read_denials=set()
    decisions=[];initial_bindings=None
    change_label='change:authority:after' if withdraw else 'change:binding:after'
    for snapshot in snapshots:
        value=snapshot['value'];phase,label=value['phase'],value['label'];key=snapshot['checkpoint']['record']
        execution=_tables(trace,snapshot['checkpoint']);config=snapshot['tables']
        require(value['wallMs']==value['monotonicMs']==ORIGIN and
            dict((r['key'],r['value']) for r in execution['meta'])['last_clock']==str(ORIGIN),'CLOCK')
        current=([config[k] for k in static_config],[execution[k] for k in static_execution],snapshot['resolver'])
        if fixed is None:
            bindings=_configuration_static(program,authority,config,execution,snapshot['resolver'])
            initial_bindings=copy.deepcopy(config['reg_bindings'])
            fixed=current;dynamic=_Dynamic(program.model,bindings,authority.initial_revision)
        else:require(current==fixed,'IMMUTABLE_CONFIGURATION')
        if previous_snapshot is not None and (label.endswith(':before') or label in {'before_reopen','test_final'}):
            require(execution==previous_execution and config==previous_snapshot['tables'],'BETWEEN_CALL_MUTATION')
        if (phase,label)==(change['phase'],change_label):
            require(not changed and authority.allowed('admin','*') and previous_snapshot is not None and
                previous_snapshot['value']['label']==change_label.removesuffix(':after')+':before' and
                execution==previous_execution and calls[phase]['outcome']['result'] is None,'CHANGE_AUTHORIZATION')
            changed=True;dynamic.revision+=1
            if withdraw:authority.grants=set()
            else:inactive={target}
            mutable={'reg_meta','reg_grants'} if withdraw else {'reg_meta','reg_bindings','reg_presence'}
            require(all(config[k]==previous_snapshot['tables'][k] for k in config if k not in mutable),'CHANGE_SIDE_EFFECT')
        require(changed or phase<=change['phase'],'CHANGE_MISSING')
        expected_bindings=copy.deepcopy(initial_bindings)
        for row in expected_bindings:
            if row['instance'] in inactive:row['active']=0
        require(config['reg_bindings']==expected_bindings,'BINDING_TRANSITION')
        presence=dynamic.checkpoint(snapshot,authority,execution,checked_inactive=inactive)
        if inactive:inactive_context[key]=set(inactive)
        previous=_decisions(program,authority,snapshot,execution,presence,previous,calls,counters,checked_inactive=inactive)
        permission=dict(invokes=authority.invokes(*program.model.target) and target not in inactive,
            read=authority.allowed('read',target))
        permissions[key]=permission
        if label=='after_reopen':
            require(changed and (target in inactive or not authority.invokes(*program.model.target)), 'RESOLVER_REFUSAL_CAUSE')
            old,=previous_execution['operations'];new,=execution['operations']
            require(old['state']=='running' and new['state']=='outcome_unknown' and
                execution['claims']==previous_execution['claims'] and execution['claims'] and
                not execution['io_owners'],'RECOVERY_CLAIMS')
            decisions.append(dict(phase=phase,kind='historical_recovery',publicReadPermitted=permission['read'],
                currentResolutionAvailable=False,claimsRetainedUntilSettlement=True))
        if label=='drive:adapters:after':
            old,=previous_execution['operations'];new,=execution['operations']
            if old['state']=='accepted':
                if target in inactive:
                    require(authority.invokes(*program.model.target) and new['state']=='rejected_before_dispatch', 'BINDING_REFUSAL')
                    binding_refusals[key,new['id']]='BINDING_INACTIVE'
                else:
                    require(permission['invokes'] and new['state']=='running','REQUIRED_DISPATCH')
            elif old['state']=='outcome_unknown':
                require(new['state']=='canceled' and not execution['claims'],'REQUIRED_RECONCILIATION')
        if label.endswith(':after_error'):
            call=calls[phase];name=call['label']
            require(execution==previous_execution and config==previous_snapshot['tables'],'DENIAL_MUTATION')
            if name in {'read:operation','read:parent','submit','probe:namespace'}:
                require(withdraw and changed and not permission['read'] and not authority.grants,'PUBLIC_DENIAL_CAUSE')
                require(execution['operations'] and execution['pr_procedures'] and len(execution['namespaces'])==1,
                    'DENIAL_RETAINED_IDENTITY')
                if name=='probe:namespace':require(not authority.allowed('namespace',program.model.deployment),'NAMESPACE_DENIAL')
                if name=='submit':read_denials.add(key)
                decisions.append(dict(phase=phase,kind=name,cause='ACCESS_DENIED',allTablesUnchanged=True))
            elif name=='probe:inactive_binding':
                require(target in inactive and authority.invokes(*program.model.target) and
                    len(execution['operations'])==1 and len(execution['namespaces'])==1,'PROBE_REFUSAL_CAUSE')
                probe=trace['authorityInput']['probes']['inactive_binding'];ns=execution['namespaces'][0]
                require(probe['replayNamespace']==ns['token'] and ns['principal']==authority.principal and
                    ORIGIN<ns['expires_ms'] and probe['operationKey'] not in
                    {r['caller_key'] for r in execution['pr_keys']+execution['replay_keys']},'PROBE_REFUSAL_CAUSE')
                decisions.append(dict(phase=phase,kind=name,cause='BINDING_INACTIVE',allTablesUnchanged=True))
            else:require(name=='resume' and permission['read'],'UNSUPPORTED_DENIAL')
        if label=='cancel:after':
            # Existing owner's withdrawal after terminal child: no invoke/read
            # permission is inferred from the successful cancellation reply.
            child,=previous_execution['operations'];parent,=previous_execution['pr_procedures']
            require(child['state']=='canceled' and not previous_execution['claims'] and
                parent['principal']==authority.principal and parent['deployment']==authority.deployment,
                'OWNER_WITHDRAWAL')
        previous_snapshot,previous_execution=snapshot,execution
    require(changed and counters==dict(namespaces=1,parents=1,parentSteps=2,admissions=1,
        dispatches=0 if scenario=='binding_before_dispatch' else 1,parentRefusals=2 if withdraw else 0,
        dispatchRefusals=1 if scenario=='binding_before_dispatch' else 0),'DECISION_COUNTS')
    require(len(read_denials)==(2 if withdraw else 0),'READ_DENIAL_INVENTORY')
    return permissions,inactive_context,binding_refusals,read_denials,dict(decisions=counters,authorityChanges=1,
        configurationSnapshots=len(snapshots),trustedChangeMatched=True,configurationHistoryChecked=True,
        publicAndRecoveryDecisions=decisions,configurationAttested=False)


def inspect_authority_challenge(references, files, configuration, configuration_files, *,
                                expected_setup, expected_case, expected_authority_change):
    structural=inspect_authority_transcript(references,files,configuration,configuration_files,
        expected_setup=expected_setup,expected_case=expected_case)
    scenario=structural['scenario'];program=_Program(expected_setup)
    trace=_read(references,files,expected_setup,authority_profile=True)
    snapshots=_configuration(trace,references,files,configuration,configuration_files)
    permissions,inactive,binding_refusals,read_denials,config=_configuration_and_decisions(
        trace,snapshots,program,scenario,expected_authority_change)
    static=_static(program,expected_setup['static_contract'])
    correspondence=_correspondence(trace|{'opened':trace['opened'][:1]},expected_setup)
    causes,guards=_guards(trace,snapshots,permissions,[])
    board=_board(trace,expected_setup,checked_causes=causes)
    operations=_operations(trace,expected_setup,checked_binding_refusals=binding_refusals)
    procedures=_procedures(trace,checked_read_denials=read_denials)
    samples=_samples(trace,snapshots,checked_inactive=inactive)
    history=dict(configuration=config,correspondence=correspondence,guardsChecked=guards,
        refusalsChecked=[dict(kind='binding_before_dispatch',operationId=op,cause=code) for (_,op),code in binding_refusals.items()],
        board=board,operations=operations,procedures=procedures,sampling=samples,
        configurationHistoryChecked=True,patCorrespondenceChecked=True,boardHistoryChecked=True,
        operationHistoryChecked=True,procedureHistoryChecked=True,observationSampleSemanticsChecked=True)
    outcome=_outcome(trace,program,history);before=scenario=='binding_before_dispatch'
    require(outcome['contractStatus']=='failed' and outcome['settledAndQuiescent'] and not outcome['unresolvedOperationIds'] and
        tuple(outcome[k] for k in ('activations','completedCycles','canceledActivations'))==((0,0,0) if before else (1,0,1)),
        'EXPECTED_OUTCOME')
    final=_tables(trace,trace['checkpoints'][-1])
    require(len(final['operations'])==1 and not final['claims'] and not final['io_owners'] and
        all(r['operation_id'] is None for r in final['pr_steps'] if r['ordinal']>0) and
        procedures['derivedProcedure']['executionState']==('failed' if before else 'canceled'),'NO_SUFFIX')
    result=dict(profile='hms.pat.io-authority-challenge-inspection/0.1',scenario=scenario,caseId=expected_case['caseId'],
        exactAuthorityScheduleChecked=True,expectedResponseVerified=True,completeHistoryChecked=True,
        independentOutcomeChecked=True,staticTimingPolicyChecked=True,wholeDeclaredDomainChecked=True,
        staticContract=static,history=history,outcome=outcome,configurationAttested=False,compilerIdentityAttested=False,
        requiredMatrixCoverageChecked=False,allFaultScenariosChecked=False,actualAggregateStorageEnforced=False,
        physicalMeasurementChecked=False,qualificationPassed=False)
    canonical(result)
    return result
