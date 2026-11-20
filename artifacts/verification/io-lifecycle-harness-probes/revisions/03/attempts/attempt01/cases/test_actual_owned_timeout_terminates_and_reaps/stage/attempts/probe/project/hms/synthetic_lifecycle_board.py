"""Original atomic generation model, sharing the ordinary pin/fence board store."""
from collections import OrderedDict

from .contracts import SAFE_INTEGER, canonical, identifier, intent_digest, parse_invoke, parse_json
from .registry import exact
from .resource_topology import binding_proof, generation_change_claims, parse_generations
from .synthetic_io_board import SyntheticIoBoard
from .synthetic_io_adapter import link_digest
from .synthetic_io_installation import definitions as io_definitions, require
from .synthetic_io_storage import bounded_rows, document_row, metadata_text
from .synthetic_lifecycle_contracts import (action_for, arguments, definitions, digest,
    installation_digest, normalize, snapshot)


class LifecycleBoard(SyntheticIoBoard):
    PROFILE = 'hms.synthetic-io-board/lifecycle/1'

    def __init__(self, path, installation, **kwargs):
        self.lifecycle_document = normalize(installation)
        self.lifecycle_digest = installation_digest(self.lifecycle_document)
        self.management_definitions = definitions(self.lifecycle_document)
        self._historical = OrderedDict()
        self.current_definitions = {}
        super().__init__(path, self.lifecycle_document['io'], **kwargs)

    def _extend_idle(self):
        graph = self.lifecycle_document['io']['topology']
        targets = {target for row in self.lifecycle_document['management'] for target in row['actions'].values()}
        for atom, detail in graph['atoms'].items():
            if detail['node'] in targets and detail['purpose'] == 'lifecycle':
                self._idle[atom] = {'kind':'lifecycle','idle':True}

    def _create(self):
        self._extend_idle()
        super()._create()
        initial = self.installation['initialGenerations']
        with self._transaction():
            for sql in (
                'CREATE TABLE io_lc_snapshots(revision INTEGER PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL,operation TEXT NOT NULL)',
                'CREATE TABLE io_lc_tokens(node TEXT NOT NULL,generation TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(node,generation))',
                'CREATE TABLE io_lc_bindings(instance TEXT NOT NULL,generation TEXT NOT NULL,revision INTEGER NOT NULL,document BLOB NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(instance,generation))',
                'CREATE TABLE io_lc_receipts(operation TEXT PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL)'):
                self.db.execute(sql)
            self.db.executemany('INSERT INTO io_meta VALUES(?,?)',
                [('lifecycleInstallationDigest',self.lifecycle_digest),('lifecycleRevision','1')])
            self._store_snapshot(initial,'')
            self.db.executemany('INSERT INTO io_lc_tokens VALUES(?,?,1)',initial['nodes'].items())
            self._store_bindings(initial)

    def _open(self):
        self._extend_idle()
        require(metadata_text(self.db,'lifecycleInstallationDigest') == self.lifecycle_digest, 'LIFECYCLE_BOARD_IDENTITY')
        self._refresh_current()
        super()._open()

    def _store_snapshot(self, value, operation):
        self.db.execute('INSERT INTO io_lc_snapshots VALUES(?,?,?,?)',
            (value['revision'],canonical(value),digest('HMS-LIFECYCLE-BOARD-GENERATIONS-v1',value),operation))

    def _read_snapshot(self, revision):
        require(type(revision) is int and 1 <= revision <= SAFE_INTEGER,'LIFECYCLE_BOARD_HISTORY')
        row = document_row(self.db,'io_lc_snapshots',{'revision':revision},extra=('operation',))
        require(row is not None,'LIFECYCLE_BOARD_HISTORY')
        value = parse_generations(self.installation['topology'],bytes(row['document']))
        require(value['revision'] == revision and canonical(value) == bytes(row['document']) and
            row['digest'] == digest('HMS-LIFECYCLE-BOARD-GENERATIONS-v1',value),'LIFECYCLE_BOARD_HISTORY')
        for node,token in value['nodes'].items():
            records = bounded_rows(self.db,'io_lc_tokens',('revision',),limit=1,keys={'node':node,'generation':token})
            require(len(records) == 1 and type(records[0]['revision']) is int and 1 <= records[0]['revision'] <= revision,
                'LIFECYCLE_BOARD_HISTORY')
        return value,row['operation']

    def _binding_rows(self, generations):
        rows = []
        for instance, definition in io_definitions(self.installation,generations=generations).items():
            generation = definition['binding']['generation']
            value = {'binding':definition['binding'],'proof':definition['proof']}
            old = document_row(self.db,'io_lc_bindings',{'instance':instance,'generation':generation},extra=('revision',))
            if old is not None:
                require(bytes(old['document']) == canonical(value) and old['digest'] == digest('HMS-LIFECYCLE-BOARD-BINDING-v1',value),
                    'LIFECYCLE_BOARD_BINDING_HISTORY')
                continue
            rows.append((instance,generation,generations['revision'],canonical(value),digest('HMS-LIFECYCLE-BOARD-BINDING-v1',value)))
        return rows

    def _store_bindings(self, generations):
        self.db.executemany('INSERT INTO io_lc_bindings VALUES(?,?,?,?,?)',self._binding_rows(generations))

    def _refresh_current(self):
        raw = metadata_text(self.db,'lifecycleRevision')
        require(raw.isascii() and raw.isdigit() and len(raw) <= 16,'LIFECYCLE_BOARD_HISTORY')
        value,_operation = self._read_snapshot(int(raw))
        self._current_generations = value
        self.current_definitions = io_definitions(self.installation,generations=value)

    def _acquire_history(self, instance, generation):
        """Explicit provider read, never invoked from a policy evidence callback."""
        if instance in self.management_definitions:
            require(self.management_definitions[instance]['binding']['generation'] == generation,'LIFECYCLE_BINDING_CHANGED')
            return
        row = document_row(self.db,'io_lc_bindings',{'instance':instance,'generation':generation},extra=('revision',))
        require(row is not None,'LIFECYCLE_BOARD_BINDING_HISTORY')
        saved = snapshot(bytes(row['document'])); exact(saved,{'binding','proof'})
        generations,_operation = self._read_snapshot(row['revision'])
        expected = io_definitions(self.installation,generations=generations).get(instance)
        require(expected is not None and saved['binding']['generation'] == generation and
            canonical(saved) == bytes(row['document']) and row['digest'] == digest('HMS-LIFECYCLE-BOARD-BINDING-v1',saved) and
            canonical(saved) == canonical({'binding':expected['binding'],'proof':expected['proof']}),'LIFECYCLE_BOARD_BINDING_HISTORY')
        key = (instance,generation)
        self._historical[key] = expected; self._historical.move_to_end(key)
        while len(self._historical) > 128:
            self._historical.popitem(last=False)

    def _descriptor(self, intent):
        instance = intent['instanceId']; generation = intent['bindingGeneration']
        current = self.management_definitions.get(instance) or self.current_definitions.get(instance)
        if current is not None and current['binding']['generation'] == generation:
            return current
        result = self._historical.get((instance,generation))
        require(result is not None,'LIFECYCLE_HISTORY_NOT_ACQUIRED')
        return result

    def supports_binding(self, binding):
        expected = self.current_definitions.get(binding.get('instanceId'))
        return expected is not None and canonical(binding) == canonical(expected['binding'])

    def management_supports_binding(self, binding):
        expected = self.management_definitions.get(binding.get('instanceId'))
        return expected is not None and canonical(binding) == canonical(expected['binding'])

    def _validate_operation(self, operation, adapter):
        # Pure validation: current descriptors or explicitly acquired history.
        identifier(operation['id']); intent = operation['intent']
        parse_invoke(canonical({'protocol':'hms.invoke/0.1','replayNamespace':'io:validation','operationKey':'io:validation','intent':intent}))
        require(operation['digest'] == intent_digest(intent),'IO_OPERATION_DIGEST')
        expected = self._descriptor(intent); binding = expected['binding']
        require(binding['adapterId'] == adapter,'IO_ROUTE_MISMATCH')
        for name, field in (('descriptionDigest','typeDigest'),('bindingGeneration','generation'),
                            ('controlGeneration','controlGeneration'),('calibrationRevision','calibrationRevision')):
            require(intent[name] == binding[field],'IO_BINDING_CHANGED')
        if intent['instanceId'] in self.management_definitions:
            _entry,target = action_for(self.lifecycle_document,intent['instanceId'],intent['actionId'])
            arguments(intent['arguments'])
            require(intent['requiredEffect'] == 'capability_completion','IO_EFFECT_UNSUPPORTED')
            detail = {'claims':generation_change_claims(self.installation['topology'],target)['claims'],'target':target}
        else:
            detail = self._arguments(intent)  # Immutable electrical/argument envelopes.
        claims = operation['claims']
        require(type(claims) is list and len(claims) == len(detail['claims']),'IO_CLAIM_CLOSURE')
        for claim,atom in zip(claims,detail['claims']):
            exact(claim,{'resource','fence'})
            require(claim['resource'] == atom and type(claim['fence']) is int and 1 <= claim['fence'] <= SAFE_INTEGER,'IO_CLAIM_CLOSURE')
        return detail

    def receipt(self, operation_id, *, sequence=None):
        with self.lock:
            table = 'io_receipts' if sequence is None else 'io_receipt_versions'
            keys = {'operation':operation_id} if sequence is None else {'operation':operation_id,'sequence':sequence}
            row = document_row(self.db,table,keys)
            if row is not None:
                value = snapshot(bytes(row['document']))
                self._acquire_history(value['intent']['instanceId'],value['intent']['bindingGeneration'])
            return super().receipt(operation_id,sequence=sequence)

    def begin(self, operation, adapter, *, guard):
        with self.lock:
            existing = self.receipt(operation['id'])
            if existing is None:
                self._refresh_current()
                definition = self.current_definitions.get(operation['intent']['instanceId'])
                require(definition is not None and definition['binding']['generation'] == operation['intent']['bindingGeneration'],
                    'IO_BINDING_CHANGED')
            return super().begin(operation,adapter,guard=guard)

    def _validate_state(self):
        super()._validate_state()
        value,operation = self._read_snapshot(self._current_generations['revision'])
        require(canonical(value) == canonical(self._current_generations),'LIFECYCLE_BOARD_HISTORY')
        if operation:
            receipt = self.lifecycle_receipt(operation)
            require(receipt is not None and receipt['generationApplied'] and receipt['afterRevision'] == value['revision'],
                'LIFECYCLE_BOARD_HISTORY')
            before,_ = self._read_snapshot(receipt['beforeRevision'])
            expected = snapshot(before); expected['revision'] += 1
            expected['nodes'][receipt['dispatch']['target']] = receipt['dispatch']['newGeneration']
            require(before['nodes'][receipt['dispatch']['target']] == receipt['dispatch']['oldGeneration'] and
                canonical(expected) == canonical(value),'LIFECYCLE_BOARD_HISTORY')

    def lifecycle_receipt(self, operation_id):
        with self.lock:
            row = document_row(self.db,'io_lc_receipts',{'operation':operation_id})
            if row is None:
                return None
            value = snapshot(bytes(row['document']))
            require(canonical(value) == bytes(row['document']) and row['digest'] == digest('HMS-LIFECYCLE-RECEIPT-v1',value),
                'LIFECYCLE_RECEIPT_CHANGED')
            self.validate_lifecycle_receipt(value)
            return value

    def validate_lifecycle_receipt(self, value):
        """Pure closed validation; current state/history checks are separate reads."""
        exact(value,{'profile','operationId','authorityId','boardId','installationDigest','ioLink','dispatch',
            'generationApplied','safeIdle','idleState','beforeRevision','afterRevision','reason'})
        require(value['profile'] == 'hms.synthetic-lifecycle-receipt/1' and value['authorityId'] == self.authority_id and
            value['boardId'] == self.installation['boardId'] and value['installationDigest'] == self.lifecycle_digest,
            'LIFECYCLE_RECEIPT_IDENTITY')
        link = value['ioLink']; dispatch = value['dispatch']
        exact(link,{'profile','operationId','digest','intent','claims','adapterId','authorityId','attemptId','ownerEpoch',
            'checkpoint','budgetOriginMonoMs','clockEpoch','installationDigest'})
        exact(dispatch,{'profile','operationId','ioDispatchDigest','installationDigest','target','oldGeneration','newGeneration',
            'dispatchRevision','scope','affected'})
        require(link['profile'] == 'hms.synthetic-io-dispatch/1' and link['authorityId'] == self.authority_id and
            link['installationDigest'] == self.installation_digest and dispatch['profile'] == 'hms.synthetic-lifecycle-dispatch/1' and
            dispatch['installationDigest'] == self.lifecycle_digest and dispatch['ioDispatchDigest'] == link_digest(link),
            'LIFECYCLE_RECEIPT_IDENTITY')
        for field in ('attemptId','clockEpoch','adapterId'):
            identifier(link[field])
        require(all(type(link[key]) is int and 0 <= link[key] <= SAFE_INTEGER for key in ('ownerEpoch','checkpoint','budgetOriginMonoMs')) and
            1 <= link['ownerEpoch'] <= self.owner_epoch and link['clockEpoch'] == self.authority_id+':'+str(link['ownerEpoch']),
            'LIFECYCLE_RECEIPT_IDENTITY')
        require(value['operationId'] == link['operationId'] == dispatch['operationId'],'LIFECYCLE_RECEIPT_IDENTITY')
        detail = self._validate_operation({'id':value['operationId'],'digest':link['digest'],'intent':link['intent'],'claims':link['claims']},link['adapterId'])
        args = arguments(link['intent']['arguments'])
        require(dispatch['target'] == detail['target'] and dispatch['oldGeneration'] == args['expectedGeneration'] and
            dispatch['newGeneration'] == args['newGeneration'] and type(dispatch['dispatchRevision']) is int and
            dispatch['dispatchRevision'] == args['expectedRevision'],'LIFECYCLE_RECEIPT_IDENTITY')
        require(type(value['generationApplied']) is bool and value['safeIdle'] is True and
            type(value['beforeRevision']) is int and 1 <= value['beforeRevision'] < SAFE_INTEGER and
            type(value['afterRevision']) is int and value['afterRevision'] == value['beforeRevision'] + int(value['generationApplied']),
            'LIFECYCLE_RECEIPT_STATE')
        scope = generation_change_claims(self.installation['topology'],dispatch['target'])
        require(type(dispatch['affected']) is dict and set(dispatch['affected']) == {row['instanceId'] for row in scope['affectedConsumers']},
            'LIFECYCLE_RECEIPT_STATE')
        for previous in dispatch['affected'].values():
            exact(previous,{'binding','proof'})
        require(canonical(value['idleState']) == canonical({atom:self._idle[atom] for atom in scope['claims']}) and
            canonical(dispatch['scope']) == canonical(scope),'LIFECYCLE_RECEIPT_STATE')
        if value['generationApplied']:
            require(value['reason'] is None,'LIFECYCLE_RECEIPT_STATE')
        else:
            identifier(value['reason'])

    def acquire_lifecycle_receipt(self, operation_id):
        with self.lock:
            self._refresh_current(); self._validate_state()
            receipt = self.lifecycle_receipt(operation_id)
            if receipt is None:
                return None
            before,_ = self._read_snapshot(receipt['beforeRevision'])
            after,operation = self._read_snapshot(receipt['afterRevision'])
            target = receipt['dispatch']['target']
            require(before['nodes'][target] == receipt['dispatch']['oldGeneration'],'LIFECYCLE_RECEIPT_HISTORY')
            expected = snapshot(before)
            before_definitions = io_definitions(self.installation,generations=before)
            for instance, previous in receipt['dispatch']['affected'].items():
                require(canonical(previous) == canonical({'binding':before_definitions[instance]['binding'],
                    'proof':before_definitions[instance]['proof']}),'LIFECYCLE_RECEIPT_HISTORY')
            if receipt['generationApplied']:
                expected['revision'] += 1; expected['nodes'][target] = receipt['dispatch']['newGeneration']
                require(operation == operation_id,'LIFECYCLE_RECEIPT_HISTORY')
            require(canonical(expected) == canonical(after),'LIFECYCLE_RECEIPT_HISTORY')
            return receipt

    def advance_generation(self, operation, io_link, dispatch, *, guard):
        require(callable(guard),'IO_START_GUARD_REQUIRED')
        with self._transaction():
            self._refresh_current(); self._validate_state()
            old = self.lifecycle_receipt(operation['id'])
            if old is not None:
                require(canonical(old['ioLink']) == canonical(io_link) and canonical(old['dispatch']) == canonical(dispatch),
                    'LIFECYCLE_RECEIPT_CONFLICT')
                return old
            detail = self._validate_operation(operation,io_link['adapterId'])
            require(io_link['ownerEpoch'] == self.owner_epoch and io_link['clockEpoch'] == self.clock_epoch and
                io_link['operationId'] == operation['id'] and io_link['digest'] == operation['digest'] and
                canonical(io_link['intent']) == canonical(operation['intent']) and canonical(io_link['claims']) == canonical(operation['claims']),
                'LIFECYCLE_DISPATCH_CHANGED')
            require(operation['intent']['endpointSession'] == self.session,'IO_SESSION_CHANGED')
            current = self._current_generations; target = detail['target']
            require(current['revision'] < SAFE_INTEGER and current['nodes'][target] == dispatch['oldGeneration'],
                'RESOURCE_GENERATION_CONFLICT')
            require(self.db.execute('SELECT 1 FROM io_lc_tokens WHERE node=? AND generation=?',
                (target,dispatch['newGeneration'])).fetchone() is None,'RESOURCE_GENERATION_REUSED')
            for instance,previous in dispatch['affected'].items():
                require(canonical(self.current_definitions[instance]['binding']) == canonical(previous['binding']) and
                    canonical(self.current_definitions[instance]['proof']) == canonical(previous['proof']),'LIFECYCLE_PROVIDER_GENERATION_CHANGED')
            for claim in operation['claims']:
                require(self.db.execute('SELECT 1 FROM io_owners WHERE resource=?',(claim['resource'],)).fetchone() is None,'IO_RESOURCE_BUSY')
                floor = bounded_rows(self.db,'io_fences',('fence',),limit=1,keys={'resource':claim['resource']})
                require(not floor or claim['fence'] > floor[0]['fence'],'IO_STALE_FENCE')
            next_value = snapshot(current); next_value['revision'] += 1; next_value['nodes'][target] = dispatch['newGeneration']
            binding_rows = self._binding_rows(next_value)  # All expensive derivation before final veto.
            decision = guard()
            exact(decision,{'reason','nowMonoMs','budgetOriginMonoMs','clockEpoch'})
            reason = decision['reason']
            if reason is None:
                require(decision['clockEpoch'] == self.clock_epoch and all(type(decision[key]) is int and 0 <= decision[key] <= SAFE_INTEGER
                    for key in ('nowMonoMs','budgetOriginMonoMs')),'IO_START_CLOCK')
            else:
                identifier(reason)
            applied = reason is None
            receipt = {'profile':'hms.synthetic-lifecycle-receipt/1','operationId':operation['id'],'authorityId':self.authority_id,
                'boardId':self.installation['boardId'],'installationDigest':self.lifecycle_digest,'ioLink':snapshot(io_link),'dispatch':snapshot(dispatch),
                'generationApplied':applied,'safeIdle':True,'idleState':{atom:self._idle[atom] for atom in detail['claims']},
                'beforeRevision':current['revision'],'afterRevision':current['revision']+int(applied),'reason':reason}
            self.validate_lifecycle_receipt(receipt); encoded = canonical(receipt)  # Bounds before any effect write.
            if applied:
                final = guard()
                exact(final,{'reason','nowMonoMs','budgetOriginMonoMs','clockEpoch'})
                require(final['clockEpoch'] == self.clock_epoch and all(type(final[key]) is int and 0 <= final[key] <= SAFE_INTEGER
                    for key in ('nowMonoMs','budgetOriginMonoMs')),'IO_START_CLOCK')
                if final['reason'] is not None:
                    identifier(final['reason']); applied = False
                    receipt.update(generationApplied=False,afterRevision=current['revision'],reason=final['reason'])
                    self.validate_lifecycle_receipt(receipt); encoded = canonical(receipt)
            if applied:
                value = next_value
                self.db.execute('INSERT INTO io_lc_tokens VALUES(?,?,?)',(target,dispatch['newGeneration'],value['revision']))
                self._store_snapshot(value,operation['id'])
                self.db.executemany('INSERT INTO io_lc_bindings VALUES(?,?,?,?,?)',binding_rows)
                self.db.execute("UPDATE io_meta SET value=? WHERE key='lifecycleRevision'",(str(value['revision']),))
                for claim in operation['claims']:
                    self.db.execute('INSERT INTO io_fences VALUES(?,?,?) ON CONFLICT(resource) DO UPDATE SET fence=excluded.fence,operation=excluded.operation',
                        (claim['resource'],claim['fence'],operation['id']))
            self.db.execute('INSERT INTO io_lc_receipts VALUES(?,?,?)',(operation['id'],encoded,digest('HMS-LIFECYCLE-RECEIPT-v1',receipt)))
        with self.lock:
            self._refresh_current()
        return snapshot(receipt)
