"""Run the nine inherited public contract tests on the exact isolated candidate."""
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import sys
import sysconfig
import time
import unittest

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2];STAGE=BASE/'implementation01';PROJECT=STAGE/'project'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert sha(STAGE/'index.json')=='387d33e2992d2862b1c21902b8de09195a56b569f52c3c3e04b84ce09b2d8849'
output=BASE/'contract-controls.json';assert not output.exists()
inputs=read(STAGE/'index.json')['files']
external_path=ROOT/'artifacts/verification/pat-native-worker-accounting/harness01/attempts/attempt01-accounting/external-before.json'
external=read(external_path)['files']
allowed={str((ROOT/row['path']).resolve()):row['sha256'] for row in inputs}
allowed.update({row['resolvedPath']:row['sha256'] for row in external})
for path,digest in allowed.items():assert sha(Path(path))==digest
stdlib=Path(sysconfig.get_path('stdlib')).resolve()
roots=read(ROOT/'artifacts/implementation/pat-native-supervisor/harness02/references/approved-external-roots.json')['roots']
sys.path[:0]=[str(PROJECT),str(PROJECT/'tests')]+roots
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
denied=[];executed=set()
def audit(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','sqlite3.connect'):
        denied.append(event);raise RuntimeError('Contract controls forbid execution/network/database effects')
    if event=='open':
        name,mode,flags=args
        if (type(mode)is str and any(c in mode for c in 'wax+')) or (type(flags)is int and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            if type(name)is not str or Path(name).resolve()!=output:
                denied.append(event);raise RuntimeError('Only one contract-control receipt may be written')
        if type(name)is str and name.endswith('.pyc') and any(name.startswith(root+'/') for root in [str(PROJECT),*roots]):
            raise FileNotFoundError('Use verified selected source, not bytecode')
    if event=='exec':
        name=args[0].co_filename
        if name.startswith('<'):return
        path=Path(name).resolve()
        if path.is_relative_to(stdlib) and not {'site-packages','dist-packages'}.intersection(path.parts):return
        if str(path) not in allowed or sha(path)!=allowed[str(path)]:
            denied.append(event);raise RuntimeError('Unselected executed source')
        executed.add(str(path))
sys.addaudithook(audit)
suite=unittest.defaultTestLoader.loadTestsFromName('test_contracts.ContractTests')
ids=[test.id() for test in suite];assert len(ids)==len(set(ids))==9
log=io.StringIO();started=time.monotonic_ns()
result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
import hms.contracts as contracts
assert contracts._fast_allowed()
for path,digest in allowed.items():assert sha(Path(path))==digest
origins=[]
for name,module in tuple(sys.modules.items()):
    origin=getattr(module,'__file__',None)
    if not origin:continue
    path=Path(origin).resolve()
    if str(path).startswith(str(PROJECT)+'/') or any(str(path).startswith(root+'/') for root in roots):
        assert str(path) in allowed and sha(path)==allowed[str(path)]
        origins.append(dict(module=name,path=str(path),sha256=allowed[str(path)]))
receipt=dict(status='passed' if result.wasSuccessful() and not denied else 'failed',testsRun=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),
    expectedFailures=len(result.expectedFailures),unexpectedSuccesses=len(result.unexpectedSuccesses),ids=ids,
    elapsedNanoseconds=time.monotonic_ns()-started,sourceIndexSha256=sha(STAGE/'index.json'),
    runnerSha256=sha(Path(__file__)),externalReceiptSha256=sha(external_path),inputsUnchanged=True,
    deniedEvents=denied,executedSources=sorted(executed),selectedModuleOrigins=origins,integerPathEnabled=True,
    fullWorkerExecuted=False,physicalObjectiveVerified=False,log=log.getvalue())
with output.open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps({key:receipt[key] for key in ('status','testsRun','failures','errors','integerPathEnabled','inputsUnchanged','deniedEvents')}))
raise SystemExit(0 if receipt['status']=='passed' else 1)
