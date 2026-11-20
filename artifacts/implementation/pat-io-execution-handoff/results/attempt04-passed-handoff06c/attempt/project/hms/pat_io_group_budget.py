"""Private coordinator accounting for one preflighted I/O matrix.

Serialized evidence is charged before writes; tickets cannot be reused across
cases or engines. SQLite filesystem growth is observed after close, not subjected
to an OS aggregate quota here. This is not an execution authorization service.
"""
import copy
import time

from .pat_contracts import integer, require, snapshot
from .pat_io_validated_matrix import ValidatedIoMatrix


class IoGroupBudget:
    def __init__(self, matrix, *, started, validated_plan=None):
        # Only the trusted coordinator supplies the already validated matrix.
        self._matrix = snapshot(matrix)
        require(validated_plan is None or type(validated_plan) is ValidatedIoMatrix, 'PAT_IO_GROUP_PLAN_TYPE')
        if validated_plan is not None:
            validated_plan.assert_matrix(self._matrix)
        self._validated_plan = validated_plan
        self._limits = self._matrix['limits']
        self._started = self._last_clock = started
        self._active = None
        self._next = 0
        self._failed = False
        self._terminal = False
        self._counts = dict(records=1, producerBytes=self._limits['maxDocumentBytes'],
            derivedBytes=self._limits['maxDocumentBytes'], observedStateBytes=0,
            reservedChildOperations=0, actualChildOperations=0, schedulerTicks=0,
            completedCases=0)
        # Reserve exactly one bounded terminal receipt before any trial can act.
        require(self._counts['producerBytes'] <= self._limits['maxProducerBytes'] and
                self._counts['derivedBytes'] <= self._limits['maxDerivedBytes'],
                'PAT_IO_GROUP_TERMINAL_RESERVATION')
        self.check()

    def check(self):
        require(not self._failed and not self._terminal, 'PAT_IO_GROUP_STOPPED')
        now = time.monotonic()
        if now < self._last_clock or now - self._started >= self._limits['maxWallMs']/1000:
            self._failed = True
            require(False, 'PAT_IO_GROUP_WALL_LIMIT')
        self._last_clock = now

    def _limit(self, condition, code):
        if not condition:
            self._failed = True
            require(False, code)

    def record(self, size):
        self.check()
        integer(size, 1, self._limits['maxDocumentBytes'], 'PAT_IO_GROUP_DOCUMENT_LIMIT')
        c, l = self._counts, self._limits
        self._limit(c['records'] < l['maxRecords'] and
            c['producerBytes'] + size <= l['maxProducerBytes'] and
            c['derivedBytes'] + size <= l['maxDerivedBytes'], 'PAT_IO_GROUP_EVIDENCE_LIMIT')
        c['records'] += 1; c['producerBytes'] += size; c['derivedBytes'] += size

    def begin(self, case_id):
        self.check()
        require(self._active is None and self._next < len(self._matrix['cases']), 'PAT_IO_GROUP_CASE_ORDER')
        case = self._matrix['cases'][self._next]
        require(case['caseId'] == case_id, 'PAT_IO_GROUP_CASE_ORDER')
        c = self._counts
        self._limit(c['reservedChildOperations'] + case['plannedChildOperations'] <=
                    self._limits['maxChildOperations'], 'PAT_IO_GROUP_OPERATION_LIMIT')
        c['reservedChildOperations'] += case['plannedChildOperations']
        self._active = IoTrialBudget(self, case)
        return self._active

    def observe_state(self, size):
        self.check()
        integer(size, 0, self._limits['maxDerivedBytes'], 'PAT_IO_GROUP_STATE_LIMIT')
        self._limit(self._counts['derivedBytes'] + size <= self._limits['maxDerivedBytes'],
                    'PAT_IO_GROUP_DERIVED_LIMIT')
        self._counts['derivedBytes'] += size
        self._counts['observedStateBytes'] += size

    def end(self, ticket, *, operation_count, scheduler_ticks):
        ticket.check()
        integer(operation_count, 0, ticket._case['plannedChildOperations'], 'PAT_IO_GROUP_OPERATION_LIMIT')
        require(type(scheduler_ticks) is int and scheduler_ticks == ticket._ticks,
                'PAT_IO_GROUP_TICK_ACCOUNTING')
        require(ticket._bound or ticket._case['plannedChildOperations'] == 0, 'PAT_IO_GROUP_ENGINE_MISSING')
        self._counts['actualChildOperations'] += operation_count
        self._counts['completedCases'] += 1
        self._next += 1; self._active = None

    def stop(self):
        self._failed = True

    def snapshot(self):
        return copy.deepcopy(dict(profile='hms.pat.io-group-budget/0.1', limits=self._limits,
            charged=self._counts, terminalBytesReserved=self._limits['maxDocumentBytes'],
            nextCase=self._next, activeCaseId=None if self._active is None else self._active._case['caseId'],
            stopped=self._failed, terminal=self._terminal, hardAggregateFilesystemQuota=False))

    def terminal(self, size, *, success):
        # A pre-reserved failure receipt may be emitted after the deadline.
        require(not self._terminal, 'PAT_IO_GROUP_ALREADY_TERMINAL')
        integer(size, 1, self._limits['maxDocumentBytes'], 'PAT_IO_GROUP_DOCUMENT_LIMIT')
        if success:
            self.check()
            require(self._active is None and self._next == len(self._matrix['cases']), 'PAT_IO_GROUP_INCOMPLETE')
        self._terminal = True


