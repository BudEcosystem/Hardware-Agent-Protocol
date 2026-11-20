"""Seal successful GPIO capture, retained PWM failures and current goal evidence."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-efficiency';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt36-group-efficiency'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):assert not p.is_symlink()and p.is_file()and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],str(p)
names=['attempt01-passed87','attempt02-passed-storage6','attempt03-passed-cutoff',
 'attempt04-passed-gpio','attempt05-failed-pwm','attempt06-profiled-pwm-failure']
passed=set();identities={}
for n in names:
 p=read(R/n/'proof.json');a=read(R/n/'attempt/result.json')
 assert p['sourceFilesVerified']==221 and p['frozenFilesVerified']==224 and p['externalPinsVerified']==159
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
assert len(passed)==95
rows=[]
for f in sorted(R.rglob('*')):
 assert not f.is_symlink()
 if f.is_file():rows.append(dict(path=f.relative_to(R).as_posix(),bytes=f.stat().st_size,sha256=sha(f)))
assert len(rows)==10958
write(R/'index.json',dict(scope='95 distinct passing methods including full30-case GPIO capture; retained PWM28/30 deadline failure and separate failed diagnostic profile. Full qualification incomplete.',files=rows))
entries=[(B/'implementation01','cd3593c1c6aec73eb74bdbac9ea48c5d9f5b835818a4095b27fd6d13616b58d5',True)]
hp=['c0f4c82b3202603b3c4e2553212ade29bcc240c9f45a2a0673d0e6f0c9dcdfb8','0784d6599eaebb79baa1a604250abefafbc0fe78b4ad99338e4aea12330537fb',
 '98f8b717f647ce81d4dfe7cf6e68ed4afdb2eeb9ddcf4c148e05ac47fdfa100e','859b61bc213de479e2d9720fdf4a83ca1b0b6b9d9b17c4f40c11d82f1a1c1b30',
 'c03ba72f8f1c5eaee1c42df67a7c5663e01a62ef3655e85eb8c3759c3a95c243','a96bedbedd385e1fb7a961be271b22d01453ed7938556d2bb60af513e968aa44']
entries +=[(B/('harness%02d'%i),pin,False)for i,pin in enumerate(hp,1)]+[(R,sha(R/'index.json'),False)]
old=ROOT/'artifacts/implementation/pat-io-schema-memo'
entries +=[(old/'implementation01','3dc293962505981a0564286e473eea278664b3544582fbfa9161803e2975d73d',True),
 (old/'results','ae0393ab9cf2c40fe37238a02dc812b9d57d59adb12f5f3c79e3e4cd230995dd',False)]
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
sources +=[(B/n).relative_to(ROOT).as_posix()for n in ['DESIGN.md','GROUP-ANALYSIS.json','PROFILE-ANALYSIS.json',
 'prepare.py','prepare-profile.py','acquire.py','acquire.patch','implementation.patch','audit-states.py','audit-states.patch',
 'audit-storage.py','write-docs.py','finish-stage.py']]
sources +=[(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
copies=[]
for name in sources:
 src=ROOT/name;dst=D/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 row=dict(source=name,copy=dst.relative_to(ROOT).as_posix(),bytes=src.stat().st_size,sha256=sha(src));verify(dst,row);copies.append(row)
write(D/'index.json',dict(scope='Exact plan reuse, compact fresh stores,95 distinct passing checks, complete GPIO capture and incomplete PWM reconciled. End-to-end goal remains active.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(files=len(rows),indexSha256=sha(R/'index.json')),documents=dict(indexSha256=sha(D/'index.json'),
 copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))
