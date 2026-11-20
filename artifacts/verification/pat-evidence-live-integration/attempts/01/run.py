"""Current evidence-library integration proof; fresh original worker results retained."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import sys
import tempfile
import time
import unittest

ROOT = Path.cwd()
BASE = Path(__file__).resolve().parent / 'attempts' / sys.argv[1]
BASE.mkdir(exist_ok=False, parents=True)
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
from scripts.check_runtime import input_paths, compiler_identity


def records(root):
    return [{'path': str(p.relative_to(root)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
             'bytes': p.stat().st_size} for p in input_paths(root)]


before = records(ROOT)
for row in before:
    destination = BASE / 'inputs' / row['path']
    destination.parent.mkdir(exist_ok=True, parents=True)
    shutil.copy2(ROOT / row['path'], destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == row['sha256']
(BASE / 'inputs-before.json').write_text(json.dumps(before, indent=2) + '\n')
sys.path[:0] = [str(BASE / 'inputs/tests'), str(BASE / 'inputs')]
identity = compiler_identity()
(BASE / 'compiler-before.json').write_text(json.dumps(identity, indent=2) + '\n')
names = ['test_pat_simulation_evidence', 'test_pat_evidence_hook', 'test_pat_evaluation_integrity']
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
import test_pat_simulation_evidence as worker_tests
scratch = tempfile.TemporaryDirectory(prefix='hms-pat-evidence-integration-')
worker_tests.RETAIN_OUTPUT_ROOT = scratch.name
started = time.monotonic()
try:
    with (BASE / 'tests.log').open('w') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    seconds = time.monotonic() - started
    # Preserve the exact output and scratch bytes, including negative/unknown
    # trials, before removing only the original temporary duplicate.
    shutil.copytree(scratch.name, BASE / 'worker-output')
    (BASE / 'worker-report.json').write_text(json.dumps(worker_tests.LAST_REPORT, indent=2) + '\n')
finally:
    worker_tests.RETAIN_OUTPUT_ROOT = None
    scratch.cleanup()
after = records(BASE / 'inputs')
after_identity = compiler_identity()
(BASE / 'inputs-after.json').write_text(json.dumps(after, indent=2) + '\n')
(BASE / 'compiler-after.json').write_text(json.dumps(after_identity, indent=2) + '\n')
(BASE / 'run.py').write_bytes(Path(__file__).read_bytes())
report = {'schema': 'hms-current-pat-evidence-integration/1', 'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope': 'Original local Runtime/SQLite tests in exact copied inputs. Worker evidence and scratch databases retained. No hardware, model, acquired controller or public service execution.',
    'command': 'python3 -B artifacts/verification/pat-evidence-live-integration/run.py ' + sys.argv[1], 'modules': names,
    'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
    'seconds': seconds, 'inputs': len(before), 'inputsStable': before == after, 'compilerIdentityStable': identity == after_identity,
    'passed': result.wasSuccessful() and not result.skipped and before == after and identity == after_identity,
    'failureDetails': [{'test': str(t), 'detail': d} for t, d in result.failures],
    'errorDetails': [{'test': str(t), 'detail': d} for t, d in result.errors],
    'workerOriginalExecutionDirectory': scratch.name, 'retainedOutputDirectory': str(BASE / 'worker-output'),
    'runnerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(BASE / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in {'failureDetails', 'errorDetails', 'modules'}}))
raise SystemExit(0 if report['passed'] else 1)
