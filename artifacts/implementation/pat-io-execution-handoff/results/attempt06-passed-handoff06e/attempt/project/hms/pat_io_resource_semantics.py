"""Independent complete history for the closed four-actor resource challenge.

No runtime/provider/compiler imports or I/O. The explicit trusted actor set is
validated before the private multi-actor board/operation handoffs are constructed.
This validates one provider challenge, never a whole candidate or physical device.
"""
from .contracts import ContractError, canonical, parse_json
from .pat_io_resource_history import inspect_resource_transcript
from .pat_io_transcript import _read
from .pat_io_board_history import _tables, _reduce as _board
from .pat_io_operation_history import _fold as _operations
from .pat_io_configuration_history import _configuration, _Authority, _Dynamic, _static as _static_config
from .pat_io_correspondence import _Program
from .pat_io_outcome_history import _static as _static_timing
from .pat_io_authorized_history import _guards
from .pat_io_observation_history import _samples


class IoResourceHistoryError(ValueError):
    def __init__(self, code):
        super().__init__('PAT_IO_RESOURCE_HISTORY_'+code)


def require(value, code):
    if not value: raise IoResourceHistoryError(code)


def same(left,right):
    return canonical(left)==canonical(right)


class _SharedModel:
    def __init__(self, programs):
        require(set(programs)=={'gpio','pwm','alias','independent'}, 'ACTORS')
        first=programs['gpio'].model
        for field in ('installation','installation_digest','deployment','routes','proofs','details','idle','binding','target'):
            setattr(self,field,getattr(first,field))
        self.models={p.model.target:p.model for p in programs.values()}
        self.bindings={p.model.target[0]:p.model.binding for p in programs.values()}
        require(len(self.models)==len(self.bindings)==4,'ACTORS')

    def intent(self,value):
        key=(value['instanceId'],value['actionId'])
        require(key in self.models,'UNDECLARED_ACTOR')
        return self.models[key].intent(value)


def _configuration_history(trace,snapshots,programs,expected_authority):
    base=programs['gpio'];model=base.model
    require(expected_authority['grantChanges']==[],'GRANT_PLAN')
    authority=_Authority(expected_authority,model.deployment)
    registrations=[]
    for program in programs.values():
        d=program.descriptor
        registration={k:d[k] for k in ('driverProfile','driverDigest','installationDigest','argumentMetadata')}
        registration.update(instanceId=d['binding']['instanceId'],typeDigest=d['binding']['typeDigest'])
        registrations.append(registration)
    registrations.sort(key=lambda r:r['instanceId'])
    static_config=('reg_types','reg_instances','reg_capabilities','reg_bindings','reg_binding_history',
                   'reg_resource_requirements','reg_resource_instances')
    static_execution=('rt_catalog','rt_adapters','rt_io_installation','rc_catalog','rc_generations','rc_tokens','rc_proofs')
    fixed=dynamic=previous=None;frames={};permissions={}
    for snapshot in snapshots:
        cp=snapshot['checkpoint'];execution=_tables(trace,cp);config=snapshot['tables'];value=snapshot['value']
        current=([config[k] for k in static_config],[execution[k] for k in static_execution],snapshot['resolver'])
        if fixed is None:
            bindings=None
            for program in programs.values():
                checked=_static_config(program,authority,config,execution,snapshot['resolver'],checked_registrations=registrations)
                require(bindings is None or same(checked,bindings),'BINDINGS')
                bindings=checked
            fixed=current;dynamic=_Dynamic(model,bindings,authority.initial_revision)
        else: require(current==fixed,'IMMUTABLE_CONFIGURATION')
        presence=dynamic.checkpoint(snapshot,authority,execution)
        require(authority.principal=='pat-io-trial-worker' and authority.allowed('namespace','*') and
                all(authority.invokes(*p.model.target) and authority.allowed('read',p.model.target[0])
                    for p in programs.values()), 'AUTHORIZATION')
        # Source clock changes and intervening records do not mutate either DB.
        if value['label'].endswith(':before') or value['label']=='test_final':
            require(previous is not None and execution==previous['execution'] and config==previous['config'] and
                    snapshot['resolver']==previous['resolver'],'BETWEEN_CALL_MUTATION')
        frame=dict(execution=execution,config=config,resolver=snapshot['resolver'],presence=presence,value=value)
        frames[value['phase'],value['label']]=frame
        permissions[cp['record']]=dict(invokes=True,read=True)
        previous=frame
    require(authority.index==0,'GRANT_PLAN')
    return frames,permissions,dict(configurationSnapshots=len(snapshots),trustedGrantPlanMatched=True,
        actorDescriptorsChecked=4,configurationHistoryChecked=True,configurationAttested=False)


def _operation_value(row,tables):
    return row|dict(intent=parse_json(row['intent']),admission=parse_json(row['admission']),
        may_have_acted=bool(row['may_have_acted']),
        claims=[dict(resource=r['resource'],fence=r['fence']) for r in tables['claims'] if r['operation_id']==row['id']])


