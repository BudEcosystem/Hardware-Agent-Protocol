"""Pure shared-resource schedule/request inspection, not a complete effect fold."""
import hashlib
import re

from .contracts import canonical
from .pat_io_transcript import _read, ORIGIN, require, closed
from .pat_io_configuration_history import _configuration
from .pat_io_correspondence import _Program, _no_work
from .pat_io_board_history import _tables, digest

ROLES = ('gpio','pwm','alias','independent')


def _case(programs, supplied):
    actors={}
    for role,p in programs.items():
        model=p.model; detail=model.details[model.target]; a=p.artifact
        primitive='pwm_burst' if role=='pwm' else 'gpio_pulse'
        arguments=dict(durationMs=10)
        arguments.update(dict(frequencyHz=detail['envelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8)
                         if role=='pwm' else dict(level=1))
        require(detail['primitive']==primitive and p.role=='io' and a['parameters']=={} and
            a['timingBudget']==dict(latestStartOffsetMs=100,latestCompletionOffsetMs=1000,maxRunSumMs=100) and
            a['steps']==[dict(stepId='step:0',role='io',actionId=p.action,
                arguments={k:{'literal':v} for k,v in arguments.items()},
                timing=dict(notBeforeOffsetMs=0,latestStartOffsetMs=100,latestCompletionOffsetMs=1000,maxRunMs=100))],
            'PAT_IO_RESOURCE_PROGRAM')
        actors[role]=dict(instanceId=model.target[0],actionId=p.action,primitive=primitive,
            adapterId=model.routes[model.target[0]],claims=list(detail['claims']),programDigest=p.pat_digest)
    require(len({a['instanceId'] for a in actors.values()})==4 and
            actors['gpio']['claims']==actors['alias']['claims'] and
            actors['gpio']['adapterId']!=actors['alias']['adapterId'] and
            set(actors['gpio']['claims'])<set(actors['pwm']['claims']) and
            not set(actors['independent']['claims'])&set(actors['pwm']['claims']), 'PAT_IO_RESOURCE_TOPOLOGY')
    definition=dict(scenario='shared_resources',schedulerTickCeiling=128,
        actorOrder=['gpio','independent','alias','pwm'],
        probes=[dict(name='gpio_while_pwm',actor='gpio',operationKey='trial:probe:gpio_busy',
                     expectedError='RESOURCE_BUSY',expectedAdmissions=0,possibleAdmissions=1)],
        control=['start_gpio','pwm_busy','alias_busy','start_independent','finish_gpio_and_independent',
            'replay_original_gpio','start_alias','read_historical_gpio_while_alias_active','finish_alias',
            'start_pwm','gpio_busy','finish_pwm','replay_all_original_requests'],
        expected=dict(activations=4,completedCycles=4,canceledActivations=0,completionContract='provider_challenge',
            settledAndQuiescent=True,unresolvedOperations=0,
            checks=['both_primitives_execute','gpio_pwm_mutual_exclusion','cross_route_alias_exclusion',
                'independent_pad_progress','same_key_replay_no_activation','one_shared_fence_history',
                'historical_idle_not_current_idle','no_hidden_actor']))
    body=dict(kind='resource_challenge',definition=definition,actors=actors,plannedChildOperations=5,schedulerTickCeiling=128)
    body['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',body)
    require(canonical(body)==canonical(supplied),'PAT_IO_RESOURCE_CASE')


def inspect_resource_transcript(references, files, configuration, configuration_files, *, expected_setup, expected_case, expected_actors):
    closed(expected_actors,ROLES)
    require(canonical(expected_setup)==canonical(expected_actors['gpio']|{'installation':expected_setup['installation']}),
            'PAT_IO_RESOURCE_SETUP')
    programs={}
    for role,actor in expected_actors.items():
        closed(actor,{'artifact','original_descriptor','static_contract'})
        programs[role]=_Program(actor|{'installation':expected_setup['installation']})
    _case(programs,expected_case)
    trace=_read(references,files,expected_setup,resource_profile=True)
    snapshots=_configuration(trace,references,files,configuration,configuration_files)
    require(canonical(trace['resourceInput'])==canonical(dict(case=expected_case,actors=expected_actors)),
            'PAT_IO_RESOURCE_INPUT')
    o=ORIGIN
    wanted=[('lower',o,True,None),('invoke:gpio',o,True,None),('drive:adapters',o,True,None),
        ('invoke:pwm',o,False,'RESOURCE_BUSY'),('invoke:alias',o,False,'RESOURCE_BUSY'),
        ('invoke:independent',o,True,None),('drive:adapters',o,True,None),
        ('drive:adapters',o+10,True,None),('invoke:gpio',o+10,True,None),
        ('invoke:alias',o+10,True,None),('drive:adapters',o+10,True,None),('read:gpio',o+10,True,None),
        ('drive:adapters',o+20,True,None),('invoke:pwm',o+20,True,None),('drive:adapters',o+20,True,None),
        ('probe:gpio_while_pwm',o+20,False,'RESOURCE_BUSY'),('drive:adapters',o+30,True,None)]
    wanted += [('invoke:'+role,o+30,True,None) for role in ROLES]
    actual=[(c['label'],c['clock'],c['returned'],c['outcome'].get('code')) for c in trace['calls']]
    require(actual==wanted and len(trace['opened'])==1 and trace['ticks']==7,'PAT_IO_RESOURCE_SCHEDULE')
    require(all(c['returned'] or c['outcome']['exception']=='JournalError' for c in trace['calls']),
            'PAT_IO_RESOURCE_EXCEPTION')
    opening=trace['opened'][0]
    lower=next(cp for cp in trace['checkpoints'] if cp['value']['label']=='lower:after')
    tables=_tables(trace,lower);_no_work(tables,programs['gpio'].model)
    require(len(tables['namespaces'])==1,'PAT_IO_RESOURCE_NAMESPACE');ns=tables['namespaces'][0]
    require(ns['principal']=='pat-io-trial-worker' and ns['deployment']==programs['gpio'].model.deployment and
            ns['epoch']==1 and ns['expires_ms']==ORIGIN+1001 and
            re.fullmatch('replay:'+re.escape(opening['authorityId'])+':1:[0-9a-f]{32}',ns['token']) is not None,
            'PAT_IO_RESOURCE_NAMESPACE')
    plan,=[r['value'] for r in trace['records'] if r['kind']=='compiled_plan']
    closed(plan,{'actors','probes'});closed(plan['actors'],ROLES);closed(plan['probes'],{'gpio_while_pwm'})
    compilers=set();requests={};registrations=[];wanted_env={};actual_env={}
    for role,p in programs.items():
        actual=plan['actors'][role];compiler=actual['compilerDigest']
        require(type(compiler) is str and re.fullmatch('sha256:[0-9a-f]{64}',compiler) is not None,'PAT_IO_RESOURCE_COMPILER')
        compilers.add(compiler)
        request=p.request({},ns['token'],opening['session']);request['procedureKey']='trial:parent:'+role
        child=request['procedure']['steps'][0]['request'];child['operationKey']='trial:actor:'+role;requests[role]=child
        bound=p.descriptor|{'endpointSession':opening['session']}
        wanted_env[role]=p.environment(compiler,p.descriptor['endpointSession'])
        actual_env[role]=p.environment(compiler,opening['session'])
        expected=actual_env[role]|dict(request=request,requestDigest=digest(b'HMS-PROCEDURE-JCS-SHA256-v0.1',request),
            runBindingDigest=digest(b'HMS-PAT-RUN-BINDING-v0.1',dict(bindings={'io':bound},compilerDigest=compiler,
                targetProfile='hms.bound-sequence/0.1')),
            report=dict(targetProfile='hms.bound-sequence/0.1',stepCount=1,admitted=False,parameterDomainPreserved=True,
                unitConversions=[],frameConversions=[],unsupported=[],runtimeGuards='installed_primitive_guards_only',
                evidenceMode='simulation',physicalObjectiveVerified=False))
        require(canonical(actual)==canonical(expected),'PAT_IO_RESOURCE_PLAN')
        registration={k:p.descriptor[k] for k in ('driverProfile','driverDigest','installationDigest','argumentMetadata')}
        registration.update(instanceId=p.model.target[0],typeDigest=p.model.binding['typeDigest']);registrations.append(registration)
    require(len(compilers)==1 and canonical(opening['originalEnvironment'])==canonical(wanted_env) and
            canonical(opening['workerEnvironment'])==canonical(actual_env),'PAT_IO_RESOURCE_ENVIRONMENT')
    require(canonical(plan['probes']['gpio_while_pwm'])==canonical(requests['gpio']|{'operationKey':'trial:probe:gpio_busy'}),
            'PAT_IO_RESOURCE_PROBE')
    registrations.sort(key=lambda r:r['instanceId']);model=programs['gpio'].model
    identity=dict(profile='hms.pat.bindings.sqlite-finite-io/0.1',installationDigest=model.installation_digest,
                  driverDigest=model.installation['driverDigest'],registrations=registrations)
    resolver=dict(profile='hms.pat.io-resolver-configuration/0.1',resolverProfile=identity['profile'],registrations=registrations,
        registrationIdentity='sha256:'+hashlib.sha256(b'HMS-PAT-IO-BINDING-REGISTRATIONS-v1\0'+canonical(identity)).hexdigest())
    require(all(canonical(s['resolver'])==canonical(resolver) for s in snapshots),'PAT_IO_RESOURCE_RESOLVER')
    # These are targeted checks, not a derivation of every operation/event/effect.
    # Replays, failed admissions and historical reads must be entirely read-only.
    unchanged_phases={4,5,9,12,16,18,19,20,21}
    for phase in unchanged_phases:
        pair=[s for s in snapshots if s['value']['phase']==phase and s['value']['label']!='test_final']
        require(len(pair)==2,'PAT_IO_RESOURCE_PAIR')
        require(pair[0]['checkpoint']['tables']==pair[1]['checkpoint']['tables'] and
                pair[0]['tables']==pair[1]['tables'],'PAT_IO_RESOURCE_READ_ONLY')
    return dict(profile='hms.pat.io-resource-transcript-inspection/0.1',transcriptGrammarChecked=True,
        pairedConfigurationStructureChecked=True,exactResourceScheduleChecked=True,actorRequestsChecked=4,
        predeclaredProbeChecked=True,historicalIdentityConsistencyChecked=True,readOnlyPhasesChecked=9,
        checkpointsChecked=len(snapshots),schedulerTicks=7,childOperationReservation=5,
        completeHistoryChecked=False,boardHistoryChecked=False,operationHistoryChecked=False,
        independentOutcomeChecked=False,expectedResponseVerified=False,requiredMatrixCoverageChecked=False,
        configurationAttested=False,actualAggregateStorageEnforced=False,physicalMeasurementChecked=False,qualificationPassed=False)
