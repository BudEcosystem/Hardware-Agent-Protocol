"""Seal every actual attempt, retained failure and current progress document."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-group-worker';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt34-io-group-capture'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):assert not p.is_symlink()and p.is_file()and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],str(p)
names=['attempt01-passed11','attempt02-failed-gpio-acquired','attempt03-passed12',
 'attempt04-failed-gpio-deadline','attempt05-passed-cutoff','attempt06-profiled-cutoff']
for n in names:
 p=read(R/n/'proof.json');a=read(R/n/'attempt/result.json')
 assert p['sourceFilesVerified']==217 and p['frozenFilesVerified']==220 and p['externalPinsVerified']==159
 assert a['childState']=='exited' and not (Path('/proc')/str(a['pid'])).exists()
 raw=Path(p['rawScratch']['path']);info=raw.lstat();assert stat.S_ISDIR(info.st_mode)and info.st_ino==p['rawScratch']['inode']
 original=[]
 for f in sorted(raw.rglob('*')):
  assert not f.is_symlink()
  if f.is_file():original.append(dict(path=f.relative_to(raw).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
 assert original==read(R/n/'attempt/scratch-index.json')
 for r in original:verify(R/n/'attempt/scratch'/r['path'],r)
 assert len(original)==p['rawScratchFiles']and sum(r['bytes']for r in original)==p['rawScratchBytes']<=16*1024*1024
 for label in ('compiler','driver'):assert read(R/n/'attempt'/(label+'-before.json'))==read(R/n/'attempt'/(label+'-after.json'))
for label in ('compiler','driver'):
 current=read(R/'attempt03-passed12/attempt'/(label+'-before.json'))
 for n in names[3:]:assert current==read(R/n/'attempt'/(label+'-before.json'))
assert read(R/'attempt02-failed-gpio-acquired/attempt/driver-before.json')!=read(R/'attempt03-passed12/attempt/driver-before.json')
for h in ('harness03','harness04','harness07'):assert not(B/h/'attempts').exists()
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==3383
write(R/'index.json',dict(scope='Two failed full-group attempts,13 distinct current passes and one repeated diagnostic profile; complete qualification remains unfinished.',files=rows))
entries=[(B/'implementation01','84d21cc5515a9be0d8c8112b1c1c49a747e3088a243ca82eead659009c3e1408',True),
 (B/'implementation02','b9359ddff03ac8f7f29a82b3eea1af949afc8db4e1b1b06a2d759fa6c9669d99',True)]
hp=['1ab6d97090991d005acb62bdff8eae2320c0f9dad7f5c6badda6087f0debbd7c','4ea07f36f9b2bfed55fa90ef3becc2cde8c05fca88b698ca2b83eb9b6c3558d1',
 '22e666cf4231f394b222074e929ecca63425838850748aa8cb75c1a0638af760','c455f36150f15e35f34ff050daeadcffbc8acae3424f2cb6400e82f9b5a4a0b3',
 'a09a5d06696a77856afec21ff65f737d8c3b8f171d6534ab4155db3ceddc6deb','e613aefeb0cd047c6ffb255c386908e643db3255b864ceb5d09a0e6c4772fab4',
 '4a8a48e8e06e88fc3de67d977ad98ab1b5dec82ae97fbf89734fdadf35375085','ecf1ba28ca46a03dda074db5e33ecfaddc54559862d5c2f5236b4edc01a6f5e6',
 '94b480fdd5556f67d267e45f8a0b04ccb69596e94e2444a8685dce8b4ffafadc']
entries +=[(B/('harness%02d'%i),pin,False)for i,pin in enumerate(hp,1)]+[(R,sha(R/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;rr=read(folder/'index.json')['files']
 for r in rr:verify((ROOT if rooted else folder)/r['path'],r)
 counts[folder.relative_to(ROOT).as_posix()]=len(rr)
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
D.mkdir(exist_ok=False)
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
 'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources +=[(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','DIAGNOSIS.json','DEADLINE-DIAGNOSIS.json','PROFILE-ANALYSIS.json',
 'prepare.py','prepare02.py','acquire.py','acquire.patch','acquire02.py','acquire02.patch','negative-result-correction.patch','audit-states.py','write-docs.py','finish-stage.py']]
sources +=[(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(D/'index.json',dict(scope='Current group capture/budget implementation and measured deadline failure reconciled; end-to-end goal remains incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(files=len(rows),indexSha256=sha(R/'index.json')),documents=dict(indexSha256=sha(D/'index.json'),
 copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