def _read_value(row,tables,model):
    receipt,=[parse_json(r['document']) for r in tables['io_receipts'] if r['operation']==row['id']]
    retained,=[r for r in tables['io_receipts'] if r['operation']==row['id']]
    intent=parse_json(row['intent'])
    require(receipt['state']=='completed','HISTORICAL_READ')
    return dict(protocol='hms.operation/0.1',operationId=row['id'],requestDigest=row['digest'],
        instanceId=intent['instanceId'],actionId=intent['actionId'],executionState=row['state'],
        cancellationState=row['cancel_state'],effectVerification=row['verification'],mayHaveActed=bool(row['may_have_acted']),
        eventSequence=row['sequence'],resourceClaims=_operation_value(row,tables)['claims'],
        result=dict(evidenceKind='simulation',output=dict(profile='hms.synthetic-io-result/1',
            primitive=model.details[intent['instanceId'],intent['actionId']]['primitive'],result=receipt['result'],
            safeIdleState=receipt['idleState'],receiptDigest=retained['digest'])))


def _decisions(trace,frames,requests,probe,model):
    counters=dict(admissions=0,busyRefusals=0,replays=0,historicalReads=0,dispatches=0)
    for call in trace['calls']:
        label,phase=call['label'],call['phase'];outcome=call['outcome']
        before=frames[phase,label+':before'];after=frames[phase,label+(':after' if call['returned'] else ':after_error')]
        b,a=before['execution'],after['execution'];now=after['value']['wallMs']
        if label=='lower': continue
        if label=='drive:adapters':
            require(call['returned'] and outcome['result'] is None,'DRIVE_RESULT')
            old_links={r['operation'] for r in b['io_dispatch_links']}
            new_links={r['operation'] for r in a['io_dispatch_links']}-old_links
            eligible=set()
            for row in b['operations']:
                if row['state']!='accepted':continue
                intent=parse_json(row['intent']);timing=intent['timing'];p=after['presence'][intent['instanceId']]
                require(p['session']==intent['endpointSession'] and now<p['expires_ms'] and
                        timing['notBeforeUnixMs']<=now<timing['latestStartUnixMs'] and
                        now<parse_json(row['admission'])['lease_expires_ms'] and
                        now+intent['arguments']['durationMs']<now+timing['maxRunMs'],'DISPATCH_CONTEXT')
                eligible.add(row['id'])
            require(new_links==eligible,'DISPATCH_INVENTORY');counters['dispatches']+=len(eligible)
            continue
        if label=='read:gpio':
            key=next(r for r in b['replay_keys'] if r['caller_key']=='trial:actor:gpio')
            row=next(r for r in b['operations'] if r['id']==key['operation_id'])
            require(call['returned'] and same(outcome['result'],_read_value(row,b,model)),'HISTORICAL_READ')
            counters['historicalReads']+=1;continue
        probe_call=label=='probe:gpio_while_pwm'
        require(probe_call or label.startswith('invoke:'),'CALL')
        request=probe if probe_call else requests[label.split(':')[1]]
        intent=request['intent'];detail,_=model.intent(intent)
        old=[r for r in b['replay_keys'] if (r['namespace'],r['caller_key'])==(request['replayNamespace'],request['operationKey'])]
        if old:
            require(not probe_call and len(old)==1 and call['returned'],'REPLAY')
            row=next(r for r in b['operations'] if r['id']==old[0]['operation_id'])
            require(same(parse_json(row['intent']),intent) and same(outcome['result'],_operation_value(row,b)),'REPLAY')
            counters['replays']+=1;continue
        ns,=b['namespaces'];presence=before['presence'][intent['instanceId']];timing=intent['timing']
        require(ns['token']==request['replayNamespace'] and now<ns['expires_ms'] and
                now<timing['latestStartUnixMs'] and now<timing['latestCompletionUnixMs'] and
                presence['session']==intent['endpointSession'] and now<presence['expires_ms'],'ADMISSION_CONTEXT')
        overlap=set(detail['claims'])&{r['resource'] for r in b['claims']}
        if overlap:
            require(not call['returned'] and outcome['exception']=='JournalError' and outcome['code']=='RESOURCE_BUSY','BUSY_CAUSE')
            counters['busyRefusals']+=1;continue
        require(not probe_call and call['returned'],'ADMISSION_RESULT')
        rows=[r for r in a['operations'] if r['id'] not in {r['id'] for r in b['operations']}]
        require(len(rows)==1,'ADMISSION_INVENTORY');row=rows[0]
        require(row['state']=='accepted' and same(parse_json(row['intent']),intent) and
                parse_json(row['admission'])['policy_revision']=='registry:'+dict((r['key'],r['value']) for r in after['config']['reg_meta'])['revision'] and
                same(outcome['result'],_operation_value(row,a)),'ADMISSION_RESULT')
        counters['admissions']+=1
    require(counters==dict(admissions=4,busyRefusals=3,replays=5,historicalReads=1,dispatches=4),'DECISION_COUNTS')
    return counters


