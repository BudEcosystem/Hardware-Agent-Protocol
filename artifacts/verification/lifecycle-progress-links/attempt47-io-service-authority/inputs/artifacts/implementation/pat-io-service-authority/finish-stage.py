"""Seal both source snapshots, failed attempt, corrected scopes and documents."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-service-authority';R=B/'results';O=ROOT/'artifacts/implementation/pat-io-service-config'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt47-io-service-authority'
assert not(R/'index.json').exists() and not D.exists()
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
 return sorted(rows,key=lambda x:x['path'])
def identity(p):
 s=p.lstat();assert stat.S_ISDIR(s.st_mode)
 return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
pins=['4450761e8fb816ba557556a31538f9cd4ff4266dae162750ba97d9195fd24cd3','6215ff9c5fe621a704c1996af86fc6ad80da994ffb6d92e97f7bad71afb75470']
entries=[(O/'implementation01','a242d84d16919fe15da783397642d1ae7ed9b07cc14a4a5ce1de78ebabae3f65',True),
 (O/'results','f7546a5571b600c9a90a97c576bad3e294e76166f44c903affa026318b9b25bf',False)]
entries.extend((B/('implementation%02d'%n),pin,True)for n,pin in enumerate(pins,1))
for n in range(1,27):
 H=B/('harness%02d'%n);review=read(H/'review.json');assert review['sourceIndexSha256']==pins[0 if n<=13 else 1]
 prior=B/('harness%02d'%(n-13))if n>13 else O/('harness%02d'%(n if n<=11 else 1 if n==12 else 11))
 assert review['inheritedHarnessIndexSha256']==sha(prior/'index.json')
 entries.append((H,sha(H/'index.json'),False))
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin
 rows=read(folder/'index.json')['files']
 for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
 counts[folder.relative_to(ROOT).as_posix()]=len(rows)
for name,base,expected in [('implementation01',O/'implementation01/project',['hms/pat_io_bindings.py','supervisor/io_services.py','supervisor/supervisor_contracts.py']),('implementation02',B/'implementation01/project',['supervisor/io_service_store.py'])]:
 rows=read(B/name/'baseline-inputs.json')['inheritedProjectInputs'];changed=[]
 for row in rows:
  relative=(ROOT/row['path']).relative_to(base)
  if sha(B/name/'project'/relative)!=row['sha256']:changed.append(relative.as_posix())
 assert changed==expected
analysis=read(B/'RESULTS.json');assert analysis['goalStatus']=='active' and len(analysis['attempts'])==14
assert analysis['distinctTestedMethods']==analysis['distinctPassingMethods']==249 and analysis['authorityConfigurationLibraryVerified'] and not analysis['publicServiceMounted']
originals={};passed=set();identities={}
for item in analysis['attempts']:
 F=R/item['destination'];A=F/'attempt';proof=read(F/'proof.json');result=read(A/'result.json');H=B/proof['harness']
 assert proof['status']==result['status']==item['status'] and proof['counts']==result['counts']==item['counts']
 assert result['childState']=='exited' and not(Path('/proc')/str(result['pid'])).exists() and result['errors']==result['childErrors']==[]
 assert proof['harnessIndexSha256']==sha(H/'index.json') and proof['sourceIndexSha256']==read(H/'review.json')['sourceIndexSha256']
 targets=read(H/'targets.json')['targets'];actual=read(A/'actual-tests.json');assert actual['loaded']==actual['executed']==targets and actual['exactSelection']
 if proof['status']=='passed':assert not passed.intersection(targets);passed.update(targets)
 for prefix,folder,size in [('inputs',A/'project',244),('frozen',ROOT,247),('harness',A/'harness',6)]:
  rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json')) and len(rows)==size
  for row in rows:verify(folder/row['path'],row)
 external=read(A/'external-before.json');assert external==read(A/'external-after.json') and len(external['files'])==159
 for row in external['files']:verify(Path(row['resolvedPath']),row)
 origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
 for row in origins['records']:
  if 'sha256'in row:assert sha(Path(row['origin']))==row['sha256']
 for label in ('compiler','driver'):
  value=read(A/(label+'-before.json'));assert value==read(A/(label+'-after.json'))
  if label in identities:assert value==identities[label]
  else:identities[label]=value
 raw=Path(proof['rawScratch']['path']);assert identity(raw)==proof['rawScratch'] and identity(raw.parent)==read(A/'raw-scratch-before.json')['parent']
 rows=inventory(raw);assert rows==inventory(A/'scratch')==read(A/'scratch-index.json') and len(rows)==proof['rawScratchFiles']
 assert sum(row['bytes']for row in rows)==proof['rawScratchBytes']<=read(H/'review.json')['scratchBytesCeiling']
 assert len(read(A/'sqlite-connections.json'))==proof['sqliteConnections']==item['parentSqliteConnections']
 original=H/'attempts'/proof['attempt'];rows=inventory(original);assert rows==inventory(A) and len(rows)==proof['attemptFilesAcquired'];originals[item['destination']]=len(rows)
 storage=read(F/'storage-audit.json');assert storage['databaseBytesUnchanged']
 if item['counts']['testsRun']==206:
  control=read(F/'control-audit.json');assert control['databasesUnchanged']and not control['corruptStateRepaired']and len(control['corruptRecords'])==11
 elif item['counts']['testsRun']==32:
  if proof['status']=='passed':
   control=read(F/'authority-audit.json');assert control['authorityCount']==34 and control['validatedVersions']==25 and control['allSourceAuthorityEffectsZero'] and control['allDatabasesUnchanged']
  else:
   failure=read(F/'failure-audit.json');assert failure['configurationCommits']==0 and len(failure['authorities'])==32
 else:
  assert item['counts']['testsRun']==1 and proof['status']=='passed'
  q=read(A/'writer-quiescence.json');assert q['ownerQuiescent'] and len(q['records'])==1
  assert q['records'][0].get('writerQuiescent')or q['records'][0].get('launchIntentAbsent')
  process=read(F/'process-audit.json');assert process['ledgerUnchanged'] and not process['qualificationPassed'] and process['archive']['unresolvedEffects']is None
  if process['groupStatus']=='captured':
   assert process['codeImageExactClosure']and process['codeImageFiles']==258 and process['completedCases']==30 and process['states']==26 and process['claims']==process['owners']==0
   assert process['effects']==dict(activations=21,completed=11,canceled=10)
assert len(passed)==249
joined=read(R/'attempt04-passed-authority-owned/authority-service-audit.json');assert joined['configurationPersistedByAuthorityStore']and joined['sourceImageFiles']==258
authority=read(R/'attempt04-passed-authority-owned/authority-audit.json');assert authority['authorityCount']==1 and authority['validatedVersions']==1 and authority['allSourceAuthorityEffectsZero']
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]and report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(R);write(R/'index.json',dict(scope='Retained initial failure and corrected249-method authority configuration regression; full goal active.',files=rows));counts[R.relative_to(ROOT).as_posix()]=len(rows)
entries.append((R,sha(R/'index.json'),False));D.mkdir()
names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py','artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names.extend(p.relative_to(ROOT).as_posix()for p in sorted(B.iterdir())if p.is_file()and p.suffix in('.md','.py','.json','.patch','.log'))
names.extend(p.relative_to(ROOT).as_posix()for p in sorted((B/'tooling-failures').iterdir())if p.is_file())
names.extend((folder/'index.json').relative_to(ROOT).as_posix()for folder,_,_ in entries)
assert len(names)==len(set(names));copies=[]
for name in names:
 source=ROOT/name;dest=D/'inputs'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
 row=dict(source=name,copy=dest.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=sha(source));verify(dest,row);copies.append(row)
write(D/'index.json',dict(scope='Authority-owned configuration and exact249 passing methods; initial failed32 and tooling failure retained. Full goal active; no public/physical qualification.',distinctTestedMethods=249,distinctPassingMethods=249,authorityConfigurationLibraryVerified=True,publicServiceMounted=False,historicalFailuresPreserved=True,markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],originalAttemptFilesReverified=originals,artifactEntriesReverified=counts,reportFileHashesVerified=len(report['files']),files=copies))
print(json.dumps(dict(resultsFiles=len(rows),resultsIndexSha256=sha(R/'index.json'),documentIndexSha256=sha(D/'index.json'),documentCopies=len(copies),artifactEntriesReverified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'])))
