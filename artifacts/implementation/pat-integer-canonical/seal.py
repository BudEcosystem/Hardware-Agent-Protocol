"""Seal the controlled candidate, complete actual import and immutable checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01';HARNESS=BASE/'harness01';ATTEMPT=HARNESS/'attempts/attempt01-actual'
PURE=ROOT/'artifacts/verification/pat-integer-canonical-evaluation'
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt69-native-worker-accounting/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt70-integer-canonical'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def verify(prefix,row):
    path=prefix/row['path'];assert path.lstat().st_size==row['bytes'] and sha(path)==row['sha256']
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='7e86a6ddd142e59a2b7bee1daa822a0679c5d3893a301b72df14d5c6e56651b2'
assert sha(SOURCE/'index.json')=='387d33e2992d2862b1c21902b8de09195a56b569f52c3c3e04b84ce09b2d8849'
assert sha(HARNESS/'index.json')=='88a1f8019e26607ca12526c3154cfc0ff9640ca8e39fb68189133169bce6dd44'
assert sha(PURE/'index.json')=='158a1b49bc13291eaf24a59f2bc47ba6cceff5a0c86b476e95a96c6ce1edd9de'
for folder,prefix in ((SOURCE,ROOT),(HARNESS,HARNESS),(PURE,PURE)):
    for row in read(folder/'index.json')['files']:verify(prefix,row)
controls=read(BASE/'contract-controls.json')
assert controls['status']=='passed' and controls['testsRun']==9 and controls['inputsUnchanged']
assert controls['deniedEvents']==[] and controls['integerPathEnabled']
assert all(controls[key]==0 for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses'))
assert controls['runnerSha256']==sha(BASE/'run_contract_controls.py')
for row in controls['selectedModuleOrigins']:assert sha(Path(row['path']))==row['sha256']
for row in read(BASE/'audit-inputs.json')['files']:verify(BASE,row)
pure=read(PURE/'RESULTS.json')
assert pure['differentialCases']==1668 and pure['allNinePairsLower'] and not pure['projectChanged']
result=read(BASE/'RESULTS.json');actual=read(ATTEMPT/'result.json')
assert result['stageStatus']=='verified-progress-actual-scope-passed' and result['actualScopePassed']
assert actual['status']=='passed' and actual['currentPass'] and actual['childState']=='exited' and actual['exitCode']==0
assert result['caseManifests']==result['requestedCases']==30 and result['incompleteScenario'] is None
assert result['rawFiles']==4259 and result['rawBytes']==35391693
assert len(result['ownerAndWriterLocks'])==57 and len(result['readonlySourceDatabases'])==4
assert result['workerCaseDatabasesOpened']==0 and result['importReached'] and result['sourceApplicationInvocations']==0
assert result['importIntents']==result['publications']==result['evidenceManifests']==1
assert result['productionCandidateChanged'] and not result['publicRuntimeChanged']
assert result['nativeImageReceiptVerified'] and not result['nativeOriginReopenedAfterChildExit']
assert sha(ATTEMPT/'result.json')==result['resultSha256']
observation=result['workerResourceObservation'];vault=result['vaultImportObservation']
assert observation['associationVerified'] and observation['ownedObjectAndInheritedDescriptorsAssociated']
assert observation['directChildLaunches']==1 and not observation['pidBasedSampling']
assert sha(ATTEMPT/'worker-accounting.json')==observation['accountingSha256']
assert sha(ATTEMPT/'worker-accounting-launch-audit.json')==observation['launchAuditSha256']
assert vault['allVaultBodiesAndReferencesVerified'] and vault['originalBundleAndOutputBytesEqual']
assert vault['completeCases']==30 and vault['syntheticUnresolvedEffects']==0
assert vault['storage']==dict(authorityBytes=690176,vaultBytes=15448064,references=4011,bodies=2798)
assert vault['vaultUnreservedPageCapHeadroomBytes']==280576 and not vault['catalogIntegrated']
for row in read(ATTEMPT/'scratch-index.json'):verify(ATTEMPT/'scratch',row)
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
files=[]
for parent,dirs,names in os.walk(BASE,followlinks=False):
    for name in dirs:assert not (Path(parent)/name).is_symlink()
    for name in names:
        path=Path(parent)/name
        files.append(dict(path=str(path.relative_to(BASE)),bytes=path.lstat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='One-module canonicalization candidate; nine contract tests and complete original thirty-case vault import/cold history pass',
    files=sorted(files,key=lambda row:row['path']),publicRuntimeChanged=False,actualScopePassed=True))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',ROOT/'docs/prompt-to-pat.md',
    ROOT/'docs/io-driver-hub-control.md',ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(path for path in SOURCE.iterdir() if path.is_file())
selected.update(path for path in HARNESS.iterdir() if path.is_file())
selected.update(path for path in PURE.rglob('*') if path.is_file())
for name in ('result.json','worker-accounting.json','worker-accounting-launch-audit.json','imports.json','actual-tests.json'):
    selected.add(ATTEMPT/name)
work=ATTEMPT/'scratch/test_actual_original_matrix_import_and_cold_vault_history'
for name in ('original-import.json','actual-vault-checks.json','phase-times.json','worker-archive.json','scope.json'):
    selected.add(work/name)
copies=[]
for path in sorted(selected):
    body=path.read_bytes();relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(body)
    assert path.read_bytes()==target.read_bytes()
    copies.append(dict(source=str(relative),copy=str(target.relative_to(ROOT)),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),
    sourceIndexSha256=sha(SOURCE/'index.json'),pureEvaluationIndexSha256=sha(PURE/'index.json'),
    pureDifferentialCases=1668,publicContractTests=9,actualScopePassed=True,caseManifests=30,
    originalProcessAssociationVerified=True,originalVaultImportVerified=True,originalKeyReplayAndColdVaultHistoryVerified=True,
    originalStatePreserved=True,publicRuntimeChanged=False,catalogIntegrated=False,physicalObjectiveVerified=False,
    goalStatus='active',markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT/'index.json'),actualScopePassed=True,goalStatus='active')))
