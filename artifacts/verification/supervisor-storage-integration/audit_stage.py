"""Final source/evidence audit; no project imports, tests or database opens."""
import ast
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as stream:json.dump(v,stream,indent=2);stream.write('\n')
def verify(index,prefix,pin):
    assert sha(index)==pin
    rows=read(index)['files']
    for r in rows:
        p=prefix/r['path'];assert not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
    return len(rows)
previous=ROOT/'artifacts/implementation/supervisor-storage-bindings'
assert verify(previous/'index.json',previous,'088c3474ae31d3d3aee38d787ec3b84b0d5cce3f8896335ac53ae6eea02d53dd')==655
assert verify(previous/'implementation01/index.json',ROOT,'ffcace54bb02211d47e2f69febfb2f7f1566d6ee6dcb8264a3f10ecef5a8534f')==312
verify(BASE/'control-harness-index.json',BASE,'6c45843e89b771776eae5e608f920a3aeafd4a33efbd619e521c5b4d78e65e24')
verify(BASE/'harness02/index.json',BASE/'harness02','c131c5b7947ed9267765738b534b413a63bba9dd416d9f3fd3a18db6ef36bf99')
verify(BASE/'harness01/index.json',BASE/'harness01','b53a90f96fbe5e15b4531c3b3474eb212d98a3d0fcb14f06111e82f1434e5873')
controls=read(BASE/'CONTROL_AUDIT.json');actual=read(BASE/'ACTUAL_RESULTS.json')
assert controls['tests']==71 and controls['completePassingScopes']==47 and controls['retainedFailedScopes']==['controls/legacy-handoff-02']
assert controls['diagnosticBatchingChanged'] and controls['aggregateDiagnosticBudgetIncreased'] and not controls['originalFourteenScopeProfilePassed']
release=read(BASE/'actual-release.json');assert release['controlAuditSha256']==sha(BASE/'CONTROL_AUDIT.json')
attempt=BASE/'harness01/attempts/attempt01-actual';result=read(attempt/'result.json')
assert result['currentPass'] and result['status']=='passed' and result['childState']=='exited' and result['exitCode']==0
assert result['elapsedSeconds']<180 and actual['observedSpawnToSettledMs']<60000
assert result['counts']==dict(testsRun=1,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert not result['errors'] and not result['childErrors']
assert actual['resultSha256']==sha(attempt/'result.json') and actual['actualScopePassed'] and actual['requestedCases']==actual['caseManifests']==30
assert actual['rawFiles']==4270 and actual['rawBytes']==35508922 and len(actual['ownerAndWriterLocks'])==58
assert actual['producerImageFiles']==268 and actual['workerCaseDatabasesOpened']==0 and len(actual['readonlySourceDatabases'])==4
assert actual['catalogObservation']['oneCompletedApplication'] and actual['catalogObservation']['activations']==actual['catalogObservation']['completions']==1
assert actual['catalogObservation']['cancellations']==0 and actual['sourceApplicationInvocations']==1
assert actual['catalogObservation']['originalKeyReplay'] and actual['catalogObservation']['coldVaultAndBridgeHistory']
assert actual['catalogObservation']['configurationDriftRefusesFreshAdmission']
assert read(BASE/'actual-audit-review.json')['auditSha256']==sha(BASE/'audit_actual.py')
assert (BASE/'actual-audit.stderr.txt').read_bytes()==(BASE/'actual-launch.stderr.txt').read_bytes()==b''
for pid in (result['pid'],actual['workerResourceObservation']['pid']):assert not Path('/proc',str(pid)).exists()
for r in controls['records']:
    assert sha(BASE/r['scope']/'result.json')==r['resultSha256']
runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
assert sha(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
receipt=read(runtime);assert receipt['passed'] and receipt['tests']==866 and len(receipt['files'])==244
for r in receipt['files']:assert sha(ROOT/r['path'])==r['sha256']
for p in BASE.glob('*.py'):ast.parse(p.read_bytes())
files=[p for p in BASE.rglob('*') if p.is_file()]
assert not any(p.is_symlink() for p in BASE.rglob('*'))
assert all(p.stat().st_size<=16777216 for p in files)
stage_bytes=sum(p.stat().st_size for p in files)
raw_bytes=controls['rawScratchBytes']+actual['rawBytes']
assert stage_bytes+raw_bytes<1024**3
audit=dict(status='verified-split-storage-integration',reviewer='primary-agent',independentReview=False,
    previousStageFilesVerified=655,frozenSourceFilesVerified=312,productionCandidateChanged=False,
    distinctPassingControls=71,passingControlScopes=47,retainedFailedControlScopes=1,
    originalFourteenScopeProfilePassed=False,diagnosticBatchingChanged=True,aggregateDiagnosticBudgetIncreased=True,
    actualWorkers=1,actualCases=30,actualImports=1,actualPublications=1,actualApplicationInvocations=1,
    simulatedActivations=1,simulatedCompletions=1,simulatedCancellations=0,originalKeyReplay=True,
    configurationDriftRefused=True,coldVaultAndBridgeHistory=True,originalWorkerMs=60000,originalParentSeconds=180,
    workerObservedMs=actual['observedSpawnToSettledMs'],parentElapsedSeconds=result['elapsedSeconds'],
    actualEvidenceFiles=4270,actualEvidenceBytes=actual['rawBytes'],actualOwnerWriterLocks=58,
    producerImageFiles=268,parentDatabasesReadonlyAudited=4,workerDatabasesOpened=0,
    vaultReferences=4011,vaultBodies=2798,controlBulkObjectsVerified=True,
    runtimeInputsUnchanged=244,publicBaselineTests=866,publicTestsRepeated=False,
    publicRuntimeChanged=False,stageBytesBeforeSeal=stage_bytes,additionalOriginalRawScratchBytes=raw_bytes,
    physicalProvidersQualified=False,hardAggregateQuotaEnforced=False,backedControlCapacity=False,
    hotJournalRecoveryQualified=False,wholeGoalComplete=False)
write(BASE/'AUDIT.json',audit)
write(BASE/'RESULTS.json',dict(status='verified-split-storage-controls-and-complete-simulated-integration',
    auditSha256=sha(BASE/'AUDIT.json'),controlAuditSha256=sha(BASE/'CONTROL_AUDIT.json'),actualAuditSha256=sha(BASE/'ACTUAL_RESULTS.json'),
    distinctControls=71,completeMatrixCases=30,oneSimulatedApplication=True,failedBatchPreserved=True,
    diagnosticBatchingChanged=True,actualScopeAndLimitsUnchanged=True,publicRuntimeUnchanged=True,goalComplete=False))
print(json.dumps(audit,indent=2))
