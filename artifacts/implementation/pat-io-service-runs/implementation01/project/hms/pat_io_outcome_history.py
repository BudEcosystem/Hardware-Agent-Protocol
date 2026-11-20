"""Independent static timing and declared simulation outcome over complete trials.

This evaluates one retained trial, not a complete qualification matrix. No
compiler, policy planner, runtime, driver, filesystem or clock is consulted.
"""
from __future__ import annotations

from .contracts import SAFE_INTEGER, canonical, parse_json
from .pat_io_board_history import _tables, digest
from .pat_io_correspondence import _Program
from .pat_io_refusal_history import inspect_refusal_history
from .pat_io_transcript import ORIGIN, _read


class IoOutcomeHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_OUTCOME_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoOutcomeHistoryError(code)


def _extrema(domain):
    return (domain['enum'][0], domain['enum'][-1]) if 'enum' in domain else (domain['minimum'], domain['maximum'])


def _static(program, supplied):
    """Independently reconstruct the exact closed producer contract."""
    artifact, descriptor, domains = program.artifact, program.descriptor, program.domains
    parent = artifact['timingBudget']; rows = []; admission_low = admission_high = 0
    require(admission_high < parent['latestStartOffsetMs'], 'PARENT_START')
    for step in artifact['steps']:
        expression = step['arguments']['durationMs']
        low, high = (_extrema(domains[expression['parameter']]) if 'parameter' in expression else
                     (expression['literal'], expression['literal']))
        window = step['timing']
        require(1 <= low <= high < window['maxRunMs'], 'DURATION_BUDGET')
        start_low = max(admission_low, window['notBeforeOffsetMs'])
        start_high = max(admission_high, window['notBeforeOffsetMs'])
        finish_low, finish_high = start_low + low, start_high + high
        require(all(type(n) is int and 0 <= n <= SAFE_INTEGER for n in
                    (start_low, start_high, finish_low, finish_high, admission_low + 60000)), 'INTEGER_BOUNDS')
        require(start_high < window['latestStartOffsetMs'], 'START_WINDOW')
        require(finish_high < window['latestCompletionOffsetMs'], 'COMPLETION_WINDOW')
        require(finish_high < admission_low + 60000, 'LEASE_WINDOW')
        require(finish_high < parent['latestCompletionOffsetMs'], 'PARENT_WINDOW')
        rows.append(dict(stepId=step['stepId'], durationMinMs=low, durationMaxMs=high,
            admissionMinOffsetMs=admission_low, admissionMaxOffsetMs=admission_high,
            startMinOffsetMs=start_low, startMaxOffsetMs=start_high,
            finishMinOffsetMs=finish_low, finishMaxOffsetMs=finish_high,
            earliestLeaseExpiryOffsetMs=min(window['latestCompletionOffsetMs'], admission_low + 60000)))
        admission_low, admission_high = finish_low, finish_high
    applicable = {key: value | ({'enum': list(value['enum'])} if 'enum' in value else {}) for key, value in domains.items()}
    context = {'trigger.taskKind': artifact['taskKind'], 'trigger.inputProfile': artifact['inputProfile'],
               'context.evidenceMode': 'simulation'}
    for predicate in artifact['applicability']['all']:
        field = predicate['field']
        if not field.startswith('parameters.'):
            require(predicate['literal'] == context[field], 'EMPTY_APPLICABILITY')
            continue
        domain = applicable[field[len('parameters.'):]]
        lo, hi = ((predicate['literal'], predicate['literal']) if predicate['op'] == 'equals' else
                  (predicate['minimum'], predicate['maximum']))
        domain['minimum'] = max(domain['minimum'], lo); domain['maximum'] = min(domain['maximum'], hi)
    nominal = {}
    for key, domain in applicable.items():
        require(domain['minimum'] <= domain['maximum'], 'EMPTY_APPLICABILITY')
        if 'enum' in domain:
            domain['enum'] = [n for n in domain['enum'] if domain['minimum'] <= n <= domain['maximum']]
            require(bool(domain['enum']), 'EMPTY_APPLICABILITY')
            domain['minimum'], domain['maximum'] = _extrema(domain)
            nominal[key] = domain['enum'][len(domain['enum']) // 2]
        else:
            nominal[key] = (domain['minimum'] + domain['maximum']) // 2
    schedule = dict(profile='hms.pat.io-clock.zero-latency/0.1', dispatchLagMs=0, guardLagMs=0,
        pollLagMs=0, settlementLagMs=0, steps=rows,
        maxOriginMs=SAFE_INTEGER-parent['latestCompletionOffsetMs'], correlationsOverapproximated=True, hostTimingGuaranteed=False)
    expected = dict(profile='hms.pat.io-static-contract/0.1', policy='hms.pat.eval.sqlite-finite-io-sequence/0.1',
        artifactDigest=program.pat_digest, descriptorDigest=digest(b'HMS-PAT-IO-DESCRIPTOR-v0.1', descriptor),
        installationDigest=program.model.installation_digest, driverDigest=descriptor['driverDigest'],
        role=program.role, actionId=program.action, primitive=program.model.details[program.model.target]['primitive'],
        declaredDomains=domains, applicableDomains=applicable, nominalParameters=nominal, schedule=schedule, qualificationPassed=False)
    require(canonical(supplied) == canonical(expected), 'STATIC_CONTRACT')
    return expected


def inspect_static_policy(*, expected_setup):
    """Check whole declared domain before applicability; no execution claim."""
    result = dict(profile='hms.pat.io-static-policy-inspection/0.1',
        derivedContract=_static(_Program(expected_setup), expected_setup['static_contract']),
        staticTimingPolicyChecked=True, wholeDeclaredDomainChecked=True,
        independentOutcomeChecked=False, configurationAttested=False, compilerIdentityAttested=False, qualificationPassed=False)
    canonical(result)
    return result


def _outcome(transcript, program, history):
    tables = _tables(transcript, transcript['checkpoints'][-1])
    parent = history['procedures']['derivedProcedure']
    operations = {row['id']: row for row in tables['operations']}
    steps = sorted(tables['pr_steps'], key=lambda row: row['ordinal'])
    unresolved = history['operations']['unresolvedOperationIds']
    board = history['board']; quiescent = board['modeledBoardIdle'] and not unresolved and not tables['claims']
    failed_child = any(row['state'] in {'failed', 'canceled', 'rejected_before_dispatch', 'rejected_before_start'} for row in operations.values())
    denied_parent = any(row['kind'] == 'parent_before_acceptance' for row in history['refusalsChecked'])
    lower_refused = history['correspondence']['parameterOutcome'] == 'refused'
    completed = parent is not None and parent['executionState'] == 'completed'
    status = ('satisfied' if completed else 'failed' if failed_child or denied_parent or lower_refused or
              parent is not None and parent['executionState'] in {'failed', 'canceled', 'expired'} else 'incomplete')
    cycle_count = sum(row['completedCycles'] for row in board['instances'])
    activation_count = sum(row['activations'] for row in board['instances'])
    cancel_count = sum(row['canceledActivations'] for row in board['instances'])
    schedule_rows = []; zero_lag = parent_timely = nominal_timing = None
    parent_completed_at = None
    if completed:
        count = len(program.artifact['steps'])
        require(quiescent and len(steps) == len(operations) == count and
                all(row['operation_id'] in operations and operations[row['operation_id']]['state'] == 'completed' and
                    operations[row['operation_id']]['verification'] == 'unverified' for row in steps), 'COMPLETION_AUTHORITY')
        target = program.model.target[0]
        require(all((r['activations'], r['completedCycles'], r['canceledActivations']) ==
                    ((count, count, 0) if r['instanceId'] == target else (0, 0, 0)) for r in board['instances']), 'COMPLETION_EFFECTS')
        receipts = {row['operation']: parse_json(row['document']) for row in tables['io_receipts']}
        require(set(receipts) == set(operations) and all(r['state'] == 'completed' for r in receipts.values()), 'COMPLETION_RECEIPTS')
        expected_admission = ORIGIN; zero_lag = True
        for row, instruction in zip(steps, program.artifact['steps']):
            op = row['operation_id']; receipt = receipts[op]
            start = max(expected_admission, ORIGIN + instruction['timing']['notBeforeOffsetMs'])
            finish = start + receipt['intent']['arguments']['durationMs']
            accepted = [event['time_ms'] for event in tables['events'] if event['operation_id'] == op and event['kind'] == 'accepted']
            board_done = [event['clock'] for event in board['transitions'] if event['operationId'] == op and event['state'] == 'completed']
            settled = [event['clock'] for event in history['operations']['transitions'] if event['operationId'] == op and event['state'] == 'completed']
            require(len(accepted) == len(board_done) == 1 and bool(settled), 'COMPLETION_TIMES')
            matched = (accepted[0] == expected_admission and receipt['startedMonoMs'] == start and
                       receipt['budgetOriginMonoMs'] == start and receipt['dueMonoMs'] == finish and
                       board_done[0] == finish and min(settled) == finish)
            zero_lag = zero_lag and matched
            schedule_rows.append(dict(stepId=instruction['stepId'], operationId=op,
                expectedAdmissionMs=expected_admission, actualAdmissionMs=accepted[0], expectedStartMs=start,
                actualStartMs=receipt['startedMonoMs'], expectedFinishMs=finish,
                actualBoardCompletionMs=board_done[0], actualAuthorityCompletionMs=min(settled), matched=matched))
            expected_admission = finish
        completion_events = [event for event in tables['pr_events'] if event['kind'] == 'state_changed' and
                             parse_json(event['payload'])['state'] == 'completed']
        require(len(completion_events) == 1, 'PARENT_COMPLETION_TIME')
        parent_completed_at = completion_events[0]['time_ms']
        parent_timely = parent_completed_at < ORIGIN + program.artifact['timingBudget']['latestCompletionOffsetMs']
        nominal_timing = zero_lag and parent_timely and parent_completed_at == expected_admission
    return dict(contractStatus=status, requiredCompletedSteps=[s['stepId'] for s in program.artifact['steps']],
        actualParentState=None if parent is None else parent['executionState'],
        activations=activation_count, completedCycles=cycle_count, canceledActivations=cancel_count,
        modeledBoardIdle=board['modeledBoardIdle'], settledAndQuiescent=quiescent,
        unresolvedOperationIds=unresolved, parentCompletedAtMs=parent_completed_at,
        parentCompletionBeforeDeadline=parent_timely, zeroLagChildScheduleMatched=zero_lag,
        nominalTimingSatisfied=nominal_timing, concreteSchedule=schedule_rows,
        nominalCompletionSatisfied=status == 'satisfied' and quiescent and nominal_timing is True,
        physicalObjectiveVerified=False)


def inspect_trial_outcome(references, files, configuration, configuration_files, *,
                          expected_setup, expected_authority, expected_faults=None):
    """Evaluate the declared capability-completion contract on one exact history.

Failed fault trials may be correct fault responses; this API does not decide
whether the mandatory fault matrix is complete or whether a PAT may be promoted.
"""
    transcript = _read(references, files, expected_setup); program = _Program(expected_setup)
    static = _static(program, expected_setup['static_contract'])
    history = inspect_refusal_history(references, files, configuration, configuration_files,
        expected_setup=expected_setup, expected_authority=expected_authority, expected_faults=expected_faults)
    outcome = _outcome(transcript, program, history)
    result = dict(profile='hms.pat.io-trial-outcome-inspection/0.1', staticTimingPolicyChecked=True,
        wholeDeclaredDomainChecked=True, completeHistoryChecked=True, simulationOutcomeEvaluated=True,
        independentOutcomeChecked=outcome['contractStatus'] != 'incomplete',
        staticContract=static, outcome=outcome, history=history,
        configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
        requiredMatrixCoverageChecked=False, allFaultScenariosChecked=False, qualificationPassed=False)
    canonical(result)
    return result
