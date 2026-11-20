"""Seal all three terminal attempts and reconciled documentation; stdlib only."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-conflict-history'
DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt23-io-conflict52'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def write(p,v):
    with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
results=[]
for number,count,size,status in [('01',52,7104,'failed'),('02',48,8442,'passed'),('03',4,8698,'passed')]:
    folder=BASE/('results/attempt'+number);proof=read(folder/'proof.json')
    assert proof['status']==status and proof['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert proof['qualificationPassed'] is False and proof['currentPass'] is (status=='passed')
    assert not (folder/'index.json').exists(); rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_dir():continue
        assert stat.S_ISREG(p.stat().st_mode)
        rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    assert len(rows)==size,(number,len(rows))
    write(folder/'index.json',dict(scope='Terminal attempt'+number+': '+status+'; no PAT qualification or full-matrix claim.',files=rows))
    results.append((folder,sha(folder/'index.json'),False))
first=read(BASE/'results/attempt01/proof.json')
assert first['retentionLimitExceeded'] and not first['rawScratchCopied'] and first['rawScratchBytes']==16817257
left=read(BASE/'results/attempt02/attempt/actual-tests.json')['executed'];right=read(BASE/'results/attempt03/attempt/actual-tests.json')['executed']
original=read(BASE/'results/attempt01/attempt/actual-tests.json')['executed']
assert len(left)==48 and len(right)==4 and set(left).isdisjoint(right) and set(left)|set(right)==set(original)
entries=[(BASE/'implementation01','eccd20743c61cb37d73c3f2f0df770d4c0b7529132287426eac7b8921875c524',True),
    (BASE/'harness01','1874885a7b2c42dd8a721505f16fb36a619cc8b7d6afcaee04ef56ae61569ac5',False),
    (BASE/'harness02','4b717fa60a5a9592de1ee6e952c4ffb8c38c34e5579ff881d0e74d93b74cfc1a',False),
    (BASE/'harness03','ad97585d532ed6cdd9a1d3b2ee71f5af1b483f4b2fc7ae4ea839abca44117444',False)]+results
counts={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
    for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(rows)
report=read(ROOT/'artifacts/verification/project-links.json')
assert report['missing']==[] and report['project_markdown_files']==252 and report['local_links_checked']==1153
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
DOCS.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md',
    'artifacts/implementation/pat-io-conflict-history/followup-plan.json']
sources += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
copies=[]
for name in sources:
    src=ROOT/name;dst=DOCS/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(DOCS/'index.json',dict(scope='52 distinct passing methods across48+4 successful invocations; failed combined retention preserved. Full qualification and original end-to-end goal incomplete.',
    markdownFiles=252,localLinks=1153,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=[dict(index=str(p.relative_to(ROOT)/'index.json'),sha256=pin,files=counts[p.relative_to(ROOT).as_posix()])for p,pin,_ in results],
    documents=dict(indexSha256=sha(DOCS/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=252,localLinks=1153))))
