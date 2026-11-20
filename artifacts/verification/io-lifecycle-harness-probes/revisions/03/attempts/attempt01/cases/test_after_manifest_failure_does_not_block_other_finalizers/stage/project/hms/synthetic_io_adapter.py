"""Original finite I/O route: exact durable receipts before Journal release."""
import copy
import hashlib
import threading
import uuid

from .contracts import SAFE_INTEGER, ContractError, canonical, identifier, parse_json
from .journal import Context, Evidence, JournalError, TERMINAL
from .registry import RegistryPolicy, exact
from .synthetic_io_board import receipt_digest
from .synthetic_io_installation import require
from .synthetic_io_storage import bounded_rows, document_row


def link_digest(value):
    return 'sha256:' + hashlib.sha256(b'HMS-SYNTHETIC-IO-DISPATCH-v1\0' + canonical(value)).hexdigest()


class IoRegistryPolicy(RegistryPolicy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.io_backends = {}

    def evidence(self, operation, evidence):
        super().evidence(operation,evidence)
        backend = self.io_backends.get(evidence.source)
        require(backend is not None, 'IO_EVIDENCE_ROUTE_UNINSTALLED')
        # Only authority-local SQL plus pure validation. Provider I/O occurred
        # before the adapter retained this exact immutable receipt version.
        backend.validate_evidence(operation,evidence)


class IoRouteAdapter:
    def __init__(self, runtime, installation, board):
        self.runtime, self.installation, self.board = runtime,copy.deepcopy(installation),board
        self.journal,self.registry,self.policy = runtime.journal,runtime.registry,runtime.policy
        self.adapter_id = installation['adapterId']
        require(self.installation in runtime.catalog.installations and board.installation_digest == installation['installationDigest'],
                'IO_ROUTE_INSTALLATION_CHANGED')
        self._streams = {}; self._last_sample = None; self._pending = {}; self._tick_lock = threading.Lock()

    def close(self):
        # Shared board lifetime belongs to IoRuntime, not an individual route.
        pass

    def validate_admission(self, intent, binding, resources):
        self.board.validate_admission(self.adapter_id,intent,binding,resources)

    def refresh(self, *, force=False):
        with self.journal._mutex:
            mono = self.registry._monotonic()
            if not force and self._last_sample is not None and mono-self._last_sample < 200:
                return
            streams = copy.deepcopy(self._streams)
            presences,starts,observations = [],[],[]
            for instance in self.installation['instances']:
                binding,active = self.registry._binding(instance)
                if not active or not self.board.supports_binding(binding):
                    continue
                acquired = self.registry._monotonic()
                sample = self.board.observe(instance)
                presences.append(dict(instance_id=instance,adapter_id=self.adapter_id,endpoint_session=self.board.session,ttl_ms=3000))
                for property_id in ('value','ready'):
                    key = (instance,property_id,binding['generation'],self.board.session)
                    if key not in streams:
                        epoch = 'io-stream:' + uuid.uuid4().hex
                        streams[key] = [epoch,0]
                        starts.append(dict(instance_id=instance,property_id=property_id,adapter_id=self.adapter_id,
                            endpoint_session=self.board.session,binding_generation=binding['generation'],stream_epoch=epoch))
                    stream = streams[key]; stream[1] += 1
                    observations.append(dict(instance_id=instance,property_id=property_id,adapter_id=self.adapter_id,
                        endpoint_session=self.board.session,binding_generation=binding['generation'],value=sample[property_id],
                        evidence_kind='simulation',quality='valid',stream_epoch=stream[0],sequence=stream[1],
                        acquisition={'clockDomain':'synthetic-io-monotonic','clockEpoch':self.registry.receipt_epoch,'ticksMs':acquired},
                        acquisition_latency_bound_ms=None,acquisition_host_earliest_ms=acquired,clock_uncertainty_ms=0,
                        measurement_uncertainty={'absolute':0,'unit':'1','method':'synthetic_exact_counter'}))
            self.registry.report_adapter_snapshot(self.adapter_id,presences=presences,streams=starts,observations=observations)
            self._streams,self._last_sample = streams,mono

    def _reserve(self, operation, ticket, checkpoint, budget_origin):
        require(self.journal._db.in_transaction, 'IO_RESERVATION_TRANSACTION_REQUIRED')
        value = {'profile':'hms.synthetic-io-dispatch/1','operationId':operation['id'],'digest':operation['digest'],
            'intent':operation['intent'],'claims':operation['claims'],'adapterId':self.adapter_id,
            'authorityId':self.journal.authority_id,'attemptId':ticket.attempt_id,'ownerEpoch':ticket.owner_epoch,
            'checkpoint':checkpoint,'budgetOriginMonoMs':budget_origin,'clockEpoch':self.registry.receipt_epoch,
            'installationDigest':self.board.installation_digest}
        self.journal._db.execute('INSERT INTO io_dispatch_links VALUES (?,?,?)',(operation['id'],canonical(value),link_digest(value)))

    def _link(self, operation):
        row = document_row(self.journal._db,'io_dispatch_links',{'operation':operation['id']})
        require(row is not None, 'IO_DISPATCH_LINK_MISSING')
        value = parse_json(bytes(row['document']))
        exact(value, {'profile','operationId','digest','intent','claims','adapterId','authorityId','attemptId','ownerEpoch',
                      'checkpoint','budgetOriginMonoMs','clockEpoch','installationDigest'})
        require(value['profile'] == 'hms.synthetic-io-dispatch/1', 'IO_DISPATCH_LINK_PROFILE')
        for field in ('operationId','adapterId','authorityId','attemptId','clockEpoch'):
            identifier(value[field])
        require(all(type(value[key]) is int and 0 <= value[key] <= SAFE_INTEGER for key in ('ownerEpoch','checkpoint','budgetOriginMonoMs')) and
                1 <= value['ownerEpoch'] <= self.journal.owner_epoch and
                value['clockEpoch'] == self.journal.authority_id+':'+str(value['ownerEpoch']) and
                value['attemptId'] == operation['attempt_id'], 'IO_DISPATCH_ATTEMPT_CHANGED')
        claimed = bounded_rows(self.journal._db,'events',('payload','time_ms'),limit=1,
            keys={'operation_id':operation['id'],'kind':'dispatch_claimed'},blobs=('payload',))
        require(len(claimed) == 1 and type(claimed[0]['time_ms']) is int and claimed[0]['time_ms'] == value['checkpoint'],
                'IO_DISPATCH_EVENT_CHANGED')
        event = parse_json(bytes(claimed[0]['payload'])); exact(event,{'attemptId','ownerEpoch'})
        require(type(event['ownerEpoch']) is int and event['ownerEpoch'] == value['ownerEpoch'] and
                event['attemptId'] == value['attemptId'], 'IO_DISPATCH_EVENT_CHANGED')
        require(canonical(value) == bytes(row['document']) and link_digest(value) == row['digest'] and
                value['operationId'] == operation['id'] and value['digest'] == operation['digest'] and
                canonical(value['intent']) == canonical(operation['intent']) and value['adapterId'] == self.adapter_id and
                value['authorityId'] == self.journal.authority_id and value['installationDigest'] == self.board.installation_digest,
                'IO_DISPATCH_LINK_CHANGED')
        self.board._validate_operation({'id':operation['id'],'digest':operation['digest'],'intent':value['intent'],'claims':value['claims']},self.adapter_id)
        require([claim['resource'] for claim in value['claims']] == operation['admission']['resources'], 'IO_DISPATCH_CLAIMS_CHANGED')
        if operation['claims']:
            require(canonical(value['claims']) == canonical(operation['claims']), 'IO_AUTHORITY_CLAIMS_CHANGED')
        return value

    def _check_receipt(self, operation, receipt):
        self.board._validate_receipt(receipt)  # Pure: no provider SQL or state transition.
        link = self._link(operation)
        require(receipt['operationId'] == operation['id'] and receipt['digest'] == operation['digest'] and
                canonical(receipt['intent']) == canonical(link['intent']) and canonical(receipt['claims']) == canonical(link['claims']) and
                receipt['adapterId'] == self.adapter_id and receipt['ownerEpoch'] == link['ownerEpoch'] and
                receipt['clockEpoch'] == link['clockEpoch'], 'IO_RECEIPT_LINK_CONFLICT')
        if receipt['state'] != 'rejected_before_start':
            require(receipt['budgetOriginMonoMs'] == link['budgetOriginMonoMs'], 'IO_RECEIPT_LINK_CONFLICT')

    def _retain_receipt(self, operation, receipt):
        self._check_receipt(operation,receipt)
        data,digest = canonical(receipt),receipt_digest(receipt)
        with self.journal._transaction():
            old = document_row(self.journal._db,'io_authority_receipts',{'operation':operation['id'],'sequence':receipt['sequence']})
            if old is not None:
                require(bytes(old['document']) == data and old['digest'] == digest, 'IO_RETAINED_RECEIPT_CONFLICT')
            else:
                self.journal._db.execute('INSERT INTO io_authority_receipts VALUES (?,?,?,?)',
                    (operation['id'],receipt['sequence'],data,digest))

    def _evidence(self, receipt, assertion):
        return Evidence('simulation',self.adapter_id,'io-receipt:' + receipt_digest(receipt).removeprefix('sha256:'),(assertion,))

    def validate_evidence(self, operation, evidence):
        require(evidence.kind == 'simulation' and evidence.source == self.adapter_id and evidence.reference.startswith('io-receipt:'),
                'IO_EVIDENCE_IDENTITY')
        wanted = 'sha256:' + evidence.reference.removeprefix('io-receipt:')
        rows = bounded_rows(self.journal._db,'io_authority_receipts',('document','digest','sequence'),limit=2,
            keys={'operation':operation['id']},blobs=('document',))
        require(all(type(row['sequence']) is int and row['sequence'] in {1,2} for row in rows), 'IO_RETAINED_RECEIPT_SEQUENCE')
        matches = [row for row in rows if row['digest'] == wanted]
        require(len(matches) == 1, 'IO_RETAINED_RECEIPT_MISSING')
        receipt = parse_json(bytes(matches[0]['document']))
        require(receipt['sequence'] == matches[0]['sequence'], 'IO_RETAINED_RECEIPT_SEQUENCE')
        require(canonical(receipt) == bytes(matches[0]['document']) and receipt_digest(receipt) == wanted, 'IO_RETAINED_RECEIPT_CHANGED')
        self._check_receipt(operation,receipt)
        state = receipt['state']; allowed = set()
        if state == 'pending':
            allowed = {'running','cancel_ack'}
        elif state == 'rejected_before_start':
            allowed = {'start_excluded','resources_quiescent'}
        elif state == 'completed':
            allowed = {'completed','resources_quiescent'}
        elif state == 'canceled':
            allowed = {'resources_quiescent','terminated' if receipt['result']['reason'] in {'client_cancel','board_owner_reopened'} else 'failed'}
        require(set(evidence.assertions) <= allowed and bool(evidence.assertions), 'IO_EVIDENCE_ASSERTION')

    def _timing(self, operation, link, checkpoint, *, start):
        now = self.journal.effect_veto_time(checkpoint)
        mono = self.registry._monotonic()
        timing = operation['intent']['timing']
        reason = None
        if now < timing['notBeforeUnixMs']:
            reason = 'start_not_yet_authorized'
        elif start and now >= timing['latestStartUnixMs']:
            reason = 'start_deadline'
        elif now >= timing['latestCompletionUnixMs'] or mono-link['budgetOriginMonoMs'] >= timing['maxRunMs']:
            reason = 'execution_deadline'
        elif now >= operation['admission']['lease_expires_ms']:
            reason = 'lease_expired'
        return now,mono,reason

    def _guard(self, operation, link, checkpoint, *, start):
        result = {'reason':None,'nowMonoMs':None,'clockEpoch':self.registry.receipt_epoch}
        if start:
            result['budgetOriginMonoMs'] = link['budgetOriginMonoMs']
        try:
            now,mono,reason = self._timing(operation,link,checkpoint,start=start)
            if reason is None:
                context = Context(operation['principal'],operation['deployment'])
                self.policy.authorize(context,'invoke',operation['intent']['instanceId'])
                self.policy.recheck(context,operation,now)
                # Complete topology/proof validation can consume the budget.
                now,mono,reason = self._timing(operation,link,checkpoint,start=start)
            result.update(reason=reason,nowMonoMs=mono)
        except JournalError as error:
            result['reason'] = 'clock_authority_lost' if error.code in {'CLOCK_REGRESSION','CLOCK_MAPPING_INVALID','INVALID_CLOCK'} else 'authority_or_binding_lost'
        return result

    def _settle(self, operation, receipt, ticket=None):
        if receipt is None:
            return
        validated = self.board.validated_receipt(operation['id'],sequence=receipt['sequence'])
        require(validated is not None and canonical(validated) == canonical(receipt), 'IO_RECEIPT_SNAPSHOT_CHANGED')
        self._retain_receipt(operation,receipt)
        if receipt['state'] == 'pending':
            return
        if receipt['state'] == 'rejected_before_start':
            state,assertion = 'rejected_before_start','start_excluded'
        elif receipt['state'] == 'completed':
            state,assertion = 'completed','completed'
        elif receipt['result']['reason'] in {'client_cancel','board_owner_reopened'}:
            state,assertion = 'canceled','terminated'
        else:
            state,assertion = 'failed','failed'
        if operation['state'] == 'outcome_unknown':
            self.journal.reconcile(operation['id'],state,self._evidence(receipt,assertion))
        elif operation['state'] not in TERMINAL:
            require(ticket is not None,'IO_DISPATCH_TICKET_MISSING')
            self.journal.record_execution(ticket,state,self._evidence(receipt,assertion))
        current = self.journal._operation(operation['id'])
        if current['claims']:
            require(receipt['result']['safeIdle'] is True, 'IO_QUIESCENCE_UNKNOWN')
            self.journal.release_resources(operation['id'],self._evidence(receipt,'resources_quiescent'))

    def tick(self):
        with self._tick_lock:
            refresh_error = None
            try:
                self.refresh()
            except (JournalError,ContractError) as error:
                refresh_error = error
            for operation in self.runtime.work_items(self.adapter_id,('outcome_unknown',)):
                with self.journal._mutex:
                    receipt = self.board.receipt(operation['id'])
                    if receipt is not None and receipt['state'] == 'pending':
                        self._check_receipt(operation,receipt)
                        # An exact durable pending receipt can justify a stop
                        # in this atomic model, never an implicit continuation.
                        receipt = self.board.finish(operation['id'],guard=None,cancel_reason='reconciliation_stop')
                    self._settle(operation,receipt)
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
                    operation = self.journal._operation(operation['id']); link = self._link(operation)
                    try:
                        receipt = self.board.begin(operation,self.adapter_id,
                            guard=lambda:self._guard(operation,link,link['checkpoint'],start=True))
                        self._retain_receipt(operation,receipt)
                    except Exception:
                        self.journal.mark_unknown(ticket,'io_acceptance_unknown'); continue
                    if receipt['state'] != 'pending':
                        self._settle(operation,receipt,ticket); continue
                    self._pending[operation['id']] = ticket
                    self.journal.record_execution(ticket,'running',self._evidence(receipt,'running'))
            for operation_id,ticket in list(self._pending.items())[:64]:
                with self.journal._mutex:
                    operation = self.journal._operation(operation_id)
                    try:
                        link = self._link(operation)
                        if operation['cancel_state'] == 'requested':
                            receipt = self.board.finish(operation_id,guard=None,cancel_reason='client_cancel')
                        elif refresh_error is not None:
                            receipt = self.board.finish(operation_id,guard=None,cancel_reason='observation_authority_lost')
                        else:
                            try:
                                checkpoint = self.journal.authority_time()
                            except JournalError:
                                receipt = self.board.finish(operation_id,guard=None,cancel_reason='clock_authority_lost')
                            else:
                                receipt = self.board.finish(operation_id,
                                    guard=lambda _receipt:self._guard(operation,link,checkpoint,start=False))
                        self._settle(operation,receipt,ticket)
                    except Exception:
                        current = self.journal._operation(operation_id)
                        if current['state'] in {'dispatching','running'}:
                            self.journal.mark_unknown(ticket,'io_completion_unknown')
                        self._pending.pop(operation_id,None)
                        raise
                    if receipt['state'] != 'pending':
                        self._pending.pop(operation_id,None)
            for operation in self.runtime.work_items(self.adapter_id,('completed','failed','canceled'),claims_only=True):
                with self.journal._mutex:
                    self._settle(operation,self.board.receipt(operation['id']))
            if refresh_error is not None:
                raise refresh_error

    def result(self, operation_id):
        with self.journal._mutex:
            operation = self.journal._operation(operation_id)
            receipt = self.board.validated_receipt(operation_id)
            if receipt is None:
                return None
            self._check_receipt(operation,receipt)
            if receipt['state'] in {'pending','rejected_before_start'}:
                return None
            return {'evidenceKind':'simulation','output':{'profile':'hms.synthetic-io-result/1',
                'primitive':self.board._details[(operation['intent']['instanceId'],operation['intent']['actionId'])]['primitive'],
                'result':receipt['result'],'safeIdleState':receipt['idleState'],'receiptDigest':receipt_digest(receipt)}}
