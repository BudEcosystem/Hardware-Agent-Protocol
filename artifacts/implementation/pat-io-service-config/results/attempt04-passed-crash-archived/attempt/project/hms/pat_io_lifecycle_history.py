"""Pure exact lifecycle request/schedule reader; no complete outcome claim."""
from .contracts import canonical
from .pat_io_board_history import digest
from .pat_io_configuration_history import _configuration
from .pat_io_correspondence import _Program, _inspect
from .pat_io_transcript import _read, ORIGIN, require


# Independent policy declarations. No producer schedule or matrix imports.
SPECS = {
 'cancel_accepted':(2,dict(at='accepted',action='cancel_parent'),(0,0,0),'failed','no_handoff,claims_released,floor_retained,no_suffix'),
 'cancel_pending':(2,dict(at='pending',action='cancel_parent'),(1,0,1),'failed','one_activation,idle_before_release,no_suffix'),
 'reopen_accepted':(2,dict(at='accepted',action='reopen',recovery='resume_refuses_then_cancel'),(0,0,0),'failed','new_session,old_request_preserved,no_rebinding,no_suffix'),
 'reopen_pending':(2,dict(at='pending',action='reopen',recovery='reconcile_then_cancel'),(1,0,1),'failed','owner_reopen_stop,old_request_preserved,no_rebinding,no_suffix'),
 'completion_reply_lost':(2,dict(at='first_board_completion',action='lose_completion_record',recovery='reopen_resume_refuses_then_cancel'),(1,1,0),'failed','historical_completion,no_reactivation,stale_suffix_refused'),
 'pending_reply_lost':(2,dict(at='first_board_activation',action='lose_begin_reply',recovery='reconcile_stop'),(1,0,1),'failed','unknown_holds_claims,exact_reconciliation_stop,no_suffix'),
 'permission_before_parent':(1,dict(at='before_submit',action='withdraw_invoke_keep_read'),(0,0,0),'failed','no_parent,no_child,no_claim,no_floor'),
 'permission_before_dispatch':(2,dict(at='accepted',action='withdraw_invoke_keep_read'),(0,0,0),'failed','no_handoff,claims_released,floor_retained,no_suffix'),
 'permission_pending':(2,dict(at='pending',action='withdraw_invoke_keep_read'),(1,0,1),'failed','authority_loss_stop,idle_before_release,no_suffix'),
 'permission_after_completion':(1,dict(at='board_completed_before_settlement',action='withdraw_invoke_keep_read'),(1,1,0),'satisfied','historical_completion,retained_read,no_reactivation'),
}
WITHDRAW = {'permission_before_parent':(2,'submit:before'),
 'permission_before_dispatch':(4,'drive:adapters:before'),'permission_pending':(5,'drive:adapters:before'),
 'permission_after_completion':(6,'drive:adapters:before')}


