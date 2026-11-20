"""Run the retained targeted tests using only the copied source tree."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

LANE = Path(__file__).resolve().parent
ROOT = LANE / 'inputs'
PINS = json.loads((LANE / 'input-pins.json').read_text())


def verify():
    for name, value in PINS.items():
        data = (ROOT / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == value['sha256'], name
        assert len(data) == value['bytes'], name


verify()
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
import test_compact_admission

for name, module in list(sys.modules.items()):
    if name.startswith(('hms', 'protocol.')) or name in {'test_compact_admission', 'test_multi_adapter'}:
        path = getattr(module, '__file__', None)
        if path is not None:
            assert Path(path).resolve().is_relative_to(ROOT), (name, path)

started = time.monotonic()
log = io.StringIO()
suite = unittest.defaultTestLoader.loadTestsFromModule(test_compact_admission)
result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
verify()
report = {'schema': 'hms-compact-admission-proof/1', 'tests': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'passed': result.wasSuccessful(),
          'seconds': time.monotonic() - started, 'frozenInputsUnchanged': True,
          'inputCount': len(PINS), 'trace': test_compact_admission.LAST_REPORT}
for name, data in [('run.log', log.getvalue()), ('run.json', json.dumps(report, indent=2, sort_keys=True) + '\n')]:
    with (LANE / name).open('x') as output:
        output.write(data)
print(log.getvalue())
print(json.dumps({key: value for key, value in report.items() if key != 'trace'}, indent=2, sort_keys=True))
raise SystemExit(0 if result.wasSuccessful() else 1)
