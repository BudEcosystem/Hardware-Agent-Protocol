"""Original finite-I/O trial phase engine, not an installed qualification worker.

One fresh private IoRuntime, immutable compiled requests, bounded virtual-time
progress, and raw checkpoint records. No outcome reducer or promotion decision is
implemented here. Close preserves state; it is not proof of idle or cancellation.
"""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import time

from .contracts import SAFE_INTEGER, canonical
from .journal import Context, JournalError, TERMINAL
from .pat_compiler import compile_pat, evaluation_environment
from .pat_contracts import PatError, integer, pat_digest, require, snapshot
from .pat_io_group_budget import IoTrialBudget
from .pat_io_bindings import IoRegistryPatBindings
from .pat_io_contracts import IoSequencePolicy
from .pat_simulation_contracts import _tag
from .state_path import private_state_directory
from .synthetic_io_installation import normalize_installation
from .synthetic_io_runtime import IoRuntime

ORIGIN = 1000000
RECORD_PROFILE = 'hms.pat.io-trial-record/0.1'
MAX_RECORDS, MAX_OUTPUT_BYTES, MAX_TICKS = 4096, 16 * 1024 * 1024, 2048
MAX_WALL_SECONDS = 60

# Closed snapshots of execution, ownership, replay and retained configuration.
# Observations are separately refreshed input, not a durable-progress signal.
_BOARD = {
    'io_meta': ('key,value', 32),
    'io_resources': ('resource,state', 128),
    'io_owners': ('resource,operation,fence', 128),
    'io_fences': ('resource,fence,operation', 128),
    'io_receipts': ('operation,state,sequence,digest,document', 16),
    'io_receipt_versions': ('operation,sequence,digest,document', 32),
    'io_effects': ('instance,activations,completed,canceled', 128),
}
_AUTHORITY = {
    'meta': ('key,value', 32),
    'series': ('principal,deployment,next_epoch,floor,last_expiry', 1),
    'namespaces': ('token,principal,deployment,epoch,expires_ms', 1),
    'operations': ('id,principal,deployment,digest,intent,admission,state,cancel_state,verification,may_have_acted,sequence,attempt_id,owner_epoch', 16),
    'replay_keys': ('namespace,caller_key,operation_id', 16),
    'resource_floors': ('deployment,resource,fence', 128),
    'claims': ('deployment,resource,operation_id,fence', 128),
    'events': ('operation_id,sequence,time_ms,clock_status,kind,payload', 1024),
    'io_dispatch_links': ('operation,document,digest', 16),
    'io_authority_receipts': ('operation,sequence,document,digest', 32),
    'pr_meta': ('key,value', 8),
    'pr_procedures': ('id,principal,deployment,digest,request,state,reason,cursor,cancel_requested,cancel_delivery,sequence', 1),
    'pr_steps': ('procedure_id,ordinal,step_id,request,digest,operation_id', 16),
    'pr_keys': ('namespace,caller_key,procedure_id,step_id', 17),
    'pr_events': ('procedure_id,sequence,time_ms,clock_status,kind,payload', 1024),
    'rt_catalog': ('singleton,profile,legacy,owner', 1),
    'rt_adapters': ('adapter,document,digest,ready', 16),
    'rt_io_installation': ('singleton,document,digest', 1),
    'rc_catalog': ('singleton,profile,topology,topology_digest,routes,routes_digest,current_revision', 1),
    'rc_generations': ('revision,document,digest', 1),
    'rc_tokens': ('node,generation,revision', 128),
    'rc_proofs': ('instance,generation,revision,document,digest,binding_digest', 128),
}


class _Clock:
    def __init__(self):
        self.value = ORIGIN

    def __call__(self):
        return self.value


