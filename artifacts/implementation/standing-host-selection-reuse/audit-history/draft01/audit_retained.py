"""Data-only retained audit of two original selection-reuse profiles.

Imports no candidate or oracle; launches/signals no child. Reads SQLite with
immutable read-only URI/query_only. Only a new exclusive AUDIT.json is published
after root review and execution. Current /proc absence is observation, never
stored-PID signal authority. Retained control equivalence is audited, not rerun.
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
REVIEW_SHA='25e1be4db68cec9b639667e034656f45fc985923bdf4bc8a2b8ab8a3a060bdb1'
INPUT_SHA='61d8494517a4f388cd48397251e8f3f80748ecde32df03f04bb78271c08de73a'
NATIVE_SHA='5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399'
QUALIFIER_SHA='b89d0a1030768932ace1c9c2da5a4a888d0ae7da46a8a77473b2b145293ff842'
ORACLE_SHA='b1734acbe443501124b2a6965aa9768abd1eb3c3966e57f4945ebc10f801d726'
LIVE=('management_replays','final_evidence_withdrawal','final_artifact_change',
 'renewal_withdrawal','expiry_after_commit','shared_authority','finite_policy_replacement',
 'prepared_mutation_recovery','common_revoke_remains_unresolved')
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


# Source-derived fixed scenario snapshots; all28 selectors are joined, including
# response count and feedback sentinel. RETIRE clears slot fields but not ST_HIGH.
SNAPSHOTS={
 'management_replays':[0,0,0,1,1,1,96,2,2,1,0,0,1,0,3,0,25,0,0,1,1,1,8,0,0,0,25000,4294967295],
 'final_evidence_withdrawal':[0,0,0,1,1,1,96,2,2,1,0,0,1,0,3,0,25,0,0,1,1,1,8,0,0,0,25000,4294967295],
 'final_artifact_change':[0,0,0,1,1,1,96,2,2,1,0,0,1,0,3,0,25,0,0,1,1,1,8,0,0,0,25000,4294967295],
 'renewal_withdrawal':[0,1,0,2,3,0,0,22,2,1,0,0,0,0,0,0,25,0,0,1,1,1,21,0,0,0,25000,4294967295],
 'expiry_after_commit':[0,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,25,0,0,1,1,1,6,0,0,0,25000,4294967295],
 'shared_authority':[0,1,0,1,2,0,0,7,2,1,0,0,0,0,0,0,25,0,0,1,1,1,14,0,0,0,25000,4294967295],
 'finite_policy_replacement':[0,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,25,0,0,1,1,1,3,0,0,0,25000,4294967295],
 'prepared_mutation_recovery':[0,1,0,1,2,0,0,7,2,1,0,0,0,0,0,0,25,0,0,1,1,1,17,0,0,0,25000,4294967295],
 'common_revoke_remains_unresolved':[0,1,0,1,2,5,992,7,2,1,0,0,3,1,3,3,25,0,0,1,1,1,13,3,0,0,25000,4294967295]}
OPCOUNTS={name:{1:6,16:1,64:1} for name in LIVE[:3]}
OPCOUNTS.update({'renewal_withdrawal':{1:8,16:1,64:1,67:7,65:1,66:1,71:1,72:1},
 'expiry_after_commit':{1:4,16:1,67:1},'shared_authority':{1:6,16:1,64:1,67:4,71:1,72:1},
 'finite_policy_replacement':{1:2,16:1},'prepared_mutation_recovery':{1:4,16:1,64:1,67:8,65:1,71:1,72:1},
 'common_revoke_remains_unresolved':{1:4,16:1,64:1,67:6,71:1}})


def audit_trace(entries,route,name,mapping):
    need(type(entries) is list and len(entries)<=2048,'Bounded actual raw trace')
    requests={};responses={};counts={};last_tx=last_rx=0
    for entry in entries:
        need(set(entry)=={'direction','session','sequence','raw'},'Trace shape');uint(entry['session']);uint(entry['sequence'],2**32-1)
        body=bytes.fromhex(entry['raw']);need(body.hex()==entry['raw'] and 2<=len(body)<=192 and body[0]==2,'Original bounded canonical v2 bytes')
        if entry['direction']=='request':
            op=body[1];need(op in OPCOUNTS[name] and entry['sequence']>last_tx and entry['session']==(0 if op==1 else 1),'Closed request opcode and original non-retried sequence')
            last_tx=entry['sequence'];requests[last_tx]=entry;counts[op]=counts.get(op,0)+1
            if op>=64:reference(body,mapping)
            if op==67:need(len(body)==49 and body[44:]==bytes(5),'Actual read-only page0 STATUS')
        else:
            need(entry['direction']=='response' and entry['session']==1 and len(body)>=66 and entry['sequence']==last_rx+1,'Complete decoded reply sequence')
            tx=u32(body,2);need(tx in requests and tx not in responses and body[1]==bytes.fromhex(requests[tx]['raw'])[1]|128,'Unique actual response request join')
            need(body[6]==(8 if name=='expiry_after_commit' and body[1]==195 else 0),'Only expected NOT_SEEN response, all other exchanges successful')
            if body[1]>=192 and body[6]==0:reference(body,mapping,8)
            last_rx=entry['sequence'];responses[tx]=entry
    need(counts==OPCOUNTS[name] and set(requests)==set(responses) and last_tx==route['tx'] and
         last_rx==route['rx']==SNAPSHOTS[name][22],'Exact original trace closure and route counters')
    return requests,responses


def audit_database(path,name,evidence,interpreter_sha,manifest,qualification):
    before=digest(path);size=path.stat().st_size;need(size<=1024*1024,'Unchanged1MiB profile DB bound')
    sidecars=lambda:any(Path(str(path)+s).exists() for s in ('-journal','-wal','-shm'))
    need(not sidecars(),'Closed DB without recovery sidecar')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        db.execute('PRAGMA query_only=ON');need(db.execute('PRAGMA query_only').fetchone()[0]==1,'Read-only connection')
        need(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)] and not db.execute('PRAGMA foreign_key_check').fetchall(),'Retained SQLite integrity')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        charge,counts=charges(db,tables);meta=dict(db.execute('SELECT key,value FROM meta'))
        installed=doc(db.execute('SELECT document FROM sd_meta').fetchone()[0],65536)
        installation=installed['installation'];route=doc(db.execute('SELECT document FROM sd_route').fetchone()[0],4096)
        need(installed['authorityId']==meta['authority'] and installed['installationDigest']==identity('HMS-STANDING-INSTALLATION-v0.1',installation),'Independent installed identity')
        host=identity('HMS-STANDING-HOST-IMAGE-v0.1',{'sources':{p:'sha256:'+digest(HERE/'project'/p) for p in HOST_SOURCES},
            'interpreter':'sha256:'+interpreter_sha,'dependencyScope':'original-source-pins;trusted-python-stdlib-loader-validation-packages'})
        driver=identity('HMS-STANDING-PIPE-SOURCES-v0.1',{p:'sha256:'+digest(HERE/'project'/p) for p in DRIVER_SOURCES})
        need(installation['hostImplementationDigest']==host==evidence['hostImplementationDigest'] and installation['driverSourceDigest']==driver and
             installation['driverImageDigest']=='sha256:'+NATIVE_SHA and installation['qualificationImageDigest']=='sha256:'+QUALIFIER_SHA,'Actual changed host/unchanged native closure')
        artifact,current,evaluation,decision,revision=catalog(db,name,meta,installation,manifest,qualification)
        need(evidence['capacity']==charge and evidence['route']==route and set(evidence['native'])=={str(i) for i in range(28)},'Independent accounting/route/full snapshot association')
        for i,value in enumerate(SNAPSHOTS[name]):uint(evidence['native'][str(i)],2**64-1);need(evidence['native'][str(i)]==value,'Exact native selector '+str(i))
        operations=db.execute('SELECT id,principal,deployment,digest,intent,admission,state,cancel_state,verification,may_have_acted,sequence,attempt_id,owner_epoch FROM operations').fetchall()
        need(len(operations)==(1 if name in ('shared_authority','finite_policy_replacement') else 0),'Exact finite history count')
        for op in operations:
            intent=doc(op[4],65536);admission=doc(op[5],8192)
            need(op[1:4]==('native-standing-owner','simulation:standing-host',identity('HMS-INTENT-JCS-SHA256-v0.1',intent)) and
                 op[6:]==('canceled','confirmed','unverified',0,2,None,1),'Finite replacement/admission remains canceled without dispatch')
            need(admission['resources']==['atom:demand','atom:output','atom:slot'] and not db.execute('SELECT 1 FROM claims WHERE operation_id=?',(op[0],)).fetchone(),'Shared three finite claims released by cancellation')
            need(len(db.execute('SELECT * FROM replay_keys WHERE operation_id=?',(op[0],)).fetchall())==1,'One original finite replay key')
            events=db.execute('SELECT sequence,kind,payload FROM events WHERE operation_id=? ORDER BY sequence',(op[0],)).fetchall()
            need([x[0] for x in events]==[1,2] and [x[1] for x in events]==['accepted','canceled_before_dispatch'],'Original finite accepted/canceled events')
            for event in events:doc(event[2],65536)
        stored=db.execute('SELECT id,principal,deployment,namespace,caller_key,request_digest,document FROM sd_deployments').fetchall()
        need(len(stored)==(0 if name=='finite_policy_replacement' else 1),'Exact deployment count')
        if not stored:
            need(not any(counts[t] for t in STANDING) and counts['claims']==0 and route['standingFloor']==0 and route['fences']==[0]*8,'No standing admission after finite policy replacement')
            audit_trace(evidence['trace'],route,name,None)
            return {'case':name,'databaseSha256':before,'databaseBytes':size,'charge':charge,'deployments':0,'finiteOperations':1,'retainedClaims':0},(artifact,current,installation)
        sql=stored[0];row=doc(sql[6],32768);mapping=row['mapping'];request=row['request'];identifier=row['id']
        need(tuple(row[k] for k in ('id','principal','deployment','namespace','key','requestDigest'))==sql[:6],'Canonical deployment SQL keys')
        need(row['requestDigest']==identity('HMS-STANDING-REQUEST-v0.1',request)==mapping['requestDigest'],'Original request identity')
        base=dict(mapping);base.pop('deploymentDigest');need(mapping['deploymentDigest']==identity('HMS-STANDING-DEPLOYMENT-v0.1',base),'Frozen deployment mapping identity')
        need(mapping['authorityId']==meta['authority'] and mapping['installationDigest']==installed['installationDigest'] and
             row['key']==request['deploymentKey']=='application' and row['namespace']==request['replayNamespace'],'Exact authority/original replay identity')
        selection=mapping['selection'];need(selection['artifact']==artifact and selection['compilation']==current and selection['evaluation']==evaluation and
             selection['decision']==decision and selection['catalogRevision']==revision,'Mapping binds exact current qualified catalog selection')
        need(set(mapping['resourceProof']['expandedClaims']['control'])=={'atom:demand','atom:output'} and
             {x['resource'] for x in mapping['claims']}=={'atom:demand','atom:output','atom:slot'} and len(mapping['claims'])==3,'Physical2 plus installed lifecycle slot actual3')
        need([r[0] for r in db.execute('SELECT instance_id FROM resource_owner_instances WHERE owner_id=? ORDER BY instance_id',(identifier,))]==['native:finite','native:standing'],'One shared alias owner')
        owned=db.execute('SELECT resource,fence FROM claims WHERE operation_id=? ORDER BY resource',(identifier,)).fetchall()
        retired=name in ('renewal_withdrawal','shared_authority','prepared_mutation_recovery')
        need(row['retired'] is retired and owned==([] if retired else sorted((x['resource'],x['fence']) for x in mapping['claims'])),'Claims released only for retained accepted RETIRE')
        need(counts['claims']==len(owned) and not row['disputed'] and not row['effectUnknown'] and row['everPossiblyActed'] is True,'No unaccounted shared claims or fabricated novelty')
        for field in ('retired','disputed','effectUnknown','recoveryRequired','sequenceUncertain','transportUncertain','everPossiblyActed'):need(type(row[field]) is bool,'Exact durable flag type')
        uncertain=name in ('expiry_after_commit','common_revoke_remains_unresolved')
        need(row['recoveryRequired'] is uncertain and row['transportUncertain'] is uncertain and row['sequenceUncertain'] is (name=='expiry_after_commit'),'Separate possible OPEN/common REVOKE uncertainty')
        need(row['ownerEpoch']==int(meta['owner_epoch'])==(2 if name in ('expiry_after_commit','prepared_mutation_recovery','common_revoke_remains_unresolved') else 1),'Exact reopened owner epoch')
        need(row['acknowledged']==row['collected']==row['highWater']==0 and all(counts[t]==0 for t in ('sd_activations','sd_activation_versions','sd_conflicts')),'No invented activation/conflict evidence')
        need(route['boot']==mapping['boot']=='1' and route['standingFloor']==mapping['standingNumber']==1 and route['fences']==mapping['fences'],'Monotonic route identity and floors')
        opened=bytes.fromhex(row['open']);need(len(opened)==134 and opened[:2]==b'\x02\x40','Original OPEN body');reference(opened,mapping)
        need(opened[47:79]==CONFIG_BYTES and opened[79]==3 and [u32(opened,80+4*i) for i in range(8)]==mapping['fences'] and
             u16(opened,44)==1 and opened[46]==32 and u64(opened,112)==1000 and opened[120:122]==bytes(2) and
             u32(opened,122)==100 and u32(opened,126)==u32(opened,130)==1,'Literal qualified native OPEN bytes')
        requests,responses=audit_trace(evidence['trace'],route,name,mapping);envelopes=[];mutations=[]
        def occurs(tx,body):return tx in requests and requests[tx]['raw']==body
        need(row['openState']==('possible' if name=='expiry_after_commit' else 'accepted') and
             occurs(row['openTx'],row['open']) is (name!='expiry_after_commit'),'No retry of possible original OPEN')
        for key in ('openReply','lastStatus'):
            if row[key] is not None:envelope(row[key],mapping);envelopes.append(row[key])
        for number,key,sequence,body in db.execute('SELECT number,host_key,endpoint_sequence,document FROM sd_mutations ORDER BY number'):
            item=doc(body,1536);mutations.append(item);payload=bytes.fromhex(item['body'])
            need((item['number'],item['hostKey'],item['endpointSequence'])==(number,key,sequence) and
                 len(payload)==66 and payload[:2]==bytes((2,item['opcode'])),'Original mutation SQL and wire key')
            reference(payload,mapping);need(item['bodyDigest']=='sha256:'+sha(payload) and u32(payload,44)==sequence and
                 u64(payload,52)==item['leaseUntil'] and u32(payload,60)==item['ack'],'Immutable typed mutation request')
            need(item['state'] in ('accepted','never_handed_off') and item['reply'] is not None,'Exact settled mutation state')
            req,res=envelope(item['reply'],mapping);envelopes.append(item['reply'])
            if item['state']=='never_handed_off':
                need(item.get('settlement')=='durable-prepared-never-possible' and req[1]==67 and res[6]==0 and u32(res,54)==sequence-1 and not occurs(item['tx'],item['body']),'Prepared original never sent, unchanged-sequence STATUS proof')
            else:need(req==payload and res[6]==0 and occurs(item['tx'],item['body']),'Accepted exact original send/receipt')
        need([m['number'] for m in mutations]==list(range(1,len(mutations)+1)),'Contiguous original outbox numbers')
        expected_mutations={'renewal_withdrawal':[(65,'start',1),(66,'renew',2),(71,'stop',3),(72,'retire',4)],
            'shared_authority':[(71,'stop',1),(72,'retire',2)],
            'prepared_mutation_recovery':[(65,'start-original',1),(65,'start-new',1),(71,'stop',2),(72,'retire',3)],
            'common_revoke_remains_unresolved':[(71,'stop',1)]}.get(name,[])
        need([(m['opcode'],m['hostKey'],m['endpointSequence']) for m in mutations]==expected_mutations,'Exact scenario mutation history')
        need(sum(m['state']=='never_handed_off' for m in mutations)==(1 if name=='prepared_mutation_recovery' else 0),'Only intentional never-handed-off record')
        episodes=[]
        for key,body in db.execute('SELECT episode_key,document FROM sd_episodes ORDER BY episode_key'):
            episode=doc(body,1536);req,res=envelope(episode['state'],mapping);envelopes.append(episode['state']);state=res[66:]
            need(req[1]==67 and res[6]==0 and len(state)==124 and state[89]==5 and state[92:94]==bytes((3,3)) and state[101]==3 and u16(state,96)&128 and not u16(state,96)&6,'Actual quiescent STOP episode')
            witness=bytes.fromhex(episode['witness']);need(state[102:124]==witness and witness[:4]==bytes((1,1,5,0)) and witness[16:]==bytes(6) and
                key==str(u64(state,53))+':'+str(u16(state,94)),'Original loss witness and episode key')
            episodes.append(episode)
        need(len(episodes)==(1 if retired or name=='common_revoke_remains_unresolved' else 0),'Exact retained loss episode count')
        if retired:need(mutations[-1]['opcode']==72 and mutations[-1]['state']=='accepted' and episodes,'Retirement release retains terminal response and loss proof')
        if name=='common_revoke_remains_unresolved':
            revoke=row['revoke'];need(set(revoke)=={'body','reply','state','tx'} and revoke['state']=='possible' and revoke['reply'] is None and not occurs(revoke['tx'],revoke['body']),'Separate original common REVOKE uncertainty, no resend')
            rb=bytes.fromhex(revoke['body']);need(rb==b'\x02\x12'+struct.pack('>IHH',mapping['generation'],mapping['handle'],6) and len(owned)==3,'Matching common outbox keeps ownership despite STOP witness')
        else:need(row['revoke'] is None,'No additional common outbox')
        for env in envelopes:
            need(occurs(env['tx'],env['request']) and env['tx'] in responses and responses[env['tx']]['sequence']==env['rx'] and
                 responses[env['tx']]['raw']==env['response'],'Every retained receipt joins exact actual request/response')
        return {'case':name,'databaseSha256':before,'databaseBytes':size,'charge':charge,'deployments':1,'finiteOperations':len(operations),
            'retainedClaims':len(owned),'retired':retired,'openState':row['openState'],'mutations':len(mutations),'episodes':len(episodes),
            'commonRevokeState':None if row['revoke'] is None else row['revoke']['state']},(artifact,current,installation)
    finally:
        db.close();need(digest(path)==before and not sidecars(),'DB bytes and sidecar absence unchanged')


def audit_pure(evidence,reference_data,manifest):
    artifact,current,installation=reference_data
    need(evidence['case']=='compiler_equivalence' and evidence['publicParseCalls']==5 and evidence['privateParseCalls']==1 and
         evidence['observationalProfileHook'] is True and evidence['timingMeasured'] is False and
         evidence['oldOracleSha256']==ORACLE_SHA==digest(HERE/'originals/standing_pat.py'),'Exact old/new observational compiler control')
    names=['literal','canonical_bytes','label_id','label_taskKind','label_inputProfile','resource_order']
    malformed={'bad_json':'invalid bounded UTF-8 JSON','duplicate_key':'duplicate JSON object field',
        'oversize':'string exceeds host byte limit','excess_depth':'JSON depth/node limit exceeded',
        'negative_zero':'non-finite number or negative zero','missing_fields':'STANDING_FIELDS','unexpected_fields':'STANDING_FIELDS'}
    for name in malformed:names.extend((name,name+'_and_bad_installation'))
    remaining={'bool_kernel':'STANDING_PAT_DOMAIN_UNQUALIFIED','float_kernel':'STANDING_PAT_DOMAIN_UNQUALIFIED',
        'bool_lower':'STANDING_PAT_DOMAIN_UNQUALIFIED','float_lower':'STANDING_PAT_DOMAIN_UNQUALIFIED',
        'invalid_label':'invalid identifier','wrong_domain':'STANDING_PAT_DOMAIN_UNQUALIFIED','slot_service':'STANDING_SLOT_RESOURCE',
        'capacity_bool':'STANDING_CAPACITY_UNQUALIFIED','driver_digest':'STANDING_SLOT_DRIVER_IDENTITY',
        'missing_driver_dependency':'STANDING_SLOT_DEPENDENCY','alias_extra_slot':'RESOURCE_ALIAS_FOOTPRINT',
        'epoch_bool':'STANDING_INTEGER','different_boot':'STANDING_PAT_INSTALLATION_UNQUALIFIED',
        'different_incarnation':'STANDING_PAT_INSTALLATION_UNQUALIFIED'}
    names+=list(remaining);vectors=evidence['vectors']
    need(len(vectors)==34 and [x['case'] for x in vectors]==names,'Exact ordered34 original vectors')
    hashes=[]
    for index,row in enumerate(vectors):
        need(set(row)=={'case','outcome','error','compiledSha256'},'Closed equivalence-vector record')
        name=row['case']
        if index<6:
            aa=copy.deepcopy(artifact);ii=copy.deepcopy(installation)
            if name.startswith('label_'):aa[name[6:]]='other:valid-label'
            if name=='resource_order':
                ii['hardwareResources'].reverse();aa['requirements']['installationDigest']=identity('HMS-STANDING-INSTALLATION-v0.1',ii)
            expected=sha(canon(compiled(aa,ii,manifest)));hashes.append(expected)
            need(row['outcome']=='ok' and row['error'] is None and row['compiledSha256']==expected,'Independent successful compiled-record bytes')
        else:
            key=name.removesuffix('_and_bad_installation');error=malformed[key] if key in malformed else remaining[key]
            kind='ResourceTopologyError' if error=='RESOURCE_ALIAS_FOOTPRINT' else ('JournalError' if error.startswith('STANDING_') else 'ContractError')
            need(row['outcome']=='error' and row['compiledSha256'] is None and row['error']==[kind,error if kind!='ContractError' else None,error],'Exact error class/code/message and malformed precedence')
    need(evidence['compiledSha256']==hashes[0]==hashes[1]==sha(canon(current)),'Pure/native-selection exact compilation join')
    return {'vectors':34,'successVectors':6,'refusalVectors':28,'publicInstallationParses':5,'privateInstallationParses':1,
        'compiledSha256':hashes[0],'retainedControlEquivalenceAudited':True,'compilerReexecuted':False,'speedupEstablished':False}


def owned(record,cpu,memory,parent=None):
    for field in ('pid','parent','group','session','startTicks'):uint(record[field]);need(record[field]>0,'Positive retained process identity')
    need(record['reaped'] is True and record['exitCode']==0,'Clean owned child reap')
    if parent is not None:need(record['parent']==parent,'Exact registered direct parent')
    need(type(record['cpuSeconds']) in (int,float) and 0<=record['cpuSeconds']<=cpu and
         type(record['peakRSSKiB']) is int and 0<=record['peakRSSKiB']<=memory,'Observed per-process usage within unchanged bounds')
    need(not Path('/proc',str(record['pid'])).exists(),'Observed identity absent, never signal authority')
    return (record['pid'],record['startTicks'])


def decimal(value):
    need(type(value) is str and value.isascii() and value.isdigit() and value==str(int(value)),'Canonical decimal duration');return int(value)


def main():
    need(len(sys.argv)==1 and not sys.flags.optimize,'Fixed assertion-enabled data-only invocation')
    source_sha=digest(Path(__file__))
    need(digest(HERE/'SOURCE-REVIEW.json')==REVIEW_SHA and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA,'Original frozen review/actual attempt pins')
    review=data(HERE/'SOURCE-REVIEW.json',False);inputs=data(HERE/'source-pins.json',False);pins=data(HERE/'AUDIT-INPUT-PINS.json',False)
    need(len(review['files'])==283 and review['inputBytes']==5010312 and pins['sourceReviewSha256']==REVIEW_SHA,'Exact reviewed283 input files')
    def stable():
        for row in review['files']:need((HERE/row['path']).lstat().st_size==row['bytes'] and digest(HERE/row['path'])==row['sha256'],'Frozen input bytes unchanged')
        total=0
        for key in ('parentPacket','secondParentPacket','proposalPacket'):
            spec=inputs[key];parent=REPO/spec['path'];need(digest(parent/'index.json')==spec['indexSha256'],'Original sealed index')
            rows=data(parent/'index.json',False)['files'];inventory(parent,rows,('index.json',));total+=len(rows)
        need(total==4394,'Exact three sealed parent inventories')
        receipt=REPO/inputs['publicReceipt']['path'];need(digest(receipt)==inputs['publicReceipt']['sha256'],'Public baseline receipt')
        public=data(receipt,False)['files'];need(len(public)==244,'Public244')
        for row in public:need(digest(REPO/row['path'])==row['sha256'],'Public file unchanged')
        need(len(inputs['copies'])==260 and len(inputs['originalProvenance'])==11,'Exact unchanged reuse/provenance scope')
        for row in inputs['copies']+inputs['originalProvenance']:
            need(digest(REPO/row['source'])==digest(HERE/row['copy'])==row['sha256'] and (HERE/row['copy']).stat().st_size==row['bytes'],'Original source/copy association')
        changed=inputs['modifiedProduction'];need(len(changed)==1 and changed[0]['path']=='project/hms/standing_pat.py' and
            changed[0]['baselineSha256']==ORACLE_SHA and digest(HERE/changed[0]['path'])==changed[0]['candidateSha256'],'Only declared changed production identity')
    stable();native=Path(inputs['nativeImage']);qualification=Path(inputs['qualificationRoot'])
    parent=REPO/'artifacts/implementation/standing-host-deployment'
    need(native==parent/'host-attempt04/standing-host-pipe' and qualification==parent/'host-attempt04/qualification','Original absolute image/evidence roots')
    need(digest(native)==NATIVE_SHA and digest(qualification/'standing-controls')==QUALIFIER_SHA,'Original native images unchanged')
    manifest=data(qualification/'manifest.json',False);receipt=data(qualification/'receipt.json');reservation=data(qualification/'reservation.json')
    for key in ('evaluatorId','runId','runnerDigest','domainDigest','sourcePins','binaryPath','binaryDigest','argv'):
        need(manifest[key]==receipt[key]==reservation[key],'Original qualification common identity '+key)
    need(manifest['argv']==[str(qualification/'standing-controls')] and manifest['runId']=='native-standing-original:4' and
         manifest['evaluatorId']=='standing-native-controls-v1' and manifest['binaryDigest']=='sha256:'+QUALIFIER_SHA and
         receipt['attemptId']==reservation['attemptId']=='native-standing-attempt:4' and receipt['exitCode']==receipt['terminationSignal']==0 and
         receipt['ownership']['cleanupComplete'] is True and receipt['ownership']['reaped'] is True and receipt['ownership']['openChildHandles']==0,'Actual original completed qualification, never relabeled or rerun')
    for field,file in (('receiptDigest','receipt.json'),('reservationDigest','reservation.json'),('stdoutDigest','stdout'),('stderrDigest','stderr')):
        need(manifest[field]=='sha256:'+digest(qualification/file),'Original qualification file association '+field)
    need(receipt['reservationDigest']==manifest['reservationDigest'] and receipt['stdoutDigest']==manifest['stdoutDigest'] and
         receipt['stderrDigest']==manifest['stderrDigest'] and raw(qualification/'stdout')==b'{"cases":12,"assertions":638,"physical_qualification":false}\n' and not raw(qualification/'stderr'),'Actual original12/638 output')
    need(len(manifest['sourcePins'])==12,'Exact original C source closure')
    for name,value in manifest['sourcePins'].items():need(value=='sha256:'+digest(HERE/'project'/name),'Original qualified source pin')
    domain={'profile':'hms.standing-native-domain/0.1','kernel':1,'mask':3,'parameters':{},'configuration':CONFIG,'limits':LIMITS,
        'evidenceMode':'simulation','sourceEpochs':[1,1],'caseClosure':QUAL_CASES,'sourcePins':manifest['sourcePins'],'physicalEligible':False,'protectedCapacity':False}
    need(manifest['domainDigest']==identity('HMS-STANDING-NATIVE-DOMAIN-v0.1',domain),'Independent literal qualification domain')
    need([x['profile'] for x in pins['attempts']]==['pure','live'],'Exactly both actual original profiles')
    identities=[];summaries=[];databases=[];pure=None;reference_data=None;interpreter_sha=None;attempt_files=0
    for spec in pins['attempts']:
        profile=spec['profile'];need(spec['path']=='selection-reuse-'+profile+'-attempt01','No retry or invented attempt')
        attempt=HERE/spec['path'];inventory(attempt,spec['files']);attempt_files+=len(spec['files'])
        result=data(attempt/'RESULTS.json');inner=data(attempt/'state/CONTROL-RESULTS.json');intent=data(attempt/'intent.json')
        need(digest(attempt/'RESULTS.json')==spec['resultSha256'] and digest(attempt/'state/CONTROL-RESULTS.json')==spec['controlResultSha256'],'Actual terminal receipt pins')
        inventory(attempt/'frozen',review['files'],('SOURCE-REVIEW.json',));need(digest(attempt/'frozen/SOURCE-REVIEW.json')==REVIEW_SHA,'Exact executed review')
        need(intent['sourcePins']=={**{r['path']:r['sha256'] for r in review['files']},'SOURCE-REVIEW.json':REVIEW_SHA},'Every executed source byte pinned')
        names=['compiler_equivalence'] if profile=='pure' else list(LIVE)
        need(result['passed'] is inner['passed'] is True and result['reason'] is inner['failure'] is None and
             result['controlProfile']==intent['controlProfile']==inner['profile']==profile and intent['cases']==names and
             [x['case'] for x in inner['cases']]==names and result['attemptNumber']==intent['attemptNumber']==1 and
             result['priorProfileAttemptResults']==intent['priorProfileAttemptResults']==[] and intent['controlProfilePreviouslyExecuted'] is False,'Original ordered successful profile, no retry')
        need(intent['wallSeconds']==intent['cpuSeconds']==30 and intent['addressBytes']==512*1024*1024 and
             intent['childCpuSeconds']==5 and intent['childAddressBytes']==256*1024*1024 and
             intent['fileBytes']==intent['nativeChildFileBytes']==result['fileBytes']==1024*1024 and intent['openFiles']==64 and
             intent['cleanupSeconds']==8 and intent['termGraceSeconds']==3 and intent['stateDiskBytes']==96*1024*1024,'Unchanged reviewed process bounds')
        argv=[intent['interpreter'],'-I','-B',str(attempt/'frozen/selection_reuse_controls.py'),profile,str(attempt/'state'),
              str(native),str(qualification),str(qualification/'manifest.json'),str(attempt/'frozen/owner/libharness-owner.so')]
        need(intent['argv']==argv and intent['nativeImageSha256']==NATIVE_SHA and intent['originalQualificationRoot']==str(qualification) and
             intent['originalQualificationRunId']=='native-standing-original:4','Exact command and original qualification root')
        if interpreter_sha is None:interpreter_sha=intent['interpreterSha256']
        need(intent['interpreterSha256']==interpreter_sha==digest(intent['interpreter']) and result['heldInterpreterBefore']==result['heldInterpreterAfter'] and
             result['heldInterpreterBefore']['sha256']==interpreter_sha,'Held/current interpreter identity before and after')
        for report in (result,inner):need(report['ownerEmpty'] is True and report['ownerClosed'] is True and not report['cleanupErrors'] and not report['interruptsPending'],'Independent clean ownership receipt')
        need(not result['unexpectedChildrenObserved'] and len(result['outerChildrenReaped'])==1 and result['controlExit']==result['outerChildrenReaped'][0],'One exact outer control reap')
        outer=result['controlExit'];identities.append(owned(outer,30,512*1024));start=data(attempt/'control.started.json')
        need(all(outer[k]==v for k,v in start.items()),'Outer registration to clean reap')
        n=0 if profile=='pure' else 9
        need(len(inner['nativeChildrenReaped'])==result['innerReaps']==intent['expectedInnerReaps']==n and
             result['innerCases']==len(names) and intent['expectedOuterReaps']==1,'Exact inner/outer role counts')
        need(not raw(attempt/'control.stderr') and json.loads(raw(attempt/'control.stdout'))==inner,'Clean control stderr and exact stdout receipt')
        elapsed=decimal(result['controlTerminalObservedMonotonicNs'])-decimal(result['controlStartedMonotonicNs'])
        need(0<elapsed==decimal(result['controlObservedElapsedMonotonicNs'])<=30_000_000_000 and decimal(result['elapsedMonotonicNs'])>=elapsed,'Original observed deadline, final includes cleanup')
        case_checks=legacy_checks=0
        for index,case in enumerate(inner['cases']):
            name=case['case'];directory=attempt/'state'/name;evidence=data(directory/'evidence.json')
            need(case['passed'] is True and evidence['case']==name and digest(directory/'evidence.json')==case['evidenceSha256'],'Exact successful case evidence')
            uint(case['checks']);uint(case['legacyChecks']);need(0<decimal(case['elapsedMonotonicNs'])<=elapsed,'Per-case monotonic observation')
            case_checks+=case['checks'];legacy_checks+=case['legacyChecks']
            for key in ('physicalEligible','protectedCapacity'):need(evidence[key] is False,'Explicit local synthetic case scope')
            if profile=='pure':
                need(case['databaseSha256'] is case['nativeStartIdentity'] is case['nativeReap'] is None and
                     not (directory/'authority.db').exists(),'Pure profile does not claim native or DB effect');pure=evidence
            else:
                reap=inner['nativeChildrenReaped'][index];identities.append(owned(reap,5,256*1024,outer['pid']))
                need(case['nativeReap']==evidence['nativeReap']==reap and case['nativeStartIdentity']==evidence['nativeStartIdentity'] and
                     all(reap[k]==v for k,v in case['nativeStartIdentity'].items()),'Per-case original registered native identity and clean EOF reap')
                need(digest(directory/'authority.db')==case['databaseSha256'] and evidence['legacyChecks']==case['legacyChecks'] and
                     evidence['selectionParseCalls']==(3 if name=='management_replays' else None),'DB and current7-to3 selection observation')
                database,reference_data=audit_database(directory/'authority.db',name,evidence,interpreter_sha,manifest,qualification);databases.append(database)
        need(inner['checks']==case_checks+1==(84 if profile=='pure' else 267) and
             inner['legacyChecks']==result['legacyChecks']==legacy_checks==(0 if profile=='pure' else 76),'Exact case/invocation/legacy checks, kept separate')
        for report in (intent,result,inner):
            need(report['productionChanged'] is True,'Honest changed host source identity')
            for key in ('qualificationRerun','full128RecordQualification','physicalEligible','protectedCapacity','publicMountEligible'):need(report[key] is False,'Explicit scope exclusion '+key)
        need(result['parentPacketStable'] is True and result['publicInputsExact']==244 and result['logicalCeilingBytes']==16*1024*1024 and
             result['fullSimultaneousCapacityEstablished'] is False and result['historicalPossibleEffectsResent'] is False and
             result['actualOwnerDeath'] is inner['actualOwnerDeath'] is False and result['universalContainment'] is False,'No broadened capacity/crash/containment/authority claim')
        summaries.append({'profile':profile,'resultSha256':spec['resultSha256'],'cases':len(names),'checks':inner['checks'],
            'legacyChecks':legacy_checks,'nativeReaps':n,'outerReaps':1,'observedElapsedNs':str(elapsed),'finalElapsedNs':result['elapsedMonotonicNs']})
    pure_result=audit_pure(pure,reference_data,manifest)
    need(len(identities)==len(set(identities))==11 and attempt_files==608,'Exactly9 native plus2 distinct outer identities and608 retained attempt files')
    need(sum(x['deployments'] for x in databases)==8 and sum(x['finiteOperations'] for x in databases)==2 and
         sum(x.get('retired',False) for x in databases)==3 and sum(x['retainedClaims'] for x in databases)==15,'Actual retained standing/finite ownership totals')
    stable()
    for spec in pins['attempts']:inventory(HERE/spec['path'],spec['files'])
    need(digest(Path(__file__))==source_sha and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA and
         digest(intent['interpreter'])==interpreter_sha,'Audit source/input/interpreter stable through read')
    output={'profile':'hms.standing-host-selection-reuse-retained-audit/0.1','passed':True,'checks':checks,
        'meaning':'Independent retained equivalence/native authority joins; no candidate execution or performance extrapolation.',
        'auditSourceSha256':source_sha,'auditInputPinsSha256':INPUT_SHA,'sourceReviewSha256':REVIEW_SHA,
        'sourceFilesReverified':283,'unchangedReuseFiles':260,'provenanceCopies':11,'sealedParentFilesReverified':4394,'publicFilesReverified':244,
        'attemptFiles':attempt_files,'completedCases':10,'newControlChecks':351,'legacyChecks':76,
        'profiles':summaries,'pure':pure_result,'databases':databases,'ownedIdentitiesCurrentlyAbsent':11,'nativeReaps':9,'outerReaps':2,
        'productionChanged':True,'qualificationRerun':False,'full128RecordQualification':False,'oldFailedCapacityProfileRemainsFailed':True,
        'actualOwnerDeath':False,'speedupEstablished':False,'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
    body=canon(output)
    if len(body)>1024*1024:raise AssertionError('Audit receipt bound')
    destination=HERE/'AUDIT.json';temporary=HERE/'.AUDIT.json.pending'
    with temporary.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    os.link(temporary,destination,follow_symlinks=False);fd=os.open(HERE,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd);temporary.unlink();os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'passed':True,'checks':checks,'cases':10,'attemptFiles':attempt_files,'ownedIdentities':11},sort_keys=True))


if __name__=='__main__':main()
