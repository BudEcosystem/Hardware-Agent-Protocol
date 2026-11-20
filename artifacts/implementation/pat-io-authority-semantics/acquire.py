"""Acquire one terminated pure authority history attempt, including failures; stdlib only."""
import hashlib,json,re,shutil,stat,sys
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-authority-semantics'
harness,name,dest,count=sys.argv[1:];count=int(count);H=BASE/harness;A=H/'attempts'/name;OUT=BASE/'results'/dest
assert not OUT.exists();OUT.mkdir(parents=True)
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):assert not p.is_symlink() and p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def inventory(folder):
 rows=[]
 for p in sorted(folder.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return rows
def identity(p):
 s=p.lstat();assert stat.S_ISDIR(s.st_mode)
 return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
for row in read(H/'index.json')['files']:verify(H/row['path'],row)
review=read(H/'review.json');assert review['tests']==count and sha(H/'targets.json')==review['targetSha256']
r=read(A/'result.json');assert r['status']in{'passed','failed'} and r['childState']=='exited' and r['currentPass']is(r['status']=='passed')
assert r['exitCode']in{0,1} and not Path('/proc/'+str(r['pid'])).exists() and r['timeoutSeconds']==180
assert r['errors']==r['childErrors']==[] and r['counts']['testsRun']==count
for key in ('skips','expectedFailures','unexpectedSuccesses'):assert r['counts'][key]==0
if r['status']=='passed':assert r['exitCode']==r['counts']['failures']==r['counts']['errors']==0
for prefix,folder,n in [('inputs',A/'project',8098),('frozen',ROOT,8101),('harness',A/'harness',6)]:
 rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json'))and len(rows)==n
 for row in rows:verify(folder/row['path'],row)
external=read(A/'external-before.json');assert external==read(A/'external-after.json') and len(external['files'])==159
for row in external['files']:verify(Path(row['resolvedPath']),row)
assert read(A/'sqlite-connections.json')==[]
origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
for row in origins['records']:
 if 'sha256'in row:assert sha(Path(row['origin']))==row['sha256']
for label in ('compiler','driver'):assert read(A/(label+'-before.json'))==read(A/(label+'-after.json'))
actual=read(A/'actual-tests.json');targets=read(H/'targets.json')['targets'];assert actual['loaded']==actual['executed']==targets and len(targets)==count
raw=Path(r['scratchPath']);before=read(A/'raw-scratch-before.json');assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
assert inventory(raw)==inventory(A/'scratch')==read(A/'scratch-index.json')==[]
log=(A/'output.log').read_text();m=re.search(r'Ran '+str(count)+r' tests in ([0-9.]+)s',log);assert m
rows=inventory(A);shutil.copytree(A,OUT/'attempt');assert inventory(OUT/'attempt')==rows==inventory(A)
proof=dict(scope='Acquired complete terminated pure-authority test attempt; no database or device execution.',
 harness=harness,harnessIndexSha256=sha(H/'index.json'),sourceIndexSha256=review['sourceIndexSha256'],targetsSha256=sha(H/'targets.json'),
 attempt=name,status=r['status'],counts=r['counts'],testSeconds=float(m.group(1)),elapsedSeconds=r['elapsedSeconds'],
 sourceFilesVerified=8098,frozenFilesVerified=8101,externalPinsVerified=159,actualOrigins=origins['summary'],
 bytecodeReadsRefused=len(origins['deniedBytecodeReads']),rawScratch=before['identity'],rawScratchFiles=0,rawScratchBytes=0,
 attemptFilesAcquired=len(rows),sourceAndCompilerDriverStable=True,actualOriginHashesRechecked=True,originalsAndCompleteCopiesRetained=True,
 sqliteConnections=0,qualificationPassed=False,requiredMatrixCoverageChecked=False,physicalMeasurementChecked=False)
with (OUT/'proof.json').open('x')as f:f.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
