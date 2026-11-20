"""Read retained configured-worker identity joins without importing project code."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-service-authority';F=B/'results'/sys.argv[1];A=F/'attempt'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(domain,value):return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(value)).hexdigest()
proof=read(F/'proof.json');process=read(F/'process-audit.json')
assert proof['status']=='passed'and process['completedCases']==30 and process['claims']==process['owners']==0
method=read(A/'harness/targets.json')['targets'][0].rsplit('.',1)[1];work=A/'scratch'/method
config=read(work/'service-configuration.json');pin=read(work/'service-pin.json');request_id=read(work/'service-request-digest.json')
for name,value in [('service-configuration.json',config),('service-pin.json',pin),('service-request-digest.json',request_id)]:
 assert (work/name).read_bytes()==canonical(value)
database=work/'supervisor/attempts.db';before=sha(database)
assert not any(database.with_name(database.name+suffix).exists()for suffix in ('-wal','-journal','-shm'))
db=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)
try:rows=db.execute('SELECT request,record FROM qs_attempts').fetchall()
finally:db.close()
assert len(rows)==1 and sha(database)==before
request,record=map(json.loads,rows[0]);assert tuple(map(canonical,(request,record)))==rows[0]
assert request_id['requestDigest']==record['requestDigest']==digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1',request)
assert config['profile']=='hms.pat.io-simulation-services/0.1'and pin['profile']=='hms.pat.io-service-pin/0.2'
assert config['policy']==pin['policy']=='hms.pat.eval.sqlite-finite-io-combined/0.3'
assert pin['configurationDigest']==request['context']['configurationDigest']==digest(b'HMS-PAT-IO-AUTHORITY-SERVICE-CONFIG-v0.1',dict(authorityId=pin['authorityId'],configuration=config))
assert config['revision']==pin['configurationRevision']==request['context']['configurationRevision']
assert config['evaluatorId']==pin['evaluatorId']==request['context']['evaluatorId']
assert config['deployment']==pin['deployment']==request['context']['deployment']
assert pin['implementation']==request['implementation']and pin['supervisorIdentity']==request['supervisorIdentity']
assert request['limits']==config['supervisorLimits']and request['groupLimits']==config['groupLimits']
root=work/'supervisor'/record['attemptId'];input_root=root/'bundle/inputs'
candidate=read(input_root/'candidate.json');assignment=next(row for row in config['qualifications']if row['artifactDigest']==digest(b'HMS-PAT-JCS-SHA256-v0.1',candidate))
descriptor=read(input_root/'descriptor.json');assert set(assignment['roleInstances'])==set(candidate['roles'])
assert list(assignment['roleInstances'].values())==[descriptor['binding']['instanceId']]
installation=read(input_root/'installation.json')
assert config['installationDigest']==pin['installationDigest']==digest(b'HMS-SYNTHETIC-IO-INSTALLATION-v1',installation)
actors=read(input_root/'bindings.json');assert set(actors)==set(config['challengeBindings'])
for role,choice in config['challengeBindings'].items():
 actual=actors[role];assert actual['actionId']==choice['actionId']and actual['descriptor']['binding']['instanceId']==choice['instanceId']
 registrations={row['instanceId']:row for row in config['registrations']};registration=registrations[choice['instanceId']]
 assert actual['descriptor']['argumentMetadata']==registration['argumentMetadata']and actual['descriptor']['binding']['typeDigest']==registration['typeDigest']
image=work/'supervisor'/('code-'+request['supervisorIdentity'][7:]);source=image/'supervisor/io_services.py'
assert source.read_bytes()==(A/'project/supervisor/io_services.py').read_bytes()and process['codeImageExactClosure']and process['codeImageFiles']==258
checks=read(work/'inspection/supervisor-checks.json')
assert checks['exactReplayBeforeAndAfterReopen']and checks['changedSameKeyRefused']and checks['oneWorkerLaunched']and checks['preLaunchInputsMatched']
report=dict(scope='Independent authority-bound configuration/pin/descriptor/request/image joins; separate authority audit validates committed history and actual registry snapshots. No public mount or physical qualification.',configurationDigest=pin['configurationDigest'],configurationRevision=config['revision'],evaluatorId=config['evaluatorId'],requestDigest=request_id['requestDigest'],configuredArtifact=assignment['artifactDigest'],roleInstances=assignment['roleInstances'],registrations=len(config['registrations']),challengeActors=len(actors),serviceSourceSha256=sha(source),sourceImageFiles=258,completeCases=30,ledgerUnchanged=True,configurationPersistedByAuthorityStore=True,oneOriginalWorker=True,exactReplayBeforeAndAfterReopen=True,changedSameKeyRefused=True,qualificationPassed=False)
with(F/'authority-service-audit.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
