"""One controlled aging run; the retained production/test sources are unchanged."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

LANE = Path(__file__).resolve().parent
ROOT = LANE.parents[2]
PRIOR = ROOT / 'artifacts/verification/endpoint-cli-observation-semantics'
INPUTS = PRIOR / 'inputs'
PINS = json.loads((PRIOR / 'input-pins.json').read_text())


def verify():
    for name, pin in PINS.items():
        data = (INPUTS / name).read_bytes()
        assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], name


verify()
sys.path[:0] = [str(INPUTS / 'tests'), str(INPUTS)]
import test_endpoint_cli
import test_multi_cli
test_multi_cli.ROOT = ROOT  # Collector output only; fixture/runtime stay isolated.


class AgedObservation(test_endpoint_cli.CompactCliRestartTests):
    def _cli_process(self, *arguments):
        if arguments == ('observe', 'sim:home-fan', 'value', '--max-age-ms', '10000',
                         '--evidence-kind', 'simulation'):
            self.assertNotIn('controlledAging', self.report)
            self.assertEqual(len(self.report['scenarios']), 1)
            scenario = self.report['scenarios'][0]
            self.assertEqual(scenario['completed']['executionState'], 'completed')
            self.assertFalse(scenario['completed']['resourceClaims'])
            self.assertEqual(scenario['firstReplay'], scenario['completed'])
            self.assertEqual(scenario['secondReplay'], scenario['completed'])
            self.assertEqual(len(self.relay.op_frames()), 1)
            self.report['controlledAging'] = {
                'requestedWaitSeconds': 11, 'started': self._times(),
                'opFramesBeforeWait': 1,
                'scope': 'One deliberate wait after first completion and both replays, immediately before unchanged final strict observation. No deadline, TTL, max-age or sample mutation.'}
            time.sleep(11)
            self.report['controlledAging']['finished'] = self._times()
            self.report['controlledAging']['opFramesAfterWait'] = len(self.relay.op_frames())
            self.assertEqual(len(self.relay.op_frames()), 1)
        return super()._cli_process(*arguments)


log = io.StringIO()
started = time.monotonic()
case = AgedObservation('test_three_native_scenarios_reconcile_after_SIGKILL_without_replaying_OP')
result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.TestSuite([case]))
verify()
trace = test_endpoint_cli.LAST_REPORT
checks = {}
if result.wasSuccessful():
    value = trace['cases'][case.id()]
    scenarios = value['scenarios']
    first = scenarios[0]
    checks = {'firstStrictOutcome': first['freshness']['strictOutcome'],
              'firstProjection': first['freshness']['projection'],
              'firstKnownAgeUpperBoundMs': first['freshness']['ageUpperBoundMs'],
              'forwardedOpCounts': [item['forwardedOpCount'] for item in scenarios],
              'otherFreshness': [item['freshness'] for item in scenarios[1:]],
              'allOriginalSampleTicksPreserved': all(item['observation']['acquisition']['ticksMs'] ==
                  item['completedResult']['output']['sampleTick'] for item in scenarios)}
    assert checks['firstStrictOutcome'] == 'OBSERVATION_STALE'
    assert checks['firstProjection'] == 'historical' and checks['firstKnownAgeUpperBoundMs'] > 10000
    assert checks['forwardedOpCounts'] == [1, 2, 3] and checks['allOriginalSampleTicksPreserved']
report = {'schema': 'hms-endpoint-cli-aged-observation-proof/1', 'tests': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
          'passed': result.wasSuccessful(), 'seconds': time.monotonic() - started,
          'inputCount': len(PINS), 'inputsUnchanged': True, 'checks': checks, 'trace': trace,
          'scope': 'Controlled aging demonstration, not reproduction of an earlier run timing. One artifact-only wait; original source and thresholds unchanged.'}
for name, data in [('tests.log', log.getvalue()), ('run.json', json.dumps(report, indent=2, sort_keys=True) + '\n')]:
    with (LANE / name).open('x') as output:
        output.write(data)
print(log.getvalue())
print(json.dumps({key: value for key, value in report.items() if key != 'trace'}, indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
