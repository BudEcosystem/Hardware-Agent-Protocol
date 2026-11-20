"""Seal complete resource history results and reconciled documentation."""
from pathlib import Path
import hashlib,json,shutil,stat
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-resource-semantics';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt28-io-resource152'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,r):assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
names=['attempt01-passed31','attempt02-passed73','attempt03-passed48'];targets=set()
for number,(name,count) in enumerate(zip(names,[31,73,48]),1):
 p=read(R/name/'proof.json');h=B/('harness%02d'%number)
 assert p['status']=='passed' and p['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert p['sourceFilesVerified']==7665 and p['frozenFilesVerified']==7668 and p['externalPinsVerified']==159 and p['attemptFilesAcquired']==7699
 assert p['rawScratchFiles']==p['rawScratchBytes']==p['sqliteConnections']==0 and not p['qualificationPassed']
 assert Path(p['rawScratch']['path']).is_dir() and not any(Path(p['rawScratch']['path']).iterdir())
 t=read(h/'targets.json')['targets'];assert len(t)==count and not targets.intersection(t);targets.update(t)
assert len(targets)==152
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():
  assert stat.S_ISREG(f.stat().st_mode)
  rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==23104
write(R/'index.json',dict(scope='152 distinct passing pure methods; complete history for the fixed resource challenge, not full PAT qualification.',files=rows))
entries=[(B/'implementation01','045897b786682b0e676a376e1292bd86309f22bd9a73744fd86e9df841e7c639',True),
 (B/'harness01','9db0613dd63c4afefdcc9a431e50b43424e96032a60b4a7635b0c17bd0a0d9a1',False),
 (B/'harness02','b7a981ba11fd4e831495162b8ff4d4a62af13282cc52a7940e8d96ad054cd64f',False),
 (B/'harness03','abad135692b4f4fdfbd17dd27a313983e1542938f753f6d60d205848bfbd2610',False),(R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;records=read(folder/'index.json')['files']
 for r in records:verify((ROOT if rooted else folder)/r['path'],r)
 counts[folder.relative_to(ROOT).as_posix()]=len(records)
assert sum(counts.values())==30808
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[] and report['project_markdown_files']==338 and report['local_links_checked']==1345
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for r in report['files']:assert sha(ROOT/r['path'])==r['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','prepare.py','acquire.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 r=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,r);copies.append(r)
write(D/'index.json',dict(scope='Resource152 complete fixed-challenge history reconciled; full candidate qualification and original end-to-end goal remain incomplete.',
 markdownFiles=338,localLinks=1345,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=23104),documents=dict(indexSha256=sha(D/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=338,localLinks=1345))))
