"""Original stdlib-only audit of the stopped three-profile retained prefix.

Review before execution. Imports no candidate, launches/signals no process,
opens authority DBs read-only/immutable/query_only, writes only new AUDIT.json.
Audit success means retained evidence joins, not that the failed matrix passed.
"""
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
REVIEW_SHA='0634a6a8bc8ac78be1e2f4a3f2e9239da02206d331fd2dfebf7b97f29b7ab302'
INPUT_SHA='d2c1e0432dc5da5e1d63cc022e01b212b7c33b1d41b17cd3cdcc375a161568a3'
NATIVE_SHA='5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399'
QUALIFIER_SHA='b89d0a1030768932ace1c9c2da5a4a888d0ae7da46a8a77473b2b145293ff842'
NEGATIVE=('expired_qualification','driver_expiry_after_possible','installed_context_change',
 'boot_after_acceptance','retired_without_terminal_proof','refused_sequence_original_key',
 'automatic_ack_revision_refusal','dispute_retention')
STORAGE=tuple('storage_'+phase+'_'+when for phase in ('prepare','open','collection','retire')
              for when in ('before','after'))+('rollback_exception','sqlite_page_exhaustion')
PROFILES={'negative':NEGATIVE,'storage':STORAGE,'mutation':('mutation_capacity',)}
UNEXECUTED=('episodes','activations','keys','fixed','accounting')
# Expected durable edge counts: mutations, activations, versions, episodes,
# retained conflicts, retained claims, dispatches and installed loss commands.
EDGES={
 'expired_qualification':(2,0,0,1,0,0,0,1),
 'driver_expiry_after_possible':(0,0,0,0,0,3,0,0),
 'installed_context_change':(3,0,0,1,0,0,0,1),
 'boot_after_acceptance':(1,0,0,0,1,3,0,0),
 'retired_without_terminal_proof':(3,0,0,1,0,0,0,1),
 'refused_sequence_original_key':(3,0,0,1,0,0,0,1),
 'automatic_ack_revision_refusal':(5,1,1,1,0,0,1,1),
 'dispute_retention':(1,0,0,1,16,3,0,1),
 'storage_prepare_before':(2,0,0,1,0,0,0,1),
 'storage_prepare_after':(0,0,0,0,0,0,0,0),
 'storage_open_before':(0,0,0,0,0,0,0,0),
 'storage_open_after':(0,0,0,0,0,3,0,0),
 'storage_collection_before':(4,1,1,1,0,0,1,1),
 'storage_collection_after':(4,1,1,1,0,0,1,1),
 'storage_retire_before':(2,0,0,1,0,0,0,1),
 'storage_retire_after':(2,0,0,1,0,0,0,1),
 'rollback_exception':(2,0,0,1,0,0,0,1),
 'sqlite_page_exhaustion':(2,0,0,1,0,0,0,1)}
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


