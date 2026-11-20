"""Seal failed and passing attempts plus the reconciled documentation; stdlib only."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-timing-challenges'
DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt24-io-timing94'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def write(p,value):
    with p.open('x')as f:f.write(json.dumps(value,indent=2)+'\n')

results=[]
for name,size,counts,status,errors in [('attempts01-02',16498,[9,8],'failed',2),('attempts03-05',23605,[9,8,77],'passed',0)]:
    folder=BASE/'results'/name;proof=read(folder/'proof.json')
    assert not proof['qualificationPassed'] and not proof['requiredMatrixCoverageChecked']
    assert len(proof['attempts'])==len(counts)
    for attempt,count in zip(proof['attempts'],counts):
        assert attempt['status']==status and attempt['counts']==dict(testsRun=count,failures=0,errors=errors,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    rows=[]
    assert not (folder/'index.json').exists()
    for path in sorted(folder.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir():continue
        assert stat.S_ISREG(path.stat().st_mode)
        rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    assert len(rows)==size,(name,len(rows))
    write(folder/'index.json',dict(scope=status+' timing attempts; original failures preserved, no complete matrix or PAT qualification claim.',files=rows))
    results.append((folder,sha(folder/'index.json'),False))
audit=read(BASE/'results/attempts03-05/data-audit.json')
assert audit['distinctPassingMethods']==94 and audit['runtimeCases']==16 and not audit['qualificationPassed']
assert audit['totals']==dict(activations=12,completedCycles=8,canceledActivations=4,schedulerTicks=68)
assert sha(BASE/'preparation-diagnostics/rejected-child.txt')==read(BASE/'correction-plan.json')['rejectedChildSha256']
assert read(BASE/'preparation-diagnostics/failure.json')['projectExecution'] is False

entries=[(BASE/'implementation01','adb63bce663e249d06b1c46bec3d04fed6d1111e43796dd56c9567211bcbd381',True),
    (BASE/'implementation02','6a7531015ffe1e5a758e7cbe27d94f54a6a9134e8e423d14e40b45154a7e46a0',True),
    (BASE/'harness01','8200dc8c5c2ed0fda1ef487707da1a3a899fd279cb9fb6cf22eb26f266740c43',False),
    (BASE/'harness02','c7c18267b43f66707edeeaa4fc22ae362a2c8fb65c7d2d207bc2388349461fa3',False),
    (BASE/'harness03','53d8141865899203d4562f52ad2f299b424764cf9d9394c8889dc6cc2238a729',False),
    (BASE/'harness04','5d7de5288ec2703bbf170f14c6114edabaa56936f92bd8c23abf3dc10bab9696',False),
    (BASE/'harness05','fa2f9fee9301bc59dc4d705cdc240a912e8ec0bcdb96d18b6bc403aa03dd9194',False)]+results
counts={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
    for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(rows)
assert sum(counts.values())==54309
report=read(ROOT/'artifacts/verification/project-links.json')
assert report['missing']==[] and report['project_markdown_files']==266 and report['local_links_checked']==1181
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']

DOCS.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(BASE/name).relative_to(ROOT).as_posix() for name in ('correction-plan.json','preparation-diagnostics/failure.json',
    'preparation-diagnostics/rejected-child.txt','prepare.py','prepare-correction.py','prepare-acquisition.py','finish-stage.py')]
sources += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
copies=[]
for name in sources:
    src=ROOT/name;dst=DOCS/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(DOCS/'index.json',dict(scope='94 distinct passing methods across9+8+77 bounded invocations,16 timing trials; initial failed attempts preserved. Full qualification and original end-to-end goal incomplete.',
    markdownFiles=266,localLinks=1181,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=[dict(index=str(p.relative_to(ROOT)/'index.json'),sha256=pin,files=counts[p.relative_to(ROOT).as_posix()])for p,pin,_ in results],
    documents=dict(indexSha256=sha(DOCS/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=266,localLinks=1181))))
