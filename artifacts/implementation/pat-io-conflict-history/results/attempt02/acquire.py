"""Acquire terminal conflict48 evidence; stdlib data inspection only."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-conflict-history'
SOURCE=BASE/'harness02/attempts/attempt02-conflict48'; OUT=BASE/'results/attempt02'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def inventory(folder):
    rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_dir(): continue
        assert stat.S_ISREG(p.stat().st_mode)
        rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
def identity(p):
    s=p.lstat(); assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
def records(folder,refs,profile):
    assert 1<=len(refs)<=4096
    assert {p.name for p in folder.iterdir()}=={r['path'] for r in refs}
    docs={}
    for number,row in enumerate(refs):
        assert row['path']=='%06d.json'%number and row['bytes']<=65536
        verify(folder/row['path'],row); doc=read(folder/row['path'])
        assert set(doc)=={'profile','kind','value'} and doc['profile']==profile
        docs[row['path']]=doc
    return docs
def tables(docs,cp):
    count=0
    for table in cp['tables']:
        found=0
        for ref in table['pages']:
            page=docs[ref['path']]['value']
            assert page['table']==table['table'] and page['first']==found and page['totalRows']==table['rowCount']
            assert 0<=len(page['rows'])<=8
            found+=len(page['rows']); count+=1
        assert found==table['rowCount']
    return count

seals=[]
for folder,pin,rooted in [
    (BASE/'implementation01','eccd20743c61cb37d73c3f2f0df770d4c0b7529132287426eac7b8921875c524',True),
    (BASE/'harness02','4b717fa60a5a9592de1ee6e952c4ffb8c38c34e5579ff881d0e74d93b74cfc1a',False),
    (ROOT/'artifacts/implementation/pat-io-combined-matrix/implementation01','0a34336874ffe2c3d65301e40adf2b7a9328ddb08a074e02e4e777b9528bf78a',True)]:
    assert sha(folder/'index.json')==pin; indexed=read(folder/'index.json')['files']
    for row in indexed: verify((ROOT if rooted else folder)/row['path'],row)
    seals.append(dict(index=(folder/'index.json').relative_to(ROOT).as_posix(),sha256=pin,filesVerified=len(indexed)))
result=read(SOURCE/'result.json')
assert result['childState']=='exited' and not Path('/proc/'+str(result['pid'])).exists()
assert result['timeoutSeconds']==180 and result['status'] in {'passed','failed'} and result['counts']['testsRun']==48
for prefix,root,count in [('inputs',SOURCE/'project',7067),('frozen',ROOT,7070),('harness',SOURCE/'harness',6)]:
    rows=read(SOURCE/(prefix+'-before.json')); assert rows==read(SOURCE/(prefix+'-after.json')) and len(rows)==count
    for row in rows: verify(root/row['path'],row)
external=read(SOURCE/'external-before.json'); assert external==read(SOURCE/'external-after.json') and len(external['files'])==159
for row in external['files']: verify(Path(row['resolvedPath']),row)
assert sha(SOURCE/'harness/targets.json')=='083ba21385798a11695c84f9a9f34258ec54b045fc7806438ffd0536b5879cb0'
targets=read(SOURCE/'harness/targets.json')['targets']; actual=read(SOURCE/'actual-tests.json')
assert actual['loaded']==actual['executed']==targets and len(set(targets))==48
origins=read(SOURCE/'imports.json')
assert origins['violations']==origins['prohibitedAttempts']==[] and origins['summary']['allOriginsMatched']
for row in origins['records']:
    if 'sha256' in row: assert sha(Path(row['origin']))==row['sha256']
for name in ['compiler','driver']: assert read(SOURCE/(name+'-before.json'))==read(SOURCE/(name+'-after.json'))
log=(SOURCE/'output.log').read_text(); match=re.search(r'Ran 48 tests in ([0-9.]+)s',log); assert match
passed=result['status']=='passed'
if passed:
    assert result['currentPass'] and result['exitCode']==0 and result['errors']==result['childErrors']==[]
    assert result['counts']==dict(testsRun=48,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert log.endswith('\nOK\n')
    assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')]==targets
raw=Path(result['scratchPath']); before=read(SOURCE/'raw-scratch-before.json')
assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
raw_rows=inventory(raw)
assert len(raw_rows)<=8192
assert passed and sum(r['bytes'] for r in raw_rows)<=16*1024*1024
assert raw_rows==inventory(SOURCE/'scratch')==read(SOURCE/'scratch-index.json')
runtime=[t for t in targets if not t.startswith('test_pat_io_transcript.')]
assert len(runtime)==9
expected_connections=set(); summaries=[]
for test in runtime:
    method=test.split('.')[-1]; retained=SOURCE/'scratch'/method; manifest=read(retained/'engine-0.json')
    original=raw/method/'trial-0'; trial=retained/'trial-0'
    assert manifest['testId']==test and manifest['directory']==str(original) and manifest['closed'] and not manifest['cleanupErrors']
    new=test.startswith('test_pat_io_conflict_history.')
    docs=records(trial/'records',manifest['records'],'hms.pat.io-trial-record/0.'+('2' if new else '1'))
    config=manifest['configuration']; cd=records(trial/'configuration',config['records'],'hms.pat.io-configuration-record/0.1')
    assert config['combinedRecords']==len(docs)+len(cd)<=4096
    assert config['configurationBytes']==sum(r['bytes'] for r in config['records'])
    assert config['combinedBytes']==sum(r['bytes'] for r in manifest['records']+config['records'])<=16*1024*1024
    cps=[r for r in manifest['records'] if docs[r['path']]['kind']=='checkpoint']
    assert [p['checkpoint'] for p in config['snapshots']]==cps
    page_refs=0
    for pair in config['snapshots']:
        cp=docs[pair['checkpoint']['path']]['value']; side=cd[pair['configuration']['path']]['value']
        assert side['checkpoint']==pair['checkpoint']
        assert all(side[k]==cp[k] for k in ('phase','label','wallMs','monotonicMs','clockEpoch'))
        assert len(cp['tables'])==29 and len(side['tables'])==15
        page_refs+=tables(docs,cp)+tables(cd,side)
    databases=sorted((trial/'state').glob('*.db')); assert len(databases)==2
    expected_connections.update((test,str(original/'state'/db.name)) for db in databases)
    inspections=manifest.get('independentConflictInspection')
    if passed and new:
        assert inspections['sameKeyConflictChecked'] and inspections['exactReplayChecked'] and not inspections['qualificationPassed']
        assert len(inspections['conflictsChecked'])==1 and inspections['replaysChecked']
        inputs=[d['value'] for d in docs.values() if d['kind']=='conflict_input']; assert len(inputs)==1
        original_request=next(d['value']['request'] for d in docs.values() if d['kind']=='compiled_plan')
        conflicting=inputs[0]['request']
        assert original_request['replayNamespace']==conflicting['replayNamespace'] and original_request['procedureKey']==conflicting['procedureKey']
        assert [s['request']['operationKey'] for s in original_request['procedure']['steps']]==[s['request']['operationKey'] for s in conflicting['procedure']['steps']]
        assert original_request!=conflicting
    summaries.append(dict(testId=test,executionRecords=len(docs),configurationRecords=len(cd),checkpoints=len(cps),tablePageReferences=page_refs,
        profile='0.2' if new else '0.1',independentConflictChecked=bool(inspections),report=manifest['report']))
actual_connections={(row['testId'],row['database']) for row in read(SOURCE/'sqlite-connections.json')}
assert actual_connections==expected_connections and len(actual_connections)==18
if passed and True:
    attacks=read(SOURCE/'scratch/test_conflict_gpio_completed_rejects_rehashed_false_claims/engine-0.json')
    assert attacks['rehashedRefusals']==15 and attacks['privateGuardChecks']==2 and attacks['purityChecked']
rows=inventory(SOURCE); shutil.copytree(SOURCE,OUT/'attempt'); assert inventory(OUT/'attempt')==rows==inventory(SOURCE)
proof=dict(scope='48 selected tests:39 inherited pure transcript methods and nine new conflict/replay captures.',
    status=result['status'],currentPass=result['currentPass'],counts=result['counts'],testSeconds=float(match.group(1)),elapsedSeconds=result['elapsedSeconds'],
    preparationSeals=seals,projectFilesVerified=7067,frozenFilesVerified=7070,activeHarnessFilesVerified=6,externalFilesVerified=159,
    originSummary=origins['summary'],actualOriginFileHashesRechecked=True,bytecodeReadsRefused=len(origins['deniedBytecodeReads']),
    compilerAndDriverStable=True,methodOrderVerified=True,attemptFilesAcquired=len(rows),rawScratch=before['identity'],rawScratchOriginalRetained=True,
    rawScratchFiles=len(raw_rows),rawScratchBytes=sum(r['bytes'] for r in raw_rows),runtimeCases=summaries,exactDatabasePathsChecked=18,
    rawScratchCopied=True,rawScratchHashInventoryRetained=True,retentionLimitExceeded=False,
    independentReview=False,configurationAttested=False,compilerIdentityAttested=False,physicalMeasurementChecked=False,
    requiredOutcomesVerified=False,actualAggregateStorageEnforced=False,qualificationPassed=False,
    limitations=['This is one versioned worker/checker extension, not the complete candidate fault/resource matrix.',
        'The v0.2 checker retains read authority; auxiliary actors, in-phase delay, clock faults, full-read withdrawal and binding changes remain separate work.',
        'No current-source attestation, aggregate worker quotas, physical execution, public qualification service or PAT promotion.'])
with (OUT/'proof.json').open('x') as stream: stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],counts=result['counts'],acquiredFiles=len(rows),rawScratchFiles=len(raw_rows),rawScratchBytes=proof['rawScratchBytes'])))
