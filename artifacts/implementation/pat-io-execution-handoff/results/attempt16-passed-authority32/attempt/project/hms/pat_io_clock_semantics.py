"""Pure composition for the three fixed finite-I/O clock challenges.

Clock controls are inputs, never proof of an effect. Derive each private handoff
from exact controls, prior durable state and paired configuration, then consume
it in the ordinary independent folds. Captured clocks and events stay unchanged.
No runtime, producer, provider, SQL, filesystem or live clock is used here.
"""
from .contracts import canonical, parse_json
from .pat_io_transcript import _read, ORIGIN
from .pat_io_clock_history import inspect_clock_transcript
from .pat_io_configuration_history import _configuration, _validated_configuration_history
from .pat_io_correspondence import _Program, _inspect as _correspondence
from .pat_io_board_history import _tables, _reduce as _board
from .pat_io_operation_history import _fold as _operations
from .pat_io_procedure_history import _fold as _procedures
from .pat_io_authorized_history import _guards
from .pat_io_refusal_history import _refusals
from .pat_io_observation_history import _samples
from .pat_io_outcome_history import _static, _outcome


class IoClockHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_CLOCK_HISTORY_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoClockHistoryError(code)


def _one(rows, code):
    require(len(rows) == 1, code)
    return rows[0]


