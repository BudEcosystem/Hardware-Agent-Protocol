"""Source-only original vertical controls; require reviewed bounded launcher."""
import copy
import json
import os
from pathlib import Path
import signal
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT));sys.path.insert(0,str(PROJECT/'tests'))
sys.path.insert(0,str(PROJECT.parent/'owner'))
from guardian import Guardian
from standing_host_fixture import Fixture,OWNER
from hms.journal import JournalError, Evidence
from hms.standing_endpoint import StandingHost
from hms.standing_store import StandingStore
from hms.standing_wire import Opcode
from hms.contracts import canonical
from hms.registry import Registry
from hms.demo import type_bundle,object_schema
from hms.standing_capacity import check as capacity_check

checks=0
FINAL_DESTINATION=None
FINAL_REPORT=None

def require(value):
    global checks
    checks+=1
    if not value:raise AssertionError('Control assertion '+str(checks))


def refusal(code,function,*args,**kwargs):
    try:function(*args,**kwargs)
    except JournalError as error:require(error.code==code)
    else:raise AssertionError('Expected '+code)


class LostReplyHost(StandingHost):
    lose=None
    between_descriptor=None
    reserved_fault=False
    def _checkpoint(self,phase,value=None):
        if phase=='after_mutation_reservation_commit' and self.reserved_fault:
            self.reserved_fault=False
            raise JournalError('CONTROL_MUTATION_RESERVED')
        if phase=='after_exchange':
            if self.between_descriptor is not None and value['opcode']==Opcode.DESCRIBE and value['page']==0:
                hook=self.between_descriptor;self.between_descriptor=None;hook()
            if self.lose==value['opcode']:
                self.lose=None
                raise JournalError('CONTROL_LOST_AFTER_RX_COMMIT')


class FaultStore(StandingStore):
    fault=None
    hook=None
    def _checkpoint(self,phase,value=None):
        if phase==self.fault:
            self.fault=None
            if self.hook is not None:self.hook();return
            raise JournalError('CONTROL_STORAGE_BOUNDARY')


def opened(f,key='application'):
    row=f.host.prepare(OWNER,f.request(key));require(row['openState']=='prepared')
    row=f.host.open(OWNER,row['id']);require(row['openState']=='accepted')
    f.cycle(0)
    return row['id']


def active(f):
    identifier=opened(f)
    f.host.mutate(OWNER,identifier,'start',Opcode.START)
    require(f.snapshot(5)==2)
    return identifier


def transition(f):
    identifier=active(f);f.command(3,35000);f.cycle(12)
    require(f.snapshot(0)==1 and f.snapshot(2)==1)
    f.cycle(24)
    return identifier


def stop(f,identifier,at=40):
    f.host.mutate(OWNER,identifier,'stop',Opcode.STOP)
    f.cycle(at)
    row=f.host.collect(OWNER,identifier)
    require(f.store.state(row)['lifecycle']==5 and row['collected']==row['acknowledged']==row['highWater'])
    return row


