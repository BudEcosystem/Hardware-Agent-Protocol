"""Seal the bounded authority challenge and reconciled repository documents."""
from pathlib import Path
import hashlib,json,shutil,stat
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-authority-challenges';R=B/'results/attempt01-passed76'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt29-io-authority76'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,r):assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
p=read(R/'proof.json');a=read(R/'data-audit.json')
assert p['status']=='passed' and p['counts']==dict(testsRun=76,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert a['totals']['activations']==a['totals']['canceledActivations']==4 and a['totals']['completedCycles']==0
assert a['totals']['operations']==6 and a['totals']['checkpoints']==140 and a['totals']['publicDenials']==16
assert not p['qualificationPassed'] and not a['completeAuthorityHistoryChecked']
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():
  assert stat.S_ISREG(f.stat().st_mode)
  rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==p['attemptFilesAcquired']+3
write(R/'index.json',dict(scope='76 selected methods pass; binding/full withdrawal capture and partial independent checks, not full qualification.',files=rows))
entries=[(B/'implementation01','709cbe3024ba8b08dacc601b24b06e1e9a105c1fc2d94958ff29c9c0dd0d0d79',True),
 (B/'harness01','74e95d69cbfbc56e1145f6e1ffe1f1c6c162f9774e0fb9b57ba80add1843e3eb',False),(R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;inventory=read(folder/'index.json')['files']
 for r in inventory:verify((ROOT if rooted else folder)/r['path'],r)
 counts[folder.relative_to(ROOT).as_posix()]=len(inventory)
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for r in report['files']:assert sha(ROOT/r['path'])==r['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','prepare.py','acquire.py','audit-captures.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 r=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,r);copies.append(r)
write(D/'index.json',dict(scope='Authority76 capture/request checks reconciled; complete authority history, qualification and original end-to-end goal remain incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],
 reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=len(rows)),documents=dict(
 indexSha256=sha(D/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
