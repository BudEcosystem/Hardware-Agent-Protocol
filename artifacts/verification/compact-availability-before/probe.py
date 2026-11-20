"""Original native/virtual-clock availability probes against a frozen input tree."""
from contextlib import contextmanager
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
import unittest
from unittest.mock import patch


LANE = Path(__file__).resolve().parent
BASELINE = LANE / 'inputs'
sys.path[:0] = [str(BASELINE / 'tests'), str(BASELINE)]
from hms.contracts import canonical
from hms.journal import JournalError
from test_multi_adapter import MultiHarness, installation


REPORT = {'schema':'hms-compact-availability-probe/1', 'cases':{},
    'scope':'Original native C simulation fixtures with synchronized synthetic clocks. Delays are injected logical elapsed time after real SQLite commits; no hardware or measured latency claim.'}


class ObservedConnection:
    """Forward actual SQLite statements; classify commits and advance test clocks."""
    def __init__(self, connection, probe, delay):
        self.connection, self.probe, self.delay = connection, probe, delay
        self.writes = []
        self.index = 0

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, *args, **kwargs):
        before = {'wall':self.probe.wall, 'mono':self.probe.mono}
        result = self.connection.execute(sql, *args, **kwargs)
        if sql.startswith('BEGIN'):
            self.writes = []
        elif sql.startswith(('INSERT', 'UPDATE', 'DELETE')):
            self.writes.append(sql)
            if 'reg_presence' in sql:
                self.probe.case['presenceWrites'].append({'wall':self.probe.wall,
                    'mono':self.probe.mono, 'parameters':list(args[0])})
        elif sql == 'COMMIT':
            self.index += 1
            if any('reg_presence' in item for item in self.writes):
                kind = 'snapshot_publication'
            elif self.writes and all('UPDATE meta SET' in item for item in self.writes):
                kind = 'authority_floor'
            elif any('ep_packets' in item for item in self.writes):
                kind = 'endpoint_packet'
            elif any('ep_state' in item for item in self.writes):
                kind = 'endpoint_state'
            else:
                kind = 'empty_or_other'
            record = {'index':self.index, 'kind':kind, 'before':before,
                      'writes':list(self.writes), 'delayMs':self.delay(self.index, kind)}
            self.probe.move(record['delayMs'])
            record['after'] = {'wall':self.probe.wall, 'mono':self.probe.mono}
            self.probe.case['commits'].append(record)
            self.writes = []
        return result