def audit_database(path,name,interpreter_sha,evidence=None,failed=False):
    before=digest(path);size=path.stat().st_size;need(size<=(32 if failed else 1)*1024*1024,'Profile DB file ceiling')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        db.execute('PRAGMA query_only=ON');need(db.execute('PRAGMA query_only').fetchone()[0]==1,'Read-only audit connection')
        need(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)] and not db.execute('PRAGMA foreign_key_check').fetchall(),'SQLite retained integrity')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        charge,counts=charges(db,tables)
        meta=dict(db.execute('SELECT key,value FROM meta'))
        installed=doc(db.execute('SELECT document FROM sd_meta').fetchone()[0],65536)
        route=doc(db.execute('SELECT document FROM sd_route').fetchone()[0],4096)
        need(installed['authorityId']==meta['authority'] and installed['installationDigest']==identity('HMS-STANDING-INSTALLATION-v0.1',installed['installation']),'Installed authority identity')
        installation=installed['installation']
        expected_host=identity('HMS-STANDING-HOST-IMAGE-v0.1',{'sources':{p:'sha256:'+digest(HERE/'project'/p) for p in HOST_SOURCES},
            'interpreter':'sha256:'+interpreter_sha,'dependencyScope':'original-source-pins;trusted-python-stdlib-loader-validation-packages'})
        expected_driver=identity('HMS-STANDING-PIPE-SOURCES-v0.1',{p:'sha256:'+digest(HERE/'project'/p) for p in DRIVER_SOURCES})
        need(installation['hostImplementationDigest']==expected_host and installation['driverSourceDigest']==expected_driver and
            installation['driverImageDigest']=='sha256:'+NATIVE_SHA and installation['qualificationImageDigest']=='sha256:'+QUALIFIER_SHA,'Actual installed source/interpreter/image closure')
        evaluations=db.execute('SELECT evaluator,run_id,document FROM sp_evaluations').fetchall()
        need(len(evaluations)==1 and evaluations[0][:2]==('standing-native-controls-v1','native-standing-original:4'),'Original evaluator run')
        doc(evaluations[0][2],16384)
        stored=db.execute('SELECT id,principal,deployment,namespace,caller_key,request_digest,document FROM sd_deployments').fetchall()
        need(len(stored)==1,'One original deployment in this actual prefix')
        sql=stored[0];row=doc(sql[6],32768);mapping=row['mapping'];request=row['request'];identifier=row['id']
        need(tuple(row[k] for k in ('id','principal','deployment','namespace','key','requestDigest'))==sql[:6],'Deployment SQL keys')
        need(row['requestDigest']==identity('HMS-STANDING-REQUEST-v0.1',request)==mapping['requestDigest'],'Original request digest')
        base=dict(mapping);base.pop('deploymentDigest');need(mapping['deploymentDigest']==identity('HMS-STANDING-DEPLOYMENT-v0.1',base),'Frozen mapping digest')
        need(mapping['authorityId']==meta['authority'] and mapping['installationDigest']==installed['installationDigest'],'Mapping authority/install join')
        need(row['key']==request['deploymentKey']=='application' and row['namespace']==request['replayNamespace'],'Exact original replay key')
        need(set(mapping['resourceProof']['expandedClaims']['control'])=={'atom:demand','atom:output'} and
             {entry['resource'] for entry in mapping['claims']}=={'atom:demand','atom:output','atom:slot'} and len(mapping['claims'])==3,'Physical2/actual3 claims')
        need([r[0] for r in db.execute('SELECT instance_id FROM resource_owner_instances WHERE owner_id=? ORDER BY instance_id',(identifier,))]==['native:finite','native:standing'],'Shared alias owner')
        owned=db.execute('SELECT resource,fence FROM claims WHERE operation_id=? ORDER BY resource',(identifier,)).fetchall()
        expected_claims=sorted((claim['resource'],claim['fence']) for claim in mapping['claims'])
        need(owned==([] if row['retired'] else expected_claims),'Claim release only for retained terminal settlement')
        for field in ('retired','disputed','effectUnknown','recoveryRequired','sequenceUncertain','transportUncertain','everPossiblyActed'):need(type(row[field]) is bool,'Typed durable flags')
        need(0<=row['acknowledged']<=row['collected']<=row['highWater']<=100,'Retained prefix ordering')
        need(route['boot']==mapping['boot']=='1' and route['standingFloor']==mapping['standingNumber']==1 and route['fences']==mapping['fences'],'Retained route high-water/fences')
        opened=bytes.fromhex(row['open']);need(len(opened)==134 and opened[:2]==b'\x02\x40','OPEN body');reference(opened,mapping)
        configuration=struct.pack('>iiii6H4B',20000,30000,0,500,10,100,100,0,0,50,0,1,0,0)
        need(opened[47:79]==configuration and opened[79]==3 and [u32(opened,80+4*i) for i in range(8)]==mapping['fences'] and
             u64(opened,112)==1000 and u32(opened,122)==100 and u32(opened,126)==u32(opened,130)==1,'Literal qualified native domain')
        sent=[];retained_envelopes=[];mutations=[];activations=[];versions=[];episodes=[];conflicts=[]
        for name_ in ('openReply','lastStatus'):
            if row[name_] is not None:envelope(row[name_],mapping);retained_envelopes.append(row[name_])
        for number,key,sequence,body in db.execute('SELECT number,host_key,endpoint_sequence,document FROM sd_mutations ORDER BY number'):
            item=doc(body,1536);mutations.append(item)
            need((item['number'],item['hostKey'],item['endpointSequence'])==(number,key,sequence),'Mutation original SQL key')
            payload=bytes.fromhex(item['body']);need(len(payload)==66 and payload[:2]==bytes((2,item['opcode'])),'Mutation opcode/body')
            reference(payload,mapping);need(item['bodyDigest']=='sha256:'+sha(payload) and u32(payload,44)==sequence and
                u64(payload,52)==item['leaseUntil'] and u32(payload,60)==item['ack'],'Immutable mutation request')
            need(item['state'] in {'accepted','refused','never_handed_off','possible','prepared'},'Mutation state domain')
            if item['state']=='never_handed_off':need(item.get('settlement')=='durable-prepared-never-possible' and item['reply'] is not None,'Never-possible proof retained')
            if item['reply'] is not None:
                req,res=envelope(item['reply'],mapping);retained_envelopes.append(item['reply'])
                if item['state']=='never_handed_off':
                    need(req[1]==67 and res[6]==0 and u32(res,54)==item['endpointSequence']-1,'Never-possible original settles by unchanged-sequence STATUS')
                elif 'retirementEvidence' in item:
                    need(item['opcode']==72 and req[1]==67 and res[6]==8 and item['state']=='accepted','Lost RETIRE original proof')
                    envelope(item['retirementEvidence'],mapping);retained_envelopes.append(item['retirementEvidence'])
                else:
                    need(req==payload and ((res[6]==0)==(item['state']=='accepted')),'Exact mutation receipt state')
        need([m['number'] for m in mutations]==list(range(1,len(mutations)+1)),'Contiguous retained outbox numbers')
        for table,destination in (('sd_activations',activations),('sd_activation_versions',versions)):
            for entry in db.execute('SELECT * FROM '+table+' ORDER BY number'+(',version' if table.endswith('versions') else '')):
                event=doc(entry[-1],1024);payload=bytes.fromhex(event['raw']);number=entry[1]
                need(len(payload)==44 and u32(payload,0)==number and event['state']==payload[40]&7,'Activation key/raw/state')
                req,res=envelope(event['envelope'],mapping);retained_envelopes.append(event['envelope'])
                need(req[1]==67 and req[44]==2 and u32(req,45)==number and res[66:]==payload and payload[41]&7==5 and payload[40]>>4&3==0,'Actual synthetic activation evidence')
                destination.append(event)
        for key,body in db.execute('SELECT episode_key,document FROM sd_episodes ORDER BY episode_key'):
            episode=doc(body,1536);req,res=envelope(episode['state'],mapping);retained_envelopes.append(episode['state']);state=res[66:]
            need(len(state)==124 and state[89] in (4,5) and state[92:94]==bytes((3,3)) and state[101]==3 and u16(state,96)&128 and not u16(state,96)&6,'Exact quiescent loss episode')
            witness=bytes.fromhex(episode['witness']);need(state[102:124]==witness and witness[:4]==bytes((1,1,5,0)) and
                witness[16:]==bytes(6) and key==str(u64(state,53))+':'+str(u16(state,94)),'Original loss witness/key')
            episodes.append(episode)
        for number,body in db.execute('SELECT number,document FROM sd_conflicts ORDER BY number'):
            conflict=doc(body,1536);conflicts.append(conflict)
            need(number==len(conflicts) and 'evidence' in conflict and 'request' in conflict['evidence'],'Bounded original conflict packet')
            envelope(conflict['evidence'],mapping,conflict=True)
        need(row['revoke'] is None,'No common REVOKE reached in the actual stopped prefix')
        if evidence is not None:
            need(evidence['route']==route and evidence['capacity']==charge and evidence['tableCounts']==counts and
                 evidence['ownerEpoch']==int(meta['owner_epoch']) and evidence['authority']==meta['authority'],'Independent DB/evidence/accounting join')
            requests,responses=audit_trace(evidence['trace'],route,conflicts)
            def occurrences(tx,body):return sum(entry['sequence']==tx and entry['raw']==body for entry in requests)
            need(occurrences(row['openTx'],row['open'])==(1 if row['openState']=='accepted' else 0),'Original OPEN send count')
            for item in mutations:need(occurrences(item['tx'],item['body'])==(0 if item['state']=='never_handed_off' else 1),'Never resend original outbox or send abandoned intent')
            for env in retained_envelopes:
                need(occurrences(env['tx'],env['request'])==1,'Retained receipt request exists in actual stream trace')
                need(any(entry['session']==int(env['boot']) and entry['sequence']==env['rx'] and entry['raw']==env['response'] for entry in responses),'Retained receipt response exists in actual stream trace')
            audit_edge(name,row,mutations,activations,versions,episodes,conflicts,owned,evidence['native'])
        else:
            need(failed and len(mutations)==68 and all(m['state']=='never_handed_off' and m['opcode']==65 and m['endpointSequence']==1 and
                m['hostKey']=='never-start:'+str(i) for i,m in enumerate(mutations)),'Exact failed progress68 retained original STARTs')
            need(row['openState']=='accepted' and row['mutationSequence']==0 and not row['retired'] and not row['disputed'] and
                 not row['effectUnknown'] and row['revoke'] is None and len(owned)==3 and not activations and not episodes,'Failed run retains uncertainty boundary/claims with no activation history')
        return {'case':name,'databaseSha256':before,'databaseBytes':size,'chargedLogicalBytes':charge['chargedLogicalBytes'],
            'mutations':len(mutations),'activations':len(activations),'versions':len(versions),'episodes':len(episodes),
            'conflicts':len(conflicts),'retainedClaims':len(owned),'retired':row['retired'],'openState':row['openState'],
            'mutationSequence':row['mutationSequence'],'hasFullCaseSnapshot':evidence is not None}
    finally:
        db.close();need(digest(path)==before,'Read-only DB bytes unchanged')


