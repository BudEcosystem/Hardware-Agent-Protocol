"""Verify every scope, immutable input and retained fixture without repairs."""
import hashlib
import json
from pathlib import Path
import sqlite3
import stat

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-content-store'
PIN='f19f9d9fa10ea0a62347a811a1a8e0a78de45954a759916042225125cbabd95f'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def verify(path,row):assert path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
assert sha(BASE/'implementation01/index.json')==PIN
for row in read(BASE/'implementation01/index.json')['files']:verify(ROOT/row['path'],row)
baseline=read(BASE/'implementation01/baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==261
for row in baseline:
    source=ROOT/row['path'];relative=source.relative_to(ROOT/'artifacts/implementation/pat-io-bound-import/implementation01/project')
    verify(source,row);verify(BASE/'implementation01/project'/relative,row)
attempts=[];databases=[]
for n in range(1,20):
    harness=BASE/('harness%02d'%n);attempt=harness/'attempts'/('attempt01-compact-real' if n==2 else 'attempt01')
    review=read(harness/'review.json');assert review['sourceIndexSha256']==PIN
    for row in read(harness/'index.json')['files']:verify(harness/row['path'],row)
    result=read(attempt/'result.json');targets=read(harness/'targets.json')['targets']
    assert result['status']=='passed' and result['currentPass'] and result['childState']=='exited' and result['exitCode']==0
    assert result['counts']==dict(testsRun=1,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert result['actualTests']==dict(loaded=targets,executed=targets,exactSelection=True)
    assert result['errors']==result['childErrors']==[] and result['originSummary']['allOriginsMatched']
    assert result['timeoutSeconds']==180 and result['limits']['singleAcquiredFileBytes']==16*1024*1024
    for label,folder in [('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')]:
        rows=read(attempt/(label+'-before.json'));assert rows==read(attempt/(label+'-after.json'))
        for row in rows:verify(folder/row['path'],row)
    assert read(attempt/'external-before.json')==read(attempt/'external-after.json')
    for row in read(attempt/'external-before.json')['files']:verify(Path(row['resolvedPath']),row)
    for label in ('compiler','driver'):assert read(attempt/(label+'-before.json'))==read(attempt/(label+'-after.json'))
    origins=read(attempt/'imports.json');assert origins['violations']==origins['prohibitedAttempts']==[]
    for row in origins['records']:
        if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
    scratch=Path(result['scratchPath']);saved=read(attempt/'raw-scratch-before.json')['identity'];info=scratch.lstat()
    assert stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))==(saved['device'],saved['inode'],saved['uid'],saved['mode'])
    rows=inventory(scratch);assert rows==inventory(attempt/'scratch')==read(attempt/'scratch-index.json')
    assert sum(row['bytes'] for row in rows)==result['scratchRetainedBytes']<=review['scratchBytesCeiling']
    assert all(row['bytes']<=16*1024*1024 for row in rows)
    sql=read(attempt/'sqlite-connections.json');assert len(sql)==review['sqliteConnectionsMaximum']
    seen=set()
    for entry in sql:
        original=Path(entry['database']);relative=original.relative_to(scratch);copied=attempt/'scratch'/relative
        if str(relative) in seen:continue
        seen.add(str(relative));before=sha(original);assert sha(copied)==before
        db=sqlite3.connect(copied.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            audit=dict(harness=n,database=relative.as_posix(),sha256=before)
            if 'ioec_runs' in tables:
                audit['imports']=db.execute('SELECT count(*) FROM ioec_runs').fetchone()[0]
                audit['references']=db.execute('SELECT count(*) FROM ioec_documents').fetchone()[0]
                audit['bodyTablePresent']='ioec_bodies' in tables
                if audit['bodyTablePresent']:
                    audit['bodies']=db.execute('SELECT count(*) FROM ioec_bodies').fetchone()[0]
                    if n!=2:
                        for (body,) in db.execute("SELECT b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest WHERE d.path='original/output/result.json'"):
                            assert json.loads(body)==dict(fixture=True,workerExecuted=False,semanticsVerified=False)
                        audit['originalOutputsExplicitFixtures']=True
            databases.append(audit)
        finally:db.close()
        assert sha(original)==before==sha(copied)
    attempts.append(dict(harness=harness.name,attempt=attempt.relative_to(BASE).as_posix(),status=result['status'],
        counts=result['counts'],targets=targets,elapsedSeconds=result['elapsedSeconds'],
        rawFiles=len(rows),rawBytes=result['scratchRetainedBytes'],harnessIndexSha256=sha(harness/'index.json')))
actual=read(BASE/'actual-import-audit.json')
assert actual['actualScopePassed'] and actual['allOriginalAndStoredBytesMatched'] and actual['sourceIdentitiesIndependentlyRecomputed']
assert actual['authorityDatabaseBytes']==16132096 and actual['referenceCount']==4011 and actual['uniqueBodies']==2798
assert actual['headroomBytes']==645120 and not actual['physicalObjectiveVerified'] and not actual['freshEligibilityClaimed']
prior=ROOT/'artifacts/implementation/pat-io-bound-import'
assert sha(prior/'index.json')=='c80f00a04dbaf7a3c2775ffa3c58a74ebf8a639abaa5a70ea69f5c04e0f61e06'
manifest=read(prior/'forensic01/raw-manifest.json');old=next(row for row in manifest['files'] if row['path'].endswith('/runtime/authority.db'))
verify(Path(manifest['originalScratch']['path'])/old['path'],old)
assert old['bytes']==17591296
write(BASE/'RESULTS.json',dict(goalStatus='active',attemptedScopes=19,passingScopes=19,failingScopes=0,
    newFixtureControlsPassed=18,actualIntegrationScopePassed=True,completeMethodReceipts=19,
    realWorkerCases=30,referenceCount=4011,uniqueBodies=2798,expandedBytes=actual['expandedBytes'],
    uniqueBodyBytes=actual['uniqueBodyBytes'],authorityDatabaseBytes=16132096,originalSingleFileLimit=16*1024*1024,
    headroomBytes=645120,observedReductionFromPriorBytes=17591296-16132096,
    sourceIndexSha256=PIN,unchangedInheritedProjectFiles=261,newProductionFiles=3,
    legacyIdentityUnchanged=True,producerImageFiles=262,compactStoreImplemented=True,
    actualAudit='actual-import-audit.json',attempts=attempts,databaseAudits=databases,
    allOriginalAndCopiedDatabasesUnchanged=True,historicalFailuresPreserved=True,
    publicCatalogMounted=False,freshEligibilityClaimed=False,physicalObjectiveVerified=False,
    generalCapacityOrTimingGuarantee=False,independentReview=False))
print(json.dumps(dict(passingScopes=19,fixtureControls=18,actualIntegrationPassed=True,
    authorityDatabaseBytes=16132096,headroomBytes=645120,databases=len(databases),goalStatus='active')))
