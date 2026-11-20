"""Original shared SQLite GPIO/PWM model with durable ownership and idle receipts.

No physical I/O is opened. Atomic model-state/receipt commits are an explicit
simulation capability, not a property inferred for real boards or drivers.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import uuid

from .contracts import SAFE_INTEGER, canonical, identifier, intent_digest, parse_invoke, parse_json
from .journal import JournalError
from .registry import exact
from .synthetic_io_installation import (definitions, handler_details, installation_digest,
    normalize_installation, require)

RECEIPT_PROFILE = 'hms.synthetic-io-receipt/1'


def receipt_digest(value):
    return 'sha256:' + hashlib.sha256(b'HMS-SYNTHETIC-IO-RECEIPT-v1\0' + canonical(value)).hexdigest()


class SyntheticIoBoard:
    def __init__(self, path, installation, *, authority_id, owner_epoch, clock_epoch, create=False):
        self.installation = normalize_installation(installation)
        self.installation_digest = installation_digest(self.installation)
        self.authority_id = identifier(authority_id)
        self.clock_epoch = identifier(clock_epoch)
        require(type(owner_epoch) is int and 1 <= owner_epoch <= SAFE_INTEGER, 'IO_OWNER_EPOCH_INVALID')
        self.owner_epoch = owner_epoch
        self.definitions = definitions(self.installation)
        self._details = {(row['instanceId'], row['actionId']): handler_details(self.installation, row['instanceId'], row['actionId'])
                         for row in self.installation['handlers']}
        self._idle = {}
        for detail in self._details.values():
            for atom in detail['claims']:
                node = self.installation['topology']['nodes'][self.installation['topology']['atoms'][atom]['node']]
                if node['kind'] == 'pin':
                    state = {'kind': 'pin', 'mode': 'high_impedance', 'level': None}
                elif node['kind'] == 'timer':
                    state = {'kind': 'timer', 'enabled': False, 'frequencyHz': 0, 'resolutionBits': 0}
                elif node['kind'] == 'timer_channel':
                    state = {'kind': 'timer_channel', 'enabled': False, 'dutyPermille': 0}
                else:
                    raise JournalError('IO_RESOURCE_UNSUPPORTED')
                self._idle[atom] = state
        self.path = Path(path)
        self.lock = threading.RLock()
        self.db = None; self._owner_fd = None; self._closed = False
        try:
            self._owner_fd = os.open(str(self.path) + '.owner', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(self._owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JournalError('IO_BOARD_OWNER_BUSY') from error
            if create:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600); os.close(fd)
            else:
                require(self.path.is_file() and not self.path.is_symlink(), 'IO_BOARD_MISSING')
            self.db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=0.2)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA journal_mode=DELETE'); self.db.execute('PRAGMA synchronous=EXTRA')
            if create:
                self._create()
            self._open()
        except BaseException:
            self.close(); raise

    @contextmanager
    def _transaction(self):
        with self.lock:
            require(not self._closed and not self.db.in_transaction, 'IO_BOARD_TRANSACTION_STATE')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise

    def _create(self):
        with self._transaction():
            statements = (
                'CREATE TABLE io_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)',
                'CREATE TABLE io_resources(resource TEXT PRIMARY KEY,state BLOB NOT NULL)',
                'CREATE TABLE io_owners(resource TEXT PRIMARY KEY,operation TEXT NOT NULL,fence INTEGER NOT NULL)',
                'CREATE TABLE io_fences(resource TEXT PRIMARY KEY,fence INTEGER NOT NULL,operation TEXT NOT NULL)',
                'CREATE TABLE io_receipts(operation TEXT PRIMARY KEY,state TEXT NOT NULL,sequence INTEGER NOT NULL,digest TEXT NOT NULL,document BLOB NOT NULL)',
                'CREATE TABLE io_receipt_versions(operation TEXT NOT NULL,sequence INTEGER NOT NULL,digest TEXT NOT NULL,document BLOB NOT NULL,PRIMARY KEY(operation,sequence))',
                'CREATE TABLE io_effects(instance TEXT PRIMARY KEY,activations INTEGER NOT NULL,completed INTEGER NOT NULL,canceled INTEGER NOT NULL)')
            for statement in statements:
                self.db.execute(statement)
            metadata = {'profile': 'hms.synthetic-io-board/1', 'authority': self.authority_id,
                'deployment': self.installation['topology']['deployment'], 'board': self.installation['boardId'],
                'installation': canonical(self.installation).decode(), 'installationDigest': self.installation_digest,
                'ownerEpoch': str(self.owner_epoch), 'clockEpoch': self.clock_epoch, 'session': 'io-session:' + uuid.uuid4().hex}
            self.db.executemany('INSERT INTO io_meta VALUES (?,?)', metadata.items())
            self.db.executemany('INSERT INTO io_resources VALUES (?,?)', ((atom, canonical(state)) for atom, state in self._idle.items()))
            self.db.executemany('INSERT INTO io_effects VALUES (?,0,0,0)', ((instance,) for instance in self.definitions))

    def _meta(self, key):
        row = self.db.execute('SELECT value FROM io_meta WHERE key=?', (key,)).fetchone()
        require(row is not None, 'IO_BOARD_METADATA_MISSING')
        return row[0]

    def _open(self):
        with self._transaction():
            expected = {'profile': 'hms.synthetic-io-board/1', 'authority': self.authority_id,
                'deployment': self.installation['topology']['deployment'], 'board': self.installation['boardId'],
                'installation': canonical(self.installation).decode(), 'installationDigest': self.installation_digest}
            require(all(self._meta(key) == value for key, value in expected.items()), 'IO_BOARD_IDENTITY_CHANGED')
            previous = int(self._meta('ownerEpoch'))
            require(1 <= previous <= self.owner_epoch, 'IO_BOARD_OWNER_EPOCH_REGRESSION')
            require(previous != self.owner_epoch or self._meta('clockEpoch') == self.clock_epoch, 'IO_BOARD_CLOCK_EPOCH_CHANGED')
            self._validate_state()
            if previous < self.owner_epoch:
                # Only internally consistent owned model state justifies this
                # declared atomic idle transition. Missing evidence is not fixed.
                pending = self.db.execute("SELECT operation FROM io_receipts WHERE state='pending' ORDER BY operation LIMIT 129").fetchall()
                require(len(pending) <= 128, 'IO_BOARD_PENDING_LIMIT')
                for row in pending:
                    self._idle_receipt(self.receipt(row[0]), 'canceled', 'board_owner_reopened')
                self.db.execute("UPDATE io_meta SET value=? WHERE key='ownerEpoch'", (str(self.owner_epoch),))
                self.db.execute("UPDATE io_meta SET value=? WHERE key='clockEpoch'", (self.clock_epoch,))
                self.db.execute("UPDATE io_meta SET value=? WHERE key='session'", ('io-session:' + uuid.uuid4().hex,))
            self.session = identifier(self._meta('session'))

    def close(self):
        with self.lock:
            if not self._closed:
                if self.db is not None:
                    self.db.close()
                if self._owner_fd is not None:
                    os.close(self._owner_fd)
                self._closed = True

    def supports_binding(self, binding):
        expected = self.definitions.get(binding.get('instanceId'))
        return expected is not None and canonical(binding) == canonical(expected['binding'])

    def _arguments(self, intent):
        detail = self._details.get((intent['instanceId'], intent['actionId']))
        require(detail is not None, 'IO_HANDLER_UNSUPPORTED')
        args = intent['arguments']
        schema = self.definitions[intent['instanceId']]['binding']['argumentSchemas'][intent['actionId']]
        require(type(args) is dict and set(args) == set(schema['properties']), 'IO_ARGUMENTS_REFUSED')
        for key, limits in schema['properties'].items():
            value = args[key]
            require(type(value) is int and limits.get('minimum', value) <= value <= limits.get('maximum', value)
                    and value == limits.get('const', value), 'IO_ARGUMENTS_REFUSED')
        require(intent['requiredEffect'] == 'capability_completion' and intent['timing']['maxRunMs'] <= 5000,
                'IO_EFFECT_UNSUPPORTED')
        return detail

    def validate_admission(self, adapter, intent, binding, resources):
        require(self.supports_binding(binding) and binding['adapterId'] == adapter, 'IO_INSTALLATION_UNSUPPORTED')
        detail = self._arguments(intent)
        require(tuple(resources) == tuple(detail['claims']), 'IO_CLAIM_CLOSURE')
        require(intent['endpointSession'] == self.session, 'IO_SESSION_CHANGED')

    def _validate_operation(self, operation, adapter):
        identifier(operation['id'])
        intent = operation['intent']
        parse_invoke(canonical({'protocol': 'hms.invoke/0.1', 'replayNamespace': 'io:validation', 'operationKey': 'io:validation', 'intent': intent}))
        require(operation['digest'] == intent_digest(intent), 'IO_OPERATION_DIGEST')
        expected = self.definitions.get(intent['instanceId'])
        require(expected is not None and expected['binding']['adapterId'] == adapter, 'IO_ROUTE_MISMATCH')
        binding = expected['binding']
        for intent_key, binding_key in (('descriptionDigest','typeDigest'), ('bindingGeneration','generation'),
                                        ('controlGeneration','controlGeneration'), ('calibrationRevision','calibrationRevision')):
            require(intent[intent_key] == binding[binding_key], 'IO_BINDING_CHANGED')
        detail = self._arguments(intent)
        claims = operation['claims']
        require(type(claims) is list and len(claims) == len(detail['claims']), 'IO_CLAIM_CLOSURE')
        for claim, atom in zip(claims, detail['claims']):
            exact(claim, {'resource','fence'})
            require(claim['resource'] == atom and type(claim['fence']) is int and 1 <= claim['fence'] <= SAFE_INTEGER,
                    'IO_CLAIM_CLOSURE')
        return detail

    def _active_state(self, intent, detail):
        args = intent['arguments']; result = {}
        for atom in detail['claims']:
            state = self._idle[atom]; kind = state['kind']
            if kind == 'pin':
                state = {'kind': kind, 'mode': 'push_pull_output' if detail['primitive'] == 'gpio_pulse' else 'pwm_output',
                         'level': args['level'] if detail['primitive'] == 'gpio_pulse' else None}
            elif kind == 'timer':
                state = {'kind': kind, 'enabled': True, 'frequencyHz': args['frequencyHz'], 'resolutionBits': args['resolutionBits']}
            else:
                state = {'kind': kind, 'enabled': True, 'dutyPermille': args['dutyPermille']}
            result[atom] = state
        return result

    def _store_receipt(self, value):
        data, digest = canonical(value), receipt_digest(value)
        self.db.execute('INSERT INTO io_receipt_versions VALUES (?,?,?,?)', (value['operationId'], value['sequence'], digest, data))
        self.db.execute('INSERT INTO io_receipts VALUES (?,?,?,?,?) ON CONFLICT(operation) DO UPDATE SET state=excluded.state,sequence=excluded.sequence,digest=excluded.digest,document=excluded.document',
            (value['operationId'], value['state'], value['sequence'], digest, data))

    def receipt(self, operation_id, *, sequence=None):
        with self.lock:
            if sequence is None:
                row = self.db.execute('SELECT sequence,digest,document FROM io_receipts WHERE operation=?', (operation_id,)).fetchone()
            else:
                require(type(sequence) is int and sequence in {1,2}, 'IO_RECEIPT_SEQUENCE')
                row = self.db.execute('SELECT sequence,digest,document FROM io_receipt_versions WHERE operation=? AND sequence=?', (operation_id,sequence)).fetchone()
            if row is None:
                return None
            value = parse_json(bytes(row['document']))
            require(canonical(value) == bytes(row['document']) and receipt_digest(value) == row['digest'], 'IO_RECEIPT_INTEGRITY')
            require(value['operationId'] == operation_id and value['sequence'] == row['sequence'], 'IO_RECEIPT_IDENTITY')
            self._validate_receipt(value)
            return value

    def _validate_receipt(self, value):
        exact(value, {'profile','operationId','sequence','authorityId','boardId','installationDigest','adapterId','digest','intent','claims',
                      'ownerEpoch','clockEpoch','providerSession','state','startedMonoMs','budgetOriginMonoMs','dueMonoMs','activeState','idleState','result'})
        require(value['profile'] == RECEIPT_PROFILE and value['authorityId'] == self.authority_id and
                value['boardId'] == self.installation['boardId'] and value['installationDigest'] == self.installation_digest,
                'IO_RECEIPT_IDENTITY')
        detail = self._validate_operation({'id':value['operationId'],'digest':value['digest'],'intent':value['intent'],'claims':value['claims']}, value['adapterId'])
        require(type(value['sequence']) is int and value['sequence'] in {1,2} and type(value['ownerEpoch']) is int and
                1 <= value['ownerEpoch'] <= self.owner_epoch, 'IO_RECEIPT_IDENTITY')
        identifier(value['clockEpoch']); identifier(value['providerSession'])
        require(value['providerSession'] == value['intent']['endpointSession'], 'IO_RECEIPT_SESSION')
        require(canonical(value['activeState']) == canonical(self._active_state(value['intent'], detail)) and
                canonical(value['idleState']) == canonical({atom:self._idle[atom] for atom in detail['claims']}), 'IO_RECEIPT_STATE')
        result = value['result']; exact(result, {'activationCommitted','cycleCompleted','safeIdle','reason'})
        require(all(type(result[key]) is bool for key in ('activationCommitted','cycleCompleted','safeIdle')), 'IO_RECEIPT_STATE')
        state = value['state']
        require(state in {'pending','completed','canceled','rejected_before_start'}, 'IO_RECEIPT_STATE')
        if state == 'rejected_before_start':
            require(value['sequence'] == 1 and (result['activationCommitted'],result['cycleCompleted'],result['safeIdle']) == (False,False,True)
                    and all(value[key] is None for key in ('startedMonoMs','budgetOriginMonoMs','dueMonoMs')), 'IO_RECEIPT_STATE')
        else:
            require(all(type(value[key]) is int and 0 <= value[key] <= SAFE_INTEGER for key in ('startedMonoMs','budgetOriginMonoMs','dueMonoMs')),
                    'IO_RECEIPT_TIME')
            require(value['budgetOriginMonoMs'] <= value['startedMonoMs'] and
                    value['dueMonoMs'] == value['startedMonoMs'] + value['intent']['arguments']['durationMs'], 'IO_RECEIPT_TIME')
            require(result['activationCommitted'] and result['cycleCompleted'] == (state == 'completed') and
                    result['safeIdle'] == (state != 'pending') and value['sequence'] == (1 if state == 'pending' else 2), 'IO_RECEIPT_STATE')
        if state in {'canceled','rejected_before_start'}:
            identifier(result['reason'])
        else:
            require(result['reason'] is None, 'IO_RECEIPT_STATE')

    def _validate_state(self):
        resources = {row['resource']: parse_json(bytes(row['state'])) for row in self.db.execute('SELECT * FROM io_resources')}
        require(set(resources) == set(self._idle), 'IO_RESOURCE_INVENTORY')
        owners = {row['resource']: dict(row) for row in self.db.execute('SELECT * FROM io_owners')}
        require(set(owners) <= set(resources), 'IO_OWNERSHIP_UNKNOWN')
        pending = self.db.execute("SELECT operation FROM io_receipts WHERE state='pending' LIMIT 129").fetchall()
        require(len(pending) <= 128, 'IO_BOARD_PENDING_LIMIT')
        pending_ids = {row[0] for row in pending}
        require({row['operation'] for row in owners.values()} == pending_ids, 'IO_OWNERSHIP_UNKNOWN')
        counters = {row['instance']:dict(row) for row in self.db.execute('SELECT * FROM io_effects')}
        require(set(counters) == set(self.definitions), 'IO_EFFECT_INVENTORY')
        pending_counts = {instance:0 for instance in counters}
        for operation in pending_ids:
            receipt = self.receipt(operation)
            require(receipt['state'] == 'pending', 'IO_RECEIPT_STATE')
            pending_counts[receipt['intent']['instanceId']] += 1
            expected = {row['resource']:row['fence'] for row in receipt['claims']}
            require({atom:row['fence'] for atom,row in owners.items() if row['operation'] == operation} == expected, 'IO_OWNERSHIP_UNKNOWN')
            for atom,fence in expected.items():
                floor = self.db.execute('SELECT fence,operation FROM io_fences WHERE resource=?', (atom,)).fetchone()
                require(floor is not None and floor['fence'] == fence and floor['operation'] == operation and
                        canonical(resources[atom]) == canonical(receipt['activeState'][atom]), 'IO_OWNERSHIP_UNKNOWN')
        for atom,state in resources.items():
            if atom not in owners:
                require(canonical(state) == canonical(self._idle[atom]), 'IO_QUIESCENCE_UNKNOWN')
        for instance,row in counters.items():
            require(all(type(row[key]) is int and 0 <= row[key] <= SAFE_INTEGER for key in ('activations','completed','canceled')) and
                    row['activations'] == row['completed'] + row['canceled'] + pending_counts[instance], 'IO_EFFECT_COUNTER_INVALID')

    def begin(self, operation, adapter, *, guard):
        require(callable(guard), 'IO_START_GUARD_REQUIRED')
        with self._transaction():
            detail = self._validate_operation(operation, adapter)
            old = self.receipt(operation['id'])
            if old is not None:
                require(old['digest'] == operation['digest'] and canonical(old['intent']) == canonical(operation['intent']) and
                        canonical(old['claims']) == canonical(operation['claims']) and old['adapterId'] == adapter, 'IO_OPERATION_KEY_CONFLICT')
                return old
            self._validate_state()
            require(operation['intent']['endpointSession'] == self.session, 'IO_SESSION_CHANGED')
            require(self.db.execute('SELECT activations FROM io_effects WHERE instance=?', (operation['intent']['instanceId'],)).fetchone()[0] < SAFE_INTEGER,
                    'IO_EFFECT_COUNTER_EXHAUSTED')
            for claim in operation['claims']:
                require(self.db.execute('SELECT 1 FROM io_owners WHERE resource=?', (claim['resource'],)).fetchone() is None, 'IO_RESOURCE_BUSY')
                floor = self.db.execute('SELECT fence FROM io_fences WHERE resource=?', (claim['resource'],)).fetchone()
                require(floor is None or claim['fence'] > floor[0], 'IO_STALE_FENCE')
            decision = guard()
            exact(decision, {'reason','nowMonoMs','budgetOriginMonoMs','clockEpoch'})
            reason = decision['reason']
            if reason is not None:
                identifier(reason)
            else:
                require(decision['clockEpoch'] == self.clock_epoch and all(type(decision[key]) is int and 0 <= decision[key] <= SAFE_INTEGER
                    for key in ('nowMonoMs','budgetOriginMonoMs')) and decision['budgetOriginMonoMs'] <= decision['nowMonoMs'], 'IO_START_CLOCK')
                if decision['nowMonoMs'] + operation['intent']['arguments']['durationMs'] >= decision['budgetOriginMonoMs'] + operation['intent']['timing']['maxRunMs']:
                    reason = 'duration_budget_excluded'
            state = 'pending' if reason is None else 'rejected_before_start'
            started = decision['nowMonoMs'] if reason is None else None
            receipt = {'profile':RECEIPT_PROFILE,'operationId':operation['id'],'sequence':1,'authorityId':self.authority_id,
                'boardId':self.installation['boardId'],'installationDigest':self.installation_digest,'adapterId':adapter,
                'digest':operation['digest'],'intent':operation['intent'],'claims':operation['claims'],'ownerEpoch':self.owner_epoch,
                'clockEpoch':self.clock_epoch,'providerSession':self.session,'state':state,'startedMonoMs':started,
                'budgetOriginMonoMs':decision['budgetOriginMonoMs'] if reason is None else None,
                'dueMonoMs':started + operation['intent']['arguments']['durationMs'] if reason is None else None,
                'activeState':self._active_state(operation['intent'],detail),'idleState':{atom:self._idle[atom] for atom in detail['claims']},
                'result':{'activationCommitted':reason is None,'cycleCompleted':False,'safeIdle':reason is not None,'reason':reason}}
            if reason is None:
                for claim in operation['claims']:
                    atom,fence = claim['resource'],claim['fence']
                    self.db.execute('INSERT INTO io_fences VALUES (?,?,?) ON CONFLICT(resource) DO UPDATE SET fence=excluded.fence,operation=excluded.operation', (atom,fence,operation['id']))
                    self.db.execute('INSERT INTO io_owners VALUES (?,?,?)', (atom,operation['id'],fence))
                    self.db.execute('UPDATE io_resources SET state=? WHERE resource=?', (canonical(receipt['activeState'][atom]),atom))
                self.db.execute('UPDATE io_effects SET activations=activations+1 WHERE instance=?', (operation['intent']['instanceId'],))
            self._validate_receipt(receipt); self._store_receipt(receipt)
            return parse_json(canonical(receipt))

    def _idle_receipt(self, receipt, state, reason):
        # Caller validated complete active ownership before entering this path.
        for claim in receipt['claims']:
            atom = claim['resource']
            self.db.execute('UPDATE io_resources SET state=? WHERE resource=?', (canonical(self._idle[atom]),atom))
        self.db.execute('DELETE FROM io_owners WHERE operation=?', (receipt['operationId'],))
        field = 'completed' if state == 'completed' else 'canceled'
        self.db.execute('UPDATE io_effects SET ' + field + '=' + field + '+1 WHERE instance=?', (receipt['intent']['instanceId'],))
        value = receipt | {'state':state,'sequence':2,'result':{'activationCommitted':True,'cycleCompleted':state == 'completed','safeIdle':True,'reason':reason}}
        self._validate_receipt(value); self._store_receipt(value)
        return value

    def finish(self, operation_id, *, guard, cancel_reason=None):
        require(callable(guard) or cancel_reason is not None, 'IO_FINISH_GUARD_REQUIRED')
        with self._transaction():
            receipt = self.receipt(operation_id)
            require(receipt is not None, 'IO_RECEIPT_MISSING')
            if receipt['state'] != 'pending':
                return receipt
            self._validate_state()
            if cancel_reason is not None:
                identifier(cancel_reason)
                return self._idle_receipt(receipt,'canceled',cancel_reason)
            decision = guard(receipt)
            exact(decision, {'reason','nowMonoMs','clockEpoch'})
            reason = decision['reason']
            if reason is not None:
                identifier(reason)
                return self._idle_receipt(receipt,'canceled',reason)
            require(decision['clockEpoch'] == receipt['clockEpoch'] and type(decision['nowMonoMs']) is int and
                    receipt['startedMonoMs'] <= decision['nowMonoMs'] <= SAFE_INTEGER, 'IO_FINISH_CLOCK')
            if decision['nowMonoMs'] < receipt['dueMonoMs']:
                return receipt
            return self._idle_receipt(receipt,'completed',None)

    def observe(self, instance):
        with self.lock:
            require(instance in self.definitions, 'IO_INSTANCE_UNSUPPORTED')
            self._validate_state()
            row = self.db.execute('SELECT * FROM io_effects WHERE instance=?', (instance,)).fetchone()
            require(row is not None and all(type(row[key]) is int and 0 <= row[key] <= SAFE_INTEGER for key in ('activations','completed','canceled')),
                    'IO_EFFECT_COUNTER_INVALID')
            atoms = sorted({atom for (owner,_),detail in self._details.items() if owner == instance for atom in detail['claims']})
            states = {atom:parse_json(bytes(self.db.execute('SELECT state FROM io_resources WHERE resource=?',(atom,)).fetchone()[0])) for atom in atoms}
            return {'value':row['activations'],'ready':True,'completed':row['completed'],'canceled':row['canceled'],'resources':states}
