"""Controlled capture selfcheck or one unchanged real endpoint-CLI test."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import time
import unittest
from unittest.mock import patch

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
import test_endpoint_cli as endpoint
import tests.test_endpoint_cli as endpoint_package
import test_multi_cli as captures
from protocol.serial.frame import Decoder

# Execution still uses the copied source/binary tree. Only the existing failure
# collector's output root is redirected to the repository artifact area, so its
# root-relative manifests remain usable by the main audit.
captures.ROOT = ROOT
for name, module in list(sys.modules.items()):
    if name.startswith(('hms', 'protocol.')) or name in {
            'test_endpoint_cli', 'tests.test_endpoint_cli', 'test_multi_cli', 'test_multi_adapter'}:
        path = getattr(module, '__file__', None)
        if path:
            assert Path(path).resolve().is_relative_to(INPUTS), (name, path)


def decode(raw):
    decoder, frames = Decoder(), []
    for byte in raw:
        item = decoder.feed(byte)
        if item and item[0] == 'frame':
            frames.append(item[1])
    assert len(frames) == 1
    return frames[0]


mode = sys.argv[1]
label = sys.argv[2] if len(sys.argv) == 3 else mode
assert label.replace('-', '').isalnum()
log = io.StringIO()
started = time.monotonic()
extra = {}
if mode == 'selfcheck':
    # Copy original previously retained HELLO bytes into the diagnostic relay
    # lists; no endpoint is executed or contacted in this controlled selfcheck.
    evidence = ROOT / 'artifacts/verification/compact-availability-before/probe-output/test_baseline_fresh_admission/initial.db'
    with sqlite3.connect(evidence.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        tx = db.execute("SELECT wire FROM ep_packets WHERE direction='tx' ORDER BY id LIMIT 1").fetchone()[0]
        rx = db.execute("SELECT wire FROM ep_packets WHERE direction='rx' ORDER BY id LIMIT 1").fetchone()[0]
    extra['retainedRawInput'] = {'path': str(evidence.relative_to(ROOT)),
                               'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}

    class FixtureStub:
        returncode = None
        def communicate(self, timeout=None):
            self.returncode = 0
            return b'', b''

    class ControlledCapture(endpoint.CompactCliRestartTests):
        failure_stage = 'test'
        def start_daemon(self, *, create=False):
            self.state.mkdir()
            with sqlite3.connect(self.state / 'authority.db') as db:
                db.execute('CREATE TABLE capture_probe(marker TEXT)')
                db.execute('INSERT INTO capture_probe VALUES (?)', ('retained-before-cleanup',))
            (self.base / 'probe-request.json').write_text('{"probe":"original-scratch"}\n')
            self.relay.close()
            with self.relay.lock:
                self.relay.requests.append((decode(tx), tx))
                self.relay.responses.append((decode(rx), rx))
                self.relay.pending.append(rx)
            self.report['scope'] = 'Controlled capture selfcheck: original scratch SQLite, retained original raw bytes, process-lifetime stub; no native execution.'
            if self.failure_stage == 'setup':
                raise RuntimeError('controlled setup failure after evidence creation')
        def setUp(self):
            with patch.object(endpoint.subprocess, 'Popen', return_value=FixtureStub()):
                super().setUp()
        def test_capture(self):
            self.fail('controlled non-SQL test assertion')

    class SetupCapture(ControlledCapture):
        failure_stage = 'setup'

    class EarlySetupCapture(endpoint.CompactCliRestartTests):
        def setUp(self):
            with patch.object(endpoint.subprocess, 'Popen', side_effect=RuntimeError('controlled Popen setup failure')):
                super().setUp()
        def test_capture(self):
            raise AssertionError('unreachable')

    cases = [ControlledCapture('test_capture'), SetupCapture('test_capture'), EarlySetupCapture('test_capture')]
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.TestSuite(cases))
    assert result.testsRun == 3 and len(result.failures) == 1 and len(result.errors) == 2
    artifacts = []
    for case in cases:
        report = endpoint.LAST_REPORT['cases'][case.id()]
        assert report['passed'] is False and len(report['failureArtifacts']) == 1
        assert not case.base.exists(), 'temporary directory must still be cleaned'
        manifest_path = ROOT / report['failureArtifacts'][0]
        manifest = json.loads(manifest_path.read_bytes())
        artifacts.append({'path': str(manifest_path.relative_to(ROOT)),
                          'sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()})
        for pin in manifest['files']:
            raw = (manifest_path.parent / pin['path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == pin['sha256'] and len(raw) == pin['bytes']
        retained = json.loads((manifest_path.parent / 'report.json').read_bytes())
        assert retained['failureDetails'][0]['stage'] == 'before-cleanup'
        if not isinstance(case, EarlySetupCapture):
            relay = json.loads((manifest_path.parent / 'relay.json').read_bytes())
            assert relay['requests'] == [tx.hex()] and relay['responses'] == [rx.hex()]
            assert relay['pendingReplies'] == [rx.hex()]
            with sqlite3.connect((manifest_path.parent / 'databases/authority.db').as_uri() + '?mode=ro&immutable=1', uri=True) as db:
                assert db.execute('SELECT marker FROM capture_probe').fetchall() == [('retained-before-cleanup',)]
            assert retained['processOutput'][-1]['process'] == 'fixture'
    passed = True
    extra.update(expectedControlledFailures=1, expectedControlledSetupErrors=2, artifacts=artifacts)
elif mode == 'actual':
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.TestSuite([
        endpoint.CompactCliRestartTests('test_three_native_scenarios_reconcile_after_SIGKILL_without_replaying_OP')]))
    passed = result.wasSuccessful()
else:
    raise ValueError('unknown mode')
verify()
report = {'schema': 'hms-endpoint-cli-capture-proof/1', 'mode': mode, 'label': label, 'passed': passed,
          'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
          'seconds': time.monotonic() - started, 'inputsUnchanged': True,
          'inputCount': len(PINS), 'trace': endpoint.LAST_REPORT, **extra}
for name, data in [(label + '.log', log.getvalue()),
                   (label + '.json', json.dumps(report, indent=2, sort_keys=True) + '\n')]:
    with (LANE / name).open('x') as output:
        output.write(data)
print(log.getvalue())
print(json.dumps({key: value for key, value in report.items() if key != 'trace'}, indent=2))
raise SystemExit(0 if passed else 1)
