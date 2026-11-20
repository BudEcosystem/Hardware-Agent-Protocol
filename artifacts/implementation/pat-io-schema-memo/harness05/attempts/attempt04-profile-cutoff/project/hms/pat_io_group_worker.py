"""One current-candidate I/O matrix with shared bounded evidence capture.

Trusted isolated host component only. It executes original synthetic primitives,
retains every case and stops on any failure. It does not qualify/promote a PAT,
authenticate service configuration, or enforce an OS aggregate storage quota.
"""
import copy
import hashlib
import os
from pathlib import Path
import stat
import time

from .contracts import canonical
from .journal import JournalError
from .pat_compiler import compile_pat, compiler_digest
from .pat_contracts import PatError, require, snapshot
from .pat_io_combined_matrix import IoCombinedMatrixPolicy
from .pat_io_conflict_capture import ConflictIoTrialEngine
from .pat_io_group_budget import IoGroupBudget
from .pat_io_timing_worker import run_timing_challenge, SCHEDULES
from .pat_io_clock_capture import run_clock_challenge, SCENARIOS as CLOCK_SCENARIOS
from .pat_io_lifecycle_capture import run_lifecycle_challenge, SCENARIOS as LIFECYCLE_SCENARIOS
from .pat_io_authority_capture import run_authority_challenge
from .pat_io_resource_capture import run_resource_challenge
from .pat_io_trials import ORIGIN
from .pat_simulation_contracts import decode_case_input
from .pat_simulation_worker import _source_identity, _IMPORTED_IDENTITY
from .state_path import private_state_directory
from .synthetic_io_installation import implementation_digest

PROFILE = 'hms.pat.io-group-capture/0.1'
AUTHORITY_SCENARIOS = frozenset(('binding_before_dispatch', 'binding_pending', 'full_authority_withdrawal'))


def _identities():
    current = _source_identity()
    require(current == _IMPORTED_IDENTITY, 'PAT_IO_GROUP_IMPLEMENTATION_CHANGED')
    return dict(compilerDigest=compiler_digest(), driverDigest=implementation_digest(),
        workerDigest='sha256:' + hashlib.sha256(b'HMS-PAT-IO-GROUP-WORKER-v0.1\0' +
            canonical(dict(profile=PROFILE, installedClosure=current))).hexdigest())


def _write(path, data):
    with path.open('xb') as stream:
        require(stream.write(data) == len(data), 'PAT_IO_GROUP_SHORT_WRITE')
        stream.flush(); os.fsync(stream.fileno())


def _emit(root, name, value, budget):
    data = canonical(value); budget.record(len(data))
    _write(root/name, data)
    return dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def _state_bytes(directory):
    total = 0
    state = directory/'state'
    if not state.exists(): return 0
    for base, dirs, files in os.walk(state, followlinks=False):
        for name in dirs:
            require(stat.S_ISDIR((Path(base)/name).lstat().st_mode), 'PAT_IO_GROUP_STATE_KIND')
        for name in files:
            info = (Path(base)/name).lstat()
            require(stat.S_ISREG(info.st_mode), 'PAT_IO_GROUP_STATE_KIND')
            total += info.st_size
    return total


def _candidate(directory, case, options, ticket):
    artifact, descriptor = options['candidate'], options['descriptor']
    decoded = decode_case_input(case['domainCase']['input'])
    parameters = decoded.pop('parameters')
    expected = case['domainCase']['expected']
    if expected['staticOutcome'] != 'applicable':
        # Typed negative preflight does not need a runtime, namespace or authority.
        end = ORIGIN + artifact['timingBudget']['latestCompletionOffsetMs']
        try:
            compile_pat(artifact, parameters, {next(iter(artifact['roles'])): descriptor},
                origin_ms=ORIGIN, caller_deadline_ms=end, replay_namespace='group:negative:unused',
                procedure_key='group:negative:parent',
                operation_keys={s['stepId']:'group:negative:child:'+str(i) for i,s in enumerate(artifact['steps'])},
                context=decoded | {'deployment':options['installation']['topology']['deployment']})
        except PatError as error:
            expected_code = ('PAT_NOT_APPLICABLE' if expected['staticOutcome']=='not_applicable'
                             else expected['errorCode'])
            require(error.code == expected_code, 'PAT_IO_GROUP_NEGATIVE_OUTCOME')
            code = error.code
        else:
            require(False, 'PAT_IO_GROUP_NEGATIVE_ACCEPTED')
        return dict(profile='hms.pat.io-negative-capture/0.1',caseId=case['caseId'],
            programDigest=case['programDigest'], staticOutcome=expected['staticOutcome'],
            errorCode=code, executionPerformed=False,
            operationIds=[], schedulerTicks=0, qualificationPassed=False)
    engine = ConflictIoTrialEngine(directory,artifact,options['installation'],descriptor,group_budget=ticket)
    try:
        engine.lower(parameters,context=decoded); engine.submit(); engine.finish()
        engine.submit()
        try: engine.submit_conflict()
        except JournalError as error:
            require(error.code == 'KEY_CONFLICT','PAT_IO_GROUP_CONFLICT_RESULT')
        else: require(False,'PAT_IO_GROUP_CONFLICT_MISSING')
        engine.capture('test_final'); report=engine.report()
        result=dict(profile='hms.pat.io-candidate-capture/0.1',caseId=case['caseId'],
            programDigest=case['programDigest'],records=copy.deepcopy(engine.records),
            configuration=engine.configuration_manifest(),report=report,
            executionPerformed=True,closed=False,qualificationPassed=False)
    finally: engine.close()
    result['closed']=True
    return result


