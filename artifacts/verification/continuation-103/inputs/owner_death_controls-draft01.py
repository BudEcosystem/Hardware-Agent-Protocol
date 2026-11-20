"""Original fixed thirteen-cut owner-death controls; reviewed launcher only."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import struct
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'project'));sys.path.insert(0,str(HERE/'project/tests'))
sys.path.insert(0,str(HERE/'owner'))
from guardian import Guardian,read_record,write_record
from hms.contracts import canonical
from hms.journal import Journal,JournalError
from hms import standing_contracts as c
from hms.standing_endpoint import StandingHost,InstalledNativeDriver
from hms.endpoint_transport import LocalEndpointStream
from hms.standing_store import StandingStore
from hms.standing_pat import InstalledNativeProducer,StandingCatalog,installed_artifact,EVALUATOR
from hms.standing_wire import Opcode
from standing_host_fixture import installation,OWNER,Fixture

CASES=tuple((name,op,cut) for op in ('OPEN','START','ACK','RETIRE') for cut in ('prepared','possible','reply')
            for name in (op.lower()+'-'+cut,))
CASES=CASES[:6]+(('collection-before-ack','COLLECTION','collection'),)+CASES[6:]
IMMUTABLE=('id','principal','deployment','namespace','key','request','requestDigest','mapping','open','openTx')
MUTATION_IDENTITY=('number','hostKey','opcode','endpointSequence','body','bodyDigest','tx','leaseUntil','ack')
READ_ONLY={int(Opcode.DESCRIBE),int(Opcode.STATUS)}
SELECTORS=(0,1,2,5,7,8,9,10,11,13,21,22)
FINAL_PATH=None
FINAL_REPORT=None


def require(value,message='Control assertion'):
    if not value:raise AssertionError(message)


def sha(body):return hashlib.sha256(body).hexdigest()


def save(path,value,*,replace=False,limit=128*1024):
    body=canonical(value);require(len(body)<=limit,'Bounded evidence exceeded')
    path=Path(path);target=Path(str(path)+'.pending') if replace else path
    with target.open('wb' if replace else 'xb') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())
    if replace:os.replace(target,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'file':path.name,'bytes':len(body),'sha256':sha(body)}


def load(path,limit=128*1024):
    body=c.bounded_file(path,limit);value=json.loads(body)
    require(canonical(value)==body,'Noncanonical evidence');return value


def close_unneeded(keep):
    for fd in range(3,64):
        if fd not in keep:
            try:os.close(fd)
            except OSError:pass


def refusal(code,function,*args,**kwargs):
    try:function(*args,**kwargs)
    except JournalError as error:require(error.code==code,('Unexpected refusal',error.code,code))
    else:raise AssertionError('Missing refusal '+code)


def snapshot(assembly):
    journal,store=assembly.journal,assembly.store
    require(not journal._db.in_transaction,'Checkpoint inside transaction')
    ids=journal._db.execute('SELECT id FROM sd_deployments ORDER BY id LIMIT 2').fetchall()
    require(len(ids)==1,'One deployment required');identifier=ids[0][0]
    row=store.row(identifier)
    limits={'sd_mutations':(8,1536),'sd_activations':(2,1024),'sd_activation_versions':(4,1024),'sd_episodes':(2,1536)}
    records={}
    for table,(count,maximum) in limits.items():
        rows=journal._db.execute('SELECT document FROM '+table+' WHERE deployment_id=? ORDER BY rowid LIMIT ?',
                                (identifier,count+1)).fetchall()
        require(len(rows)<=count,'Snapshot row cap')
        require(all(type(r[0]) is bytes and len(r[0])<=maximum for r in rows),'Snapshot record cap')
        records[table]=[r[0].hex() for r in rows]
    claims=[dict(r) for r in journal._db.execute('SELECT resource,fence FROM claims WHERE operation_id=? ORDER BY resource LIMIT 4',(identifier,))]
    aliases=[r[0] for r in journal._db.execute('SELECT instance_id FROM resource_owner_instances WHERE owner_id=? ORDER BY instance_id LIMIT 3',(identifier,))]
    require(len(claims)<=3 and len(aliases)==2,'Snapshot ownership cap')
    raw=journal._db.execute('SELECT document FROM sd_deployments WHERE id=?',(identifier,)).fetchone()[0]
    require(type(raw) is bytes and len(raw)<=32768 and canonical(row)==raw,'Original row bytes')
    return {'authorityId':journal.authority_id,'ownerEpoch':journal.owner_epoch,'route':store.route(),
            'row':row,'rowRaw':raw.hex(),'records':records,'claims':claims,'aliases':aliases,
            'installationDigest':store.meta['installationDigest'],'producerIdentity':assembly.producer.identity,
            'originalRunId':assembly.producer.manifest['runId'],'selection':row['mapping']['selection']}


class Assembly:
    """Constructed only after fork, never inherited with a Journal connection."""
    def __init__(self,directory,wire,pipe,evidence,manifest,hook,*,create):
        self.journal=self.stream=None;self.hook=hook;self.audit=[]
        self.installation=installation(pipe,evidence/manifest['binaryPath'])
        self.policy=c.InstalledPolicy(OWNER,self.installation)
        self.driver=InstalledNativeDriver(pipe,self.installation)
        self.stream=LocalEndpointStream(wire);os.close(wire)
        self.journal=Journal(directory/'authority.db',self.policy,clock_ms=lambda:1000,
                             standing_profile=True,create=create)
        self.policy.journal=self.journal
        self.producer=InstalledNativeProducer(self.journal,evidence,manifest=manifest)
        self.catalog=StandingCatalog(self.journal,self.policy,self.producer,create=create)
        assembly=self
        class Store(StandingStore):
            def _checkpoint(self,phase,value=None):assembly.hook(assembly,phase,value)
        class Host(StandingHost):
            def _checkpoint(self,phase,value=None):
                if phase=='before_exchange':
                    require(len(assembly.audit)<64,'Outgoing audit exhausted')
                    assembly.audit.append({'opcode':int(value.opcode),'tx':value.frame.sequence,
                        'body':value.frame.payload.hex(),'bodySha256':sha(value.frame.payload)})
                assembly.hook(assembly,phase,value)
        self.store=Store(self.journal,self.policy,self.catalog,create=create)
        self.host=Host(self.store,self.stream,self.driver)
        if create:
            artifact=self.catalog.publish(OWNER,installed_artifact(self.installation))
            self.catalog.record_evaluation(OWNER,artifact,EVALUATOR,manifest['runId'])
            self.catalog.promote(OWNER,artifact)
            self.namespace=self.journal.issue_namespace(OWNER,9000)['token']
            self.host.initialize(OWNER)
        else:
            namespaces=self.journal._db.execute('SELECT token FROM namespaces LIMIT 2').fetchall()
            require(len(namespaces)==1);self.namespace=namespaces[0][0]
    request=Fixture.request
    def close(self):
        errors=[]
        for target in (self.journal,self.stream):
            if target is not None:
                try:target.close()
                except BaseException as error:errors.append(repr(error))
        self.journal=self.stream=None
        require(not errors,('Assembly cleanup',errors))


def owner_work(case,directory,wire,notice,gate,pipe,evidence,manifest):
    name,operation,cut=case;assembly=None;occurred=False;stage_number=0
    def stage(label):
        nonlocal stage_number
        require(not assembly.journal._db.in_transaction and assembly.policy._held_image is None)
        write_record(notice,{'kind':'stage','case':name,'number':stage_number,'stage':label})
        require(os.read(gate,1)==b'G','Stage gate EOF');stage_number+=1
    def hook(a,phase,value):
        nonlocal occurred
        wanted={'prepared':'after_deployment_commit' if operation=='OPEN' else 'after_mutation_reservation_commit',
                'possible':'after_open_handoff_commit' if operation=='OPEN' else 'after_mutation_handoff_commit',
                'reply':'after_exchange','collection':'after_collection_before_ack'}[cut]
        if phase!=wanted:return
        if cut=='reply' and int(value['opcode'])!=int(getattr(Opcode,operation)):return
        if operation not in ('OPEN','COLLECTION') and cut!='reply' and value['opcode']!=int(getattr(Opcode,operation)):return
        require(not occurred,'Duplicate death cut');occurred=True
        view=snapshot(a);row=view['row']
        mutations=[json.loads(bytes.fromhex(raw)) for raw in view['records']['sd_mutations']]
        item=mutations[-1] if operation not in ('OPEN','COLLECTION') else None
        if item is not None:require(item['opcode']==int(getattr(Opcode,operation)))
        pointer=save(directory/'checkpoint.json',view)
        write_record(notice,{'kind':'cut','case':name,'phase':phase,'operation':operation,
            'deployment':row['id'],'mutation':None if item is None else item['number'],**pointer})
        # There is never a continuation token at the selected death cut. EOF
        # or any unexpected byte fails; parent alone owns the gate writer.
        os.read(gate,1)
        raise AssertionError('Death cut must not resume')
    try:
        assembly=Assembly(directory,wire,pipe,evidence,manifest,hook,create=True)
        row=assembly.host.prepare(OWNER,assembly.request());identifier=row['id']
        assembly.host.open(OWNER,identifier);stage('open-poll')
        assembly.host.mutate(OWNER,identifier,'start',Opcode.START)
        stage('transition')
        assembly.host.collect(OWNER,identifier)
        assembly.host.mutate(OWNER,identifier,'stop',Opcode.STOP);stage('stop-cycle')
        assembly.host.collect(OWNER,identifier)
        assembly.host.mutate(OWNER,identifier,'retire',Opcode.RETIRE)
        raise AssertionError('Selected death cut not reached')
    finally:
        if assembly is not None:assembly.close()


def recovery_work(case,directory,wire,notice,gate,pipe,evidence,manifest):
    name,operation,cut=case;assembly=None
    try:
        before=load(directory/'checkpoint.json')
        assembly=Assembly(directory,wire,pipe,evidence,manifest,lambda *_:None,create=False)
        reopened=snapshot(assembly);save(directory/'reopened.json',reopened)
        require(reopened['authorityId']==before['authorityId'] and reopened['ownerEpoch']==before['ownerEpoch']+1)
        require(reopened['route']==before['route'] and reopened['records']==before['records'])
        require(reopened['claims']==before['claims'] and reopened['aliases']==before['aliases'])
        require(reopened['installationDigest']==before['installationDigest'] and reopened['producerIdentity']==before['producerIdentity'])
        old=copy.deepcopy(before['row']);new=copy.deepcopy(reopened['row'])
        for field in ('ownerEpoch','recoveryRequired','hostRevision'):old.pop(field);new.pop(field)
        require(old==new and reopened['row']['recoveryRequired'])
        row=reopened['row'];identifier=row['id'];host=assembly.host;store=assembly.store
        items=[json.loads(bytes.fromhex(raw)) for raw in before['records']['sd_mutations']]
        original=items[-1] if operation not in ('OPEN','COLLECTION') else None
        require(host.prepare(OWNER,row['request'])['id']==identifier)
        if operation=='OPEN':host.open(OWNER,identifier)
        elif operation in ('START','RETIRE'):host.mutate(OWNER,identifier,original['hostKey'],getattr(Opcode,operation))
        elif operation=='ACK':host.collect(OWNER,identifier)
        if operation=='OPEN' and cut in ('prepared','possible'):
            refusal('STANDING_RECONCILIATION_UNRESOLVED',host.reconcile,OWNER,identifier)
        else:host.reconcile(OWNER,identifier)
        observed=snapshot(assembly);save(directory/'observed.json',observed)
        require(all(entry['opcode'] in READ_ONLY for entry in assembly.audit),'Historical effect resent')
        read_count=len(assembly.audit)
        pointer=save(directory/'read-only-audit.json',{'case':name,'audit':assembly.audit,'observedSnapshotSha256':sha((directory/'observed.json').read_bytes())})
        require(not assembly.journal._db.in_transaction and assembly.policy._held_image is None)
        write_record(notice,{'kind':'recovery-stage','case':name,'stage':'read-only-complete',**pointer})
        require(os.read(gate,1)==b'G','Recovery gate EOF')
        if cut=='prepared':
            if operation=='OPEN':
                host.abandon_prepared(OWNER,identifier)
                require(store.row(identifier)['retired'] and store.row(identifier)['openState']=='never_handed_off')
                require(host.open(OWNER,identifier)['openState']=='never_handed_off')
            else:
                settled=host.abandon_prepared(OWNER,identifier,mutation_key=original['hostKey'])
                require(settled['state']=='never_handed_off')
                require(all(settled[k]==original[k] for k in MUTATION_IDENTITY))
                if operation=='ACK':host.collect(OWNER,identifier)
                else:host.mutate(OWNER,identifier,'new-'+operation.lower(),getattr(Opcode,operation))
                retained=store.mutation(identifier,original['number']);require(retained['state']=='never_handed_off')
                require(all(retained[k]==original[k] for k in MUTATION_IDENTITY))
                if operation in ('START','RETIRE'):
                    require(host.mutate(OWNER,identifier,original['hostKey'],getattr(Opcode,operation))['state']=='never_handed_off')
        elif cut=='possible':
            if operation=='OPEN':
                refusal('STANDING_NEVER_HANDED_OFF_REQUIRED',host.abandon_prepared,OWNER,identifier)
                require(store.row(identifier)['openState']=='possible')
            else:
                refusal('STANDING_NEVER_HANDED_OFF_REQUIRED',host.abandon_prepared,OWNER,identifier,mutation_key=original['hostKey'])
                require(store.mutation(identifier,original['number'])['state']=='possible')
                refusal('STANDING_SEQUENCE_UNRESOLVED',host.mutate,OWNER,identifier,'forbidden-renew',Opcode.RENEW)
            require(len(snapshot(assembly)['claims'])==3 and store.row(identifier)['recoveryRequired'])
        elif cut=='reply':
            if operation=='OPEN':require(store.row(identifier)['openState']=='accepted')
            else:require(store.mutation(identifier,original['number'])['state']=='accepted')
            if operation=='RETIRE':require(store.row(identifier)['retired'] and not snapshot(assembly)['claims'])
        else:
            require(operation=='COLLECTION' and row['collected']==1 and row['acknowledged']==0)
            require(not any(item['opcode']==int(Opcode.ACK) for item in items))
            require(observed['records']==before['records'],'Read-only collection recovery changed records')
            host.collect(OWNER,identifier)
        final=snapshot(assembly)
        require(all(final['row'][field]==before['row'][field] for field in IMMUTABLE))
        if original is not None:
            retained=store.mutation(identifier,original['number'])
            require(all(retained[k]==original[k] for k in MUTATION_IDENTITY))
        allowed=[]
        if cut=='prepared' and operation in ('START','ACK','RETIRE'):allowed=[int(getattr(Opcode,operation))]
        if operation=='COLLECTION':allowed=[int(Opcode.ACK)]
        effects=[e['opcode'] for e in assembly.audit[read_count:] if e['opcode'] not in READ_ONLY]
        require(effects==allowed,('Unexpected explicit effects',effects,allowed))
        expected_claims=0 if (operation=='OPEN' and cut=='prepared') or (operation=='RETIRE' and cut in ('prepared','reply')) else 3
        require(len(final['claims'])==expected_claims)
        if operation in ('ACK','COLLECTION') and cut!='possible':require(final['row']['acknowledged']==1)
        save(directory/'recovery.json',{'case':name,'passed':True,'readOnlyAuditCount':read_count,
            'audit':assembly.audit,'allowedExplicitEffects':allowed,'final':final,
            'historicalPossibleEffectsResent':False,'lockAcquiredAfterOwnerReap':True})
    finally:
        if assembly is not None:assembly.close()


def command(sock,opcode,value=0):
    packet=struct.pack('>BQ',opcode,value);end=time.monotonic()+1;offset=0;reply=b''
    sock.setblocking(False)
    while offset<len(packet):
        left=end-time.monotonic();require(left>0 and select.select([],[sock],[],left)[1])
        offset+=sock.send(packet[offset:])
    while len(reply)<9:
        left=end-time.monotonic();require(left>0 and select.select([sock],[],[],left)[0])
        chunk=sock.recv(9-len(reply));require(chunk);reply+=chunk
    kind,result=struct.unpack('>BQ',reply);require(kind==opcode);return result


def observations(control):return {str(k):command(control,5,k) for k in SELECTORS}


def expected_native(operation,cut):
    if operation=='OPEN':return (0,0,0,0,0) if cut!='reply' else (1,1,0,0,0)
    if operation=='START':return (1,1,0,0,0) if cut!='reply' else (2,1,0,0,1)
    if operation in ('ACK','COLLECTION'):return (2,1,1,1,2) if cut=='reply' else (2,1,1,0,1)
    return (0,1,0,0,0) if cut=='reply' else (5,1,1,1,3)


def run_case(guardian,case,state,pipe,evidence,manifest):
    name,operation,cut=case;directory=state/name;directory.mkdir();start=time.monotonic()
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    control,child_control=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    executable=os.open(pipe,os.O_RDONLY|os.O_CLOEXEC);fcntl.flock(executable,fcntl.LOCK_SH|fcntl.LOCK_NB)
    before=os.fstat(executable);body=os.pread(executable,2*1024*1024+1,0)
    require(stat.S_ISREG(before.st_mode) and len(body)==before.st_size<=2*1024*1024)
    image=sha(body);identities={};reaps={};stage_trace=[];record_start=len(guardian.records)
    owned_fds=[];logs=[];native=None;failure=None
    def launch(role,work,keep):
        out=(directory/(role+'.stdout')).open('xb');err=(directory/(role+'.stderr')).open('xb');logs.extend((out,err))
        def child_work():
            os.dup2(out.fileno(),1);os.dup2(err.fileno(),2)
            close_unneeded(set(keep)|{1,2})
            try:work()
            except BaseException as error:
                save(directory/(role+'-failure.json'),{'error':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()[-65536:]})
                raise
        pid=guardian.fork(child_work);identities[role]=guardian.handles[pid]['identity']
        out.close();err.close();return pid
    try:
        require(guardian.empty(),'Previous case child retained')
        def native_work():
            os.dup2(child.fileno(),0);os.dup2(child.fileno(),1)
            os.set_inheritable(child_control.fileno(),True)
            os.execve('/proc/self/fd/'+str(executable),[str(pipe),'--test-control-fd',str(child_control.fileno())],{'LANG':'C','LC_ALL':'C'})
        native=launch('native',native_work,{child.fileno(),child_control.fileno(),executable})
        child.close();child_control.close()
        notice_read,notice_write=os.pipe();gate_read,gate_write=os.pipe()
        owned_fds.extend((notice_read,notice_write,gate_read,gate_write))
        owner=launch('owner',lambda:owner_work(case,directory,parent.fileno(),notice_write,gate_read,pipe,evidence,manifest),
                     {parent.fileno(),notice_write,gate_read})
        os.close(notice_write);owned_fds.remove(notice_write);os.close(gate_read);owned_fds.remove(gate_read)
        expected_stages=[] if operation=='OPEN' else ['open-poll'] if operation=='START' else ['open-poll','transition'] if operation in ('ACK','COLLECTION') else ['open-poll','transition','stop-cycle']
        for index,label in enumerate(expected_stages):
            message=read_record(notice_read,max(.001,5-(time.monotonic()-start)))
            require(message=={'kind':'stage','case':name,'number':index,'stage':label})
            if label=='open-poll':command(control,2,0)
            elif label=='transition':command(control,3,35000);command(control,2,12);command(control,2,24)
            else:command(control,2,40)
            stage_trace.append(message);require(os.write(gate_write,b'G')==1)
        notice=read_record(notice_read,max(.001,5-(time.monotonic()-start)))
        require(time.monotonic()-start<5,'Case cut deadline')
        expected_phase={'prepared':'after_deployment_commit' if operation=='OPEN' else 'after_mutation_reservation_commit',
                        'possible':'after_open_handoff_commit' if operation=='OPEN' else 'after_mutation_handoff_commit',
                        'reply':'after_exchange','collection':'after_collection_before_ack'}[cut]
        require(notice['kind']=='cut' and notice['case']==name and notice['operation']==operation and
                notice['phase']==expected_phase and notice['file']=='checkpoint.json')
        checkpoint_body=c.bounded_file(directory/'checkpoint.json',128*1024)
        require(sha(checkpoint_body)==notice['sha256'] and len(checkpoint_body)==notice['bytes'])
        checkpoint=load(directory/'checkpoint.json');require(checkpoint['row']['id']==notice['deployment'])
        require(checkpoint['row']['revoke'] is None and len(checkpoint['claims'])==3)
        selected=[json.loads(bytes.fromhex(raw)) for raw in checkpoint['records']['sd_mutations']]
        require(notice['mutation']==(selected[-1]['number'] if operation not in ('OPEN','COLLECTION') else None))
        if operation=='OPEN':require(checkpoint['row']['openState']==('prepared' if cut=='prepared' else 'possible'))
        elif operation!='COLLECTION':require(selected[-1]['state']==('prepared' if cut=='prepared' else 'possible'))
        else:require(checkpoint['row']['collected']==1 and checkpoint['row']['acknowledged']==0)
        pre=observations(control)
        require(tuple(pre[str(k)] for k in (5,9,10,11,13))==expected_native(operation,cut))
        require(set(guardian.refresh())=={native,owner} and guardian.status(native) is None and guardian.status(owner) is None)
        guardian.send(owner,signal.SIGKILL);reaps['owner']=guardian.wait_exit(owner)
        require(reaps['owner']['exitCode']==-signal.SIGKILL)
        os.close(gate_write);owned_fds.remove(gate_write);os.close(notice_read);owned_fds.remove(notice_read)
        post=observations(control);require(post==pre,'Native changed across host death')
        require(set(guardian.refresh())=={native} and guardian.status(native) is None)
        recovery_read,recovery_write=os.pipe();continue_read,continue_write=os.pipe()
        owned_fds.extend((recovery_read,recovery_write,continue_read,continue_write))
        recovery=launch('recovery',lambda:recovery_work(case,directory,parent.fileno(),recovery_write,continue_read,pipe,evidence,manifest),
                        {parent.fileno(),recovery_write,continue_read})
        os.close(recovery_write);owned_fds.remove(recovery_write);os.close(continue_read);owned_fds.remove(continue_read)
        require(set(guardian.refresh())=={native,recovery})
        recovery_notice=read_record(recovery_read)
        require(recovery_notice['kind']=='recovery-stage' and recovery_notice['case']==name and
                recovery_notice['stage']=='read-only-complete' and recovery_notice['file']=='read-only-audit.json')
        audit_body=c.bounded_file(directory/'read-only-audit.json',128*1024)
        require(sha(audit_body)==recovery_notice['sha256'] and len(audit_body)==recovery_notice['bytes'])
        audit_view=load(directory/'read-only-audit.json')
        require(all(entry['opcode'] in READ_ONLY for entry in audit_view['audit']))
        readonly_native=observations(control)
        require({k:v for k,v in readonly_native.items() if k!='22'}=={k:v for k,v in pre.items() if k!='22'})
        require(guardian.status(native) is None and guardian.status(recovery) is None)
        require(os.write(continue_write,b'G')==1)
        reaps['recovery']=guardian.wait_exit(recovery);require(reaps['recovery']['exitCode']==0,'Recovery failed')
        os.close(continue_write);owned_fds.remove(continue_write);os.close(recovery_read);owned_fds.remove(recovery_read)
        result=load(directory/'recovery.json');require(result['passed'])
        require(guardian.status(native) is None and set(guardian.refresh())=={native})
        final_native=observations(control)
        # Native control state cannot change during historical replay. Only the
        # explicitly logged newly admitted action may consume a sequence.
        if not result['allowedExplicitEffects']:
            require({k:v for k,v in final_native.items() if k!='22'}=={k:v for k,v in pre.items() if k!='22'})
        else:
            effect=result['allowedExplicitEffects'];expected={int(Opcode.START):(2,1,0,0,1),int(Opcode.ACK):(2,1,1,1,2),int(Opcode.RETIRE):(0,1,0,0,0)}
            require(len(effect)==1 and tuple(final_native[str(k)] for k in (5,9,10,11,13))==expected[effect[0]])
        parent.close();control.close()
        reaps['native']=guardian.wait_exit(native);require(reaps['native']['exitCode']==0,'Native EOF exit required')
        require(guardian.empty() and len(guardian.records)-record_start==3)
        after=os.fstat(executable);require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and sha(os.pread(executable,2*1024*1024+1,0))==image)
        value={'case':name,'operation':operation,'cut':cut,'passed':True,'nativeImageSha256':image,
            'identities':identities,'reaps':reaps,'stages':stage_trace,'checkpointNotice':notice,
            'nativeBeforeOwnerDeath':pre,'nativeAfterOwnerDeath':post,'nativeAfterReadOnlyRecovery':readonly_native,
            'recoveryStage':recovery_notice,'nativeAfterRecovery':final_native,
            'actualOwnerDeath':True,'nativePeerSurvivedOwner':True,'historicalPossibleEffectsResent':False,
            'evidence':{name:sha((directory/name).read_bytes()) for name in ('checkpoint.json','reopened.json','observed.json','read-only-audit.json','recovery.json')}}
        save(directory/'CASE-RESULT.json',value);return value
    except BaseException as error:
        failure=type(error).__name__+': '+str(error)
        save(directory/'CASE-FAILURE.json',{'case':name,'failure':failure,'identities':identities,'reaps':reaps,'stages':stage_trace})
        raise
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        errors=[]
        for target in (parent,child,control,child_control,*logs):
            try:target.close()
            except BaseException as error:errors.append(repr(error))
        for fd in owned_fds+[executable]:
            try:os.close(fd)
            except OSError as error:errors.append(repr(error))
        if failure is not None:
            try:guardian.settle()
            except BaseException as error:errors.append(repr(error))
        try:
            require(not errors,('Case cleanup',errors))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)


def main():
    global FINAL_PATH,FINAL_REPORT
    require(not sys.flags.optimize and len(sys.argv)==5,'Fixed runner invocation required')
    state,pipe,evidence,helper=map(Path,sys.argv[1:]);state.mkdir()
    def interrupted(signum,_):raise RuntimeError('Control interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    manifest=load(evidence/'manifest.json',16384)
    FINAL_PATH=state/'CONTROL-RESULTS.json';FINAL_REPORT={'passed':False,'phase':'preparation'}
    save(FINAL_PATH,FINAL_REPORT,replace=True)
    guardian=Guardian(helper);cases=[];failure=None
    try:
        for case in CASES:cases.append(run_case(guardian,case,state,pipe,evidence,manifest))
    except BaseException as error:failure=type(error).__name__+': '+str(error)
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        errors=[];empty=closed=False
        for label,action in [('settle',guardian.settle),('empty',guardian.empty),('close',guardian.close)]:
            try:
                value=action()
                if label=='empty':empty=value is True
                if label=='close':closed=True
            except BaseException as error:errors.append(label+': '+repr(error))
        pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        reaps=guardian.records
        expected=(len(reaps)==39 and sum(r['exitCode']==-signal.SIGKILL for r in reaps)==13 and sum(r['exitCode']==0 for r in reaps)==26)
        passed=failure is None and len(cases)==13 and expected and empty and closed and not errors and not pending
        FINAL_REPORT={'passed':passed,'cases':cases,'childrenReaped':reaps,'failure':failure,'cleanupErrors':errors,
            'ownerEmpty':empty,'ownerClosed':closed,'interruptsPending':pending,'actualOwnerDeath':passed,
            'nativePeerSurvivedOwner':passed,'historicalPossibleEffectsResent':False if passed else None,
            'physicalEligible':False,'publicMountEligible':False,'protectedCapacity':False,'universalContainment':False}
        try:
            save(FINAL_PATH,FINAL_REPORT,replace=True,limit=1024*1024)
            print(json.dumps({'passed':passed,'cases':len(cases),'childrenReaped':len(reaps),'failure':failure},sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    require(FINAL_REPORT['passed'],'Owner-death controls failed')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_PATH is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['actualOwnerDeath']=False;FINAL_REPORT['nativePeerSurvivedOwner']=False
            FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            save(FINAL_PATH,FINAL_REPORT,replace=True,limit=1024*1024)
        raise
