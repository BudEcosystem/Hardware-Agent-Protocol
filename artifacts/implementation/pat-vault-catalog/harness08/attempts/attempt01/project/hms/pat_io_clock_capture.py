"""Exact clock-fault captures from a closed combined plan; no qualification claim."""
import copy

from .contracts import canonical
from .journal import JournalError
from .pat_contracts import require, snapshot
from .pat_io_combined_matrix import IoCombinedMatrixPolicy
from .pat_io_configuration_capture import ConfiguredIoTrialEngine
from .pat_io_trials import _Clock, ORIGIN, MAX_RECORDS, MAX_OUTPUT_BYTES

SCENARIOS = {'start_run_equal', 'wall_clock_regression', 'clock_epoch_mismatch'}


class ClockIoTrialEngine(ConfiguredIoTrialEngine):
    _record_profile = 'hms.pat.io-trial-record/0.3'

    def __init__(self, *args, scenario, **kwargs):
        require(type(scenario) is str and scenario in SCENARIOS, 'PAT_IO_CLOCK_SCENARIO')
        self.scenario = scenario
        self.wall = _Clock()
        self.controls = []
        super().__init__(*args, **kwargs)

    def _clock_sources(self):
        return self.wall, self.clock

    def _clock_values(self):
        return {'wallMs': self.wall.value, 'monotonicMs': self.clock.value}

    def _change(self, point, wall, monotonic):
        value = dict(phase=self.phase, point=point, ownerEpoch=1,
                     before=self._clock_values(), after=dict(wallMs=wall,monotonicMs=monotonic))
        self._write('clock_control', value)
        self.wall.value, self.clock.value = wall, monotonic
        self.controls.append(copy.deepcopy(value))

    def advance_to(self, value):
        require(False, 'PAT_IO_CLOCK_UNPLANNED_ADVANCE')

    def delayed_start(self):
        require(self.scenario=='start_run_equal' and self.phase==3 and not self.controls,
                'PAT_IO_CLOCK_PHASE')
        board = self.runtime.io_board; original = board.begin; hits = []
        def begin(operation, adapter, *, guard):
            require(self.phase==4 and not hits and operation['state']=='dispatching' and
                    self.runtime.journal._db.execute('SELECT count(*) FROM io_dispatch_links').fetchone()[0]==1,
                    'PAT_IO_CLOCK_DELAY_POINT')
            hits.append(operation['id'])
            self._change('reserved_before_begin', ORIGIN+99, ORIGIN+99)
            return original(operation, adapter, guard=guard)
        board.begin = begin
        try: self.drive('adapters')
        finally: board.begin = original
        require(len(hits)==1, 'PAT_IO_CLOCK_DELAY_MISSING')

    def invalidate_pending(self):
        require(self.scenario!='start_run_equal' and self.phase==4 and not self.controls,
                'PAT_IO_CLOCK_PHASE')
        operations = self.operations()
        require(len(operations)==1 and operations[0]['state']=='running' and
                self.runtime.io_board.receipt(operations[0]['id'])['state']=='pending', 'PAT_IO_CLOCK_NOT_PENDING')
        if self.scenario=='wall_clock_regression':
            self._change('pending_wall_regression', ORIGIN-1, ORIGIN)
        else:
            self._change('pending_mapping_invalidation', ORIGIN, ORIGIN-1)

    def restore_mapping_source(self):
        require(self.scenario=='clock_epoch_mismatch' and self.phase==5 and len(self.controls)==1 and
                self.runtime.registry._monotonic_invalid, 'PAT_IO_CLOCK_PHASE')
        # Restore the source only. The existing Registry's invalid latch remains set.
        self._change('mapping_source_restored', ORIGIN, ORIGIN)

    def reopen_clock(self):
        expected = 5 if self.scenario=='wall_clock_regression' else 6
        require(self.scenario!='start_run_equal' and self.phase==expected and
                self.runtime.journal.owner_epoch==1, 'PAT_IO_CLOCK_PHASE')
        self.capture('before_reopen'); self.close()
        # Advance beyond the retained floor; never reset the database, old receipt,
        # request, ownership floor, or the failed Registry's invalid-clock latch.
        self._change('before_new_epoch_open', ORIGIN+1, ORIGIN+1)
        try:
            self._open(create=False); self.capture('after_reopen')
        except BaseException:
            self.close(); raise


