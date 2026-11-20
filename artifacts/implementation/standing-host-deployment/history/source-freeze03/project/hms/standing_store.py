"""Standing deployment identity/outbox/prefix on the original Journal authority.

The local SQLite ordering test has bounded logical records, not protected disk
capacity. No method performs transport or starts a process. Test checkpoints are
original private subclass hooks, never application request fields.
"""
from __future__ import annotations
import copy
import json
import uuid

from .contracts import canonical, parse_json
from .journal import Context, JournalError
from . import standing_contracts as c
from . import standing_wire as w
from protocol.serial.frame import Frame

_DDL = (
    'CREATE TABLE sd_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1), document BLOB NOT NULL)',
    'CREATE TABLE sd_route(singleton INTEGER PRIMARY KEY CHECK(singleton=1), document BLOB NOT NULL)',
    '''CREATE TABLE sd_deployments(id TEXT PRIMARY KEY REFERENCES resource_owners(id),
       principal TEXT NOT NULL,deployment TEXT NOT NULL,namespace TEXT NOT NULL,caller_key TEXT NOT NULL,
       request_digest TEXT NOT NULL,document BLOB NOT NULL,UNIQUE(principal,deployment,namespace,caller_key))''',
    '''CREATE TABLE sd_mutations(deployment_id TEXT NOT NULL REFERENCES sd_deployments(id),
       number INTEGER NOT NULL,host_key TEXT NOT NULL,endpoint_sequence INTEGER NOT NULL,
       document BLOB NOT NULL,PRIMARY KEY(deployment_id,number),UNIQUE(deployment_id,host_key))''',
    '''CREATE TABLE sd_activations(deployment_id TEXT NOT NULL REFERENCES sd_deployments(id),
       number INTEGER NOT NULL,document BLOB NOT NULL,PRIMARY KEY(deployment_id,number))''',
    '''CREATE TABLE sd_episodes(deployment_id TEXT NOT NULL REFERENCES sd_deployments(id),
       episode_key TEXT NOT NULL,document BLOB NOT NULL,PRIMARY KEY(deployment_id,episode_key))''',
    '''CREATE TABLE sd_activation_versions(deployment_id TEXT NOT NULL REFERENCES sd_deployments(id),
       number INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version IN (0,1)),
       document BLOB NOT NULL,PRIMARY KEY(deployment_id,number,version))''',
    '''CREATE TABLE sd_conflicts(deployment_id TEXT NOT NULL REFERENCES sd_deployments(id),
       number INTEGER NOT NULL,document BLOB NOT NULL,PRIMARY KEY(deployment_id,number))''',
)
_TABLES = ('sd_meta','sd_route','sd_deployments','sd_mutations','sd_activations','sd_episodes',
           'sd_activation_versions','sd_conflicts')
_ROW_FIELDS = ('id','principal','deployment','namespace','key','request','requestDigest',
    'mapping','open','openTx','openState','openReply','revoke','ownerEpoch','recoveryRequired',
    'transportUncertain','sequenceUncertain','effectUnknown','disputed','everPossiblyActed','retired','collected',
    'acknowledged','highWater','mutationSequence','revision','lastStatus','hostRevision')
_IMMUTABLE = ('id','principal','deployment','namespace','key','request','requestDigest','mapping','open','openTx')
_DEPLOYMENT_CHARGE = 896 * 1024
_FIXED_CHARGE = 512 * 1024
_RECORD_LIMITS = {'sd_meta':65536,'sd_route':4096,'sd_deployments':32768,'sd_mutations':1536,
                  'sd_activations':1024,'sd_activation_versions':1024,'sd_episodes':1536,'sd_conflicts':1536}


