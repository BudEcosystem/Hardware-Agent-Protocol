"""Seal acquired clock captures and reconciled documentation; stdlib only."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-challenges'
DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt25-io-clock50'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def write(p,value):
    with p.open('x')as f:f.write(json.dumps(value,indent=2)+'\n')
folder=BASE/'results/attempts01-02';proof=read(folder/'proof.json');audit=read(folder/'data-audit.json')
assert not proof['qualificationPassed'] and not proof['independentClockOutcomeChecked']
for attempt,count in zip(proof['attempts'],[46,4]):
    assert attempt['status']=='passed' and attempt['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert len(proof['attempts'])==2 and len(audit['cases'])==6
assert audit['totals']==dict(activations=4,completedCycles=0,canceledActivations=4,ticks=28,checkpoints=116,executionRecords=664,configurationRecords=270)
assert not (folder/'index.json').exists();rows=[]
for p in sorted(folder.rglob('*')):
    assert not p.is_symlink()
    if p.is_dir():continue
    assert stat.S_ISREG(p.stat().st_mode)
    rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==16790,len(rows)
write(folder/'index.json',dict(scope='50 distinct passing methods across46+4 bounded invocations. Clock capture/structural inspection only; semantic outcome and full qualification pending.',files=rows))
result_pin=sha(folder/'index.json')
entries=[(BASE/'implementation01','83df5455e2a0ecd21ccc2c9aeb42ffbcc80ba6f7dd2483ff4cb4ba44ad087f40',True),
    (BASE/'harness01','c7de4e6813e4193ae0567ddc70e7a60921aecf820ef6f9ae3aada891a3f71013',False),
    (BASE/'harness02','fa6f4df49dc4bf8dd2d6cfa944cc96ccc08e5107f68168ee2d13dc75b9389330',False),
    (folder,result_pin,False)]
counts={}
for item,pin,rooted in entries:
    assert sha(item/'index.json')==pin;rows=read(item/'index.json')['files']
    for row in rows:verify((ROOT if rooted else item)/row['path'],row)
    counts[item.relative_to(ROOT).as_posix()]=len(rows)
assert sum(counts.values())==23890
report=read(ROOT/'artifacts/verification/project-links.json')
assert report['missing']==[] and report['project_markdown_files']==274 and report['local_links_checked']==1199
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
DOCS.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(BASE/name).relative_to(ROOT).as_posix() for name in ('DESIGN.md','prepare.py','finish-stage.py')]
sources += [(item/'index.json').relative_to(ROOT).as_posix() for item,_,_ in entries]
copies=[]
for name in sources:
    src=ROOT/name;dst=DOCS/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(DOCS/'index.json',dict(scope='50 distinct passing methods across46+4 bounded invocations and6 clock/guard captures. Full semantic clock composition, qualification and original goal remain incomplete.',
    markdownFiles=274,localLinks=1199,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=result_pin,files=16790),documents=dict(indexSha256=sha(DOCS/'index.json'),
    copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=274,localLinks=1199))))
