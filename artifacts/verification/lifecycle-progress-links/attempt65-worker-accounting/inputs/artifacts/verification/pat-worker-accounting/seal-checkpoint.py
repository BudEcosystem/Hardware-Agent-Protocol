"""Seal a successful resource observation and the still-failed original scope."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt64-io-proof-batch/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt65-worker-accounting'
RESEARCH=ROOT/'research/host-contract/worker-accounting'
SOURCE=ROOT/'artifacts/implementation/pat-io-proof-batch/implementation01'
ATTEMPT=BASE/'harness02/attempts/attempt01-accounting'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path,row):assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='8ecd324342f56cec8de28b18452d73540fd9b5c1c99ceb34f6498cb17bb5a0cd'
assert sha(RESEARCH/'index.json')=='9a7a88ac0535e1bb22a6f496f2d6579b414a616a8d3aea5810fb3ed67647ce45'
assert read(RESEARCH/'reading.json')['totalLfLines']==1315
pins={BASE/'harness01':'b14032b19e17e9b5a023099c46f39fbf6747100639f85b7c5b0a8e4afc955377',
    BASE/'harness02':'8c3800eec1af47f41027bd61efedeafe567d74944659db88870858c41c31e30a',
    SOURCE:'a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5',
    RESEARCH:'9a7a88ac0535e1bb22a6f496f2d6579b414a616a8d3aea5810fb3ed67647ce45'}
for folder,pin in pins.items():
    assert sha(folder/'index.json')==pin
    for row in read(folder/'index.json')['files']:verify((ROOT if folder==SOURCE else folder)/row['path'],row)
assert not (BASE/'harness01/attempts').exists()
controls=read(BASE/'controls.json');result=read(BASE/'RESULTS.json');actual=read(ATTEMPT/'result.json')
assert controls['status']=='passed' and controls['testsRun']==15 and controls['sourceUnchanged'] and controls['deniedEvents']==[]
for row in controls['before']:verify(BASE/row['path'],row)
assert result['stageStatus']=='verified-resource-observation-original-scope-failed'
assert not result['actualScopePassed'] and not result['productionCandidateChanged'] and not result['publicRuntimeChanged']
assert result['requestedCases']==30 and result['caseManifests']==25 and result['originalMaxWallMs']==60000
assert not result['importReached'] and result['workerUnresolvedEffects'] is None and result['workerCaseDatabasesOpened']==0
assert len(result['ownerAndWriterLocks'])==49 and len(result['readonlySourceDatabases'])==4
observation=result['resourceObservation']
assert observation['associationVerified'] and observation['directChildLaunches']==1
assert observation['launchToReapCpuSeconds']=={'self':18.454471,'children':36.580244}
assert not observation['schedulingWaitCauseMeasured'] and not observation['parentFunctionAttributionMeasured']
assert sha(ATTEMPT/'worker-accounting.json')==observation['accountingSha256']
assert sha(ATTEMPT/'worker-accounting-launch-audit.json')==observation['launchAuditSha256']
assert sha(ATTEMPT/'result.json')==result['resultSha256']
assert actual['status']=='failed' and actual['childState']=='exited' and actual['exitCode']==1
assert actual['errors']==actual['childErrors']==[]
for row in read(ATTEMPT/'scratch-index.json'):verify(ATTEMPT/'scratch'/row['path'],row)
for label,prefix in (('inputs',ATTEMPT/'project'),('frozen',ROOT),('harness',ATTEMPT/'harness')):
    before=read(ATTEMPT/(label+'-before.json'));assert before==read(ATTEMPT/(label+'-after.json'))
    for row in before:verify(prefix/row['path'],row)
assert sha(BASE/'audit.py')==read(BASE/'audit-review.json')['auditSha256']
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and sha(ROOT/'scripts/check_project_links.py')==links['checker_sha256']
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
write(BASE/'index.json',dict(scope='15 pure observer controls pass; original 30-case integration fails before import; resource observations and original association verified; public runtime unchanged',files=files))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',ROOT/'docs/prompt-to-pat.md',
    ROOT/'docs/io-driver-hub-control.md',ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR,SOURCE/'index.json'}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(BASE.glob('harness*/index.json'))
selected.update(BASE.glob('harness*/README.md'))
selected.update(BASE.glob('harness*/SCOPE.md'))
selected.update(path for path in RESEARCH.rglob('*') if path.is_file())
copies=[]
for path in sorted(selected):
    relative=path.relative_to(ROOT);target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True);body=path.read_bytes()
    with target.open('xb') as stream:stream.write(body)
    assert target.read_bytes()==path.read_bytes()==body
    copies.append(dict(source=relative.as_posix(),copy=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(files),
    researchIndexSha256=sha(RESEARCH/'index.json'),fullyReadLfLines=1315,pureTests=15,
    originalIntegrationPassed=False,requestedCases=30,caseManifests=25,importReached=False,
    measurementAssociationVerified=True,childCpuSeconds=36.580244,parentCpuSeconds=18.454471,
    productionSourceChanged=False,publicRuntimeChanged=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(files),stageIndexSha256=sha(BASE/'index.json'),
    checkpointFiles=len(copies),checkpointIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
