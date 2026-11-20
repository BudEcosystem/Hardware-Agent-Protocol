"""Seal both lifecycle semantic attempts and reconciled documentation."""
from pathlib import Path
import hashlib,json,shutil,stat
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-semantics';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt32-io-lifecycle58'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,r):assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
for name,count,errors in [('attempt01-failed57',57,7),('attempt02-passed58',58,0)]:
 p=read(R/name/'proof.json')
 assert p['counts']==dict(testsRun=count,failures=0,errors=errors,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert p['status']==('failed' if errors else 'passed') and p['sourceFilesVerified']==7755 and p['frozenFilesVerified']==7758
 assert p['externalPinsVerified']==159 and p['attemptFilesAcquired']==7789
 assert p['rawScratchFiles']==p['rawScratchBytes']==p['sqliteConnections']==0
 raw=Path(p['rawScratch']['path']);assert raw.is_dir() and not any(raw.iterdir())
 a=read(R/name/'attempt/result.json');assert a['childState']=='exited' and not Path('/proc/'+str(a['pid'])).exists()
for label in ('compiler','driver'):
 assert read(R/'attempt01-failed57/attempt'/(label+'-before.json'))==read(R/'attempt02-passed58/attempt'/(label+'-before.json'))
assert sha(B/'implementation01/project/hms/pat_io_lifecycle_semantics.py')==sha(B/'implementation02/project/hms/pat_io_lifecycle_semantics.py')
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():
  assert stat.S_ISREG(f.stat().st_mode)
  rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==15583
write(R/'index.json',dict(scope='All58 pure checks pass after retained failed57 and test-only adversary construction correction; complete20 fixed histories, not full qualification.',files=rows))
entries=[(B/'implementation01','14e731f9e5fa81ce78d663049e9d54326e5511411dc42ceee7930672c388067e',True),
 (B/'implementation02','9171613b64444be9d79b10576852cda6411a0a46c7adcd1138e8e983948ee1d4',True),
 (B/'harness01','153ababfe7ee1fb2aace6589022e7fe28c074b85b872777b91964184cbf02696',False),
 (B/'harness02','81a17bd222ab56c09f66fa45b37a4bfae8e89b579597e09bdb3118be9c471941',False),
 (R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;records=read(folder/'index.json')['files']
 for row in records:verify((ROOT if rooted else folder)/row['path'],row)
 counts[folder.relative_to(ROOT).as_posix()]=len(records)
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','DIAGNOSIS.json','test-only-correction.patch','prepare.py','prepare02.py','acquire.py','write-docs.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(D/'index.json',dict(scope='Lifecycle58 complete fixed histories reconciled; current-candidate matrix, attestation, aggregate bounds and end-to-end goal remain incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],reportFileHashesVerified=len(report['files']),
 artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=len(rows)),documents=dict(
 indexSha256=sha(D/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