def _run_case(directory, case, options, ticket):
    if case['kind']=='candidate': return _candidate(directory,case,options,ticket)
    if case['kind']=='resource_challenge': runner=run_resource_challenge
    else:
        scenario=case['definition']['scenario']
        if scenario in SCHEDULES: runner=run_timing_challenge
        elif scenario in CLOCK_SCENARIOS: runner=run_clock_challenge
        elif scenario in LIFECYCLE_SCENARIOS: runner=run_lifecycle_challenge
        elif scenario in AUTHORITY_SCENARIOS: runner=run_authority_challenge
        else: require(False,'PAT_IO_GROUP_UNSUPPORTED_CASE')
    return runner(directory,**options,case_id=case['caseId'],group_budget=ticket)


def run_io_group(directory, *, candidate, installation, descriptor, challenge_bindings, limits=None):
    """Capture the complete generated matrix, or a retained incomplete attempt.

    Directory and all installed inputs are trusted setup, never PAT-controlled.
    No caller case selection, fault callbacks, retries or effect resumption exist.
    A failed result remains failed even if earlier cases finished successfully.
    """
    started=time.monotonic()
    options=dict(candidate=snapshot(candidate), installation=snapshot(installation),
        descriptor=snapshot(descriptor),challenge_bindings=snapshot(challenge_bindings))
    policy=IoCombinedMatrixPolicy(options['installation'])
    matrix=policy.generate(options['candidate'],options['descriptor'],options['challenge_bindings'],limits=limits)
    matrix_digest=policy.validate(matrix,options['candidate'],options['descriptor'],options['challenge_bindings'],limits=matrix['limits'])
    identity=_identities()
    root=private_state_directory(directory)
    require(not any(root.iterdir()),'PAT_IO_GROUP_DIRECTORY_NOT_EMPTY')
    budget=IoGroupBudget(matrix,started=started)
    refs=[]; results=[]; error=None
    try:
        for name,value in [('candidate.json',options['candidate']),('installation.json',options['installation']),
                           ('descriptor.json',options['descriptor']),('bindings.json',options['challenge_bindings']),
                           ('matrix.json',matrix),('implementation.json',identity)]:
            refs.append(_emit(root,name,value,budget))
        options['matrix']=matrix
        for index,case in enumerate(matrix['cases']):
            ticket=budget.begin(case['caseId'])
            name='case-%02d'%index
            trial=root/name; trial.mkdir(mode=0o700)
            result=_run_case(trial,case,options,ticket)
            if result['executionPerformed']:
                ticket.assert_evidence(result['configuration'])
                report=result['report']
                require(not report['unresolvedOperations'],'PAT_IO_GROUP_UNRESOLVED')
                operations,ticks=len(report['operationIds']),report['schedulerTicks']
            else: operations,ticks=0,0
            state_bytes=_state_bytes(trial); budget.observe_state(state_bytes)
            ref=_emit(root,name+'/manifest.json',result,budget)
            budget.end(ticket,operation_count=operations,scheduler_ticks=ticks)
            results.append(dict(caseId=case['caseId'],kind=case['kind'],manifest=ref,
                retainedStateBytes=state_bytes,operationCount=operations,schedulerTicks=ticks))
        require(_identities()==identity,'PAT_IO_GROUP_IMPLEMENTATION_CHANGED')
        budget.check()
    except BaseException as exc:
        budget.stop()
        error=dict(exception=type(exc).__name__,code=getattr(exc,'code',None),message=str(exc)[:1024])
    result=dict(profile=PROFILE,status='captured' if error is None else 'failed',
        matrixDigest=matrix_digest,artifactDigest=matrix['artifactDigest'],identities=identity,
        inputs=refs,cases=results,error=error,accounting=budget.snapshot(),
        allMatrixCasesCaptured=error is None,requiredMatrixCoverageChecked=False,
        independentOutcomeChecked=False,configurationAttested=False,implementationIdentityAttested=False,
        serializedEvidenceBudgetEnforced=True,actualAggregateStorageEnforced=False,
        qualificationPassed=False,physicalMeasurementChecked=False)
    data=canonical(result)
    try:
        budget.terminal(len(data),success=error is None)
    except PatError as exc:
        if error is not None: raise
        budget.stop()
        result.update(status='failed',allMatrixCasesCaptured=False,accounting=budget.snapshot(),
            error=dict(exception=type(exc).__name__,code=exc.code,message=str(exc)[:1024]))
        data=canonical(result); budget.terminal(len(data),success=False)
    _write(root/'result.json',data)
    return result