def _case(setup, supplied):
    require(type(supplied) is dict and type(supplied.get('definition')) is dict,'PAT_IO_LIFECYCLE_CASE')
    name=supplied['definition'].get('scenario')
    require(type(name) is str and name in SPECS,'PAT_IO_LIFECYCLE_CASE')
    count,control,effects,status,checks=SPECS[name];p=_Program(setup)
    detail=p.model.details[p.model.target];primitive=detail['primitive'];pwm=primitive=='pwm_burst'
    definition=dict(scenario=name,window='ordinary',stepCount=count,control=control,
        expected=dict(activations=effects[0],completedCycles=effects[1],canceledActivations=effects[2],
            completionContract=status,settledAndQuiescent=True,unresolvedOperations=0,checks=checks.split(',')),
        schedulerTickCeiling=64)
    body=dict(kind='fixed_challenge',definition=definition,targetRole='pwm' if pwm else 'gpio',
        programDigest=p.pat_digest,plannedChildOperations=count,schedulerTickCeiling=64)
    body['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',body)
    require(canonical(supplied)==canonical(body),'PAT_IO_LIFECYCLE_CASE')
    args=dict(durationMs=10)
    args.update(dict(frequencyHz=detail['envelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8) if pwm else dict(level=1))
    expected=dict(protocol='hms.pat/0.1',profile='hms.pat.bound-sequence/0.1',name='io-policy-'+primitive,
        version='1',taskKind='sim.io.qualification.challenge',inputProfile='hms.sim.io.challenge/0.1',parameters={},
        roles={'io':dict(capabilityFamily='sim:finite-gpio-pwm',actions=[p.action],driverProfiles=['sqlite-finite-io/1'])},
        applicability={'phase':'selection','all':[dict(field='context.evidenceMode',op='equals',literal='simulation')]},
        targetProfile='hms.bound-sequence/0.1',executionPlacement='hms-host-orchestration',
        timingBudget=dict(latestStartOffsetMs=100,latestCompletionOffsetMs=1000,maxRunSumMs=count*100),
        steps=[dict(stepId='step:'+str(i),role='io',actionId=p.action,arguments={k:{'literal':v} for k,v in args.items()},
            timing=dict(notBeforeOffsetMs=0,latestStartOffsetMs=100 if i==0 else 999,
                latestCompletionOffsetMs=1000,maxRunMs=100)) for i in range(count)],
        effectBudget=dict(maxInvocations=count,scope='simulation_only'),
        outcomeContract=dict(requiredEffect='capability_completion',requiredCompletedSteps=['step:'+str(i) for i in range(count)],
            evidenceMode='simulation',physicalObjectiveVerified=False),runtimeGuardProfile='installed_primitive_guards_only')
    require(canonical(p.artifact)==canonical(expected),'PAT_IO_LIFECYCLE_PROGRAM')
    return name,p


def inspect_lifecycle_transcript(references, files, configuration, configuration_files, *,
                                  expected_setup, expected_case, expected_authority):
    name,p=_case(expected_setup,expected_case)
    trace=_read(references,files,expected_setup)
    snapshots=_configuration(trace,references,files,configuration,configuration_files)
    correspondence=_inspect(trace,expected_setup)
    ok=lambda label,t=0:(label,ORIGIN+t,True,None)
    fail=lambda label,code,t=0:(label,ORIGIN+t,False,code)
    wanted=[ok('lower')];reopen=None;ticks=0
    if name=='permission_before_parent':wanted.append(fail('submit','ACCESS_DENIED'))
    else:
        wanted += [ok('submit'),ok('drive:procedure')];ticks=1
        if name=='cancel_accepted':wanted += [ok('cancel'),ok('drive:cycle')];ticks=2
        elif name=='reopen_accepted':
            reopen=3;wanted += [fail('resume','IO_SESSION_CHANGED'),ok('cancel'),ok('drive:cycle')];ticks=2
        elif name=='permission_before_dispatch':wanted += [ok('drive:adapters'),ok('drive:procedure')];ticks=3
        else:
            wanted.append(ok('drive:adapters'));ticks=2
            if name=='cancel_pending':wanted += [ok('cancel'),ok('drive:cycle')];ticks=3
            elif name=='reopen_pending':
                reopen=4;wanted += [ok('drive:adapters'),fail('resume','PROCEDURE_DEPENDENCY_UNRESOLVED'),ok('cancel'),ok('drive:cycle')];ticks=4
            elif name in {'pending_reply_lost','permission_pending'}:
                wanted += [ok('drive:adapters'),ok('drive:procedure')];ticks=4
            else:
                wanted.append(fail('drive:adapters','injected:io_lifecycle_completion_reply_loss',10));ticks=5
                if name=='completion_reply_lost':
                    reopen=5;wanted += [ok('drive:adapters',10),fail('resume','IO_SESSION_CHANGED',10),ok('cancel',10),ok('drive:cycle',10)]
                else:wanted += [ok('drive:adapters',10),ok('drive:procedure',10)]
    actual=[(c['label'],c['clock'],c['returned'],c['outcome'].get('code')) for c in trace['calls']]
    require(actual==wanted and trace['ticks']==ticks,'PAT_IO_LIFECYCLE_SCHEDULE')
    require(all(c['returned'] or c['outcome']['exception']=='JournalError' for c in trace['calls']),
        'PAT_IO_LIFECYCLE_EXCEPTION')
    reopens=[(s['value']['phase'],s['value']['label']) for s in snapshots if s['value']['label'] in {'before_reopen','after_reopen'}]
    require(reopens==([] if reopen is None else [(reopen,'before_reopen'),(reopen,'after_reopen')]) and
        len(trace['opened'])==(1 if reopen is None else 2),'PAT_IO_LIFECYCLE_REOPEN')
    clocks=[(r['value']['from'],r['value']['to']) for r in trace['records'] if r['kind']=='clock_advanced']
    require(clocks==([(ORIGIN,ORIGIN+10)] if name in {'completion_reply_lost','permission_after_completion'} else []),
        'PAT_IO_LIFECYCLE_CLOCK')
    owner=dict(principal='pat-io-trial-worker',deployment=p.model.installation['topology']['deployment'])
    initial=[owner|dict(target='*',verb='admin')];read=[owner|dict(target=p.model.target[0],verb='read')]
    changes=[]
    if name in WITHDRAW:
        phase,label=WITHDRAW[name];changes=[dict(phase=phase,label=label,grants=read)]
    authority=owner|dict(profile='hms.pat.io-trusted-authority/0.1',initialRegistryRevision=13,
        initialGrants=initial,grantChanges=changes)
    require(canonical(expected_authority)==canonical(authority),'PAT_IO_LIFECYCLE_AUTHORITY_PLAN')
    for snapshot in snapshots:
        changed=bool(changes) and snapshot['value']['phase']>=changes[0]['phase']
        require(snapshot['tables']['reg_grants']==(read if changed else initial),
            'PAT_IO_LIFECYCLE_GRANT_SNAPSHOT')
        revision=next(r['value'] for r in snapshot['tables']['reg_meta'] if r['key']=='revision')
        require(revision==str(15 if changed else 13),'PAT_IO_LIFECYCLE_REVISION')
    refusals=[c['phase'] for c in trace['calls'] if not c['returned'] and c['label'] in {'submit','resume'}]
    for phase in refusals:
        pair=[s for s in snapshots if s['value']['phase']==phase and s['value']['label'].endswith((':before',':after_error'))]
        require(len(pair)==2 and pair[0]['checkpoint']['tables']==pair[1]['checkpoint']['tables'] and
            pair[0]['tables']==pair[1]['tables'],'PAT_IO_LIFECYCLE_REFUSAL_MUTATED_STATE')
    return dict(profile='hms.pat.io-lifecycle-transcript-inspection/0.1',scenario=name,
        transcriptGrammarChecked=True,pairedConfigurationStructureChecked=True,
        exactControlScheduleChecked=True,patCorrespondenceChecked=correspondence['patCorrespondenceChecked'],
        trustedGrantSnapshotsChecked=True,readOnlyRefusalsChecked=len(refusals),
        checkpointsChecked=len(snapshots),runtimeOpens=len(trace['opened']),schedulerTicks=ticks,
        completeHistoryChecked=False,independentOutcomeChecked=False,expectedResponseVerified=False,
        requiredMatrixCoverageChecked=False,configurationAttested=False,actualAggregateStorageEnforced=False,
        physicalMeasurementChecked=False,qualificationPassed=False)
