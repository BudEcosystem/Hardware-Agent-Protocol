"""Reconcile the early-key-guard result without changing earlier test evidence."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-run-bundle'; R=B/'results'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,indent=2)+'\n')
old=read(B/'RESULTS.json'); assert old['distinctPassingMethods']==148
assert (B/'RESULTS.json').read_bytes()==(B/'RESULTS-source02.json').read_bytes()
name='attempt03-passed149'; folder=R/name; p=read(folder/'proof.json'); a=folder/'attempt'; result=read(a/'result.json')
assert p['status']==result['status']=='passed' and result['currentPass'] and result['childState']=='exited'
assert p['counts']==dict(testsRun=149,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert p['sqliteConnections']==0 and result['errors']==result['childErrors']==[]
example=a/'scratch/io-run-bundle-example'; raw=(example/'header.json').read_bytes(); header=json.loads(raw)
association=read(example/'association.json'); context=read(example/'trusted-context.json')
assert header['context']==context and association['freshReconstructionMatched'] is True
assert association['bundleDigest']=='sha256:'+hashlib.sha256(b'HMS-PAT-IO-RUN-BUNDLE-v0.1\0'+raw).hexdigest()
expected=['inputs/'+k+'.json' for k in ('candidate','installation','descriptor','bindings','matrix','implementation','authority')]+['cases/%02d.json'%i for i in range(30)]
assert [r['path'] for r in header['manifest']]==expected and len(header['caseIds'])==30
for row in header['manifest']:
    f=example/row['path']; assert 0<f.stat().st_size==row['bytes']<=65536 and sha(f)==row['sha256']
assert sum(r['bytes'] for r in header['manifest'])==header['inputBytes']
for k in ('configurationAttested','runAssociationAttested','implementationIdentityAttested','actualAggregateStorageEnforced','physicalMeasurementChecked','qualificationPassed'): assert association[k] is False
rows={f.relative_to(example).as_posix():f.read_bytes() for f in example.rglob('*') if f.is_file()}
prior=R/'attempt02-passed148/attempt/scratch/io-run-bundle-example'
priorrows={f.relative_to(prior).as_posix():f.read_bytes() for f in prior.rglob('*') if f.is_file()}
assert set(rows)==set(priorrows)==set(expected+['header.json','association.json','trusted-context.json'])
changed=sorted(k for k in rows if rows[k]!=priorrows[k])
assert changed==sorted(['association.json','header.json','inputs/implementation.json','inputs/installation.json',
    'inputs/descriptor.json','inputs/bindings.json','inputs/matrix.json']+['cases/%02d.json'%i for i in range(30)])
assert json.loads(rows['inputs/matrix.json'])['cases']==json.loads(priorrows['inputs/matrix.json'])['cases']
assert json.loads(rows['inputs/matrix.json'])['programs']==json.loads(priorrows['inputs/matrix.json'])['programs']
leaves=[]
def differences(left,right,path):
    assert type(left) is type(right)
    if type(left) is dict:
        assert set(left)==set(right)
        for k in left: differences(left[k],right[k],path+[k])
    elif type(left) is list:
        assert len(left)==len(right)
        for i,(x,y) in enumerate(zip(left,right)): differences(x,y,path+[i])
    elif left!=right:
        assert type(left) is str and type(right) is str
        import re
        assert re.fullmatch(r'(sha256:)?[0-9a-f]{64}',left) and re.fullmatch(r'(sha256:)?[0-9a-f]{64}',right)
        leaves.append(dict(path=path,before=left,after=right))
for k in changed: differences(json.loads(priorrows[k]),json.loads(rows[k]),[k])
write(B/'SOURCE03-IDENTITY-DELTA.json',dict(scope='Every changed example leaf is an exact hash string; full case/program bodies and non-hash fields are unchanged.',changedFiles=changed,leaves=leaves))
identity=read(example/'inputs/implementation.json'); oldidentity=read(prior/'inputs/implementation.json')
assert identity['workerDigest']!=oldidentity['workerDigest']
assert identity['driverDigest']!=oldidentity['driverDigest']
assert {k:v for k,v in identity.items() if k not in ('workerDigest','driverDigest')}=={k:v for k,v in oldidentity.items() if k not in ('workerDigest','driverDigest')}
entry=dict(attempt=name,status='passed',counts=p['counts'],testSeconds=p['testSeconds'],elapsedSeconds=p['elapsedSeconds'],
    sourceIndexSha256=p['sourceIndexSha256'],harnessIndexSha256=p['harnessIndexSha256'],actualOrigins=p['actualOrigins']['recordCount'],
    rawScratch=p['rawScratch'],rawScratchFiles=p['rawScratchFiles'],rawScratchBytes=p['rawScratchBytes'],attemptFilesAcquired=p['attemptFilesAcquired'],
    example=dict(headerBytes=len(raw),inputDocuments=37,inputBytes=header['inputBytes'],retainedExampleFiles=len(rows),
        retainedExampleBytes=sum(map(len,rows.values())),bundleDigest=association['bundleDigest']))
analysis=old | dict(scope='Bounded pre-run I/O carriers with early builtin-key guard;149pure methods on source03. No supervisor/device execution.',
    distinctPassingMethods=149,newMethods=20,productionUnchangedBetweenVersions=False,productionUnchangedSource01To02=True,
    completeExampleBytesEqualBetweenVersions=False,completeExampleBytesEqualSource01To02=True,
    source03ExampleChangedFiles=changed,source03Change='Exact builtin key/value checks precede path-set hashing.',attempts=old['attempts']+[entry])
write(B/'RESULTS.json',analysis)
(folder/'README.md').write_text(f'''# Current pure149 attempt passes

[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).
149methods pass in {p['testSeconds']:.3f} test seconds and {p['elapsedSeconds']:.3f}s harness elapsed.
The original180s parent bound and all group/input/storage/effect ceilings remain.
230project files,233frozen entries,6active harness files and159external pins remain unchanged;
{p['actualOrigins']['recordCount']}origins match, {p['bytecodeReadsRefused']}bytecode reads are refused, and no SQL connection occurs.
Original raw scratch and its complete copy retain {p['rawScratchFiles']}files/{p['rawScratchBytes']}bytes.

The [header](attempt/scratch/io-run-bundle-example/header.json) binds37documents/{header['inputBytes']}bytes;
its {len(raw)}bytes remain within the original per-carrier limit. The [association record](attempt/scratch/io-run-bundle-example/association.json)
reports exact fresh reconstruction; configuration/run/implementation attestation,
actual aggregate enforcement, physical measurement and qualification remain false.
Source03 changes both conservative driver and worker identities. Installation, descriptor, binding,
static-contract and enclosing manifest hashes change transitively; the exact case/program bodies,
candidate, original authority and logical context remain identical. Every changed example leaf
is a hash string; the retained identity-delta report records each path and both values.
The [key guard](../../KEY-GUARD.md) adds one regression and changes only validation order.
No supervisor launch, runtime effects, device/MCU, inference or live service ran.
''')
table='\n'.join(f"| [{e['attempt']}]({e['attempt']}/README.md) |{e['counts']['testsRun']-e['counts']['failures']}pass /{e['counts']['failures']}failure |{e['testSeconds']:.3f}|{e['rawScratchFiles']} /{e['rawScratchBytes']}|" for e in analysis['attempts'])
(R/'README.md').write_text(f'''# Bounded pre-run I/O bundle:149 pure checks pass

The [current source03](../implementation03/README.md) passes149methods in {p['testSeconds']:.3f} test seconds
({p['elapsedSeconds']:.3f}s harness elapsed):129unchanged pure checks and20new bundle checks.
GPIO/PWM setup reconstructs exactly. Missing/extra/reordered documents, changed content,
cross-run/configuration substitution, malformed numeric types and changed source identities refuse.
The parser's no-I/O/planner/SQL/clock guards pass; custom key hooks refuse before hashing.
Fully rehashed false setup and changed original authority demonstrate the separate structural
and fresh-validation boundaries. Logical metadata and hashes alone do not attest a deployment.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
{table}

The first [test correction](../CORRECTION.md) changes only the mock lookup and verifies its call.
The later [key guard](../KEY-GUARD.md) moves type validation before set comparison and adds one method.
All228original baseline project files remain byte-identical in current source03. Each attempt
retains230project inputs,233frozen entries,6active harness inputs and159external pins.
Complete original attempts, raw scratch and the initial failed assertion remain retained.
Current driver/worker identities and dependent hashes reflect the source03 change; non-hash
fields and exact case/program bodies are unchanged. The initial reporting reduction's overly narrow
identity-change assertion is preserved in [analysis correction](../ANALYSIS-CORRECTION.md).
No SQL connection, runtime/device effect, inference or live service ran. Primary-agent review only.

The [design](../DESIGN.md) is an input association component. Trusted service configuration,
durable retention before release, owned child/run association, complete output collection,
hard aggregate storage and public qualification remain required. The broader prompt-to-PAT,
physical device/driver/hub and microscope objective remains active.
''')
(B/'README.md').write_text('# Pre-run I/O bundle\n\n[Design](DESIGN.md), [results](results/README.md), [test correction](CORRECTION.md), [key guard](KEY-GUARD.md).\nCurrent additive source: [implementation03](implementation03/README.md).\n')
print(json.dumps(entry))
