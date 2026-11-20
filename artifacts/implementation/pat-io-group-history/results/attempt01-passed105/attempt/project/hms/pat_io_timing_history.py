"""Independently check a named timing challenge and its actual expected outcome.

The producer schedule and expected flags are not imported. Exact calls/clocks,
fixed challenge artifact, complete history and deadline precedence are checked.
"""
from .contracts import canonical, parse_json
from .pat_io_board_history import _tables, digest
from .pat_io_correspondence import _Program
from .pat_io_outcome_history import inspect_trial_outcome
from .pat_io_transcript import ORIGIN, _read


class IoTimingHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_TIMING_HISTORY_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoTimingHistoryError(code)


# Independently stated policy data: name, window, six offsets/budgets, controls,
# effects, completion contract, named requirements and exact adapter poll times.
SPECS = {
    'not_before_boundary': ('not_before',(50,100,1000,100,10,1000),{'advanceOffsetsMs':[49,50,60]},(1,1,0),'satisfied',
        'no_early_handoff,start_at_lower_bound,due_equality_completes',(0,49,50,60),60,True),
    'latest_start_before': ('latest_start',(0,50,1000,100,1,1000),{'advanceOffsetsMs':[49,50]},(1,1,0),'satisfied',
        'start_before_upper_bound,started_work_can_finish_at_start_deadline',(49,50),50,False),
    'latest_start_equal': ('latest_start',(0,50,1000,100,1,1000),{'advanceOffsetsMs':[50]},(0,0,0),'failed',
        'no_start_at_upper_bound,claims_released,floor_retained',(50,),50,None),
    'run_completion_equal': ('run_finish',(0,100,1000,100,1,1000),{'at':'pending','advanceOffsetsMs':[100]},(1,0,1),'failed',
        'execution_deadline_precedes_due,activation_not_completion',(0,100),100,None),
    'wall_completion_equal': ('wall_finish',(0,10,50,50,1,1000),{'dispatchOffsetMs':5,'finishOffsetMs':50},(1,0,1),'failed',
        'wall_deadline_precedes_due,wall_deadline_precedes_equal_lease,run_budget_not_expired',(5,50),50,None),
    'lease_wait_before': ('lease_wait',(59998,60001,70000,2,1,70000),{'advanceOffsetsMs':[59997,59998,59999]},(1,1,0),'satisfied',
        'lease_starts_at_admission,no_early_handoff,finish_before_lease',(0,59997,59998,59999),59999,True),
    'lease_wait_equal': ('lease_wait',(59998,60001,70000,2,1,70000),{'advanceOffsetsMs':[60000]},(0,0,0),'failed',
        'accepted_wait_consumes_lease,lease_precedes_latest_start,no_activation',(60000,),60000,None),
    'late_parent_reporting': ('late_parent',(0,100,1000,100,1,1000),{'boardFinishOffsetMs':1,'parentReportOffsetMs':1000},(1,1,0),'satisfied',
        'historical_completion,parent_completion_at_deadline,nominal_timing_false',(0,1),1000,False),
}


