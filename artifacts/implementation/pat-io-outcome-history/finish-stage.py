"""Seal the terminal pure24 result and current documentation evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-outcome-history'
RESULT=BASE/'results/attempt01'; DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt21-io-outcome24'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as stream: stream.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
proof=read(RESULT/'proof.json')
assert proof['status']=='passed' and proof['currentPass'] and proof['counts']['testsRun']==24
assert proof['inheritedInputsUnchanged']==7060 and not proof['qualificationPassed']
rows=[]
assert not (RESULT/'index.json').exists()
for path in sorted(RESULT.rglob('*')):
    assert not path.is_symlink()
    if path.is_dir(): continue
    assert stat.S_ISREG(path.stat().st_mode)
    rows.append(dict(path=path.relative_to(RESULT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
assert len(rows)==7098
write(RESULT/'index.json',dict(scope='Actual passing24 pure independent static-policy and single-trial-outcome methods; no full matrix qualification or broader regression claim.',files=rows))
result_pin=sha(RESULT/'index.json')
entries=[(BASE/'implementation01','4e297e540c22035bd65a1b7bc1312478e0843b00a4b0f25ba0bfd683c82da2ee',True),
         (BASE/'harness01','20fa738a1627d0dd7a5b2cb7524959275c1a819fe74b8b88bf4faed94db11cfa',False),
         (RESULT,result_pin,False)]
counts={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin; indexed=read(folder/'index.json')['files']
    for row in indexed: verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(indexed)
report=read(ROOT/'artifacts/verification/project-links.json')
assert report['missing']==[] and report['project_markdown_files']==238 and report['local_links_checked']==1119
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT/row['path'])==row['sha256']
DOCS.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
         'artifacts/verification/project-links.json',(BASE/'NEXT-QUALIFICATION.md').relative_to(ROOT).as_posix()]
sources += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
copies=[]
for name in sources:
    src=ROOT/name; dst=DOCS/'inputs'/name; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dst)
    row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src)); verify(dst,row); copies.append(row)
write(DOCS/'index.json',dict(scope='Documentation/link reconciliation after static-policy and trial-outcome24; full matrix qualification, physical control and end-to-end goal remain incomplete.',
    markdownFiles=238,localLinks=1119,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(result=dict(indexSha256=result_pin,files=len(rows),bytes=sum(r['bytes'] for r in rows)),
    documents=dict(indexSha256=sha(DOCS/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=238,localLinks=1119))))
