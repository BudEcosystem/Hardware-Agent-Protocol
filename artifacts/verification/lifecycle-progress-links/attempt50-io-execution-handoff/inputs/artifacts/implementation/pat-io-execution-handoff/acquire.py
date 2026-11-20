"""Acquire a complete terminated group attempt, preserving raw state."""
import hashlib,json,re,shutil,stat,sys
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-execution-handoff'
harness,name,dest=sys.argv[1:];H=BASE/harness;A=H/'attempts'/name;OUT=BASE/'results'/dest
assert not OUT.exists();OUT.mkdir(parents=True)
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,r):assert not p.is_symlink() and p.is_file() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def inventory(folder):
 rows=[]
 for p in sorted(folder.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda row:row['path'])
def identity(p):
 s=p.lstat();assert stat.S_ISDIR(s.st_mode)
 return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
for row in read(H/'index.json')['files']:verify(H/row['path'],row)
review=read(H/'review.json');count=review['tests'];assert sha(H/'targets.json')==review['targetSha256']
project_count=review.get('projectInputCount',252);frozen_count=review.get('frozenPreparationInputCount',255)
assert (project_count,frozen_count) in {(252,255),(253,256)}
r=read(A/'result.json');assert r['status'] in {'passed','failed'} and r['childState']=='exited' and r['currentPass'] is (r['status']=='passed')
assert r['exitCode']in{0,1} and not Path('/proc/'+str(r['pid'])).exists() and r['timeoutSeconds']==180
assert r['errors']==r['childErrors']==[] and r['counts']['testsRun']==count
for key in ('skips','expectedFailures','unexpectedSuccesses'):assert r['counts'][key]==0
if r['status']=='passed':assert r['exitCode']==r['counts']['failures']==r['counts']['errors']==0
for prefix,folder,n in [('inputs',A/'project',project_count),('frozen',ROOT,frozen_count),('harness',A/'harness',6)]:
 rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json')) and len(rows)==n
 for row in rows:verify(folder/row['path'],row)
external=read(A/'external-before.json');assert external==read(A/'external-after.json') and len(external['files'])==159
for row in external['files']:verify(Path(row['resolvedPath']),row)
origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
for row in origins['records']:
 if 'sha256'in row:assert sha(Path(row['origin']))==row['sha256']
for label in ('compiler','driver'):assert read(A/(label+'-before.json'))==read(A/(label+'-after.json'))
actual=read(A/'actual-tests.json');targets=read(H/'targets.json')['targets'];assert actual['loaded']==actual['executed']==targets and len(targets)==count
raw=Path(r['scratchPath']);before=read(A/'raw-scratch-before.json');assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
rawrows=inventory(raw);assert rawrows==inventory(A/'scratch')==read(A/'scratch-index.json');assert sum(v['bytes']for v in rawrows)<=review['scratchBytesCeiling']
connections=read(A/'sqlite-connections.json')
kind=review.get('selectionKind','inherited')
if kind!='inherited':
 assert kind in {'authority','handoff','process','history'}
 assert len(connections)<=review['sqliteConnectionsMaximum']
 if kind=='process' and r['status']=='passed':assert len(connections)==6
 for c in connections:
  assert c['testId'] in targets
  path=Path(c['database']);assert path.parent.parent==raw/c['testId'].rsplit('.',1)[1]
  if kind=='authority':assert path.parent.name in {'supervisor','other','legacy'} and path.name=='attempts.db'
  else:
   assert (path.parent.name in ({'supervisor'} if kind in {'process','history'} else {'supervisor','replacement'}) and path.name=='attempts.db') or (path.parent.name=='runtime' and (path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\.db',path.name)))
 for target in targets:assert sum(c['testId']==target for c in connections)<=review['sqliteConnectionsPerMethod']
 if kind=='process':
  quiescence=read(A/'writer-quiescence.json');assert quiescence['ownerQuiescent']
  if r['status']=='passed':assert len(quiescence['records'])==1 and quiescence['records'][0]['state']=='archived'
elif count==206:
 assert len(connections)<=32
 if r['status']=='passed':assert len(connections)==28
 for c in connections:
  assert c['testId'] in review['controlTargets']
  path=Path(c['database']);assert path.parent.parent==raw/c['testId'].rsplit('.',1)[1]
  assert path.parent.name in review['controlLabels'] and path.name=='attempts.db'
elif count==19:
 assert connections==[] and review['sqliteConnectionsMaximum']==0
elif count in (32,15,14):
 assert len(connections)<=review['sqliteConnectionsMaximum']
 if r['status']=='passed': assert len(connections)==review['sqliteConnectionsMaximum']
 for c in connections:
  assert c['testId'] in targets
  path=Path(c['database']);assert path.parent.parent==raw/c['testId'].rsplit('.',1)[1]
  assert path.parent.name in {'runtime','runtime-other'} and (path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\.db',path.name))
 for target in targets: assert sum(c['testId']==target for c in connections)<=4
else:
 assert count==1
 expected=9 if '.IoReservedProcessTests.' in targets[0] else 6 if '.IoAuthorityProcessTests.' in targets[0] else 2 if any(cls in targets[0] for cls in ('.IoPwmSupervisionTests.','.IoConfiguredProcessTests.')) else 1
 assert len(connections)==expected if r['status']=='passed' else 0<=len(connections)<=expected
 for c in connections:
  assert c['testId']==targets[0]
  path=Path(c['database']);work=raw/targets[0].rsplit('.',1)[1]
  assert path==work/'supervisor'/'attempts.db' or (any(cls in targets[0] for cls in ('.IoAuthorityProcessTests.','.IoReservedProcessTests.')) and path.parent==work/'runtime' and (path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\.db',path.name)))
 quiescence=read(A/'writer-quiescence.json')
 if r['status']=='passed':
  assert quiescence['ownerQuiescent'] is True and len(quiescence['records'])==1
  q=quiescence['records'][0];assert q['state']=='archived'
  assert q.get('writerQuiescent') is True or q.get('launchIntentAbsent') is True
log=(A/'output.log').read_text();m=re.search(r'Ran '+str(count)+r' tests? in ([0-9.]+)s',log);assert m
rows=inventory(A);shutil.copytree(A,OUT/'attempt');assert inventory(OUT/'attempt')==rows==inventory(A)
proof=dict(scope='Complete terminated exact I/O-supervision test scope; parent SQL inventory distinguished from pinned synthetic worker state.',
 harness=harness,harnessIndexSha256=sha(H/'index.json'),sourceIndexSha256=review['sourceIndexSha256'],targetsSha256=sha(H/'targets.json'),
 attempt=name,status=r['status'],counts=r['counts'],testSeconds=float(m.group(1)),elapsedSeconds=r['elapsedSeconds'],
 sourceFilesVerified=project_count,frozenFilesVerified=frozen_count,externalPinsVerified=159,actualOrigins=origins['summary'],
 bytecodeReadsRefused=len(origins['deniedBytecodeReads']),rawScratch=before['identity'],rawScratchFiles=len(rawrows),rawScratchBytes=sum(v['bytes']for v in rawrows),
 attemptFilesAcquired=len(rows),sourceAndCompilerDriverStable=True,actualOriginHashesRechecked=True,originalsAndCompleteCopiesRetained=True,
 sqliteConnections=len(connections),qualificationPassed=False,requiredMatrixCoverageChecked=False,completeLifecycleHistoryChecked=False,physicalMeasurementChecked=False)
with (OUT/'proof.json').open('x')as f:f.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
