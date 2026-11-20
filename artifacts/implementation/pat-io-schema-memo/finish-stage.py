"""Seal exact schema-reuse evidence, retained failed state and current documents."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-schema-memo';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt35-schema-reuse'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):assert not p.is_symlink()and p.is_file()and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],str(p)
names=['attempt01-passed44','attempt02-passed-cutoff','attempt03-failed-gpio-deadline','attempt04-profiled-cutoff']
passed=set();identities={}
for n in names:
 p=read(R/n/'proof.json');a=read(R/n/'attempt/result.json')
 assert p['sourceFilesVerified']==218 and p['frozenFilesVerified']==221 and p['externalPinsVerified']==159
 assert a['childState']=='exited'and not(Path('/proc')/str(a['pid'])).exists()
 assert a['errors']==a['childErrors']==[]
 if p['status']=='passed':passed.update(read(R/n/'attempt/actual-tests.json')['executed'])
 raw=Path(p['rawScratch']['path']);info=raw.lstat();assert stat.S_ISDIR(info.st_mode)and info.st_ino==p['rawScratch']['inode']
 rows=[]
 for f in sorted(raw.rglob('*')):
  assert not f.is_symlink()
  if f.is_file():rows.append(dict(path=f.relative_to(raw).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
 assert rows==read(R/n/'attempt/scratch-index.json')
 for row in rows:verify(R/n/'attempt/scratch'/row['path'],row)
 assert len(rows)==p['rawScratchFiles']and sum(row['bytes']for row in rows)==p['rawScratchBytes']<=16*1024*1024
 for label in ('compiler','driver'):
  value=read(R/n/'attempt'/(label+'-before.json'));assert value==read(R/n/'attempt'/(label+'-after.json'))
  if label in identities:assert value==identities[label]
  else:identities[label]=value
assert len(passed)==45
assert not(B/'harness03/attempts').exists()
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==4508
write(R/'index.json',dict(scope='45 distinct passing checks, one retained full GPIO deadline failure after25/30cases and one repeated diagnostic profile. No qualified full group.',files=rows))
entries=[(B/'implementation01','3dc293962505981a0564286e473eea278664b3544582fbfa9161803e2975d73d',True)]
hp=['5d3df8da64fe68f7f08944e77f0c2211a945ff9385b49ab2dcbbbba3203b42b9','1407d07a56d56641ceb082173430636988ef61b4f01a8905f90bc7b4c3e2e51b',
 '868ec9a3b0c8b6f1ac3a7e106c1e02fbfd15864e76495336f52d687258c84fea','ba41735d1f118a110e11de127e8e84662a2d0f59893bde384941399a972d0f44',
 'ad89a5e05e9775bd137eb90e2a148c803a6a9fd789ebc010934096e7b7e9f115']
entries +=[(B/('harness%02d'%i),pin,False)for i,pin in enumerate(hp,1)]+[(R,sha(R/'index.json'),False)]
old=ROOT/'artifacts/implementation/pat-io-group-worker'
entries +=[(old/'implementation02','b9359ddff03ac8f7f29a82b3eea1af949afc8db4e1b1b06a2d759fa6c9669d99',True),
 (old/'results','1c764b970b22645e52b7ae3a2a5496ed34138c8234412058b24f286b95ed3746',False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;rr=read(folder/'index.json')['files']
 for row in rr:verify((ROOT if rooted else folder)/row['path'],row)
 counts[folder.relative_to(ROOT).as_posix()]=len(rr)
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources +=[(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','DEADLINE-DIAGNOSIS.json','PROFILE-ANALYSIS.json','STORAGE-ANALYSIS.json',
 'prepare.py','prepare-profile.py','acquire.py','acquire.patch','schema-reuse.patch','audit-states.py','audit-states.patch','write-docs.py','finish-stage.py']]
sources +=[(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(D/'index.json',dict(scope='Bounded schema reuse,45 distinct passing checks and actual25/30 GPIO deadline failure reconciled. End-to-end goal remains incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(files=len(rows),indexSha256=sha(R/'index.json')),documents=dict(indexSha256=sha(D/'index.json'),
 copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