def _contexts(transcript, snapshots, scenario):
    """Derive exceptions to same-clock sampling/events; none is caller supplied."""
    frames = [(s, _tables(transcript, s['checkpoint'])) for s in snapshots]
    def at(phase, label):
        return _one([(s, t) for s, t in frames if
                     (s['value']['phase'], s['value']['label']) == (phase, label)], 'PHASE')
    context = dict(floors={}, ceilings={}, times={}, no_starts={}, board_no_starts={},
                   failed=set(), sample_clocks={}, failures=[])
    start, start_tables = at(4, 'drive:adapters:before')
    finish, finish_tables = at(4, 'drive:adapters:after')
    prior = _one(start_tables['operations'], 'OPERATION')
    require(prior['state'] == 'accepted' and prior['may_have_acted'] == 0 and
            prior['cancel_state'] == 'not_requested' and start_tables['claims'] and
            not any(start_tables[k] for k in ('io_dispatch_links', 'io_receipts', 'io_owners', 'io_fences')),
            'START_CONTEXT')
    operation = _one(finish_tables['operations'], 'OPERATION'); op = operation['id']
    require(prior['id'] == op, 'OPERATION')
    link = parse_json(_one(finish_tables['io_dispatch_links'], 'DISPATCH')['document'])
    require(link['checkpoint'] == link['budgetOriginMonoMs'] == ORIGIN and
            start['value']['wallMs'] == start['value']['monotonicMs'] == ORIGIN, 'RESERVATION_CLOCK')
    receipt = parse_json(_one(finish_tables['io_receipts'], 'RECEIPT')['document'])
    if scenario == 'start_run_equal':
        key = finish['checkpoint']['record']
        timing = parse_json(operation['intent'])['timing']
        lease = parse_json(operation['admission'])['lease_expires_ms']
        now = finish['value']['monotonicMs']
        require(now == finish['value']['wallMs'] == ORIGIN + 99 and
                timing['notBeforeUnixMs'] <= ORIGIN < now < timing['latestStartUnixMs'] and
                now < timing['latestCompletionUnixMs'] and now < lease and
                now < link['budgetOriginMonoMs'] + timing['maxRunMs'] and
                now + receipt['intent']['arguments']['durationMs'] == link['budgetOriginMonoMs'] + timing['maxRunMs'],
                'DURATION_BOUNDARY')
        require(receipt['state'] == operation['state'] == 'rejected_before_start' and
                receipt['result']['reason'] == 'duration_budget_excluded' and
                operation['may_have_acted'] == 0 and not finish_tables['io_fences'], 'NO_START')
        dispatch = _one([e for e in finish_tables['events'] if e['operation_id'] == op and
                         e['kind'] == 'dispatch_claimed'], 'DISPATCH')
        context['times'][key, op, dispatch['sequence']] = ORIGIN
        context['no_starts'][op] = 'duration_budget_excluded'
        context['board_no_starts'][key, op] = 'duration_budget_excluded'
        context['sample_clocks'][key] = ORIGIN
        return context

    require(operation['state'] == 'running' and operation['may_have_acted'] == 1 and
            receipt['state'] == 'pending' and receipt['sequence'] == 1 and
            finish_tables['claims'] and finish_tables['io_owners'], 'PENDING_CONTEXT')
    floor = int(dict((r['key'], r['value']) for r in finish_tables['meta'])['last_clock'])
    require(floor == ORIGIN and finish['value']['wallMs'] == finish['value']['monotonicMs'] == ORIGIN,
            'CLOCK_FLOOR')
    before_reopen = _one([(s, t) for s, t in frames if s['value']['label'] == 'before_reopen'], 'REOPEN')
    end = before_reopen[0]['checkpoint']['record']
    held = [(s, t) for s, t in frames if finish['checkpoint']['record'] < s['checkpoint']['record'] <= end]
    expected_labels = [(5, 'drive:adapters:before'), (5, 'drive:adapters:after_error')]
    if scenario == 'clock_epoch_mismatch':
        expected_labels += [(6, 'drive:adapters:before'), (6, 'drive:adapters:after_error')]
    expected_labels += [(5 if scenario == 'wall_clock_regression' else 6, 'before_reopen')]
    require([(s['value']['phase'], s['value']['label']) for s, _ in held] == expected_labels, 'FAULT_PHASES')
    calls = {c['phase']: c for c in transcript['calls']}
    mapping_invalid = False
    for s, tables in held:
        value = s['value']; key = s['checkpoint']['record']
        # A clock failure occurs before observation refresh or any durable work.
        # Compare with the last good phase, including intervening before frames.
        require(tables == finish_tables and s['tables'] == finish['tables'] and
                s['resolver'] == finish['resolver'], 'FAILED_CLOCK_MUTATION')
        if value['wallMs'] < floor: context['floors'][key] = floor
        if value['monotonicMs'] < ORIGIN: context['ceilings'][key] = ORIGIN
        if value['label'] != 'drive:adapters:after_error': continue
        if scenario == 'wall_clock_regression':
            require(value['wallMs'] < floor and value['monotonicMs'] == ORIGIN, 'WALL_REGRESSION')
            code = 'CLOCK_REGRESSION'
        else:
            require(value['wallMs'] == ORIGIN, 'MAPPING_REGRESSION')
            if not mapping_invalid:
                require(value['monotonicMs'] < ORIGIN, 'MAPPING_REGRESSION')
                mapping_invalid = True
            else:
                require(value['monotonicMs'] == ORIGIN, 'MAPPING_LATCH')
            code = 'CLOCK_MAPPING_INVALID'
        call = calls[value['phase']]
        require(not call['returned'] and call['outcome']['code'] == code and
                call['outcome']['exception'] == 'JournalError', 'FAULT_CAUSE')
        context['failed'].add(key)
        context['failures'].append(dict(phase=value['phase'], cause=code, allTablesUnchanged=True,
            authorityClaimsRetained=True, boardOutputStillPending=True, observationRefreshFailed=True))
    reopened, reopened_tables = _one([(s, t) for s, t in frames if s['value']['label'] == 'after_reopen'], 'REOPEN')
    changed_operation = _one(reopened_tables['operations'], 'REOPEN')
    require(changed_operation['id'] == op and changed_operation['state'] == 'outcome_unknown' and
            reopened_tables['claims'] == finish_tables['claims'] and not reopened_tables['io_owners'], 'REOPEN_OWNERSHIP')
    for table in ('namespaces', 'series', 'pr_keys', 'pr_steps', 'replay_keys', 'resource_floors',
                  'io_dispatch_links', 'io_authority_receipts'):
        require(reopened_tables[table] == finish_tables[table], 'REOPEN_RETAINED_IDENTITY')
    stopped = parse_json(_one(reopened_tables['io_receipts'], 'REOPEN')['document'])
    require(stopped['state'] == 'canceled' and stopped['result']['reason'] == 'board_owner_reopened' and
            stopped['ownerEpoch'] == 1 and reopened['value']['ownerEpoch'] == 2 and
            reopened['value']['wallMs'] == reopened['value']['monotonicMs'] == ORIGIN + 1, 'REOPEN_STOP')
    return context


