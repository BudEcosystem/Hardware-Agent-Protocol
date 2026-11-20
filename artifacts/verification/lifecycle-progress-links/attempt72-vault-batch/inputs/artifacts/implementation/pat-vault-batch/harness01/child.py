"""Bounded normal imports and retained host transaction controls."""
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
from urllib.parse import unquote, urlsplit

HARNESS=Path(__file__).resolve().parent;BASE=HARNESS.parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01';PROJECT=SOURCE/'project'
ATTEMPT=Path(sys.argv[1]).resolve();SCRATCH=ATTEMPT/'scratch'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert ATTEMPT==HARNESS/'attempts/attempt01' and SCRATCH.is_dir()
assert sha(SOURCE/'index.json')=='71595be27f62d50424ec996a2fdd4b4cad1732f7315026d4009c5213cd657171'
inputs=read(SOURCE/'index.json')['files']
external_path=ROOT/'artifacts/verification/pat-native-worker-accounting/harness01/attempts/attempt01-accounting/external-before.json'
external=read(external_path)['files']
allowed={str((ROOT/row['path']).resolve()):row['sha256'] for row in inputs}
allowed.update({row['resolvedPath']:row['sha256'] for row in external})
for path,digest in allowed.items():assert sha(Path(path))==digest
stdlib=Path(sysconfig.get_path('stdlib')).resolve()
roots=read(ROOT/'artifacts/implementation/pat-native-supervisor/harness02/references/approved-external-roots.json')['roots']
sys.path[:0]=[str(PROJECT),str(PROJECT/'tests'),str(PROJECT/'supervisor')]+roots
os.environ['HMS_PRECOMMIT_TEST_ROOT']=str(SCRATCH/'new')
(SCRATCH/'new').mkdir(mode=0o700)
os.environ['HMS_BATCH_VAULT_TEST_ROOT']=str(SCRATCH/'batch')
os.environ['HMS_VAULT_TEST_ROOT']=str(SCRATCH/'single')
(SCRATCH/'batch').mkdir(mode=0o700)
(SCRATCH/'single').mkdir(mode=0o700)
resource.setrlimit(resource.RLIMIT_CPU,(45,45))
resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024*1024,8*1024*1024))
resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
denied=[];executed=set();connections=[]
def audit(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'):
        denied.append(event);raise RuntimeError('No network, processes or device services in these host controls')
    if event=='sqlite3.connect':
        name=args[0]
        path=Path(unquote(urlsplit(name).path) if type(name)is str and name.startswith('file:') else name).resolve()
        if not path.is_relative_to(SCRATCH):
            denied.append(event);raise RuntimeError('Database outside retained fresh test state')
        connections.append(str(path.relative_to(SCRATCH)))
    if event=='open':
        name,mode,flags=args
        if (type(mode)is str and any(c in mode for c in 'wax+')) or (type(flags)is int and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            if type(name)is not str or not Path(name).resolve().is_relative_to(ATTEMPT):
                denied.append(event);raise RuntimeError('Write outside fresh retained attempt')
        if type(name)is str and name.startswith('/dev/'):
            denied.append(event);raise RuntimeError('Device files unavailable')
        if type(name)is str and name.endswith('.pyc') and any(name.startswith(root+'/') for root in [str(PROJECT),*roots]):
            raise FileNotFoundError('Use verified selected source')
    if event in ('os.remove','os.rmdir','os.rename','os.mkdir','os.chmod','os.symlink','os.link'):
        count=2 if event in ('os.rename','os.symlink','os.link') else 1
        for name in args[:count]:
            if type(name)is not str or not Path(name).resolve().is_relative_to(ATTEMPT):
                denied.append(event);raise RuntimeError('Filesystem mutation outside attempt')
    if event=='exec':
        name=args[0].co_filename
        if name.startswith('<'):return
        path=Path(name).resolve()
        if path.is_relative_to(stdlib) and not {'site-packages','dist-packages'}.intersection(path.parts):return
        if str(path) not in allowed or sha(path)!=allowed[str(path)]:
            denied.append(event);raise RuntimeError('Unselected executed source')
        executed.add(str(path))
sys.addaudithook(audit)

selection=read(SOURCE/'test-selection.json')
ids=selection['ids']
assert len(ids)==len(set(ids))==60
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in ids)
assert suite.countTestCases()==60
log=io.StringIO();started=time.monotonic_ns()
result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
elapsed=time.monotonic_ns()-started
with (ATTEMPT/'tests.log').open('x') as stream:stream.write(log.getvalue())
with (ATTEMPT/'tests-before-verification.json').open('x') as stream:
    json.dump(dict(testsRun=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),
        ids=ids,postRunVerificationComplete=False),stream,indent=2);stream.write('\n')
from evidence_vault.contracts import identity as vault_identity
from evidence.contracts import identity as legacy_identity
pins=read(SOURCE/'identity-pins.json')
assert vault_identity()==pins['vault'] and legacy_identity()==pins['legacy']
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
    failureDetails=[dict(test=test.id(),trace=trace) for test,trace in result.failures],
    errorDetails=[dict(test=test.id(),trace=trace) for test,trace in result.errors],
    elapsedNanoseconds=elapsed,sourceIndexSha256=sha(SOURCE/'index.json'),childSha256=sha(Path(__file__)),
    externalReceiptSha256=sha(external_path),inputsUnchanged=True,deniedEvents=denied,
    executedSources=sorted(executed),selectedModuleOrigins=origins,sqliteConnections=connections,
    runtimeLegacyIdentity=pins['legacy'],runtimeVaultIdentity=pins['vault'],
    fullWorkerExecuted=False,catalogIntegrated=False,physicalObjectiveVerified=False,log=log.getvalue())
with (ATTEMPT/'child-result.json').open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps({key:receipt[key] for key in ('status','testsRun','failures','errors','inputsUnchanged','deniedEvents')}))
raise SystemExit(0 if receipt['status']=='passed' else 1)
