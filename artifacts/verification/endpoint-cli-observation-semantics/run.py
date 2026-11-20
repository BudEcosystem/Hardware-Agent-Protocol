"""Seven scoped tests against the retained source closure; no broad rerun."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

LANE = Path(__file__).resolve().parent
ROOT = LANE.parents[2]
INPUTS = LANE / 'inputs'
PINS = json.loads((LANE / 'input-pins.json').read_text())


def verify():
    for name, pin in PINS.items():
        data = (INPUTS / name).read_bytes()
        assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], name


verify()
sys.path[:0] = [str(INPUTS / 'tests'), str(INPUTS)]
import test_endpoint_cli
import test_endpoint_binding
import test_multi_cli
test_multi_cli.ROOT = ROOT  # Existing capture output only; execution stays isolated.
for name, module in list(sys.modules.items()):
    if name.startswith(('hms', 'protocol.')) or name in {
            'test_endpoint_cli', 'test_endpoint_binding', 'test_multi_cli', 'test_multi_adapter'}:
        path = getattr(module, '__file__', None)
        if path:
            assert Path(path).resolve().is_relative_to(INPUTS), (name, path)

suite = unittest.TestSuite([
    test_endpoint_cli.CompactCliRestartTests(
        'test_three_native_scenarios_reconcile_after_SIGKILL_without_replaying_OP'),
    unittest.defaultTestLoader.loadTestsFromTestCase(test_endpoint_cli.ReadOnlyObserverTests),
    test_endpoint_binding.CompactBindingTests(
        'test_completed_observation_keeps_original_sample_age_on_query_and_restart')])
assert suite.countTestCases() == 7
log = io.StringIO()
started = time.monotonic()
result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
verify()
report = {'schema': 'hms-endpoint-cli-observation-semantics-proof/1', 'tests': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
          'passed': result.wasSuccessful(), 'seconds': time.monotonic() - started,
          'inputsUnchanged': True, 'inputCount': len(PINS), 'trace': test_endpoint_cli.LAST_REPORT}
for name, data in [('tests.log', log.getvalue()), ('run.json', json.dumps(report, indent=2, sort_keys=True) + '\n')]:
    with (LANE / name).open('x') as output:
        output.write(data)
print(log.getvalue())
print(json.dumps({key: value for key, value in report.items() if key != 'trace'}, indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