def _case(program, supplied):
    require(type(supplied) is dict and type(supplied.get('definition')) is dict, 'CASE')
    name = supplied['definition'].get('scenario')
    require(type(name) is str and name in SPECS, 'UNSUPPORTED_CASE')
    window,times,control,effects,status,checks,polls,parent_at,nominal = SPECS[name]
    n,s,c,r,d,p = times
    model = program.model; detail = model.details[model.target]; primitive = detail['primitive']
    arguments = ({'durationMs':d,'level':1} if primitive == 'gpio_pulse' else
        dict(durationMs=d,frequencyHz=detail['envelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8))
    a = program.artifact
    expected = dict(protocol='hms.pat/0.1',profile='hms.pat.bound-sequence/0.1',name='io-policy-'+primitive,
        version='1',taskKind='sim.io.qualification.challenge',inputProfile='hms.sim.io.challenge/0.1',parameters={},
        roles={'io':dict(capabilityFamily='sim:finite-gpio-pwm',actions=[program.action],driverProfiles=['sqlite-finite-io/1'])},
        applicability={'phase':'selection','all':[dict(field='context.evidenceMode',op='equals',literal='simulation')]},
        targetProfile='hms.bound-sequence/0.1',executionPlacement='hms-host-orchestration',
        timingBudget=dict(latestStartOffsetMs=s,latestCompletionOffsetMs=p,maxRunSumMs=r),
        steps=[dict(stepId='step:0',role='io',actionId=program.action,
            arguments={key:{'literal':value} for key,value in arguments.items()},
            timing=dict(notBeforeOffsetMs=n,latestStartOffsetMs=s,latestCompletionOffsetMs=c,maxRunMs=r))],
        effectBudget=dict(maxInvocations=1,scope='simulation_only'),
        outcomeContract=dict(requiredEffect='capability_completion',requiredCompletedSteps=['step:0'],evidenceMode='simulation',physicalObjectiveVerified=False),
        runtimeGuardProfile='installed_primitive_guards_only')
    require(canonical(a) == canonical(expected), 'PROGRAM')
    definition=dict(scenario=name,window=window,stepCount=1,control=control,
        expected=dict(activations=effects[0],completedCycles=effects[1],canceledActivations=effects[2],completionContract=status,
            settledAndQuiescent=True,unresolvedOperations=0,checks=checks.split(',')),schedulerTickCeiling=64)
    body=dict(kind='fixed_challenge',definition=definition,targetRole='gpio' if primitive=='gpio_pulse' else 'pwm',
        programDigest=program.pat_digest,plannedChildOperations=1,schedulerTickCeiling=64)
    body['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',body)
    require(canonical(supplied) == canonical(body), 'CASE')
    return name,effects,status,polls,parent_at,nominal


def inspect_timing_challenge(references, files, configuration, configuration_files, *,
                             expected_setup, expected_authority, expected_case):
    """Require the exact named challenge, not merely a coherent successful trial."""
    transcript=_read(references,files,expected_setup); program=_Program(expected_setup)
    name,effects,status,polls,parent_at,nominal=_case(program,expected_case)
    require(len(transcript['opened'])==1 and expected_authority['grantChanges']==[], 'CONTEXT')
    expected_calls=[('lower',0),('submit',0),('drive:procedure',0)]
    expected_calls += [('drive:adapters',t) for t in polls]+[('drive:procedure',parent_at)]
    actual=[(c['label'],c['clock']-ORIGIN) for c in transcript['calls']]
    require(actual==expected_calls and all(c['returned'] for c in transcript['calls']), 'CONTROL_SCHEDULE')
    offsets=[]; clock=0
    for _,value in expected_calls:
        if value!=clock: offsets.append((clock+ORIGIN,value+ORIGIN));clock=value
    require([(r['value']['from'],r['value']['to']) for r in transcript['records'] if r['kind']=='clock_advanced']==offsets, 'CLOCK_SCHEDULE')
    result=inspect_trial_outcome(references,files,configuration,configuration_files,
        expected_setup=expected_setup,expected_authority=expected_authority)
    outcome=result['outcome']; final=_tables(transcript,transcript['checkpoints'][-1])
    require(outcome['contractStatus']==status and outcome['settledAndQuiescent'] and not outcome['unresolvedOperationIds'] and
            tuple(outcome[k] for k in ('activations','completedCycles','canceledActivations'))==effects and
            outcome['nominalTimingSatisfied'] is nominal, 'EXPECTED_OUTCOME')
    claims=program.model.details[program.model.target]['claims']
    require(len(final['operations'])==1 and not final['claims'] and
            sorted((r['resource'],r['fence']) for r in final['resource_floors'])==[(resource,1) for resource in claims], 'CLAIM_HISTORY')
    operation=final['operations'][0]; intent=parse_json(operation['intent']); admission=parse_json(operation['admission'])
    if name in {'latest_start_equal','lease_wait_equal'}:
        require(not final['io_dispatch_links'] and not final['io_receipts'] and not final['io_fences'] and
                operation['attempt_id'] is None and operation['may_have_acted']==0, 'NO_HANDOFF')
        at=ORIGIN+parent_at
        require((at==intent['timing']['latestStartUnixMs'] and at<admission['lease_expires_ms']) if name=='latest_start_equal' else
                (at==admission['lease_expires_ms'] and at<intent['timing']['latestStartUnixMs']), 'EXPIRY_PRECEDENCE')
    if name in {'run_completion_equal','wall_completion_equal'}:
        receipt=parse_json(final['io_receipts'][0]['document']); at=ORIGIN+parent_at
        require(receipt['state']=='canceled' and receipt['result']['reason']=='execution_deadline' and at>=receipt['dueMonoMs'], 'STOP_PRECEDENCE')
        require((at==receipt['budgetOriginMonoMs']+intent['timing']['maxRunMs'] and at<intent['timing']['latestCompletionUnixMs']) if name=='run_completion_equal' else
                (at==intent['timing']['latestCompletionUnixMs']==admission['lease_expires_ms'] and
                 at<receipt['budgetOriginMonoMs']+intent['timing']['maxRunMs']), 'STOP_PRECEDENCE')
    if name=='late_parent_reporting':
        require(outcome['parentCompletedAtMs']==ORIGIN+1000 and outcome['parentCompletionBeforeDeadline'] is False and
                outcome['zeroLagChildScheduleMatched'] is True and outcome['nominalCompletionSatisfied'] is False, 'HISTORICAL_COMPLETION')
    return dict(profile='hms.pat.io-timing-challenge-inspection/0.1',caseId=expected_case['caseId'],scenario=name,
        exactControlScheduleChecked=True,expectedResponseVerified=True,independentOutcomeChecked=True,
        trial=result,requiredMatrixCoverageChecked=False,configurationAttested=False,compilerIdentityAttested=False,
        actualAggregateStorageEnforced=False,physicalMeasurementChecked=False,qualificationPassed=False)
