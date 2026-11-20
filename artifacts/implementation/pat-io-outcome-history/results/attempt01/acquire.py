"""Retain the actual terminal outcome24 attempt without importing project code."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-outcome-history'
SOURCE=BASE/'harness01/attempts/attempt01-outcome24'; OUT=BASE/'results/attempt01'
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,r):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'], str(p)
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
    (BASE/'implementation01','4e297e540c22035bd65a1b7bc1312478e0843b00a4b0f25ba0bfd683c82da2ee',True),
    (BASE/'harness01','20fa738a1627d0dd7a5b2cb7524959275c1a819fe74b8b88bf4faed94db11cfa',False),
    (ROOT/'artifacts/implementation/pat-io-refusal-history/implementation01','43834d85b3843409f0402663331dd636339f224aabdf1047c655d512eef65ac1',True),
]:
    assert sha(folder/'index.json')==pin; rows=read(folder/'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder)/row['path'],row)
    seals.append(dict(index=(folder/'index.json').relative_to(ROOT).as_posix(),sha256=pin,filesVerified=len(rows)))
old=ROOT/'artifacts/implementation/pat-io-refusal-history/implementation01/project'
baseline=read(BASE/'implementation01/baseline-inputs.json')
assert len(baseline['inheritedProjectInputs'])==7060
for row in baseline['inheritedProjectInputs']: verify(BASE/'implementation01/project'/(ROOT/row['path']).relative_to(old),row)
result=read(SOURCE/'result.json')
assert result['childState']=='exited' and not Path('/proc/'+str(result['pid'])).exists()
assert result['timeoutSeconds']==180 and result['status'] in {'passed','failed'}
assert result['counts']['testsRun']==24
for prefix,root,count in [('inputs',SOURCE/'project',7062),('frozen',ROOT,7065),('harness',SOURCE/'harness',6)]:
    rows=read(SOURCE/(prefix+'-before.json'))
    assert rows==read(SOURCE/(prefix+'-after.json')) and len(rows)==count
    for row in rows: verify(root/row['path'],row)
external=read(SOURCE/'external-before.json')
assert external==read(SOURCE/'external-after.json') and len(external['files'])==159
for row in external['files']: verify(Path(row['resolvedPath']),row)
assert sha(SOURCE/'harness/targets.json')=='fcf05b04971dc40645a5581ec88fae48e4cc69dc80ed4816101a4a6bc341d1af'
targets=read(SOURCE/'harness/targets.json')['targets']; actual=read(SOURCE/'actual-tests.json')
assert actual['loaded']==actual['executed']==targets and len(set(targets))==24
origins=read(SOURCE/'imports.json')
assert origins['violations']==origins['prohibitedAttempts']==[] and origins['summary']['allOriginsMatched']
for row in origins['records']:
    if 'sha256' in row: assert sha(Path(row['origin']))==row['sha256']
for name in ['compiler','driver']: assert read(SOURCE/(name+'-before.json'))==read(SOURCE/(name+'-after.json'))
log=(SOURCE/'output.log').read_text(); match=re.search(r'Ran 24 tests in ([0-9.]+)s',log); assert match
if result['status']=='passed':
    assert result['currentPass'] and result['exitCode']==0 and result['errors']==result['childErrors']==[]
    assert result['counts']==dict(testsRun=24,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert log.endswith('\nOK\n')
raw=Path(result['scratchPath']); before=read(SOURCE/'raw-scratch-before.json')
assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
assert inventory(raw)==inventory(SOURCE/'scratch')==read(SOURCE/'scratch-index.json')==[]
rows=inventory(SOURCE); shutil.copytree(SOURCE,OUT/'attempt')
assert inventory(OUT/'attempt')==rows==inventory(SOURCE)

fixtures=[]
for group,path,pin,expected in [
    ('io-configuration','pat-io-configuration-capture/results/attempt01-passed32','ee98257543d28db76e77eed56f1b31f3a0934071e96492b3485551279fa6b122',(12,1721,504,206)),
    ('io-active','pat-io-active-revocation/results/attempt01-passed38','a324f88d1425148f3913b0dc3ba3a19b6f99c55b53678e6a6edf68d5d1b1bbc3',(6,608,235,92)),
    ('io-recovery','pat-io-pending-recovery/results/attempt01-passed46','64f228609eb271c346ba18c4e4874e2417e032b9e30bf83e6498231cd738818b',(8,823,318,136)),
]:
    prior=ROOT/'artifacts/implementation'/path; assert sha(prior/'index.json')==pin
    indexed={r['path']:r for r in read(prior/'index.json')['files']}
    folder=SOURCE/'project/tests/data'/group; catalog=read(folder/'index.json')
    execution=configuration=snapshots=files=0
    for fixture in catalog['fixtures']:
        original=prior/'attempt/scratch'/fixture['method']; copied=folder/fixture['method']; manifest=read(copied/'manifest.json')
        p=original/'engine-0.json'; verify(p,indexed[p.relative_to(prior).as_posix()]); assert sha(p)==sha(copied/'manifest.json'); files+=1
        for directory,refs in [('records',manifest['records']),('configuration',manifest['configuration']['records'])]:
            for row in refs:
                p=original/'trial-0'/directory/row['path']; verify(p,indexed[p.relative_to(prior).as_posix()]); verify(p,row); verify(copied/directory/row['path'],row); files+=1
        execution+=len(manifest['records']); configuration+=len(manifest['configuration']['records']); snapshots+=len(manifest['configuration']['snapshots'])
    assert (len(catalog['fixtures']),execution,configuration,snapshots)==expected
    fixtures.append(dict(group=group,sourceIndexSha256=pin,fixtures=expected[0],executionRecords=execution,configurationRecords=configuration,snapshots=snapshots,exactFilesReverified=files))
proof=dict(scope='Actual outcome24 invocation; no new inherited128/full136/full748 regression or full qualification claim.',
    status=result['status'],currentPass=result['currentPass'],counts=result['counts'],testSeconds=float(match.group(1)),elapsedSeconds=result['elapsedSeconds'],
    preparationSeals=seals,inheritedInputsUnchanged=7060,projectFilesVerified=7062,frozenFilesVerified=7065,activeHarnessFilesVerified=6,externalFilesVerified=159,
    originSummary=origins['summary'],actualOriginFileHashesRechecked=True,bytecodeReadsRefused=len(origins['deniedBytecodeReads']),
    compilerAndDriverStable=True,methodOrderVerified=True,attemptFilesAcquired=len(rows),rawScratch=before['identity'],rawScratchEmpty=True,rawScratchOriginalRetained=True,
    fixtureProvenance=fixtures,independentReview=False,configurationAttested=False,compilerIdentityAttested=False,physicalMeasurementChecked=False,
    requiredMatrixCoverageChecked=False,allFaultScenariosChecked=False,qualificationPassed=False,
    limitations=['This evaluates one retained trial and whole-domain static compatibility, not a required-case group or an automatically promoted PAT.',
        'Existing ordinary/denial/recovery captures do not cover all delayed-reporting, clock-loss and auxiliary-actor cases.',
        'No Runtime, SQL connection, physical device, MCU/emulator, inference, public service or live source change.'])
with (OUT/'proof.json').open('x') as stream: stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],counts=result['counts'],acquiredFiles=len(rows),fixtureFiles=sum(r['exactFilesReverified'] for r in fixtures))))
