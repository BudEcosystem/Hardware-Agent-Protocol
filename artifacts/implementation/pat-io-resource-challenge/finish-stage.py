"""Seal bounded resource capture results and reconciled repository docs."""
from pathlib import Path
import hashlib,json,shutil,stat
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-resource-challenge';R=BASE/'results/attempt01-passed72'
DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt27-io-resource72'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,r):assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
p=read(R/'proof.json');a=read(R/'data-audit.json')
assert p['status']=='passed' and p['counts']==dict(testsRun=72,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert a['totals']==dict(activations=8,completedCycles=8,canceledActivations=0,operations=8,declaredPossibleAdmissions=10,ticks=14,checkpoints=88,executionRecords=438,configurationRecords=142,rehashedRefusals=9)
assert p['rawScratchFiles']==595 and p['rawScratchBytes']==3214434 and p['attemptFilesAcquired']==8654
assert not p['qualificationPassed'] and not a['completeMultiActorHistoryChecked']
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():
  assert stat.S_ISREG(f.stat().st_mode)
  rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==8657
write(R/'index.json',dict(scope='72 selected methods pass; synthetic resource capture and partial independent checks, not full multi-actor qualification.',files=rows))
entries=[(BASE/'implementation01','1f86626a0ea1c298b23065505c6728c0e73679269b4b642536fa4f7669cf1f6c',True),
 (BASE/'harness01','11c107abb92e286e2f07649be5117370cccc61cc7c3b92472ecd4f371698ec8b',False),(R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
 for r in rows:verify((ROOT if rooted else folder)/r['path'],r)
 counts[folder.relative_to(ROOT).as_posix()]=len(rows)
assert sum(counts.values())==16697
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[] and report['project_markdown_files']==326 and report['local_links_checked']==1314
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for r in report['files']:assert sha(ROOT/r['path'])==r['sha256']
DOCS.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(BASE/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','prepare.py','acquire.py','audit-captures.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=DOCS/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 r=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,r);copies.append(r)
write(DOCS/'index.json',dict(scope='Resource72 capture/request checks reconciled; complete multi-actor history, qualification and original end-to-end goal remain incomplete.',
 markdownFiles=326,localLinks=1314,missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=8657),documents=dict(indexSha256=sha(DOCS/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=326,localLinks=1314))))
