"""Seal complete fixed lifecycle captures and the reconciled repository prose."""
from pathlib import Path
import hashlib,json,shutil,stat
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-lifecycle-challenges';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt31-io-lifecycle21'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(p,r):assert p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
names=['attempt01-passed6','attempt02-passed5','attempt03-passed5','attempt04-passed5'];targets=set();acquired=0
harness_pins=['944ccf800e93760ee6d9c23b5e9303ab01219ff0be599b2ce281f9c667f7fbd6',
 '19a56579d7b88fd1a2107506ab1f1aea183eaf3ab3bc9584727455117690ab33',
 '74a87f922c7f4501598b8ab2b7002001481ff48df3a05ae631c36f77ebea0a3c',
 '834c2e6fe6292256fa54dfa986e30358f205ebeaa3d46ff14bced2ae9ca242b8']
for number,(name,count) in enumerate(zip(names,[6,5,5,5]),1):
 p=read(R/name/'proof.json');h=B/('harness%02d'%number)
 assert p['status']=='passed' and p['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert p['sourceFilesVerified']==8101 and p['frozenFilesVerified']==8104 and p['externalPinsVerified']==159
 assert p['rawScratchBytes']<=16*1024*1024 and p['sqliteConnections']>0 and not p['qualificationPassed']
 raw=Path(p['rawScratch']['path']);assert raw.is_dir()
 rawrows=read(R/name/'attempt/scratch-index.json')
 for row in rawrows:verify(raw/row['path'],row)
 assert len(rawrows)==p['rawScratchFiles'];acquired+=p['attemptFilesAcquired']
 chosen=read(h/'targets.json')['targets'];assert len(chosen)==count and not targets.intersection(chosen);targets.update(chosen)
 assert p['harnessIndexSha256']==harness_pins[number-1]
assert len(targets)==21
audit=read(R/'data-audit.json');assert len(audit['cases'])==20 and not audit['completeLifecycleHistoryChecked']
assert audit['totals']['operations']==18 and audit['totals']['rehashedRefusals']==30
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():
  assert stat.S_ISREG(f.stat().st_mode)
  rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==acquired+10
write(R/'index.json',dict(scope='21 passing methods;20 fresh fixed lifecycle captures and partial independent request/schedule checks, not full qualification.',files=rows))
entries=[(B/'implementation01','0a3360ba3a6e9ee0fd5c9db8d8a38ef64761b9bda69969fae42264e4556c2e87',True)]
entries += [(B/('harness%02d'%i),pin,False)for i,pin in enumerate(harness_pins,1)]
entries.append((R,sha(R/'index.json'),False));counts={}
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
sources += [(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','AUDIT-ORDERING.json','prepare.py','acquire.py','audit-captures.py','write-docs.py','finish-stage.py']]
sources += [(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(D/'index.json',dict(scope='Lifecycle21 fixed captures reconciled; complete independent semantic composition, candidate qualification and end-to-end goal remain incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],
 reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(R/'index.json'),files=len(rows)),documents=dict(
 indexSha256=sha(D/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
