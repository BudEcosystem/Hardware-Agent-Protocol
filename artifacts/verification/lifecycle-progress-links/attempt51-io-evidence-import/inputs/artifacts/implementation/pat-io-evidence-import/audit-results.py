"""Read-only receipt/source/retention audit; never execute or repair a fixture."""
import hashlib
import json
from pathlib import Path
import sqlite3
import stat

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-evidence-import'
PINS={'implementation01':'25678ecd4d7c3daf4719b51d97fa323da2d2cba3b899d72ee77c7e65bb4adb4c',
      'implementation02':'fdb4486f667c5ef626a9a55eee023d043544ae0b5856c56c511b7c641508a452'}
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def verify(path,row):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])

for name,pin in PINS.items():
    assert sha(BASE/name/'index.json')==pin
    for row in read(BASE/name/'index.json')['files']:verify(ROOT/row['path'],row)
results=[]; database_audits=[]
for i in range(1,25):
    harness=BASE/('harness%02d'%i); attempt=harness/'attempts/attempt01'
    for row in read(harness/'index.json')['files']:verify(harness/row['path'],row)
    result=read(attempt/'result.json'); targets=read(harness/'targets.json')['targets']
    assert result['childState']=='exited' and result['errors']==result['childErrors']==[]
    assert result['counts']==dict(testsRun=len(targets),failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert result['actualTests']==dict(loaded=targets,executed=targets,exactSelection=True)
    assert result['originSummary']['allOriginsMatched'] and result['originSummary']['prohibitedAttemptCount']==0
    for key in ('inputsUnchanged','frozenPreparationUnchanged','harnessUnchanged','retainedHarnessUnchanged',
                'externalInputsUnchanged','compilerIdentityUnchanged','driverIdentityUnchanged','scratchRetained',
                'rawScratchRetained','rawScratchIdentityUnchanged','rawScratchParentIdentityUnchanged',
                'rawScratchInventoryTerminal','rawScratchCopyVerified'):
        assert result[key] is True
    assert result['timeoutSeconds']==180 and result['limits']['scratchRetentionBytes']==16*1024*1024
    if i<24: assert result['status']=='passed' and result['exitCode']==0 and result['currentPass'] is True
    else: assert result['status']=='failed' and result['exitCode']==1 and result['currentPass'] is False
    for label,folder in [('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')]:
        rows=read(attempt/(label+'-before.json')); assert rows==read(attempt/(label+'-after.json'))
        for row in rows:verify(folder/row['path'],row)
    assert read(attempt/'external-before.json')==read(attempt/'external-after.json')
    for row in read(attempt/'external-before.json')['files']:verify(Path(row['resolvedPath']),row)
    for row in read(attempt/'imports.json')['records']:
        if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
    for label in ('compiler','driver'):assert read(attempt/(label+'-before.json'))==read(attempt/(label+'-after.json'))
    scratch=Path(result['scratchPath']); meta=read(attempt/'raw-scratch-before.json')['identity']; info=scratch.lstat()
    assert stat.S_ISDIR(info.st_mode) and not scratch.is_symlink()
    assert (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode))==(meta['device'],meta['inode'],meta['uid'],meta['mode'])
    rows=inventory(scratch); assert rows==inventory(attempt/'scratch')==read(attempt/'scratch-index.json')
    assert sum(row['bytes'] for row in rows)==result['scratchRetainedBytes']<=16*1024*1024
    sql=read(attempt/'sqlite-connections.json'); assert len(sql)==(0 if i==24 else 3)
    for entry in sql:
        original=Path(entry['database']); relative=original.relative_to(scratch); copied=attempt/'scratch'/relative
        assert sha(original)==sha(copied); before=sha(copied)
        connection=sqlite3.connect(copied.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            audit=dict(control=i,database=relative.as_posix(),sha256=before)
            if 'ioei_runs' in tables:
                audit['importRows']=connection.execute('SELECT count(*) FROM ioei_runs').fetchone()[0]
                audit['documentRows']=connection.execute('SELECT count(*) FROM ioei_documents').fetchone()[0]
                audit['actualWorkerVerified']=False
                for (body,) in connection.execute("SELECT body FROM ioei_documents WHERE path='original/output/result.json'"):
                    assert json.loads(body)==dict(fixture=True,workerExecuted=False,semanticsVerified=False)
                audit['allImportedOutputsExplicitFixtures']=True
            database_audits.append(audit)
        finally:connection.close()
        assert sha(copied)==before==sha(original)
    results.append(dict(scope=i,harness=harness.relative_to(BASE).as_posix(),attempt=attempt.relative_to(BASE).as_posix(),
        harnessIndexSha256=sha(harness/'index.json'),sourceIndexSha256=read(harness/'review.json')['sourceIndexSha256'],
        status=result['status'],currentPass=result['currentPass'],targets=targets,counts=result['counts'],
        elapsedSeconds=result['elapsedSeconds'],scratchFiles=len(rows),scratchBytes=result['scratchRetainedBytes']))

# Diagnose the exact retained child expression without importing/rerunning it.
child=BASE/'harness24/attempts/attempt01/harness/attempt_child.py'
text=child.read_text(); assert text.count("counts['testsRun'] == 1")==1
result=read(BASE/'harness24/attempts/attempt01/result.json')
diagnosis=dict(originalStatus='failed',originalChildExitCode=1,originalStatusPreserved=True,
    testMethodsReportedPassing=3,exactSelection=True,originsVerified=True,childErrors=[],
    offendingExpression="counts['testsRun'] == 1",actualTestsRun=3,
    source=child.relative_to(ROOT).as_posix(),sourceSha256=sha(child),rerun=False,repair=False,
    conclusion='The final one-test count predicate is false; all other recorded final predicates pass. The wrapper failure remains retained.')
write(BASE/'reducer-harness-diagnosis.json',diagnosis)
pure=BASE/'harness24/attempts/attempt01/scratch/test_complete_legacy_capture_reduces_without_claiming_new_handoff/pure-reducer-result.json'
value=read(pure)
assert value['realHandoff'] is value['workerExecuted'] is value['published'] is False
assert value['evaluation']['inspectedCases']==30 and value['evaluation']['unresolvedEffects']==0
write(BASE/'RESULTS.json',dict(goalStatus='active',attemptedScopes=24,passingScopes=23,failingScopes=1,
    completeMethodReceipts=26,storageControlMethodsPassed=23,pureReducerMethodsReportedPassing=3,
    pureReducerWrapperPassed=False,historicalMatrixCasesInspected=30,actualBoundWorkerExecuted=False,
    realBoundImportVerified=False,publicCatalogMounted=False,physicalObjectiveVerified=False,
    sourcePins=PINS,attempts=results,databaseAudits=database_audits,
    diagnosis='reducer-harness-diagnosis.json',rawAndCopiedDatabaseBytesUnchanged=True,
    historicalFailuresPreserved=True,independentReview=False))
print(json.dumps(dict(scopes=24,passed=23,failed=1,methodReceipts=26,databases=len(database_audits),goalStatus='active')))
