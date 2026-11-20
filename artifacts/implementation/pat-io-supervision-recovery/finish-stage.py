"""Seal exact attempts, original failures, independent audits and current progress."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-recovery';R=B/'results';D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt43-io-supervision-recovery'
assert not(R/'index.json').exists()and not D.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,row):assert not p.is_symlink()and p.is_file()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],str(p)
def inventory(folder):
 rows=[]
 for p in folder.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda r:r['path'])
def identity(p):
 s=p.lstat();assert stat.S_ISDIR(s.st_mode)
 return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
pins=['773e8fa8a052794f6052d128e7ffe92122d72f9f68374dbc86b37b1763518fe9','8d261b1dbcff5e0cd2c533a5dfad38b48a5f7ac33a826b64d443453005271e6a','618106137f7574298f3c13edeee86ffd9f9397bc3e92b6e530f32b66997c3ad0','662f2ac9478b2ba694083fe2535d3dd711ddc6126eab94df126142779cf3d3db','e0805df38e9344f3760b2af10a6f5f2ac70d36d3e29b4bfac92ff6eef7b61cad','fedf7f63cbd4131f48b770abb0615e2cacc1a377f2d1cff0623974780566a67c','97b2ae26e1f2e5e1bfaf9ad3e56e7a8d96a45b9be96e24a0bdb23661f1575f60','0ef306eca5f90da0b37add270d8ece674855ad7d8abb859a94c5b47edfd95120','eaa9305b5457deac6650a553d2ea77e8ca33164083fe004c0e1b7fe8f9b2de92','d06fe1332af4af28ade4b6e5ed7a60c78b4af35b4a9e949850f68e04abb0bbb3']
entries=[(B/'implementation01','d1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c',True)]
entries +=[(B/('harness%02d'%i),pin,False)for i,pin in enumerate(pins,1)]
old=ROOT/'artifacts/implementation/pat-io-supervision';entries +=[(old/'implementation03','30e8155181a738ace3d02de0f89402d82927dfcbf605fcd5ba1138278a6d70f4',True),(old/'results','4e01806952289d7164b8d4b4897f5b3040875640ec414123bee4f3eb0a8f6edc',False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
 for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
 counts[folder.relative_to(ROOT).as_posix()]=len(rows)
baseline=read(B/'implementation01/baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==237
for row in baseline:verify(B/'implementation01/project'/(ROOT/row['path']).relative_to(old/'implementation03/project'),row)
analysis=read(B/'RESULTS.json');assert analysis['distinctTestedMethods']==180 and len(analysis['attempts'])==10 and analysis['goalStatus']=='active'
assert analysis['qualificationPassed']is False and analysis['publicQualificationMounted']is False
passed=set();tested=set();originals={};identities={}
for e in analysis['attempts']:
 F=R/e['destination'];p=read(F/'proof.json');A=F/'attempt';r=read(A/'result.json')
 assert p['counts']==r['counts']==e['counts']and p['status']==r['status']==e['status']
 assert r['childState']=='exited'and not(Path('/proc')/str(r['pid'])).exists()and r['errors']==r['childErrors']==[]
 H=B/p['harness'];targets=read(H/'targets.json')['targets'];actual=read(A/'actual-tests.json');assert actual['loaded']==actual['executed']==targets and actual['exactSelection']
 tested.update(targets)
 if p['status']=='passed':assert r['exitCode']==p['counts']['failures']==p['counts']['errors']==0;passed.update(targets)
 for prefix,base,size in [('inputs',A/'project',239),('frozen',ROOT,242),('harness',A/'harness',6)]:
  rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json'))and len(rows)==size
  for row in rows:verify(base/row['path'],row)
 external=read(A/'external-before.json');assert external==read(A/'external-after.json')and len(external['files'])==159
 for row in external['files']:verify(Path(row['resolvedPath']),row)
 origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched']and origins['violations']==origins['prohibitedAttempts']==[]
 for row in origins['records']:
  if 'sha256'in row:assert sha(Path(row['origin']))==row['sha256']
 for label in ('compiler','driver'):
  value=read(A/(label+'-before.json'));assert value==read(A/(label+'-after.json'))
  if label in identities:assert value==identities[label]
  else:identities[label]=value
 raw=Path(p['rawScratch']['path']);assert identity(raw)==p['rawScratch']and identity(raw.parent)==read(A/'raw-scratch-before.json')['parent']
 rows=inventory(raw);assert rows==inventory(A/'scratch')==read(A/'scratch-index.json')and len(rows)==p['rawScratchFiles']
 assert sum(v['bytes']for v in rows)==p['rawScratchBytes']<=read(H/'review.json')['scratchBytesCeiling']
 assert len(read(A/'sqlite-connections.json'))==p['sqliteConnections']==e['parentSqliteConnections']
 original=H/'attempts'/p['attempt'];rows=inventory(original);assert rows==inventory(A)and len(rows)==p['attemptFilesAcquired'];originals[e['destination']]=len(rows)
 assert read(F/'storage-audit.json')['databaseBytesUnchanged']
 if p['counts']['testsRun']==1:
  q=read(A/'writer-quiescence.json');assert q['ownerQuiescent']and all(v.get('writerQuiescent')or v.get('launchIntentAbsent')for v in q['records'])
  audit=read(F/('process-audit.json'if p['status']=='passed'else'failure-audit.json'));assert audit['ledgerUnchanged'] and audit['qualificationPassed']is False
assert len(tested)==180 and len(passed)==analysis['distinctPassingMethods'] and sorted(tested-passed)==analysis['failedMethods']
F=R/'attempt01-preparation-refused';proof=read(F/'proof.json');r=read(F/'attempt/result.json');assert r['childState']=='not_started'and r['counts']is None and 'pid'not in r and 'scratchPath'not in r
for row in proof['files']:
 verify(F/'attempt'/row['path'],row);verify(B/'harness01/attempts/attempt01-control171'/row['path'],row)
originals[F.name]=len(proof['files'])
control=read(R/'attempt02-passed171/control-audit.json');assert control['databasesUnchanged']and control['corruptStateRepaired']is False and len(control['corruptRecords'])==11
for F in R.iterdir():
 for failure in F.glob('initial-*-failure.json'):
  v=read(failure);assert sha(ROOT/v['script'])==v['scriptSha256']
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]and report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(R);write(R/'index.json',dict(scope='Exact I/O recovery checks and nominal deadline failures, all originals retained; no public or physical qualification.',files=rows));counts[R.relative_to(ROOT).as_posix()]=len(rows);entries.append((R,sha(R/'index.json'),False))
D.mkdir();names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py','artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names +=[p.relative_to(ROOT).as_posix()for p in sorted(B.iterdir())if p.is_file()and p.suffix in ('.md','.py','.json','.patch')]
names +=[(folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries]
assert len(names)==len(set(names));copies=[]
for name in names:
 p=ROOT/name;q=D/'inputs'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);row=dict(source=name,copy=q.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p));verify(q,row);copies.append(row)
write(D/'index.json',dict(scope='I/O recovery stage with preserved nominal deadline failures; complete goal remains active.',distinctTestedMethods=180,distinctPassingMethods=len(passed),failedMethods=analysis['failedMethods'],markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],originalAttemptFilesReverified=originals,artifactEntriesReverified=counts,reportFileHashesVerified=len(report['files']),files=copies))
print(json.dumps(dict(resultsFiles=len(rows),resultsIndexSha256=sha(R/'index.json'),documentIndexSha256=sha(D/'index.json'),documentCopies=len(copies),artifactEntriesReverified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'])))
