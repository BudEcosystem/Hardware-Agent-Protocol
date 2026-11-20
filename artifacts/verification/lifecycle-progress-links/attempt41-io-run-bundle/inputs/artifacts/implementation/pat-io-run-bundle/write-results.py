"""Reduce retained test evidence; execute only after acquisition completes."""
import hashlib
import json
from pathlib import Path

ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-run-bundle'; R=B/'results'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as f: f.write(json.dumps(v,indent=2)+'\n')
entries=[]; examples=[]; identities={}
for name,status in [('attempt01-failed148','failed'),('attempt02-passed148','passed')]:
    folder=R/name; proof=read(folder/'proof.json'); attempt=folder/'attempt'
    result=read(attempt/'result.json')
    assert proof['status']==result['status']==status and result['childState']=='exited'
    assert proof['counts']['testsRun']==148 and proof['counts']['failures']==(1 if status=='failed' else 0)
    assert proof['counts']['errors']==proof['sqliteConnections']==0 and proof['sourceFilesVerified']==230
    assert proof['frozenFilesVerified']==233 and proof['externalPinsVerified']==159
    assert result['errors']==result['childErrors']==[] and result['currentPass'] is (status=='passed')
    example=attempt/'scratch/io-run-bundle-example'; header=(example/'header.json').read_bytes(); value=json.loads(header)
    association=read(example/'association.json'); context=read(example/'trusted-context.json')
    assert value['context']==context
    assert association['bundleDigest']=='sha256:'+hashlib.sha256(b'HMS-PAT-IO-RUN-BUNDLE-v0.1\0'+header).hexdigest()
    assert association['freshReconstructionMatched'] is True and association['expectedCases']==len(value['caseIds'])==30
    for key in ('configurationAttested','runAssociationAttested','implementationIdentityAttested',
            'actualAggregateStorageEnforced','physicalMeasurementChecked','qualificationPassed'): assert association[key] is False
    expected=['inputs/'+k+'.json' for k in ('candidate','installation','descriptor','bindings','matrix','implementation','authority')]
    expected+=['cases/%02d.json'%i for i in range(30)]
    assert [r['path'] for r in value['manifest']]==expected
    total=0
    for row in value['manifest']:
        p=example/row['path']; assert 0<p.stat().st_size==row['bytes']<=65536 and sha(p)==row['sha256']; total+=row['bytes']
    assert total==value['inputBytes']<=2555904 and len(header)<=65536
    rows={p.relative_to(example).as_posix():p.read_bytes() for p in example.rglob('*') if p.is_file()}
    assert set(rows)==set(expected+['header.json','association.json','trusted-context.json'])
    examples.append(rows)
    for label in ('compiler','driver'):
        ident=read(attempt/(label+'-before.json')); assert ident==read(attempt/(label+'-after.json'))
        if label in identities: assert identities[label]==ident
        else: identities[label]=ident
    entry=dict(attempt=name,status=status,counts=proof['counts'],testSeconds=proof['testSeconds'],elapsedSeconds=proof['elapsedSeconds'],
        sourceIndexSha256=proof['sourceIndexSha256'],harnessIndexSha256=proof['harnessIndexSha256'],actualOrigins=proof['actualOrigins']['recordCount'],
        rawScratch=proof['rawScratch'],rawScratchFiles=proof['rawScratchFiles'],rawScratchBytes=proof['rawScratchBytes'],
        attemptFilesAcquired=proof['attemptFilesAcquired'],example=dict(headerBytes=len(header),inputDocuments=len(expected),inputBytes=total,
            retainedExampleFiles=len(rows),retainedExampleBytes=sum(map(len,rows.values())),bundleDigest=association['bundleDigest']))
    entries.append(entry)
    (folder/'README.md').write_text(f'''# {status.title()} pure148 attempt

[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).
148 methods in {proof['testSeconds']:.3f} test seconds; {proof['counts']['failures']} failures, zero errors.
Harness elapsed {proof['elapsedSeconds']:.3f}s, original 180s deadline. No SQL connection or device execution.
230 project files,233 frozen entries,6 active harness files and159 external pins remain unchanged;
{proof['actualOrigins']['recordCount']} origins match and255bytecode reads were refused.
Original raw scratch and its complete acquired copy retain {proof['rawScratchFiles']}files/{proof['rawScratchBytes']}bytes.

The [pre-run example](attempt/scratch/io-run-bundle-example/header.json) binds37documents/{total}bytes
under a {len(header)}byte header. Its [association record](attempt/scratch/io-run-bundle-example/association.json)
reports fresh reconstruction, with all attestation/storage/physical/qualification flags false.
The original trusted context is test metadata, not a deployed service configuration.
See the [test correction](../../CORRECTION.md) for the first attempt's wrong mock lookup.
''')
assert examples[0]==examples[1]
analysis=dict(scope='Bounded pre-run I/O carriers;148pure methods on source02. No supervisor launch or physical/public qualification.',
    distinctPassingMethods=148,newMethods=19,inheritedMethods=129,productionUnchangedBetweenVersions=True,
    completeExampleBytesEqualBetweenVersions=True,attempts=entries,qualificationPassed=False,supervisorIntegrated=False,
    configurationAttested=False,actualAggregateStorageEnforced=False,physicalMeasurementChecked=False)
write(B/'RESULTS.json',analysis)
ok=entries[1]
(R/'README.md').write_text(f'''# Bounded pre-run I/O bundle:148 pure checks pass

The [corrected source02](../implementation02/README.md) passes148methods in {ok['testSeconds']:.3f} test seconds
({ok['elapsedSeconds']:.3f}s harness elapsed):129unchanged pure checks and19new bundle checks.
GPIO and PWM setup reconstruct exactly. Missing/extra/reordered documents, changed content,
cross-run/configuration substitution, malformed numeric types and changed source identities refuse.
The parser's no-I/O/planner/SQL/clock guards pass. Fully rehashed false setup and changed original
authority demonstrate the separate structural and fresh-validation boundaries.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
| [source01](attempt01-failed148/README.md) |147pass; one test injection failure |{entries[0]['testSeconds']:.3f}|60 /508951|
| [source02](attempt02-passed148/README.md) |148pass |{ok['testSeconds']:.3f}|{ok['rawScratchFiles']} /{ok['rawScratchBytes']}|

The [correction](../CORRECTION.md) changes only a test's patch lookup and verifies its call.
All production bytes match between versions. Each retains a byte-identical40file pre-run example;
all230project inputs,233frozen entries,6harness inputs and159external pins are verified.
No SQL connections, runtime effects, devices, inference or live services ran. The original failed
attempt and both raw scratch roots remain. Review is by the primary agent only.

This [design](../DESIGN.md) is an input association component. Trusted fixed service configuration,
durable retention before release, owned child/run association, complete output collection,
hard aggregate storage and public qualification remain required. The broader prompt-to-PAT,
physical device/driver/hub and microscope objective remains active.
''')
(B/'README.md').write_text('# Pre-run I/O bundle\n\n[Design](DESIGN.md), [results](results/README.md), [test correction](CORRECTION.md).\nThe current additive source is [implementation02](implementation02/README.md).\n')
print(json.dumps(analysis))