def audit_trace(entries,route,conflicts):
    need(type(entries) is list and len(entries)<=2048,'Bounded raw trace')
    requests=[];responses=[];last_tx=0;last_rx=0
    for entry in entries:
        need(set(entry)=={'direction','session','sequence','raw'},'Trace shape');uint(entry['session']);uint(entry['sequence'],2**32-1)
        body=bytes.fromhex(entry['raw']);need(2<=len(body)<=192 and body[0]==2,'Original bounded v2 body')
        if entry['direction']=='request':
            need(entry['sequence']>last_tx and entry['session']==1,'Strict original request continuity');last_tx=entry['sequence'];requests.append(entry)
            need(body[1] in (1,16,18,64,65,66,67,68,69,70,71,72),'Closed wire opcodes')
        else:
            need(entry['direction']=='response' and len(body)>=66 and entry['session']==1 and entry['sequence']>last_rx,'Decoded response continuity')
            last_rx=entry['sequence'];responses.append(entry)
            matches=[r for r in requests if r['sequence']==u32(body,2)]
            need(len(matches)==1 and body[1]==bytes.fromhex(matches[0]['raw'])[1]|128,'Actual response request join')
    need(last_tx<=route['tx'] and last_rx<=route['rx'],'Trace below committed route watermarks')
    retained={(c['evidence']['tx'],c['evidence']['request']) for c in conflicts}
    missing=[]
    for request in requests:
        matched=[r for r in responses if u32(bytes.fromhex(r['raw']),2)==request['sequence']]
        need(len(matched)<=1,'One observed reply per original request')
        if not matched:missing.append(request)
    # Conflict retention saturates at16. In dispute_retention, the17th original
    # malformed reply is deliberately not retained, but sticky dispute survives.
    unknown=[r for r in missing if (r['sequence'],r['raw']) not in retained]
    need(len(unknown)<=(1 if len(conflicts)==16 else 0),'Every absent decoded reply has retained conflict or the explicit17th overflow')
    return requests,responses


