"""Pure fixed authority/binding schedule and request inspection, not full semantics."""
import hashlib

from .contracts import canonical
from .pat_io_transcript import _read, ORIGIN, require
from .pat_io_configuration_history import _configuration
from .pat_io_correspondence import _Program, _inspect
from .pat_io_board_history import digest


def _case(setup, supplied):
    require(type(supplied) is dict and type(supplied.get('definition')) is dict,'PAT_IO_AUTHORITY_CASE')
    name = supplied['definition'].get('scenario')
    require(type(name) is str and name in {'binding_before_dispatch','binding_pending','full_authority_withdrawal'},
        'PAT_IO_AUTHORITY_CASE')
    before = name=='binding_before_dispatch';withdraw = name=='full_authority_withdrawal'
    control = dict(at='accepted' if before else 'pending',action='withdraw_all' if withdraw else 'invalidate_binding')
    if not before:control['recovery']='privileged_capture_reopen_and_reconcile' if withdraw else 'reopen_and_reconcile'
    checks = ('no_handoff,no_rebinding,claims_released,no_suffix' if before else
        'public_read_denied,internal_recovery_retained,no_namespace_bypass,no_suffix' if withdraw else
        'historical_stop,new_admission_refused,no_rebinding,no_suffix')
    definition = dict(scenario=name,window='ordinary',stepCount=2,control=control,
        expected=dict(activations=0 if before else 1,completedCycles=0,canceledActivations=0 if before else 1,
            completionContract='failed',settledAndQuiescent=True,unresolvedOperations=0,checks=checks.split(',')),
        schedulerTickCeiling=64)
    if name=='binding_pending':
        definition['probes']=[dict(name='inactive_binding',operationKey='trial:probe:inactive_binding',
            expectedError='BINDING_INACTIVE',expectedAdmissions=0,possibleAdmissions=1)]
    p = _Program(setup);detail=p.model.details[p.model.target];pwm=detail['primitive']=='pwm_burst'
    body = dict(kind='fixed_challenge',definition=definition,targetRole='pwm' if pwm else 'gpio',
        programDigest=p.pat_digest,plannedChildOperations=3 if name=='binding_pending' else 2,schedulerTickCeiling=64)
    body['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',body)
    require(canonical(supplied)==canonical(body),'PAT_IO_AUTHORITY_CASE')
    args = dict(durationMs=10)
    args.update(dict(frequencyHz=detail['envelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8) if pwm else dict(level=1))
    require(p.role=='io' and p.artifact['parameters']=={} and p.artifact['timingBudget']==dict(
        latestStartOffsetMs=100,latestCompletionOffsetMs=1000,maxRunSumMs=200) and
        p.artifact['steps']==[dict(stepId='step:'+str(i),role='io',actionId=p.action,
            arguments={k:{'literal':v} for k,v in args.items()},timing=dict(notBeforeOffsetMs=0,
                latestStartOffsetMs=100 if i==0 else 999,latestCompletionOffsetMs=1000,maxRunMs=100)) for i in range(2)],
        'PAT_IO_AUTHORITY_PROGRAM')
    return name,p


def inspect_authority_transcript(references, files, configuration, configuration_files, *, expected_setup, expected_case):
    name,p = _case(expected_setup,expected_case)
    trace = _read(references,files,expected_setup,authority_profile=True)
    snapshots = _configuration(trace,references,files,configuration,configuration_files)
    # The existing exact lowering check applies to the actual initial resolved
    # environment. Reopen is explicitly unavailable and checked separately;
    # never synthesize a descriptor for that unavailable environment.
    initial_correspondence = _inspect(trace | {'opened':trace['opened'][:1]},expected_setup)
    before = name=='binding_before_dispatch';pending=name=='binding_pending'
    success = lambda label:(label,ORIGIN,True,None)
    denied = lambda label,code:(label,ORIGIN,False,code)
    wanted = [success('lower'),success('submit'),success('drive:procedure')]
    if not before:wanted.append(success('drive:adapters'))
    wanted.append(success('change:authority' if name=='full_authority_withdrawal' else 'change:binding'))
    public_denials = [denied(label,'ACCESS_DENIED') for label in ('read:operation','read:parent','submit','probe:namespace')]
    if before:wanted += [success('drive:adapters'),success('drive:procedure')]
    else:
        if not pending:wanted += public_denials
        wanted.append(success('drive:adapters'))
        if pending:wanted.append(denied('resume','PROCEDURE_DEPENDENCY_UNRESOLVED'))
        wanted.append(success('cancel'))
        wanted += [denied('probe:inactive_binding','BINDING_INACTIVE')] if pending else public_denials
    actual=[(c['label'],c['clock'],c['returned'],c['outcome'].get('code')) for c in trace['calls']]
    require(actual==wanted and trace['ticks']==3 and len(trace['opened'])==(1 if before else 2),
        'PAT_IO_AUTHORITY_SCHEDULE')
    require(all(c['returned'] or c['outcome']['exception']=='JournalError' for c in trace['calls']),
        'PAT_IO_AUTHORITY_EXCEPTION')
    reopens=[(s['value']['phase'],s['value']['label']) for s in snapshots if s['value']['label'] in {'before_reopen','after_reopen'}]
    phase=5 if pending else 9
    require(reopens==([] if before else [(phase,'before_reopen'),(phase,'after_reopen')]),'PAT_IO_AUTHORITY_REOPEN')
    plan,=[r['value'] for r in trace['records'] if r['kind']=='compiled_plan']
    probes = ({'inactive_binding':plan['request']['procedure']['steps'][0]['request'] | {
        'operationKey':'trial:probe:inactive_binding'}} if pending else {})
    require(canonical(trace['authorityInput'])==canonical(dict(case=expected_case,probes=probes)),
        'PAT_IO_AUTHORITY_PROBE')
    d=p.descriptor
    record={k:d[k] for k in ('driverProfile','driverDigest','installationDigest','argumentMetadata')}
    record.update(instanceId=p.model.target[0],typeDigest=d['binding']['typeDigest'])
    identity=dict(profile='hms.pat.bindings.sqlite-finite-io/0.1',installationDigest=p.model.installation_digest,
        driverDigest=p.model.installation['driverDigest'],registrations=[record])
    resolver=dict(profile='hms.pat.io-resolver-configuration/0.1',resolverProfile=identity['profile'],registrations=[record],
        registrationIdentity='sha256:'+hashlib.sha256(b'HMS-PAT-IO-BINDING-REGISTRATIONS-v1\0'+canonical(identity)).hexdigest())
    require(all(canonical(s['resolver'])==canonical(resolver) for s in snapshots),'PAT_IO_AUTHORITY_RESOLVER')
    readonly=[c['phase'] for c in trace['calls'] if not c['returned']]
    for phase in readonly:
        pair=[s for s in snapshots if s['value']['phase']==phase and
            s['value']['label'].endswith((':before',':after_error'))]
        require(len(pair)==2 and pair[0]['checkpoint']['tables']==pair[1]['checkpoint']['tables'] and
            pair[0]['tables']==pair[1]['tables'],'PAT_IO_AUTHORITY_READ_ONLY')
    return dict(profile='hms.pat.io-authority-transcript-inspection/0.1',scenario=name,
        transcriptGrammarChecked=True,pairedConfigurationStructureChecked=True,exactAuthorityScheduleChecked=True,
        initialPatCorrespondenceChecked=initial_correspondence['patCorrespondenceChecked'],
        predeclaredProbeChecked=pending,unavailableCurrentEnvironmentRecorded=not before,
        privilegedObservationLabeled=True,readOnlyDenialsChecked=len(readonly),
        checkpointsChecked=len(snapshots),runtimeOpens=len(trace['opened']),schedulerTicks=3,
        completeHistoryChecked=False,boardHistoryChecked=False,operationHistoryChecked=False,procedureHistoryChecked=False,
        independentOutcomeChecked=False,expectedResponseVerified=False,requiredMatrixCoverageChecked=False,
        configurationAttested=False,actualAggregateStorageEnforced=False,physicalMeasurementChecked=False,qualificationPassed=False)
