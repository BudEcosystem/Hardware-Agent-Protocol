"""Verify immutable sources, original attempt receipts and forensic retention."""
import hashlib
import json
from pathlib import Path
import sqlite3
import stat

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-bound-import'
PIN='f65744faaea97e566549904d05a7115d30b2b08760d679b77f0808d484073c8d'
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
for row in read(BASE/'implementation01/baseline-inputs.json')['inheritedProjectInputs']:
    previous=ROOT/row['path'];relative=previous.relative_to(ROOT/'artifacts/implementation/pat-io-evidence-import/implementation01/project')
    verify(previous,row);verify(BASE/'implementation01/project'/relative,row)
preparation=read(BASE/'harness01/attempts/attempt01-real-import/result.json')
assert preparation['status']=='failed' and preparation['childState']=='not_started' and preparation.get('pid') is None and preparation['counts'] is None
assert not read(BASE/'preparation-failure.json')['workerLaunched']
results=[];databases=[]
for n in range(2,8):
    harness=BASE/('harness%02d'%n);attempt=harness/'attempts'/('attempt01-real-import' if n==2 else 'attempt01')
    review=read(harness/'review.json');assert review['sourceIndexSha256']==PIN
    for row in read(harness/'index.json')['files']:verify(harness/row['path'],row)
    result=read(attempt/'result.json');targets=read(harness/'targets.json')['targets']
    assert result['childState']=='exited' and result['exitCode']==0
    assert result['counts']==dict(testsRun=1,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert result['actualTests']==dict(loaded=targets,executed=targets,exactSelection=True)
    assert result['childErrors']==[] and result['originSummary']['allOriginsMatched']
    if n==2:
        assert result['status']=='failed' and not result['currentPass'] and len(result['errors'])==1
        assert result['errors'][0]['phase']=='scratch-retention'
    else:assert result['status']=='passed' and result['currentPass'] and result['errors']==[]
    for label,folder in [('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')]:
        rows=read(attempt/(label+'-before.json'));assert rows==read(attempt/(label+'-after.json'))
        for row in rows:verify(folder/row['path'],row)
    assert read(attempt/'external-before.json')==read(attempt/'external-after.json')
    for row in read(attempt/'external-before.json')['files']:verify(Path(row['resolvedPath']),row)
    for label in ('compiler','driver'):assert read(attempt/(label+'-before.json'))==read(attempt/(label+'-after.json'))
    origins=read(attempt/'imports.json');assert origins['violations']==origins['prohibitedAttempts']==[]
    for row in origins['records']:
        if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
    sql=read(attempt/'sqlite-connections.json');assert len(sql)==review['sqliteConnectionsMaximum']
    if n!=2:
        scratch=Path(result['scratchPath']);before=read(attempt/'raw-scratch-before.json')['identity'];info=scratch.lstat()
        assert stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino,info.st_uid)==(before['device'],before['inode'],before['uid'])
        rows=inventory(scratch);assert rows==inventory(attempt/'scratch')==read(attempt/'scratch-index.json')
        assert sum(row['bytes'] for row in rows)==result['scratchRetainedBytes']<=16*1024*1024
        for item in sql:
            original=Path(item['database']);copied=attempt/'scratch'/original.relative_to(scratch)
            before_hash=sha(original);assert sha(copied)==before_hash
            db=sqlite3.connect(copied.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
            try:
                tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                audit=dict(harness=n,database=original.relative_to(scratch).as_posix(),sha256=before_hash)
                if 'ioei_runs' in tables:
                    audit['imports']=db.execute('SELECT count(*) FROM ioei_runs').fetchone()[0]
                    audit['documents']=db.execute('SELECT count(*) FROM ioei_documents').fetchone()[0]
                    for (body,) in db.execute("SELECT body FROM ioei_documents WHERE path='original/output/result.json'"):
                        assert json.loads(body)==dict(fixture=True,workerExecuted=False,semanticsVerified=False)
                databases.append(audit)
            finally:db.close()
            assert sha(original)==before_hash==sha(copied)
    results.append(dict(harness=harness.name,attempt=attempt.relative_to(BASE).as_posix(),status=result['status'],
        currentPass=result['currentPass'],counts=result['counts'],targets=targets,errors=result['errors'],
        elapsedSeconds=result['elapsedSeconds'],harnessIndexSha256=sha(harness/'index.json')))
forensic=read(BASE/'forensic01/audit.json');assert forensic['failurePreserved'] and forensic['allOriginalBytesUnchanged']
assert forensic['allStoredEvidenceBodiesMatched'] and forensic['allOriginalProducerOutputsMatched']
assert forensic['completeMatrixCases']==30 and forensic['realOriginalAuthorityHandoffAttemptJoined']
manifest=read(BASE/'forensic01/raw-manifest.json');raw=Path(manifest['originalScratch']['path'])
assert len(manifest['files'])==4255 and manifest['totalBytes']==36807069
for row in manifest['files']:
    verify(raw/row['path'],row)
    if 'copy' in row:verify(BASE/'forensic01'/row['copy'],row)
    else:
        combined=hashlib.sha256();offset=0
        for chunk in row['chunks']:
            assert chunk['offset']==offset and chunk['bytes']<=8*1024*1024
            path=BASE/'forensic01'/chunk['path'];verify(path,chunk);combined.update(path.read_bytes());offset+=chunk['bytes']
        assert combined.hexdigest()==row['sha256'] and offset==row['bytes']
        assert row['originalSingleFileLimitExceeded'] and row['bytes']==17591296
# Verify the actual copied producer image against selected immutable origins.
work=raw/'test_real_bound_worker_import_and_historical_replay';record=read(work/'worker-archive.json')['record']
actual=BASE/'harness02/attempts/attempt01-real-import';request=read(work/'supervisor'/record['attemptId']/'input.json')['request']
image=work/'supervisor'/('code-'+request['supervisorIdentity'][7:]);files=[path for path in image.rglob('*') if path.is_file()]
assert len(files)==262
external=read(actual/'external-before.json')['files']
for path in files:
    relative=path.relative_to(image).as_posix()
    if relative.startswith('dependencies/'):
        tail='/'+relative[len('dependencies/'):]
        candidates=[row for row in external if row['resolvedPath'].endswith(tail)];assert len(candidates)==1
        assert sha(path)==candidates[0]['sha256']
    else:assert sha(path)==sha(actual/'project'/relative)
sizing=read(BASE/'deduplication-sizing.json')
assert sizing['allReconstructedRowsByteIdentical'] and not sizing['implementedStore'] and sizing['estimatedHeadroomBytes']==649216
write(BASE/'RESULTS.json',dict(goalStatus='active',preparationFailures=1,executedScopes=6,passingScopes=5,
    failingExecutedScopes=1,completeMethodReceipts=6,methodReceiptsReportedPassing=6,newFixtureControlsPassed=5,
    realWorkerCases=30,realOriginalBoundImportVerified=True,historicalReplayAfterDriftVerified=True,
    actualIntegrationScopePassed=False,retentionFailurePreserved=True,originalAuthorityDatabaseBytes=17591296,
    originalSingleFileLimit=16*1024*1024,excessBytes=814080,producerImageFiles=262,
    sourceIndexSha256=PIN,unchangedInheritedProjectFiles=259,newProductionFiles=0,
    attempts=results,fixtureDatabaseAudits=databases,forensicAudit='forensic01/audit.json',
    forensicManifest='forensic01/raw-manifest.json',storageSizing='deduplication-sizing.json',
    compactStoreImplemented=False,publicCatalogMounted=False,physicalObjectiveVerified=False,
    independentReview=False,historicalFailuresPreserved=True))
print(json.dumps(dict(executedScopes=6,passingScopes=5,retentionFailure=1,methodReceiptsReportedPassing=6,
    actualBoundImportVerified=True,compactStoreImplemented=False,goalStatus='active')))
