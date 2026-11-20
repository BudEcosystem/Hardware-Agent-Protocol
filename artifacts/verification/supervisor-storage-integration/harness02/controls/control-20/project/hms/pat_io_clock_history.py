"""Pure structural/clock-schedule inspection; full clock-fault semantics are pending.

No producer schedule, runtime or provider is imported. This reader deliberately
does not assert board/authority/outcome correctness merely from a valid capture.
"""
from .contracts import canonical
from .pat_io_transcript import _read, ORIGIN, require
from .pat_io_configuration_history import _configuration
from .pat_io_correspondence import _Program
from .pat_io_board_history import digest


def _case(setup, supplied):
    require(type(supplied) is dict and type(supplied.get('definition')) is dict, 'PAT_IO_CLOCK_CASE')
    scenario=supplied['definition'].get('scenario')
    require(type(scenario) is str and scenario in {'start_run_equal','wall_clock_regression','clock_epoch_mismatch'}, 'PAT_IO_CLOCK_CASE')
    delayed=scenario=='start_run_equal'; count=1 if delayed else 2
    program=_Program(setup); a=program.artifact
    control=({'at':'reserved_before_begin','guardDelayMs':99} if delayed else
        {'at':'pending','action':'regress_wall_by_one' if scenario=='wall_clock_regression' else 'invalidate_clock_mapping',
         'recovery':'new_epoch_reopen_and_reconcile'})
    checks=('due_equals_reserved_run_limit,start_excluded_receipt,no_board_fence' if delayed else
        'invalid_clock_no_continuation,new_epoch_retained,no_reset,no_suffix' if scenario=='wall_clock_regression' else
        'invalid_mapping_no_continuation,new_epoch_retained,no_rebinding,no_suffix')
    definition=dict(scenario=scenario,window='start_run' if delayed else 'ordinary',stepCount=count,control=control,
        expected=dict(activations=0 if delayed else 1,completedCycles=0,canceledActivations=0 if delayed else 1,
            completionContract='failed',settledAndQuiescent=True,unresolvedOperations=0,checks=checks.split(',')),schedulerTickCeiling=64)
    primitive=program.model.details[program.model.target]['primitive']
    body=dict(kind='fixed_challenge',definition=definition,targetRole='gpio' if primitive=='gpio_pulse' else 'pwm',
        programDigest=program.pat_digest,plannedChildOperations=count,schedulerTickCeiling=64)
    body['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',body)
    require(canonical(supplied)==canonical(body),'PAT_IO_CLOCK_CASE')
    require(a['parameters']=={} and len(a['steps'])==count and
        a['timingBudget']==dict(latestStartOffsetMs=200 if delayed else 100,latestCompletionOffsetMs=1000,maxRunSumMs=100*count),
        'PAT_IO_CLOCK_PROGRAM')
    detail=program.model.details[program.model.target]
    arguments={'durationMs':1 if delayed else 10}
    arguments.update({'level':1} if primitive=='gpio_pulse' else dict(frequencyHz=detail['envelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8))
    for i,step in enumerate(a['steps']):
        require(step==dict(stepId='step:'+str(i),role='io',actionId=program.action,
            arguments={k:{'literal':v} for k,v in arguments.items()},
            timing=dict(notBeforeOffsetMs=0,latestStartOffsetMs=(200 if delayed else 100) if i==0 else 999,
                latestCompletionOffsetMs=1000,maxRunMs=100)), 'PAT_IO_CLOCK_PROGRAM')
    return scenario


def inspect_clock_transcript(references, files, configuration, configuration_files, *, expected_setup, expected_case):
    transcript=_read(references,files,expected_setup,clock_profile=True)
    snapshots=_configuration(transcript,references,files,configuration,configuration_files)
    scenario=_case(expected_setup,expected_case)
    initial=[('lower',ORIGIN,True,None),('submit',ORIGIN,True,None),('drive:procedure',ORIGIN,True,None)]
    if scenario=='start_run_equal':
        points=['reserved_before_begin']; opens=1
        wanted=initial+[('drive:adapters',ORIGIN,True,None),('drive:procedure',ORIGIN+99,True,None)]
        require(transcript['calls'][3]['endClock']==ORIGIN+99,'PAT_IO_CLOCK_SCHEDULE')
    else:
        opens=2; code='CLOCK_REGRESSION' if scenario=='wall_clock_regression' else 'CLOCK_MAPPING_INVALID'
        points=['pending_wall_regression'] if scenario=='wall_clock_regression' else ['pending_mapping_invalidation','mapping_source_restored']
        bad_mono=ORIGIN if scenario=='wall_clock_regression' else ORIGIN-1
        wanted=initial+[('drive:adapters',ORIGIN,True,None),('drive:adapters',bad_mono,False,code)]
        if scenario=='clock_epoch_mismatch':wanted.append(('drive:adapters',ORIGIN,False,code))
        wanted += [('drive:adapters',ORIGIN+1,True,None),('resume',ORIGIN+1,False,'PROCEDURE_DEPENDENCY_UNRESOLVED'),
                   ('cancel',ORIGIN+1,True,None),('drive:cycle',ORIGIN+1,True,None)]
        points += ['before_new_epoch_open']
    actual=[(c['label'],c['clock'],c['returned'],c['outcome'].get('code')) for c in transcript['calls']]
    require(actual==wanted and len(transcript['opened'])==opens and
            [c['point'] for c in transcript['clockControls']]==points,'PAT_IO_CLOCK_SCHEDULE')
    require(all(c['returned'] or c['outcome']['exception']=='JournalError' for c in transcript['calls']), 'PAT_IO_CLOCK_EXCEPTION')
    # Source equality and paired records are structural evidence only. A future
    # semantic fold must derive all events, effects, sample ages and stop causes.
    result=dict(profile='hms.pat.io-clock-transcript-inspection/0.1',scenario=scenario,
        transcriptGrammarChecked=True,pairedConfigurationStructureChecked=True,exactClockControlScheduleChecked=True,
        checkpointsChecked=len(snapshots),runtimeOpens=opens,schedulerTicks=transcript['ticks'],
        clockControls=transcript['clockControls'],completeHistoryChecked=False,boardHistoryChecked=False,
        operationHistoryChecked=False,procedureHistoryChecked=False,independentOutcomeChecked=False,
        expectedResponseVerified=False,requiredMatrixCoverageChecked=False,configurationAttested=False,
        actualAggregateStorageEnforced=False,physicalMeasurementChecked=False,qualificationPassed=False)
    canonical(result)
    return result
