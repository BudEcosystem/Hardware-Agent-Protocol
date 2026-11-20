"""Retain the actual terminal matrix61 attempt using only standard-library data operations."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-combined-matrix'
SOURCE=BASE/'harness01/attempts/attempt01-matrix61'; OUT=BASE/'results/attempt01'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'], str(p)
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

seals=[]
for folder,pin,rooted in [
    (BASE/'implementation01','0a34336874ffe2c3d65301e40adf2b7a9328ddb08a074e02e4e777b9528bf78a',True),
    (BASE/'harness01','987740d8376199a0ac2623cfa5f107e3985220b3a439a5f831cfa14d06cc112e',False),
    (ROOT/'artifacts/implementation/pat-io-outcome-history/implementation01','4e297e540c22035bd65a1b7bc1312478e0843b00a4b0f25ba0bfd683c82da2ee',True),
]:
    assert sha(folder/'index.json')==pin; indexed=read(folder/'index.json')['files']
    for row in indexed: verify((ROOT if rooted else folder)/row['path'],row)
    seals.append(dict(index=(folder/'index.json').relative_to(ROOT).as_posix(),sha256=pin,filesVerified=len(indexed)))
baseline=read(BASE/'implementation01/baseline-inputs.json'); old=ROOT/'artifacts/implementation/pat-io-outcome-history/implementation01/project'
assert len(baseline['inheritedProjectInputs'])==7062
for row in baseline['inheritedProjectInputs']: verify(BASE/'implementation01/project'/(ROOT/row['path']).relative_to(old),row)
result=read(SOURCE/'result.json')
assert result['childState']=='exited' and not Path('/proc/'+str(result['pid'])).exists()
assert result['timeoutSeconds']==180 and result['status'] in {'passed','failed'} and result['counts']['testsRun']==61
for prefix,root,count in [('inputs',SOURCE/'project',7064),('frozen',ROOT,7067),('harness',SOURCE/'harness',6)]:
    rows=read(SOURCE/(prefix+'-before.json')); assert rows==read(SOURCE/(prefix+'-after.json')) and len(rows)==count
    for row in rows: verify(root/row['path'],row)
external=read(SOURCE/'external-before.json'); assert external==read(SOURCE/'external-after.json') and len(external['files'])==159
for row in external['files']: verify(Path(row['resolvedPath']),row)
assert sha(SOURCE/'harness/targets.json')=='fa2729900d442787dde2e4747419132cd1e1b3ee019d8b30f51a9a1232f56979'
targets=read(SOURCE/'harness/targets.json')['targets']; actual=read(SOURCE/'actual-tests.json')
assert actual['loaded']==actual['executed']==targets and len(set(targets))==61
assert sum(name.startswith('test_pat_io_contracts.IoContractTests.') for name in targets)==31
assert sum(name.startswith('test_pat_io_combined_matrix.IoCombinedMatrixTests.') for name in targets)==30
origins=read(SOURCE/'imports.json')
assert origins['violations']==origins['prohibitedAttempts']==[] and origins['summary']['allOriginsMatched']
for row in origins['records']:
    if 'sha256' in row: assert sha(Path(row['origin']))==row['sha256']
for name in ['compiler','driver']: assert read(SOURCE/(name+'-before.json'))==read(SOURCE/(name+'-after.json'))
log=(SOURCE/'output.log').read_text(); match=re.search(r'Ran 61 tests in ([0-9.]+)s',log); assert match
if result['status']=='passed':
    assert result['currentPass'] and result['exitCode']==0 and result['errors']==result['childErrors']==[]
    assert result['counts']==dict(testsRun=61,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert log.endswith('\nOK\n')
    assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')]==targets
raw=Path(result['scratchPath']); before=read(SOURCE/'raw-scratch-before.json')
assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
assert inventory(raw)==inventory(SOURCE/'scratch')==read(SOURCE/'scratch-index.json')==[]
rows=inventory(SOURCE); shutil.copytree(SOURCE,OUT/'attempt'); assert inventory(OUT/'attempt')==rows==inventory(SOURCE)
proof=dict(scope='Actual61 pure planning tests:31 inherited domain/timing and30 new combined-matrix methods. No listed qualification challenge executed.',
    status=result['status'],currentPass=result['currentPass'],counts=result['counts'],testSeconds=float(match.group(1)),elapsedSeconds=result['elapsedSeconds'],
    preparationSeals=seals,inheritedInputsUnchanged=7062,projectFilesVerified=7064,frozenFilesVerified=7067,
    activeHarnessFilesVerified=6,externalFilesVerified=159,originSummary=origins['summary'],actualOriginFileHashesRechecked=True,
    bytecodeReadsRefused=len(origins['deniedBytecodeReads']),compilerAndDriverStable=True,methodOrderVerified=True,
    attemptFilesAcquired=len(rows),rawScratch=before['identity'],rawScratchEmpty=True,rawScratchOriginalRetained=True,
    independentReview=False,configurationAttested=False,compilerIdentityAttested=False,physicalMeasurementChecked=False,
    requiredOutcomesVerified=False,actualAggregateStorageEnforced=False,qualificationPassed=False,
    limitations=['The plan is complete for its declared fixed challenge set; an extended worker/reducer still must execute and verify those exact cases.',
        'Original bounds are unchanged. The ordinary duration-parameter example is refused because37 combined cases exceed32.',
        'Static case/operation/tick accounting does not prove actual evidence bytes, wall time or hard aggregate storage will fit.',
        'No Runtime, SQL connection, physical device, MCU/emulator, inference, public service or live source change.'])
with (OUT/'proof.json').open('x') as stream: stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],counts=result['counts'],acquiredFiles=len(rows))))