def inspect_resource_challenge(references,files,configuration,configuration_files,*,
                               expected_setup,expected_case,expected_actors,expected_authority):
    try:
        structural=inspect_resource_transcript(references,files,configuration,configuration_files,
            expected_setup=expected_setup,expected_case=expected_case,expected_actors=expected_actors)
        trace=_read(references,files,expected_setup,resource_profile=True)
        snapshots=_configuration(trace,references,files,configuration,configuration_files)
        programs={role:_Program(actor|{'installation':expected_setup['installation']}) for role,actor in expected_actors.items()}
        static={role:_static_timing(p,expected_actors[role]['static_contract']) for role,p in programs.items()}
        model=_SharedModel(programs)
        plan,=[r['value'] for r in trace['records'] if r['kind']=='compiled_plan']
        requests={role:p['request']['procedure']['steps'][0]['request'] for role,p in plan['actors'].items()}
        probe=plan['probes']['gpio_while_pwm']
        frames,permissions,config=_configuration_history(trace,snapshots,programs,expected_authority)
        causes,guards=_guards(trace,snapshots,permissions,[])
        require(not causes,'UNPLANNED_STOP')
        board=_board(trace,expected_setup,checked_model=model)
        operations=_operations(trace,expected_setup,checked_model=model,checked_invokes=requests)
        sampling=_samples(trace,snapshots)
        decisions=_decisions(trace,frames,requests,probe,model)
        final=_tables(trace,trace['checkpoints'][-1]);ids={}
        for role in requests:
            key,=[r for r in final['replay_keys'] if r['caller_key']=='trial:actor:'+role];ids[role]=key['operation_id']
        require(len(final['operations'])==4 and all(r['state']=='completed' for r in final['operations']) and
                not operations['unresolvedOperationIds'] and not final['claims'] and not final['io_owners'] and
                board['modeledBoardIdle'],'FINAL_SETTLEMENT')
        effects={r['instanceId']:(r['activations'],r['completedCycles'],r['canceledActivations']) for r in board['instances']}
        for p in programs.values():require(effects.pop(p.model.target[0])==(1,1,0),'ACTOR_OUTCOME')
        require(all(v==(0,0,0) for v in effects.values()),'HIDDEN_EFFECT')
        both=frames[7,'drive:adapters:after']['execution'];done=frames[8,'drive:adapters:after']['execution']
        require({r['operation'] for r in both['io_owners']}=={ids['gpio'],ids['independent']} and
                {r['id'] for r in done['operations'] if r['state']=='completed'}=={ids['gpio'],ids['independent']},'INDEPENDENT_PROGRESS')
        historical=frames[12,'read:gpio:after']['execution'];live={r['resource']:parse_json(r['state']) for r in historical['io_resources']}
        require({r['operation'] for r in historical['io_owners']}=={ids['alias']} and
                all(live[atom]!=model.idle[atom] for atom in model.details[programs['gpio'].model.target]['claims']), 'HISTORICAL_IDLE')
        observation=trace['finalObservation']
        require(observation['procedure'] is None and set(observation['operationIds'])==set(ids.values()) and
                observation['unresolvedOperations']==[],'FINAL_REPORT')
        result=dict(profile='hms.pat.io-resource-challenge-inspection/0.1',caseId=expected_case['caseId'],
            exactResourceScheduleChecked=True,expectedResponseVerified=True,completeHistoryChecked=True,
            independentOutcomeChecked=True,staticTimingPolicyChecked=True,wholeDeclaredDomainChecked=True,
            history=dict(structure=structural,staticContracts=static,configuration=config,decisions=decisions,
                board=board,operations=operations,guardsChecked=guards,sampling=sampling,
                configurationHistoryChecked=True,boardHistoryChecked=True,operationHistoryChecked=True,
                observationSampleSemanticsChecked=True,parentAbsenceChecked=True,historicalResultChecked=True),
            outcome=dict(completionContract='provider_challenge',activations=4,completedCycles=4,canceledActivations=0,
                settledAndQuiescent=True,unresolvedOperationIds=[],independentPadProgress=True,
                historicalIdleNotCurrentIdle=True,physicalObjectiveVerified=False),
            configurationAttested=False,compilerIdentityAttested=False,requiredMatrixCoverageChecked=False,
            allFaultScenariosChecked=False,actualAggregateStorageEnforced=False,physicalMeasurementChecked=False,qualificationPassed=False)
        canonical(result);return result
    except (ContractError,KeyError,TypeError,IndexError,UnicodeError,RecursionError,StopIteration) as error:
        raise IoResourceHistoryError('SHAPE') from error
