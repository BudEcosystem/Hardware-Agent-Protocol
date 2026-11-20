"""Independent stdlib-only retained-data audit. Review before execution.

Imports no candidate code and launches/signals no processes. Writes only a new
AUDIT.json beside this source; no attempt, database or pinned input is modified.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ATTEMPT=HERE/'owner-death-attempt01'
RESULT_SHA='c7dc7de7f0bf5f8b70ab1037f7894c9e5b8518c289e0d24b3be1e33ae26a4f77'
REVIEW_SHA='4dca9bff924a726520952e9beae2a4b7d18bd73f46a4735e2fd1c227f2aba9fe'
CASES=[('open-prepared','OPEN','prepared'),('open-possible','OPEN','possible'),('open-reply','OPEN','reply'),
       ('start-prepared','START','prepared'),('start-possible','START','possible'),('start-reply','START','reply'),
       ('collection-before-ack','COLLECTION','collection'),('ack-prepared','ACK','prepared'),
       ('ack-possible','ACK','possible'),('ack-reply','ACK','reply'),('retire-prepared','RETIRE','prepared'),
       ('retire-possible','RETIRE','possible'),('retire-reply','RETIRE','reply')]
OPS={'OPEN':64,'START':65,'ACK':68,'RETIRE':72}
IMMUTABLE=('id','principal','deployment','namespace','key','request','requestDigest','mapping','open','openTx')
MUTATION_IDENTITY=('number','hostKey','opcode','endpointSequence','body','bodyDigest','tx','leaseUntil','ack')
TABLES={'sd_mutations':(('number','host_key','endpoint_sequence'),8,1536),
        'sd_activations':(('number',),2,1024),'sd_activation_versions':(('number','version'),4,1024),
        'sd_episodes':(('episode_key',),2,1536)}
checks=0


def need(value,message):
    global checks
    checks+=1
    if not value:raise AssertionError(message)


def sha(body):return hashlib.sha256(body).hexdigest()


def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def raw(path,limit=1024*1024):
    info=Path(path).lstat();need(stat.S_ISREG(info.st_mode) and info.st_size<=limit,'Bounded regular input '+str(path))
    with Path(path).open('rb') as stream:body=stream.read(limit+1)
    need(len(body)==info.st_size,'Stable byte length '+str(path));return body


def data(path,*,canonical=True,limit=1024*1024):
    body=raw(path,limit);value=json.loads(body)
    if canonical:need(canon(value)==body,'Canonical JSON '+str(path))
    return value


def digest_file(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def uint(value,maximum=2**32-1):need(type(value) is int and 0<=value<=maximum,'Exact integer')

def u16(body,offset):return int.from_bytes(body[offset:offset+2],'big')

def u32(body,offset):return int.from_bytes(body[offset:offset+4],'big')

def u64(body,offset):return int.from_bytes(body[offset:offset+8],'big')


def identity(domain,value):return 'sha256:'+sha(domain.encode()+b'\0'+canon(value))


def reference(body,mapping,offset=2):
    need(u32(body,offset)==mapping['generation'] and u16(body,offset+4)==mapping['handle'] and
         u32(body,offset+6)==mapping['standingNumber'] and body[offset+10:offset+42].hex()==mapping['deploymentDigest'][7:],
         'Original wire reference identity')


def envelope(value,mapping):
    need(set(value)=={'boot','request','response','rx','tx'},'Envelope keys')
    request=bytes.fromhex(value['request']);response=bytes.fromhex(value['response'])
    uint(value['rx']);uint(value['tx']);need(value['rx']>0 and value['tx']>0 and value['boot']==mapping['boot']=='1','Envelope continuity')
    need(2<=len(request)<=192 and request[0]==2 and 66<=len(response)<=192,'Bounded v2 envelope')
    need(response[0]==2 and response[1]==request[1]|128 and u32(response,2)==value['tx'],'Response/request join')
    if request[1]!=1:
        reference(request,mapping);reference(response,mapping,8)
    return request,response


def records(view,table):
    keys,cap,limit=TABLES[table];rows=view['records'][table]
    need(type(rows) is list and len(rows)<=cap,'Snapshot row bound')
    result=[];seen=[]
    for entry in rows:
        need(set(entry)=={'key','document'} and set(entry['key'])==set(keys),'Keyed record shape')
        key=tuple(entry['key'][k] for k in keys);need(key not in seen,'Unique SQL key');seen.append(key)
        body=bytes.fromhex(entry['document']);need(len(body)<=limit,'Document bound');document=json.loads(body)
        need(canon(document)==body,'Original canonical document bytes');result.append((entry['key'],document))
    need(seen==sorted(seen),'Canonical SQL key order');return result


def validate_snapshot(view):
    row=view['row'];mapping=row['mapping'];request=row['request']
    need(canon(row).hex()==view['rowRaw'] and len(bytes.fromhex(view['rowRaw']))<=32768,'Original row bytes')
    need(row['disputed'] is False and row['effectUnknown'] is False and row['revoke'] is None,'Clean fixed setup, no common revoke')
    for field in ('ownerEpoch','hostRevision','mutationSequence','revision','collected','acknowledged','highWater','openTx'):uint(row[field],2**53-1)
    need(row['requestDigest']==identity('HMS-STANDING-REQUEST-v0.1',request)==mapping['requestDigest'],'Request digest')
    base=dict(mapping);base.pop('deploymentDigest')
    need(mapping['deploymentDigest']==identity('HMS-STANDING-DEPLOYMENT-v0.1',base),'Deployment digest')
    need(request['replayNamespace']==row['namespace'] and request['deploymentKey']==row['key']=='application','Original key')
    need(mapping['authorityId']==view['authorityId'],'Authority join')
    need(view['selection']==mapping['selection'] and view['installationDigest']==mapping['installationDigest'],'Installed selection join')
    need(view['originalRunId']=='native-standing-original:4','Original evaluator identity')
    need(set(mapping['resourceProof']['expandedClaims']['control'])=={'atom:demand','atom:output'},'Physical proof remains two')
    need({r['resource'] for r in mapping['claims']}=={'atom:demand','atom:output','atom:slot'} and len(mapping['claims'])==3,'Actual original shared claims')
    need(view['claims'] in ([],mapping['claims']) and view['aliases']==['native:finite','native:standing'],'Exact original claim retention/release')
    opened=bytes.fromhex(row['open']);need(len(opened)==134 and opened[:2]==b'\x02\x40','Original OPEN bytes')
    reference(opened,mapping)
    need(opened[79]==3 and [u32(opened,80+4*i) for i in range(8)]==mapping['fences'],'OPEN resource fences')
    need(u16(opened,44)==1 and opened[46]==32 and u64(opened,112)==1000 and u32(opened,122)==100 and
         u32(opened,126)==u32(opened,130)==1 and opened[120:122]==b'\0\0','Installed OPEN parameters')
    route=view['route'];need(route['standingFloor']==mapping['standingNumber']==1 and route['fences']==mapping['fences'] and route['boot']==mapping['boot'],'Monotone retained route floors')
    for table in TABLES:
        for key,document in records(view,table):
            if table=='sd_mutations':
                need(key=={'number':document['number'],'host_key':document['hostKey'],'endpoint_sequence':document['endpointSequence']},'Mutation SQL/document keys')
                body=bytes.fromhex(document['body']);need(len(body)==66 and body[:2]==bytes((2,document['opcode'])),'Mutation wire bytes')
                reference(body,mapping);need(document['bodyDigest']=='sha256:'+sha(body),'Mutation body digest')
                need(u32(body,44)==document['endpointSequence'] and u64(body,52)==document['leaseUntil'] and u32(body,60)==document['ack'],'Mutation immutable parameter join')
                if document['reply'] is not None:envelope(document['reply'],mapping)
                if 'retirementEvidence' in document:envelope(document['retirementEvidence'],mapping)
            elif table in ('sd_activations','sd_activation_versions'):
                activation=bytes.fromhex(document['raw']);need(len(activation)==44 and u32(activation,0)==key['number'],'Original activation ID/raw bytes')
                need(document['state']==activation[40]&7 and document['state']==2,'Completed fixed activation')
                req,res=envelope(document['envelope'],mapping)
                need(req[1]==67 and req[44]==2 and u32(req,45)==key['number'] and res[66:]==activation,'Activation response/raw join')
                need(activation[40]>>4&3==0 and activation[41]&7==5,'Synthetic activation is not physical evidence')
            else:
                req,res=envelope(document['state'],mapping);state=res[66:]
                need(len(state)==124 and state[89]==5 and state[92:94]==bytes((3,3)) and state[101]==3,'Terminal aggregate state')
                need(u16(state,96)&128 and not u16(state,96)&6,'Terminal witness and no pending output')
                witness=bytes.fromhex(document['witness']);need(state[102:124]==witness and len(witness)==22,'Original witness bytes')
                need(key['episode_key']==str(u64(state,53))+':'+str(u16(state,94)),'Episode SQL identity')
                need(witness[:4]==bytes((1,1,5,0)) and u32(witness,4)>0 and witness[16:22]==bytes(6),'Synthetic zero-output witness')
    if row['openReply'] is not None:envelope(row['openReply'],mapping)
    if row['lastStatus'] is not None:envelope(row['lastStatus'],mapping)
    need(0<=row['acknowledged']<=row['collected']<=row['highWater']<=1,'Exact fixed prefix limits')


def audit_wire(entries,mapping):
    need(type(entries) is list and len(entries)<=64,'Audit cap');last=0
    for entry in entries:
        need(set(entry)=={'opcode','tx','body','bodySha256'},'Audit fields');uint(entry['opcode'],255);uint(entry['tx'])
        body=bytes.fromhex(entry['body']);need(2<=len(body)<=192 and body[0]==2 and body[1]==entry['opcode'] and sha(body)==entry['bodySha256'],'Audit original wire/hash')
        need(entry['tx']>last,'Strict outbound sequence');last=entry['tx']
        if entry['opcode']==1:need(len(body)==3 and body[2]<=1,'Descriptor query')
        else:reference(body,mapping)
        if entry['opcode']==67:need(len(body)==49 and body[44]<=2,'Status query')


def expected_vector(op,cut):
    if op=='OPEN':return (1,1,0,0,0) if cut=='reply' else (0,0,0,0,0)
    if op=='START':return (2,1,0,0,1) if cut=='reply' else (1,1,0,0,0)
    if op in ('ACK','COLLECTION'):return (2,1,1,1,2) if cut=='reply' else (2,1,1,0,1)
    return (0,1,0,0,0) if cut=='reply' else (5,1,1,1,3)


def compare_database(directory,view):
    database=directory/'authority.db';need(database.stat().st_size<=1024*1024,'Database file bound')
    need(not any(Path(str(database)+suffix).exists() for suffix in ('-journal','-wal','-shm')),'No live database sidecar')
    connection=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        need(connection.execute('PRAGMA quick_check').fetchall()==[('ok',)],'Retained database consistency')
        need(connection.execute('PRAGMA foreign_key_check').fetchall()==[],'Retained foreign-key integrity')
        row=view['row'];owner=row['id']
        rows=connection.execute('SELECT id,principal,deployment,namespace,caller_key,request_digest,document FROM sd_deployments').fetchall()
        expected=(owner,row['principal'],row['deployment'],row['namespace'],row['key'],row['requestDigest'],bytes.fromhex(view['rowRaw']))
        need(rows==[expected],'Exact indexed replay/owner/deployment record')
        need(connection.execute('SELECT id,kind,principal,deployment FROM resource_owners').fetchall()==
             [(owner,'standing_deployment',row['principal'],row['deployment'])],'Common owner identity/kind')
        need(connection.execute('SELECT count(*) FROM sd_conflicts').fetchone()==(0,),'No retained conflicts in clean fixed slice')
        need(json.loads(connection.execute('SELECT document FROM sd_route').fetchone()[0])==view['route'],'Final database route')
        metadata=dict(connection.execute('SELECT key,value FROM meta'))
        need(metadata['authority']==view['authorityId'] and int(metadata['owner_epoch'])==view['ownerEpoch'],'Final authority/owner epoch')
        meta=json.loads(connection.execute('SELECT document FROM sd_meta').fetchone()[0]);installed=meta['installation']
        need(identity('HMS-STANDING-INSTALLATION-v0.1',installed)==meta['installationDigest']==view['installationDigest'],'Complete original installation binding')
        for table,(keys,_,_) in TABLES.items():
            rows=connection.execute('SELECT deployment_id,'+','.join(keys)+',document FROM '+table+' ORDER BY '+','.join(keys)).fetchall()
            need(all(entry[0]==owner for entry in rows),'Exact record owner '+table)
            observed=[{'key':dict(zip(keys,entry[1:-1])),'document':entry[-1].hex()} for entry in rows]
            need(observed==view['records'][table],'Final exact keyed '+table)
        rows=connection.execute('SELECT deployment,resource,operation_id,fence FROM claims ORDER BY resource').fetchall()
        need(all(entry[0]==row['deployment'] and entry[2]==owner for entry in rows),'Actual shared claim owner/deployment')
        claims=[{'resource':entry[1],'fence':entry[3]} for entry in rows]
        need(claims==view['claims'],'Final actual shared claim set')
        need(connection.execute('SELECT owner_id,instance_id FROM resource_owner_instances ORDER BY instance_id').fetchall()==
             [(owner,instance) for instance in view['aliases']],'Exact retained alias ownership')
    finally:connection.close()


def observe_absence(record):
    path=Path('/proc')/str(record['pid'])/'stat'
    try:
        with path.open('rb') as stream:body=stream.read(4097)
        need(len(body)<=4096,'Bounded proc identity')
    except FileNotFoundError:return {'pid':record['pid'],'startTicks':record['startTicks'],'observation':'absent'}
    fields=body.rsplit(b')',1)[1].split();start=int(fields[19])
    need(start!=record['startTicks'],'Original owned identity still exists, including zombie')
    return {'pid':record['pid'],'startTicks':record['startTicks'],'observation':'pid-reused-with-different-startTicks','currentStartTicks':start}


def main():
    need(not sys.flags.optimize and len(sys.argv)==1,'Fixed assertion-enabled audit')
    need(digest_file(ATTEMPT/'RESULTS.json')==RESULT_SHA,'Original final result pin')
    result=data(ATTEMPT/'RESULTS.json');intent=data(ATTEMPT/'intent.json');inner=data(ATTEMPT/'state/CONTROL-RESULTS.json')
    need(result['passed'] is True and inner['passed'] is True,'Both reducers passed')
    for value in (result,inner):
        need(value['ownerEmpty'] is True and value['ownerClosed'] is True and value['cleanupErrors']==[] and value['interruptsPending']==[],'Clean terminal owners')
        need(value['actualOwnerDeath'] is True and value['nativePeerSurvivedOwner'] is True and value['historicalPossibleEffectsResent'] is False,'Claimed narrow outcome')
        need(all(value[key] is False for key in ('physicalEligible','publicMountEligible','protectedCapacity','universalContainment')),'Narrow eligibility')
    need(result['reason'] is None and result['unexpectedChildrenObserved']==[] and inner['failure'] is None,'No hidden failure')
    start=int(result['controlStartedMonotonicNs']);end=int(result['controlTerminalObservedMonotonicNs'])
    need(0<end-start==int(result['controlObservedElapsedMonotonicNs'])<=30_000_000_000 and int(result['elapsedMonotonicNs'])>=end-start,'Observed command deadline')
    need(result['heldInterpreterBefore']==result['heldInterpreterAfter'] and result['heldInterpreterBefore']['sha256']==intent['interpreterSha256']==digest_file(intent['interpreter']),'Held/current interpreter pins')
    need(intent['wallSeconds']==intent['cpuSeconds']==30 and intent['addressBytes']==512*1024**2 and intent['childCpuSeconds']==5 and intent['childAddressBytes']==256*1024**2 and intent['fileBytes']==1024**2 and intent['openFiles']==64 and intent['cleanupSeconds']==8 and intent['termGraceSeconds']==3,'Original caps')
    need(result['qualificationRerun'] is False and intent['qualificationRerun'] is False,'No replaced evaluator')
    need([(r['case'],r['operation'],r['cut']) for r in inner['cases']]==CASES,'Exact thirteen-case matrix')
    outer=result['controlExit'];need(0<=outer['cpuSeconds']<=30 and outer['peakRSSKiB']<=512*1024,'Outer profile usage')
    need(result['outerChildrenReaped']==[outer] and outer['exitCode']==0 and outer['reaped'] is True,'Exact outer reap')
    need(data(ATTEMPT/'control.started.json')=={k:outer[k] for k in ('pid','parent','group','session','startTicks','state')},'Outer original start identity')
    need(len(inner['childrenReaped'])==39 and len({(r['pid'],r['startTicks']) for r in inner['childrenReaped']})==39,'Distinct inner identities')
    observed=[];joined=[];classifications=[]
    for case,(name,op,cut) in zip(inner['cases'],CASES):
        directory=ATTEMPT/'state'/name
        need(data(directory/'CASE-RESULT.json')==case and case['passed'] is True,'Per-case retained result')
        need(case['nativeImageSha256']==intent['nativeImageSha256'],'Every native peer image association')
        stage_names=[] if op=='OPEN' else ['open-poll'] if op=='START' else ['open-poll','transition'] if op in ('ACK','COLLECTION') else ['open-poll','transition','stop-cycle']
        need(case['stages']==[{'kind':'stage','case':name,'number':n,'stage':label} for n,label in enumerate(stage_names)],'Exact fixed setup stages')
        for filename,pin in case['evidence'].items():need(digest_file(directory/filename)==pin,'Case evidence pin')
        before=data(directory/'checkpoint.json',limit=128*1024);reopened=data(directory/'reopened.json',limit=128*1024)
        observed_view=data(directory/'observed.json',limit=128*1024);recovery=data(directory/'recovery.json',limit=128*1024);final=recovery['final']
        need(recovery['passed'] is True and recovery['case']==name and recovery['historicalPossibleEffectsResent'] is False and recovery['lockAcquiredAfterOwnerReap'] is True,'Recovery result scope')
        uint(recovery['readOnlyAuditCount'],64)
        for view in (before,reopened,observed_view,final):validate_snapshot(view)
        for field in ('authorityId','route','records','claims','aliases','installationDigest','producerIdentity','originalRunId','selection'):
            need(reopened[field]==before[field],'Exact immediate reopen '+field)
        need(reopened['ownerEpoch']==before['ownerEpoch']+1==reopened['row']['ownerEpoch'] and
             reopened['row']['ownerEpoch']==before['row']['ownerEpoch']+1 and reopened['row']['hostRevision']==before['row']['hostRevision']+1 and reopened['row']['recoveryRequired'] is True,'Exact allowed reopen changes')
        old=dict(before['row']);new=dict(reopened['row'])
        for field in ('ownerEpoch','hostRevision','recoveryRequired'):old.pop(field);new.pop(field)
        need(old==new,'No other reopen changes')
        for view in (observed_view,final):need(all(view['row'][f]==before['row'][f] for f in IMMUTABLE),'Immutable original application identity')
        notice=case['checkpointNotice'];need(notice['case']==name and notice['deployment']==before['row']['id'] and notice['operation']==op and notice['file']=='checkpoint.json','Cut association')
        phase={'prepared':'after_deployment_commit' if op=='OPEN' else 'after_mutation_reservation_commit','possible':'after_open_handoff_commit' if op=='OPEN' else 'after_mutation_handoff_commit','reply':'after_exchange','collection':'after_collection_before_ack'}[cut]
        need(notice['phase']==phase and notice['bytes']==len(raw(directory/'checkpoint.json')) and notice['sha256']==digest_file(directory/'checkpoint.json'),'Exact committed cut notice')
        original_items=[d for _,d in records(before,'sd_mutations')];final_items=[d for _,d in records(final,'sd_mutations')]
        for original in original_items:
            retained=next(d for d in final_items if d['number']==original['number'])
            need(all(retained[k]==original[k] for k in MUTATION_IDENTITY),'Original mutation not rewritten')
        target=original_items[-1] if op not in ('OPEN','COLLECTION') else None
        need(notice['mutation']==(None if target is None else target['number']),'Original target mutation')
        if op=='OPEN':need(before['row']['openState']==('prepared' if cut=='prepared' else 'possible'),'OPEN durable cut')
        elif target is not None:need(target['opcode']==OPS[op] and target['state']==('prepared' if cut=='prepared' else 'possible'),'Mutation durable cut')
        prefix=data(directory/'read-only-audit.json',limit=128*1024);audit=recovery['audit'];mapping=before['row']['mapping']
        audit_wire(audit,mapping)
        stage=case['recoveryStage']
        need(stage['kind']=='recovery-stage' and stage['case']==name and stage['stage']=='read-only-complete' and stage['file']=='read-only-audit.json' and
             stage['sha256']==digest_file(directory/'read-only-audit.json') and stage['bytes']==len(raw(directory/'read-only-audit.json')),'Recovery stage notice join')
        need(recovery['readOnlyAuditCount']==len(prefix['audit']),'Exact read-only count')
        need(prefix['case']==name and prefix['observedSnapshotSha256']==digest_file(directory/'observed.json'),'Read-only evidence association')
        need(prefix['audit']==audit[:recovery['readOnlyAuditCount']] and all(e['opcode'] in (1,67) for e in prefix['audit']),'No historical effect opcode')
        need(observed_view['route']['tx']==before['route']['tx']+recovery['readOnlyAuditCount'] and
             observed_view['route']['rx']==before['route']['rx']+recovery['readOnlyAuditCount'],'Read-only frame accounting')
        need(final['route']['tx']==before['route']['tx']+len(audit) and final['route']['rx']==before['route']['rx']+len(audit),'Complete outgoing/received audit accounting')
        expected_effects=[OPS[op]] if cut=='prepared' and op in ('START','ACK','RETIRE') else [68] if op=='COLLECTION' else []
        effects=[e for e in audit[recovery['readOnlyAuditCount']:] if e['opcode'] not in (1,67)]
        need(recovery['allowedExplicitEffects']==expected_effects and [e['opcode'] for e in effects]==expected_effects,'Only separately requested new effects')
        original_tx=before['row']['openTx'] if op=='OPEN' else target['tx'] if target is not None else None
        need(all(e['tx']!=original_tx for e in effects),'Original handed-off identity not resent')
        for effect in effects:
            need(any(d['state']=='accepted' and d['body']==effect['body'] and d['tx']==effect['tx'] for d in final_items),'Explicit effect joined to accepted new outbox')
        pre=case['nativeBeforeOwnerDeath'];post=case['nativeAfterOwnerDeath'];readonly=case['nativeAfterReadOnlyRecovery'];native_final=case['nativeAfterRecovery']
        need(tuple(pre[str(k)] for k in (5,9,10,11,13))==expected_vector(op,cut),'Native cut vector')
        need((pre['0'],pre['1'],pre['2'])==((0,0,0) if op in ('OPEN','START') else (1,1,0) if op=='RETIRE' else (1,0,1)),'Exact driver cut counters')
        need(pre==post and {k:v for k,v in pre.items() if k!='22'}=={k:v for k,v in readonly.items() if k!='22'},'Native survives death/read-only recovery unchanged')
        need(all(native_final[str(k)]==pre[str(k)] for k in (0,1,2,7,8,9,21)),'No spontaneous driver/context change')
        if expected_effects:
            vector={65:(2,1,0,0,1),68:(2,1,1,1,2),72:(0,1,0,0,0)}[expected_effects[0]]
            need(tuple(native_final[str(k)] for k in (5,9,10,11,13))==vector,'Explicit accepted native result')
        else:need({k:v for k,v in native_final.items() if k!='22'}=={k:v for k,v in pre.items() if k!='22'},'No extra native effects')
        released=(op=='OPEN' and cut=='prepared') or (op=='RETIRE' and cut in ('prepared','reply'))
        need(final['row']['retired'] is released and len(final['claims'])==(0 if released else 3),'Retired release versus retained ownership')
        if cut=='prepared':
            if op=='OPEN':need(final['row']['openState']=='never_handed_off','Never-sent OPEN settled')
            else:
                settled=next(d for d in final_items if d['number']==target['number'])
                need(settled['state']=='never_handed_off' and settled['settlement']=='durable-prepared-never-possible','Original prepared mutation retained settled')
        elif cut=='possible':
            need(all(final['row'][k] is True for k in ('recoveryRequired','transportUncertain','sequenceUncertain')),'Possible send remains unresolved')
            need(final['row']['openState']=='possible' if op=='OPEN' else next(d for d in final_items if d['number']==target['number'])['state']=='possible','Original possible state retained')
        elif cut=='reply':
            need(final['row']['openState']=='accepted' if op=='OPEN' else next(d for d in final_items if d['number']==target['number'])['state']=='accepted','Exact reply recovered')
        if cut!='possible':need(all(final['row'][k] is False for k in ('recoveryRequired','transportUncertain','sequenceUncertain')),'Settled observation has no pending authority ambiguity')
        if cut=='reply' and op in ('OPEN','START','ACK'):
            saved=final['row']['openReply'] if op=='OPEN' else next(d for d in final_items if d['number']==target['number'])['reply']
            _,response=envelope(saved,mapping);state=response[66:]
            need(response[6]==0 and len(state)==124,'Successful observed state')
            if target is not None:
                original_body=bytes.fromhex(target['body'])
                need(u32(state,5)==target['endpointSequence'] and state[9:29]==original_body[:2]+original_body[48:66],'Exact original accepted mutation comparison')
        if op in ('ACK','COLLECTION'):need(final['row']['collected']==1 and final['row']['acknowledged']==(0 if cut=='possible' else 1),'Committed prefix/ACK result')
        if op=='RETIRE':
            need(before['row']['collected']==before['row']['acknowledged']==before['row']['highWater']==1 and len(before['records']['sd_episodes'])==1,'Prior terminal prefix/witness before retirement')
            if cut=='reply':
                item=final_items[-1];_,forgotten=envelope(item['reply'],mapping);_,caps=envelope(item['retirementEvidence'],mapping);body=caps[66:]
                need(forgotten[6]==8 and u32(forgotten,50)==0 and len(body)==116 and body[50]==0 and u32(body,76)==1 and [u32(body,84+4*i) for i in range(8)]==mapping['fences'],'Retirement absence joined to retained original fences')
                need(u32(body,68)==u32(body,72)==1 and body[6:38].hex()==final['route']['contextDigest'],'Retirement epoch/context join')
        compare_database(directory,final)
        for role,exit_code in [('owner',-9),('recovery',0),('native',0)]:
            reap=case['reaps'][role];started=case['identities'][role]
            need(reap['parent']==outer['pid'] and reap['exitCode']==exit_code and reap['reaped'] is True and all(reap[k]==v for k,v in started.items()),'Kernel child/start/reap classification')
            need(0<=reap['cpuSeconds']<=5 and reap['peakRSSKiB']<=256*1024,'Child profile usage')
            for suffix in ('stdout','stderr'):need(raw(directory/(role+'.'+suffix))==b'','Clean fixed child log')
            joined.append(reap)
        classifications.append({'case':name,'classification':'retired-released' if released else 'possible-unresolved-retained' if cut=='possible' else 'accepted-or-explicitly-settled-retained','claims':len(final['claims']),'explicitEffects':expected_effects})
    need(sorted(joined,key=lambda r:(r['pid'],r['startTicks']))==sorted(inner['childrenReaped'],key=lambda r:(r['pid'],r['startTicks'])),'All39 original inner reaps joined exactly')
    for record in [outer]+joined:observed.append(observe_absence(record))
    inputs=data(HERE/'source-pins.json',canonical=False);review=data(HERE/'SOURCE-REVIEW.json',canonical=False)
    need(intent['parentPacket']==inputs['parentPacket'] and intent['publicReceipt']==inputs['publicReceipt'] and
         intent['originalQualificationRoot']==inputs['qualificationRoot'] and intent['originalQualificationRunId']=='native-standing-original:4','Original attempt intent association')
    need(digest_file(HERE/'SOURCE-REVIEW.json')==REVIEW_SHA and digest_file(ATTEMPT/'frozen/SOURCE-REVIEW.json')==REVIEW_SHA,'Exact executed manifest')
    for name,pin in intent['sourcePins'].items():need(digest_file(HERE/name)==digest_file(ATTEMPT/'frozen'/name)==pin,'Prepared/frozen executed input bytes')
    need(len(review['files'])==287 and set(intent['sourcePins'])=={r['path'] for r in review['files']}|{'SOURCE-REVIEW.json'},'Exact corrected inventory')
    for row in review['files']:
        need(intent['sourcePins'][row['path']]==row['sha256'],'Reviewed manifest/intent digest association')
        for path in (HERE/row['path'],ATTEMPT/'frozen'/row['path']):
            need(path.stat().st_size==row['bytes'] and digest_file(path)==row['sha256'],'Exact reviewed file bytes')
    need(len(inputs['copies'])==261 and len(inputs['originalProvenance'])==19,'Exact copied/provenance counts')
    for row in inputs['copies']+inputs['originalProvenance']:
        need(digest_file(HERE/row['copy'])==digest_file(REPO/row['source'])==row['sha256'],'Original source/provenance copies')
        need((HERE/row['copy']).stat().st_size==(REPO/row['source']).stat().st_size==row['bytes'],'Original copied byte counts')
    parent=REPO/inputs['parentPacket']['path'];need(digest_file(parent/'index.json')==inputs['parentPacket']['indexSha256'],'Sealed parent index')
    parent_index=data(parent/'index.json',canonical=False,limit=2*1024*1024)
    need({str(f.relative_to(parent)) for f in parent.rglob('*') if f.is_file()}=={r['path'] for r in parent_index['files']}|{'index.json'},'Exact parent inventory')
    for row in parent_index['files']:need(digest_file(parent/row['path'])==row['sha256'],'Sealed parent bytes')
    baseline=REPO/inputs['publicReceipt']['path'];need(digest_file(baseline)==inputs['publicReceipt']['sha256'],'Baseline receipt')
    public=data(baseline,canonical=False,limit=2*1024*1024)['files'];need(len(public)==244,'Public inventory')
    for row in public:need(digest_file(REPO/row['path'])==row['sha256'],'Public input unchanged')
    evidence=Path(inputs['qualificationRoot']);manifest=data(evidence/'manifest.json');reservation=data(evidence/'reservation.json');receipt=data(evidence/'receipt.json')
    need(manifest['runId']==reservation['runId']==receipt['runId']=='native-standing-original:4' and reservation['attemptId']==receipt['attemptId']=='native-standing-attempt:4','Original qualification provenance')
    need(manifest['argv']==reservation['argv']==receipt['argv']==[str(evidence/'standing-controls')],'Original absolute qualifier root')
    for key in ('binaryDigest','runnerDigest','domainDigest','sourcePins'):need(manifest[key]==reservation[key]==receipt[key],'Original qualification identity '+key)
    need(manifest['reservationDigest']=='sha256:'+digest_file(evidence/'reservation.json') and manifest['receiptDigest']=='sha256:'+digest_file(evidence/'receipt.json'),'Original qualifier reservation/receipt bytes')
    need(raw(evidence/'stdout')==b'{"cases":12,"assertions":638,"physical_qualification":false}\n' and raw(evidence/'stderr')==b'' and receipt['exitCode']==0 and receipt['ownership']['reaped'] is True,'Actual original12/638 evidence')
    need(digest_file(inputs['nativeImage'])==intent['nativeImageSha256']=='5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399','Original native image')
    files=[]
    for path in sorted(ATTEMPT.rglob('*')):
        if path.is_file():files.append({'path':str(path.relative_to(ATTEMPT)),'bytes':path.stat().st_size,'sha256':digest_file(path)})
    report={'profile':'hms.standing-owner-death-retained-audit/0.1','status':'verified-thirteen-fixed-owner-death-cuts',
            'auditSourceSha256':digest_file(__file__),'resultsSha256':RESULT_SHA,'sourceReviewSha256':REVIEW_SHA,
            'checks':checks,'cases':classifications,'innerReaps':39,'outerReaps':1,'ownedIdentityObservations':observed,
            'controlObservedElapsedMonotonicNs':str(end-start),'publicInputsExact':244,'sealedParentFilesExact':len(parent_index['files']),
            'copiedSourceHelperFilesExact':261,'originalProvenanceFilesExact':19,'files':files,'candidateImports':False,
            'candidateRerun':False,'qualificationRerun':False,'actualOwnerDeath':True,'nativePeerSurvivedOwner':True,
            'historicalPossibleEffectsResent':False,'wholeHostQualified':False,'physicalEligible':False,
            'publicMountEligible':False,'protectedCapacity':False,'universalContainment':False}
    with (HERE/'AUDIT.json').open('x') as output:json.dump(report,output,sort_keys=True,indent=2);output.write('\n')
    print(json.dumps({'passed':True,'checks':checks,'attemptFiles':len(files),'cases':13,'ownedIdentities':len(observed)},sort_keys=True))


if __name__=='__main__':main()