def _expected_failure(function, code):
    try: function()
    except JournalError as error:
        require(error.code==code, 'PAT_IO_CLOCK_UNEXPECTED_FAILURE')
        return
    require(False, 'PAT_IO_CLOCK_FAILURE_MISSING')


def run_clock_challenge(directory, *, matrix, candidate, installation, descriptor, challenge_bindings, case_id, group_budget=None):
    if group_budget is not None: group_budget.assert_case(case_id)
    matrix = snapshot(matrix, 'PAT_IO_CLOCK_MATRIX')
    if group_budget is None:
        matrix_digest = IoCombinedMatrixPolicy(installation).validate(
            matrix,candidate,descriptor,challenge_bindings,limits=matrix.get('limits'))
    else:
        matrix_digest = group_budget.validated_matrix_digest(matrix=matrix,candidate=candidate,
            installation=installation,descriptor=descriptor,challenge_bindings=challenge_bindings)
    require(type(case_id) is str, 'PAT_IO_CLOCK_CASE')
    cases = [c for c in matrix['cases'] if c['caseId']==case_id]
    require(len(cases)==1, 'PAT_IO_CLOCK_CASE'); case=cases[0]
    require(case['kind']=='fixed_challenge' and case['definition']['scenario'] in SCENARIOS,
            'PAT_IO_CLOCK_UNSUPPORTED_CASE')
    scenario=case['definition']['scenario']
    artifact, = [p['artifact'] for p in matrix['programs'] if p['digest']==case['programDigest']]
    engine=ClockIoTrialEngine(directory,artifact,installation,descriptor,scenario=scenario,group_budget=group_budget)
    try:
        engine.lower({}); engine.submit(); engine.drive('procedure')
        if scenario=='start_run_equal':
            engine.delayed_start(); engine.drive('procedure')
        else:
            engine.drive('adapters'); engine.invalidate_pending()
            _expected_failure(lambda:engine.drive('adapters'),
                'CLOCK_REGRESSION' if scenario=='wall_clock_regression' else 'CLOCK_MAPPING_INVALID')
            if scenario=='clock_epoch_mismatch':
                engine.restore_mapping_source()
                _expected_failure(lambda:engine.drive('adapters'),'CLOCK_MAPPING_INVALID')
            engine.reopen_clock(); engine.drive('adapters')
            _expected_failure(engine.resume,'PROCEDURE_DEPENDENCY_UNRESOLVED')
            engine.cancel(); engine.drive('cycle')
        engine.capture('test_final'); report=engine.report()
        require(report['schedulerTicks']<=case['schedulerTickCeiling'], 'PAT_IO_CLOCK_TICK_RESERVATION')
        manifest=dict(profile='hms.pat.io-clock-trial/0.1',caseId=case_id,matrixDigest=matrix_digest,
            programDigest=case['programDigest'],records=copy.deepcopy(engine.records),configuration=engine.configuration_manifest(),
            report=report,clockControls=copy.deepcopy(engine.controls),closed=False,executionPerformed=True,
            requiredMatrixCoverageChecked=False,independentOutcomeChecked=False,qualificationPassed=False,
            actualAggregateStorageEnforced=False,childOperationReservation=case['plannedChildOperations'],
            schedulerTickReservation=case['schedulerTickCeiling'])
    finally: engine.close()
    manifest['closed']=True; encoded=canonical(manifest)
    require(len(encoded)<=65536 and manifest['configuration']['combinedRecords']+1<=MAX_RECORDS and
            manifest['configuration']['combinedBytes']+len(encoded)<=MAX_OUTPUT_BYTES,'PAT_IO_CLOCK_MANIFEST_LIMIT')
    return manifest
