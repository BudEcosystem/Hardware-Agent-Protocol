"""Run only pure observer controls, with process/network/database execution vetoed."""
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time
import unittest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
sys.dont_write_bytecode = True
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert not (BASE / 'controls.json').exists()
expected = json.loads((BASE / 'controls-inputs.json').read_bytes())
def inventory():
    result = []
    for name in ('observer.py', 'test_observer.py', 'test_composition.py', 'run-controls.py', 'harness01/attempt_child.py', 'harness01/references/original-attempt_child.py'):
        body = (BASE / name).read_bytes()
        result.append(dict(path=name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
    return result
assert inventory() == expected['files']
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
denied = []
def audit(event, args):
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.exec',
            'os.fork', 'os.forkpty', 'os.posix_spawn', 'sqlite3.connect'):
        denied.append(event)
        raise RuntimeError('Pure observer controls forbid process/network/database execution')
sys.addaudithook(audit)
suite = unittest.TestSuite(list(unittest.defaultTestLoader.loadTestsFromName('test_observer.ObserverTests')) + list(unittest.defaultTestLoader.loadTestsFromName('test_composition.CompositionTests')))
ids = [test.id() for test in suite]
assert len(ids) == len(set(ids)) == 21
log = io.StringIO()
started = time.monotonic_ns()
result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
elapsed = time.monotonic_ns() - started
after = inventory()
text = log.getvalue()
assert len(text.encode()) <= 65536
receipt = dict(status='passed' if result.wasSuccessful() else 'failed',
    testsRun=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skips=len(result.skipped), expectedFailures=len(result.expectedFailures),
    unexpectedSuccesses=len(result.unexpectedSuccesses), ids=ids, elapsedNanoseconds=elapsed,
    before=expected['files'], after=after, sourceUnchanged=after == expected['files'],
    deniedEvents=denied, realWorkerExecuted=False, log=text)
with (BASE / 'controls.json').open('x') as stream:
    json.dump(receipt, stream, indent=2); stream.write('\n')
print(json.dumps({key: receipt[key] for key in ('status', 'testsRun', 'failures', 'errors', 'sourceUnchanged', 'deniedEvents')}))
raise SystemExit(0 if result.wasSuccessful() and after == expected['files'] and not denied else 1)