class StandingStore:
    def __init__(self, journal, policy, catalog, *, create=False):
        c.require(journal.standing_profile and policy.journal is journal and catalog.journal is journal,
                  'SHARED_AUTHORITY_REQUIRED')
        self.journal, self.db, self.policy, self.catalog = journal, journal._db, policy, catalog
        with journal._transaction():
            present = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'sd_*'")}
            if create:
                c.require(not present, 'ALREADY_INITIALIZED')
                for sql in _DDL:
                    self.db.execute(sql)
                installation = copy.deepcopy(policy.installation)
                meta = {'profile':c.PROFILE, 'authorityId':journal.authority_id,
                        'installation':installation, 'installationDigest':c.identity('HMS-STANDING-INSTALLATION-v0.1',installation)}
                route = {'boot':str(installation['endpoint']['boot']), 'tx':0,'rx':0,'standingFloor':0,
                         'fences':[0]*8,'generation':0,'handle':0,'contextDigest':None,'bind':None}
                self.db.execute('INSERT INTO sd_meta VALUES(1,?)',(canonical(meta),))
                self.db.execute('INSERT INTO sd_route VALUES(1,?)',(canonical(route),))
            else:
                c.require(present == set(_TABLES), 'SCHEMA')
            self.meta = self._read('sd_meta','singleton=?',(1,),65536)
            c.exact(self.meta,('profile','authorityId','installation','installationDigest'))
            c.require(self.meta['profile'] == c.PROFILE and self.meta['authorityId'] == journal.authority_id,
                      'AUTHORITY_CHANGED')
            self.installation = c.parse_installation(self.meta['installation'])
            c.require(c.identity('HMS-STANDING-INSTALLATION-v0.1',self.installation) == self.meta['installationDigest'],
                      'INSTALLATION_CHANGED')
            self.route()
            rows = self.db.execute('SELECT id FROM sd_deployments ORDER BY id LIMIT 17').fetchall()
            c.require(len(rows) <= 16, 'CAPACITY')
            for (identifier,) in rows:
                row = self.row(identifier)
                if not row['retired'] and row['ownerEpoch'] != journal.owner_epoch:
                    row['recoveryRequired'] = True
                    row['ownerEpoch'] = journal.owner_epoch
                    self._save(row)

    def _checkpoint(self, phase, value=None):
        pass

    def _read(self, table, where, args, maximum, *, optional=False):
        with self.journal._mutex:
            return self._read_locked(table,where,args,maximum,optional=optional)

    def _read_locked(self, table, where, args, maximum, *, optional=False):
        c.require(table in _TABLES, 'TABLE')
        maximum=min(maximum,_RECORD_LIMITS[table])
        shape = self.db.execute('SELECT typeof(document),length(document) FROM '+table+' WHERE '+where+' LIMIT 2',args).fetchall()
        if not shape and optional:
            return None
        c.require(len(shape)==1 and shape[0][0]=='blob' and type(shape[0][1]) is int and
                  0<shape[0][1]<=maximum,'STORED_RECORD')
        raw = self.db.execute('SELECT document FROM '+table+' WHERE '+where,args).fetchone()[0]
        value = parse_json(raw)
        c.require(canonical(value)==raw,'NONCANONICAL_RECORD')
        return value

    def _write(self, table, where, args, value, maximum=65536):
        c.require(self.db.in_transaction and table in _TABLES,'TRANSACTION_REQUIRED')
        maximum=min(maximum,_RECORD_LIMITS[table])
        wire = canonical(value);c.require(len(wire)<=maximum,'RECORD_LIMIT')
        self.db.execute('UPDATE '+table+' SET document=? WHERE '+where,(wire,*args))

    def route(self):
        route = self._read('sd_route','singleton=?',(1,),4096)
        c.exact(route,('boot','tx','rx','standingFloor','fences','generation','handle','contextDigest','bind'))
        c.require(type(route['boot']) is str and route['boot'].isdigit() and str(int(route['boot']))==route['boot'], 'BOOT')
        c.uint(int(route['boot']),2**64-2,1)
        for key in ('tx','rx','standingFloor','generation'):
            c.uint(route[key],2**32-1)
        c.uint(route['handle'],65535)
        c.require(type(route['fences']) is list and len(route['fences'])==8,'FENCES')
        for fence in route['fences']:
            c.uint(fence,2**32-1)
        if route['contextDigest'] is not None:
            c.hex_bytes(route['contextDigest'],32,nonzero=True)
        return route

    def row(self, identifier):
        row = self._read('sd_deployments','id=?',(identifier,),32768)
        c.exact(row,_ROW_FIELDS)
        c.require(row['id']==identifier and row['requestDigest']==c.request_digest(row['request']), 'IDENTITY')
        c.require(row['namespace']==row['request']['replayNamespace'] and row['key']==row['request']['deploymentKey'],'IDENTITY')
        for key in ('recoveryRequired','transportUncertain','sequenceUncertain','effectUnknown','disputed','everPossiblyActed','retired'):
            c.require(type(row[key]) is bool,'STORED_RECORD')
        for key in ('collected','acknowledged','highWater','mutationSequence','revision','hostRevision','openTx'):
            c.uint(row[key],2**32-1)
        c.uint(row['ownerEpoch'],c.SAFE_INTEGER)
        c.require(row['acknowledged']<=row['collected']<=row['highWater']<=row['request']['limits']['activationCap'],'PREFIX')
        opened = w.Open.parse(c.hex_bytes(row['open'],134))
        c.require(opened.reference.intent_digest.hex()==row['mapping']['deploymentDigest'][7:] and
                  row['mapping']['requestDigest']==row['requestDigest'],'IDENTITY')
        c.require(row['openState'] in {'prepared','possible','accepted','refused','never_handed_off'},'OUTBOX_STATE')
        if row['revoke'] is not None:
            revoke=row['revoke'];c.exact(revoke,('body','tx','state','reply'))
            c.uint(revoke['tx'],2**32-1,1)
            c.require(revoke['state'] in {'prepared','possible','accepted','refused'} and
                      c.hex_bytes(revoke['body'],10)==w.revoke(row['mapping']['generation'],row['mapping']['handle']),
                      'REVOKE_RECORD')
        return row

    def _save(self,row):
        old = self.row(row['id'])
        c.require(all(canonical(row[key])==canonical(old[key]) for key in _IMMUTABLE),'IDENTITY_REWRITE')
        c.require(all(row[key]>=old[key] for key in ('collected','acknowledged','highWater','mutationSequence','revision')),'COUNTER_REGRESSION')
        c.require(not old['everPossiblyActed'] or row['everPossiblyActed'],'EFFECT_REGRESSION')
        c.require(not old['effectUnknown'] or row['effectUnknown'],'EFFECT_REGRESSION')
        c.require(not old['disputed'] or row['disputed'],'DISPUTE_REGRESSION')
        if old['revoke'] is not None:
            c.require(row['revoke'] is not None and all(row['revoke'][key]==old['revoke'][key] for key in ('body','tx')),
                      'IDENTITY_REWRITE')
        c.require(not old['retired'] or row==old,'TERMINAL_REWRITE')
        row['hostRevision'] = old['hostRevision']+1
        c.uint(row['hostRevision'],2**32-1)
        self._write('sd_deployments','id=?',(row['id'],),row,32768)

    def access(self,context,row):
        self.policy.authorize(context,'read',self.installation['instanceId'])
        c.require((context.principal,context.deployment)==(row['principal'],row['deployment']),'ACCESS_DENIED')

    def prior(self,context,request):
        with self.journal._mutex:
            found = self.db.execute('SELECT id FROM sd_deployments WHERE principal=? AND deployment=? AND namespace=? AND caller_key=?',
                (context.principal,context.deployment,request['replayNamespace'],request['deploymentKey'])).fetchone()
            if found is None:
                return None
            row=self.row(found[0]);self.access(context,row)
            c.require(row['requestDigest']==c.request_digest(request),'KEY_CONFLICT')
            return row

    def reserve_frame(self,payload):
        c.require(self.db.in_transaction,'TRANSACTION_REQUIRED')
        route=self.route();c.require(route['tx']<2**32-1,'COUNTER_EXHAUSTED')
        route['tx']+=1
        request=w.Request(Frame(1,0,0 if payload[1]==w.Opcode.DESCRIBE else int(route['boot']),route['tx'],payload))
        self._write('sd_route','singleton=?',(1,),route,4096)
        return request

    def receive(self,frame):
        c.require(frame.kind==2 and frame.channel==0 and frame.sequence>0,'FRAME')
        with self.journal._transaction():
            route=self.route()
            c.require(frame.session==int(route['boot']) and frame.sequence>route['rx'],'BOOT_OR_RESPONSE_REPLAY')
            route['rx']=frame.sequence
            self._write('sd_route','singleton=?',(1,),route,4096)

    def admit(self,context,request,selection,capabilities):
        """Caller holds image/evidence owners and one short authority TX."""
        c.require(self.db.in_transaction,'TRANSACTION_REQUIRED')
        previous=self.prior(context,request)
        if previous is not None:
            return previous,False
        namespace=self.journal._namespace(context,request['replayNamespace'])
        now=self.journal._now();c.require(now<namespace['expires_ms'],'NAMESPACE_EXPIRED')
        installation,proof=self.policy.fresh(context)
        c.require(canonical(installation)==canonical(self.installation),'INSTALLATION_CHANGED')
        self.catalog.check_selection(selection,context)
        self.journal._require_at_commit(self.policy.check_image)
        deployment_count=self.db.execute('SELECT count(*) FROM sd_deployments').fetchone()[0]
        c.require(deployment_count<16 and _FIXED_CHARGE+(deployment_count+1)*_DEPLOYMENT_CHARGE<=
                  c.CAPACITY['maxStandingLogicalBytes'],'CAPACITY')
        for (identifier,) in self.db.execute('SELECT id FROM sd_deployments').fetchall():
            c.require(self.row(identifier)['retired'],'ENDPOINT_SLOT_BUSY')
        for table,field in (('replay_keys','caller_key'),('pr_keys','caller_key'),('px_triggers','run_key')):
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                c.require(self.db.execute('SELECT 1 FROM '+table+' WHERE namespace=? AND '+field+'=?',
                    (request['replayNamespace'],request['deploymentKey'])).fetchone() is None,'KEY_CONFLICT')
        route=self.route();c.require(route['generation']>0 and route['handle']>0 and route['bind'] is None,'BIND_REQUIRED')
        confirmed_high,confirmed_fences=self._confirmed_route_counters()
        c.require(capabilities['slot_kind']==0 and capabilities['standing_high_water']==confirmed_high and
                  list(capabilities['fence_floors'])==confirmed_fences and capabilities['finite_high_water']==0,
                  'ENDPOINT_COUNTER_DRIFT')
        c.require(capabilities['generation']==route['generation'] and capabilities['handle']==route['handle'] and
                  capabilities['context_digest'].hex()==route['contextDigest'],'CONTEXT_CHANGED')
        c.require(route['standingFloor']<2**32-1,'COUNTER_EXHAUSTED')
        route['standingFloor']+=1
        owner='standing:'+uuid.uuid4().hex
        resources=tuple(sorted(proof['expandedClaims']['control']))
        claims=self.journal._reserve_standing_resources(owner,context,(installation['instanceId'],),resources)
        for i in range(2):
            c.require(route['fences'][i]<2**32-1,'COUNTER_EXHAUSTED');route['fences'][i]+=1
        mapping={'requestDigest':c.request_digest(request),'installationDigest':self.meta['installationDigest'],
                 'selection':selection.document,'claims':claims,'resourceProof':proof,
                 'authorityId':self.journal.authority_id,'boot':route['boot'],
                 'generation':route['generation'],'handle':route['handle'],
                 'standingNumber':route['standingFloor'],'fences':list(route['fences']),
                 'instanceId':installation['instanceId'],'capacityScope':c.CAPACITY,
                 'logicalContinuationReservation':_DEPLOYMENT_CHARGE}
        mapping['deploymentDigest']=c.identity('HMS-STANDING-DEPLOYMENT-v0.1',mapping)
        reference=w.Reference(route['generation'],route['handle'],route['standingFloor'],bytes.fromhex(mapping['deploymentDigest'][7:]))
        until=capabilities['now']+request['limits']['leaseHorizonMs']
        c.require(until<2**64-1 and request['limits']['leaseHorizonMs']<=capabilities['maximum_lease'],'LEASE')
        opened=w.Open(reference,selection.configuration,3,tuple(route['fences']),until,
                      request['limits']['activationCap'],*installation['endpoint']['epochs'])
        self._write('sd_route','singleton=?',(1,),route,4096)
        frame=self.reserve_frame(opened.payload())
        row={'id':owner,'principal':context.principal,'deployment':context.deployment,
             'namespace':request['replayNamespace'],'key':request['deploymentKey'],'request':copy.deepcopy(request),
             'requestDigest':c.request_digest(request),'mapping':mapping,'open':opened.payload().hex(),
             'openTx':frame.frame.sequence,'openState':'prepared','openReply':None,'revoke':None,
             'ownerEpoch':self.journal.owner_epoch,'recoveryRequired':False,'transportUncertain':False,'sequenceUncertain':False,
             'effectUnknown':False,'disputed':False,'everPossiblyActed':False,'retired':False,'collected':0,
             'acknowledged':0,'highWater':0,'mutationSequence':0,'revision':0,'lastStatus':None,'hostRevision':1}
        # Keep8KiB within the persisted32KiB row ceiling for OPEN/state replies,
        # the one common-revoke outbox and counter growth. Two maximum OPEN
        # envelopes are <=1476B together; revoke with reply <=565B, scalar
        # growth <256B. Immutable selection/configuration can never spend this.
        raw=canonical(row);c.require(len(raw)<=24*1024,'ADMISSION_RECORD_HEADROOM')
        self.db.execute('INSERT INTO sd_deployments VALUES(?,?,?,?,?,?,?)',
            (owner,context.principal,context.deployment,row['namespace'],row['key'],row['requestDigest'],raw))
        self._checkpoint('before_deployment_commit',copy.deepcopy(row))
        return row,True

    @staticmethod
    def reference(row):
        return w.Open.parse(bytes.fromhex(row['open'])).reference

    @staticmethod
    def envelope(request,response):
        return {'request':request.frame.payload.hex(),'tx':request.frame.sequence,
                'response':response['raw'].hex(),'rx':response['response_sequence'],'boot':str(response['session'])}

    @staticmethod
    def decode(envelope):
        payload=bytes.fromhex(envelope['request'])
        session=0 if payload[1]==w.Opcode.DESCRIBE else int(envelope['boot'])
        request=w.Request(Frame(1,0,session,envelope['tx'],payload))
        return w.decode_response(Frame(2,0,int(envelope['boot']),envelope['rx'],bytes.fromhex(envelope['response'])),request)

    @staticmethod
    def _checked_response(request,response,expected=None):
        """Only canonical raw frame bytes can supply endpoint evidence.

        Mapping fields supplied by a route cannot substitute for re-decoding
        against the exact retained request. None means evidence must be latched
        as conflicting/unknown by the owning transaction, not silently dropped.
        """
        try:
            c.require(type(request) is w.Request and type(response) is dict,'RESPONSE_ASSOCIATION')
            checked=w.Request(request.frame)
            if expected is not None:
                c.require(checked.frame==expected.frame,'RESPONSE_ASSOCIATION')
            return w.decode_response(Frame(2,0,response['session'],response['response_sequence'],response['raw']),checked)
        except (JournalError,ValueError,TypeError,KeyError,IndexError,OverflowError):
            return None

    @staticmethod
    def _possible_evidence(request,response):
        """Retain bounded offending wire bytes even when decode fails."""
        if (type(request) is w.Request and type(response) is dict and
                type(response.get('raw')) is bytes and len(response['raw'])<=192 and
                type(response.get('session')) is int and 0<=response['session']<2**64 and
                type(response.get('response_sequence')) is int and 0<=response['response_sequence']<2**32):
            return StandingStore.envelope(request,response)
        return {'malformedEvidence':True}

    def _latch_conflict(self,row,reason,request,response):
        c.require(self.db.in_transaction,'TRANSACTION_REQUIRED')
        row['disputed']=row['effectUnknown']=row['recoveryRequired']=True
        if reason in {'IDENTITY','FOREIGN_MUTATION','STATUS_ASSOCIATION','OPEN_RESPONSE_ASSOCIATION',
                      'MUTATION_RESPONSE_ASSOCIATION','REVOKE_RESPONSE_ASSOCIATION','RETIREMENT_ASSOCIATION'}:
            row['sequenceUncertain']=True
        evidence={'reason':reason,'evidence':self._possible_evidence(request,response)}
        raw=canonical(evidence);c.require(len(raw)<=1536,'RECORD_LIMIT')
        existing=self.db.execute('SELECT document FROM sd_conflicts WHERE deployment_id=? ORDER BY number LIMIT 17',
                                 (row['id'],)).fetchall()
        c.require(len(existing)<=16,'CONFLICT_CAPACITY')
        if not any(bytes(saved[0])==raw for saved in existing) and len(existing)<16:
            self.db.execute('INSERT INTO sd_conflicts VALUES(?,?,?)',(row['id'],len(existing)+1,raw))
        # Exhaustion never removes the sticky fact or an earlier retained
        # contradiction. At most16 original conflict packets are retained.
        return False

    def _known_sequence(self,row,state,accepted_item=None):
        sequence=state['mutation_sequence']
        if sequence==0:
            return row['mutationSequence']==0 and not any(state['last_comparison'])
        if sequence<row['mutationSequence'] or sequence>row['mutationSequence']+1:
            return False
        candidates=self.db.execute('SELECT number FROM sd_mutations WHERE deployment_id=? AND endpoint_sequence=? ORDER BY number LIMIT 129',
                                   (row['id'],sequence)).fetchall()
        if len(candidates)>128:
            return False
        items=[self.mutation(row['id'],number) for (number,) in candidates]
        if accepted_item is not None:
            items.append(accepted_item)
        for item in items:
            if item['state'] not in {'accepted','possible'} or item['endpointSequence']!=sequence:
                continue
            body=bytes.fromhex(item['body'])
            if body[:2]+body[48:66]==state['last_comparison']:
                return True
        return False

    def state(self,row):
        c.require(row['lastStatus'] is not None,'STATUS_REQUIRED')
        return self.decode(row['lastStatus'])['state']

    def _state_record(self,row,request,response,accepted_item=None):
        state=response['state'];prefix=response['prefix']
        reference=self.reference(row)
        checks=(
            ((prefix['generation'],prefix['handle'],prefix['standing_number'],prefix['intent_digest'])==
             (reference.generation,reference.handle,reference.standing_number,reference.intent_digest),'IDENTITY'),
            (state['owned_mask']==3 and state['epochs']==tuple(self.installation['endpoint']['epochs']),'FOOTPRINT'),
            (not state['witness']['valid'] or (state['witness']['evidence'],state['witness']['verification'])==(5,0),
             'PHYSICAL_EVIDENCE_UNQUALIFIED'),
            (prefix['ack_watermark']<=row['collected'],'ACK_AHEAD_OF_COMMIT'),
            (row['highWater']<=prefix['activation_high_water']<=row['request']['limits']['activationCap'] and
             prefix['ack_watermark']>=row['acknowledged'] and prefix['revision']>=row['revision'],'COUNTER_REGRESSION'),
            (self._known_sequence(row,state,accepted_item),'FOREIGN_MUTATION'))
        for valid,reason in checks:
            if not valid:
                return self._latch_conflict(row,reason,request,response)
        row['acknowledged']=prefix['ack_watermark'];row['highWater']=prefix['activation_high_water']
        row['mutationSequence']=prefix['mutation_sequence'];row['revision']=prefix['revision']
        row['everPossiblyActed'] |= bool(state['flags']&1)
        row['effectUnknown'] |= bool(state['flags']&6)
        row['disputed'] |= bool(state['flags']&4)
        row['recoveryRequired'] |= row['effectUnknown'] or row['disputed']
        row['lastStatus']=self.envelope(request,response)
        return True

    def record_status(self,identifier,request,response):
        with self.journal._transaction():
            row=self.row(identifier)
            checked=self._checked_response(request,response)
            valid=(checked is not None and request.opcode==w.Opcode.STATUS and checked['status']==0 and 'state' in checked)
            if valid:
                valid=self._state_record(row,request,checked)
            else:
                self._latch_conflict(row,'STATUS_ASSOCIATION',request,response)
            self._save(row)
        c.require(valid,'EVIDENCE_CONFLICT')
        return self.row(identifier)

    def mark_open_possible(self,identifier,*,admission_check):
        with self.journal._transaction():
            row=self.row(identifier)
            c.require(not row['recoveryRequired'] and row['openState']=='prepared','RECOVERY_REQUIRED')
            c.require(callable(admission_check),'ORDINARY_GUARD_REQUIRED')
            admission_check();self.journal._require_at_commit(admission_check)
            row['openState']='possible';row['transportUncertain']=row['sequenceUncertain']=True
            # OPEN can acquire from the device even before an output transition.
            row['everPossiblyActed']=True
            self._save(row);self._checkpoint('before_open_handoff_commit',copy.deepcopy(row))
        self._checkpoint('after_open_handoff_commit',copy.deepcopy(row))
        return w.Request(Frame(1,0,int(row['mapping']['boot']),row['openTx'],bytes.fromhex(row['open'])))

    def record_open(self,identifier,request,response):
        with self.journal._transaction():
            row=self.row(identifier);c.require(row['openState']=='possible','OUTBOX_STATE')
            expected=w.Request(Frame(1,0,int(row['mapping']['boot']),row['openTx'],bytes.fromhex(row['open'])))
            checked=self._checked_response(request,response,expected)
            valid=checked is not None
            if checked is None:
                self._latch_conflict(row,'OPEN_RESPONSE_ASSOCIATION',request,response)
            elif checked['status']==0:
                valid=self._state_record(row,request,checked)
                if valid:
                    row['openReply']=self.envelope(request,checked)
                    row['openState']='accepted';row['transportUncertain']=row['sequenceUncertain']=False
            else:
                row['openReply']=self.envelope(request,checked)
                row['openState']='refused';row['recoveryRequired']=True
                row['transportUncertain']=row['sequenceUncertain']=False
            self._save(row)
        c.require(valid,'EVIDENCE_CONFLICT')
        return self.row(identifier)

    def mutation(self,identifier,number):
        c.uint(number,128,1)
        item=self._read('sd_mutations','deployment_id=? AND number=?',(identifier,number),1536)
        required={'number','hostKey','opcode','endpointSequence','body','bodyDigest','tx','leaseUntil','ack','state','reply'}
        c.require(type(item) is dict and required<=set(item)<=required|{'retirementEvidence','settlement'},'MUTATION_RECORD')
        c.require(item['number']==number and item['state'] in {'prepared','possible','accepted','refused','never_handed_off'},'MUTATION_RECORD')
        if item['state']=='never_handed_off':
            c.require(item.get('settlement')=='durable-prepared-never-possible','MUTATION_RECORD')
        for key in ('number','endpointSequence','tx'):
            c.uint(item[key],2**32-1,1)
        c.uint(item['ack'],2**32-1);c.uint(item['leaseUntil'])
        c.identifier(item['hostKey'])
        body=c.hex_bytes(item['body'],66)
        w.Request(Frame(1,0,1,item['tx'],body))
        c.require(c.sha(body)==item['bodyDigest'] and body[1]==item['opcode'] and
                  int.from_bytes(body[44:48],'big')==item['endpointSequence'] and
                  int.from_bytes(body[52:60],'big')==item['leaseUntil'] and
                  int.from_bytes(body[60:64],'big')==item['ack'],'MUTATION_RECORD')
        return item

    @staticmethod
    def _mutation_request(row,item):
        request=w.Request(Frame(1,0,int(row['mapping']['boot']),item['tx'],bytes.fromhex(item['body'])))
        c.require(request.reference==StandingStore.reference(row),'MUTATION_ASSOCIATION')
        return request

    def pending(self,identifier):
        with self.journal._mutex:
            rows=self.db.execute('SELECT number FROM sd_mutations WHERE deployment_id=? ORDER BY number LIMIT 129',(identifier,)).fetchall()
            c.require(len(rows)<=128,'CAPACITY')
            return [self.mutation(identifier,n) for (n,) in rows if self.mutation(identifier,n)['state'] in {'prepared','possible'}]

    def reserve_mutation(self,context,identifier,host_key,opcode,*,admission_check,lease_until=0,ack=0):
        c.require(self.db.in_transaction,'TRANSACTION_REQUIRED')
        c.identifier(host_key)
        c.uint(lease_until);c.uint(ack,2**32-1)
        row=self.row(identifier);self.access(context,row);c.require(not row['retired'],'RETIRED')
        previous=self.db.execute('SELECT number FROM sd_mutations WHERE deployment_id=? AND host_key=?',(identifier,host_key)).fetchone()
        if previous:
            saved=self.mutation(identifier,previous[0])
            c.require((saved['opcode'],saved['leaseUntil'],saved['ack'])==(int(opcode),lease_until,ack),'KEY_CONFLICT')
            return saved,False
        state=self.state(row)
        loss=opcode in {w.Opcode.STOP,w.Opcode.SUSPEND,w.Opcode.RETIRE} or (opcode==w.Opcode.ACK and state['lifecycle'] in (4,5))
        c.require(row['openState']=='accepted' and not row['sequenceUncertain'] and not self.pending(identifier),
                  'SEQUENCE_UNRESOLVED')
        if loss:
            self.policy.authorize(context,'cancel',self.installation['instanceId'])
            if opcode not in {w.Opcode.STOP,w.Opcode.SUSPEND}:
                c.require(not row['effectUnknown'] and not row['disputed'],'EFFECT_UNRESOLVED')
        else:
            c.require(not row['recoveryRequired'] and not row['transportUncertain'] and
                      not row['effectUnknown'] and not row['disputed'],'RECOVERY_REQUIRED')
            c.require(callable(admission_check),'ORDINARY_GUARD_REQUIRED')
            admission_check();self.journal._require_at_commit(admission_check)
            self.policy.fresh(context);self.journal._require_at_commit(self.policy.check_image)
            episodes=self.db.execute('SELECT count(*) FROM sd_episodes WHERE deployment_id=?',(identifier,)).fetchone()[0]
            # A new active interval must leave the complete installed loss
            # reserve unused. Existing suspended/terminal collection may use it.
            c.require(episodes<row['request']['limits']['episodeRecords']-c.CAPACITY['lossEpisodeReserve'],
                      'EPISODE_CAPACITY')
        count=self.db.execute('SELECT count(*) FROM sd_mutations WHERE deployment_id=?',(identifier,)).fetchone()[0]
        limit=row['request']['limits']['mutationRecords']-(0 if loss else c.CAPACITY['lossMutationReserve'])
        c.require(count<limit,'MUTATION_CAPACITY')
        if opcode==w.Opcode.START:
            c.require(state['lifecycle']==1,'BAD_STATE')
        elif opcode==w.Opcode.RENEW:
            c.require(state['lifecycle']==2 and state['lease_until']<lease_until,'BAD_STATE')
        elif opcode==w.Opcode.ACK:
            c.require(row['acknowledged']<ack<=row['collected'],'PREFIX')
        elif opcode==w.Opcode.RESUME:
            c.require(state['lifecycle']==4 and state['loss_reason'] in (2,3,4) and row['collected']==row['highWater']==row['acknowledged'], 'RESUME_FORBIDDEN')
            self._require_episode(row,state)
        elif opcode==w.Opcode.RETIRE:
            c.require(state['lifecycle']==5 and row['collected']==row['highWater']==row['acknowledged']==ack,'RETIRE_FORBIDDEN')
            self._require_episode(row,state)
        else:
            c.require(opcode in {w.Opcode.STOP,w.Opcode.SUSPEND},'OPCODE')
            if opcode==w.Opcode.SUSPEND:
                c.require(state['lifecycle'] in (1,2),'ALREADY_SUSPENDING')
            else:
                c.require(state['lifecycle'] in (1,2,3,4,6) and
                          not (state['lifecycle']==3 and state['drain_target']==5),'ALREADY_STOPPING')
                c.require(not any(self.mutation(identifier,n)['opcode']==w.Opcode.STOP and
                                  self.mutation(identifier,n)['state']=='accepted' for (n,) in
                                  self.db.execute('SELECT number FROM sd_mutations WHERE deployment_id=?',(identifier,)).fetchall()),
                          'ALREADY_STOPPING')
        # Loss commands cannot consume the last owed ACK/RETIRE slots. Repeated
        # stale proposals with a different host key consume no extra row.
        if loss:
            tail=0 if opcode==w.Opcode.RETIRE else 1
            if opcode in {w.Opcode.STOP,w.Opcode.SUSPEND} and row['highWater']>row['acknowledged']:
                tail+=1
            c.require(count<row['request']['limits']['mutationRecords']-tail,'LOSS_CONTINUATION_RESERVED')
        c.require(row['mutationSequence']<2**32-1,'COUNTER_EXHAUSTED')
        payload=w.mutation(self.reference(row),opcode,row['mutationSequence']+1,row['revision'],
            lease_until=lease_until,ack_watermark=ack,reason=1 if opcode==w.Opcode.STOP else 2 if opcode==w.Opcode.SUSPEND else 0)
        for (prior_number,) in self.db.execute('SELECT number FROM sd_mutations WHERE deployment_id=? AND endpoint_sequence=?',
                                               (identifier,row['mutationSequence']+1)).fetchall():
            prior=self.mutation(identifier,prior_number)
            c.require(prior['state']=='never_handed_off' or prior['body']!=payload.hex(),'REUSE_ORIGINAL_CONTROL_KEY')
        frame=self.reserve_frame(payload)
        item={'number':count+1,'hostKey':host_key,'opcode':int(opcode),'endpointSequence':row['mutationSequence']+1,
              'body':payload.hex(),'bodyDigest':c.sha(payload),'tx':frame.frame.sequence,'leaseUntil':lease_until,
              'ack':ack,'state':'prepared','reply':None}
        # Closed prepared fields are <=521B with128-byte ASCII host keys and
        # maximum permitted counters. Reserve960B by admitting at most576B.
        # A full state reply adds <=598B; retirement recovery adds <=798B
        # (STATUS refusal plus capabilities envelope), hence <=1374B<1536B.
        c.require(len(canonical(item))<=576,'MUTATION_RECORD_HEADROOM')
        self.db.execute('INSERT INTO sd_mutations VALUES(?,?,?,?,?)',(identifier,count+1,host_key,item['endpointSequence'],canonical(item)))
        self._checkpoint('before_mutation_commit',copy.deepcopy(item))
        return item,True

    def mark_mutation_possible(self,identifier,number,*,admission_check=None):
        with self.journal._transaction():
            row=self.row(identifier);item=self.mutation(identifier,number)
            c.require(item['state']=='prepared' and not row['sequenceUncertain'],'RECOVERY_REQUIRED')
            state=self.state(row)
            loss=item['opcode'] in {w.Opcode.STOP,w.Opcode.SUSPEND,w.Opcode.RETIRE} or (
                item['opcode']==w.Opcode.ACK and state['lifecycle'] in (4,5))
            if not loss:
                c.require(not row['recoveryRequired'] and not row['transportUncertain'] and
                          not row['effectUnknown'] and not row['disputed'] and callable(admission_check),
                          'ORDINARY_GUARD_REQUIRED')
                admission_check();self.journal._require_at_commit(admission_check)
            elif item['opcode'] not in {w.Opcode.STOP,w.Opcode.SUSPEND}:
                c.require(not row['effectUnknown'] and not row['disputed'],'EFFECT_UNRESOLVED')
            item['state']='possible';row['transportUncertain']=row['sequenceUncertain']=True
            self._write('sd_mutations','deployment_id=? AND number=?',(identifier,number),item,1536)
            self._save(row);self._checkpoint('before_mutation_handoff_commit',copy.deepcopy(item))
        self._checkpoint('after_mutation_handoff_commit',copy.deepcopy(item))
        return w.Request(Frame(1,0,int(row['mapping']['boot']),item['tx'],bytes.fromhex(item['body'])))

    def record_mutation(self,identifier,number,request,response):
        with self.journal._transaction():
            row=self.row(identifier);item=self.mutation(identifier,number)
            c.require(item['state']=='possible','OUTBOX_STATE')
            checked=self._checked_response(request,response,self._mutation_request(row,item))
            valid=checked is not None
            if checked is None:
                self._latch_conflict(row,'MUTATION_RESPONSE_ASSOCIATION',request,response)
            elif checked['status']==0:
                if item['opcode']==w.Opcode.RETIRE:
                    self._retirement_ready(row,item)
                    row['retired']=True
                    self.db.execute('DELETE FROM claims WHERE operation_id=?',(identifier,))
                else:
                    accepted=dict(item,state='accepted')
                    valid=self._state_record(row,request,checked,accepted)
                    if valid and row['mutationSequence']!=item['endpointSequence']:
                        valid=self._latch_conflict(row,'MUTATION_RESPONSE_ASSOCIATION',request,checked)
            else:
                # A definitive refusal consumes no sequence. Its prefix may
                # reveal foreign acceptance or a missing/regressed record;
                # such a refusal must not reopen the cached old sequence.
                prefix=checked['prefix'];reference=self.reference(row)
                refusal_join=((prefix['generation'],prefix['handle'],prefix['standing_number'],prefix['intent_digest'])==
                              (reference.generation,reference.handle,reference.standing_number,reference.intent_digest) and
                              prefix['mutation_sequence']==row['mutationSequence'] and
                              prefix['revision']>=row['revision'] and
                              prefix['activation_high_water']>=row['highWater'] and
                              row['acknowledged']<=prefix['ack_watermark']<=row['collected'])
                if not refusal_join:
                    valid=self._latch_conflict(row,'MUTATION_RESPONSE_ASSOCIATION',request,checked)
            if valid:
                item['reply']=self.envelope(request,checked)
                item['state']='accepted' if checked['status']==0 else 'refused'
                row['transportUncertain']=row['sequenceUncertain']=False
                self._write('sd_mutations','deployment_id=? AND number=?',(identifier,number),item,1536)
            self._save(row)
        c.require(valid,'EVIDENCE_CONFLICT')
        return self.row(identifier)

    def _retirement_ready(self,row,item):
        c.require(item['opcode']==w.Opcode.RETIRE and item['state']=='possible' and
                  not row['effectUnknown'] and not row['disputed'],'RETIRE_FORBIDDEN')
        state=self.state(row);self._require_episode(row,state)
        body=bytes.fromhex(item['body'])
        c.require(state['lifecycle']==5 and row['acknowledged']==row['collected']==row['highWater']==item['ack'] and
                  row['mutationSequence']+1==item['endpointSequence'] and
                  int.from_bytes(body[48:52],'big')==row['revision'],'RETIRE_FORBIDDEN')

    @staticmethod
    def _episode_key(state):
        return str(state['first_loss_tick'])+':'+str(state['loss_reason'])

    def _require_episode(self,row,state):
        c.require(state['flags']&128 and not state['flags']&6 and state['loss_command']==3 and
                  state['owned_mask']==state['quiescent_mask']==3 and state['witness']['valid'],'QUIESCENCE_REQUIRED')
        saved=self._read('sd_episodes','deployment_id=? AND episode_key=?',
            (row['id'],self._episode_key(state)),1536,optional=True)
        c.require(saved is not None and saved['witness']==state['witness']['raw'].hex(),'EPISODE_NOT_COMMITTED')

    def collect(self,identifier,records,state_request,state_response):
        """Commit exact activation prefix and loss summary before ACK exists."""
        c.require(type(records) in (list,tuple) and len(records)<=2,'LEDGER_LIMIT')
        with self.journal._transaction():
            row=self.row(identifier)
            checked=self._checked_response(state_request,state_response)
            valid=(checked is not None and state_request.opcode==w.Opcode.STATUS and checked['status']==0 and 'state' in checked)
            if valid:
                valid=self._state_record(row,state_request,checked)
            else:
                self._latch_conflict(row,'STATUS_ASSOCIATION',state_request,state_response)
            state=checked['state'] if valid else None
            if valid and state['flags']&128 and not state['flags']&6:
                key=self._episode_key(state)
                previous=self._read('sd_episodes','deployment_id=? AND episode_key=?',(identifier,key),1536,optional=True)
                if previous is None:
                    count=self.db.execute('SELECT count(*) FROM sd_episodes WHERE deployment_id=?',(identifier,)).fetchone()[0]
                    c.require(count<row['request']['limits']['episodeRecords'],'EPISODE_CAPACITY')
                    episode={'state':self.envelope(state_request,checked),'witness':state['witness']['raw'].hex()}
                    c.require(len(canonical(episode))<=1536,'RECORD_LIMIT')
                    self.db.execute('INSERT INTO sd_episodes VALUES(?,?,?)',(identifier,key,canonical(episode)))
                elif previous['witness']!=state['witness']['raw'].hex():
                    valid=self._latch_conflict(row,'EPISODE_CONFLICT',state_request,checked)
            for request,response in records:
                if not valid:
                    break
                decoded=self._checked_response(request,response)
                if decoded is None or request.opcode!=w.Opcode.STATUS or decoded['status']!=0 or 'activation' not in decoded:
                    valid=self._latch_conflict(row,'ACTIVATION_ASSOCIATION',request,response);break
                if request.reference!=self.reference(row):
                    valid=self._latch_conflict(row,'IDENTITY',request,decoded);break
                prefix=decoded['prefix'];event=decoded['activation'];number=event['activation_id']
                if prefix['mutation_sequence']!=row['mutationSequence']:
                    valid=self._latch_conflict(row,'FOREIGN_MUTATION',request,decoded);break
                if not (row['acknowledged']<number<=row['highWater'] and prefix['ack_watermark']<=row['collected'] and
                        event['evidence'] in (0,5) and event['verification']==0):
                    valid=self._latch_conflict(row,'ACTIVATION_CONFLICT',request,decoded);break
                old=self._read('sd_activations','deployment_id=? AND number=?',(identifier,number),1024,optional=True)
                if old is not None:
                    previous=self.decode(old['envelope'])['activation']
                    immutable=('activation_id','dispatch_tick','demand_sequence','demand_value','demand_age','previous_output','requested_output')
                    consistent=(previous['raw']==event['raw'] or previous['state']==1) and all(previous[key]==event[key] for key in immutable)
                    consistent=consistent and event['feedback_sequence']>=previous['feedback_sequence']
                    if previous['feedback_acquired_at']!=w.ABSENT_TIME:
                        consistent=consistent and event['feedback_acquired_at']!=w.ABSENT_TIME and event['feedback_acquired_at']>=previous['feedback_acquired_at']
                    if event['feedback_sequence']==previous['feedback_sequence']:
                        consistent=consistent and all(event[key]==previous[key] for key in ('feedback_acquired_at','feedback_value','evidence_quality'))
                    if not consistent:
                        valid=self._latch_conflict(row,'ACTIVATION_CONFLICT',request,decoded);break
                if event['state']==5:
                    row['effectUnknown']=row['recoveryRequired']=True
                saved={'envelope':self.envelope(request,decoded),'state':event['state'],'raw':event['raw'].hex()}
                encoded=canonical(saved);c.require(len(encoded)<=1024,'RECORD_LIMIT')
                if old is None:
                    self.db.execute('INSERT INTO sd_activations VALUES(?,?,?)',(identifier,number,encoded))
                    self.db.execute('INSERT INTO sd_activation_versions VALUES(?,?,0,?)',(identifier,number,encoded))
                else:
                    self._write('sd_activations','deployment_id=? AND number=?',(identifier,number),saved,1024)
                    first=self._read('sd_activation_versions','deployment_id=? AND number=? AND version=0',(identifier,number),1024)
                    final=self._read('sd_activation_versions','deployment_id=? AND number=? AND version=1',(identifier,number),1024,optional=True)
                    if event['state']!=1 and first['raw']!=saved['raw']:
                        if final is None:
                            self.db.execute('INSERT INTO sd_activation_versions VALUES(?,?,1,?)',(identifier,number,encoded))
                        elif final['raw']!=saved['raw']:
                            valid=self._latch_conflict(row,'ACTIVATION_CONFLICT',request,decoded);break
            upto=row['collected']
            while valid and upto<row['highWater']:
                record=self._read('sd_activations','deployment_id=? AND number=?',(identifier,upto+1),1024,optional=True)
                if record is None or record['state'] in (1,5):
                    break
                event=self.decode(record['envelope'])['activation']
                c.require(event['verification']!=3,'DISPUTED')
                if event['state']==4:
                    if not (state['flags']&128 and not state['flags']&6 and state['lifecycle'] in (4,5)):
                        break
                    self._require_episode(row,state)
                else:
                    c.require(event['state'] in (2,3),'ACTIVATION_STATE')
                upto+=1
            row['collected']=upto
            self._save(row);self._checkpoint('before_collection_commit',copy.deepcopy(row))
        self._checkpoint('after_collection_commit',copy.deepcopy(row))
        c.require(valid,'EVIDENCE_CONFLICT')
        return self.row(identifier)

    def reconcile_status(self,identifier,request,response):
        """Read-only endpoint evidence resolves acceptance; never redispatch."""
        with self.journal._transaction():
            row=self.row(identifier)
            checked=self._checked_response(request,response)
            valid=(checked is not None and request.opcode==w.Opcode.STATUS and checked['status']==0 and 'state' in checked)
            if valid:
                valid=self._state_record(row,request,checked)
            else:
                self._latch_conflict(row,'STATUS_ASSOCIATION',request,response)
            resolved=valid
            if valid:
                if row['openState']=='possible':
                    row['openState']='accepted';row['openReply']=self.envelope(request,checked)
                elif row['openState']!='accepted':
                    valid=resolved=self._latch_conflict(row,'OPEN_RESPONSE_ASSOCIATION',request,checked)
                for item in self.pending(identifier):
                    state=checked['state'];body=bytes.fromhex(item['body'])
                    if item['state']=='possible' and state['mutation_sequence']==item['endpointSequence'] and state['last_comparison']==body[:2]+body[48:66]:
                        item['state']='accepted';item['reply']=self.envelope(request,checked)
                        self._write('sd_mutations','deployment_id=? AND number=?',(identifier,item['number']),item,1536)
                    else:
                        resolved=False
                if resolved:
                    row['transportUncertain']=row['sequenceUncertain']=False
                else:
                    row['transportUncertain']=row['sequenceUncertain']=True
                # Recovery does not erase driver uncertainty or contradictions.
                row['recoveryRequired']=not resolved or row['effectUnknown'] or row['disputed']
            self._save(row)
        c.require(valid,'EVIDENCE_CONFLICT')
        return self.row(identifier)

    def reconcile_retirement(self,identifier,request,response,capabilities_request,capabilities_response):
        """Join one exact possibly sent RETIRE to same-boot empty evidence.

        An OLD_OR_FORGOTTEN response alone never releases claims. The pre-send
        terminal episode/full committed ACK and exact retained retirement body
        must still exist, with unchanged endpoint fences and namespace.
        """
        with self.journal._transaction():
            row=self.row(identifier)
            pending=self.pending(identifier)
            c.require(len(pending)==1 and pending[0]['opcode']==w.Opcode.RETIRE and
                      pending[0]['state']=='possible','RETIREMENT_UNRESOLVED')
            item=pending[0];self._retirement_ready(row,item)
            forgotten=self._checked_response(request,response)
            caps=self._checked_response(capabilities_request,capabilities_response)
            reference=self.reference(row)
            valid=(forgotten is not None and caps is not None and request.opcode==w.Opcode.STATUS and
                   request.frame.payload==w.status(reference) and
                   forgotten['status']==w.Status.OLD_OR_FORGOTTEN and forgotten['prefix']['revision']==0 and
                   forgotten['session']==int(row['mapping']['boot']) and
                   capabilities_request.frame.payload==w.describe(1) and caps['status']==0 and
                   'capabilities' in caps and caps['session']==int(row['mapping']['boot']))
            if valid:
                prefix=forgotten['prefix'];observed=caps['capabilities']
                valid=((prefix['generation'],prefix['handle'],prefix['standing_number'],prefix['intent_digest'])==
                       (reference.generation,reference.handle,reference.standing_number,reference.intent_digest) and
                       observed['slot_kind']==0 and observed['standing_high_water']==reference.standing_number and
                       list(observed['fence_floors'])==row['mapping']['fences'] and
                       observed['epochs']==tuple(self.installation['endpoint']['epochs']))
            if valid:
                item['state']='accepted'
                item['reply']=self.envelope(request,forgotten)
                item['retirementEvidence']=self.envelope(capabilities_request,caps)
                self._write('sd_mutations','deployment_id=? AND number=?',(identifier,item['number']),item,1536)
                row['retired']=True;row['transportUncertain']=row['sequenceUncertain']=row['recoveryRequired']=False
                self.db.execute('DELETE FROM claims WHERE operation_id=?',(identifier,))
            else:
                self._latch_conflict(row,'RETIREMENT_ASSOCIATION',request,response)
            self._save(row)
        c.require(valid,'RETIREMENT_UNRESOLVED')
        return self.row(identifier)

    def reserve_revoke(self,context,identifier):
        """One separately retained common loss outbox; no standing sequence."""
        c.require(self.db.in_transaction,'TRANSACTION_REQUIRED')
        row=self.row(identifier);self.access(context,row)
        self.policy.authorize(context,'cancel',self.installation['instanceId'])
        c.require(not row['retired'],'RETIRED')
        if row['revoke'] is not None:
            return copy.deepcopy(row['revoke'])
        payload=w.revoke(row['mapping']['generation'],row['mapping']['handle'])
        request=self.reserve_frame(payload)
        c.require(request.frame.session==int(row['mapping']['boot']),'BOOT_CHANGED')
        item={'body':payload.hex(),'tx':request.frame.sequence,'state':'prepared','reply':None}
        row['revoke']=item;self._save(row)
        self._checkpoint('before_revoke_commit',copy.deepcopy(item))
        return item

    def mark_revoke_possible(self,identifier):
        with self.journal._transaction():
            row=self.row(identifier);item=row['revoke']
            c.require(item is not None and item['state']=='prepared','OUTBOX_STATE')
            item['state']='possible'
            row['transportUncertain']=row['recoveryRequired']=True
            row['everPossiblyActed']=True
            self._save(row);self._checkpoint('before_revoke_handoff_commit',copy.deepcopy(item))
        self._checkpoint('after_revoke_handoff_commit',copy.deepcopy(item))
        return w.Request(Frame(1,0,int(row['mapping']['boot']),item['tx'],bytes.fromhex(item['body'])))

    def record_revoke(self,identifier,request,response):
        with self.journal._transaction():
            row=self.row(identifier);item=row['revoke']
            c.require(item is not None and item['state']=='possible','OUTBOX_STATE')
            expected=w.Request(Frame(1,0,int(row['mapping']['boot']),item['tx'],bytes.fromhex(item['body'])))
            checked=self._checked_response(request,response,expected)
            valid=checked is not None
            if checked is None:
                self._latch_conflict(row,'REVOKE_RESPONSE_ASSOCIATION',request,response)
            elif checked['status']==0:
                if 'state' not in checked:
                    valid=self._latch_conflict(row,'REVOKE_RESPONSE_ASSOCIATION',request,checked)
                else:
                    valid=self._state_record(row,request,checked)
            if valid:
                item['state']='accepted' if checked['status']==0 else 'refused'
                item['reply']=self.envelope(request,checked)
            # Common invalidation proves neither standing mutation acceptance
            # nor physical settlement. Leave pending/effect/recovery facts.
            row['recoveryRequired']=True
            self._save(row)
        c.require(valid,'EVIDENCE_CONFLICT')
        return self.row(identifier)

    def _confirmed_route_counters(self):
        """Allocated but never-handed-off OPEN numbers/fences remain gaps."""
        high=0;fences=[0]*8
        for (identifier,) in self.db.execute('SELECT id FROM sd_deployments ORDER BY id LIMIT 17').fetchall():
            row=self.row(identifier)
            if row['openState']=='accepted':
                high=max(high,row['mapping']['standingNumber'])
                fences=[max(a,b) for a,b in zip(fences,row['mapping']['fences'])]
        return high,fences

    def record_transport_conflict(self,identifier,request,frame):
        """Retain a real received frame rejected before semantic store ingress."""
        with self.journal._transaction():
            row=self.row(identifier)
            c.require(not row['retired'],'RETIRED')
            c.require(type(request) is w.Request and request.frame.session in (0,int(row['mapping']['boot'])),
                      'TRANSPORT_ASSOCIATION')
            c.require(request.reference is None or request.reference==self.reference(row),'TRANSPORT_ASSOCIATION')
            response={'raw':frame.payload,'session':frame.session,'response_sequence':frame.sequence}
            self._latch_conflict(row,'TRANSPORT_RESPONSE_ASSOCIATION',request,response)
            row['sequenceUncertain']=True
            self._save(row)
        return self.row(identifier)

    def abandon_prepared_mutation(self,context,identifier,number,request,response):
        """Explicit settlement proves never possible; never sends this body."""
        with self.journal._transaction():
            row=self.row(identifier);self.access(context,row)
            self.policy.authorize(context,'cancel',self.installation['instanceId'])
            item=self.mutation(identifier,number)
            if item['state']=='never_handed_off':
                return item
            c.require(item['state']=='prepared' and not row['retired'],'NEVER_HANDED_OFF_REQUIRED')
            c.require([pending['number'] for pending in self.pending(identifier)]==[number],'SEQUENCE_UNRESOLVED')
            checked=self._checked_response(request,response)
            valid=(checked is not None and request.frame.payload==w.status(self.reference(row)) and
                   checked['status']==0 and 'state' in checked and
                   checked['state']['mutation_sequence']==row['mutationSequence'] and
                   item['endpointSequence']==row['mutationSequence']+1)
            if valid:
                valid=self._state_record(row,request,checked)
            else:
                self._latch_conflict(row,'NEVER_HANDED_OFF_ASSOCIATION',request,response)
            if valid:
                item['state']='never_handed_off';item['settlement']='durable-prepared-never-possible'
                item['reply']=self.envelope(request,checked)
                self._write('sd_mutations','deployment_id=? AND number=?',(identifier,number),item,1536)
                row['sequenceUncertain']=False
                row['transportUncertain']=bool(row['revoke'] and row['revoke']['state']=='possible')
                row['recoveryRequired']=row['effectUnknown'] or row['disputed'] or row['revoke'] is not None
            self._save(row);self._checkpoint('before_never_handed_off_commit',copy.deepcopy(item))
        c.require(valid,'NEVER_HANDED_OFF_UNRESOLVED')
        return self.mutation(identifier,number)

    def abandon_prepared_open(self,context,identifier,request,response,caps_request,caps_response):
        """Close only a never-possible deployment; retain key and all floors."""
        with self.journal._transaction():
            row=self.row(identifier);self.access(context,row)
            self.policy.authorize(context,'cancel',self.installation['instanceId'])
            if row['openState']=='never_handed_off':
                return row
            c.require(row['openState']=='prepared' and not row['everPossiblyActed'] and
                      not row['retired'] and row['openReply'] is None and row['revoke'] is None and not self.pending(identifier),
                      'NEVER_HANDED_OFF_REQUIRED')
            checked=self._checked_response(request,response);descriptor=self._checked_response(caps_request,caps_response)
            high,fences=self._confirmed_route_counters();route=self.route()
            valid=(checked is not None and descriptor is not None and request.frame.payload==w.status(self.reference(row)) and
                   checked['status']==w.Status.NOT_SEEN and checked['prefix']['revision']==0 and
                   caps_request.frame.payload==w.describe(1) and descriptor['status']==0 and 'capabilities' in descriptor)
            if valid:
                caps=descriptor['capabilities'];ref=self.reference(row);prefix=checked['prefix']
                valid=((prefix['generation'],prefix['handle'],prefix['standing_number'],prefix['intent_digest'])==
                       (ref.generation,ref.handle,ref.standing_number,ref.intent_digest) and
                       descriptor['session']==int(row['mapping']['boot']) and caps['slot_kind']==0 and
                       caps['standing_high_water']==high and list(caps['fence_floors'])==fences and caps['finite_high_water']==0 and
                       caps['generation']==route['generation'] and caps['handle']==route['handle'] and
                       caps['context_digest'].hex()==route['contextDigest'] and not row['disputed'] and not row['effectUnknown'])
            if valid:
                row['openState']='never_handed_off';row['openReply']=self.envelope(request,checked)
                row['lastStatus']=self.envelope(caps_request,descriptor)
                row['retired']=True;row['recoveryRequired']=row['transportUncertain']=row['sequenceUncertain']=False
                self.db.execute('DELETE FROM claims WHERE operation_id=?',(identifier,))
            else:
                self._latch_conflict(row,'NEVER_HANDED_OFF_ASSOCIATION',request,response)
            self._save(row);self._checkpoint('before_never_handed_off_open_commit',copy.deepcopy(row))
        c.require(valid,'NEVER_HANDED_OFF_UNRESOLVED')
        return self.row(identifier)

    def conflicts(self,identifier):
        with self.journal._mutex:
            return [self._read('sd_conflicts','deployment_id=? AND number=?',(identifier,n),1536)
                    for (n,) in self.db.execute('SELECT number FROM sd_conflicts WHERE deployment_id=? ORDER BY number LIMIT 16',
                                                (identifier,)).fetchall()]