class IoTrialEngine:
    """Trusted local test component; never accept a directory from a PAT payload."""

    _record_profile = RECORD_PROFILE
    _storage_profile = 'hms.sqlite.compact/0.1'

    def __init__(self, directory, artifact, installation, descriptor, *, group_budget=None):
        self.runtime = None
        require(group_budget is None or type(group_budget) is IoTrialBudget, 'PAT_IO_GROUP_TICKET')
        self._group_budget = group_budget
        if group_budget is not None:
            group_budget.bind(pat_digest(artifact))
        self.clock, self.plan, self.procedure_id = _Clock(), None, None
        self._lower_attempted = False
        self.ticks = self.phase = self.output_bytes = 0
        self.records, self._objects = [], {}
        self._started = time.monotonic()
        self.document = normalize_installation(installation)
        self.artifact = snapshot(artifact)
        self.original_descriptor = snapshot(descriptor)
        self.policy = IoSequencePolicy(self.document)
        self.contract = self.policy.qualify(self.artifact, self.original_descriptor)
        require(ORIGIN <= self.contract['schedule']['maxOriginMs'], 'PAT_TIME_BOUNDS')
        self.role = self.contract['role']
        self.owner = Context('pat-io-trial-worker', self.document['topology']['deployment'])
        # Existing validated empty directory only. No user authority is reopened.
        self.directory = private_state_directory(directory)
        require(not any(self.directory.iterdir()), 'PAT_IO_TRIAL_DIRECTORY_NOT_EMPTY')
        self.record_directory = self.directory / 'records'
        self.record_directory.mkdir(mode=0o700)
        try:
            for kind, value in [('artifact', self.artifact), ('installation', self.document),
                                ('original_descriptor', self.original_descriptor), ('static_contract', self.contract)]:
                self._write(kind, value)
            self._open(create=True)
            self.capture('baseline')
        except BaseException:
            self.close()
            raise

    def _check_budget(self):
        if self._group_budget is not None:
            self._group_budget.check()
        require(time.monotonic() - self._started < MAX_WALL_SECONDS, 'PAT_IO_TRIAL_WALL_LIMIT')

    def _write(self, kind, value, *, reuse=False):
        self._check_budget()
        data = canonical({'profile': self._record_profile, 'kind': kind, 'value': value})
        digest = hashlib.sha256(data).hexdigest()
        if reuse and digest in self._objects:
            return copy.deepcopy(self._objects[digest])
        require(len(self.records) < MAX_RECORDS and self.output_bytes + len(data) <= MAX_OUTPUT_BYTES,
                'PAT_IO_TRIAL_EVIDENCE_LIMIT')
        reference = {'path': '%06d.json' % len(self.records), 'bytes': len(data), 'sha256': digest}
        if self._group_budget is not None:
            self._group_budget.record(len(data))
        with (self.record_directory / reference['path']).open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        self.output_bytes += len(data)
        self.records.append(reference)
        if reuse:
            self._objects[digest] = reference
        return copy.deepcopy(reference)

    def _clock_sources(self):
        return self.clock, self.clock

    def _clock_values(self):
        return {'wallMs': self.clock.value, 'monotonicMs': self.clock.value}

    def _open(self, *, create):
        self._check_budget()
        wall, monotonic = self._clock_sources()
        self.runtime = IoRuntime(self.directory / 'state', create=create, owner=self.owner if create else None,
                                 installation=self.document, wall_clock_ms=wall, monotonic_ms=monotonic,
            storage_profile=self._storage_profile)
        require(not self.runtime.route_errors and not self.runtime._threads and
                set(self.runtime.adapters) == set(self.document['routes']['adapters']), 'PAT_IO_TRIAL_RECONSTRUCTION')
        original = self.runtime.journal.submission_guard

        def bounded_admission(context, request, intent, digest, managed, now):
            count = self.runtime.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]
            if self._group_budget is not None:
                self._group_budget.admission(count)
            require(self.plan is not None and count < len(self.artifact['steps']), 'PAT_IO_TRIAL_OPERATION_LIMIT')
            return original(context, request, intent, digest, managed, now)

        self.runtime.journal.submission_guard = bounded_admission
        record = {key: self.original_descriptor[key] for key in ('driverProfile', 'driverDigest', 'installationDigest', 'argumentMetadata')}
        record.update(instanceId=self.original_descriptor['binding']['instanceId'],
                      typeDigest=self.original_descriptor['binding']['typeDigest'])
        provider = IoRegistryPatBindings(self.runtime, [record])
        self._binding_configuration(copy.deepcopy(record), provider.registration_identity)
        with self.runtime.journal._transaction():
            current = provider.for_roles(self.owner, self.artifact, {self.role: record['instanceId']})
        wanted = evaluation_environment(self.artifact, {self.role: self.original_descriptor}, deployment=self.owner.deployment)
        actual = evaluation_environment(self.artifact, current, deployment=self.owner.deployment)
        require(actual['evaluationEnvironment'] == wanted['evaluationEnvironment'] and
                actual['environmentDigest'] == wanted['environmentDigest'], 'PAT_IO_TRIAL_ENVIRONMENT_CHANGED')
        self.bindings = current
        self._write('runtime_opened', {'create': create, 'wallMs': self._clock_values()['wallMs'],
            'ownerEpoch': self.runtime.journal.owner_epoch, 'authorityId': self.runtime.journal.authority_id,
            'session': self.runtime.io_board.session, 'originalEnvironment': wanted, 'workerEnvironment': actual})

    def _binding_configuration(self, registration, identity):
        """Optional trusted evidence hook; the default trial retains no sidecar."""
        pass

    def close(self):
        if self.runtime is not None:
            runtime = self.runtime
            runtime.close()
            self.runtime = None

    def reopen(self):
        """Retain the old compiled request. A new session is never rebound into it."""
        self.capture('before_reopen')
        self.close()
        try:
            self._open(create=False)
            self.capture('after_reopen')
        except BaseException:
            self.close()
            raise

    def _table(self, db, store, table, specification):
        fields, limit = specification
        columns = fields.split(',')
        schema = db.execute('PRAGMA table_info(' + table + ')').fetchmany(33)
        require(len(schema) <= 32 and [row[1] for row in schema] == columns, 'PAT_IO_TRIAL_STORAGE_SHAPE')
        count = db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
        require(type(count) is int and count <= limit, 'PAT_IO_TRIAL_STORAGE_LIMIT')
        sizes = ','.join('max(length(CAST(' + column + ' AS BLOB)))' for column in columns)
        require(all(value is None or value <= 65536 for value in db.execute('SELECT ' + sizes + ' FROM ' + table).fetchone()),
                'PAT_IO_TRIAL_STORAGE_LIMIT')
        rows = db.execute('SELECT ' + fields + ' FROM ' + table + ' ORDER BY ' + fields + ' LIMIT ?', (limit + 1,)).fetchall()
        require(len(rows) == count, 'PAT_IO_TRIAL_STORAGE_CHANGED')
        def cell(value):
            if type(value) is bytes:
                return {'type': 'blob-utf8', 'value': value.decode('utf-8')}
            require(value is None or type(value) in {int, str}, 'PAT_IO_TRIAL_STORAGE_TYPE')
            return {'type': 'null' if value is None else 'integer' if type(value) is int else 'text', 'value': value}
        pages = []
        # Empty tables still have a page and explicit zero row count.
        for offset in range(0, max(count, 1), 8):
            pages.append(self._write('table_page', {'store': store, 'table': table, 'columns': columns,
                'first': offset, 'totalRows': count, 'rows': [[cell(value) for value in row] for row in rows[offset:offset + 8]]}, reuse=True))
        return {'store': store, 'table': table, 'rowCount': count, 'pages': pages}

    def capture(self, label):
        self._check_budget()
        require(self.runtime is not None, 'PAT_IO_TRIAL_CLOSED')
        with self.runtime.journal._mutex, self.runtime.io_board.lock:
            authority, board = self.runtime.journal._db, self.runtime.io_board.db
            require(not authority.in_transaction and not board.in_transaction, 'PAT_IO_TRIAL_UNCOMMITTED_CAPTURE')
            tables = [self._table(db, store, table, spec)
                      for store, db, inventory in [('authority', authority, _AUTHORITY), ('board', board, _BOARD)]
                      for table, spec in inventory.items()]
            return self._write('checkpoint', {'phase': self.phase, 'label': label,
                **self._clock_values(),
                'clockEpoch': self.runtime.registry.receipt_epoch, 'tables': tables})

    def operations(self):
        rows = self.runtime.journal._db.execute('SELECT id FROM operations ORDER BY rowid LIMIT 17').fetchall()
        require(len(rows) <= len(self.artifact['steps']), 'PAT_IO_TRIAL_OPERATION_LIMIT')
        return [self.runtime.journal._operation(row[0]) for row in rows]

    def status(self):
        require(self.procedure_id is not None, 'PAT_IO_TRIAL_NOT_SUBMITTED')
        return self.runtime.procedures.status(self.owner, self.procedure_id)

    def lower(self, parameters, *, context=None):
        require(not self._lower_attempted, 'PAT_IO_TRIAL_ALREADY_COMPILED')
        self._lower_attempted = True
        parameters = snapshot(parameters, 'PAT_INVALID_PARAMETERS')
        require(type(parameters) is dict, 'PAT_INVALID_PARAMETERS')
        end = ORIGIN + self.artifact['timingBudget']['latestCompletionOffsetMs']
        if context is None:
            context = {'taskKind': self.artifact['taskKind'], 'inputProfile': self.artifact['inputProfile'], 'evidenceMode': 'simulation'}
        context = snapshot(context, 'PAT_INVALID_CONTEXT')
        self._write('lower_input', {'parameters': {key: _tag(value) for key, value in parameters.items()}, 'context': context})
        def compile_one():
            namespace = self.runtime.journal.issue_namespace(self.owner, end + 1)['token']
            return compile_pat(self.artifact, parameters, self.bindings, origin_ms=ORIGIN,
                replay_namespace=namespace, procedure_key='trial:parent',
                operation_keys={step['stepId']: 'trial:child:' + str(i) for i, step in enumerate(self.artifact['steps'])},
                caller_deadline_ms=end, context=context | {'deployment': self.owner.deployment})
        self.plan = self._call('lower', compile_one)
        self._write('compiled_plan', self.plan)
        return copy.deepcopy(self.plan)

    def _call(self, label, function):
        self._check_budget()
        self.phase += 1
        self.capture(label + ':before')
        self._write('call_started', {'phase': self.phase, 'label': label, 'clock': self.clock.value})
        try:
            result = function()
        except BaseException as error:
            self._write('call_failed', {'phase': self.phase, 'label': label, 'clock': self.clock.value,
                'exception': type(error).__name__, 'code': getattr(error, 'code', None)})
            self.capture(label + ':after_error')
            raise
        self._write('call_returned', {'phase': self.phase, 'label': label, 'clock': self.clock.value, 'result': result})
        self.capture(label + ':after')
        return result

    def submit(self):
        require(self.plan is not None, 'PAT_IO_TRIAL_NOT_COMPILED')
        result = self._call('submit', lambda: self.runtime.procedures.submit(self.owner, self.plan['request']))
        if self.procedure_id is not None:
            require(result['procedureId'] == self.procedure_id, 'PAT_IO_TRIAL_REPLAY_CHANGED')
        self.procedure_id = result['procedureId']
        return result

    def cancel(self):
        return self._call('cancel', lambda: self.runtime.procedures.cancel(self.owner, self.procedure_id))

    def resume(self):
        return self._call('resume', lambda: self.runtime.procedures.resume(self.owner, self.procedure_id))

    def drive(self, phase='cycle'):
        require(phase in {'cycle', 'procedure', 'adapters'}, 'PAT_IO_TRIAL_INVALID_PHASE')
        require(self.ticks < MAX_TICKS, 'PAT_IO_TRIAL_TICK_LIMIT')
        if self._group_budget is not None:
            self._group_budget.tick()
        self.ticks += 1
        def execute():
            self.runtime._refresh(force=True)
            if phase == 'cycle':
                self.runtime.tick()
            elif phase == 'procedure':
                self.runtime.procedures.tick()
            else:
                for adapter in self.runtime.adapters.values():
                    adapter.tick()
        return self._call('drive:' + phase, execute)

    def advance_to(self, value):
        integer(value, self.clock.value + 1, SAFE_INTEGER, 'PAT_IO_TRIAL_CLOCK')
        self._write('clock_advanced', {'from': self.clock.value, 'to': value})
        self.clock.value = value

    def _progress(self):
        # No refreshed presence/observation counters: only durable work changes.
        return canonical({'procedure': self.status(), 'operations': self.operations(),
            'receipts': [dict(row) for row in self.runtime.io_board.db.execute(
                'SELECT operation,state,sequence,digest FROM io_receipts ORDER BY operation LIMIT 17')]})

    def next_event(self):
        require(self.plan is not None, 'PAT_IO_TRIAL_NOT_COMPILED')
        future = [self.plan['request']['procedure']['timing']['latestCompletionUnixMs']]
        for operation in self.operations():
            timing = operation['intent']['timing']
            if operation['state'] == 'accepted':
                future.extend([timing['notBeforeUnixMs'], timing['latestStartUnixMs'], operation['admission']['lease_expires_ms']])
            receipt = self.runtime.io_board.receipt(operation['id'])
            if receipt is not None and receipt['state'] == 'pending':
                # Zero-lag policy uses the same integer wall/monotonic origin.
                future.extend([receipt['dueMonoMs'], receipt['budgetOriginMonoMs'] + timing['maxRunMs'],
                               timing['latestCompletionUnixMs'], operation['admission']['lease_expires_ms']])
        future = [value for value in future if value > self.clock.value]
        require(bool(future), 'PAT_IO_TRIAL_STALLED')
        return min(future)

    def finish(self):
        while True:
            before = self._progress()
            self.drive()
            status = self.status()
            if status['executionState'] in {'completed', 'failed', 'canceled', 'expired', 'interrupted'}:
                return status
            if self._progress() == before:
                self.advance_to(self.next_event())

    def report(self):
        operations = self.operations()
        unresolved = [op['id'] for op in operations if op['state'] not in TERMINAL or op['claims']]
        result = {'profile': 'hms.pat.io-trial-observation/0.1', 'clock': self.clock.value,
            'procedure': self.status() if self.procedure_id else None, 'operationIds': [op['id'] for op in operations],
            'unresolvedOperations': unresolved, 'schedulerTicks': self.ticks,
            'evidenceRecords': len(self.records), 'evidenceBytes': self.output_bytes,
            'qualificationPassed': False, 'independentOutcomeChecked': False}
        self._write('trial_observation', result)
        return result
