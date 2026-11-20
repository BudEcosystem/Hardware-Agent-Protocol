"""Audit completed pure controls, then freeze the unchanged full actual scope."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import stat
import statistics

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
STAGE=BASE/'implementation01';PURE=BASE/'harness01';ATTEMPT=PURE/'attempts/attempt01-pure63'
HARNESS=BASE/'harness02';TEMPLATE=ROOT/'artifacts/implementation/pat-vault-original-run/harness03'
PIN='a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path,row):assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):write(path,json.dumps(value,indent=2)+'\n')
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
assert sha(STAGE/'index.json')==PIN
assert sha(PURE/'index.json')=='dc350cdb4847178e203b307ac20b142a6a73e072f373a4f71316abe585b4feea'
for folder,prefix in ((STAGE,ROOT),(PURE,PURE)):
    for row in read(folder/'index.json')['files']:verify(prefix/row['path'],row)
result=read(ATTEMPT/'result.json')
assert result['status']=='passed' and result['currentPass'] and result['childState']=='exited' and result['exitCode']==0
assert result['counts']==dict(testsRun=63,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert result['errors']==result['childErrors']==[]
assert result['timeoutSeconds']==180 and result['limits']['scratchRetentionBytes']==16777216
for label,prefix in (('inputs',ATTEMPT/'project'),('frozen',ROOT),('harness',ATTEMPT/'harness')):
    rows=read(ATTEMPT/(label+'-before.json'));assert rows==read(ATTEMPT/(label+'-after.json'))
    for row in rows:verify(prefix/row['path'],row)
external=read(ATTEMPT/'external-before.json');assert external==read(ATTEMPT/'external-after.json')
for row in external['files']:verify(Path(row['resolvedPath']),row)
origins=read(ATTEMPT/'imports.json');assert origins['violations']==origins['prohibitedAttempts']==[]
for row in origins['records']:
    if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
assert read(ATTEMPT/'sqlite-connections.json')==[]
for label in ('compiler','driver'):assert read(ATTEMPT/(label+'-before.json'))==read(ATTEMPT/(label+'-after.json'))
targets=read(PURE/'targets.json')['targets'];assert len(targets)==63
assert read(ATTEMPT/'actual-tests.json')==dict(loaded=targets,executed=targets,exactSelection=True)
raw=Path(result['scratchPath']);identity=read(ATTEMPT/'raw-scratch-before.json')['identity'];info=raw.lstat()
assert stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))==tuple(identity[k] for k in ('device','inode','uid','mode'))
rows=inventory(raw);assert rows==inventory(ATTEMPT/'scratch')==read(ATTEMPT/'scratch-index.json')
assert sum(row['bytes'] for row in rows)==result['scratchRetainedBytes']<=16777216
counts=read(raw/'test_exact_build_with_one_validation_and_four_separate_proofs/validation-counts.json')
assert counts['reference']==[4,4,8,8,4] and counts['candidate']==[1,1,2,2,4] and counts['exactCanonicalOutputEqual']
timings=read(raw/'test_fixed_interleaved_build_measurements/build-timings.json');samples=timings['samples'];assert len(samples)==14
ratios=[]
for number in range(7):
    pair=samples[number*2:number*2+2]
    assert [row['implementation'] for row in pair]==(['reference','candidate'] if number%2==0 else ['candidate','reference'])
    assert all(row['round']==number and row['builds']==8 and row['cpuNanoseconds']>0 and row['wallNanoseconds']>0 for row in pair)
    pair={row['implementation']:row for row in pair};ratios.append(pair['candidate']['cpuNanoseconds']/pair['reference']['cpuNanoseconds'])
medians={name:statistics.median(row['cpuNanoseconds'] for row in samples if row['implementation']==name) for name in ('reference','candidate')}
assert medians==timings['medianCpuNanoseconds'] and medians['candidate']/medians['reference']==timings['candidateToReferenceMedianCpuRatio']
assert all(value<1 for value in ratios) and timings['candidateToReferenceMedianCpuRatio']<0.8
dump(BASE/'PURE-RESULTS.json',dict(status='verified-pure-controls',tests=63,sourceIndexSha256=PIN,
    harnessIndexSha256=sha(PURE/'index.json'),resultSha256=sha(ATTEMPT/'result.json'),
    rawPath=str(raw),rawFiles=len(rows),rawBytes=result['scratchRetainedBytes'],
    sourceAndOriginsAndRetainedBytesVerified=True,sqliteOpens=0,validationCounts=counts,
    timingObservations=timings,pairedCpuRatios=ratios,actualWorkerVerified=False,independentReview=False,goalStatus='active'))
assert not HARNESS.exists() and sha(TEMPLATE/'index.json')=='7e85f2300c1346c34caaa377416eae197fa88e4b3c6ad37e5e10928823eac532'
for row in read(TEMPLATE/'index.json')['files']:verify(TEMPLATE/row['path'],row)
borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
    path=TEMPLATE/name;copy='references/'+Path(name).name;write(HARNESS/copy,path.read_bytes())
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy=copy,bytes=path.stat().st_size,sha256=sha(path)))
    if not name.endswith('.py'):continue
    original=path.read_text();updated=original
    if name=='run_attempt.py':
        updated=updated.replace('4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4',PIN)
        updated=updated.replace('artifacts/implementation/pat-vault-original-run/implementation02/','artifacts/implementation/pat-io-proof-batch/implementation01/')
        assert updated.count("stage = here.parent / 'implementation02'")==1
        updated=updated.replace("stage = here.parent / 'implementation02'","stage = here.parent / 'implementation01'")
        updated=re.sub(r'\b286\b','288',updated);updated=re.sub(r'\b290\b','292',updated)
        updated=updated.replace("prefix='hms-vault-original-run-'","prefix='hms-io-proof-batch-actual-'")
    ast.parse(updated);write(HARNESS/name,updated)
    write(HARNESS/(name+'.patch'),''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='original-vault/'+name,tofile='proof-batch/'+name)))
dump(HARNESS/'borrowed-inputs.json',borrowed);write(HARNESS/'targets.json',(TEMPLATE/'targets.json').read_bytes())
write(HARNESS/'README.md','# Actual proof-build integration\n\n[Scope](SCOPE.md), [source](../implementation01/README.md), [pure controls](../PURE-RESULTS.json). Original failed attempts remain unchanged.\n')
write(HARNESS/'SCOPE.md','# Exact actual scope\n\nOne complete original 30-case worker through the actual execution service, authority-vault import, warm replay, configuration change and cold vault-only history. The fixture changes only the current source consumer pin. This does not reopen the entire source runtime/supervisor, test endpoint-session drift or invoke a source PAT.\n\nOriginal bounds remain: 60-second worker, 180-second parent, six parent SQLite opens, 16 MiB single-file, 256 MiB scratch, 8,192 files, 8 MiB log, five-second held vault snapshot and 15 MiB evidence vault. Exact declared vault file URI handling is unchanged. No physical device, MCU, model, network or live service runs. Original producer ownership/writer leases and exact raw/copied bytes remain required.\n')
dump(HARNESS/'review.json',dict(reviewer='primary-agent',independentReview=False,sourceIndexSha256=PIN,
    pureTestsPassed=63,originalCaseMatrixUnchanged=True,workerMaxWallMs=60000,parentMaxSeconds=180,
    sqliteConnectionsMaximum=6,scratchBytesMaximum=268435456,vaultBytesMaximum=15728640,
    heldSnapshotSecondsMaximum=5,childHarnessUnchanged=True,sourceApplicationInvocationsMaximum=0,
    timingQualified=False,actualScopeNotYetExecuted=True))
dump(HARNESS/'index.json',dict(scope='Fresh actual original worker and authority-vault import under unchanged bounds',files=inventory(HARNESS)))
print(json.dumps(dict(pureTests=63,candidateToReferenceMedianCpuRatio=timings['candidateToReferenceMedianCpuRatio'],pairedCpuRatios=ratios,harnessIndexSha256=sha(HARNESS/'index.json'))))
