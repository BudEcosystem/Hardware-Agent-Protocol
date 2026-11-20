"""Independent read-only association, image, output and recovery evidence."""
import ast,fcntl,hashlib,json,os,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-document-validation';F=B/'results'/sys.argv[1];A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b):return 'sha256:'+hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
p=read(F/'proof.json');r=read(A/'result.json');assert r['status']=='passed' and r['childState']=='exited'
target=read(A/'harness/targets.json')['targets'][0];method=target.rsplit('.',1)[1];work=A/'scratch'/method;root=work/'supervisor'
database=root/'attempts.db';pin=sha(database);db=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
try:
 assert db.execute('SELECT count(*),sum(active) FROM qs_attempts').fetchone()==(1,0)
 request_raw,record_raw,returned_raw=db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchone()
finally:db.close()
assert sha(database)==pin
request=json.loads(request_raw);record=json.loads(record_raw);assert canonical(request)==request_raw and canonical(record)==record_raw
identifier=record['attemptId'];attempt=root/identifier;archive=record['archive'];assert record['state']=='archived'
assert record['requestDigest']==digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1\0'+request_raw)
assert archive['semanticQualificationVerified'] is False and archive['totalDiskQuotaEnforced'] is False and archive['unresolvedEffects'] is None
if returned_raw is not None:
 returned=json.loads(returned_raw);assert canonical(returned)==returned_raw and archive['returnDigest']==digest(returned_raw)
 assert (attempt/'worker-return.json').read_bytes()==returned_raw and returned['requestDigest']==record['requestDigest']
 assert returned['attemptId']==identifier and returned['bundleDigest']==request['bundleDigest']
else:returned=None;assert archive['returnDigest'] is None
leases=[]
original=Path(p['rawScratch']['path'])/method/'supervisor'
try:
 fd=os.open(original/'supervisor.owner',os.O_RDONLY|os.O_NOFOLLOW);leases.append(fd);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if record['lease'] is not None:
  fd=os.open(original/identifier/'writer.lease',os.O_RDONLY|os.O_NOFOLLOW);leases.append(fd);info=os.fstat(fd)
  assert record['lease']==dict(device=str(info.st_dev),inode=str(info.st_ino));fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  launch=read(attempt/'input.json');assert launch['attemptId']==identifier and launch['request']==request
  header=(attempt/'bundle/header.json').read_bytes();assert canonical(request['bundleHeader'])==header
  assert request['bundleDigest']==digest(b'HMS-PAT-IO-RUN-BUNDLE-v0.1\0'+header)
  for row in request['bundleHeader']['manifest']:
   f=attempt/'bundle'/row['path'];assert f.stat().st_size==row['bytes'] and sha(f)==row['sha256']
finally:
 for fd in leases:os.close(fd)
output=attempt/'output';closure=None;group=None
if returned:
 group=read(output/'result.json');assert returned['groupResultDigest']==digest((output/'result.json').read_bytes())
 assert group['status']==returned['status'] and group['matrixDigest']==request['bundleHeader']['matrixDigest']
 chain=hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0');files=[]
 def walk(folder):
  for f in sorted(folder.iterdir(),key=lambda p:p.name):
   assert not f.is_symlink()
   if f.is_dir():walk(f)
   else:
    row=dict(path=f.relative_to(output).as_posix(),bytes=f.stat().st_size,sha256=sha(f));chain.update(canonical(row)+b'\n');files.append(row)
 walk(output);closure=dict(fileCount=len(files),bytes=sum(v['bytes']for v in files),orderedDigest='sha256:'+chain.hexdigest())
 assert closure==archive['evidenceIntegrity'] and closure['bytes']<=20*1024*1024