class IoTrialBudget:
    """An in-process ticket; not a wire capability or adversarial sandbox."""
    def __init__(self, group, case):
        self._group, self._case = group, copy.deepcopy(case)
        self._bound = False
        self._ticks = self._records = self._bytes = 0

    def check(self):
        self._group.check()
        require(self._group._active is self, 'PAT_IO_GROUP_STALE_TICKET')

    def bind(self, artifact_digest):
        self.check()
        require(not self._bound, 'PAT_IO_GROUP_ENGINE_REUSE')
        expected = (self._case['actors']['gpio']['programDigest'] if self._case['kind'] == 'resource_challenge'
                    else self._case['programDigest'])
        require(artifact_digest == expected, 'PAT_IO_GROUP_PROGRAM_MISMATCH')
        self._bound = True

    def record(self, size):
        self.check(); require(self._bound, 'PAT_IO_GROUP_ENGINE_MISSING')
        self._group.record(size)
        self._records += 1; self._bytes += size

    def tick(self):
        self.check(); require(self._bound, 'PAT_IO_GROUP_ENGINE_MISSING')
        self._group._limit(self._ticks < self._case['schedulerTickCeiling'] and
            self._group._counts['schedulerTicks'] < self._group._limits['maxSchedulerTicks'],
            'PAT_IO_GROUP_TICK_LIMIT')
        self._ticks += 1; self._group._counts['schedulerTicks'] += 1

    def admission(self, existing_count):
        self.check(); require(self._bound, 'PAT_IO_GROUP_ENGINE_MISSING')
        require(type(existing_count) is int and 0 <= existing_count < self._case['plannedChildOperations'],
                'PAT_IO_GROUP_OPERATION_LIMIT')

    def assert_case(self, case_id):
        self.check()
        require(case_id == self._case['caseId'], 'PAT_IO_GROUP_CASE_MISMATCH')

    def validated_matrix_digest(self, **inputs):
        self.check()
        require(not self._bound, 'PAT_IO_GROUP_ENGINE_REUSE')
        require(self._group._validated_plan is not None, 'PAT_IO_GROUP_PLAN_REQUIRED')
        return self._group._validated_plan.validate_inputs(**inputs)

    def assert_evidence(self, configuration):
        self.check()
        require(configuration['combinedRecords'] == self._records and
                configuration['combinedBytes'] == self._bytes, 'PAT_IO_GROUP_EVIDENCE_ACCOUNTING')
