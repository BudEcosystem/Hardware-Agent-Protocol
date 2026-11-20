"""Exercise failure retention on scratch SQLite state; no daemon/native execution."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
from test_multi_cli import finish_transport_failure, retain_transport_failure
from test_procedure_transport import MixedDaemon
from test_runtime_ipc import RuntimeIpc


def fixture(state):
    state.mkdir()
    with sqlite3.connect(state / 'authority.db') as db:
        db.executescript('CREATE TABLE operations(id TEXT, state TEXT, may_have_acted INTEGER); '
                        'CREATE TABLE events(operation_id TEXT, sequence INTEGER, kind TEXT, payload BLOB); '
                        "INSERT INTO operations VALUES ('op:diagnostic','rejected_before_dispatch',0);")
        db.execute('INSERT INTO events VALUES (?,?,?,?)', ('op:diagnostic', 2, 'rejected_before_dispatch',
                   json.dumps({'reason':'OBSERVATION_STALE'}).encode()))
    with sqlite3.connect(state / 'plant.db') as db:
        db.executescript('CREATE TABLE devices(id TEXT,value INTEGER,effects INTEGER); '
                        "INSERT INTO devices VALUES ('simulation:diagnostic',0,0);")


def verify(report):
    paths = report['failureArtifacts']
    assert paths and not report.get('failureCaptureErrors'), report
    for name in paths:
        manifest_path = ROOT / name
        manifest = json.loads(manifest_path.read_text())
        for pin in manifest['files']:
            data = (manifest_path.parent / pin['path']).read_bytes()
            assert len(data) == pin['bytes']
            assert hashlib.sha256(data).hexdigest() == pin['sha256']
        summary = json.loads((manifest_path.parent / 'databases/authority.db.json').read_text())
        assert summary['integrity'] == 'ok'
        event = summary['tables']['events']['rows'][0]
        assert event['kind'] == 'rejected_before_dispatch'
        assert event['payload']['reason'] == 'OBSERVATION_STALE'
    return paths


def main():
    retained = []
    with tempfile.TemporaryDirectory(prefix='hms-capture-check-') as temporary:
        base = Path(temporary); state = base / 'state'; fixture(state)
        (base / 'request.json').write_text(json.dumps({'operationKey':'diagnostic:exact'}))
        before = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in state.glob('*.db')}
        report = {'passed':False,'purpose':'intentional failure-capture validation','processOutput':[]}
        relay = SimpleNamespace(lock=threading.Lock(), requests=[(None,b'original-request')],
            responses=[(None,b'original-response')], pending=[b'held-response'], error=None)
        harness = MixedDaemon.__new__(MixedDaemon)
        harness.report, harness.state, harness.base, harness.relay = report, state, base, relay
        harness.retain_failure('intentional failure before cleanup')
        report['processOutput'].append({'stderr':'synthetic retained stderr','exitCode':0})
        finish_transport_failure(report)
        retained += verify(report)
        assert before == {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in state.glob('*.db')}
        captured = ROOT / report['failureArtifacts'][0]
        wires = json.loads((captured.parent / 'relay.json').read_text())
        assert wires['requests'] == [b'original-request'.hex()]
        assert wires['responses'] == [b'original-response'.hex()]
        assert wires['pendingReplies'] == [b'held-response'.hex()]
        assert json.loads((captured.parent / 'report.json').read_text())['processOutput'][0]['stderr'] == 'synthetic retained stderr'

    class ExpectedSubtestFailure(RuntimeIpc):
        def runTest(self):
            fixture(self.state)
            with self.subTest(case='intentional diagnostic probe'):
                self.fail('intentional subtest failure retained before cleanup')

    probe = ExpectedSubtestFailure('runTest')
    output = io.StringIO()
    outcome = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.TestSuite([probe]))
    assert outcome.testsRun == 1 and len(outcome.failures) == 1 and not outcome.errors
    assert not probe.path.exists(), 'fixture cleanup must still run'
    retained += verify(probe.report)

    with tempfile.TemporaryDirectory(prefix='hms-capture-error-check-') as temporary:
        state = Path(temporary); (state / 'invalid.db').write_bytes(b'not a SQLite database')
        report = {'passed':False,'purpose':'intentional capture-error containment validation'}
        retain_transport_failure(report,'expected-invalid-database',state,'original assertion remains the failure')
        metadata = json.loads((ROOT / report['failureArtifacts'][0]).with_name('capture.json').read_text())
        assert metadata['databases'][0]['complete'] is False
        assert metadata['databases'][0]['stderr']
        retained += report['failureArtifacts']

    result = {'schema':'hms-failure-capture-self-check/1','passed':True,
        'checks':['read-only consistent backups and exact rejection reason','original relay bytes retained',
                  'cleanup stderr included in final manifest','subtest failure captured before temporary cleanup',
                  'capture error does not replace original failure'],
        'intentionalSubtestFailures':1,'failureArtifacts':retained,
        'scope':'Original scratch SQLite and Python diagnostic code only; no daemon, native endpoint or hardware execution.'}
    (Path(__file__).parent / 'capture-self-check.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    (Path(__file__).parent / 'capture-self-check.log').write_text(output.getvalue())
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
