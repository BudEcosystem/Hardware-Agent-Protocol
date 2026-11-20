"""Explicit host lifecycle over the actual version-2 native standing endpoint.

No launches, automatic reconnect work, prompt evaluator, physical transport or
background renewal. A trusted launcher owns the fixed native executable and the
connected stream. Application methods accept identities and typed intent only.
All effect outboxes commit before one handoff attempt. Failure never retries.
"""
from contextlib import contextmanager, ExitStack
import copy
import fcntl
import os
import stat
from pathlib import Path
import threading
import time

from .contracts import canonical, identifier as validate_identifier
from .journal import JournalError
from .endpoint_transport import LocalEndpointStream
from . import standing_contracts as c
from . import standing_wire as w
from .standing_pat import SOURCE_PINS
from protocol.serial.frame import Frame


class InstalledNativeDriver:
    """Trusted installation/launcher contract, not executable selection by API.

    The original launcher pins and starts this exact finite native pipe image.
    Hashes bind the held installation; they do not attest an arbitrary peer or
    contain hostile same-user writers. The fixed native fixture remains test-only.
    """
    def __init__(self, image, installation):
        self.path = Path(image).resolve(strict=True)
        self.installation = c.parse_installation(installation)
        self.expected = self.installation['driverImageDigest']
        self.source_pins = dict(SOURCE_PINS)
        self.source_pins['tests/standing_host_pipe.c'] = c.sha(c.bounded_file(c.ROOT/'tests/standing_host_pipe.c',1024*1024))
        c.require(c.identity('HMS-STANDING-PIPE-SOURCES-v0.1',self.source_pins)==
                  self.installation['driverSourceDigest'],'DRIVER_SOURCE_CHANGED')
        self.original_path = str(self.path)
        self._lease = None
        self.enabled = True

    @contextmanager
    def hold(self):
        c.require(self._lease is None and self.enabled,'DRIVER_UNAVAILABLE')
        with ExitStack() as stack:
            retained=[]
            for path,expected,maximum in [(self.path,self.expected,2*1024*1024)]+[
                    (c.ROOT/name,pin,1024*1024) for name,pin in sorted(self.source_pins.items())]:
                stream=stack.enter_context(os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb'))
                fcntl.flock(stream.fileno(),fcntl.LOCK_SH|fcntl.LOCK_NB)
                before=os.fstat(stream.fileno())
                c.require(stat.S_ISREG(before.st_mode) and before.st_size<=maximum,'DRIVER_IMAGE_LIMIT')
                body=stream.read(maximum+1);after=os.fstat(stream.fileno())
                signature=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
                c.require(len(body)==before.st_size and signature(before)==signature(after) and
                          c.sha(body)==expected,'DRIVER_IMAGE_CHANGED')
                retained.append(body)
            c.require(sum(map(len,retained))<=8*1024*1024,'DRIVER_SNAPSHOT_LIMIT')
            self._lease = (threading.get_ident(),time.monotonic_ns()+2_000_000_000,tuple(retained))
            try:
                yield self.check
            finally:
                self._lease = None

    def check(self):
        c.require(self.enabled and self._lease is not None and self._lease[0]==threading.get_ident() and
                  time.monotonic_ns()<self._lease[1] and str(self.path)==self.original_path,'DRIVER_LEASE_UNAVAILABLE')


class StandingHost:
    def __init__(self, store, stream, driver):
        c.require(type(stream) is LocalEndpointStream and type(driver) is InstalledNativeDriver,'INSTALLED_ROUTE_REQUIRED')
        self.store, self.stream, self.driver = store, stream, driver
        self.journal, self.policy, self.catalog = store.journal, store.policy, store.catalog
        with self.journal._mutex:
            if not hasattr(self.journal,'_standing_route_lock'):
                self.journal._standing_route_lock=threading.RLock()
            self._route_lock=self.journal._standing_route_lock
        c.require(canonical(driver.installation)==canonical(store.installation),'INSTALLATION_CHANGED')

    def _checkpoint(self, phase, value=None):
        pass

    @contextmanager
    def _images(self):
        with self.policy.hold_image():
            with self.driver.hold():
                yield

    def _check_images(self):
        self.policy.check_image();self.driver.check()

    def _response_owner(self,request):
        with self.journal._mutex:
            rows=self.journal._db.execute('SELECT id FROM sd_deployments ORDER BY id LIMIT 17').fetchall()
            c.require(len(rows)<=16,'CAPACITY')
            live=[self.store.row(row[0]) for row in rows if not self.store.row(row[0])['retired']]
            c.require(len(live)<=1,'ENDPOINT_SLOT_BUSY')
            if not live:
                return None
            row=live[0]
            c.require(request.reference is None or request.reference==self.store.reference(row),'TRANSPORT_ASSOCIATION')
            return row['id']

    def _exchange(self, request):
        c.require(not self.journal._db.in_transaction,'TRANSPORT_IN_TRANSACTION')
        owner=self._response_owner(request)
        self._checkpoint('before_exchange',request)
        def receive(frame):
            try:
                self.store.receive(frame)
            except JournalError as error:
                if owner is not None and error.code in {'STANDING_FRAME','STANDING_BOOT_OR_RESPONSE_REPLAY'}:
                    self.store.record_transport_conflict(owner,request,frame)
                raise
        frame=self.stream.exchange(request,receive)
        try:
            response=w.decode_response(frame,request)
        except w.WireError as error:
            if owner is not None:
                self.store.record_transport_conflict(owner,request,frame)
            raise JournalError('STANDING_EVIDENCE_CONFLICT') from error
        self._checkpoint('after_exchange',response)
        return response

    def _query(self,payload):
        with self.journal._transaction():
            request=self.store.reserve_frame(payload)
        return request,self._exchange(request)

    def _descriptor(self):
        identity_request,identity=self._query(w.describe(0))
        c.require(identity['status']==0 and 'identity' in identity,'DESCRIPTOR_REQUIRED')
        expected=self.store.installation['endpoint'];actual=identity['identity']
        c.require(identity['session']==expected['boot'] and actual['incarnation'].hex()==expected['incarnationHex'] and
            actual['firmware_digest'].hex()==expected['firmwareHex'] and
            actual['manifest_digest'].hex()==expected['manifestHex'],'ENDPOINT_IDENTITY_CHANGED')
        request,response=self._query(w.describe(1))
        c.require(response['status']==0 and 'capabilities' in response,'DESCRIPTOR_REQUIRED')
        caps=response['capabilities']
        c.require(caps['resource_count']==2 and caps['installed_mask']==3 and caps['kernel_id']==1 and
            caps['epochs']==tuple(expected['epochs']) and caps['maximum_on_ms']==500 and
            caps['maximum_lease']>=1000 and caps['cleanup_budget']==100 and
            caps['platform_flags']&31==25,'ENDPOINT_PROFILE_UNQUALIFIED')
        return request,response

    def initialize(self,context):
        """Explicit first BIND only. An ambiguous original BIND is never resent."""
        with self._route_lock:
            self.policy.authorize(context,'admin','*')
            route=self.store.route()
            if route['generation']:
                return copy.deepcopy(route)
            with self._images():
                _,response=self._descriptor();caps=response['capabilities']
                c.require(route['bind'] is None and caps['slot_kind']==0 and caps['handle']==0 and
                    caps['generation']==1 and caps['standing_high_water']==0 and caps['finite_high_water']==0 and
                    not any(caps['fence_floors']),'PRISTINE_ROUTE_REQUIRED')
                with self.journal._transaction():
                    self.policy.fresh(context);self._check_images()
                    route=self.store.route();c.require(route['bind'] is None,'BIND_UNCERTAIN')
                    # Host-authority association is part of the context, not a
                    # mutable label supplied by the application.
                    context_digest=c.identity('HMS-STANDING-CONTEXT-v0.1',{
                        'authority':self.journal.authority_id,'installation':self.store.meta['installationDigest']})
                    request=self.store.reserve_frame(w.bind(1,1,bytes.fromhex(self.store.installation['endpoint']['manifestHex']),
                                                            bytes.fromhex(context_digest[7:])))
                    route=self.store.route()
                    route['bind']={'body':request.frame.payload.hex(),'tx':request.frame.sequence,
                                   'state':'possible','context':context_digest[7:]}
                    self.store._write('sd_route','singleton=?',(1,),route,4096)
                    self.journal._require_at_commit(self._check_images)
                self._checkpoint('after_bind_handoff_commit',copy.deepcopy(route))
                self._check_images()  # expiry can veto only; committed possibility remains
                result=self._exchange(request)
                c.require(result['status']==0 and 'capabilities' in result,'BIND_REFUSED_OR_UNCERTAIN')
                self._accept_bind(request,result)
                return self.store.route()

    def _accept_bind(self,request,response):
        caps=response['capabilities']
        with self.journal._transaction():
            route=self.store.route();pending=route['bind']
            c.require(pending is not None and pending['body']==request.frame.payload.hex() and
                pending['tx']==request.frame.sequence and caps['generation']==2 and caps['handle']==1 and
                caps['context_digest'].hex()==pending['context'] and caps['slot_kind']==0,'BIND_ASSOCIATION')
            route.update(generation=2,handle=1,contextDigest=pending['context'],bind=None)
            self.store._write('sd_route','singleton=?',(1,),route,4096)

    def reconcile_binding(self,context):
        """Observe an exact original BIND; never create/replace context on loss."""
        with self._route_lock:
            self.policy.authorize(context,'read',self.store.installation['instanceId'])
            route=self.store.route();c.require(route['bind'] is not None,'BIND_NOT_PENDING')
            _,response=self._descriptor();caps=response['capabilities'];pending=route['bind']
            c.require(caps['generation']==2 and caps['handle']==1 and caps['context_digest'].hex()==pending['context'] and
                      caps['slot_kind']==0,'BIND_UNRESOLVED')
            with self.journal._transaction():
                route=self.store.route();route.update(generation=2,handle=1,contextDigest=pending['context'],bind=None)
                self.store._write('sd_route','singleton=?',(1,),route,4096)
            return self.store.route()

    def prepare(self,context,request):
        request=c.parse_request(request)
        with self._route_lock:
            prior=self.store.prior(context,request)
            if prior is not None:
                return prior
            with self._images():
                _,response=self._descriptor()
                with self.catalog.hold_selection(context,request):
                    with self.journal._transaction():
                        selection=self.catalog.select(context,request)
                        self.journal._require_at_commit(self._check_images)
                        row,_=self.store.admit(context,request,selection,response['capabilities'])
            self._checkpoint('after_deployment_commit',copy.deepcopy(row))
            return row

    @contextmanager
    def _extension(self,context,row):
        with self._images():
            with self.catalog.hold_selection(context,row['request']):
                def check():
                    self._check_images()
                    current=self.catalog._selected(context,row['request'])
                    c.require(canonical(current.document)==canonical(row['mapping']['selection']),'ORIGINAL_SELECTION_CHANGED')
                yield check

    def _veto_extension(self,row):
        # Pure held-image/evidence and bounded inventory read after the final
        # possible-send COMMIT. The route mutex excludes another route sender;
        # this final sample can only withdraw already committed permission.
        # It is not an atomic/realtime guarantee across a blocking handoff.
        with self.journal._mutex:
            self._check_images()
            self.policy.fresh(self.policy.owner)
            held=self.catalog._selection
            c.require(held is not None and held[2]==canonical(row['request']),'SELECTION_UNAVAILABLE')
            held[4].check()
            inventory,_=self.catalog._inventory(row['request'])
            c.require(inventory==held[3],'SELECTION_CHANGED')

    def open(self,context,identifier):
        with self._route_lock:
            row=self.store.row(identifier);self.store.access(context,row)
            if row['openState']!='prepared' or row['recoveryRequired'] or row['retired']:
                return row
            with self._extension(context,row) as check:
                request=self.store.mark_open_possible(identifier,admission_check=check)
                # A fresh final held-evidence veto after the durable possible
                # checkpoint, including a blocking COMMIT, never grants a retry.
                self._veto_extension(row)
                response=self._exchange(request)
                return self.store.record_open(identifier,request,response)

    def status(self,context,identifier):
        with self._route_lock:
            row=self.store.row(identifier);self.store.access(context,row)
            if row['retired']:
                return row
            request,response=self._query(w.status(self.store.reference(row)))
            if response['status']==0:
                return self.store.record_status(identifier,request,response)
            raise JournalError('STANDING_STATUS_UNRESOLVED')

    def _prior_mutation(self,context,identifier,key,opcode):
        validate_identifier(key)
        with self.journal._mutex:
            row=self.store.row(identifier);self.store.access(context,row)
            prior=self.journal._db.execute('SELECT number FROM sd_mutations WHERE deployment_id=? AND host_key=?',(identifier,key)).fetchone()
            if prior:
                item=self.store.mutation(identifier,prior[0])
                c.require(item['opcode']==int(opcode),'KEY_CONFLICT')
                return item
            return None

    def mutate(self,context,identifier,key,opcode):
        """START/RENEW/SUSPEND/RESUME/STOP/RETIRE. No raw lease or wire ingress."""
        c.require(type(opcode) is w.Opcode and opcode in {w.Opcode.START,w.Opcode.RENEW,w.Opcode.SUSPEND,
            w.Opcode.RESUME,w.Opcode.STOP,w.Opcode.RETIRE},'OPCODE')
        with self._route_lock:
            prior=self._prior_mutation(context,identifier,key,opcode)
            if prior is not None:
                return prior
            row=self.status(context,identifier)
            ordinary=opcode in {w.Opcode.START,w.Opcode.RENEW,w.Opcode.RESUME}
            lease=0
            if opcode in {w.Opcode.RENEW,w.Opcode.RESUME}:
                _,description=self._descriptor();lease=description['capabilities']['now']+1000
            ack=row['collected'] if opcode==w.Opcode.RETIRE else 0
            if ordinary:
                with self._extension(context,row) as check:
                    with self.journal._transaction():
                        item,_=self.store.reserve_mutation(context,identifier,key,opcode,
                            lease_until=lease,ack=ack,admission_check=check)
                    self._checkpoint('after_mutation_reservation_commit',copy.deepcopy(item))
                    return self._send_mutation(identifier,item,ordinary=True,admission_check=check)
            with self.journal._transaction():
                item,_=self.store.reserve_mutation(context,identifier,key,opcode,
                    lease_until=lease,ack=ack,admission_check=None)
            self._checkpoint('after_mutation_reservation_commit',copy.deepcopy(item))
            return self._send_mutation(identifier,item,ordinary=False)

    def _send_mutation(self,identifier,item,*,ordinary,admission_check=None):
        if item['state']!='prepared':
            return item
        request=self.store.mark_mutation_possible(identifier,item['number'],admission_check=admission_check)
        if ordinary:
            self._veto_extension(self.store.row(identifier))
        response=self._exchange(request)
        return self.store.record_mutation(identifier,item['number'],request,response)

    def collect(self,context,identifier,*,acknowledge=True):
        c.require(type(acknowledge) is bool,'BOOLEAN')
        with self._route_lock:
            row=self.store.row(identifier);self.store.access(context,row)
            c.require(not row['retired'],'RETIRED')
            reference=self.store.reference(row)
            first_request,first=self._query(w.status(reference))
            c.require(first['status']==0 and 'state' in first,'STATUS_REQUIRED')
            records=[]
            # Native ledger capacity is exactly two. Pages are separate samples;
            # immutable identity/activation bytes, not a fictitious atomic
            # multi-page revision, join them in the shared commit.
            for number in range(first['prefix']['ack_watermark']+1,first['prefix']['activation_high_water']+1):
                c.require(len(records)<2,'LEDGER_CAPACITY')
                request,response=self._query(w.status(reference,2,number))
                c.require(response['status']==0 and 'activation' in response,'ACTIVATION_REQUIRED')
                records.append((request,response))
            request,response=self._query(w.status(reference))
            c.require(response['status']==0,'STATUS_REQUIRED')
            row=self.store.collect(identifier,records,request,response)
            # Separate committed outbox reservation is deliberate: after a
            # crash here, exact committed prefix remains and no ACK was sent.
            self._checkpoint('after_collection_before_ack',copy.deepcopy(row))
            if acknowledge and row['collected']>row['acknowledged'] and not row['effectUnknown']:
                base='ack:'+str(row['collected'])+':'+str(row['revision'])
                key=base
                for _ in range(128):
                    prior=self._prior_mutation(context,identifier,key,w.Opcode.ACK)
                    if prior is None:
                        break
                    if prior['state']!='never_handed_off':
                        return row
                    # Explicitly abandoned originals remain replayable. A new
                    # caller-requested collect may admit a new ACK identity,
                    # but never resends a prepared/possible/refused old body.
                    key=base+':after:'+str(prior['number'])
                else:
                    raise JournalError('STANDING_MUTATION_CAPACITY')
                loss=self.store.state(row)['lifecycle'] in (4,5)
                if loss:
                    with self.journal._transaction():
                        item,_=self.store.reserve_mutation(context,identifier,key,w.Opcode.ACK,
                            ack=row['collected'],admission_check=None)
                    self._checkpoint('after_mutation_reservation_commit',copy.deepcopy(item))
                    self._send_mutation(identifier,item,ordinary=False)
                else:
                    with self._extension(context,row) as check:
                        with self.journal._transaction():
                            item,_=self.store.reserve_mutation(context,identifier,key,w.Opcode.ACK,
                                ack=row['collected'],admission_check=check)
                        self._checkpoint('after_mutation_reservation_commit',copy.deepcopy(item))
                        self._send_mutation(identifier,item,ordinary=True,admission_check=check)
            return self.store.row(identifier)

    def reconcile(self,context,identifier):
        """Explicit read-only endpoint recovery; never OPEN/START/RENEW/ACK."""
        with self._route_lock:
            row=self.store.row(identifier);self.store.access(context,row)
            if row['retired']:
                return row
            request,response=self._query(w.status(self.store.reference(row)))
            if response['status']==0:
                return self.store.reconcile_status(identifier,request,response)
            if response['status']==w.Status.OLD_OR_FORGOTTEN:
                caps_request,caps_response=self._descriptor()
                return self.store.reconcile_retirement(identifier,request,response,caps_request,caps_response)
            raise JournalError('STANDING_RECONCILIATION_UNRESOLVED')

    def abandon_prepared(self,context,identifier,*,mutation_key=None):
        """Explicitly settle a never-possible original; never resume its send."""
        with self._route_lock:
            row=self.store.row(identifier);self.store.access(context,row)
            self.policy.authorize(context,'cancel',self.store.installation['instanceId'])
            if mutation_key is None:
                if row['openState']=='never_handed_off':
                    return row
                c.require(row['openState']=='prepared' and row['revoke'] is None,'NEVER_HANDED_OFF_REQUIRED')
                request,response=self._query(w.status(self.store.reference(row)))
                caps_request,caps=self._descriptor()
                return self.store.abandon_prepared_open(context,identifier,request,response,caps_request,caps)
            validate_identifier(mutation_key)
            with self.journal._mutex:
                found=self.journal._db.execute('SELECT number FROM sd_mutations WHERE deployment_id=? AND host_key=?',
                    (identifier,mutation_key)).fetchone()
                c.require(found is not None,'MUTATION_NOT_FOUND')
                item=self.store.mutation(identifier,found[0])
            if item['state']=='never_handed_off':
                return item
            c.require(item['state']=='prepared','NEVER_HANDED_OFF_REQUIRED')
            request,response=self._query(w.status(self.store.reference(row)))
            return self.store.abandon_prepared_mutation(context,identifier,item['number'],request,response)

    def revoke(self,context,identifier):
        """Bounded common loss command even when mutation acceptance is unknown."""
        with self._route_lock:
            with self.journal._transaction():
                item=self.store.reserve_revoke(context,identifier)
            if item['state']!='prepared':
                return self.store.row(identifier)
            request=self.store.mark_revoke_possible(identifier)
            response=self._exchange(request)
            return self.store.record_revoke(identifier,request,response)