def audit_edge(name,row,mutations,activations,versions,episodes,conflicts,owned,native):
    need(set(native)=={str(n) for n in range(28)},'All28 native selectors')
    for value in native.values():uint(value)
    expected=EDGES[name];actual=(len(mutations),len(activations),len(versions),len(episodes),len(conflicts),len(owned),native['0'],native['1'])
    need(actual==expected,'Exact observed edge '+name)
    need(native['2']==native['17']==native['18']==0 and native['19']==native['20']==1 and native['27']==2**32-1,'Unchanged output/driver timing/epochs/feedback scope')
    need(native['21']==(2 if name=='boot_after_acceptance' else 1) and native['16']==(27 if name=='boot_after_acceptance' else 25),'Native boot/platform qualification')
    disputed=name in {'boot_after_acceptance','dispute_retention'}
    need(row['disputed']==row['effectUnknown']==disputed,'Sticky conflict/effect flags')
    if row['retired']:
        need(all(native[str(n)]==0 for n in (5,6,10,11,12,13,14,15,23,24,25)),'RETIRE or never-possible empty native slot')
        need(native['9']==(1 if row['openState']=='accepted' else 0),'Retained endpoint high-water after empty slot')
    if name in {'driver_expiry_after_possible','storage_open_after'}:
        need(row['openState']=='possible' and row['transportUncertain'] and row['recoveryRequired'] and native['9']==0,'Committed possibility is not retried/not-seen is not absence authority')
    if name=='refused_sequence_original_key':
        need([(m['state'],m['endpointSequence']) for m in mutations]==[('refused',1),('accepted',1),('accepted',2)],'Definitive refusal consumes no sequence/false novelty retained')
    if name=='automatic_ack_revision_refusal':
        first,second=mutations[1:3]
        need(first['state']=='refused' and second['state']=='accepted' and first['opcode']==second['opcode']==68 and
            first['endpointSequence']==second['endpointSequence']==2 and first['body']!=second['body'] and first['hostKey']!=second['hostKey'],'Explicit new revision ACK, original refused key unchanged')
    if name=='storage_retire_before':need('retirementEvidence' in mutations[-1],'Exact lost-RETIRE recovery evidence')
    if name=='storage_retire_after':need('retirementEvidence' not in mutations[-1],'Committed terminal receipt already retained')


