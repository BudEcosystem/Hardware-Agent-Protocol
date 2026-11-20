"""Independent sample timing/value checks for retained finite-I/O histories.

The finite trial profile samples before each driven phase. Values are simulated
activation counters, not measured electrical state or proof of task success.
"""
from __future__ import annotations

from .contracts import canonical, parse_json
from .pat_io_authorized_history import _guards, inspect_authorized_history
from .pat_io_board_history import _reduce as _board, _tables
from .pat_io_configuration_history import _validated_configuration_history
from .pat_io_correspondence import _inspect as _correspondence
from .pat_io_recovery_history import _faults, _interruptions, inspect_recovery_history


class IoObservationHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_OBSERVATION_' + code
        super().__init__(self.code)


def require(value, code):
    if not value:
        raise IoObservationHistoryError(code)


def _samples(transcript, snapshots, *, checked_failed_phases=None, checked_sample_clocks=None):
    """Consume histories whose configuration and board semantics already passed."""
    before = {}; previous = None
    checked_failed_phases = set() if checked_failed_phases is None else checked_failed_phases
    checked_sample_clocks = {} if checked_sample_clocks is None else checked_sample_clocks
    consumed_failures, consumed_clocks = set(), set()
    result = dict(snapshotsChecked=0, initialSampleBatches=0, reopenSampleBatches=0,
                  driveSampleBatches=0, samplesProduced=0, cachedSnapshots=0,
                  valueReadingsChecked=0, laggingSnapshots=0)
    for snapshot in snapshots:
        value = snapshot['value']; phase, label = value['phase'], value['label']
        execution = _tables(transcript, snapshot['checkpoint'])
        counts = {row['instance']: row['activations'] for row in execution['io_effects']}
        observations = {(row['instance'], row['property']): parse_json(row['document'])
                        for row in snapshot['tables']['reg_observations']}
        result['snapshotsChecked'] += 1
        key = snapshot['checkpoint']['record']
        if key in checked_failed_phases:
            require(label == 'drive:adapters:after_error' and phase in before and observations == previous, 'FAILED_SAMPLE')
            before.pop(phase); sampled = None; result['cachedSnapshots'] += 1
            consumed_failures.add(key)
        elif label in {'baseline', 'after_reopen'}:
            sampled = counts
            result['initialSampleBatches' if label == 'baseline' else 'reopenSampleBatches'] += 1
            require(all(o['sequence'] == 1 for o in observations.values()), 'OPEN_SEQUENCE')
        elif label in {'drive:cycle:after', 'drive:cycle:after_error',
                       'drive:procedure:after', 'drive:procedure:after_error',
                       'drive:adapters:after', 'drive:adapters:after_error'}:
            require(phase in before and previous is not None, 'PHASE_PAIRING')
            sampled = before.pop(phase)
            result['driveSampleBatches'] += 1
            require(all(o['streamEpoch'] == previous[key]['streamEpoch'] and
                        o['sequence'] == previous[key]['sequence'] + 1
                        for key, o in observations.items()), 'SAMPLE_SEQUENCE')
        else:
            sampled = None
            result['cachedSnapshots'] += 1
            require(observations == previous, 'NON_SAMPLE_PHASE')
        if sampled is not None:
            sample_clock = checked_sample_clocks.get(key, value['monotonicMs'])
            if key in checked_sample_clocks:
                require(label == 'drive:adapters:after' and sample_clock < value['monotonicMs'], 'SAMPLE_CLOCK_CONTEXT')
                consumed_clocks.add(key)
            require(all(o['receipt']['ticksMs'] == sample_clock
                        for o in observations.values()), 'SAMPLE_CLOCK')
            require(all(o['value'] is True if key[1] == 'ready' else
                        type(o['value']) is int and o['value'] == sampled[key[0]]
                        for key, o in observations.items()), 'SAMPLE_VALUE')
            result['samplesProduced'] += len(observations)
        if label in {'drive:cycle:before', 'drive:procedure:before', 'drive:adapters:before'}:
            require(phase not in before, 'PHASE_PAIRING')
            before[phase] = counts
        values = {key[0]: o['value'] for key, o in observations.items() if key[1] == 'value'}
        result['valueReadingsChecked'] += len(values)
        result['laggingSnapshots'] += any(sample < counts[instance] for instance, sample in values.items())
        previous = observations
    require(not before and result['initialSampleBatches'] == 1, 'PHASE_PAIRING')
    require(consumed_failures == set(checked_failed_phases) and consumed_clocks == set(checked_sample_clocks), 'UNUSED_CLOCK_CONTEXT')
    return result


def inspect_observation_history(references, files, configuration, configuration_files, *,
                                expected_setup, expected_authority, expected_faults=None):
    """Validate sample order/value against trusted configuration and board history.

This component does not attest the full authority/parent event history. It also
accepts pre-effect permission-denial fixtures whose observations can be checked
independently. Use inspect_observed_execution_history for full composition; that
API preserves every unsupported-case refusal of the existing history checkers.
"""
    arguments = dict(expected_setup=expected_setup, expected_authority=expected_authority)
    transcript, snapshots, permissions, denied, config = _validated_configuration_history(
        references, files, configuration, configuration_files, **arguments)
    correspondence = _correspondence(transcript, expected_setup)
    recovery = None; interruptions = []; settlements = []
    if expected_faults is not None:
        recovery, interruptions, settlements = _interruptions(transcript, _faults(expected_faults))
    causes, guards = _guards(transcript, snapshots, permissions, denied, recovery=recovery)
    board = _board(transcript, expected_setup, checked_causes=causes)
    result = dict(profile='hms.pat.io-observation-history-inspection/0.1',
                  observationSampleSemanticsChecked=True, sampling=_samples(transcript, snapshots),
                  configurationHistoryChecked=True, trustedGrantPlanMatched=True, patCorrespondenceChecked=True,
                  boardHistoryChecked=True, operationHistoryChecked=False, procedureHistoryChecked=False,
                  configuration=config, correspondence=correspondence, board=board, guardsChecked=guards,
                  trustedFaultPlanMatched=expected_faults is not None, faultsChecked=interruptions,
                  settlementsChecked=settlements,
                  configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
                  staticTimingPolicyChecked=False, allFaultScenariosChecked=False,
                  independentOutcomeChecked=False, qualificationPassed=False)
    canonical(result)
    return result


def inspect_observed_execution_history(references, files, configuration, configuration_files, *,
                                       expected_setup, expected_authority, expected_faults=None):
    """Join sample validation with the full authority and parent history checks.

There is no fallback from an unsupported execution history to a sample-only
verdict. No supplied verdict, producer implementation, I/O or new effect is used.
"""
    arguments = dict(expected_setup=expected_setup, expected_authority=expected_authority)
    if expected_faults is None:
        history = inspect_authorized_history(references, files, configuration, configuration_files, **arguments)
    else:
        history = inspect_recovery_history(references, files, configuration, configuration_files,
                                           expected_faults=expected_faults, **arguments)
    observations = inspect_observation_history(references, files, configuration, configuration_files,
                                               expected_faults=expected_faults, **arguments)
    result = dict(profile='hms.pat.io-observed-execution-history-inspection/0.1',
                  observationSampleSemanticsChecked=True, operationHistoryChecked=True, procedureHistoryChecked=True,
                  history=history, observations=observations,
                  configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
                  staticTimingPolicyChecked=False, allFaultScenariosChecked=False,
                  independentOutcomeChecked=False, qualificationPassed=False)
    canonical(result)
    return result