class AvailabilityProbe(MultiHarness):
    def setUp(self):
        super().setUp()
        self.local = installation('availability-local')
        self.other = installation('availability-c1', compact=True)
        self.target = installation('availability-c2', compact=True)
        self.open([self.local, self.other, self.target], create=True)
        self.target_adapter = self.runtime.adapters[self.target['adapterId']]
        self.other_adapter = self.runtime.adapters[self.other['adapterId']]
        self.request = self.prepare(self.target, 'focus', key='availability:exact')
        self.wire = canonical(self.request)
        self.case = {'request':copy.deepcopy(self.request), 'commits':[], 'presenceWrites':[],
                     'admissions':[], 'snapshots':{}, 'nativeCounters':{}}
        REPORT['cases'][self._testMethodName] = self.case
        self.output = LANE / 'probe-output' / self._testMethodName
        self.output.mkdir(parents=True, exist_ok=False)
        self.capture('initial')

    def move(self, amount):
        self.wall += amount
        self.mono += amount
        if amount:
            for endpoint in self.endpoints.values():
                self.assertEqual(endpoint.command(1, self.mono), self.mono)

    @contextmanager
    def commits(self, delay):
        journal, registry = self.runtime.journal, self.runtime.registry
        proxy = ObservedConnection(journal._db, self, delay)
        with patch.object(journal, '_db', proxy), patch.object(registry, '_db', proxy), \
                patch.object(self.target_adapter, 'db', proxy), patch.object(self.other_adapter, 'db', proxy):
            yield proxy

    def presence(self):
        row = self.runtime.journal._db.execute('SELECT * FROM reg_presence WHERE instance=?',
                                              (self.target['instances']['focus'],)).fetchone()
        return dict(row) if row else None

    def counts(self):
        db = self.runtime.journal._db
        result = {name:db.execute('SELECT count(*) FROM '+name).fetchone()[0]
                  for name in ('operations','claims','ep_commands')}
        result['exactReplayKeys'] = db.execute('SELECT count(*) FROM replay_keys WHERE namespace=? AND caller_key=?',
            (self.request['replayNamespace'],self.request['operationKey'])).fetchone()[0]
        return result

    def capture(self, stage):
        db = self.runtime.journal._db
        ready = db.execute('SELECT document FROM reg_observations WHERE instance=? AND property=?',
                          (self.target['instances']['focus'],'ready')).fetchone()
        self.case['snapshots'][stage] = {'wall':self.wall,'mono':self.mono,
            'presence':self.presence(),'ready':json.loads(ready[0]) if ready else None,
            'counts':self.counts(),'durableClockFloor':int(self.runtime.journal._meta('last_clock')),
            'routeFaults':{name:backend._state()['fault'] for name,backend in self.runtime.adapters.items()
                           if hasattr(backend,'_state')}}
        with sqlite3.connect(self.output / (stage+'.db')) as retained:
            db.backup(retained)

    def recorded_invoke(self):
        self.assertEqual(canonical(self.request), self.wire)
        original = self.runtime.policy.admit
        def observed(context, intent, now):
            row = self.presence()
            record = {'authorityTime':now,'wallAtPolicyEntry':self.wall,'monoAtPolicyEntry':self.mono,
                'presence':row,'presenceRemainingMs':row['expires_ms']-now if row else None,
                'countsAtPolicyEntry':self.counts(),
                'durableClockFloor':int(self.runtime.journal._meta('last_clock'))}
            self.case['admissions'].append(record)
            try:
                answer = original(context, intent, now)
            except JournalError as error:
                record['outcome'] = error.code
                raise
            record['outcome'] = 'admitted'
            return answer
        with patch.object(self.runtime.policy, 'admit', observed):
            return self.invoke(self.request)

    def assert_refusal_without_handoff(self):
        before = self.counts()
        with self.assertRaisesRegex(JournalError, '^DEVICE_UNAVAILABLE$'):
            self.recorded_invoke()
        self.assertEqual(self.counts(), before)
        self.assertEqual(before, {'operations':0,'claims':0,'ep_commands':0,'exactReplayKeys':0})
        self.assertLess(self.wall, self.request['intent']['timing']['latestStartUnixMs'])
        self.assertLess(self.wall, 150000)
        for route,endpoint in self.endpoints.items():
            counters = {'dispatches':endpoint.command(4), 'effects':endpoint.command(5)}
            self.case['nativeCounters'][route] = counters
            self.assertEqual(counters, {'dispatches':0,'effects':0})
        self.capture('refused')

    def test_baseline_fresh_admission(self):
        accepted = self.recorded_invoke()
        self.assertEqual(accepted['executionState'],'accepted')
        self.capture('accepted')

    def publication_delay(self, kind):
        original = self.runtime.registry.report_adapter_snapshot
        matched = []
        def publication(adapter_id, **kwargs):
            if adapter_id != self.target['adapterId']:
                return original(adapter_id, **kwargs)
            # One millisecond elapsed after HELLO is enough to require a new
            # authority floor; its actual COMMIT is the selected delay seam.
            self.move(1)
            def delay(_index, actual):
                if actual == kind and not matched:
                    matched.append(True)
                    return 1100
                return 0
            with self.commits(delay):
                return original(adapter_id, **kwargs)
        with patch.object(self.runtime.registry,'report_adapter_snapshot',publication):
            self.target_adapter.refresh(force=True)
        self.assertEqual(matched,[True])
        self.assertIsNone(self.target_adapter._state()['fault'])
        self.capture('refresh_returned')
        self.assertLessEqual(self.presence()['expires_ms'], self.wall)
        self.assert_refusal_without_handoff()

    def test_clock_floor_commit_can_expire_presence_before_publication(self):
        self.publication_delay('authority_floor')
        writes = self.case['presenceWrites']
        self.assertEqual(len(writes),3)
        self.assertTrue(all(entry['wall'] >= entry['parameters'][2] for entry in writes))

    def test_publication_commit_can_consume_entire_presence_lifetime(self):
        self.publication_delay('snapshot_publication')
        self.assertTrue(all(entry['wall'] < entry['parameters'][2] for entry in self.case['presenceWrites']))

    def test_other_healthy_route_commits_can_age_target_past_ttl(self):
        # The other route follows its normal refresh under the actual shared
        # Journal mutex. A contender records that it cannot acquire that mutex
        # until all this refresh's original database operations have completed.
        attempted, acquired = threading.Event(), threading.Event()
        entered = []
        def contender():
            attempted.set()
            with self.runtime.journal._mutex:
                entered.append({'wall':self.wall,'mono':self.mono})
                acquired.set()
        with self.runtime.journal._mutex:
            worker = threading.Thread(target=contender)
            worker.start()
            self.assertTrue(attempted.wait(3))
            with self.commits(lambda _index,_kind:150):
                self.other_adapter.refresh(force=True)
            self.assertFalse(acquired.is_set())
        worker.join(3)
        self.assertFalse(worker.is_alive()); self.assertTrue(acquired.is_set())
        self.case['mutexContender'] = {'acquiredAfterOtherRefresh':True,'entry':entered[0],
            'scope':'One controlled lock-contention episode, not a scheduler fairness or real-time measurement.'}
        self.assertIsNone(self.other_adapter._state()['fault'])
        self.assertIsNone(self.target_adapter._state()['fault'])
        self.capture('other_refresh_returned')
        self.assert_refusal_without_handoff()

        # This is an explicit probe action after a proven no-admission refusal,
        # not a production retry. The unchanged request and original time/key
        # remain authoritative; one new target HELLO can then permit admission.
        self.target_adapter.refresh(force=True)
        self.capture('target_refreshed')
        accepted = self.recorded_invoke()
        self.assertEqual(accepted['executionState'],'accepted')
        self.assertEqual(canonical(self.request),self.wire)
        self.case['explicitTargetRefreshRecoveredExactRequest'] = True
        self.capture('accepted_after_explicit_refresh')


def main():
    baseline = json.loads((LANE / 'baseline-pins.json').read_text())
    baseline.update(json.loads((LANE / 'supplemental-pins.json').read_text()))
    def verify():
        for name,pin in baseline.items():
            assert hashlib.sha256((BASELINE/name).read_bytes()).hexdigest()==pin['sha256'],name
    verify()
    for name,module in list(sys.modules.items()):
        if (name=='test_multi_adapter' or name.startswith(('hms','protocol.'))) and getattr(module,'__file__',None):
            assert Path(module.__file__).resolve().is_relative_to(BASELINE), (name,module.__file__)
    output=io.StringIO(); started=time.monotonic()
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AvailabilityProbe))
    verify()
    REPORT['run']={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                   'skipped':len(result.skipped),'passed':result.wasSuccessful(),
                   'seconds':time.monotonic()-started,'frozenInputsUnchanged':True,
                   'probeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (LANE/'probe.log').write_text(output.getvalue())
    (LANE/'probe.json').write_text(json.dumps(REPORT,indent=2,sort_keys=True)+'\n')
    print(output.getvalue());print(json.dumps(REPORT['run'],indent=2,sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
