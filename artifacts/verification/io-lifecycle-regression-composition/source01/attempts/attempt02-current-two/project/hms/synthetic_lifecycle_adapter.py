"""Installed receipt coordinator: no public claim exemption or administrator context."""
from .contracts import canonical
from .journal import Evidence, JournalError, Ticket
from .registry import exact
from .resource_topology import binding_proof, generation_change_claims
from .resource_catalog import control_generation
from .synthetic_io_adapter import IoRouteAdapter, link_digest
from .synthetic_io_installation import require
from .synthetic_io_storage import bounded_rows, document_row
from .synthetic_lifecycle_contracts import digest, snapshot


class LifecycleRouteAdapter(IoRouteAdapter):
    def validate_admission(self, intent, binding, resources):
        require(self.board.management_supports_binding(binding) and binding['adapterId'] == self.adapter_id,
            'LIFECYCLE_HANDLER_UNSUPPORTED')
        target,_args = self.runtime.catalog._target(intent,binding)
        require(tuple(resources) == tuple(generation_change_claims(self.board.installation['topology'],target)['claims']),
            'LIFECYCLE_CLAIM_CLOSURE')
        require(intent['endpointSession'] == self.board.session,'IO_SESSION_CHANGED')

    def refresh(self, *, force=False):
        with self.journal._mutex:
            mono = self.registry._monotonic()
            if not force and self._last_sample is not None and mono-self._last_sample < 200:
                return
            with self.board.lock:
                self.board._refresh_current(); self.board._validate_state()
            presences = []
            for instance in self.installation['instances']:
                binding,active = self.registry._binding(instance)
                if active and self.board.management_supports_binding(binding):
                    presences.append(dict(instance_id=instance,adapter_id=self.adapter_id,endpoint_session=self.board.session,ttl_ms=3000))
            self.registry.report_adapter_snapshot(self.adapter_id,presences=presences,streams=[],observations=[])
            self._last_sample = mono

    def _reserve(self, operation, ticket, checkpoint, budget_origin):
        super()._reserve(operation,ticket,checkpoint,budget_origin)
        row = document_row(self.journal._db,'io_dispatch_links',{'operation':operation['id']})
        self.runtime.catalog.reserve(operation,row['digest'])

    def _association(self, operation):
        link = self._link(operation)
        dispatch = self.runtime.catalog.dispatch(operation,link_digest(link))
        return link,dispatch

    def _guard(self, operation, link, checkpoint, *, start):
        current = self.journal._operation(operation['id'])
        refusal = None
        if (current['state'] != 'dispatching' or current['attempt_id'] != link['attemptId'] or
                current['owner_epoch'] != self.journal.owner_epoch):
            refusal = 'lifecycle_dispatch_authority_lost'
        elif current['cancel_state'] in {'requested','acknowledged','confirmed'}:
            refusal = 'client_cancel_before_generation'
        # The inherited final wall/monotonic veto follows every potentially
        # blocking operation lookup. Only a latched refusal is applied afterward.
        decision = super()._guard(current,link,checkpoint,start=start)
        if refusal is not None:
            decision['reason'] = refusal
        return decision

    def _receipt_evidence(self, receipt, assertion):
        return Evidence('simulation',self.adapter_id,
            'lifecycle-receipt:'+digest('HMS-LIFECYCLE-RECEIPT-v1',receipt)[7:],(assertion,))

    def validate_evidence(self, operation, evidence):
        """Authority-local, pure receipt/association validation; no board reads."""
        require(evidence.kind == 'simulation' and evidence.source == self.adapter_id and
            evidence.reference.startswith('lifecycle-receipt:'),'LIFECYCLE_EVIDENCE_IDENTITY')
        row = document_row(self.journal._db,'lc_receipts',{'operation':operation['id']})
        require(row is not None,'LIFECYCLE_RECEIPT_MISSING')
        receipt = snapshot(bytes(row['document']))
        self.board.validate_lifecycle_receipt(receipt)
        expected = digest('HMS-LIFECYCLE-RECEIPT-v1',receipt)
        require(row['digest'] == expected and evidence.reference == 'lifecycle-receipt:'+expected[7:] and
            canonical(receipt) == bytes(row['document']),'LIFECYCLE_RECEIPT_CHANGED')
        link,dispatch = self._association(operation)
        require(canonical(receipt['ioLink']) == canonical(link) and canonical(receipt['dispatch']) == canonical(dispatch),
            'LIFECYCLE_RECEIPT_CONFLICT')
        allowed = {'resources_quiescent','completed' if receipt['generationApplied'] else 'start_excluded'}
        require(bool(evidence.assertions) and set(evidence.assertions) <= allowed,'LIFECYCLE_EVIDENCE_STATE')

    def _owned_claims(self, operation, link, dispatch):
        claims = operation['claims']
        require(canonical(claims) == canonical(link['claims']) and [row['resource'] for row in claims] == dispatch['scope']['claims'],
            'LIFECYCLE_CLAIM_OWNERSHIP')
        db = self.journal._db
        for claim in claims:
            rows = bounded_rows(db,'claims',('operation_id','fence'),limit=1,
                keys={'deployment':operation['deployment'],'resource':claim['resource']})
            require(len(rows) == 1 and rows[0]['operation_id'] == operation['id'] and
                type(rows[0]['fence']) is int and rows[0]['fence'] == claim['fence'],'LIFECYCLE_CLAIM_OWNERSHIP')
            floors = bounded_rows(db,'resource_floors',('fence',),limit=1,
                keys={'deployment':operation['deployment'],'resource':claim['resource']})
            require(len(floors) == 1 and type(floors[0]['fence']) is int and floors[0]['fence'] == claim['fence'],
                'LIFECYCLE_CLAIM_OWNERSHIP')
        # This is not an own-operation-ID exemption. Management is a distinct
        # installed instance, and original Registry guards still check each
        # affected consumer instance when its binding is published.
        require(operation['intent']['instanceId'] not in dispatch['affected'],'LIFECYCLE_MANAGEMENT_SEPARATION')

    def _publication(self, operation):
        row = document_row(self.journal._db,'lc_publications',{'operation':operation['id']})
        if row is None:
            return None
        value = snapshot(bytes(row['document']))
        exact(value,{'profile','operationId','digest','dispatchDigest','receiptDigest','terminalState',
            'executionSequence','releaseSequence','publication'})
        require(value['profile'] == 'hms.synthetic-lifecycle-settlement/1' and value['operationId'] == operation['id'] and
            value['digest'] == operation['digest'] and canonical(value) == bytes(row['document']) and
            row['digest'] == digest('HMS-LIFECYCLE-SETTLEMENT-v1',value),'LIFECYCLE_SETTLEMENT_CHANGED')
        require(operation['state'] == value['terminalState'] and operation['state'] in {'completed','rejected_before_start'} and
            not operation['claims'] and type(value['executionSequence']) is int and type(value['releaseSequence']) is int and
            0 < value['executionSequence'] < value['releaseSequence'] <= operation['sequence'],'LIFECYCLE_SETTLEMENT_CHANGED')
        link,dispatch = self._association(operation)
        retained = document_row(self.journal._db,'lc_receipts',{'operation':operation['id']})
        require(retained is not None,'LIFECYCLE_RECEIPT_MISSING')
        receipt = snapshot(bytes(retained['document'])); self.board.validate_lifecycle_receipt(receipt)
        require(retained['digest'] == value['receiptDigest'] == digest('HMS-LIFECYCLE-RECEIPT-v1',receipt) and
            value['dispatchDigest'] == digest('HMS-LIFECYCLE-DISPATCH-v1',dispatch) and
            canonical(receipt['ioLink']) == canonical(link) and canonical(receipt['dispatch']) == canonical(dispatch),
            'LIFECYCLE_SETTLEMENT_CHANGED')
        for sequence,kind in ((value['executionSequence'],None),(value['releaseSequence'],'resources_released')):
            events = bounded_rows(self.journal._db,'events',('kind','payload'),limit=1,
                keys={'operation_id':operation['id'],'sequence':sequence},blobs=('payload',))
            require(len(events) == 1 and (events[0]['kind'] in {'execution_evidence','reconciled'} if kind is None else events[0]['kind'] == kind),
                'LIFECYCLE_SETTLEMENT_CHANGED')
            event = snapshot(bytes(events[0]['payload']))
            exact(event, {'state','evidence'} if kind is None else {'evidence'})
            expected_assertion = ('completed' if receipt['generationApplied'] else 'start_excluded') if kind is None else 'resources_quiescent'
            require(canonical(event['evidence']) == canonical(self._receipt_evidence(receipt,expected_assertion).payload()) and
                (kind is not None or event['state'] == value['terminalState']),'LIFECYCLE_SETTLEMENT_CHANGED')
        publication = value['publication']
        require((publication is not None) == receipt['generationApplied'],'LIFECYCLE_SETTLEMENT_CHANGED')
        if publication is not None:
            exact(publication,{'dispatchRevision','baseRevision','revision','target','generation','bindings'})
            require(type(publication['dispatchRevision']) is int and publication['dispatchRevision'] == dispatch['dispatchRevision'] and publication['target'] == dispatch['target'] and
                publication['generation'] == dispatch['newGeneration'] and type(publication['baseRevision']) is int and
                type(publication['revision']) is int and publication['revision'] == publication['baseRevision']+1 and
                publication['baseRevision'] >= publication['dispatchRevision'],'LIFECYCLE_SETTLEMENT_CHANGED')
            saved = self.runtime.catalog.resources._load()
            before = self.runtime.catalog.resources._generation_row(saved['topology'],publication['baseRevision'])
            after = self.runtime.catalog.resources._generation_row(saved['topology'],publication['revision'])
            expected = snapshot(before); expected['revision'] += 1; expected['nodes'][dispatch['target']] = dispatch['newGeneration']
            require(before['nodes'][dispatch['target']] == dispatch['oldGeneration'] and canonical(expected) == canonical(after) and
                type(publication['bindings']) is dict and set(publication['bindings']) == set(dispatch['affected']),'LIFECYCLE_SETTLEMENT_CHANGED')
            for instance, record in publication['bindings'].items():
                exact(record,{'generation','proofDigest'})
                proof,binding = self.runtime.catalog.resources._retained_proof(saved,instance,record['generation'])
                expected_proof = binding_proof(saved['topology'],after,instance)
                expected_binding = dispatch['affected'][instance]['binding'] | {
                    'generation':expected_proof['bindingGeneration'],'controlGeneration':control_generation(expected_proof)}
                require(record['generation'] == expected_proof['bindingGeneration'] and canonical(proof) == canonical(expected_proof) and
                    canonical(binding) == canonical(expected_binding) and
                    record['proofDigest'] == digest('HMS-LIFECYCLE-PUBLISHED-PROOF-v1',proof),'LIFECYCLE_SETTLEMENT_CHANGED')
        return value

    def settle(self, operation_id):
        """Internal id-only lookup; all authority comes from retained exact proof."""
        with self.journal._mutex:
            operation = self.journal._operation(operation_id)
            previous = self._publication(operation)
            if previous is not None:
                return previous  # Historical result, not present idle/permission.
            link,dispatch = self._association(operation)
            require(operation['state'] in {'dispatching','running','outcome_unknown'},'LIFECYCLE_SETTLEMENT_STATE')
            with self.board.lock:
                receipt = self.board.acquire_lifecycle_receipt(operation_id)
                if receipt is None:
                    return None  # Unknown is retained; never reexecute on reopen.
                require(canonical(receipt['ioLink']) == canonical(link) and canonical(receipt['dispatch']) == canonical(dispatch),
                    'LIFECYCLE_RECEIPT_CONFLICT')
                for claim in link['claims']:
                    require(self.board.db.execute('SELECT 1 FROM io_owners WHERE resource=?',(claim['resource'],)).fetchone() is None,
                        'IO_QUIESCENCE_UNKNOWN')
                    if receipt['generationApplied']:
                        floors = bounded_rows(self.board.db,'io_fences',('fence','operation'),limit=1,keys={'resource':claim['resource']})
                        require(len(floors) == 1 and floors[0]['fence'] == claim['fence'] and floors[0]['operation'] == operation_id,
                            'LIFECYCLE_PROVIDER_FENCE_CHANGED')
                if receipt['generationApplied']:
                    require(self.board._current_generations['nodes'][dispatch['target']] == dispatch['newGeneration'],
                        'LIFECYCLE_PROVIDER_GENERATION_CHANGED')
                with self.journal._transaction():
                    operation = self.journal._operation(operation_id)
                    self._owned_claims(operation,link,dispatch)
                    if operation['state'] != 'outcome_unknown':
                        self.journal._ticket(Ticket(operation_id,link['attemptId'],self.journal.owner_epoch))
                    plan = self.runtime.catalog.prepare_publication(operation,dispatch) if receipt['generationApplied'] else None
                    now = self.journal._record_now()  # Record truth; never a new effect permission.
                    encoded = canonical(receipt); receipt_digest = digest('HMS-LIFECYCLE-RECEIPT-v1',receipt)
                    old = document_row(self.journal._db,'lc_receipts',{'operation':operation_id})
                    require(old is None or (bytes(old['document']) == encoded and old['digest'] == receipt_digest),'LIFECYCLE_RECEIPT_CONFLICT')
                    if old is None:
                        self.journal._db.execute('INSERT INTO lc_receipts VALUES(?,?,?)',(operation_id,encoded,receipt_digest))
                    publication = self.runtime.catalog.apply_publication(plan,dispatch) if plan is not None else None
                    state,assertion = ('completed','completed') if receipt['generationApplied'] else ('rejected_before_start','start_excluded')
                    self.journal._execution(operation,state,self._receipt_evidence(receipt,assertion),now)
                    execution_sequence = self.journal._operation(operation_id)['sequence']
                    self.journal._release_resources_in_tx(operation_id,self._receipt_evidence(receipt,'resources_quiescent'))
                    value = {'profile':'hms.synthetic-lifecycle-settlement/1','operationId':operation_id,'digest':operation['digest'],
                        'dispatchDigest':digest('HMS-LIFECYCLE-DISPATCH-v1',dispatch),'receiptDigest':receipt_digest,'terminalState':state,
                        'executionSequence':execution_sequence,'releaseSequence':self.journal._operation(operation_id)['sequence'],
                        'publication':publication}
                    self.journal._db.execute('INSERT INTO lc_publications VALUES(?,?,?)',
                        (operation_id,canonical(value),digest('HMS-LIFECYCLE-SETTLEMENT-v1',value)))
                return snapshot(value)

    def tick(self):
        with self._tick_lock:
            refresh_error = None
            try:
                self.refresh()
            except JournalError as error:
                refresh_error = error
            for operation in self.runtime.work_items(self.adapter_id,('outcome_unknown',)):
                self.settle(operation['id'])
            self.runtime.expire_unstarted(self.adapter_id)
            for operation in self.runtime.work_items(self.adapter_id,('accepted',),skip_paused=True):
                with self.journal._mutex:
                    try:
                        origin = self.registry._monotonic()
                        ticket = self.journal.claim_dispatch(operation['id'],_reserve=lambda op,ticket,now:self._reserve(op,ticket,now,origin))
                    except JournalError as error:
                        if error.code in {'NOT_YET_STARTABLE','NOT_DISPATCHABLE','PROCEDURE_PAUSED'}:
                            continue
                        self.journal.reject_before_dispatch(operation['id'],error.code); continue
                    if ticket is None:
                        continue
                    operation = self.journal._operation(operation['id']); link,dispatch = self._association(operation)
                    try:
                        self.board.advance_generation(operation,link,dispatch,
                            guard=lambda:self._guard(operation,link,link['checkpoint'],start=True))
                        self.settle(operation['id'])
                    except Exception:
                        if self.journal._operation(operation['id'])['state'] in {'dispatching','running'}:
                            self.journal.mark_unknown(ticket,'lifecycle_effect_or_settlement_unknown')
                        raise
            if refresh_error is not None:
                raise refresh_error

    def result(self, operation_id):
        with self.journal._mutex:
            operation = self.journal._operation(operation_id)
            settled = self._publication(operation)
            if settled is None or settled['terminalState'] != 'completed':
                return None
            # This explicit output profile is not mounted in the current public
            # API validator; it must never fall through legacy effectCommitted.
            return {'evidenceKind':'simulation','output':{'profile':'hms.synthetic-lifecycle-result/1','primitive':'advance_generation',
                'receiptDigest':settled['receiptDigest'],'publication':settled['publication']}}
