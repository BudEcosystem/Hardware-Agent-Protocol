"""Reproduce only the controlled observer and migrated transport test scopes."""
from pathlib import Path
import datetime
import hashlib
import json
import platform
import sqlite3
import sys
import time
import unittest

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
GROUPS = {
    'controlled': ['test_endpoint_cli.ReadOnlyObserverTests'],
    'transport': ['test_endpoint_cli.CompactCliRestartTests', 'test_multi_cli.MultiCliTests',
                  'test_procedure_transport.ProcedureTransportTests', 'test_runtime_ipc.RuntimeIpc'],
}
label = sys.argv[1]
assert label in GROUPS
output = HERE / label
output.mkdir(exist_ok=False)
inputs = json.loads((HERE / 'inputs-before.json').read_text())['sources']
initial = {item['path']: hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() for item in inputs}
assert all(initial[item['path']] == item['sha256'] for item in inputs), 'source drift before run'
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
start = time.monotonic()
record = {'schema':'hms-shared-sqlite-observer-focused/1', 'group':label,
          'command':'python3 -B artifacts/verification/shared-sqlite-observer/after/run_focused.py ' + label,
          'startedAtUtc':started, 'names':GROUPS[label], 'status':'running',
          'environment':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'platform':platform.platform()},
          'scope':'Original local transport simulations and controlled read-only SQLite tests; no hardware, operation retry changes, deadline extension, timing or availability qualification.'}
(output / 'result.json').write_text(json.dumps(record,indent=2)+'\n')
class Tee:
    def __init__(self, target): self.target = target
    def write(self, value):
        self.target.write(value); self.target.flush(); sys.stdout.write(value); sys.stdout.flush()
    def flush(self): self.target.flush(); sys.stdout.flush()
suite = unittest.defaultTestLoader.loadTestsFromNames(GROUPS[label])
with (output / 'tests.txt').open('w') as log:
    result = unittest.TextTestRunner(stream=Tee(log), verbosity=2).run(suite)
current = {item['path']: hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() for item in inputs}
(output / 'inputs-after.json').write_text(json.dumps(current,indent=2)+'\n')
reports = {}
for module in ('test_endpoint_cli','test_multi_cli','test_procedure_transport','test_runtime_ipc'):
    loaded = sys.modules.get(module)
    if loaded is not None:
        reports[module] = getattr(loaded,'LAST_REPORT',None)
(output / 'reports.json').write_text(json.dumps(reports,indent=2)+'\n')
record.update(status='complete', finishedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              elapsedSeconds=time.monotonic()-start, tests=result.testsRun, failures=len(result.failures),
              errors=len(result.errors), skipped=len(result.skipped),
              failureDetails=[{'test':str(test),'detail':detail} for test,detail in result.failures],
              errorDetails=[{'test':str(test),'detail':detail} for test,detail in result.errors],
              skipDetails=[{'test':str(test),'reason':reason} for test,reason in result.skipped],
              inputsStable=initial==current, sourceCount=len(inputs),
              passed=result.wasSuccessful() and not result.skipped and initial==current)
(output / 'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({key:record[key] for key in ('group','tests','failures','errors','skipped','inputsStable','passed','elapsedSeconds')}))
raise SystemExit(0 if record['passed'] else 1)
