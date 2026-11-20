"""Seal the acquired compiler identity83 result and reconciled documentation."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd().resolve(); B=ROOT/'artifacts/implementation/pat-compiler-identity'; R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt33-compiler-identity83'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    with p.open('x') as f: f.write(json.dumps(value,indent=2)+'\n')
def verify(p, row):
    assert not p.is_symlink() and p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)

p=read(R/'attempt01-passed83/proof.json'); a=read(R/'attempt01-passed83/attempt/result.json')
assert p['status']=='passed' and p['counts']==dict(testsRun=83,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert (p['sourceFilesVerified'],p['frozenFilesVerified'],p['externalPinsVerified'],p['attemptFilesAcquired'])==(214,217,159,248)
assert p['rawScratchFiles']==p['rawScratchBytes']==p['sqliteConnections']==0
raw=Path(p['rawScratch']['path']); info=raw.lstat()
assert stat.S_ISDIR(info.st_mode) and not any(raw.iterdir()) and info.st_ino==p['rawScratch']['inode']
assert a['childState']=='exited' and not Path('/proc/'+str(a['pid'])).exists()
compiler=read(R/'attempt01-passed83/attempt/compiler-before.json')
assert compiler==read(R/'attempt01-passed83/attempt/compiler-after.json')
assert compiler['manifest']['profile']=='hms.pat-compiler-identity/0.2'
assert len(compiler['manifest']['sources'])==14 and sum(r['fileCount'] for r in compiler['manifest']['packages'])==104
assert len(compiler['manifest']['packages'])==7
rows=[]
for f in sorted(R.rglob('*')):
    assert not f.is_symlink()
    if f.is_file():
        assert stat.S_ISREG(f.stat().st_mode)
        rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==250
write(R/'index.json',dict(scope='83 pure checks pass for the selected compiler identity correction; no complete I/O group or deployment attestation.',files=rows))
entries=[(B/'implementation01','4bdeecaea185182dd78a3a7f3cfbb531931a926f8413766455d7b77e264dfa11',True),
    (B/'harness01','2833e9bfb3c9126f100ecbd37024ff99dcd0883bf43c12b563fc88bb87214deb',False),
    (R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin
    records=read(folder/'index.json')['files']
    for row in records: verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(records)
report=read(ROOT/'artifacts/verification/project-links.json'); assert report['missing']==[]
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT/row['path'])==row['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(B/n).relative_to(ROOT).as_posix() for n in ['DESIGN.md','prepare.py','acquire.py','acquire.patch','write-docs.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
copies=[]
for name in sources:
    src=ROOT/name; dst=D/'inputs'/name; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dst)
    row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src)); verify(dst,row); copies.append(row)
write(D/'index.json',dict(scope='Selected compiler identity83 correction reconciled; exact I/O group, full attestation, aggregate bounds and end-to-end goal remain incomplete.',
    markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],
    reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=len(rows)),documents=dict(
    indexSha256=sha(D/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),
    markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