def vertical(f):
    identifier=transition(f)
    row=f.host.collect(OWNER,identifier)
    require(row['collected']==row['acknowledged']==1 and f.snapshot(11)==1)
    stop(f,identifier)
    row=f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
    require(row['retired'] and not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    f.policy.enabled=False;f.producer.enabled=False
    before=f.snapshot(22)
    require(f.host.prepare(OWNER,f.request())['id']==identifier)
    require(f.snapshot(22)==before and f.snapshot(0)==1)
    refusal('KEY_CONFLICT',f.journal.submit,OWNER,f.finite_request('application'))


def shared_authority(f):
    with f.policy.hold_image():
        operation=f.journal.submit(OWNER,f.finite_request())
    refusal('RESOURCE_BUSY',f.host.prepare,OWNER,f.request())
    require(f.journal._instance_claimed('native:standing') and f.journal._instance_claimed('native:finite'))
    f.journal.request_cancel(OWNER,operation['id'])
    identifier=opened(f)
    with f.policy.hold_image():refusal('RESOURCE_BUSY',f.journal.submit,OWNER,f.finite_request('second'))
    require(f.journal._instance_claimed('native:finite'))
    with f.journal._transaction():refusal('STANDING_CLAIMS_UNRESOLVED',f.policy.require_lifecycle_quiescent,OWNER,'driver')
    registry=Registry(f.journal,monotonic_ms=lambda:1000,bootstrap_owner=OWNER)
    bundle=type_bundle('standing-alias','control',object_schema({}),{'type':'integer'},unit='1',effect='setpoint',resource='slot')
    digest=registry.publish_type(OWNER,canonical(bundle))
    for instance in ('native:standing','native:finite'):
        registry.enroll(OWNER,instance,digest,identity_kind='simulation',identity_ref=instance)
        binding={'profile':'hms.binding/0.1','instanceId':instance,'generation':'binding:2','typeDigest':digest,
            'calibrationRevision':'native-calibration:1','controlGeneration':'native-control:2','mode':'simulation',
            'adapterId':'native:standing-route','resourceMap':{'slot':'atom:slot'},'argumentSchemas':{'control':object_schema({})}}
        refusal('RESOURCE_CLAIMS_UNRESOLVED',registry.bind,OWNER,canonical(binding))
    stop(f,identifier,5);f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)


def open_reply_loss(f):
    row=f.host.prepare(OWNER,f.request());f.host.lose=Opcode.OPEN
    refusal('CONTROL_LOST_AFTER_RX_COMMIT',f.host.open,OWNER,row['id'])
    require(f.store.row(row['id'])['openState']=='possible' and f.snapshot(9)==1)
    refusal('STANDING_NEVER_HANDED_OFF_REQUIRED',f.host.abandon_prepared,OWNER,row['id'])
    received=f.store.route()['rx'];f.reopen()
    require(f.store.row(row['id'])['recoveryRequired'])
    before=f.snapshot(22);require(f.host.open(OWNER,row['id'])['openState']=='possible');require(f.snapshot(22)==before)
    row=f.host.reconcile(OWNER,row['id']);require(row['openState']=='accepted' and not row['transportUncertain'])
    require(f.store.route()['rx']>received and f.snapshot(0)==0)


def ack_reply_loss(f):
    identifier=transition(f);f.host.lose=Opcode.ACK
    refusal('CONTROL_LOST_AFTER_RX_COMMIT',f.host.collect,OWNER,identifier)
    row=f.store.row(identifier);require(row['collected']==1 and row['acknowledged']==0 and f.snapshot(11)==1)
    pending=f.store.pending(identifier)
    refusal('STANDING_NEVER_HANDED_OFF_REQUIRED',f.host.abandon_prepared,OWNER,identifier,mutation_key=pending[0]['hostKey'])
    f.reopen();before=f.snapshot(13)
    row=f.host.reconcile(OWNER,identifier)
    require(row['acknowledged']==1 and not row['transportUncertain'] and f.snapshot(13)==before)
    before=f.snapshot(22);f.host.prepare(OWNER,f.request());require(f.snapshot(22)==before)


def collection_rollback(f):
    identifier=transition(f);before=f.store.route()['rx'];f.store.fault='before_collection_commit'
    refusal('CONTROL_STORAGE_BOUNDARY',f.host.collect,OWNER,identifier)
    row=f.store.row(identifier)
    require(row['collected']==0 and f.snapshot(11)==0 and f.store.route()['rx']>before)
    require(f.journal._db.execute('SELECT count(*) FROM sd_activations').fetchone()[0]==0)
    f.reopen();f.host.reconcile(OWNER,identifier)
    row=f.host.collect(OWNER,identifier);require(row['collected']==row['acknowledged']==1)