image=root/('code-'+request['supervisorIdentity'][7:]);actual={};packages={}
if image.exists():
 project=A/'project';expected={}
 sources={*(project/'hms').rglob('*.py'),*(project/'schemas').glob('*.json'),*(project/'examples/wot').glob('*.json'),project/'research/protocols/wot-artifacts/td-schema-1.1.json',project/'protocol/endpoint/scenario-manifest.json'}
 for f in sources:expected[f.relative_to(project).as_posix()]=dict(bytes=f.stat().st_size,sha256=sha(f))
 tree=ast.parse((project/'supervisor/supervisor_contracts.py').read_bytes())
 names=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE_FILES'for t in n.targets)))
 supervisor_rows=[]
 for name in names:
  f=project/'supervisor'/name;expected['supervisor/'+name]=dict(bytes=f.stat().st_size,sha256=sha(f));supervisor_rows.append(dict(path=name,sha256=sha(f)))
 for row in read(A/'external-before.json')['files']:
  if 'package'in row:
   value=dict(bytes=row['bytes'],sha256=row['sha256']);assert row['path']not in packages or packages[row['path']]==value
   packages[row['path']]=value;expected['dependencies/'+row['path']]=value
 for f in image.rglob('*'):
  assert not f.is_symlink() and f.stat().st_mode&0o777==(0o700 if f.is_dir()else 0o600)
  if f.is_file():actual[f.relative_to(image).as_posix()]=dict(bytes=f.stat().st_size,sha256=sha(f))
 assert actual==expected
 runtime=hashlib.sha256(b''.join(canonical(dict(path=k,sha256=packages[k]['sha256']))+b'\n'for k in sorted(packages))).hexdigest()
 assert request['supervisorIdentity']==digest(b'HMS-PAT-QUALIFICATION-SUPERVISOR-v0.1\0'+canonical(dict(sources=supervisor_rows,worker=request['implementation'],runtimeFiles=len(packages),runtimeDigest='sha256:'+runtime)))
checks=read(work/'checks.json')if(work/'checks.json').exists()else read(work/'inspection/supervisor-checks.json')
summary=read(work/'independent-summary.json')if(work/'independent-summary.json').exists()else read(work/'inspection/summary.json')if(work/'inspection/summary.json').exists()else None
if summary:assert summary['independentOutcomeChecked'] is True and summary['qualificationPassed'] is False
crash=read(work/'prepared/crash-receipt.json')if(work/'prepared/crash-receipt.json').exists()else None
if crash:
 assert crash['hardExitCode']==91 and checks['phase']==crash['phase'] and checks['record']==record
 assert len(crash['launches'])==(0 if crash['phase'] in {'admitted','launching'}else 1)
 assert archive['transportComplete'] is (crash['phase']=='archived')
 if crash['phase']!='archived':assert archive['exitCode'] is None and archive['ownerRecovered'] is True
 assert checks['replayedWithoutRelaunch'] is True and checks['noStoredPidSignal'] is True
elif any(cls in target for cls in ('.IoPwmSupervisionTests.','.IoConfiguredProcessTests.','.IoAuthorityProcessTests.','.IoReservedProcessTests.')):
 assert checks['archive']==archive and archive['transportComplete'] is True and group['status']=='captured'
else:
 assert checks['record']==record
 if 'record_cutoff'in method:assert archive['transportComplete'] is True and group['status']=='failed'and checks['independentQualificationRefused'] is True
 else:assert archive['transportComplete'] is False
states=read(F/'state-audit.json')['groups'];effects=[sum(s['effects'][i]or 0 for g in states for s in g['states'])for i in range(3)]
report=dict(scope='Read-only original lease and retained request/input/output/image/control association; no PID-based authority or physical/service/quota attestation.',target=target,attemptId=identifier,history=record['history'],archive=archive,outputClosure=closure,codeImageFiles=len(actual),codeImageBytes=sum(v['bytes']for v in actual.values()),codeImageExactClosure=bool(actual),runtimeFiles=len(packages),originalLeaseFree=record['lease']is not None,ownerFree=True,ledgerUnchanged=True,groupStatus=group['status']if group else None,completedCases=len(group['cases'])if group else 0,states=sum(len(g['states'])for g in states),effects=dict(activations=effects[0],completed=effects[1],canceled=effects[2]),claims=sum(s['claims']for g in states for s in g['states']),owners=sum(s['owners']for g in states for s in g['states']),independentSummary=summary,crash=crash,qualificationPassed=False)
with(F/'process-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ('target','history','outputClosure','codeImageFiles','groupStatus','completedCases','states','effects','claims','owners')}))