def inspect_clock_challenge(references, files, configuration, configuration_files, *,
                            expected_setup, expected_authority, expected_case):
    """Validate one exact clock challenge; this never qualifies a whole PAT."""
    structural = inspect_clock_transcript(references, files, configuration, configuration_files,
        expected_setup=expected_setup, expected_case=expected_case)
    scenario = structural['scenario']
    transcript = _read(references, files, expected_setup, clock_profile=True)
    snapshots = _configuration(transcript, references, files, configuration, configuration_files)
    require(expected_authority['grantChanges'] == [], 'GRANT_PLAN')
    contexts = _contexts(transcript, snapshots, scenario)
    transcript, snapshots, permissions, denied, config = _validated_configuration_history(
        references, files, configuration, configuration_files, expected_setup=expected_setup,
        expected_authority=expected_authority, clock_profile=True, checked_sample_ceilings=contexts['ceilings'])
    require(not denied and all(p['invokes'] and p['read'] for p in permissions.values()), 'PERMISSION_CONTEXT')
    program = _Program(expected_setup); static = _static(program, expected_setup['static_contract'])
    correspondence = _correspondence(transcript, expected_setup)
    parents, children, refusals = _refusals(transcript, snapshots, permissions)
    causes, guards = _guards(transcript, snapshots, permissions, denied, checked_clock_failures=contexts['failed'])
    board = _board(transcript, expected_setup, checked_causes=causes, checked_no_starts=contexts['board_no_starts'])
    operations = _operations(transcript, expected_setup, checked_refusals=children,
        checked_clock_floors=contexts['floors'], checked_event_times=contexts['times'], checked_no_starts=contexts['no_starts'])
    procedures = _procedures(transcript, checked_refusals=parents)
    sampling = _samples(transcript, snapshots, checked_failed_phases=contexts['failed'],
                        checked_sample_clocks=contexts['sample_clocks'])
    history = dict(configuration=config, correspondence=correspondence, refusalsChecked=refusals,
        guardsChecked=guards, board=board, operations=operations, procedures=procedures, sampling=sampling,
        clockFailuresChecked=contexts['failures'], configurationHistoryChecked=True, patCorrespondenceChecked=True,
        boardHistoryChecked=True, operationHistoryChecked=True, procedureHistoryChecked=True,
        observationSampleSemanticsChecked=True)
    outcome = _outcome(transcript, program, history)
    effects = (0, 0, 0) if scenario == 'start_run_equal' else (1, 0, 1)
    require(outcome['contractStatus'] == 'failed' and outcome['settledAndQuiescent'] and
            not outcome['unresolvedOperationIds'] and
            tuple(outcome[k] for k in ('activations', 'completedCycles', 'canceledActivations')) == effects,
            'EXPECTED_OUTCOME')
    final = _tables(transcript, transcript['checkpoints'][-1])
    require(len(final['operations']) == 1 and not final['claims'] and not final['io_owners'] and
            all(row['operation_id'] is None for row in final['pr_steps'] if row['ordinal'] > 0), 'NO_SUFFIX')
    require(procedures['derivedProcedure']['executionState'] ==
            ('failed' if scenario == 'start_run_equal' else 'canceled'), 'PARENT_SETTLEMENT')
    result = dict(profile='hms.pat.io-clock-challenge-inspection/0.1', scenario=scenario, caseId=expected_case['caseId'],
        exactClockControlScheduleChecked=True, expectedResponseVerified=True, completeHistoryChecked=True,
        independentOutcomeChecked=True, staticTimingPolicyChecked=True, wholeDeclaredDomainChecked=True,
        staticContract=static, history=history, outcome=outcome, configurationAttested=False,
        compilerIdentityAttested=False, requiredMatrixCoverageChecked=False, allFaultScenariosChecked=False,
        actualAggregateStorageEnforced=False, physicalMeasurementChecked=False, qualificationPassed=False)
    canonical(result)
    return result