def expiry_after_commit(f):
    row=f.host.prepare(OWNER,f.request());f.store.fault='after_open_handoff_commit'
    f.store.hook=lambda:setattr(f.policy,'_held_image',(0,0,'expired'))
    refusal('STANDING_IMAGE_LEASE_UNAVAILABLE',f.host.open,OWNER,row['id'])
    require(f.store.row(row['id'])['openState']=='possible' and f.snapshot(9)==0 and f.snapshot(0)==0)
    f.reopen();before=f.snapshot(22);f.host.open(OWNER,row['id']);require(f.snapshot(22)==before)
    refusal('STANDING_RECONCILIATION_UNRESOLVED',f.host.reconcile,OWNER,row['id'])


def boot_between_pages(f):
    f.host.between_descriptor=lambda:f.command(15,2)
    refusal('STANDING_BOOT_OR_RESPONSE_REPLAY',f.host.prepare,OWNER,f.request())
    require(f.journal._db.execute('SELECT count(*) FROM sd_deployments').fetchone()[0]==0 and f.snapshot(0)==0)


def renewal_withdrawal(f):
    identifier=active(f);f.cycle(12)
    f.host.mutate(OWNER,identifier,'renew',Opcode.RENEW);before=f.snapshot(13)
    f.policy.enabled=False
    require(f.host.mutate(OWNER,identifier,'renew',Opcode.RENEW)['state']=='accepted')
    require(f.snapshot(13)==before)
    refusal('STANDING_AUTHORITY_WITHDRAWN',f.host.mutate,OWNER,identifier,'renew-other',Opcode.RENEW)
    stop(f,identifier,20);f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)


def loss_episode_resume(f):
    identifier=transition(f);f.host.collect(OWNER,identifier)
    f.host.mutate(OWNER,identifier,'suspend',Opcode.SUSPEND);f.cycle(40)
    row=f.host.collect(OWNER,identifier)
    require(f.store.state(row)['lifecycle']==4 and f.journal._db.execute('SELECT count(*) FROM sd_episodes').fetchone()[0]==1)
    f.host.mutate(OWNER,identifier,'resume',Opcode.RESUME);f.cycle(52)
    require(f.snapshot(5)==1) # RESUME returns PREPARED, START is a distinct admission.
    f.host.mutate(OWNER,identifier,'restart',Opcode.START)
    require(f.snapshot(5)==2)
    stop(f,identifier,64);f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)


def finite_reserve(f):
    with f.policy.hold_image():
        operation=f.journal.submit(OWNER,f.finite_request())
        ticket=f.journal.claim_dispatch(operation['id'])
    evidence=Evidence('simulation','native:standing-route','native:trace',('running',))
    for _ in range(6):f.journal.record_execution(ticket,'running',evidence)
    refusal('STANDING_FINITE_EVENT_CAPACITY',f.journal.record_execution,ticket,'running',evidence)
    f.journal.request_cancel(OWNER,operation['id'])
    f.journal.acknowledge_cancel(ticket,True,Evidence('simulation','native:standing-route','native:trace',('cancel_ack',)))
    f.journal.record_execution(ticket,'canceled',Evidence('simulation','native:standing-route','native:trace',('terminated',)))
    f.journal.release_resources(operation['id'],Evidence('simulation','native:standing-route','native:trace',('resources_quiescent',)))
    with f.journal._transaction():
        summary=capacity_check(f.journal._db,JournalError)
        require(summary['maxLogicalBytes']==16*1024*1024 and summary['finiteOwners'][operation['id']]<=64*1024)
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    # New schema writers cannot bypass the complete profile gate.
    try:
        with f.journal._transaction():f.journal._db.execute('CREATE TABLE arbitrary_writer(x BLOB)')
    except JournalError as error:require(error.code=='STANDING_UNBOUNDED_WRITER_SCHEMA')
    else:raise AssertionError('Unbounded writer accepted')
    require(not f.journal._db.execute("SELECT 1 FROM sqlite_master WHERE name='arbitrary_writer'").fetchone())


