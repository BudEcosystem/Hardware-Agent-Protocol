"""Execute exact forward-time challenges from a validated combined I/O matrix.

One fresh private runtime per call. This component implements eight required
scenarios; it cannot pass a group, skip unsupported scenarios or promote a PAT.
"""
import copy

from .contracts import canonical
from .pat_contracts import require, snapshot
from .pat_io_combined_matrix import IoCombinedMatrixPolicy
from .pat_io_configuration_capture import ConfiguredIoTrialEngine
from .pat_io_trials import ORIGIN, MAX_RECORDS, MAX_OUTPUT_BYTES


# Explicit adapter/procedure phases prevent a late poll from being silently
# replaced with the nominal next_event() schedule.
SCHEDULES = {
    'not_before_boundary': ((0,'adapters'),(49,'adapters'),(50,'adapters'),(60,'adapters'),(60,'procedure')),
    'latest_start_before': ((49,'adapters'),(50,'adapters'),(50,'procedure')),
    'latest_start_equal': ((50,'adapters'),(50,'procedure')),
    'run_completion_equal': ((0,'adapters'),(100,'adapters'),(100,'procedure')),
    'wall_completion_equal': ((5,'adapters'),(50,'adapters'),(50,'procedure')),
    'lease_wait_before': ((0,'adapters'),(59997,'adapters'),(59998,'adapters'),(59999,'adapters'),(59999,'procedure')),
    'lease_wait_equal': ((60000,'adapters'),(60000,'procedure')),
    'late_parent_reporting': ((0,'adapters'),(1,'adapters'),(1000,'procedure')),
}


def run_timing_challenge(directory, *, matrix, candidate, installation, descriptor, challenge_bindings, case_id):
    """Validate the full trusted plan, then run one identified supported case.

No arbitrary callback, custom timing list, effect-bearing retry or state reset
is accepted. The caller must retain the returned manifest and raw directory.
Group execution, supervision and aggregate storage admission remain separate.
"""
    matrix = snapshot(matrix, 'PAT_IO_TIMING_MATRIX')
    policy = IoCombinedMatrixPolicy(installation)
    matrix_digest = policy.validate(matrix, candidate, descriptor, challenge_bindings,
                                    limits=matrix.get('limits'))
    require(type(case_id) is str, 'PAT_IO_TIMING_CASE')
    cases = [case for case in matrix['cases'] if case['caseId'] == case_id]
    require(len(cases) == 1, 'PAT_IO_TIMING_CASE')
    case = cases[0]
    require(case['kind'] == 'fixed_challenge' and case['definition']['scenario'] in SCHEDULES,
            'PAT_IO_TIMING_UNSUPPORTED_CASE')
    scenario = case['definition']['scenario']; schedule = SCHEDULES[scenario]
    require(case['plannedChildOperations'] == 1 and 1+len(schedule) <= case['schedulerTickCeiling'], 'PAT_IO_TIMING_RESERVATION')
    artifact, = [row['artifact'] for row in matrix['programs'] if row['digest'] == case['programDigest']]
    engine = ConfiguredIoTrialEngine(directory, artifact, installation, descriptor)
    try:
        engine.lower({}); engine.submit(); engine.drive('procedure')
        for offset, phase in schedule:
            target = ORIGIN + offset
            if target > engine.clock.value: engine.advance_to(target)
            require(target == engine.clock.value, 'PAT_IO_TIMING_CLOCK')
            engine.drive(phase)
        engine.capture('test_final'); report = engine.report()
        manifest = dict(profile='hms.pat.io-timing-trial/0.1', caseId=case_id, matrixDigest=matrix_digest,
            programDigest=case['programDigest'], records=copy.deepcopy(engine.records),
            configuration=engine.configuration_manifest(), report=report,
            schedulerTickReservation=case['schedulerTickCeiling'], childOperationReservation=1,
            closed=False, executionPerformed=True, requiredMatrixCoverageChecked=False,
            independentOutcomeChecked=False, actualAggregateStorageEnforced=False, qualificationPassed=False)
    finally:
        engine.close()
    manifest['closed'] = True
    encoded = canonical(manifest)
    require(len(encoded) <= 65536 and manifest['configuration']['combinedRecords']+1 <= MAX_RECORDS and
            manifest['configuration']['combinedBytes']+len(encoded) <= MAX_OUTPUT_BYTES, 'PAT_IO_TIMING_MANIFEST_LIMIT')
    return manifest
