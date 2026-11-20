"""Single bounded selected scope, retained scratch, no qualification worker."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import sysconfig
import traceback
import unittest

for limit,value in ((resource.RLIMIT_FSIZE,16*1024*1024),(resource.RLIMIT_CPU,40),
    (resource.RLIMIT_AS,512*1024*1024),(resource.RLIMIT_NOFILE,128)):
    resource.setrlimit(limit,(value,value))
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
config=json.loads(Path(sys.argv[1]).read_bytes())
project=Path(config['project']);scratch=Path(config['scratch']);out=Path(config['out'])
sys.path[:0]=[str(project),str(project/'tests')]+config['externalRoots']
expected={str(project/r['path']):r['sha256'] for r in config['inputs']}
external={r['resolvedPath']:r['sha256'] for r in config['externalInputs']}
stdlib=Path(sysconfig.get_path('stdlib')).resolve()
origins=set();databases=[];launches=[];denied=[]
current=None

def guard(event,args):
    if event=='exec':
        origin=args[0].co_filename
        if not origin.startswith('<'):
            path=Path(origin).resolve();name=str(path)
            if name in expected or name in external:
                assert hashlib.sha256(path.read_bytes()).hexdigest()==expected.get(name,external.get(name))
            elif not path.is_relative_to(stdlib) or {'site-packages','dist-packages'}.intersection(path.parts):
                denied.append(name);raise AssertionError('Unacquired executable origin')
            origins.add(name)
    if event=='open' and isinstance(args[0],(str,bytes)) and os.fsdecode(args[0]).endswith('.pyc'):
        raise FileNotFoundError('Exact acquired source required')
    if event=='sqlite3.connect':
        path=Path(os.fsdecode(args[0])).resolve()
        assert path.is_relative_to(scratch),'Database outside retained scratch'
        databases.append(dict(test=current,path=str(path)))
    if event=='subprocess.Popen':
        executable,argv,cwd,env=args
        assert current=='test_storage_bindings.StorageBindingTests.test_inherited_writer_lease_survives_control_owner_loss'
        assert argv==[sys.executable,'-I','-B','-c',"import sys; print('held',flush=True); sys.stdin.buffer.read(1)"]
        assert executable==sys.executable and not launches
        launches.append(dict(test=current,argv=argv))
    if event.startswith('socket.') or event in {'os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        denied.append(event);raise AssertionError('Effect outside control scope')

sys.addaudithook(guard)
errors=[];result=None;executed=[]
try:
    suite=unittest.defaultTestLoader.loadTestsFromNames(config['targets'])
    assert not unittest.defaultTestLoader.errors
    def flatten(value):
        if isinstance(value,unittest.TestSuite):return [i for test in value for i in flatten(test)]
        return [value.id()]
    assert flatten(suite)==config['targets']
    class Result(unittest.TextTestResult):
        def startTest(self,test):
            global current
            current=test.id();executed.append(current);super().startTest(test)
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result,failfast=True).run(suite)
except BaseException as error:
    errors.append(dict(type=type(error).__name__,message=str(error)));traceback.print_exc()
counts=None if result is None else dict(testsRun=result.testsRun,failures=len(result.failures),errors=len(result.errors),
    skips=len(result.skipped),expectedFailures=len(result.expectedFailures),unexpectedSuccesses=len(result.unexpectedSuccesses))
passed=not errors and not denied and executed==config['targets'] and counts is not None and counts['testsRun']==len(executed) and all(v==0 for k,v in counts.items() if k!='testsRun')
(out/'child-result.json').write_text(json.dumps(dict(passed=passed,counts=counts,errors=errors,executed=executed,
    origins=sorted(origins),databaseOpens=databases,diagnosticLeaseChildren=launches,denied=denied,
    quotaEnforced=False,physicalExecution=False),indent=2)+'\n')
raise SystemExit(0 if passed else 1)
