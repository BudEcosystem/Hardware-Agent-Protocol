"""Stdlib-only retained audit of the fixed32-loop diagnostic.

Source-only until root review. Imports no candidate and starts/signals no child.
SQLite reads use immutable read-only URI/query_only; all inputs are rehashed.
Only a new exclusive AUDIT receipt may be published after authorized execution.
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
REVIEW_SHA='75bb8a047304aa6b2cd4348837e68843b01983a947640c356b8a2764ea75f082'
INPUT_SHA='411c75b8a22b50a51c6e2fe9cc09cf688ab89be8c0246759499a21ed3eee970d'
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


def audit_trace(entries,route,mapping):
    need(type(entries) is list and len(entries)==140,'Exact original70 request/reply pairs')
    requests={};responses={};counts={1:0,16:0,64:0,67:0};last_tx=last_rx=0
    for entry in entries:
        need(type(entry) is dict and set(entry)=={'direction','session','sequence','raw'},'Trace fields')
        uint(entry['session']);uint(entry['sequence'],2**32-1)
        body=bytes.fromhex(entry['raw']);need(body.hex()==entry['raw'] and 2<=len(body)<=192 and body[0]==2,'Canonical bounded v2 bytes')
        if entry['direction']=='request':
            op=body[1];need(op in counts and entry['sequence']>last_tx and entry['session']==(0 if op==1 else 1),'No START or other new effect in trace')
            counts[op]+=1;last_tx=entry['sequence'];requests[last_tx]=entry
            if op>=64:reference(body,mapping)
            if op==67:need(len(body)==49 and body[44:]==bytes(5),'Exact read-only STATUS page0')
        else:
            need(entry['direction']=='response' and entry['session']==1 and len(body)>=66 and entry['sequence']==last_rx+1,'Complete decoded reply sequence')
            tx=u32(body,2);need(tx in requests and tx not in responses and body[1]==bytes.fromhex(requests[tx]['raw'])[1]|128 and body[6]==0,'One successful original reply per request')
            responses[tx]=entry;last_rx=entry['sequence']
            if body[1]>=192:reference(body,mapping,8)
    need(counts=={1:4,16:1,64:1,67:64} and len(requests)==len(responses)==70 and
         set(requests)==set(responses) and last_tx==route['tx'] and last_rx==route['rx'],'Exact trace closure below durable route')
    return requests,responses


def audit_database(path,evidence,interpreter_sha):
    before=digest(path);size=path.stat().st_size;need(size<=1024*1024,'Original1MiB file bound')
    sidecars=lambda:any(Path(str(path)+suffix).exists() for suffix in ('-journal','-wal','-shm'))
    need(not sidecars(),'Closed retained DB')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        db.execute('PRAGMA query_only=ON');need(db.execute('PRAGMA query_only').fetchone()[0]==1,'Read-only audit connection')
        need(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)] and not db.execute('PRAGMA foreign_key_check').fetchall(),'Retained SQLite integrity')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        charge,counts=charges(db,tables);meta=dict(db.execute('SELECT key,value FROM meta'))
        installed=doc(db.execute('SELECT document FROM sd_meta').fetchone()[0],65536)
        route=doc(db.execute('SELECT document FROM sd_route').fetchone()[0],4096);installation=installed['installation']
        need(installed['authorityId']==meta['authority'] and installed['installationDigest']==identity('HMS-STANDING-INSTALLATION-v0.1',installation),'Installed identity')
        expected_host=identity('HMS-STANDING-HOST-IMAGE-v0.1',{'sources':{p:'sha256:'+digest(HERE/'project'/p) for p in HOST_SOURCES},
            'interpreter':'sha256:'+interpreter_sha,'dependencyScope':'original-source-pins;trusted-python-stdlib-loader-validation-packages'})
        expected_driver=identity('HMS-STANDING-PIPE-SOURCES-v0.1',{p:'sha256:'+digest(HERE/'project'/p) for p in DRIVER_SOURCES})
        need(installation['hostImplementationDigest']==expected_host and installation['driverSourceDigest']==expected_driver and
             installation['driverImageDigest']=='sha256:'+NATIVE_SHA and installation['qualificationImageDigest']=='sha256:'+QUALIFIER_SHA,'Actual installed source/image scope')
        evaluations=db.execute('SELECT evaluator,run_id,document FROM sp_evaluations').fetchall()
        need(len(evaluations)==1 and evaluations[0][:2]==('standing-native-controls-v1','native-standing-original:4'),'Original evaluation run');doc(evaluations[0][2],16384)
        stored=db.execute('SELECT id,principal,deployment,namespace,caller_key,request_digest,document FROM sd_deployments').fetchall()
        need(len(stored)==1,'One retained deployment');sql=stored[0];row=doc(sql[6],32768);mapping=row['mapping'];identifier=row['id']
        need(tuple(row[k] for k in ('id','principal','deployment','namespace','key','requestDigest'))==sql[:6],'Exact deployment SQL identity')
        need(row['requestDigest']==mapping['requestDigest']==identity('HMS-STANDING-REQUEST-v0.1',row['request']),'Exact original request')
        base=dict(mapping);base.pop('deploymentDigest');need(mapping['deploymentDigest']==identity('HMS-STANDING-DEPLOYMENT-v0.1',base),'Frozen deployment mapping')
        need(mapping['authorityId']==meta['authority'] and mapping['installationDigest']==installed['installationDigest'] and
             row['key']==row['request']['deploymentKey']=='application' and row['namespace']==row['request']['replayNamespace'],'Authority and original key')
        need(mapping['resourceProof']['expandedClaims']['control']==['atom:demand','atom:output'] and
             sorted((claim['resource'],claim['fence']) for claim in mapping['claims'])==[('atom:demand',1),('atom:output',1),('atom:slot',1)],'Physical2/actual3 fenced claims')
        owned_claims=db.execute('SELECT resource,fence FROM claims WHERE operation_id=? ORDER BY resource',(identifier,)).fetchall()
        need(owned_claims==[('atom:demand',1),('atom:output',1),('atom:slot',1)] and
             [r[0] for r in db.execute('SELECT instance_id FROM resource_owner_instances WHERE owner_id=? ORDER BY instance_id',(identifier,))]==['native:finite','native:standing'],'Same shared authority remains occupied')
        for key in ('retired','disputed','effectUnknown','recoveryRequired','sequenceUncertain','transportUncertain'):need(row[key] is False,'No unresolved flag invented '+key)
        need(row['everPossiblyActed'] is True and row['openState']=='accepted' and row['revoke'] is None,'Accepted original OPEN with no terminal laundering')
        for key in ('mutationSequence','collected','acknowledged','highWater'):uint(row[key]);need(row[key]==0,'Zero durable sequence/prefix')
        need(route['boot']==mapping['boot']=='1' and route['standingFloor']==mapping['standingNumber']==1 and route['fences']==mapping['fences'],'Monotonic original allocation')
        opened=bytes.fromhex(row['open']);need(len(opened)==134 and opened[:2]==b'\x02\x40','Exact OPEN');reference(opened,mapping)
        configuration=struct.pack('>iiii6H4B',20000,30000,0,500,10,100,100,0,0,50,0,1,0,0)
        need(opened[47:79]==configuration and opened[79]==3 and [u32(opened,80+4*i) for i in range(8)]==mapping['fences'] and
             u64(opened,112)==1000 and u32(opened,122)==100 and u32(opened,126)==u32(opened,130)==1,'Original tested literal domain')
        requests,responses=audit_trace(evidence['trace'],route,mapping)
        need(requests[row['openTx']]['raw']==row['open'],'Original OPEN occurred exactly once')
        retained_envelopes=[row['openReply'],row['lastStatus']];mutations=[]
        for number,key,sequence,body in db.execute('SELECT number,host_key,endpoint_sequence,document FROM sd_mutations ORDER BY number'):
            item=doc(body,1536);mutations.append(item)
            need(set(item)=={'number','hostKey','opcode','endpointSequence','body','bodyDigest','tx','leaseUntil','ack','state','reply','settlement'},'Closed never-handed-off record')
            for field in ('number','opcode','endpointSequence','tx','leaseUntil','ack'):uint(item[field])
            need((number,key,sequence)==(len(mutations),'never-start:'+str(len(mutations)-1),1)==(item['number'],item['hostKey'],item['endpointSequence']),'Original contiguous key/sequence')
            need(item['opcode']==65 and item['leaseUntil']==item['ack']==0 and item['state']=='never_handed_off' and
                 item['settlement']=='durable-prepared-never-possible','Original START retained as never handed off')
            payload=bytes.fromhex(item['body']);need(payload.hex()==item['body'] and len(payload)==66 and payload[:2]==b'\x02\x41','Canonical START body');reference(payload,mapping)
            need(item['bodyDigest']=='sha256:'+sha(payload) and u32(payload,44)==1 and u32(payload,48)==row['revision'] and
                 payload[52:]==bytes(14) and item['tx'] not in requests,'Original immutable START never sent')
            req,res=envelope(item['reply'],mapping);retained_envelopes.append(item['reply'])
            need(req[1]==67 and res[6]==0 and u32(res,54)==0 and len(res)==190,'Unchanged-sequence actual STATUS settlement')
        need(len(mutations)==32 and len({m['tx'] for m in mutations})==32,'All32 original reserved tx identities')
        for env in retained_envelopes:
            envelope(env,mapping)
            need(env['tx'] in requests and requests[env['tx']]['raw']==env['request'] and responses[env['tx']]['raw']==env['response'] and
                 responses[env['tx']]['sequence']==env['rx'] and responses[env['tx']]['session']==int(env['boot']),'Each durable envelope joins actual trace')
        for table in ('sd_activations','sd_activation_versions','sd_episodes','sd_conflicts','operations','events','replay_keys'):need(counts[table]==0,'No new effect/finite/episode history '+table)
        need(counts['sd_mutations']==32 and counts['claims']==3 and evidence['tableCounts']==counts and evidence['capacity']==charge and
             evidence['route']==route and evidence['deploymentId']==identifier and evidence['ownerEpoch']==int(meta['owner_epoch'])==row['ownerEpoch'] and
             evidence['authority']==meta['authority'],'Independent accounting and evidence joins')
        native=evidence['native'];initial=evidence['diagnostic']['initialNative']
        need(set(native)==set(initial)=={str(n) for n in range(28)},'All28 before/after selectors')
        for value in list(native.values())+list(initial.values()):uint(value)
        need(all(native[key]==initial[key] for key in native if key!='22') and initial['22']==6 and native['22']==70,'Read-only recovery changes only response sequence')
        expected={0:0,1:0,2:0,3:1,4:1,5:1,7:2,8:2,9:1,10:0,11:0,13:0,14:3,15:0,16:25,17:0,18:0,19:1,20:1,21:1,23:0,24:0,25:0,26:25000,27:2**32-1}
        need(all(native[str(k)]==v for k,v in expected.items()),'Exact unchanged fixed native driver state')
        state=bytes.fromhex(row['lastStatus']['response'])[66:]
        need(len(state)==124 and state[89]==native['5'] and state[92]==native['14'] and state[93]==native['15'] and
             u32(state,1)==row['revision']==native['12'] and u16(state,96)==native['6'] and u32(state,5)==0,'Durable native STATUS counters/flags')
        return {'databaseSha256':before,'databaseBytes':size,'chargedLogicalBytes':charge['chargedLogicalBytes'],
            'retainedMutations':32,'retainedClaims':3,'acceptedOpen':True,'retired':False,'mutationSequence':0,
            'activations':0,'episodes':0,'wireRequests':70,'wireResponses':70,'selectors':28}
    finally:
        db.close();need(digest(path)==before and not sidecars(),'Read-only DB bytes and sidecars unchanged')


def decimal(value):
    need(type(value) is str and value.isascii() and value.isdigit() and str(int(value))==value,'Canonical decimal duration')
    number=int(value);need(0<=number<=30_000_000_000,'Bounded nonnegative diagnostic nanoseconds');return number


def audit_metrics(diag):
    expected={'loopCount':32,'mutationValidationCalls':2176,'mutationReadCalls':2176,'predictedReadSelects':4352,
        'retainedMutations':32,'neverHandedOffRecords':32,'retainedClaims':3,'mutationSequence':0,'collected':0,'acknowledged':0,'highWater':0}
    for key,value in expected.items():uint(diag[key]);need(diag[key]==value,'Exact diagnostic counter '+key)
    need(diag['intrusiveInstrumentation'] is True and diag['instrumentationOverheadKnown'] is False and
         diag['selectCountIndependentlyObserved'] is False and diag['full128RecordQualification'] is False and diag['timingExtrapolation'] is False,'Intrusive count/timing limits retained')
    contexts=('policy.hold_image','driver.hold','catalog.hold_selection','producer.snapshot')
    labels={'store.mutation','store.pending','store.reserve_mutation','store.abandon_prepared_mutation',
            'policy.fresh','policy.check_image','catalog._selected'}|{'store._read_locked:'+table for table in
            ('sd_meta','sd_route','sd_deployments','sd_mutations','sd_activations','sd_episodes','sd_activation_versions','sd_conflicts')}|{label+suffix for label in contexts for suffix in ('.enter','.exit','.held')}
    loop_phases={str(n)+':'+part for n in range(32) for part in ('mutate','abandon','assert')}
    phases=loop_phases|{'setup','final','cleanup'};rows={};totals={};exclusive=0
    need(type(diag['metrics']) is list and len(diag['metrics'])<=len(phases)*len(labels),'Bounded aggregate rows')
    for row in diag['metrics']:
        need(type(row) is dict and set(row)=={'phase','method','calls','errors','inclusiveNs','exclusiveNs'},'Closed metric shape')
        key=(row['phase'],row['method']);need(key[0] in phases and key[1] in labels and key not in rows,'Unique closed metric phase/label')
        uint(row['calls'],100000);need(row['calls']>0 and type(row['errors']) is int and row['errors']==0,'Successful measured calls')
        inclusive=decimal(row['inclusiveNs']);held=key[1].endswith('.held')
        if held:need(row['exclusiveNs'] is None,'Overlapping held lifetime has no exclusive duration')
        else:need(decimal(row['exclusiveNs'])<=inclusive,'Exclusive measured wall subset')
        rows[key]=row
        if key[0] in loop_phases and not held:
            entry=totals.setdefault(key[1],{'calls':0,'inclusiveNs':0,'exclusiveNs':0})
            entry['calls']+=row['calls'];entry['inclusiveNs']+=inclusive;entry['exclusiveNs']+=int(row['exclusiveNs']);exclusive+=int(row['exclusiveNs'])
    need([tuple((r['phase'],r['method'])) for r in diag['metrics']]==sorted(rows),'Deterministic aggregate ordering')
    def count(phase,label):return rows.get((phase,label),{'calls':0})['calls']
    iterations=diag['iterations'];need(type(iterations) is list and len(iterations)==32,'All32 iteration reports')
    phase_elapsed=0;loop_count=0
    for n,entry in enumerate(iterations):
        need(set(entry)=={'number','key','predictedMutationValidations','mutationValidationCalls','mutationReadCalls','mutateElapsedNs','abandonElapsedNs','assertElapsedNs'},'Exact iteration shape')
        for field in ('number','predictedMutationValidations','mutationValidationCalls','mutationReadCalls'):uint(entry[field])
        need(entry['number']==n and entry['key']=='never-start:'+str(n) and
             entry['predictedMutationValidations']==entry['mutationValidationCalls']==entry['mutationReadCalls']==4*n+6,'Original per-iteration count')
        for part,expected_count in (('mutate',2*n),('abandon',n+5),('assert',n+1)):
            phase=str(n)+':'+part;elapsed=decimal(entry[part+'ElapsedNs']);phase_elapsed+=elapsed
            need(count(phase,'store.mutation')==count(phase,'store._read_locked:sd_mutations')==expected_count,'Exact phase validation count')
            measured=sum(int(r['exclusiveNs']) for (p,label),r in rows.items() if p==phase and not label.endswith('.held'))
            need(measured<=elapsed,'Nonoverlapping exclusive measured spans fit phase wall time')
        loop_count+=4*n+6
    need(loop_count==totals['store.mutation']['calls']==totals['store._read_locked:sd_mutations']['calls']==2176,'Independent summed validation count')
    loop_elapsed=decimal(diag['loopElapsedNs']);need(exclusive<=phase_elapsed<=loop_elapsed,'Measured exclusive spans do not double-count inclusive parents')
    for phase in phases:
        for label in contexts:
            need(count(phase,label+'.enter')==count(phase,label+'.exit')==count(phase,label+'.held'),'Complete successful context lifetime')
    for key in ('candidateImportsElapsedNs','fixtureSetupElapsedNs','applicationSetupElapsedNs','moduleToLoopsSetupNs'):decimal(diag[key])
    need(int(diag['candidateImportsElapsedNs'])+int(diag['fixtureSetupElapsedNs'])+int(diag['applicationSetupElapsedNs'])<=int(diag['moduleToLoopsSetupNs']),'Separate setup spans below true loop start')
    return {'metricRows':len(rows),'loopElapsedNs':str(loop_elapsed),'phaseElapsedNs':str(phase_elapsed),
        'nonHeldExclusiveNs':str(exclusive),'outsideMeasuredSpansNs':str(loop_elapsed-exclusive),
        'loopMethodTotals':{label:{k:(str(v) if k.endswith('Ns') else v) for k,v in values.items()} for label,values in sorted(totals.items())},
        'contextHeldLifetimesAreOverlapping':True,'durationsAreWallNotCpu':True,'overheadKnown':False,
        'performanceImprovementEstablished':False,'timeExtrapolation':False}


def owned(record,cpu,memory,parent=None):
    for field in ('pid','parent','group','session','startTicks'):uint(record[field]);need(record[field]>0,'Positive retained process identity')
    need(record['reaped'] is True and record['exitCode']==0,'Clean owned child reap')
    if parent is not None:need(record['parent']==parent,'Exact direct-parent role')
    need(type(record['cpuSeconds']) in (int,float) and 0<=record['cpuSeconds']<=cpu and
         type(record['peakRSSKiB']) is int and 0<=record['peakRSSKiB']<=memory,'Observed process usage within original per-process bounds')
    need(not Path('/proc',str(record['pid'])).exists(),'Observed identity currently absent; no stored-PID signaling authority')
    return (record['pid'],record['startTicks'])


def main():
    need(len(sys.argv)==1 and not sys.flags.optimize,'Fixed assertion-enabled data audit')
    source_sha=digest(Path(__file__))
    need(digest(HERE/'SOURCE-REVIEW.json')==REVIEW_SHA and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA,'Exact source and actual attempt inventories')
    review=data(HERE/'SOURCE-REVIEW.json',False);inputs=data(HERE/'source-pins.json',False);pins=data(HERE/'AUDIT-INPUT-PINS.json',False)
    need(len(review['files'])==299 and review['inputBytes']==6428900 and pins['sourceReviewSha256']==REVIEW_SHA,'Original frozen299 files')
    def stable():
        for row in review['files']:need((HERE/row['path']).lstat().st_size==row['bytes'] and digest(HERE/row['path'])==row['sha256'],'Frozen source unchanged')
        count=0
        for parent_spec in (inputs['parentPacket'],inputs['secondParentPacket']):
            parent=REPO/parent_spec['path'];need(digest(parent/'index.json')==parent_spec['indexSha256'],'Sealed parent index')
            rows=data(parent/'index.json',False)['files'];inventory(parent,rows,('index.json',));count+=len(rows)
        need(count==5067,'Both exact sealed parent inventories')
        receipt=REPO/inputs['publicReceipt']['path'];need(digest(receipt)==inputs['publicReceipt']['sha256'],'Public receipt pin')
        public=data(receipt,False)['files'];need(len(public)==244,'Public244')
        for row in public:need(digest(REPO/row['path'])==row['sha256'],'Public bytes exact')
        need(len(inputs['copies'])==261 and len(inputs['originalProvenance'])==25,'Exact reuse and provenance scope')
        for row in inputs['copies']+inputs['originalProvenance']:
            need(digest(REPO/row['source'])==digest(HERE/row['copy'])==row['sha256'] and (HERE/row['copy']).stat().st_size==row['bytes'],'Original source/copy join')
    stable()
    native=Path(inputs['nativeImage']);qualification=Path(inputs['qualificationRoot'])
    expected_parent=REPO/'artifacts/implementation/standing-host-deployment'
    need(native==expected_parent/'host-attempt04/standing-host-pipe' and qualification==expected_parent/'host-attempt04/qualification','Original absolute provenance roots')
    need(digest(native)==NATIVE_SHA and digest(qualification/'standing-controls')==QUALIFIER_SHA,'Actual original images')
    manifest=data(qualification/'manifest.json',False);receipt=data(qualification/'receipt.json');reservation=data(qualification/'reservation.json')
    need(manifest['argv']==[str(qualification/'standing-controls')] and manifest['runId']=='native-standing-original:4' and
         receipt['attemptId']==reservation['attemptId']=='native-standing-attempt:4' and receipt['argv']==reservation['argv']==manifest['argv'] and
         receipt['runId']==reservation['runId']==manifest['runId'] and manifest['receiptDigest']=='sha256:'+digest(qualification/'receipt.json') and
         manifest['reservationDigest']==receipt['reservationDigest']=='sha256:'+digest(qualification/'reservation.json') and
         raw(qualification/'stdout')==b'{"cases":12,"assertions":638,"physical_qualification":false}\n' and not raw(qualification/'stderr'),'Original qualification association, no rerun')
    need(pins['attempt']['path']=='history-cost-attempt01','Single original diagnostic attempt')
    attempt=HERE/pins['attempt']['path'];inventory(attempt,pins['attempt']['files'])
    result=data(attempt/'RESULTS.json');inner=data(attempt/'state/CONTROL-RESULTS.json');intent=data(attempt/'intent.json')
    need(digest(attempt/'RESULTS.json')==pins['attempt']['resultSha256'] and
         digest(attempt/'state/CONTROL-RESULTS.json')==pins['attempt']['controlResultSha256'],'Actual terminal receipt pins')
    inventory(attempt/'frozen',review['files'],('SOURCE-REVIEW.json',));need(digest(attempt/'frozen/SOURCE-REVIEW.json')==REVIEW_SHA,'Executed frozen review')
    need(intent['sourcePins']=={**{r['path']:r['sha256'] for r in review['files']},'SOURCE-REVIEW.json':REVIEW_SHA},'Exact executed inputs')
    need(result['passed'] is True and inner['passed'] is True and result['reason'] is inner['failure'] is None and
         inner['profile']==result['controlProfile']==intent['controlProfile']=='history-cost' and
         result['attemptNumber']==intent['attemptNumber']==1 and result['priorProfileAttemptResults']==intent['priorProfileAttemptResults']==[],'Original successful diagnostic, no retry')
    need(intent['cases']==['history_cost'] and intent['diagnosticLoops']==32 and intent['expectedMutationValidationCalls']==2176 and
         intent['wallSeconds']==intent['cpuSeconds']==30 and intent['addressBytes']==512*1024*1024 and
         intent['childCpuSeconds']==5 and intent['childAddressBytes']==256*1024*1024 and
         intent['fileBytes']==intent['nativeChildFileBytes']==result['fileBytes']==1024*1024 and intent['openFiles']==64 and
         intent['cleanupSeconds']==8 and intent['termGraceSeconds']==3 and intent['stateDiskBytes']==96*1024*1024,'Unchanged declared process bounds')
    argv=[intent['interpreter'],'-I','-B',str(attempt/'frozen/history_cost_controls.py'),'history-cost',str(attempt/'state'),
          str(native),str(qualification),str(qualification/'manifest.json'),str(attempt/'frozen/owner/libharness-owner.so')]
    need(intent['argv']==argv and intent['nativeImageSha256']==NATIVE_SHA and intent['originalQualificationRoot']==str(qualification) and
         intent['originalQualificationRunId']=='native-standing-original:4' and intent['qualificationRerun'] is False,'Exact command and native provenance')
    interpreter_sha=intent['interpreterSha256']
    need(digest(intent['interpreter'])==interpreter_sha and result['heldInterpreterBefore']==result['heldInterpreterAfter'] and
         result['heldInterpreterBefore']['sha256']==interpreter_sha,'Held/current interpreter identity')
    for report in (result,inner):need(report['ownerEmpty'] and report['ownerClosed'] and not report['cleanupErrors'] and not report['interruptsPending'],'Independent clean ownership receipts')
    need(not result['unexpectedChildrenObserved'] and len(result['outerChildrenReaped'])==1 and result['controlExit']==result['outerChildrenReaped'][0],'One exact outer child')
    outer=result['controlExit'];identities=[owned(outer,30,512*1024)]
    start=data(attempt/'control.started.json');need(all(outer[k]==v for k,v in start.items()),'Outer registration→reap identity')
    need(len(inner['nativeChildrenReaped'])==1 and result['innerCases']==result['innerReaps']==1 and
         [case['case'] for case in inner['cases']]==['history_cost'],'One exact named native case')
    native_reap=inner['nativeChildrenReaped'][0];identities.append(owned(native_reap,5,256*1024,outer['pid']))
    need(len(set(identities))==2 and not raw(attempt/'control.stderr'),'Distinct owned identities, empty successful stderr')
    stdout=json.loads(raw(attempt/'control.stdout'));need(stdout==inner,'Final inner stdout/receipt agreement')
    elapsed=int(result['controlTerminalObservedMonotonicNs'])-int(result['controlStartedMonotonicNs'])
    need(0<elapsed==decimal(result['controlObservedElapsedMonotonicNs'])<=30_000_000_000 and
         int(result['elapsedMonotonicNs'])>=elapsed,'Observed original control deadline; final includes cleanup')
    case=inner['cases'][0];directory=attempt/'state/history_cost';evidence=data(directory/'evidence.json')
    need(case['passed'] is True and evidence['case']=='history_cost' and digest(directory/'evidence.json')==case['evidenceSha256'] and
         digest(directory/'authority.db')==case['databaseSha256'],'Retained case artifacts')
    need(case['nativeReap']==evidence['nativeReap']==native_reap and case['nativeStartIdentity']==evidence['nativeStartIdentity'] and
         all(native_reap[k]==v for k,v in case['nativeStartIdentity'].items()),'Per-case registered native identity→clean reap')
    need(evidence['publicWriterRecords'] is True and evidence['directSQLPopulation'] is False and
         inner['diagnostic']==evidence['diagnostic']==result['diagnostic'] and inner['partialMetrics'] is None and inner['interruptedMetricFrames']==0,'Actual public writer and complete metric evidence')
    need(type(case['checks']) is int and inner['checks']==case['checks']+1,'Fixed invocation plus completed case checks')
    database=audit_database(directory/'authority.db',evidence,interpreter_sha);timing=audit_metrics(evidence['diagnostic'])
    need(decimal(evidence['diagnostic']['moduleToLoopsSetupNs'])+decimal(evidence['diagnostic']['loopElapsedNs'])<=elapsed,'Setup and loops within actual observed control')
    for report in (intent,result,inner):
        for key in ('productionChanged','full128RecordQualification','physicalEligible','protectedCapacity','publicMountEligible'):
            need(report[key] is False,'Explicit unchanged narrow diagnostic scope '+key)
    need(result['qualificationRerun'] is False and result['fullSimultaneousCapacityEstablished'] is False and
         result['logicalCeilingBytes']==16*1024*1024 and result['actualOwnerDeath'] is inner['actualOwnerDeath'] is False,'No broader capacity/crash claim')
    stable();inventory(attempt,pins['attempt']['files']);need(digest(Path(__file__))==source_sha,'Auditor source stable')
    need(digest(intent['interpreter'])==interpreter_sha and digest(HERE/'AUDIT-INPUT-PINS.json')==INPUT_SHA,'Interpreter and audit inputs stable through read')
    output={'profile':'hms.standing-host-history-cost-retained-audit/0.1','passed':True,'checks':checks,
        'meaning':'Independent retained diagnostic joins; no production optimization or full capacity qualification.',
        'originalSourceReviewSha256':REVIEW_SHA,'auditInputPinsSha256':INPUT_SHA,'auditSourceSha256':source_sha,
        'attemptResultSha256':pins['attempt']['resultSha256'],'attemptFiles':len(pins['attempt']['files']),
        'sourceFilesReverified':299,'reuseFiles':261,'provenanceCopies':25,'sealedParentFilesReverified':5067,'publicFilesReverified':244,
        'completedCases':1,'loopCount':32,'mutationValidations':2176,'ownedIdentitiesCurrentlyAbsent':2,
        'nativeReaps':1,'outerReaps':1,'controlObservedElapsedNs':str(elapsed),'finalElapsedNs':result['elapsedMonotonicNs'],
        'database':database,'timing':timing,'productionChanged':False,'qualificationRerun':False,
        'full128RecordQualification':False,'oldFailedCapacityProfileRemainsFailed':True,
        'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
    destination=HERE/'AUDIT.json';temporary=HERE/'.AUDIT.json.pending';body=canon(output)
    need(len(body)<=1024*1024,'Bounded audit receipt')
    with temporary.open('xb') as out:out.write(body);out.flush();os.fsync(out.fileno())
    os.link(temporary,destination,follow_symlinks=False)
    fd=os.open(HERE,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd);temporary.unlink();os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'passed':True,'checks':checks,'cases':1,'mutationValidations':2176,'attemptFiles':len(pins['attempt']['files']),'ownedIdentities':2},sort_keys=True))


if __name__=='__main__':main()


