"""Run only an immutable copied worker test input tree; retain actual outputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest

attempt = Path(sys.argv[1]).resolve()
inputs = attempt / 'inputs'
sys.dont_write_bytecode = True
sys.path.insert(0, str(inputs))
before = json.loads((attempt / 'inputs-before.json').read_text())
def stable():
    return all(hashlib.sha256((inputs / row['path']).read_bytes()).hexdigest() == row['sha256'] for row in before)
assert stable()
spec = importlib.util.spec_from_file_location('test_pat_simulation_worker', inputs / 'tests/test_pat_simulation_worker.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
(attempt / 'worker-output').mkdir(mode=0o700)
module.RETAIN_OUTPUT_ROOT = attempt / 'worker-output'
started = time.monotonic()
with (attempt / 'tests.txt').open('w') as output:
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
after = stable()
imports = {key: str(value.__file__) for key,value in sys.modules.items() if key.startswith('hms') and getattr(value,'__file__',None)}
assert all(path.startswith(str(inputs) + '/') for path in imports.values())
receipt = {'schema':'hms-pat-worker-tests/1','tests':result.testsRun,'failures':len(result.failures),
    'errors':len(result.errors),'skips':len(result.skipped),'passed':result.wasSuccessful() and after,
    'seconds':time.monotonic()-started,'inputCount':len(before),'inputsStable':after,'imports':imports,
    'report':module.LAST_REPORT,'scope':'Original copied host SQLite simulations; no live authority, hardware, models or acquired controllers.'}
(attempt / 'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({key:receipt[key] for key in ('tests','failures','errors','passed','seconds','inputsStable')}))
raise SystemExit(0 if receipt['passed'] else 1)
