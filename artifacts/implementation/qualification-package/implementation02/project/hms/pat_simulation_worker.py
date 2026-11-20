"""Original isolated SQLite fan trials; no live authority or physical I/O.

Run only in a trusted isolated process. The argument directory is trusted setup,
never capsule data. This module does not authenticate a live configuration,
promote artifacts, supply a sandbox, or impose a hard real-time deadline.
Evidence-loss trials use a one-shot exception and owner reopen, not a process
crash. Fresh synthetic state is intentionally distinct from live plant state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import stat
import sys
import time
import _sqlite3

from .contracts import ContractError, canonical, intent_digest
from .installations import (definitions_for, installation_digest, legacy_installation,
                            normalize_installations, resource_map)
from .journal import Context, JournalError, TERMINAL
from .pat_compiler import (compiler_digest, compile_pat,
                           evaluation_environment, verify_compiler_identity)
from .pat_contracts import (PatError, closed, integer, name, require, snapshot)
from .pat_simulation_contracts import (CEILINGS, FAN_METADATA, POLICY, _limits,
    decode_case_input, generate_cases, matrix_digest, qualify_fan_contract)
from .runtime import Runtime

INPUT_PROFILE = 'hms.pat.sqlite-fan-worker-input/0.1'
RESULT_PROFILE = 'hms.pat.sqlite-fan-worker-result/0.1'
FAULTS = ('cancel_accepted', 'cancel_running', 'reopen_accepted',
          'reopen_pending', 'completion_evidence_loss')
ORIGIN = 1000000
_ROOT = Path(__file__).resolve().parents[1]


def _hash(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None,
            'PAT_SIM_INVALID_CAPSULE')


def _same(left, right):
    """Type-sensitive equality for already bounded JSON trees."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _source_identity():
    """Installed Python/data closure, not physical or binary attestation."""
    paths = sorted({*(_ROOT / 'hms').rglob('*.py'), *(_ROOT / 'schemas').glob('*.json'),
                    *(_ROOT / 'examples/wot').glob('*.json'),
                    _ROOT / 'research/protocols/wot-artifacts/td-schema-1.1.json'})
    rows = [{'path': str(p.relative_to(_ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in paths]
    manifest = verify_compiler_identity()
    by_path = {row['path']: row['sha256'] for row in rows}
    require(all(by_path.get(row['path']) == row['sha256'] for row in manifest['sources']),
            'PAT_SIM_IMPLEMENTATION_CHANGED')
    return {'sources': rows, 'compilerManifest': manifest,
            'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'pythonExecutableSha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            'sqliteVersion': sqlite3.sqlite_version,
            'sqliteExtensionSha256': hashlib.sha256(Path(_sqlite3.__file__).read_bytes()).hexdigest()}


# Like the compiler, implementation identity is fixed at import. Each public
# identity query also detects changed source bytes beneath that imported code.
_IMPORTED_IDENTITY = _source_identity()


def simulation_identities(limits=None):
    """Recheck the reviewed installed closure; lowered ceilings change policy."""
    limits = _limits(CEILINGS if limits is None else limits)
    current = _source_identity()
    require(current == _IMPORTED_IDENTITY, 'PAT_SIM_IMPLEMENTATION_CHANGED')
    closure = _hash(b'HMS-PAT-SIM-INSTALLED-CLOSURE-v0.1', current)
    return {'compilerDigest': compiler_digest(),
            'workerDigest': _hash(b'HMS-PAT-SIM-WORKER-v0.1', {'closure': closure, 'profile': INPUT_PROFILE}),
            'driverDigest': _hash(b'HMS-SQLITE-SIM-SOURCE-CLOSURE-v0.1', {'closure': closure, 'driver': 'sqlite-simulation'}),
            'policyDigest': _hash(b'HMS-PAT-FAN-TRIAL-POLICY-v0.1',
                {'closure': closure, 'policy': POLICY, 'limits': limits, 'faults': list(FAULTS)})}


def make_capsule(artifact, installation, bindings, *, deployment, runtime_layout,
                 configuration, attempt_id, limits=None):
    """Build bounded detached input from a trusted captured assignment.

    Configuration revision/digest are provenance only; this worker cannot
    verify the live configuration or that a caller obtained these snapshots.
    """
    limits = _limits(CEILINGS if limits is None else limits)
    require(type(bindings) is dict and len(bindings) == 1, 'PAT_SIM_INVALID_CAPSULE')
    descriptor = next(iter(bindings.values()))
    evidence = evaluation_environment(artifact, bindings, deployment=deployment)
    capsule = {'profile': INPUT_PROFILE, 'policy': POLICY, 'attemptId': attempt_id,
        'configuration': configuration, 'identities': simulation_identities(limits),
        'runtimeLayout': runtime_layout, 'artifact': artifact, 'installation': installation,
        'bindings': bindings, 'evaluationEnvironment': evidence['evaluationEnvironment'],
        'environmentDigest': evidence['environmentDigest'],
        'caseMatrix': generate_cases(artifact, descriptor, limits=limits),
        'matrixDigest': matrix_digest(artifact, descriptor, limits=limits), 'limits': limits}
    return parse_capsule(capsule)


def parse_capsule(value):
    """No Runtime or output directory is touched by validation."""
    try:
        value = snapshot(value, 'PAT_SIM_INVALID_CAPSULE')
        closed(value, {'profile', 'policy', 'attemptId', 'configuration', 'identities',
            'runtimeLayout', 'artifact', 'installation', 'bindings', 'evaluationEnvironment',
            'environmentDigest', 'caseMatrix', 'matrixDigest', 'limits'}, 'PAT_SIM_INVALID_CAPSULE')
        require(value['profile'] == INPUT_PROFILE and value['policy'] == POLICY, 'PAT_SIM_INVALID_CAPSULE')
        name(value['attemptId'], 'PAT_SIM_INVALID_CAPSULE')
        closed(value['configuration'], {'revision', 'digest'}, 'PAT_SIM_INVALID_CAPSULE')
        integer(value['configuration']['revision'], 1, code='PAT_SIM_INVALID_CAPSULE')
        _digest(value['configuration']['digest'])
        limits = _limits(value['limits'])
        require(value['identities'] == simulation_identities(limits), 'PAT_SIM_IDENTITY_MISMATCH')
        installation, = normalize_installations([value['installation']])
        require(installation['driver'] == 'sqlite-simulation', 'PAT_SIM_UNSUPPORTED_RECONSTRUCTION')
        deployment = value['evaluationEnvironment']['deployment']
        require((value['runtimeLayout'] == 'legacy' and deployment == 'simulation:local' and
                 installation == legacy_installation()) or
                (value['runtimeLayout'] == 'multi' and deployment == 'simulation:multi'),
                'PAT_SIM_UNSUPPORTED_RECONSTRUCTION')
        bindings = value['bindings']
        require(type(bindings) is dict and len(bindings) == 1, 'PAT_SIM_INVALID_CAPSULE')
        role, descriptor = next(iter(bindings.items()))
        contract = qualify_fan_contract(value['artifact'], descriptor)
        require(role == contract['role'], 'PAT_SIM_INVALID_CAPSULE')
        fan = installation['instances']['fan']
        bundle = next(document for instance, _, document in definitions_for(installation) if instance == fan)
        binding = descriptor['binding']
        require(binding['instanceId'] == fan and binding['adapterId'] == installation['adapterId'] and
                binding['resourceMap'] == resource_map(installation, fan) and _same(descriptor['type'], bundle) and
                descriptor['argumentMetadata'] == FAN_METADATA and
                descriptor['installationDigest'] == 'sha256:' + installation_digest(installation) and
                descriptor['driverDigest'] == value['identities']['driverDigest'],
                'PAT_SIM_UNSUPPORTED_RECONSTRUCTION')
        evidence = evaluation_environment(value['artifact'], bindings, deployment=deployment)
        require(evidence['evaluationEnvironment'] == value['evaluationEnvironment'] and
                evidence['environmentDigest'] == value['environmentDigest'], 'PAT_SIM_ENVIRONMENT_MISMATCH')
        require(_same(generate_cases(value['artifact'], descriptor, limits=limits), value['caseMatrix']) and
                matrix_digest(value['artifact'], descriptor, limits=limits) == value['matrixDigest'],
                'PAT_SIM_MATRIX_MISMATCH')
        require(len(value['caseMatrix']['cases']) + len(FAULTS) <= limits['maxCases'], 'PAT_SIM_CASE_LIMIT')
        required = value['caseMatrix']['plannedChildOperations'] + 2 * len(value['artifact']['steps']) + 3
        require(required <= limits['maxChildOperations'], 'PAT_SIM_EFFECT_LIMIT')
        canonical(value)
        return value
    except (ContractError, KeyError, TypeError, ValueError) as error:
        raise PatError('PAT_SIM_INVALID_CAPSULE') from error


class _OracleFailure(PatError):
    def __init__(self, detail):
        super().__init__('PAT_SIM_ORACLE_FAILED', detail)


class _EvidenceLost(RuntimeError):
    pass


def _assert(condition, detail):
    if not condition:
        raise _OracleFailure(detail)


class _Budget:
    def __init__(self, limits):
        self.limits, self.ticks, self.operations, self.output_bytes = limits, 0, 0, 0
        self.started = time.monotonic()

    def check(self):
        require((time.monotonic() - self.started) * 1000 < self.limits['workerDeadlineMs'], 'PAT_SIM_WORKER_DEADLINE')

    def tick(self):
        self.check()
        require(self.ticks < self.limits['maxSchedulerTicks'], 'PAT_SIM_TICK_LIMIT')
        self.ticks += 1


class _Evidence:
    def __init__(self, directory, budget):
        self.directory, self.budget, self.records = directory, budget, []

    def write(self, kind, value):
        self.budget.check()
        require(len(self.records) < 4096, 'PAT_SIM_EVIDENCE_RECORD_LIMIT')
        data = canonical({'profile': 'hms.pat.sqlite-fan-evidence/0.1', 'kind': kind, 'value': value})
        require(self.budget.output_bytes + len(data) <= self.budget.limits['maxOutputBytes'], 'PAT_SIM_OUTPUT_LIMIT')
        path = self.directory / ('%06d.json' % len(self.records))
        with path.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.budget.output_bytes += len(data)
        record = {'path': 'evidence/' + path.name, 'bytes': len(data),
                  'sha256': hashlib.sha256(data).hexdigest(), 'kind': kind}
        self.records.append(record)
        return record

    def seal(self):
        # Each page is itself bounded/canonical. The returned page references
        # remain small even for a sixteen-step matrix; no giant JSON result.
        content = list(self.records)
        pages = []
        for offset in range(0, len(content), 100):
            pages.append(self.write('evidence_index', {'first': offset, 'records': content[offset:offset + 100]}))
        return pages

    def verify(self):
        """Bounded readback now; the supervisor must verify retained bytes later."""
        for record in self.records:
            self.budget.check()
            fd = os.open(self.directory / Path(record['path']).name, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == record['bytes'],
                        'PAT_SIM_EVIDENCE_CHANGED')
                data = stream.read(record['bytes'] + 1)
            require(len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'],
                    'PAT_SIM_EVIDENCE_CHANGED')
        self.budget.check()


class _Clock:
    def __init__(self):
        self.value = ORIGIN

    def __call__(self):
        return self.value


class _Trial:
    def __init__(self, capsule, directory, budget, evidence, number, case_id):
        self.capsule, self.directory, self.budget, self.evidence = capsule, directory, budget, evidence
        self.number, self.case_id, self.clock = number, case_id, _Clock()
        self.runtime = None
        self.procedure_id = self.request = self.plan = None
        self.accounted = 0
        self.operation_base = budget.operations
        self.owner = Context('pat-simulation-worker', capsule['evaluationEnvironment']['deployment'])
        self.role, self.original_descriptor = next(iter(capsule['bindings'].items()))
        self.fan = capsule['installation']['instances']['fan']
        self.log = []

    def initialize(self):
        self.open(create=True)
        self.baseline = self.plants()
        self.evidence.write('trial_started', {'trial': self.number, 'caseId': self.case_id, 'baseline': self.baseline,
            'originalDependencies': evaluation_environment(self.capsule['artifact'], self.capsule['bindings'],
                deployment=self.owner.deployment)['dependencies'],
            'workerDependencies': self.environment['dependencies'], 'environmentDigest': self.environment['environmentDigest']})

    def open(self, *, create):
        self.budget.check()
        installation = self.capsule['installation']
        options = {'wall_clock_ms': self.clock, 'monotonic_ms': self.clock}
        if self.capsule['runtimeLayout'] == 'multi':
            options['installations'] = [installation]
        self.runtime = Runtime(self.directory, create=create, owner=self.owner if create else None, **options)
        original_guard = self.runtime.journal.submission_guard

        def bounded_admission(context, request, intent, digest, managed, now):
            # Replay resolves before this hook. Check each genuinely fresh
            # child before the authority transaction can create its operation.
            count = self.runtime.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]
            require(self.operation_base + count < self.budget.limits['maxChildOperations'], 'PAT_SIM_EFFECT_LIMIT')
            require(count < len(self.capsule['artifact']['steps']), 'PAT_SIM_EXTRA_OPERATIONS')
            return original_guard(context, request, intent, digest, managed, now)

        self.runtime.journal.submission_guard = bounded_admission
        require(not self.runtime.route_errors and set(self.runtime.adapters) == {installation['adapterId']},
                'PAT_SIM_RECONSTRUCTION_FAILED')
        self.backend = self.runtime.adapters[installation['adapterId']]
        binding, active = self.runtime.registry._binding(self.fan)
        requested = self.original_descriptor['binding']
        if create and binding != requested:
            require(binding['generation'] != requested['generation'], 'PAT_SIM_UNSUPPORTED_RECONSTRUCTION')
            self.runtime.registry.bind(self.owner, canonical(requested))
        binding, active = self.runtime.registry._binding(self.fan)
        require(active and binding == requested and self.backend.plant.supports_binding(binding),
                'PAT_SIM_RECONSTRUCTION_FAILED')
        self.backend.refresh(force=True)
        descriptor = copy.deepcopy(self.original_descriptor)
        descriptor.update(type=self.runtime.registry._type(binding['typeDigest']), binding=binding,
                          endpointSession=self.backend.plant.session)
        self.bindings = {self.role: descriptor}
        self.environment = evaluation_environment(self.capsule['artifact'], self.bindings, deployment=self.owner.deployment)
        require(self.environment['evaluationEnvironment'] == self.capsule['evaluationEnvironment'] and
                self.environment['environmentDigest'] == self.capsule['environmentDigest'], 'PAT_SIM_ENVIRONMENT_MISMATCH')

    def close(self):
        if self.runtime is not None:
            self.runtime.close()
            self.runtime = None

    def reopen(self):
        self.capture('before_reopen')
        self.close()
        self.open(create=False)
        self.log.append({'event': 'owner_reopened', 'clock': self.clock.value})
        self.capture('after_reopen')

    def plants(self):
        return {instance: self.backend.plant.observe(instance)
                for instance in sorted(self.capsule['installation']['instances'].values())}

    def operations(self):
        db = self.runtime.journal._db
        ids = [row[0] for row in db.execute('SELECT id FROM operations ORDER BY rowid')]
        require(len(ids) <= len(self.capsule['artifact']['steps']), 'PAT_SIM_EXTRA_OPERATIONS')
        delta = len(ids) - self.accounted
        require(delta >= 0 and self.budget.operations + delta <= self.budget.limits['maxChildOperations'], 'PAT_SIM_EFFECT_LIMIT')
        self.budget.operations += delta
        self.accounted = len(ids)
        return [self.runtime.journal._operation(operation_id) for operation_id in ids]

    def state(self):
        ops = self.operations()
        receipts = [self.backend.plant.receipt(op['id']) for op in ops]
        db = self.runtime.journal._db
        return {'clock': self.clock.value, 'plants': self.plants(), 'operations': ops, 'receipts': receipts,
            'claims': [dict(row) for row in db.execute('SELECT * FROM claims ORDER BY operation_id,resource')],
            'receiptCount': self.backend.plant.db.execute('SELECT count(*) FROM receipts').fetchone()[0],
            'procedure': self.runtime.procedures.status(self.owner, self.procedure_id) if self.procedure_id else None}

    def capture(self, label):
        state = self.state()
        self.evidence.write('checkpoint', {'trial': self.number, 'label': label, 'clock': state['clock'],
            'plants': state['plants'], 'claims': state['claims'], 'receiptCount': state['receiptCount'],
            'procedure': state['procedure']})
        for operation, receipt in zip(state['operations'], state['receipts']):
            self.evidence.write('operation', {'trial': self.number, 'label': label, 'operation': operation, 'receipt': receipt})
        return state

    def lower(self, data):
        artifact = self.capsule['artifact']
        end = ORIGIN + artifact['timingBudget']['latestCompletionOffsetMs']
        namespace = self.runtime.journal.issue_namespace(self.owner, end + 1)['token']
        self.plan = compile_pat(artifact, data['parameters'], self.bindings, origin_ms=ORIGIN,
            replay_namespace=namespace, procedure_key='trial:%d:parent' % self.number,
            operation_keys={step['stepId']: 'trial:%d:step:%d' % (self.number, index)
                for index, step in enumerate(artifact['steps'])}, caller_deadline_ms=end,
            context={key: data[key] for key in ('taskKind', 'inputProfile', 'evidenceMode')} | {'deployment': self.owner.deployment})
        self.request = self.plan['request']
        _assert(self.plan['evaluationEnvironment'] == self.capsule['evaluationEnvironment'], 'compiled environment differs')
        self.evidence.write('compiled_request', {'trial': self.number, 'plan': self.plan})

    def submit(self):
        status = self.runtime.procedures.submit(self.owner, self.request)
        self.procedure_id = status['procedureId']
        self.log.append({'event': 'submitted', 'procedureId': self.procedure_id, 'requestDigest': status['requestDigest']})

    def drive(self, phase='cycle'):
        self.budget.tick()
        self.backend.refresh(force=True)
        if phase == 'cycle':
            self.runtime.tick()
        elif phase == 'procedure':
            self.runtime.procedures.tick()
        elif phase == 'adapter':
            self.backend.tick()
        else:
            raise AssertionError('unknown trusted phase')
        self.operations()
        self.budget.check()

    def next_time(self):
        """Jump to a concrete pending/not-before event; never alter deadlines."""
        now = self.clock.value
        future = [item['due'] for item in self.backend._pending.values() if item['due'] > now]
        for step in self.request['procedure']['steps']:
            value = step['request']['intent']['timing']['notBeforeUnixMs']
            if value > now:
                future.append(value)
        future.append(self.request['procedure']['timing']['latestCompletionUnixMs'])
        self.clock.value = min(value for value in future if value > now) if any(value > now for value in future) else now + 1

    def finish(self):
        while True:
            self.drive()
            status = self.runtime.procedures.status(self.owner, self.procedure_id)
            if status['executionState'] in {'completed', 'failed', 'canceled', 'expired'}:
                return status
            _assert(status['executionState'] != 'interrupted', 'unexpected interruption')
            ops = self.operations()
            # A newly admitted child can dispatch without advancing virtual time.
            if not any(op['state'] == 'accepted' for op in ops):
                self.next_time()

    def first_accepted(self):
        self.drive('procedure')
        while not self.operations():
            self.next_time()
            self.drive('procedure')
            _assert(self.runtime.procedures.status(self.owner, self.procedure_id)['executionState'] == 'accepted', 'first child refused')
        ops = self.operations()
        _assert(len(ops) == 1 and ops[0]['state'] == 'accepted', 'expected first accepted child')

    def first_running(self):
        self.first_accepted()
        self.drive('adapter')
        ops = self.operations()
        _assert(ops[0]['state'] == 'running' and self.backend.plant.receipt(ops[0]['id'])['state'] == 'pending', 'expected pending first receipt')

    def replay(self):
        before = self.state()
        status = self.runtime.procedures.submit(self.owner, self.request)
        _assert(status['procedureId'] == self.procedure_id, 'parent replay changed identity')
        changed = copy.deepcopy(self.request)
        for timing in [changed['procedure']['timing']] + [s['request']['intent']['timing'] for s in changed['procedure']['steps']]:
            for key in timing:
                if key != 'maxRunMs':
                    timing[key] += 1
        try:
            self.runtime.procedures.submit(self.owner, changed)
        except JournalError as error:
            _assert(error.code == 'KEY_CONFLICT', 'wrong parent conflict refusal')
        else:
            raise _OracleFailure('conflicting parent accepted')
        for operation, step in zip(before['operations'], self.request['procedure']['steps']):
            replay = self.runtime.journal.submit(self.owner, canonical(step['request']))
            _assert(replay['id'] == operation['id'], 'child replay changed identity')
            changed_child = copy.deepcopy(step['request'])
            changed_child['intent']['timing']['latestCompletionUnixMs'] += 1
            try:
                self.runtime.journal.submit(self.owner, canonical(changed_child))
            except JournalError as error:
                _assert(error.code == 'KEY_CONFLICT', 'wrong child conflict refusal')
            else:
                raise _OracleFailure('conflicting child accepted')
        _assert(_same(self.state(), before), 'replay/conflict changed retained work or effects')
        self.log.append({'event': 'exact_replay_and_conflict', 'children': len(before['operations'])})

    def oracle(self, *, completed, operations):
        state = self.state()
        _assert(len(state['operations']) == operations, 'operation count mismatch')
        _assert(not state['claims'], 'claims remain')
        _assert(state['receiptCount'] == sum(receipt is not None for receipt in state['receipts']), 'extra receipts')
        db = self.runtime.journal._db
        links = self.runtime.procedures._steps(self.procedure_id)
        _assert(len(links) == len(self.request['procedure']['steps']) and
                [link['operation_id'] for link in links] ==
                [op['id'] for op in state['operations']] + [None] * (len(links) - operations), 'procedure links differ')
        resource = self.capsule['installation']['resources']['fan']
        _assert([dict(row) for row in db.execute('SELECT * FROM resource_floors')] ==
                [{'deployment': self.owner.deployment, 'resource': resource, 'fence': operations}], 'resource floor mismatch')
        replay_rows = [dict(row) for row in db.execute('SELECT * FROM replay_keys ORDER BY rowid')]
        _assert(replay_rows == [{'namespace': self.request['replayNamespace'],
            'caller_key': step['request']['operationKey'], 'operation_id': operation['id']}
            for step, operation in zip(self.request['procedure']['steps'], state['operations'])], 'replay ownership mismatch')
        completed_ops = []
        for index, (operation, receipt) in enumerate(zip(state['operations'], state['receipts'])):
            intended = self.request['procedure']['steps'][index]['request']['intent']
            _assert(_same(operation['intent'], intended) and operation['digest'] == intent_digest(intended), 'operation identity mismatch')
            _assert(operation['admission']['resources'] == [resource], 'admission resource mismatch')
            _assert(operation['state'] in TERMINAL and not operation['claims'] and
                    operation['verification'] not in {'failed', 'disputed'}, 'unresolved operation')
            if receipt is None:
                _assert(operation['state'] == 'canceled' and operation['cancel_state'] == 'confirmed' and
                        operation['may_have_acted'] is False, 'missing receipt lacks no-handoff proof')
                continue
            _assert(receipt['id'] == operation['id'] and receipt['digest'] == operation['digest'] and
                    _same(receipt['intent'], intended) and receipt['state'] != 'pending', 'receipt identity/state mismatch')
            _assert(_same(receipt['claims'], [{'resource': resource, 'fence': index + 1}]), 'receipt claim mismatch')
            if operation['state'] == 'completed':
                args = intended['arguments']
                _assert(receipt['state'] == 'completed' and _same(receipt['result'],
                    {'level': args['level'], 'unit': 'percent', 'effectCommitted': True}), 'completion oracle mismatch')
                completed_ops.append(operation)
            else:
                _assert(receipt['state'] == 'canceled' and receipt['result'].get('effectCommitted') is False, 'cancellation effect mismatch')
        _assert(len(completed_ops) == completed, 'completed effect count mismatch')
        expected_value = completed_ops[-1]['intent']['arguments']['level'] if completed_ops else self.baseline[self.fan]['value']
        _assert(type(state['plants'][self.fan]['value']) is int and state['plants'][self.fan]['value'] == expected_value and
                state['plants'][self.fan]['effectCount'] - self.baseline[self.fan]['effectCount'] == completed,
                'fan final state/effect count mismatch')
        _assert(all(_same(state['plants'][instance], baseline) for instance, baseline in self.baseline.items() if instance != self.fan),
                'unrelated installed device changed')
        self.capture('final')
        for operation in state['operations']:
            after = 0
            while True:
                events = self.runtime.journal.events(self.owner, operation['id'], after=after, limit=100)
                self.evidence.write('operation_events', {'trial': self.number, 'operationId': operation['id'], 'page': events})
                if events['next'] == after or events['next'] >= events['head']:
                    break
                after = events['next']
        after = 0
        while self.procedure_id:
            events = self.runtime.procedures.events(self.owner, self.procedure_id, after=after, limit=100)
            self.evidence.write('procedure_events', {'trial': self.number, 'page': events})
            if events['next'] == after or events['next'] >= events['head']:
                break
            after = events['next']
        return state

    def unresolved(self, state):
        """Count evidenced unresolved jobs; contradictory attribution is unknown."""
        if state['receiptCount'] != sum(receipt is not None for receipt in state['receipts']):
            return None
        completed, unresolved = [], 0
        for index, (operation, receipt) in enumerate(zip(state['operations'], state['receipts'])):
            if receipt is not None:
                if (receipt['digest'] != operation['digest'] or not _same(receipt['intent'], operation['intent']) or
                        not _same(receipt['claims'], [{'resource': self.capsule['installation']['resources']['fan'],
                                                      'fence': index + 1}])):
                    return None
                if receipt['state'] == 'completed':
                    if not _same(receipt['result'], {'level': operation['intent']['arguments']['level'],
                                                    'unit': 'percent', 'effectCommitted': True}):
                        return None
                    completed.append(operation)
                elif receipt['state'] == 'canceled':
                    if receipt['result'].get('effectCommitted') is not False:
                        return None
                elif receipt['state'] != 'pending':
                    return None
            unresolved += bool(operation['state'] not in TERMINAL or operation['claims'] or
                operation['verification'] in {'failed', 'disputed'} or
                (receipt is not None and receipt['state'] == 'pending') or
                (receipt is None and operation['may_have_acted']))
        target = self.baseline[self.fan]['value'] if not completed else completed[-1]['intent']['arguments']['level']
        if (not _same(state['plants'][self.fan]['value'], target) or
                state['plants'][self.fan]['effectCount'] - self.baseline[self.fan]['effectCount'] != len(completed) or
                any(not _same(state['plants'][instance], before) for instance, before in self.baseline.items() if instance != self.fan)):
            return None
        return unresolved


def _run_case(trial, case):
    expected = case['expected']
    data = decode_case_input(case['input'])
    try:
        trial.lower(data)
    except PatError as error:
        wanted = 'PAT_NOT_APPLICABLE' if expected['staticOutcome'] == 'not_applicable' else expected['errorCode']
        _assert(expected['staticOutcome'] != 'applicable' and error.code == wanted, 'static refusal differs from matrix')
        state = trial.state()
        _assert(not state['operations'] and not state['claims'] and state['receiptCount'] == 0 and
                state['plants'] == trial.baseline, 'negative case changed operations or plant')
        trial.capture('negative_refusal')
        trial.log.append({'event': 'static_refusal', 'code': error.code})
        return
    _assert(expected['staticOutcome'] == 'applicable', 'negative case compiled')
    trial.submit()
    trial.replay()
    status = trial.finish()
    _assert(status['executionState'] == 'completed', 'applicable procedure did not complete')
    trial.replay()
    trial.oracle(completed=len(trial.capsule['artifact']['steps']), operations=len(trial.capsule['artifact']['steps']))


def _run_fault(trial, fault, nominal):
    artifact = trial.capsule['artifact']
    trial.lower({'parameters': nominal, 'taskKind': artifact['taskKind'],
                 'inputProfile': artifact['inputProfile'], 'evidenceMode': 'simulation'})
    trial.submit()
    count = len(artifact['steps'])
    if fault in {'cancel_accepted', 'reopen_accepted'}:
        trial.first_accepted()
    else:
        trial.first_running()
    if fault in {'cancel_accepted', 'cancel_running'}:
        trial.runtime.procedures.cancel(trial.owner, trial.procedure_id)
        trial.drive()
        operation, = trial.operations()
        _assert(operation['state'] == 'canceled' and operation['cancel_state'] == 'confirmed', 'cancel was not confirmed')
        if fault == 'cancel_running':
            _assert(trial.backend.plant.receipt(operation['id'])['result']['reason'] == 'client_cancel', 'wrong cancellation reason')
        trial.oracle(completed=0, operations=1)
    elif fault == 'reopen_pending':
        trial.reopen()
        _assert(trial.runtime.procedures.status(trial.owner, trial.procedure_id)['executionState'] == 'interrupted', 'reopen did not pause parent')
        trial.drive('adapter')
        operation, = trial.operations()
        _assert(operation['state'] == 'canceled' and
                trial.backend.plant.receipt(operation['id'])['result']['reason'] == 'simulator_owner_reopened',
                'pending owner reopen was not reconciled')
        try:
            trial.runtime.procedures.resume(trial.owner, trial.procedure_id)
        except JournalError as error:
            _assert(error.code == 'PROCEDURE_DEPENDENCY_UNRESOLVED', 'pending reopen resumed unexpectedly')
        else:
            raise _OracleFailure('canceled pending child resumed')
        trial.runtime.procedures.cancel(trial.owner, trial.procedure_id)
        trial.oracle(completed=0, operations=1)
    else:
        if fault == 'completion_evidence_loss':
            original = trial.runtime.journal.record_execution
            lost = []

            def lose_once(ticket, state, evidence):
                if state == 'completed' and not lost:
                    lost.append(ticket.operation_id)
                    raise _EvidenceLost('modeled completion evidence loss after plant commit')
                return original(ticket, state, evidence)

            trial.runtime.journal.record_execution = lose_once
            trial.next_time()
            try:
                trial.drive('adapter')
            except _EvidenceLost:
                pass
            _assert(len(lost) == 1 and trial.backend.plant.observe(trial.fan)['effectCount'] == 1,
                    'modeled evidence loss boundary not reached')
            trial.log.append({'event': 'modeled_completion_evidence_loss', 'operationId': lost[0], 'realProcessCrash': False})
        trial.reopen()
        _assert(trial.runtime.procedures.status(trial.owner, trial.procedure_id)['executionState'] == 'interrupted', 'reopen did not pause')
        before = trial.plants()
        trial.drive()
        _assert(len(trial.operations()) == 1 and trial.plants() == before and
                trial.runtime.procedures.status(trial.owner, trial.procedure_id)['executionState'] == 'interrupted',
                'reopen automatically continued parent')
        trial.runtime.procedures.resume(trial.owner, trial.procedure_id)
        _assert(trial.finish()['executionState'] == 'completed', 'explicit resume did not complete')
        trial.replay()
        trial.oracle(completed=count, operations=count)
    trial.log.append({'event': fault, 'passed': True})


def run_worker(capsule, trusted_private_output_dir):
    """Run finite original simulations; retain evidence and scratch databases.

    maxOutputBytes strictly bounds emitted canonical evidence. Scratch SQLite
    storage is reported separately and needs a supervisor filesystem quota.
    The deadline is checked at bounded Python boundaries; a supervisor must
    terminate a blocked process. A stopped run is never qualification success.
    """
    capsule = parse_capsule(capsule)
    directory = Path(trusted_private_output_dir)
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and not directory.is_symlink() and info.st_uid == os.geteuid() and
            info.st_mode & 0o077 == 0 and not any(directory.iterdir()), 'PAT_SIM_PRIVATE_DIRECTORY_REQUIRED')
    (directory / 'hms_qualification.evidence').mkdir(mode=0o700)
    (directory / 'work').mkdir(mode=0o700)
    budget = _Budget(capsule['limits'])
    evidence = _Evidence(directory / 'hms_qualification.evidence', budget)
    results, trial = [], None
    pages, storage = [], []
    outcome, reason, unresolved = 'inconclusive', None, None
    planned = len(capsule['caseMatrix']['cases']) + len(FAULTS)
    try:
        evidence.write('input', capsule)
        cases = capsule['caseMatrix']['cases']
        nominal = qualify_fan_contract(capsule['artifact'], next(iter(capsule['bindings'].values())))['nominalParameters']
        for number, item in enumerate([*cases, *FAULTS]):
            budget.check()
            case_id = item['caseId'] if type(item) is dict else 'lifecycle:' + item
            trial = _Trial(capsule, directory / 'work' / ('trial-%02d' % number), budget, evidence, number, case_id)
            trial.initialize()
            if type(item) is dict:
                _run_case(trial, item)
            else:
                _run_fault(trial, item, nominal)
            result = {'trial': number, 'caseId': case_id, 'passed': True, 'events': trial.log}
            evidence.write('trial_result', result)
            results.append(result)
            trial.close()
            trial = None
            storage.append({'completedCases': len(results), 'evidenceBytes': budget.output_bytes,
                'scratchBytes': sum(path.stat().st_size for path in (directory / 'work').rglob('*') if path.is_file())})
        simulation_identities(capsule['limits'])
        budget.check()
        outcome, unresolved = 'passed', 0
    except Exception as error:
        reason = getattr(error, 'code', 'PAT_SIM_WORKER_ERROR')
        outcome = 'failed' if isinstance(error, _OracleFailure) else 'inconclusive'
        if trial is not None and trial.runtime is not None:
            try:
                state = trial.state()
                unresolved = trial.unresolved(state)
                if unresolved is None or unresolved > 0:
                    outcome = 'inconclusive'
                trial.capture('failure')
                evidence.write('trial_error', {'trial': trial.number, 'code': reason,
                    'detail': getattr(error, 'detail', None), 'exceptionType': type(error).__name__, 'events': trial.log})
            except Exception:
                unresolved = None
    finally:
        if trial is not None:
            try:
                trial.close()
            except Exception:
                outcome, reason, unresolved = 'inconclusive', 'PAT_SIM_CLOSE_FAILED', None
    scratch_bytes = sum(path.stat().st_size for path in (directory / 'work').rglob('*') if path.is_file())
    try:
        evidence.write('storage_boundaries', {'boundaries': storage, 'scratchBytes': scratch_bytes,
            'totalDiskQuotaEnforced': False})
        pages = evidence.seal()
        evidence.verify()
    except Exception as error:
        outcome, reason = 'inconclusive', getattr(error, 'code', 'PAT_SIM_EVIDENCE_SEAL_FAILED')
        if reason not in {'PAT_SIM_OUTPUT_LIMIT', 'PAT_SIM_WORKER_DEADLINE', 'PAT_SIM_EVIDENCE_RECORD_LIMIT'}:
            unresolved = None
    return {'profile': RESULT_PROFILE, 'attemptId': capsule['attemptId'], 'outcome': outcome,
        'qualificationPassed': outcome == 'passed', 'reason': reason, 'unresolvedEffects': unresolved,
        'environmentDigest': capsule['environmentDigest'], 'matrixDigest': capsule['matrixDigest'],
        'identities': capsule['identities'], 'configuration': capsule['configuration'],
        'plannedCases': planned, 'completedCases': len(results), 'schedulerTicks': budget.ticks,
        'childOperations': budget.operations, 'outputBytes': budget.output_bytes, 'scratchBytes': scratch_bytes,
        'totalDiskBytes': budget.output_bytes + scratch_bytes, 'totalDiskQuotaEnforced': False,
        'evidenceRecordCount': len(evidence.records), 'evidencePages': pages,
        'scope': 'Finite original SQLite fan trials from fresh synthetic state; no physical objective or live configuration attestation.'}