def owned(record,exit_code,parent=None):
    for field in ('pid','parent','group','session','startTicks'):uint(record[field]);need(record[field]>0,'Owned identity positive')
    need(record['reaped'] is True and record['exitCode']==exit_code,'Expected original exit/reap')
    if parent is not None:need(record['parent']==parent,'Direct parent role join')
    need(type(record['cpuSeconds']) in (int,float) and 0<=record['cpuSeconds']<=30 and
         type(record['peakRSSKiB']) is int and record['peakRSSKiB']<=512*1024,'Observed usage within declared control bounds')
    need(not Path('/proc',str(record['pid'])).exists(),'Retained identity currently absent; no PID-derived signal authority')
    return (record['pid'],record['startTicks'])


def main():
    need(len(sys.argv)==1 and not sys.flags.optimize,'Fixed assertion-enabled audit')
    need(digest(HERE/'SOURCE-REVIEW.json')==REVIEW_SHA and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA,'Pinned source/audit input inventory')
    review=data(HERE/'SOURCE-REVIEW.json',False);inputs=data(HERE/'source-pins.json',False);pins=data(HERE/'AUDIT-INPUT-PINS.json',False)
    need(len(review['files'])==306 and pins['originalSourceReviewSha256']==REVIEW_SHA,'Original306 source set')
    for row in review['files']:need((HERE/row['path']).lstat().st_size==row['bytes'] and digest(HERE/row['path'])==row['sha256'],'Frozen input unchanged')
    for parent_spec in (inputs['parentPacket'],inputs['secondParentPacket']):
        parent=REPO/parent_spec['path'];need(digest(parent/'index.json')==parent_spec['indexSha256'],'Sealed parent index')
        inventory(parent,data(parent/'index.json',False)['files'],('index.json',))
    receipt=REPO/inputs['publicReceipt']['path'];need(digest(receipt)==inputs['publicReceipt']['sha256'],'Public receipt pin')
    public=data(receipt,False)['files'];need(len(public)==244,'Public244')
    for row in public:need(digest(REPO/row['path'])==row['sha256'],'Public baseline exact')
    for row in inputs['copies']+inputs['originalProvenance']:
        need(digest(REPO/row['source'])==digest(HERE/row['copy'])==row['sha256'],'Original copy/provenance join')
    native=Path(inputs['nativeImage']);qualification=Path(inputs['qualificationRoot'])
    need(digest(native)==NATIVE_SHA and digest(qualification/'standing-controls')==QUALIFIER_SHA,'Original actual native/qualifier images')
    manifest=data(qualification/'manifest.json',False)
    original_receipt=data(qualification/'receipt.json');reservation=data(qualification/'reservation.json')
    need(manifest['argv']==[str(qualification/'standing-controls')] and manifest['runId']=='native-standing-original:4' and
         original_receipt['attemptId']==reservation['attemptId']=='native-standing-attempt:4' and
         original_receipt['argv']==reservation['argv']==manifest['argv'] and original_receipt['runId']==reservation['runId']==manifest['runId'] and
         manifest['receiptDigest']=='sha256:'+digest(qualification/'receipt.json') and manifest['reservationDigest']==original_receipt['reservationDigest']=='sha256:'+digest(qualification/'reservation.json') and
         raw(qualification/'stdout')==b'{"cases":12,"assertions":638,"physical_qualification":false}\n','Original absolute qualification provenance')
    need([a['profile'] for a in pins['attempts']]==list(PROFILES),'Actual stopped prefix only')
    need(not any((HERE/('boundary-'+profile+'-attempt01')).exists() for profile in UNEXECUTED),'No later unexecuted profiles inferred')
    identities=[];attempts=[];all_cases=[];failed_progress=None;attempt_file_count=0
    for entry in pins['attempts']:
        profile=entry['profile'];attempt=HERE/entry['path'];inventory(attempt,entry['files']);attempt_file_count+=len(entry['files'])
        result=data(attempt/'RESULTS.json');inner=data(attempt/'state/CONTROL-RESULTS.json');intent=data(attempt/'intent.json')
        need(digest(attempt/'RESULTS.json')==entry['resultSha256'] and digest(attempt/'state/CONTROL-RESULTS.json')==entry['controlResultSha256'],'Actual terminal receipt pins')
        need(result['controlProfile']==inner['profile']==intent['controlProfile']==profile and result['attemptNumber']==intent['attemptNumber']==1,'Exact profile/attempt identity')
        need(intent['priorProfileAttemptResults']==result['priorProfileAttemptResults']==[],'No retry')
        need(digest(attempt/'frozen/SOURCE-REVIEW.json')==REVIEW_SHA,'Actual frozen review input')
        inventory(attempt/'frozen',review['files'],('SOURCE-REVIEW.json',))
        need(intent['sourcePins']=={**{r['path']:r['sha256'] for r in review['files']},'SOURCE-REVIEW.json':REVIEW_SHA},'Exact executed input pin set')
        need(intent['cases']==list(PROFILES[profile]) and intent['wallSeconds']==intent['cpuSeconds']==30 and intent['addressBytes']==512*1024*1024 and
             intent['childCpuSeconds']==5 and intent['childAddressBytes']==256*1024*1024 and intent['nativeChildFileBytes']==1024*1024 and
             intent['fileBytes']==result['fileBytes']==(32 if profile=='mutation' else 1)*1024*1024 and intent['openFiles']==64 and
             intent['cleanupSeconds']==8 and intent['termGraceSeconds']==3,'Unchanged declared execution profiles')
        argv=[intent['interpreter'],'-I','-B',str(attempt/'frozen/boundary_controls.py'),profile,str(attempt/'state'),str(native),str(qualification),str(qualification/'manifest.json'),str(attempt/'frozen/owner/libharness-owner.so')]
        need(intent['argv']==argv and intent['qualificationRerun'] is False and intent['originalQualificationRoot']==str(qualification) and intent['nativeImageSha256']==NATIVE_SHA,'Fixed original command/image roots')
        interpreter_sha=intent['interpreterSha256'];need(digest(intent['interpreter'])==interpreter_sha and result['heldInterpreterBefore']==result['heldInterpreterAfter'] and
             result['heldInterpreterBefore']['sha256']==interpreter_sha,'Held/current interpreter pins')
        need(result['ownerEmpty'] and result['ownerClosed'] and not result['cleanupErrors'] and not result['interruptsPending'] and not result['unexpectedChildrenObserved'],'Outer settled ownership')
        need(inner['ownerEmpty'] and inner['ownerClosed'] and not inner['cleanupErrors'] and not inner['interruptsPending'],'Independent inner cleanup record')
        need(len(result['outerChildrenReaped'])==1 and result['controlExit']==result['outerChildrenReaped'][0],'Exact outer child reap')
        outer=result['controlExit'];identities.append(owned(outer,1 if profile=='mutation' else 0))
        start=data(attempt/'control.started.json');need(all(outer[k]==v for k,v in start.items()),'Started handle→outer exit identity')
        need(result['actualOwnerDeath'] is False and result['fullSimultaneousCapacityEstablished'] is False and result['logicalCeilingBytes']==16*1024*1024,'Scope never broadened')
        records=inner['nativeChildrenReaped']
        for record in records:
            identities.append(owned(record,0,outer['pid']))
            need(record['cpuSeconds']<=5 and record['peakRSSKiB']<=256*1024,'Native observed usage')
        if profile!='mutation':
            need(result['passed'] is True and inner['passed'] is True and inner['failure'] is None and not raw(attempt/'control.stderr'),'Actual completed clean profile')
            need([case['case'] for case in inner['cases']]==list(PROFILES[profile]) and len(records)==len(PROFILES[profile]) and
                 result['innerCases']==result['innerReaps']==len(records),'Exact successful case/reap count')
            need(inner['checks']==(136 if profile=='negative' else 122) and
                 sum(case['checks'] for case in inner['cases'])==inner['checks']-3,'Completed case checks vs owner/finalization checks')
            duration=int(result['controlTerminalObservedMonotonicNs'])-int(result['controlStartedMonotonicNs'])
            need(0<duration==int(result['controlObservedElapsedMonotonicNs'])<=30_000_000_000,'Observed success within original wall bound')
            joined=[]
            for case in inner['cases']:
                name=case['case'];directory=attempt/'state'/name;evidence=data(directory/'evidence.json')
                need(case['passed'] and evidence['case']==name and digest(directory/'evidence.json')==case['evidenceSha256'] and
                     digest(directory/'authority.db')==case['databaseSha256'],'Exact completed case artifacts')
                need(evidence['nativeStartIdentity']==case['nativeStartIdentity'] and evidence['nativeReap']==case['nativeReap'] and
                     all(case['nativeReap'][k]==v for k,v in case['nativeStartIdentity'].items()),'Per-case live start→clean reap join')
                need(evidence['publicWriterRecords'] is True and evidence['directSQLPopulation'] is False,'Actual public writer scope')
                joined.append(case['nativeReap'])
                all_cases.append(audit_database(directory/'authority.db',name,interpreter_sha,evidence))
            need(joined==records,'Every native reap belongs to the exact ordered named case')
        else:
            need(result['passed'] is False and inner['passed'] is False and result['reason']=='RuntimeError: CONTROL_WALL_LIMIT' and
                inner['failure']==inner['terminalFailure']=='RuntimeError: Control interrupted 15','Observed wall failure/orderly TERM path')
            need(result['controlTerminalObservedMonotonicNs'] is None and result['controlObservedElapsedMonotonicNs'] is None and
                 int(result['elapsedMonotonicNs'])>=30_000_000_000,'Failed observed wall bound not a successful duration')
            need(inner['cases']==[] and inner['checks']==209 and len(records)==1 and result['innerCases']==result['innerReaps']==0,'Outer unloaded-inner fields are not native absence')
            need(b'Control interrupted 15' in raw(attempt/'control.stderr') and b'self.pending(identifier)' in raw(attempt/'control.stderr'),'Retained interruption stack')
            directory=attempt/'state/mutation_capacity';need(not (directory/'evidence.json').exists(),'No completed case snapshot invented')
            failed_progress=audit_database(directory/'authority.db','mutation_capacity',interpreter_sha,failed=True)
        attempts.append({'profile':profile,'resultSha256':entry['resultSha256'],'passed':result['passed'],
            'completedCases':len(inner['cases']),'nativeReapsIndependentlyRead':len(records),'outerReaps':1,
            'observedSuccessElapsedNs':result['controlObservedElapsedMonotonicNs'],'finalElapsedNs':result['elapsedMonotonicNs']})
    need(len(all_cases)==18 and len(identities)==22 and len(set(identities))==22 and attempt_file_count==995,'Actual prefix18cases/19native+3outer/995files')
    for entry in pins['attempts']:inventory(HERE/entry['path'],entry['files'])
    audit_source_sha=digest(Path(__file__))
    result={'profile':'hms.standing-boundary-retained-audit/0.1','passed':True,'meaning':'retained evidence audit passed; candidate matrix stopped on failure',
        'checks':checks,'attempts':attempts,'completedProfiles':2,'failedProfiles':1,'completedCases':18,
        'completedProfileControlChecks':258,'completedCaseChecks':252,'failedProfilePartialChecks':209,
        'nativeChildrenReaped':19,'outerChildrenReaped':3,'ownedIdentitiesCurrentlyAbsent':22,'attemptFiles':995,
        'cases':all_cases,'failedMutationProgress':failed_progress,'unexecutedProfiles':list(UNEXECUTED),
        'allEightProfilesPassed':False,'full24CaseMatrixPassed':False,'simultaneousMaximumHistoriesEstablished':False,
        'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False,'qualificationRerun':False,
        'actualOwnerDeathTestedHere':False,'storageScope':'living-owner synchronous COMMIT/rollback exceptions and configured SQLITE_FULL only',
        'partialMutationFailureHasNoFullNativeSnapshot':True,'originalSourceReviewSha256':REVIEW_SHA,'auditInputPinsSha256':INPUT_SHA,
        'auditSourceSha256':audit_source_sha,'publicFilesReverified':244,'sealedParentFilesReverified':4530}
    destination=HERE/'AUDIT.json';body=canon(result)
    with destination.open('xb') as out:out.write(body);out.flush();os.fsync(out.fileno())
    fd=os.open(HERE,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'passed':True,'completedCases':18,'failedCapacityProfile':True,'checks':checks,'attemptFiles':995,'ownedIdentities':22},sort_keys=True))


if __name__=='__main__':main()
