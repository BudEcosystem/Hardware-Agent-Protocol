"""Original fixed controls; source-only until the parent reviews the launcher.

All endpoint calls use the unchanged installed native image. Private hooks inject
owner exceptions or a SQLite-call exception; they are not application inputs.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'project'),str(HERE/'project/tests'),str(HERE/'owner')]
from guardian import Guardian
from standing_host_fixture import Fixture,OWNER
from hms.journal import JournalError
from hms.standing_endpoint import StandingHost
from hms.standing_store import StandingStore
from hms.standing_wire import Opcode
from hms.standing_capacity import check as capacity_check
from hms.contracts import canonical
from hms import standing_contracts as c

checks=0
FINAL_DESTINATION=None
FINAL_REPORT=None


def require(value,message='boundary assertion'):
    global checks
    checks+=1
    if not value:raise AssertionError(message+' #'+str(checks))


def refused(code,action,*args,**kwargs):
    try:action(*args,**kwargs)
    except JournalError as error:require(error.code==code,(code,error.code))
    else:raise AssertionError('Expected '+code)


def storage_failure(action,*args,**kwargs):
    try:action(*args,**kwargs)
    except sqlite3.OperationalError as error:require(str(error)=='original controlled storage boundary')
    else:raise AssertionError('Expected original storage exception')


def save(path,value):
    data=canonical(value);require(len(data)<=1024*1024,'bounded evidence')
    temporary=Path(str(path)+'.pending')
    with temporary.open('wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class ProbeHost(StandingHost):
    hook=None
    trace=None
    def _checkpoint(self,phase,value=None):
        if self.trace is None:self.trace=[]
        if phase=='before_exchange':
            self.trace.append({'direction':'request','session':value.frame.session,
                'sequence':value.frame.sequence,'raw':value.frame.payload.hex()})
        elif phase=='after_exchange':
            self.trace.append({'direction':'response','session':value['session'],
                'sequence':value['response_sequence'],'raw':value['raw'].hex()})
        hook=self.hook
        if hook is not None:hook(phase,value)


class ProbeStore(StandingStore):
    hook=None
    def _checkpoint(self,phase,value=None):
        hook=self.hook
        if hook is not None:hook(phase,value)


class TraceFixture(Fixture):
    def __init__(self,*args,**kwargs):
        self.retained_trace=[]
        super().__init__(*args,**kwargs)
    def attach(self,*,create):
        super().attach(create=create)
        self.host.trace=self.retained_trace


class CommitFault:
    """One synchronous call boundary; not a claim to emulate disk/power failure."""
    def __init__(self,connection,after):self.connection=connection;self.after=after;self.armed=True
    def __getattr__(self,name):return getattr(self.connection,name)
    def execute(self,sql,*args):
        if sql=='COMMIT' and self.armed:
            self.armed=False
            if self.after:self.connection.execute(sql,*args)
            raise sqlite3.OperationalError('original controlled storage boundary')
        return self.connection.execute(sql,*args)


class RollbackFault:
    def __init__(self,connection):self.connection=connection;self.armed=True
    def __getattr__(self,name):return getattr(self.connection,name)
    def execute(self,sql,*args):
        if sql=='ROLLBACK' and self.armed:
            self.armed=False
            raise sqlite3.OperationalError('original controlled storage boundary')
        return self.connection.execute(sql,*args)


def once(owner,phase,callback):
    def hook(observed,value):
        if observed==phase:
            owner.hook=None;callback(value)
    owner.hook=hook


def injected(_):raise JournalError('CONTROL_PREPARED_BOUNDARY')


def snapshot(f):return {str(n):f.snapshot(n) for n in range(27)}


def claims(f,identifier):
    return [r[0] for r in f.journal._db.execute('SELECT resource FROM claims WHERE operation_id=? ORDER BY resource',(identifier,))]


def retained(f,identifier):require(claims(f,identifier)==['atom:demand','atom:output','atom:slot'])


def opened(f,request=None):
    row=f.host.prepare(OWNER,f.request() if request is None else request)
    require(row['openState']=='prepared')
    row=f.host.open(OWNER,row['id']);require(row['openState']=='accepted')
    f.cycle(0);return row['id']


def active(f,request=None):
    identifier=opened(f,request);f.host.mutate(OWNER,identifier,'start',Opcode.START)
    require(f.snapshot(5)==2);return identifier


def transition(f):
    identifier=active(f);f.command(3,35000);f.cycle(12)
    require(f.snapshot(0)==f.snapshot(2)==1);f.cycle(24)
    return identifier


def retire(f,identifier,at):
    f.host.mutate(OWNER,identifier,'stop',Opcode.STOP);f.cycle(at)
    row=f.host.collect(OWNER,identifier)
    require(f.store.state(row)['lifecycle']==5)
    row=f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
    require(row['retired'] and claims(f,identifier)==[])


def expired_qualification(f):
    once(f.store,'before_deployment_commit',lambda _:setattr(f.producer._held,'expires',0))
    refused('STANDING_QUALIFICATION_LEASE_UNAVAILABLE',f.host.prepare,OWNER,f.request())
    require(f.journal._db.execute('SELECT count(*) FROM sd_deployments').fetchone()[0]==0)
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone() and f.snapshot(9)==0)
    identifier=opened(f);retire(f,identifier,5)


def driver_expiry_after_possible(f):
    row=f.host.prepare(OWNER,f.request());identifier=row['id']
    once(f.store,'after_open_handoff_commit',lambda _:setattr(f.driver,'_lease',(0,0,())))
    refused('STANDING_DRIVER_LEASE_UNAVAILABLE',f.host.open,OWNER,identifier)
    require(f.store.row(identifier)['openState']=='possible' and f.snapshot(9)==0)
    f.reopen();before=f.snapshot(22)
    require(f.host.open(OWNER,identifier)['openState']=='possible' and f.snapshot(22)==before)
    refused('STANDING_RECONCILIATION_UNRESOLVED',f.host.reconcile,OWNER,identifier)
    retained(f,identifier)


def installed_context_change(f):
    identifier=active(f);before=f.snapshot(13)
    original=copy.deepcopy(f.policy.installation)
    f.policy.installation['generations']['revision']=2
    try:
        require(f.host.prepare(OWNER,f.request())['id']==identifier)
        refused('STANDING_INSTALLATION_CHANGED',f.host.mutate,OWNER,identifier,'new-renew',Opcode.RENEW)
    finally:f.policy.installation=original
    require(f.snapshot(13)==before);retained(f,identifier);retire(f,identifier,5)


def boot_after_acceptance(f):
    identifier=active(f);before=f.store.row(identifier);f.command(15,2)
    refused('STANDING_BOOT_OR_RESPONSE_REPLAY',f.host.status,OWNER,identifier)
    row=f.store.row(identifier)
    require(row['disputed'] and row['effectUnknown'] and not row['retired'])
    require(row['mapping']==before['mapping'] and row['requestDigest']==before['requestDigest'])
    seq=f.snapshot(22);require(f.host.prepare(OWNER,f.request())['id']==identifier)
    require(f.snapshot(22)==seq and f.snapshot(0)==0);retained(f,identifier)


def retired_without_terminal_proof(f):
    identifier=active(f)
    refused('STANDING_RETIRE_FORBIDDEN',f.host.mutate,OWNER,identifier,'premature',Opcode.RETIRE)
    require(f.store.pending(identifier)==[] and f.snapshot(13)==1);retained(f,identifier)
    retire(f,identifier,5)


def refused_sequence_original_key(f):
    identifier=opened(f)
    # Advancing only the private virtual clock makes the installed samples stale;
    # START is definitively refused without accepting its mutation sequence.
    f.command(1,101)
    f.host.mutate(OWNER,identifier,'refused-start',Opcode.START)
    item=f.store.mutation(identifier,1)
    require(item['state']=='refused' and f.snapshot(13)==0)
    before=f.snapshot(22)
    require(f.host.mutate(OWNER,identifier,'refused-start',Opcode.START)==item)
    require(f.snapshot(22)==before)
    refused('STANDING_REUSE_ORIGINAL_CONTROL_KEY',f.host.mutate,OWNER,identifier,'false-novelty',Opcode.START)
    require(f.journal._db.execute('SELECT count(*) FROM sd_mutations').fetchone()[0]==1)
    # Fresh observations do not rewrite the retained refused original. Explicit
    # STOP has a different body and may use the unconsumed endpoint sequence.
    f.cycle(110);retire(f,identifier,120)
    require(f.store.mutation(identifier,1)==item)


def automatic_ack_revision_refusal(f):
    identifier=transition(f)
    old=f.snapshot(13)
    def race(item):
        if item['opcode']!=int(Opcode.ACK):raise AssertionError('Expected ACK reservation')
        # The endpoint's lease expires after reservation. This asynchronous loss
        # advances revision but does not consume the reserved mutation sequence.
        f.cycle(1000)
    once(f.host,'after_mutation_reservation_commit',race)
    row=f.host.collect(OWNER,identifier)
    item=f.store.mutation(identifier,2)
    require(item['state']=='refused' and item['opcode']==int(Opcode.ACK))
    require(row['collected']==1 and row['acknowledged']==0 and f.snapshot(13)==old)
    original=copy.deepcopy(item)
    # An explicit fresh collect commits terminal evidence and admits a new body
    # at the current revision, retaining the refused original and its exact key.
    row=f.host.collect(OWNER,identifier)
    require(row['acknowledged']==1 and f.snapshot(13)==old+1)
    current=f.store.mutation(identifier,3)
    require(current['hostKey']!=original['hostKey'] and current['endpointSequence']==original['endpointSequence'])
    require(current['body']!=original['body'] and f.store.mutation(identifier,2)==original)
    retire(f,identifier,1010)


def dispute_retention(f):
    identifier=opened(f)
    originals=[]
    for number in range(17):
        f.command(16,(1<<8)|int(Opcode.STATUS))
        refused('STANDING_EVIDENCE_CONFLICT',f.host.status,OWNER,identifier)
        rows=f.journal._db.execute('SELECT document FROM sd_conflicts ORDER BY number').fetchall()
        require(len(rows)==min(number+1,16))
        if number==15:originals=[bytes(r[0]) for r in rows]
        if number==16:require([bytes(r[0]) for r in rows]==originals)
    f.reopen();row=f.host.reconcile(OWNER,identifier)
    require(row['disputed'] and row['effectUnknown'] and row['recoveryRequired'])
    refused('STANDING_RECOVERY_REQUIRED',f.host.mutate,OWNER,identifier,'start',Opcode.START)
    f.host.mutate(OWNER,identifier,'stop',Opcode.STOP);f.cycle(5)
    row=f.host.collect(OWNER,identifier,acknowledge=False)
    require(row['disputed'] and row['effectUnknown'])
    refused('STANDING_EFFECT_UNRESOLVED',f.host.mutate,OWNER,identifier,'retire',Opcode.RETIRE)
    retained(f,identifier)


def storage_boundary(f,phase,after):
    identifier=None
    if phase=='prepare':pass
    elif phase=='open':identifier=f.host.prepare(OWNER,f.request())['id']
    elif phase=='collection':identifier=transition(f)
    elif phase=='retire':
        identifier=opened(f);f.host.mutate(OWNER,identifier,'stop',Opcode.STOP);f.cycle(5)
        f.host.collect(OWNER,identifier)
    else:raise AssertionError(phase)
    connection=f.journal._db
    def install(_):f.journal._db=CommitFault(connection,after)
    if phase=='prepare':once(f.store,'before_deployment_commit',install);action=lambda:f.host.prepare(OWNER,f.request())
    elif phase=='open':once(f.store,'before_open_handoff_commit',install);action=lambda:f.host.open(OWNER,identifier)
    elif phase=='collection':once(f.store,'before_collection_commit',install);action=lambda:f.host.collect(OWNER,identifier)
    else:
        def response(observed,value):
            if observed=='after_exchange' and value['opcode']==Opcode.RETIRE:
                f.host.hook=None;install(None)
        f.host.hook=response;action=lambda:f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
    try:storage_failure(action)
    finally:f.journal._db=connection
    require(not connection.in_transaction)
    if phase=='prepare':
        count=connection.execute('SELECT count(*) FROM sd_deployments').fetchone()[0]
        require(count==int(after))
        if after:identifier=connection.execute('SELECT id FROM sd_deployments').fetchone()[0]
        require(f.snapshot(9)==0)
    elif phase=='open':require(f.store.row(identifier)['openState']==('possible' if after else 'prepared') and f.snapshot(9)==0)
    elif phase=='collection':require(f.store.row(identifier)['collected']==int(after) and f.snapshot(11)==0)
    else:require(f.store.row(identifier)['retired']==after and f.snapshot(5)==0)
    f.reopen()
    if phase=='prepare':
        if after:f.host.abandon_prepared(OWNER,identifier)
        else:identifier=opened(f);retire(f,identifier,5)
    elif phase=='open':
        if after:
            before=f.snapshot(22);f.host.open(OWNER,identifier);require(f.snapshot(22)==before)
            refused('STANDING_RECONCILIATION_UNRESOLVED',f.host.reconcile,OWNER,identifier);retained(f,identifier)
        else:f.host.abandon_prepared(OWNER,identifier)
    elif phase=='collection':
        f.host.reconcile(OWNER,identifier);row=f.host.collect(OWNER,identifier)
        require(row['collected']==row['acknowledged']==1);retire(f,identifier,40)
    else:
        row=f.host.reconcile(OWNER,identifier)
        require(row['retired'] and claims(f,identifier)==[])
    require(f.snapshot(0)==(1 if phase=='collection' else 0))


def mutation_capacity(f):
    identifier=opened(f)
    # Public reserve/explicit abandonment retain119 original keys; each fixed
    # owner checkpoint proves no possible handoff. No direct SQL creates records.
    for number in range(119):
        key='never-start:'+str(number)
        once(f.host,'after_mutation_reservation_commit',injected)
        refused('CONTROL_PREPARED_BOUNDARY',f.host.mutate,OWNER,identifier,key,Opcode.START)
        item=f.host.abandon_prepared(OWNER,identifier,mutation_key=key)
        require(item['state']=='never_handed_off' and item['endpointSequence']==1)
    f.host.mutate(OWNER,identifier,'start',Opcode.START)
    require(f.snapshot(13)==1 and f.snapshot(0)==0)
    refused('STANDING_MUTATION_CAPACITY',f.host.mutate,OWNER,identifier,'ordinary-overflow',Opcode.RENEW)
    f.command(3,35000);f.cycle(12);f.cycle(24)
    row=f.host.collect(OWNER,identifier,acknowledge=False)
    require(row['collected']==1 and row['acknowledged']==0)
    for number in range(6):
        key='never-stop:'+str(number)
        once(f.host,'after_mutation_reservation_commit',injected)
        refused('CONTROL_PREPARED_BOUNDARY',f.host.mutate,OWNER,identifier,key,Opcode.STOP)
        f.host.abandon_prepared(OWNER,identifier,mutation_key=key)
    require(f.journal._db.execute('SELECT count(*) FROM sd_mutations').fetchone()[0]==126)
    refused('STANDING_LOSS_CONTINUATION_RESERVED',f.host.mutate,OWNER,identifier,'stop-overflow',Opcode.STOP)
    # Separate bounded common loss outbox remains available when standing loss
    # identities are exhausted. Its accepted receipt permits ACK+RETIRE only.
    f.host.revoke(OWNER,identifier);f.cycle(40)
    row=f.host.collect(OWNER,identifier)
    require(row['acknowledged']==1 and f.store.mutation(identifier,127)['opcode']==int(Opcode.ACK))
    row=f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
    require(row['retired'] and claims(f,identifier)==[])
    require(f.journal._db.execute('SELECT count(*) FROM sd_mutations').fetchone()[0]==128)
    require(f.store.mutation(identifier,128)['state']=='accepted')
    before=f.snapshot(22);original=f.host.mutate(OWNER,identifier,'never-start:0',Opcode.START)
    require(original['state']=='never_handed_off' and f.snapshot(22)==before)


def episode_capacity(f):
    identifier=active(f);tick=10
    for number in range(24):
        f.host.mutate(OWNER,identifier,'suspend:'+str(number),Opcode.SUSPEND);f.cycle(tick)
        row=f.host.collect(OWNER,identifier)
        require(f.store.state(row)['lifecycle']==4)
        require(f.journal._db.execute('SELECT count(*) FROM sd_episodes').fetchone()[0]==number+1)
        if number<23:
            f.host.mutate(OWNER,identifier,'resume:'+str(number),Opcode.RESUME);f.cycle(tick+10)
            f.host.mutate(OWNER,identifier,'start:'+str(number),Opcode.START)
        tick+=30
    before=f.snapshot(13)
    refused('STANDING_EPISODE_CAPACITY',f.host.mutate,OWNER,identifier,'resume-overflow',Opcode.RESUME)
    require(f.snapshot(13)==before)
    retire(f,identifier,tick)
    require(f.journal._db.execute('SELECT count(*) FROM sd_episodes').fetchone()[0]==24)


def activation_capacity(f):
    identifier=active(f)
    def pulse(tick):
        # Three actual native polls at one nondecreasing virtual tick complete
        # the installed demand/feedback/evaluate phases without a wall sleep.
        for _ in range(3):f.command(1,tick)
    tick=12
    # Two short, explicitly suspended ON intervals retain pending+interrupted
    # versions and save enough commanded-ON budget for the complete100 records.
    for number in range(1,3):
        f.command(3,35000);pulse(tick)
        row=f.host.collect(OWNER,identifier,acknowledge=False)
        require(row['highWater']==number and row['collected']==number-1)
        f.host.mutate(OWNER,identifier,'short-suspend:'+str(number),Opcode.SUSPEND)
        f.cycle(tick+1);row=f.host.collect(OWNER,identifier)
        require(row['acknowledged']==number and f.snapshot(2)==0)
        f.host.mutate(OWNER,identifier,'short-resume:'+str(number),Opcode.RESUME)
        pulse(tick+13);f.host.mutate(OWNER,identifier,'short-start:'+str(number),Opcode.START)
        tick+=23
    for number in range(3,101):
        f.command(3,35000 if number%2 else 10000);pulse(tick)
        row=f.host.collect(OWNER,identifier)
        require(row['highWater']==number and row['acknowledged']==number-1)
        require(f.snapshot(0)==number)
        if number==80:f.host.mutate(OWNER,identifier,'capacity-renew',Opcode.RENEW)
        tick+=10
    pulse(tick);row=f.host.collect(OWNER,identifier)
    require(row['collected']==row['acknowledged']==100)
    require(f.journal._db.execute('SELECT count(*) FROM sd_activations').fetchone()[0]==100)
    require(f.journal._db.execute('SELECT count(*) FROM sd_activation_versions').fetchone()[0]==200)
    require(f.snapshot(24)<500 and f.snapshot(2)==0)
    f.command(3,35000);pulse(tick+10);f.cycle(tick+11)
    row=f.host.collect(OWNER,identifier)
    require(f.snapshot(0)==100 and row['highWater']==100 and f.store.state(row)['lifecycle']==5)
    row=f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
    require(row['retired'] and claims(f,identifier)==[])


def retained_keys(f):
    original=[]
    for number in range(16):
        request=f.request('retained:'+str(number))
        row=f.host.prepare(OWNER,request);identifier=row['id']
        row=f.host.abandon_prepared(OWNER,identifier)
        require(row['retired'] and row['openState']=='never_handed_off' and claims(f,identifier)==[])
        original.append((request,identifier,canonical(row)))
    refused('STANDING_CAPACITY',f.host.prepare,OWNER,f.request('seventeenth'))
    require(f.journal._db.execute('SELECT count(*) FROM sd_deployments').fetchone()[0]==16)
    require(f.journal._db.execute('SELECT count(*) FROM resource_owners').fetchone()[0]==16)
    f.policy.enabled=False;f.producer.enabled=False;f.driver.enabled=False
    before=f.snapshot(22)
    for request,identifier,wire in original:
        require(canonical(f.host.prepare(OWNER,request))==wire)
        changed=copy.deepcopy(request);changed['limits']['mutationRecords']=127
        refused('STANDING_KEY_CONFLICT',f.host.prepare,OWNER,changed)
    require(f.snapshot(22)==before and f.snapshot(0)==0)
    require(f.store.route()['standingFloor']==16 and f.store.route()['fences'][:2]==[16,16])
    f.policy.enabled=f.producer.enabled=f.driver.enabled=True
    finite=[]
    for number in range(16):
        with f.policy.hold_image():operation=f.journal.submit(OWNER,f.finite_request('finite:'+str(number)))
        f.journal.request_cancel(OWNER,operation['id']);finite.append(operation['id'])
    with f.policy.hold_image():
        refused('STANDING_LOGICAL_CAPACITY',f.journal.submit,OWNER,f.finite_request('finite:seventeenth'))
    require(f.journal._db.execute('SELECT count(*) FROM resource_owners').fetchone()[0]==32)
    require(f.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]==16)
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    for identifier in finite:require(f.journal.status(OWNER,identifier)['state']=='canceled')


def rollback_exception(f):
    identifier=opened(f);connection=f.journal._db
    def fail(_):
        f.journal._db=RollbackFault(connection)
        raise sqlite3.OperationalError('original controlled storage boundary')
    once(f.store,'before_mutation_commit',fail)
    try:
        storage_failure(f.host.mutate,OWNER,identifier,'rolled-back',Opcode.START)
        require(connection.in_transaction and f.snapshot(13)==0 and f.snapshot(0)==0)
        refused('POLICY_REENTRANCY',f.host.mutate,OWNER,identifier,'blocked-until-close',Opcode.START)
    finally:f.journal._db=connection
    f.reopen()
    require(f.journal._db.execute('SELECT count(*) FROM sd_mutations').fetchone()[0]==0)
    f.host.reconcile(OWNER,identifier);retire(f,identifier,5)


def sqlite_page_exhaustion(f):
    identifier=opened(f);connection=f.journal._db
    original=connection.execute('PRAGMA max_page_count').fetchone()[0]
    pages=connection.execute('PRAGMA page_count').fetchone()[0]
    require(connection.execute('PRAGMA max_page_count='+str(pages)).fetchone()[0]==pages)
    tokens=[]
    try:
        for _ in range(128):
            try:tokens.append(f.journal.issue_namespace(OWNER,9000)['token'])
            except sqlite3.OperationalError as error:
                require(error.sqlite_errorcode==sqlite3.SQLITE_FULL);break
        else:raise AssertionError('Expected controlled SQLite page exhaustion')
        require(not connection.in_transaction)
    finally:require(connection.execute('PRAGMA max_page_count='+str(original)).fetchone()[0]==original)
    count=connection.execute('SELECT count(*) FROM namespaces').fetchone()[0]
    require(count==len(tokens)+1 and f.snapshot(13)==0)
    f.reopen();f.host.reconcile(OWNER,identifier);retire(f,identifier,5)
    require(f.journal._db.execute('SELECT count(*) FROM namespaces').fetchone()[0]==count)


def fixed_writer_capacity(f):
    identifier=opened(f)
    # Actual public namespace issuance consumes the fixed partition. Each token
    # is retained; every overflow attempt rolls back its new token.
    tokens=[]
    for _ in range(1025):
        try:tokens.append(f.journal.issue_namespace(OWNER,9000)['token'])
        except JournalError as error:
            require(error.code=='STANDING_LOGICAL_CAPACITY');break
    else:raise AssertionError('Fixed public writer ceiling was not reached')
    require(len(tokens)==len(set(tokens)) and len(tokens)>500)
    count=f.journal._db.execute('SELECT count(*) FROM namespaces').fetchone()[0]
    refused('STANDING_LOGICAL_CAPACITY',f.journal.issue_namespace,OWNER,9000)
    require(f.journal._db.execute('SELECT count(*) FROM namespaces').fetchone()[0]==count)
    # Metadata is a disjoint reserved charge: a larger decimal clock and owner
    # epoch survive at the public fixed-writer edge, then loss/retirement settle.
    before=f.journal.owner_epoch
    f._clock=c.SAFE_INTEGER
    require(f.journal.authority_time()==c.SAFE_INTEGER)
    f.reopen();require(f.journal.owner_epoch==before+1)
    f.host.reconcile(OWNER,identifier)
    retire(f,identifier,5)
    require(int(f.journal._meta('last_clock'))==c.SAFE_INTEGER)


def accounting_model(directory):
    """Checker-only adversarial rows; never public API/durable-capacity proof."""
    db=sqlite3.connect(':memory:',isolation_level=None)
    # Minimal known schemas deliberately model the checker's documented charge
    # interface. They are not a valid Journal, deployment, or application state.
    for name,columns in [('meta','value BLOB'),('namespaces','value BLOB'),
            ('sd_meta','value BLOB'),('operations','id TEXT,value BLOB'),
            ('sd_mutations','deployment_id TEXT,value BLOB')]:
        db.execute('CREATE TABLE '+name+'('+columns+')')
    def add(table,charge,owner=None):
        length=charge-512-(len(owner.encode()) if owner is not None else 0)
        require(length>=0)
        if owner is None:db.execute('INSERT INTO '+table+' VALUES(?)',(bytes(length),))
        else:db.execute('INSERT INTO '+table+' VALUES(?,?)',(owner,bytes(length)))
    try:
        add('meta',16384)
        for _ in range(7):add('namespaces',65536)
        add('namespaces',49152)
        for _ in range(8):add('sd_meta',65536)
        for number in range(16):
            for _ in range(8):add('operations',8192,'finite:'+str(number))
            for _ in range(14):add('sd_mutations',65536,'standing:'+str(number))
        full=capacity_check(db,JournalError)
        require(full['chargedLogicalBytes']==16*1024*1024 and not full['protectedCapacity'])
        require(set(full['finiteOwners'].values())=={65536} and set(full['standingOwners'].values())=={917504})
        outcomes=[]
        for table in ('meta','namespaces','sd_meta','sd_mutations','operations'):
            db.execute('BEGIN')
            try:
                # Last BLOB byte grows within ordinary SQL type semantics. The
                # operation row also crosses its own tighter8192B row limit.
                db.execute('UPDATE '+table+' SET value=CAST(value || x\'00\' AS BLOB) WHERE rowid=1')
                refused('STANDING_LOGICAL_CAPACITY',capacity_check,db,JournalError)
                outcomes.append(table)
            finally:db.execute('ROLLBACK')
            require(capacity_check(db,JournalError)==full)
        db.execute('CREATE TABLE external_writer(value BLOB)')
        refused('STANDING_UNBOUNDED_WRITER_SCHEMA',capacity_check,db,JournalError)
        db.execute('DROP TABLE external_writer')
        report={'profile':'checker-only-in-memory-adversarial-rows','charged':full,'overflowTables':outcomes,
            'directSQLPopulation':True,'publicWriterRecords':False,'durableCapacityEstablished':False,
            'wholeGateIndependentOfPartitions':False,
            'reason':'Partition ceilings sum to16MiB, so violating the total necessarily violates at least one partition.'}
        save(directory/'evidence.json',report)
    finally:db.close()


NEGATIVE=(expired_qualification,driver_expiry_after_possible,installed_context_change,
          boot_after_acceptance,retired_without_terminal_proof,refused_sequence_original_key,
          automatic_ack_revision_refusal,dispute_retention)
PROFILES={'negative':[f.__name__ for f in NEGATIVE],
          'storage':['storage_'+phase+'_'+when for phase in ('prepare','open','collection','retire') for when in ('before','after')]+
                    ['rollback_exception','sqlite_page_exhaustion'],
          'mutation':['mutation_capacity'],'episodes':['episode_capacity'],
          'activations':['activation_capacity'],'keys':['retained_keys'],'fixed':['fixed_writer_capacity'],
          'accounting':['accounting_model']}


def main():
    global FINAL_DESTINATION,FINAL_REPORT
    require(not sys.flags.optimize and len(sys.argv)==7,'fixed invocation')
    profile=sys.argv[1];require(profile in PROFILES)
    state,pipe,evidence,manifest_path,helper=map(Path,sys.argv[2:])
    def interrupted(signum,_):raise RuntimeError('Control interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    state.mkdir();FINAL_DESTINATION=state/'CONTROL-RESULTS.json'
    FINAL_REPORT={'passed':False,'phase':'preparation','profile':profile};save(FINAL_DESTINATION,FINAL_REPORT)
    manifest=json.loads(manifest_path.read_bytes());guardian=Guardian(helper)
    results=[];failure=None
    try:
        for name in PROFILES[profile]:
            began=time.monotonic_ns();previous_checks=checks
            if profile=='accounting':
                directory=state/name;directory.mkdir();accounting_model(directory)
                results.append({'case':name,'checks':checks-previous_checks,'passed':True,
                    'elapsedMonotonicNs':str(time.monotonic_ns()-began),
                    'evidenceSha256':hashlib.sha256((directory/'evidence.json').read_bytes()).hexdigest(),
                    'databaseSha256':None})
                continue
            with TraceFixture(guardian,state/name,pipe,evidence,manifest,host_class=ProbeHost,store_class=ProbeStore) as f:
                if name.startswith('storage_'):
                    _,phase,when=name.split('_');storage_boundary(f,phase,when=='after')
                else:globals()[name](f)
                tables=[r[0] for r in f.journal._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                record={'case':name,'native':snapshot(f),'route':f.store.route(),
                    'tableCounts':{table:f.journal._db.execute('SELECT count(*) FROM "'+table+'"').fetchone()[0] for table in tables},
                    'capacity':capacity_check(f.journal._db,JournalError),'trace':f.host.trace or [],
                    'ownerEpoch':f.journal.owner_epoch,'authority':f.journal.authority_id,
                    'publicWriterRecords':True,'directSQLPopulation':False}
                save(f.directory/'evidence.json',record)
                require(f.policy._held_image is None and f.driver._lease is None and f.catalog._selection is None)
            results.append({'case':name,'checks':checks-previous_checks,'passed':True,
                'elapsedMonotonicNs':str(time.monotonic_ns()-began),
                'evidenceSha256':hashlib.sha256((state/name/'evidence.json').read_bytes()).hexdigest(),
                'databaseSha256':hashlib.sha256((state/name/'authority.db').read_bytes()).hexdigest()})
    except BaseException as error:
        failure=type(error).__name__+': '+str(error);traceback.print_exc();raise
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            errors=[];empty=closed=False
            for label,action in [('settle',guardian.settle),('empty',guardian.empty),('close',guardian.close)]:
                try:
                    value=action()
                    if label=='empty':empty=value is True
                    if label=='close':closed=True
                except BaseException as error:errors.append(label+': '+type(error).__name__+': '+str(error))
            pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            clean=all(r['reaped'] and r['exitCode']==0 for r in guardian.records)
            FINAL_REPORT={'passed':failure is None and not errors and empty and closed and not pending and clean,
                'profile':profile,'cases':results,'checks':checks,'failure':failure,'cleanupErrors':errors,
                'ownerEmpty':empty,'ownerClosed':closed,'interruptsPending':pending,'nativeChildrenReaped':guardian.records,
                'actualOwnerDeath':False,'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
            save(FINAL_DESTINATION,FINAL_REPORT);print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            save(FINAL_DESTINATION,FINAL_REPORT)
        raise
