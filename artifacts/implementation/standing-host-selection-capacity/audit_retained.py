"""Data-only retained audit of the failed original mutation-capacity attempt.

Imports no candidate or oracle; launches/signals no child. Reads SQLite with
immutable read-only URI/query_only. Only a new exclusive AUDIT.json is published
after root review and execution. Current /proc absence is observation, never
stored-PID signal authority. Retained failure integrity is audited; the workload remains failed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
REVIEW_SHA='d72b3d26053adbd54bdf06a6b848c00fbe490cf078585b561d684057a39f9c96'
INPUT_SHA='5bff8b6c670e354847e92910a3a1444bb866f2e9b8bb2c33c7035b3df9c04cf4'
NATIVE_SHA='5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399'
QUALIFIER_SHA='b89d0a1030768932ace1c9c2da5a4a888d0ae7da46a8a77473b2b145293ff842'
HOST_SOURCES=('hms/standing_contracts.py','hms/standing_wire.py','hms/standing_store.py',
 'hms/standing_endpoint.py','hms/standing_pat.py','hms/standing_capacity.py','hms/journal.py',
 'hms/registry.py','hms/resource_catalog.py','hms/resource_topology.py','hms/endpoint_transport.py',
 'hms/contracts.py','protocol/serial/frame.py')
DRIVER_SOURCES=('tests/standing_controls.c','tests/standing_fixture.c','tests/standing_fixture.h',
 'tests/standing_vectors.h','protocol/endpoint/endpoint.c','protocol/endpoint/endpoint.h',
 'protocol/endpoint/standing.c','protocol/endpoint/standing.h','protocol/endpoint/link.c',
 'protocol/endpoint/link.h','protocol/serial/frame.c','protocol/serial/frame.h','tests/standing_host_pipe.c')
FIXED=set(('meta series namespaces resource_floors resource_owners resource_owner_instances claims '
 'reg_meta reg_types reg_instances reg_capabilities reg_bindings reg_binding_history reg_presence '
 'reg_endpoint_sessions reg_session_history reg_observations reg_streams reg_stream_history reg_grants '
 'reg_resource_requirements reg_resource_instances rc_catalog rc_generations rc_tokens rc_proofs '
 'sp_meta sp_artifacts sp_evaluations sp_decisions').split())
FINITE={'operations':'id','replay_keys':'operation_id','events':'operation_id'}
STANDING={'sd_deployments':'id','sd_mutations':'deployment_id','sd_activations':'deployment_id',
 'sd_activation_versions':'deployment_id','sd_conflicts':'deployment_id','sd_episodes':'deployment_id'}
checks=0


def need(value,message):
    global checks
    checks+=1
    if not value:raise AssertionError(str(message))


def sha(body):return hashlib.sha256(body).hexdigest()
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def identity(domain,value):return 'sha256:'+sha(domain.encode()+b'\0'+canon(value))
def u16(b,n):return int.from_bytes(b[n:n+2],'big')
def u32(b,n):return int.from_bytes(b[n:n+4],'big')
def u64(b,n):return int.from_bytes(b[n:n+8],'big')
def uint(value,maximum=2**64-1):need(type(value) is int and 0<=value<=maximum,'Exact bounded integer')


def raw(path,limit=1024*1024):
    path=Path(path);before=path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'Bounded regular input '+str(path))
    with path.open('rb') as stream:body=stream.read(limit+1)
    after=path.lstat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and len(body)==before.st_size,'Stable input bytes')
    return body


def digest(path):
    info=Path(path).lstat();need(stat.S_ISREG(info.st_mode) and info.st_size<=64*1024*1024,'Regular bounded hashed file')
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def data(path,canonical=True,limit=1024*1024):
    body=raw(path,limit);value=json.loads(body)
    if canonical:need(canon(value)==body,'Canonical JSON '+str(path))
    return value


def inventory(base,rows,extra=()):
    names=[]
    for row in rows:
        name=row['path'];need(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts,'Relative inventory path')
        path=base/name;names.append(name)
        need(path.lstat().st_size==row['bytes'] and digest(path)==row['sha256'],'Exact retained inventory '+str(path))
    need(len(names)==len(set(names)),'Unique inventory paths')
    found=set()
    for path in base.rglob('*'):
        need(not path.is_symlink(),'No inventory symlinks')
        if path.is_file():found.add(str(path.relative_to(base)))
    need(found==set(names)|set(extra),'Exact inventory membership '+str(base))


def doc(body,maximum):
    need(type(body) is bytes and 0<len(body)<=maximum,'Bounded original document')
    value=json.loads(body);need(canon(value)==body,'Canonical stored document');return value


def reference(body,mapping,offset=2):
    need(u32(body,offset)==mapping['generation'] and u16(body,offset+4)==mapping['handle'] and
         u32(body,offset+6)==mapping['standingNumber'] and body[offset+10:offset+42].hex()==mapping['deploymentDigest'][7:],
         'Exact deployment wire reference')


def envelope(value,mapping,conflict=False):
    need(set(value)=={'boot','request','response','rx','tx'},'Envelope keys')
    request=bytes.fromhex(value['request']);response=bytes.fromhex(value['response'])
    uint(value['rx'],2**32-1);uint(value['tx'],2**32-1)
    need(value['rx']>0 and value['tx']>0 and 2<=len(request)<=192 and 66<=len(response)<=192,'Envelope bounds')
    need(request[0]==response[0]==2 and response[1]==request[1]|128 and u32(response,2)==value['tx'],'Original request/response correlation')
    if not conflict:
        need(value['boot']==mapping['boot']=='1','Same-boot qualified evidence')
        if request[1]>=64:reference(request,mapping);reference(response,mapping,8)
        elif request[1]==18:reference(response,mapping,8)
    return request,response


def charges(db,tables):
    # Independent Python-cell accounting; deliberately not the production SQL
    # expression or imported checker. Only retained actual DB values are read.
    fixed=base=metadata=0;finite={};standing={};counts={}
    need(set(tables)<=FIXED|set(FINITE)|set(STANDING)|{'sd_meta','sd_route'} and len(tables)<=48,'Closed writer tables')
    for table in tables:
        columns=[r[1] for r in db.execute('PRAGMA table_info("'+table+'")')]
        need(0<len(columns)<=16,'Column bound')
        rows=db.execute('SELECT * FROM "'+table+'"').fetchall();counts[table]=len(rows)
        need(len(rows)<=(4096 if table in {'events','sd_mutations','sd_activations','sd_activation_versions'} else 1024),'Table count bound')
        for row in rows:
            amount=512
            for value in row:
                if value is None:continue
                if type(value) in (int,float):amount+=8
                elif type(value) is str:amount+=len(value.encode())
                elif type(value) is bytes:amount+=len(value)
                else:raise AssertionError('Unexpected SQLite cell type')
            need(amount<={'events':1536,'operations':8192,'replay_keys':1024}.get(table,66*1024),'Whole-row charge bound')
            if table=='meta':metadata+=amount
            elif table in FIXED:fixed+=amount
            elif table in {'sd_meta','sd_route'}:base+=amount
            else:
                groups=finite if table in FINITE else standing
                key=row[columns.index((FINITE if table in FINITE else STANDING)[table])]
                groups[key]=groups.get(key,0)+amount
    need(metadata<=16384 and fixed<=496*1024 and base<=512*1024,'Independent fixed/base reserve bounds')
    need(len(finite)<=16 and len(standing)<=16 and all(v<=65536 for v in finite.values()) and
         all(v<=917504 for v in standing.values()),'Owner reserve bounds')
    total=fixed+metadata+base+sum(finite.values())+sum(standing.values());need(total<=16*1024*1024,'Unchanged16MiB ceiling')
    return {'chargedLogicalBytes':total,'fixedBytes':fixed+metadata,'standingBaseBytes':base,
        'finiteOwners':finite,'standingOwners':standing,'maxLogicalBytes':16*1024*1024,'protectedCapacity':False},counts


# Independent fixed-domain construction and retained catalog identity joins.
CONFIG={'lowerDemand':20000,'upperDemand':30000,'requiredImprovement':0,'minimumOnFeedback':500,
 'samplePeriod':10,'demandMaxAge':100,'feedbackMaxAge':100,'minimumOnDwell':0,'minimumOffDwell':0,
 'feedbackWindow':50,'offCode':0,'onCode':1,'lossCode':0,'policy':0}
LIMITS={'activationCap':100,'commandedOnMs':500,'leaseHorizonMs':1000}
CONFIG_BYTES=struct.pack('>iiii6H4B',20000,30000,0,500,10,100,100,0,0,50,0,1,0,0)
QUAL_CASES=['wire_and_refusals','replay_and_renewal','ledger_ack_resume','pending_ack_and_feedback',
 'source_and_clock_faults','late_dispatch_and_limits','prepared_expiry_and_revoke','loss_witness_ordering',
 'acquisition_boundaries','interrupted_feedback_ack','finite_interoperation','stop_backpressure']
COMPILER='hms.standing-compiler/literal-native-domain/0.1'


def compiled(artifact,installation,manifest):
    source=identity('HMS-STANDING-NATIVE-SOURCES-v0.1',manifest['sourcePins'])
    compiler=identity('HMS-STANDING-COMPILER-v0.1',{'profile':COMPILER,
        'hostImplementationDigest':installation['hostImplementationDigest'],
        'sourceDigest':source,'domainDigest':manifest['domainDigest']})
    return {'profile':COMPILER,'artifactDigest':identity('HMS-STANDING-PAT-v0.1',artifact),
        'compilerDigest':compiler,'installationDigest':identity('HMS-STANDING-INSTALLATION-v0.1',installation),
        **{k:installation[k] for k in ('hostImplementationDigest','driverImageDigest','driverSourceDigest','qualificationImageDigest')},
        'sourceDigest':source,'domainDigest':manifest['domainDigest'],'configurationHex':CONFIG_BYTES.hex(),
        'kernel':1,'resourceMask':3,'sourceEpochs':[1,1],'limits':LIMITS,'evidenceMode':'simulation',
        'physicalEligible':False,'protectedCapacity':False}


def catalog(db,name,meta,installation,manifest,qualification):
    installation_id=identity('HMS-STANDING-INSTALLATION-v0.1',installation)
    artifacts=db.execute('SELECT digest,document,state,evaluation,decision FROM sp_artifacts ORDER BY digest').fetchall()
    evaluations=db.execute('SELECT digest,artifact,evaluator,run_id,document FROM sp_evaluations').fetchall()
    decisions=db.execute('SELECT digest,artifact,document FROM sp_decisions').fetchall()
    need(len(artifacts)==(2 if name=='management_replays' else 1) and len(evaluations)==len(decisions)==1,'Exact original catalog history')
    a=[entry for entry in artifacts if entry[2]=='promoted'];need(len(a)==1,'One eligible original artifact');a=a[0]
    artifact=doc(a[1],65536);artifact_id=identity('HMS-STANDING-PAT-v0.1',artifact)
    need(a[0]==artifact_id and artifact['configuration']==CONFIG and artifact['limits']==LIMITS and
         artifact['id']=='standing-native-golden-v1' and artifact['parameters']=={} and artifact['kernel']==1,'Literal installed PAT')
    need(artifact['requirements']=={'installationDigest':installation_id,**{k:installation[k] for k in
        ('hostImplementationDigest','driverImageDigest','driverSourceDigest','qualificationImageDigest')}} and
         artifact['qualificationDomainDigest']==manifest['domainDigest'],'Artifact binds actual installed images and domain')
    current=compiled(artifact,installation,manifest);e=evaluations[0];d=decisions[0]
    evaluation=doc(e[4],16384);decision=doc(d[2],16384)
    need(e[:4]==(identity('HMS-STANDING-EVALUATION-v0.1',evaluation),artifact_id,'standing-native-controls-v1','native-standing-original:4') and
         a[3]==e[0] and d[:2]==(identity('HMS-STANDING-PROMOTION-v0.1',decision),artifact_id) and a[4]==d[0],'Canonical catalog keyed identities')
    expected_evidence={'profile':'hms.standing-native-attempt/0.1','producerDigest':identity('HMS-STANDING-NATIVE-PRODUCER-v0.1',manifest),
        **{k:manifest[k] for k in ('evaluatorId','runId','runnerDigest','binaryDigest','domainDigest','receiptDigest','reservationDigest','stdoutDigest','stderrDigest')},
        'attemptId':'native-standing-attempt:4','sourceDigest':current['sourceDigest'],'caseClosure':QUAL_CASES,
        'cases':12,'assertions':638,'physicalQualification':False,'protectedCapacity':False}
    expected_evaluation={'profile':'hms.standing-evaluation/original-native/0.1','artifactDigest':artifact_id,
        'compilerDigest':current['compilerDigest'],'installationDigest':installation_id,'domainDigest':manifest['domainDigest'],
        'evidence':expected_evidence,'outcome':'passed-literal-synthetic-domain'}
    expected_decision={'profile':'hms.standing-promotion/0.1','artifactDigest':artifact_id,'evaluationDigest':e[0],
        'compilerDigest':current['compilerDigest'],'installationDigest':installation_id,'domainDigest':manifest['domainDigest'],
        'authority':meta['authority'],'deployment':'simulation:standing-host','physicalEligible':False,'protectedCapacity':False}
    need(canon(evaluation)==canon(expected_evaluation) and canon(decision)==canon(expected_decision),'Original evaluation/promotion evidence, no caller-manufactured qualification')
    cm=dict(db.execute('SELECT key,value FROM sp_meta'))
    need(cm=={'profile':'hms.standing-catalog/original-native/0.1','installation':installation_id,
        'producer':expected_evidence['producerDigest'],'revision':'6' if name=='management_replays' else '3'},'Exact catalog management revision')
    if name=='management_replays':
        other=next(x for x in artifacts if x[0]!=artifact_id);value=doc(other[1],65536)
        expected=copy.deepcopy(artifact);expected['id']='other:label'
        need(value==expected and other==(identity('HMS-STANDING-PAT-v0.1',value),other[1],'candidate',None,None),'Rejected original-run reassociation leaves only unlabeled-evidence candidate')
    return artifact,current,evaluation,decision,int(cm['revision'])




def audit_prefix(path,partial,interpreter_sha,manifest,qualification):
    before=digest(path);size=path.stat().st_size;need(size==344064 and size<=32*1024*1024,'Actual failed DB under original file bound')
    sidecars=lambda:any(Path(str(path)+suffix).exists() for suffix in ('-journal','-wal','-shm'))
    need(not sidecars(),'Closed retained DB without sidecars')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        db.execute('PRAGMA query_only=ON');need(db.execute('PRAGMA query_only').fetchone()[0]==1,'Read-only audit connection')
        need(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)] and not db.execute('PRAGMA foreign_key_check').fetchall(),'Retained SQLite integrity')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        charge,counts=charges(db,tables);meta=dict(db.execute('SELECT key,value FROM meta'))
        installed=doc(db.execute('SELECT document FROM sd_meta').fetchone()[0],65536);installation=installed['installation']
        route=doc(db.execute('SELECT document FROM sd_route').fetchone()[0],4096)
        need(installed['authorityId']==meta['authority'] and installed['installationDigest']==identity('HMS-STANDING-INSTALLATION-v0.1',installation),'Canonical installed authority identity')
        host=identity('HMS-STANDING-HOST-IMAGE-v0.1',{'sources':{p:'sha256:'+digest(HERE/'project'/p) for p in HOST_SOURCES},
            'interpreter':'sha256:'+interpreter_sha,'dependencyScope':'original-source-pins;trusted-python-stdlib-loader-validation-packages'})
        driver=identity('HMS-STANDING-PIPE-SOURCES-v0.1',{p:'sha256:'+digest(HERE/'project'/p) for p in DRIVER_SOURCES})
        need(installation['hostImplementationDigest']==host and installation['driverSourceDigest']==driver and
             installation['driverImageDigest']=='sha256:'+NATIVE_SHA and installation['qualificationImageDigest']=='sha256:'+QUALIFIER_SHA,'Exact validated host and original native closure')
        artifact,current,evaluation,decision,revision=catalog(db,'mutation_capacity',meta,installation,manifest,qualification)
        need(not any(counts[t] for t in ('operations','replay_keys','events','sd_activations','sd_activation_versions','sd_conflicts','sd_episodes')),'No finite work/activation/episode/conflict introduced in failed prefix')
        stored=db.execute('SELECT id,principal,deployment,namespace,caller_key,request_digest,document FROM sd_deployments').fetchall()
        need(len(stored)==1,'Exactly one retained original deployment');sql=stored[0];row=doc(sql[6],32768);mapping=row['mapping'];identifier=row['id']
        need(tuple(row[k] for k in ('id','principal','deployment','namespace','key','requestDigest'))==sql[:6],'Canonical SQL-keyed deployment')
        need(row['requestDigest']==mapping['requestDigest']==identity('HMS-STANDING-REQUEST-v0.1',row['request']) and
             row['key']==row['request']['deploymentKey']=='application' and row['namespace']==row['request']['replayNamespace'],'Original immutable request/key')
        base=dict(mapping);base.pop('deploymentDigest');need(mapping['deploymentDigest']==identity('HMS-STANDING-DEPLOYMENT-v0.1',base),'Frozen mapping digest')
        need(mapping['authorityId']==meta['authority'] and mapping['installationDigest']==installed['installationDigest'],'Mapping installed identity')
        selection=mapping['selection'];need(selection['artifact']==artifact and selection['compilation']==current and
            selection['evaluation']==evaluation and selection['decision']==decision and selection['catalogRevision']==revision,'Original qualified selection retained')
        need(set(mapping['resourceProof']['expandedClaims']['control'])=={'atom:demand','atom:output'} and
             {x['resource'] for x in mapping['claims']}=={'atom:demand','atom:output','atom:slot'} and len(mapping['claims'])==3,'Two physical atoms plus actual driver lifecycle slot')
        owned=db.execute('SELECT resource,fence FROM claims WHERE operation_id=? ORDER BY resource',(identifier,)).fetchall()
        need(owned==sorted((x['resource'],x['fence']) for x in mapping['claims']) and counts['claims']==3 and
             [r[0] for r in db.execute('SELECT instance_id FROM resource_owner_instances WHERE owner_id=? ORDER BY instance_id',(identifier,))]==['native:finite','native:standing'],'Shared ownership remains held')
        for field in ('retired','disputed','effectUnknown','recoveryRequired','sequenceUncertain','transportUncertain'):
            need(row[field] is False,'Exact retained failed-prefix flag '+field)
        need(row['everPossiblyActed'] is True and row['openState']=='accepted' and row['revoke'] is None and
             row['mutationSequence']==row['highWater']==row['collected']==row['acknowledged']==0 and row['revision']==1 and
             row['ownerEpoch']==int(meta['owner_epoch'])==1 and row['hostRevision']==224,'Accepted OPEN only, no fabricated settlement or reopening')
        need(route['boot']==mapping['boot']=='1' and route['standingFloor']==mapping['standingNumber']==1 and
             route['generation']==mapping['generation']==2 and route['handle']==mapping['handle']==1 and route['fences']==mapping['fences']==[1,1,0,0,0,0,0,0] and
             route['tx']==339 and route['rx']==227,'Actual durable route including unsent read-only reservation gap')
        opened=bytes.fromhex(row['open']);need(len(opened)==134 and opened[:2]==b'\x02\x40' and row['openTx']==6,'Original OPEN request');reference(opened,mapping)
        need(opened[47:79]==CONFIG_BYTES and opened[79]==3 and [u32(opened,80+4*i) for i in range(8)]==mapping['fences'] and
             u16(opened,44)==1 and opened[46]==32 and u64(opened,112)==1000 and opened[120:122]==bytes(2) and
             u32(opened,122)==100 and u32(opened,126)==u32(opened,130)==1,'Literal qualified native OPEN')
        requests={};responses={};opcounts={};last_tx=last_rx=0;states=[]
        need(len(partial['trace'])==454,'Actual partial trace454 packets')
        for entry in partial['trace']:
            need(set(entry)=={'direction','session','sequence','raw'},'Closed partial packet record');uint(entry['sequence'],2**32-1)
            body=bytes.fromhex(entry['raw']);need(body.hex()==entry['raw'] and 2<=len(body)<=192 and body[0]==2,'Canonical bounded original v2 bytes')
            if entry['direction']=='request':
                op=body[1];need(op in (1,16,64,67) and entry['sequence']>last_tx and entry['session']==(0 if op==1 else 1),'No observed START or other effect send beyond original OPEN')
                requests[entry['sequence']]=entry;last_tx=entry['sequence'];opcounts[op]=opcounts.get(op,0)+1
                if op>=64:reference(body,mapping)
                if op==67:need(len(body)==49 and body[44:]==bytes(5),'Original read-only page0 STATUS')
            else:
                tx=u32(body,2);need(entry['direction']=='response' and entry['session']==1 and len(body)>=66 and
                    entry['sequence']==last_rx+1 and tx in requests and tx not in responses and
                    body[1]==bytes.fromhex(requests[tx]['raw'])[1]|128 and body[6]==0,'Exact successful original response association')
                last_rx=entry['sequence'];responses[tx]=entry
                if body[1]>=192:reference(body,mapping,8)
                if body[1]==195:
                    state=body[66:];need(len(state)==124 and state[0]==2 and u32(state,1)==1 and u32(state,5)==0 and
                        u64(state,29)==1000 and u32(state,37)==u32(state,41)==0 and state[89]==1 and state[92:94]==bytes((3,0)) and
                        u16(state,96)==96 and u32(body,50)==1 and u32(body,54)==u32(body,58)==u32(body,62)==0,'Observed prepared STATUS with zero activation/ACK/mutation prefix')
                    states.append(state)
        need(opcounts=={1:4,16:1,64:1,67:221} and len(requests)==len(responses)==227 and set(requests)==set(responses) and
             last_tx==337 and last_rx==route['rx'] and len(set(states))==1,'Exact observed partial closure, no final-snapshot inference')
        need(requests[6]['raw']==row['open'] and 338 not in requests and 339 not in requests,'Prepared START and separately reserved STATUS have no observed send')
        envelopes=[row['openReply'],row['lastStatus']];mutations=[]
        for number,key,sequence,body in db.execute('SELECT number,host_key,endpoint_sequence,document FROM sd_mutations ORDER BY number'):
            item=doc(body,1536);mutations.append(item);payload=bytes.fromhex(item['body'])
            need((item['number'],item['hostKey'],item['endpointSequence'])==(number,key,sequence) and
                 number==len(mutations) and key=='never-start:'+str(number-1) and sequence==1,'Every original retained mutation key and order')
            need(len(payload)==66 and payload[:2]==b'\x02\x41','Original START body');reference(payload,mapping)
            need(item['bodyDigest']=='sha256:'+sha(payload) and u32(payload,44)==u32(payload,48)==1 and payload[52:]==bytes(14) and
                 item['leaseUntil']==item['ack']==0 and item['opcode']==65 and item['tx']==8+3*(number-1) and item['tx'] not in requests,'Unchanged original never-sent request identity')
            if number<=110:
                need(item['state']=='never_handed_off' and item.get('settlement')=='durable-prepared-never-possible' and item['reply'] is not None,'Original110 explicit local abandonment proofs')
                req,res=envelope(item['reply'],mapping);envelopes.append(item['reply'])
                need(req[1]==67 and res[6]==0 and u32(res,54)==0 and item['reply']['tx']==item['tx']+1,'Exact unchanged-sequence STATUS used for abandonment')
            else:need(number==111 and item['state']=='prepared' and item['reply'] is None and 'settlement' not in item,'Last original prepared request remains unresolved, not falsely abandoned')
        need(len(mutations)==111 and counts['sd_mutations']==111,'Actual111 retained mutations, not128')
        need(len({m['body'] for m in mutations})==1,'Repeated intent content retains111 distinct original keys')
        for env in envelopes:
            req,res=envelope(env,mapping);need(env['tx'] in requests and requests[env['tx']]['raw']==env['request'] and
                responses[env['tx']]['sequence']==env['rx'] and responses[env['tx']]['raw']==env['response'],'Every retained envelope joins actual observed wire identity')
        need(row['lastStatus']['tx']==337,'Latest retained read precedes final prepared reservation')
        return {'databaseSha256':before,'databaseBytes':size,'charge':charge,'retainedMutations':111,
            'neverHandedOffMutations':110,'preparedMutations':1,'preparedKey':'never-start:110','preparedTx':338,
            'durableTxHighWater':339,'lastObservedRequestTx':337,'lastObservedResponseRx':227,
            'observedPackets':454,'observedStatusReplies':221,'identicalObservedStatusBodies':True,
            'retainedClaims':3,'activations':0,'episodes':0,'retired':False,'openState':'accepted',
            'fullFinalNativeSnapshotAvailable':False,'full128RecordWorkloadCompleted':False}
    finally:
        db.close();need(digest(path)==before and not sidecars(),'Read-only DB bytes and sidecar absence unchanged')


def owned(record,expected_exit,cpu,memory,parent=None):
    for field in ('pid','parent','group','session','startTicks'):uint(record[field]);need(record[field]>0,'Positive retained owned identity')
    need(record['reaped'] is True and record['exitCode']==expected_exit,'Actual expected exit/reap, failure is not success')
    if parent is not None:need(record['parent']==parent,'Exact direct-parent role')
    need(type(record['cpuSeconds']) in (int,float) and 0<=record['cpuSeconds']<=cpu and
         type(record['peakRSSKiB']) is int and 0<=record['peakRSSKiB']<=memory,'Observed per-process usage under original bounds')
    need(not Path('/proc',str(record['pid'])).exists(),'Current observed absence, no PID-derived signal authority')
    return (record['pid'],record['startTicks'])


def main():
    need(len(sys.argv)==1 and not sys.flags.optimize,'Fixed assertion-enabled retained-data audit')
    source_sha=digest(Path(__file__))
    need(digest(HERE/'SOURCE-REVIEW.json')==REVIEW_SHA and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA,'Exact frozen source and actual failed attempt inventory')
    review=data(HERE/'SOURCE-REVIEW.json',False);inputs=data(HERE/'source-pins.json',False);pins=data(HERE/'AUDIT-INPUT-PINS.json',False)
    need(len(review['files'])==289 and review['inputBytes']==5476258 and pins['sourceReviewSha256']==REVIEW_SHA,'Original289 reviewed inputs')
    def stable():
        for row in review['files']:need((HERE/row['path']).lstat().st_size==row['bytes'] and digest(HERE/row['path'])==row['sha256'],'Frozen source bytes unchanged')
        total=0
        for key in ('parentPacket','secondParentPacket','thirdParentPacket'):
            spec=inputs[key];parent=REPO/spec['path'];need(digest(parent/'index.json')==spec['indexSha256'],'Exact sealed parent index')
            rows=data(parent/'index.json',False)['files'];inventory(parent,rows,('index.json',));total+=len(rows)
        need(total==5969,'All three sealed parent inventories')
        need(digest(REPO/inputs['previousReceipt']['path'])==inputs['previousReceipt']['sha256']=='be776f2d1bce37cd8adf88508f45f9fe7d060f782483fa74f35c3a38cb6e54ad','Exact continuation106 receipt')
        receipt=REPO/inputs['publicReceipt']['path'];need(digest(receipt)==inputs['publicReceipt']['sha256'],'Public baseline receipt')
        public=data(receipt,False)['files'];need(len(public)==244,'Public244')
        for row in public:need(digest(REPO/row['path'])==row['sha256'],'Exact unchanged public input')
        need(len(inputs['copies'])==262 and len(inputs['originalProvenance'])==18,'Original reuse/provenance scope')
        for row in inputs['copies']+inputs['originalProvenance']:
            need(digest(REPO/row['source'])==digest(HERE/row['copy'])==row['sha256'] and (HERE/row['copy']).stat().st_size==row['bytes'],'Exact original/copy join')
        need(inputs['productionChangedFromSelectionReuse'] is False and review['modifiedProductionFiles']==[] and
             sum(x['copy'].startswith('project/') for x in inputs['copies'])==259,'Byte-exact validated project closure')
    stable();native=Path(inputs['nativeImage']);qualification=Path(inputs['qualificationRoot']);parent=REPO/inputs['parentPacket']['path']
    need(native==parent/'host-attempt04/standing-host-pipe' and qualification==parent/'host-attempt04/qualification','Original absolute native and qualifier roots')
    need(digest(native)==NATIVE_SHA and digest(qualification/'standing-controls')==QUALIFIER_SHA,'Original native images unchanged')
    manifest=data(qualification/'manifest.json',False);receipt=data(qualification/'receipt.json');reservation=data(qualification/'reservation.json')
    for key in ('evaluatorId','runId','runnerDigest','domainDigest','sourcePins','binaryPath','binaryDigest','argv'):
        need(manifest[key]==receipt[key]==reservation[key],'Original qualifier common identity '+key)
    need(manifest['argv']==[str(qualification/'standing-controls')] and manifest['runId']=='native-standing-original:4' and
         manifest['evaluatorId']=='standing-native-controls-v1' and manifest['binaryDigest']=='sha256:'+QUALIFIER_SHA and
         receipt['attemptId']==reservation['attemptId']=='native-standing-attempt:4' and receipt['exitCode']==receipt['terminationSignal']==0 and
         receipt['ownership']['cleanupComplete'] is True and receipt['ownership']['reaped'] is True and receipt['ownership']['openChildHandles']==0,'Original completed12-case qualifier, no rerun/reassociation')
    for field,file in (('receiptDigest','receipt.json'),('reservationDigest','reservation.json'),('stdoutDigest','stdout'),('stderrDigest','stderr')):
        need(manifest[field]=='sha256:'+digest(qualification/file),'Original qualifier retained byte identity')
    need(receipt['reservationDigest']==manifest['reservationDigest'] and receipt['stdoutDigest']==manifest['stdoutDigest'] and receipt['stderrDigest']==manifest['stderrDigest'] and
         raw(qualification/'stdout')==b'{"cases":12,"assertions":638,"physical_qualification":false}\n' and not raw(qualification/'stderr'),'Original exact qualifier output')
    need(len(manifest['sourcePins'])==12,'Original source closure')
    for name,value in manifest['sourcePins'].items():need(value=='sha256:'+digest(HERE/'project'/name),'Original C source pin')
    domain={'profile':'hms.standing-native-domain/0.1','kernel':1,'mask':3,'parameters':{},'configuration':CONFIG,'limits':LIMITS,
        'evidenceMode':'simulation','sourceEpochs':[1,1],'caseClosure':QUAL_CASES,'sourcePins':manifest['sourcePins'],'physicalEligible':False,'protectedCapacity':False}
    need(manifest['domainDigest']==identity('HMS-STANDING-NATIVE-DOMAIN-v0.1',domain),'Independent literal native-domain identity')
    spec=pins['attempt'];need(spec['path']=='selection-capacity-mutation-attempt01' and len(spec['files'])==299,'One actual original failed attempt, no retry')
    attempt=HERE/spec['path'];inventory(attempt,spec['files']);result=data(attempt/'RESULTS.json');inner=data(attempt/'state/CONTROL-RESULTS.json')
    partial=data(attempt/'state/PARTIAL-EVIDENCE.json');intent=data(attempt/'intent.json')
    need(digest(attempt/'RESULTS.json')==spec['resultSha256']=='a823c6f80894dc0a53ecd3098e5cb4e12627e456fb0763eba62c1265540f0708' and
         digest(attempt/'state/CONTROL-RESULTS.json')==spec['controlResultSha256']=='f47682d5e5854ea35da00d00711094da6ab6bb1125efe19f4666ac778ee4ea17' and
         digest(attempt/'state/PARTIAL-EVIDENCE.json')==spec['partialEvidenceSha256']=='e65f273617acc0d1ea1639e9a2822f8bbcaae1d44fdbca38f157b7e414860e8d','Exact actual terminal/partial receipts')
    inventory(attempt/'frozen',review['files'],('SOURCE-REVIEW.json',));need(digest(attempt/'frozen/SOURCE-REVIEW.json')==REVIEW_SHA,'Exact executed frozen manifest')
    need(intent['sourcePins']=={**{r['path']:r['sha256'] for r in review['files']},'SOURCE-REVIEW.json':REVIEW_SHA},'All290 executed frozen inputs')
    need(result['passed'] is inner['passed'] is False and result['reason']=='RuntimeError: CONTROL_WALL_LIMIT' and
         inner['failure']==inner['terminalFailure']=='RuntimeError: Control interrupted 15' and result['controlProfile']==inner['profile']==intent['controlProfile']=='mutation' and
         inner['cases']==[] and inner['checks']==1 and inner['originalChecks']==partial['originalChecks']==333,'Failed workload,333 partial original assertions are not passing case checks')
    need(result['innerReceiptObserved'] is False and result['innerCases'] is result['innerReaps'] is result['originalChecks'] is None,'Outer absence of reduced inner receipt is not zero-child evidence')
    need(result['attemptNumber']==intent['attemptNumber']==1 and result['priorProfileAttemptResults']==intent['priorProfileAttemptResults']==[] and
         intent['controlProfilePreviouslyExecuted'] is False and intent['cases']==['mutation_capacity'],'First original fixed attempt')
    need(intent['wallSeconds']==intent['cpuSeconds']==30 and intent['addressBytes']==512*1024*1024 and
         intent['childCpuSeconds']==5 and intent['childAddressBytes']==256*1024*1024 and
         intent['fileBytes']==result['fileBytes']==32*1024*1024 and intent['nativeChildFileBytes']==1024*1024 and intent['openFiles']==64 and
         intent['cleanupSeconds']==8 and intent['termGraceSeconds']==3 and intent['stateDiskBytes']==96*1024*1024,'Original unchanged full-capacity profile bounds')
    argv=[intent['interpreter'],'-I','-B',str(attempt/'frozen/capacity_controls.py'),'mutation',str(attempt/'state'),
          str(native),str(qualification),str(qualification/'manifest.json'),str(attempt/'frozen/owner/libharness-owner.so')]
    need(intent['argv']==argv and intent['expectedInnerReaps']==intent['expectedOuterReaps']==1 and
         intent['nativeImageSha256']==NATIVE_SHA and intent['originalQualificationRoot']==str(qualification) and intent['originalQualificationRunId']=='native-standing-original:4','Fixed original command/peer/qualifier')
    need(intent['originalWorkloadSha256']==result['originalWorkloadSha256']==inner['originalWorkloadSha256']==digest(HERE/'boundary_controls.py')=='01e91d85d9da351af7f1c8dc8cd42bf375898959ff1264754408311042517e5d','Exact original unshortened workload source')
    interpreter_sha=intent['interpreterSha256'];need(digest(intent['interpreter'])==interpreter_sha and
         result['heldInterpreterBefore']==result['heldInterpreterAfter'] and result['heldInterpreterBefore']['sha256']==interpreter_sha,'Held/current interpreter before and after')
    for report in (result,inner):need(report['ownerEmpty'] is True and report['ownerClosed'] is True and not report['cleanupErrors'] and not report['interruptsPending'] and not report['terminalPendingSignals'],'Clean orderly failure settlement')
    need(not result['unexpectedChildrenObserved'] and len(result['outerChildrenReaped'])==1 and result['controlExit']==result['outerChildrenReaped'][0],'Exactly one outer control reap')
    outer=result['controlExit'];identities=[owned(outer,1,30,512*1024)]
    start=data(attempt/'control.started.json');need(all(outer[k]==v for k,v in start.items()),'Outer original registration to failure exit reap')
    need(len(inner['nativeChildrenReaped'])==1 and partial['nativeChildrenReaped']==inner['nativeChildrenReaped'],'Independently retained one native reap despite null outer reduction')
    native_reap=inner['nativeChildrenReaped'][0];identities.append(owned(native_reap,0,5,256*1024,outer['pid']))
    need(all(native_reap[k]==v for k,v in partial['nativeStartIdentity'].items()) and len(set(identities))==2,'Original native start association and two distinct identities')
    need(partial['case']=='mutation_capacity' and partial['completed'] is partial['fullFinalSnapshot'] is False and partial['boundaryNotes']=={} and
         inner['partialEvidenceFile']=='PARTIAL-EVIDENCE.json' and partial['failure']==inner['failure'],'Partial memory trace only, no reached120/126/128 note or final snapshot')
    need(not (attempt/'state/mutation_capacity/evidence.json').exists(),'No successful case evidence fabricated')
    printed=json.loads(raw(attempt/'control.stdout'));expected=dict(inner);expected.pop('terminalFailure');expected.pop('terminalPendingSignals')
    need(printed==expected and b'RuntimeError: Control interrupted 15' in raw(attempt/'control.stderr'),'Final inner stdout and later terminal failure correction retained')
    need(result['controlTerminalObservedMonotonicNs'] is result['controlObservedElapsedMonotonicNs'] is None and
         type(result['controlStartedMonotonicNs']) is str and result['controlStartedMonotonicNs'].isdigit() and
         int(result['elapsedMonotonicNs'])>=30_000_000_000,'No invented within-limit completion observation; final includes cleanup')
    dbpath=attempt/'state/mutation_capacity/authority.db';need(digest(dbpath)=='26cd3b6046e64f960d2b5c91e3a012ed82d105897b46204ddb3784c1ca3cd19e','Actual failed DB pin')
    database=audit_prefix(dbpath,partial,interpreter_sha,manifest,qualification)
    for report in (intent,result,inner):
        for key in ('productionChangedFromSelectionReuse','qualificationRerun','fullSimultaneousCapacityEstablished','physicalEligible','protectedCapacity','publicMountEligible'):
            need(report[key] is False,'Original limited scope '+key)
    need(result['full128RecordWorkloadCompleted'] is inner['full128RecordWorkloadCompleted'] is False and
         intent['full128RecordWorkloadRequested'] is True and result['oldCapacityFailureRemainsFailed'] is True and
         result['logicalCeilingBytes']==16*1024*1024 and result['publicInputsExact']==244 and result['parentPacketStable'] is True and
         result['actualOwnerDeath'] is inner['actualOwnerDeath'] is False and result['universalContainment'] is False,'Both full-capacity failures remain failures; no widened authority claim')
    stable();inventory(attempt,spec['files'])
    need(digest(Path(__file__))==source_sha and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA and digest(intent['interpreter'])==interpreter_sha,'Audit source/input/interpreter stable through reads')
    output={'profile':'hms.standing-host-selection-capacity-failed-retained-audit/0.1','passed':True,'checks':checks,
        'meaning':'Retained failure evidence joins; the full original capacity workload failed its unchanged wall bound.',
        'auditSourceSha256':source_sha,'auditInputPinsSha256':INPUT_SHA,'sourceReviewSha256':REVIEW_SHA,
        'attemptResultSha256':spec['resultSha256'],'sourceFilesReverified':289,'unchangedReuseFiles':262,'provenanceCopies':18,
        'sealedParentFilesReverified':5969,'publicFilesReverified':244,'attemptFiles':299,
        'completedCases':0,'passingCaseChecks':0,'partialOriginalChecks':333,'wrapperInvocationChecks':1,
        'nativeReaps':1,'outerReaps':1,'ownedIdentitiesCurrentlyAbsent':2,'database':database,
        'observedWithinLimitCompletion':False,'finalElapsedMonotonicNs':result['elapsedMonotonicNs'],
        'controlCpuSeconds':outer['cpuSeconds'],'nativeCpuSeconds':native_reap['cpuSeconds'],
        'productionChangedFromSelectionReuse':False,'qualificationRerun':False,'candidateReexecuted':False,
        'full128RecordWorkloadCompleted':False,'oldCapacityFailureRemainsFailed':True,'speedupEstablished':False,
        'actualOwnerDeath':False,'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
    body=canon(output)
    if len(body)>1024*1024:raise AssertionError('Audit receipt bound')
    temporary=HERE/'.AUDIT.json.pending';destination=HERE/'AUDIT.json'
    with temporary.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    os.link(temporary,destination,follow_symlinks=False);fd=os.open(HERE,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd);temporary.unlink();os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'passed':True,'checks':checks,'completedCases':0,'retainedMutations':111,'preparedMutations':1,'attemptFiles':299,'ownedIdentities':2},sort_keys=True))


if __name__=='__main__':main()