def prepared_mutation_recovery(f):
    identifier=opened(f);f.host.reserved_fault=True
    refusal('CONTROL_MUTATION_RESERVED',f.host.mutate,OWNER,identifier,'start-original',Opcode.START)
    original=f.store.pending(identifier)[0]
    require(original['state']=='prepared' and f.snapshot(13)==0)
    f.reopen();f.host.reconcile(OWNER,identifier)
    require(f.store.row(identifier)['sequenceUncertain'])
    before=f.snapshot(22)
    require(f.host.mutate(OWNER,identifier,'start-original',Opcode.START)['state']=='prepared')
    require(f.snapshot(22)==before and f.snapshot(13)==0)
    settled=f.host.abandon_prepared(OWNER,identifier,mutation_key='start-original')
    require(settled['state']=='never_handed_off' and settled['body']==original['body'] and settled['tx']==original['tx'])
    require(not f.store.pending(identifier) and f.snapshot(13)==0)
    before=f.snapshot(22)
    require(f.host.mutate(OWNER,identifier,'start-original',Opcode.START)['state']=='never_handed_off')
    require(f.snapshot(22)==before)
    f.host.mutate(OWNER,identifier,'start-new',Opcode.START)
    require(f.snapshot(13)==1 and f.snapshot(5)==2)
    stop(f,identifier,5);f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)


def prepared_open_recovery(f):
    original=f.host.prepare(OWNER,f.request('never-open'))
    allocated=f.store.route();require(allocated['standingFloor']==1 and allocated['fences'][:2]==[1,1])
    f.reopen();before=f.snapshot(22)
    require(f.host.open(OWNER,original['id'])['openState']=='prepared' and f.snapshot(22)==before)
    refusal('STANDING_RECONCILIATION_UNRESOLVED',f.host.reconcile,OWNER,original['id'])
    settled=f.host.abandon_prepared(OWNER,original['id'])
    require(settled['retired'] and settled['openState']=='never_handed_off' and not settled['everPossiblyActed'])
    require(f.store.route()['fences']==allocated['fences'] and f.snapshot(9)==0 and f.snapshot(0)==0)
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    identifier=opened(f,'replacement-explicit')
    row=f.store.row(identifier)
    require(row['mapping']['standingNumber']==2 and row['mapping']['fences'][:2]==[2,2] and f.snapshot(9)==2)
    stop(f,identifier,5);f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
    before=f.snapshot(22)
    require(f.host.prepare(OWNER,f.request('never-open'))['id']==original['id'] and f.snapshot(22)==before)


def wrong_identity_stream(f):
    row=f.host.prepare(OWNER,f.request());f.command(16,(1<<8)|int(Opcode.OPEN))
    refusal('STANDING_EVIDENCE_CONFLICT',f.host.open,OWNER,row['id'])
    conflicted=f.store.row(row['id']);evidence=f.store.conflicts(row['id'])
    require(conflicted['openState']=='possible' and conflicted['disputed'] and conflicted['effectUnknown'])
    require(len(evidence)==1 and evidence[0]['reason']=='TRANSPORT_RESPONSE_ASSOCIATION')
    raw=bytes.fromhex(evidence[0]['evidence']['response'])
    require(raw[18:50]!=f.store.reference(row).intent_digest and int(evidence[0]['evidence']['rx'])==f.store.route()['rx'])
    require(f.snapshot(9)==1 and f.snapshot(0)==0)
    f.reopen();current=f.host.reconcile(OWNER,row['id'])
    require(current['disputed'] and current['effectUnknown'] and current['recoveryRequired'])
    require(f.store.conflicts(row['id'])==evidence)
    refusal('STANDING_RECOVERY_REQUIRED',f.host.mutate,OWNER,row['id'],'forbidden-start',Opcode.START)
    f.host.revoke(OWNER,row['id']);f.cycle(5)
    require(f.journal._db.execute('SELECT count(*) FROM claims').fetchone()[0]==3)


