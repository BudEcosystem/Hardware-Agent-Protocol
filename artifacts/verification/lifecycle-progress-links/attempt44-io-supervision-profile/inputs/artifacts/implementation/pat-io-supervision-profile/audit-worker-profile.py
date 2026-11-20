"""Read-only binding of interrupted diagnostic profile to exact source/attempt."""
import ast,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-profile';F=B/'results/attempt02-profiled-worker-failed';A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(b):return 'sha256:'+hashlib.sha256(b).hexdigest()
proof=read(F/'proof.json');assert proof['status']=='failed'and proof['counts']['failures']==1
work=next((A/'scratch').iterdir());root=work/'supervisor';database=root/'attempts.db';pin=sha(database);db=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
try:
 assert db.execute('SELECT count(*),sum(active) FROM qs_attempts').fetchone()==(1,0)
 request_raw,record_raw,returned=db.execute('SELECT request,record,return_bytes FROM qs_attempts').fetchone()
finally:db.close()
assert sha(database)==pin and returned is None
request=json.loads(request_raw);record=json.loads(record_raw);identifier=record['attemptId'];attempt=root/identifier;archive=record['archive']
assert canonical(request)==request_raw and canonical(record)==record_raw and record['state']=='archived'
assert archive['supervisorReason']=='SUPERVISOR_DEADLINE'and archive['exitCode']==-15 and archive['ownerRecovered']is False
assert archive['transportComplete']is False and archive['semanticQualificationVerified']is False and archive['unresolvedEffects']is None
assert request['groupLimits']['maxWallMs']==60000 and request['groupLimits']['maxCases']==32
assert read(attempt/'input.json')['request']==request and (attempt/'bundle/header.json').read_bytes()==canonical(request['bundleHeader'])
assert record['requestDigest']==digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1\0'+request_raw)
for row in request['bundleHeader']['manifest']:
 p=attempt/'bundle'/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
profile=read(attempt/'worker-profile.json');assert profile['reason']=='SIGTERM'and profile['profile']=='hms.diagnostic.io-worker-profile/0.1'
assert (attempt/'worker-profile.json').read_bytes()==canonical(profile)and (attempt/'worker-profile.json').stat().st_size<=65536
assert profile['totalFunctions']<=8192 and len(profile['top40'])==len(profile['top40Self'])==40
for row in profile['top40']+profile['top40Self']:
 assert len(row['label'])<=512 and all(type(v)is int and v>=0 for k,v in row.items()if k!='label')
image=root/('code-'+request['supervisorIdentity'][7:]);project=A/'project';expected={};packages={}
sources={*(project/'hms').rglob('*.py'),*(project/'schemas').glob('*.json'),*(project/'examples/wot').glob('*.json'),project/'research/protocols/wot-artifacts/td-schema-1.1.json',project/'protocol/endpoint/scenario-manifest.json'}
for p in sources:expected[p.relative_to(project).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
tree=ast.parse((project/'supervisor/supervisor_contracts.py').read_bytes());names=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SOURCE_FILES'for t in n.targets)));supervisor_rows=[]
for name in names:
 p=project/'supervisor'/name;expected['supervisor/'+name]=dict(bytes=p.stat().st_size,sha256=sha(p));supervisor_rows.append(dict(path=name,sha256=sha(p)))
for row in read(A/'external-before.json')['files']:
 if 'package'in row:
  value=dict(bytes=row['bytes'],sha256=row['sha256']);assert row['path']not in packages or packages[row['path']]==value
  packages[row['path']]=value;expected['dependencies/'+row['path']]=value
actual={}
for p in image.rglob('*'):
 assert not p.is_symlink()and p.stat().st_mode&0o777==(0o700 if p.is_dir()else 0o600)
 if p.is_file():actual[p.relative_to(image).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
assert actual==expected
runtime=hashlib.sha256(b''.join(canonical(dict(path=k,sha256=packages[k]['sha256']))+b'\n'for k in sorted(packages))).hexdigest()
assert request['supervisorIdentity']==digest(b'HMS-PAT-QUALIFICATION-SUPERVISOR-v0.1\0'+canonical(dict(sources=supervisor_rows,worker=request['implementation'],runtimeFiles=len(packages),runtimeDigest='sha256:'+runtime)))
quiescence=read(A/'writer-quiescence.json');assert quiescence['ownerQuiescent']and quiescence['records'][0]['writerQuiescent']
output=attempt/'output';assert not(output/'result.json').exists();states=read(F/'state-audit.json')['groups'][0]['states'];complete=[s for s in states if s.get('inspected',True)]
report=dict(scope='Interrupted diagnostic source/input/profile/attempt association; instrumented timing is not benchmark, complete-group or physical qualification.',attemptId=identifier,history=record['history'],archive=archive,profileSha256=sha(attempt/'worker-profile.json'),profileBytes=(attempt/'worker-profile.json').stat().st_size,sourceIdentity=request['supervisorIdentity'],codeImageExactClosure=True,codeImageFiles=len(actual),codeImageBytes=sum(v['bytes']for v in actual.values()),runtimeFiles=len(packages),ledgerUnchanged=True,writerQuiescence=quiescence,retainedCaseDirectories=len(list(output.glob('case-*'))),retainedCaseManifests=len(list(output.glob('case-*/manifest.json'))),states=len(states),completeStatePairs=len(complete),incompleteStates=[s for s in states if not s.get('inspected',True)],observedEffectsInCompletePairs=dict(zip(('activations','completed','canceled'),[sum(s['effects'][i]or 0 for s in complete)for i in range(3)])),observedClaimsInCompletePairs=sum(s['claims']for s in complete),observedOwnersInCompletePairs=sum(s['owners']for s in complete),aggregateUnresolvedEffects=None,qualificationPassed=False)
with(F/'worker-profile-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ('history','profileBytes','codeImageFiles','retainedCaseDirectories','retainedCaseManifests','completeStatePairs','observedEffectsInCompletePairs','aggregateUnresolvedEffects')}))
