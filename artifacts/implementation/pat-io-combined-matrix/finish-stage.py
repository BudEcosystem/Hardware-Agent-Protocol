"""Seal terminal matrix61 evidence and documentation without project imports."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-combined-matrix'
RESULT=BASE/'results/attempt01'; DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt22-io-matrix61'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as stream: stream.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
proof=read(RESULT/'proof.json')
assert proof['status']=='passed' and proof['currentPass'] and proof['counts']['testsRun']==61
assert proof['inheritedInputsUnchanged']==7062 and not proof['qualificationPassed'] and not proof['requiredOutcomesVerified']
assert not (RESULT/'index.json').exists(); rows=[]
for path in sorted(RESULT.rglob('*')):
    assert not path.is_symlink()
    if path.is_dir(): continue
    assert stat.S_ISREG(path.stat().st_mode)
    rows.append(dict(path=path.relative_to(RESULT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
assert len(rows)==7100
write(RESULT/'index.json',dict(scope='Actual passing61 pure combined-matrix/domain/timing tests; listed qualification challenges were not executed.',files=rows))
result_pin=sha(RESULT/'index.json')
entries=[(BASE/'implementation01','0a34336874ffe2c3d65301e40adf2b7a9328ddb08a074e02e4e777b9528bf78a',True),
         (BASE/'harness01','987740d8376199a0ac2623cfa5f107e3985220b3a439a5f831cfa14d06cc112e',False),
         (RESULT,result_pin,False)]
counts={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin; indexed=read(folder/'index.json')['files']
    for row in indexed: verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(indexed)
report=read(ROOT/'artifacts/verification/project-links.json')
assert report['missing']==[] and report['project_markdown_files']==242 and report['local_links_checked']==1127
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT/row['path'])==row['sha256']
DOCS.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
         'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
copies=[]
for name in sources:
    src=ROOT/name; dst=DOCS/'inputs'/name; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dst)
    row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src)); verify(dst,row); copies.append(row)
write(DOCS/'index.json',dict(scope='Documentation/link reconciliation after combined-matrix61 pure tests; full matrix execution, physical control and end-to-end goal remain incomplete.',
    markdownFiles=242,localLinks=1127,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(result=dict(indexSha256=result_pin,files=len(rows),bytes=sum(r['bytes'] for r in rows)),
    documents=dict(indexSha256=sha(DOCS/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=242,localLinks=1127))))