def malformed_state_stream(f):
    identifier=active(f);f.command(16,(2<<8)|int(Opcode.STATUS))
    refusal('STANDING_EVIDENCE_CONFLICT',f.host.status,OWNER,identifier)
    evidence=f.store.conflicts(identifier)
    require(len(evidence)==1 and bytes.fromhex(evidence[0]['evidence']['response'])[158]==0)
    f.reopen();row=f.host.reconcile(OWNER,identifier)
    require(row['effectUnknown'] and row['disputed'] and f.store.conflicts(identifier)==evidence)
    f.host.revoke(OWNER,identifier);f.cycle(5)
    require(f.journal._db.execute('SELECT count(*) FROM claims').fetchone()[0]==3)


def finite_final_guard(f):
    def withdraw(*_):f.policy.enabled=False
    f.journal.submission_record=withdraw
    with f.policy.hold_image():
        refusal('STANDING_AUTHORITY_WITHDRAWN',f.journal.submit,OWNER,f.finite_request())
    require(f.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]==0)
    f.policy.enabled=True;f.journal.submission_record=None
    with f.policy.hold_image():operation=f.journal.submit(OWNER,f.finite_request())
    with f.policy.hold_image():
        refusal('STANDING_AUTHORITY_WITHDRAWN',f.journal.claim_dispatch,operation['id'],_reserve=withdraw)
    saved=f.journal.status(OWNER,operation['id'])
    require(saved['state']=='accepted' and not saved['may_have_acted'] and len(saved['claims'])==3 and f.snapshot(0)==0)
    f.journal.request_cancel(OWNER,operation['id'])
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())


def owner_epoch_domain(f):
    row=f.host.prepare(OWNER,f.request())
    with f.journal._transaction():
        f.journal._set_meta('owner_epoch',str(2**32))
    f.reopen();current=f.store.row(row['id'])
    require(f.journal.owner_epoch==2**32+1 and current['ownerEpoch']==2**32+1 and current['recoveryRequired'])
    settled=f.host.abandon_prepared(OWNER,row['id'])
    require(settled['retired'] and settled['openState']=='never_handed_off' and f.snapshot(9)==0)


def prepared_ack_recovery(f):
    identifier=transition(f);f.host.reserved_fault=True
    refusal('CONTROL_MUTATION_RESERVED',f.host.collect,OWNER,identifier)
    original=f.store.pending(identifier)[0]
    require(original['opcode']==Opcode.ACK and original['state']=='prepared' and f.snapshot(11)==0)
    f.reopen();f.host.reconcile(OWNER,identifier)
    f.host.abandon_prepared(OWNER,identifier,mutation_key=original['hostKey'])
    row=f.host.collect(OWNER,identifier)
    require(row['collected']==row['acknowledged']==1 and f.snapshot(11)==1 and f.snapshot(13)==2)
    require(f.store.mutation(identifier,original['number'])['state']=='never_handed_off')
    stop(f,identifier);f.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)


def prepared_open_revoke_uncertain(f):
    row=f.host.prepare(OWNER,f.request());f.store.fault='after_revoke_handoff_commit'
    refusal('CONTROL_STORAGE_BOUNDARY',f.host.revoke,OWNER,row['id'])
    current=f.store.row(row['id'])
    require(current['openState']=='prepared' and current['revoke']['state']=='possible' and current['transportUncertain'])
    f.reopen();before=f.snapshot(22)
    refusal('STANDING_NEVER_HANDED_OFF_REQUIRED',f.host.abandon_prepared,OWNER,row['id'])
    current=f.store.row(row['id'])
    require(current['revoke']['state']=='possible' and current['transportUncertain'] and not current['retired'])
    require(f.snapshot(22)==before and f.journal._db.execute('SELECT count(*) FROM claims').fetchone()[0]==3)


