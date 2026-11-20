"""Seal complete authority histories and reconciled documentation after checks."""
from pathlib import Path
import hashlib,json,shutil,stat
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-authority-semantics';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt30-io-authority181'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,r):assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
names=['attempt01-passed34','attempt02-passed72','attempt03-passed48','attempt04-passed27'];targets=set()
for number,(name,count) in enumerate(zip(names,[34,72,48,27]),1):
 p=read(R/name/'proof.json');h=B/('harness%02d'%number)
 assert p['status']=='passed' and p['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert p['sourceFilesVerified']==8098 and p['frozenFilesVerified']==8101 and p['externalPinsVerified']==159 and p['attemptFilesAcquired']==8132
 assert p['rawScratchFiles']==p['rawScratchBytes']==p['sqliteConnections']==0 and not p['qualificationPassed']
 assert Path(p['rawScratch']['path']).is_dir() and not any(Path(p['rawScratch']['path']).iterdir())
 chosen=read(h/'targets.json')['targets'];assert len(chosen)==count and not targets.intersection(chosen);targets.update(chosen)
assert len(targets)==181
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():
  assert stat.S_ISREG(f.stat().st_mode)
  rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==32537
write(R/'index.json',dict(scope='181 distinct passing pure methods; complete fixed binding/full-withdrawal histories, not full PAT qualification.',files=rows))
entries=[(B/'implementation01','56f5beaad09b6fd4233f07c403c9d3716fa6c664ae3899e905347cd9005a95f7',True),
 (B/'harness01','6d1be4d34dbae08a867712bfd736a50a012bbf17360edcf3d796f910a15f73c1',False),
 (B/'harness02','2ad4a11a054bd59b3b5f89a0b1776bd7dd8d083185717fb69c610cb6c6486d29',False),
 (B/'harness03','1ca5bbc9d9b57d82a52e429893544f8b5e3ed15a00c1e788a4a083807133511f',False),
 (B/'harness04','d6b22e97940923efaf2fd7ee4c4d3f7b00eced99997ba9d1b8b2651ff1de8e3f',False),
 (R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;records=read(folder/'index.json')['files']
 for r in records:verify((ROOT if rooted else folder)/r['path'],r)
 counts[folder.relative_to(ROOT).as_posix()]=len(records)
assert sum(counts.values())==40686
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for r in report['files']:assert sha(ROOT/r['path'])==r['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','prepare.py','acquire.py','write-docs.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 r=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,r);copies.append(r)
write(D/'index.json',dict(scope='Authority181 complete fixed histories reconciled; full candidate qualification and original end-to-end goal remain incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],
 reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=len(rows)),documents=dict(
 indexSha256=sha(D/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
