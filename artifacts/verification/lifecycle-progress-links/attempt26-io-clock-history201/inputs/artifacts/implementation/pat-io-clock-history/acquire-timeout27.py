"""Retain partial27-test evidence without treating missing child receipts as success."""
import hashlib,json,re,shutil,stat
from pathlib import Path
R=Path.cwd().resolve();B=R/'artifacts/implementation/pat-io-clock-history';H=B/'harness14';A=H/'attempts/attempt08-observation27';O=B/'results/attempt08-timeout27';O.mkdir()
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):assert p.is_file()and not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256']
def inventory(d):
 out=[]
 for p in sorted(d.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():out.append(dict(path=p.relative_to(d).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return out
def identity(p):
 s=p.lstat();assert stat.S_ISDIR(s.st_mode)
 return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
r=read(A/'result.json');assert r['status']=='timed_out'and r['currentPass']is False and r['childState']=='exited'and r['counts']is None
assert not Path('/proc/'+str(r['pid'])).exists()and r['timeoutSeconds']==180
assert {e['phase']for e in r['errors']}=={'execution','child-receipts'}
for row in read(H/'index.json')['files']:verify(H/row['path'],row)
for label,d,n in [('inputs',A/'project',8022),('frozen',R,8025),('harness',A/'harness',6)]:
 rows=read(A/(label+'-before.json'));assert rows==read(A/(label+'-after.json'))and len(rows)==n
 for row in rows:verify(d/row['path'],row)
external=read(A/'external-before.json');assert external==read(A/'external-after.json')and len(external['files'])==159
for row in external['files']:verify(Path(row['resolvedPath']),row)
raw=Path(r['scratchPath']);before=read(A/'raw-scratch-before.json');assert identity(raw)==before['identity']and identity(raw.parent)==before['parent']
assert inventory(raw)==inventory(A/'scratch')==read(A/'scratch-index.json')==[]
log=(A/'output.log').read_text();completed=re.findall(r'^test_[^\n]+ \.\.\. ok$',log,re.M);assert 'FAILED ('not in log and '\nOK\n'not in log
rows=inventory(A);shutil.copytree(A,O/'attempt');assert inventory(O/'attempt')==rows==inventory(A)
proof=dict(scope='Retained deadline failure; partial log is not a passing selection or complete origin receipt.',
 status=r['status'],counts=None,expectedTests=27,completedOkLines=len(completed),elapsedSeconds=r['elapsedSeconds'],
 childExited=True,exitCode=r['exitCode'],timeoutSeconds=180,errors=r['errors'],sourceInputsStable=True,externalPinsVerified=159,
 fullChildReceiptAvailable=False,completeActualOriginEvidence=False,attemptFilesAcquired=len(rows),rawScratch=before['identity'],rawScratchFiles=0,rawScratchBytes=0,
 qualificationPassed=False,originalsAndCompleteCopiesRetained=True)
with(O/'proof.json').open('x')as f:f.write(json.dumps(proof,indent=2)+'\n')
(O/'README.md').write_text('# Retained27-test timeout\n\nThe [partial log](attempt/output.log) has '+str(len(completed))+' completed `ok` lines before the\noriginal180-second child deadline. The owned child exited after termination.\nNo final test-return, complete origin or compiler/driver-after receipt exists;\nthis is a failed attempt, not a passing partial selection. See the [proof](proof.json).\n\nAll '+str(len(rows))+''' attempt files and the original empty raw root are retained. Frozen/project/
harness/external source inventories remained stable. The same27 exact methods
are subsequently split into14 and13 interleaved observation tests with no
source/test/bound changes. See the [combined results](../README.md).
''')
print(json.dumps(proof))