def finite_policy_replacement(f):
    original=f.policy;replacement=object()
    def replace_policy(*_):f.journal.policy=replacement
    f.journal.submission_record=replace_policy
    try:
        with original.hold_image():
            refusal('STANDING_POLICY_CHANGED',f.journal.submit,OWNER,f.finite_request())
    finally:
        f.journal.policy=original;f.journal.submission_record=None
    require(f.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]==0)
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    with original.hold_image():operation=f.journal.submit(OWNER,f.finite_request())
    try:
        with original.hold_image():
            refusal('STANDING_POLICY_CHANGED',f.journal.claim_dispatch,operation['id'],_reserve=replace_policy)
    finally:
        f.journal.policy=original
    saved=f.journal.status(OWNER,operation['id'])
    require(saved['state']=='accepted' and not saved['may_have_acted'] and saved['attempt_id'] is None)
    require(len(saved['claims'])==3 and f.snapshot(0)==0)
    f.journal.request_cancel(OWNER,operation['id'])
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())


CASES=(vertical,shared_authority,open_reply_loss,ack_reply_loss,collection_rollback,
       expiry_after_commit,boot_between_pages,renewal_withdrawal,loss_episode_resume,finite_reserve,
       prepared_mutation_recovery,prepared_open_recovery,wrong_identity_stream,malformed_state_stream,finite_final_guard,owner_epoch_domain,prepared_ack_recovery,
       prepared_open_revoke_uncertain,finite_policy_replacement)

def publish(path,value):
    temporary=Path(str(path)+'.pending')
    with temporary.open('w') as out:
        json.dump(value,out,sort_keys=True);out.flush();os.fsync(out.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def main():
    global FINAL_DESTINATION,FINAL_REPORT
    if sys.flags.optimize:raise RuntimeError('Assertions must remain enabled')
    def interrupted(signum,_):raise RuntimeError('Control interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    state,pipe,evidence,manifest_path,helper=map(Path,sys.argv[1:])
    state.mkdir();FINAL_DESTINATION=state/'CONTROL-RESULTS.json'
    FINAL_REPORT={'passed':False,'phase':'preparation'};publish(FINAL_DESTINATION,FINAL_REPORT)
    manifest=json.loads(manifest_path.read_bytes());guardian=Guardian(helper)
    results=[];failure=None
    try:
        for case in CASES:
            before=checks
            with Fixture(guardian,state/case.__name__,pipe,evidence,manifest,host_class=LostReplyHost,store_class=FaultStore) as fixture:
                case(fixture)
            results.append({'case':case.__name__,'checks':checks-before,'passed':True})
    except BaseException as error:
        failure=type(error).__name__+': '+str(error)
        raise
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            errors=[];empty=False;closed=False
            for label,action in [('settle',guardian.settle),('empty',guardian.empty),('close',guardian.close)]:
                try:
                    value=action()
                    if label=='empty':empty=value is True
                    if label=='close':closed=True
                except BaseException as error:errors.append(label+': '+type(error).__name__+': '+str(error))
            pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            clean_exits=all(record['reaped'] and record['exitCode']==0 for record in guardian.records)
            result={'passed':failure is None and not errors and empty and closed and not pending and clean_exits,
                'nativeExpectedCleanExits':clean_exits,
                'cases':results,'checks':checks,'failure':failure,'cleanupErrors':errors,
                'ownerEmpty':empty,'ownerClosed':closed,'interruptsPending':pending,
                'nativeChildrenReaped':guardian.records,'physicalEligible':False,'protectedCapacity':False,
                'publicMountEligible':False,'actualOwnerCrashTested':False}
            FINAL_REPORT=result;publish(FINAL_DESTINATION,result)
            print(json.dumps(result,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False
            FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            publish(FINAL_DESTINATION,FINAL_REPORT)
        raise
