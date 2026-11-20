"""Original probe test entry; invoked only by the released outer harness."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import traceback

config=json.loads(Path(sys.argv[1]).read_text())
source=Path(config['source']).resolve();out=Path(config['attempt']).resolve()
sys.path[:0]=[str(source/'src')]+config['externalRoots']
os.environ['PROBE_INPUT_ROOT']=str(source);os.environ['PROBE_CASE_ROOT']=str(out/'cases')
(out/'cases').mkdir()
executed=set(); errors=[];result=None


def audit(event,args):
    if event.startswith('socket.'):raise RuntimeError('Original bookkeeping probes forbid network')
    if event=='exec':executed.add(args[0].co_filename)


def interrupt(_signal,_frame):raise KeyboardInterrupt('outer probe harness requested stop')
sys.addaudithook(audit);signal.signal(signal.SIGTERM,interrupt)
try:
    import unittest
    import test_harness_probes
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_harness_probes)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
except BaseException as exc:
    errors.append({'type':type(exc).__name__,'message':str(exc)[:4096]});traceback.print_exc()
finally:
    origins=[]
    for name,module in sorted(sys.modules.items()):
        origin=getattr(module,'__file__',None)
        if origin and Path(origin).is_file():
            path=Path(origin).resolve()
            origins.append({'module':name,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'kind':'copied_input' if path.is_relative_to(source) else 'selected_external_or_stdlib_actual_file'})
    report={'testsRun':result.testsRun if result else None,'failures':len(result.failures) if result else None,
        'errors':len(result.errors) if result else None,'skips':len(result.skipped) if result else None,
        'expectedFailures':len(result.expectedFailures) if result else None,
        'unexpectedSuccesses':len(result.unexpectedSuccesses) if result else None,'entryErrors':errors}
    (out/'test-return.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'actual-origins.json').write_text(json.dumps({'modules':origins,'executedCodeOrigins':sorted(executed),
        'scope':'Actual origins, not full pre-execution stdlib/cache/shared-library attestation.'},indent=2)+'\n')
passed=(result is not None and result.testsRun>0 and result.wasSuccessful() and not result.skipped and not result.expectedFailures and not errors)
raise SystemExit(0 if passed else 1)
