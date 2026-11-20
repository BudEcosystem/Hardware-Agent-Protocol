"""Seal parent/worker diagnostic evidence and preserve nominal failures."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-profile';R=B/'results';O=ROOT/'artifacts/implementation/pat-io-supervision-recovery';D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt44-io-supervision-profile'
assert not(R/'index.json').exists()and not D.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):assert not p.is_symlink()and p.is_file()and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],str(p)
def inventory(folder):
 rows=[]
 for p in folder.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda r:r['path'])
def identity(p):
 s=p.lstat();assert stat.S_ISDIR(s.st_mode)
 return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
entries=[(O/'implementation01','d1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c',True),
 (B/'implementation01','3ce18e62eb1aaf0af2feb5a672f8010196f56f9999cf7afa6a0b6ddc657d288c',True),
 (B/'harness01','5edaccb3194e5526ddeb1ed1d93ebb420dbdf34f375dc510ea783638c8cea464',False),
 (B/'harness02','4afb4f1de9bda3fe6f837d6d8c191c327bffc6388004fadbba3e9eb91b3560a9',False),
 (O/'results','a6fa56b9d35af5c9b6b29a0c00eea5f3f0ef3ec8d0045a9b2d132a583fe4d3a4',False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
 for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
 counts[folder.relative_to(ROOT).as_posix()]=len(rows)
changed=[];base=read(B/'implementation01/baseline-inputs.json')['inheritedProjectInputs'];assert len(base)==239
for row in base:
 rel=(ROOT/row['path']).relative_to(O/'implementation01/project');p=B/'implementation01/project'/rel
 if sha(p)!=row['sha256']:changed.append(rel.as_posix())
assert changed==['supervisor/worker_entry.py']
analysis=read(B/'RESULTS.json');assert len(analysis['attempts'])==2 and analysis['originalNominalFailuresResolved']is False and analysis['goalStatus']=='active'
originals={};identities={}
for item in analysis['attempts']:
 F=R/item['destination'];A=F/'attempt';p=read(F/'proof.json');r=read(A/'result.json');H=B/p['harness']
 assert p['status']==r['status']==item['status']and p['counts']==r['counts']==item['counts']
 assert r['childState']=='exited'and not(Path('/proc')/str(r['pid'])).exists()and r['errors']==r['childErrors']==[]
 targets=read(H/'targets.json')['targets'];actual=read(A/'actual-tests.json');assert len(targets)==1 and actual['loaded']==actual['executed']==targets and actual['exactSelection']
 for prefix,folder,size in [('inputs',A/'project',239),('frozen',ROOT,242),('harness',A/'harness',6)]:
  rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json'))and len(rows)==size
  for row in rows:verify(folder/row['path'],row)
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
 assert len(read(A/'sqlite-connections.json'))==p['sqliteConnections']==item['parentSqliteConnections']
 original=H/'attempts'/p['attempt'];rows=inventory(original);assert rows==inventory(A)and len(rows)==p['attemptFilesAcquired'];originals[item['destination']]=len(rows)
 q=read(A/'writer-quiescence.json');assert q['ownerQuiescent']and q['records'][0]['writerQuiescent']
 assert read(F/'storage-audit.json')['databaseBytesUnchanged']
 if p['status']=='passed':
  assert p['counts']['failures']==p['counts']['errors']==r['exitCode']==0
  v=read(F/'process-audit.json');assert v['codeImageExactClosure']and v['ledgerUnchanged']and v['completedCases']==30 and v['claims']==v['owners']==0
  profile=read(A/'profile.json');assert profile['wallSeconds']==analysis['parentProfile']['wallSeconds']and profile['totalFunctions']==1188
 else:
  assert p['counts']['failures']==1 and p['counts']['errors']==0 and r['exitCode']==1
  v=read(F/'worker-profile-audit.json');assert v['codeImageExactClosure']and v['ledgerUnchanged']and v['retainedCaseManifests']==10 and v['aggregateUnresolvedEffects']is None
  profile_path=next((A/'scratch').glob('*/supervisor/*/worker-profile.json'));assert sha(profile_path)==v['profileSha256']
  profile=read(profile_path);assert profile['reason']=='SIGTERM'and profile['totalFunctions']==907
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]and report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(R);write(R/'index.json',dict(scope='Separate parent/worker profiles; original nominal failures unresolved; no production optimization or qualification.',files=rows));counts[R.relative_to(ROOT).as_posix()]=len(rows);entries.append((R,sha(R/'index.json'),False))
D.mkdir();names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py','artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names +=[p.relative_to(ROOT).as_posix()for p in sorted(B.iterdir())if p.is_file()and p.suffix in ('.md','.py','.json','.patch')]
names +=[(f/'index.json').relative_to(ROOT).as_posix()for f,_,_ in entries];assert len(names)==len(set(names));copies=[]
for name in names:
 p=ROOT/name;q=D/'inputs'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);row=dict(source=name,copy=q.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p));verify(q,row);copies.append(row)
write(D/'index.json',dict(scope='Bounded diagnostic profiles and next guard-preserving optimization candidate; full goal remains active.',diagnosticAttempts=2,nominalFailuresResolved=False,markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],originalAttemptFilesReverified=originals,artifactEntriesReverified=counts,reportFileHashesVerified=len(report['files']),files=copies))
print(json.dumps(dict(resultsFiles=len(rows),resultsIndexSha256=sha(R/'index.json'),documentIndexSha256=sha(D/'index.json'),documentCopies=len(copies),artifactEntriesReverified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'])))
