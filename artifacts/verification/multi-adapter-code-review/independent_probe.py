#!/usr/bin/env python3
"""Original independent host probes. No device, AVR or emulator execution.

The synthetic migration uses opaque bytes, not executable endpoint payloads.
Private helper calls deliberately exercise otherwise difficult failure edges.
"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from hms.contracts import canonical
from hms.endpoint_binding import ADAPTER, ensure_endpoint_schema
from hms.endpoint_wire import hello
from hms.installations import ROLES, legacy_installation, plant_filename
from hms.journal import Context, JournalError
from hms.runtime import Runtime


def configuration(name, compact=False):
    item = legacy_installation(compact)
    item['adapterId'] = 'independent:' + name
    item['instances'] = {r: 'sim:independent-' + name + '-' + r for r in ROLES}
    item['resources'] = {r: 'independent-resource:' + name + '-' + r for r in ROLES}
    if compact:
        item['incarnationHex'] = hashlib.sha256(name.encode()).hexdigest()[:32]
    return item


class ReviewCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hms-independent-code-review-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state'
        self.wall, self.mono = 100000, 1000
        self.owner = Context('independent-review', 'simulation:multi')
        self.runtime = None
        self.addCleanup(self.close)

    def close(self):
        if self.runtime:
            self.runtime.close()
            self.runtime = None

    def open(self, configs=None, create=False):
        self.runtime = Runtime(self.path, create=create, owner=self.owner if create else None,
            installations=configs, wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        return self.runtime

    def prepare(self, config, key):
        if not hasattr(self, 'namespace'):
            self.namespace = self.runtime.request(self.owner, 'namespace', {'expiresUnixMs':200000})['token']
        return self.runtime.request(self.owner, 'prepare', {
            'instanceId':config['instances']['fan'], 'actionId':'set_level',
            'arguments':{'level':25, 'unit':'percent'}, 'operationKey':key,
            'replayNamespace':self.namespace, 'requiredEffect':'capability_completion',
            'timing':{'notBeforeUnixMs':self.wall, 'latestStartUnixMs':self.wall+5000,
                'maxRunMs':1000, 'latestCompletionUnixMs':self.wall+6000}})['request']

    def invoke(self, request):
        return self.runtime.request(self.owner, 'invoke', {'request':request})

    def status(self, operation):
        return self.runtime.request(self.owner, 'operation', {'operationId':operation['operationId']})

    def advance(self):
        self.wall += 100
        self.mono += 100
        try:
            self.runtime.tick()
        except JournalError:
            if not self.runtime.route_errors:
                raise

    def finish(self, op):
        for _ in range(8):
            self.advance()
            state = self.status(op)
            if state['executionState'] == 'completed' and not state['resourceClaims']:
                return state
        self.fail(str(state))

    def test_each_sample_advances_wall_clock_and_snapshot_uses_one_expiry_origin(self):
        c = configuration('advancing-wall')
        runtime = self.open([c], create=True)
        calls = []
        def advancing():
            self.wall += 7
            calls.append(self.wall)
            return self.wall
        runtime.journal.clock_ms = advancing
        adapter = runtime.adapters[c['adapterId']]
        for _ in range(4):
            before = len(calls)
            adapter.refresh(force=True)
            self.assertEqual(len(calls)-before, 1)
            expiries = [r[0] for r in runtime.journal._db.execute('SELECT expires_ms FROM reg_presence')]
            self.assertEqual(expiries, [calls[-1]+3000]*3)
            self.assertEqual(int(runtime.journal._meta('last_clock')), calls[-1])
        self.assertFalse(runtime.journal._db.in_transaction)

    def test_late_batch_failure_rolls_back_session_history_and_ram_cache_but_keeps_clock_floor(self):
        c = configuration('batch-rollback')
        runtime = self.open([c], create=True)
        adapter = runtime.adapters[c['adapterId']]
        tables = ['reg_presence','reg_endpoint_sessions','reg_session_history',
                  'reg_streams','reg_stream_history','reg_observations']
        def rows():
            return {t:[tuple(r) for r in runtime.journal._db.execute('SELECT * FROM '+t+' ORDER BY rowid')]
                    for t in tables}
        before = rows()
        cache, last = copy.deepcopy(adapter._streams), adapter._last_sample
        original = runtime.registry.report_adapter_snapshot
        def reject_last(route, **groups):
            groups['observations'][-1]['sequence'] = -1
            return original(route, **groups)
        self.wall += 41
        with patch.object(adapter.plant, 'session', 'independent-session:rolled-back'):
            with patch.object(runtime.registry, 'report_adapter_snapshot', reject_last):
                with self.assertRaises(ValueError):
                    adapter.refresh(force=True)
        self.assertEqual(rows(), before)
        self.assertEqual(adapter._streams, cache)
        self.assertEqual(adapter._last_sample, last)
        self.assertEqual(int(runtime.journal._meta('last_clock')), self.wall)
        self.wall -= 1
        with self.assertRaisesRegex(JournalError, 'CLOCK_REGRESSION'):
            adapter.refresh(force=True)
        self.assertEqual(rows(), before)
        self.wall += 1
        adapter.refresh(force=True)
        self.assertEqual({k:v[1] for k,v in adapter._streams.items()}, {k:v[1]+1 for k,v in cache.items()})

    def test_acquisition_age_counts_delay_before_commit_and_late_reads(self):
        c = configuration('acquisition-age')
        runtime = self.open([c], create=True)
        adapter = runtime.adapters[c['adapterId']]
        original = adapter.plant.observe
        acquired = []
        def delayed(instance):
            acquired.append(self.mono)
            sample = original(instance)
            self.mono += 37
            return sample
        with patch.object(adapter.plant, 'observe', delayed):
            adapter.refresh(force=True)
        self.mono += 29
        for index, role in enumerate(ROLES):
            observation = runtime.registry._observation(c['instances'][role], 'ready')
            self.assertEqual(observation['ageUpperBoundMs'], self.mono-acquired[index])
            self.assertEqual(observation['acquisition']['ticksMs'], acquired[index])
            self.assertGreaterEqual(observation['acquisitionLatencyBoundMs'], 37)

    def test_empty_and_non_sqlite_store_remain_unchanged_while_other_route_completes(self):
        a, b = configuration('healthy'), configuration('broken')
        self.open([a,b], create=True)
        broken = self.path/plant_filename(b)
        for index, corrupt in enumerate((b'', b'independent invalid sqlite store\x00\x01')):
            self.close()
            broken.write_bytes(corrupt)
            self.open()
            self.assertEqual(self.runtime.route_errors, {b['adapterId']:'INVALID_SIMULATED_PLANT'})
            op = self.invoke(self.prepare(a, 'healthy-'+str(index)))
            self.assertEqual(self.finish(op)['executionState'], 'completed')
            self.assertEqual(broken.read_bytes(), corrupt)
            self.assertFalse(self.runtime.work_items(b['adapterId'], ('accepted',), limit=1))

    def test_offline_compact_fault_does_not_touch_other_route_or_local_running_work(self):
        local, a, b = configuration('local'), configuration('offline-a', True), configuration('offline-b', True)
        runtime = self.open([local,a,b], create=True)
        op = self.invoke(self.prepare(local, 'running-during-fault'))
        self.advance()
        self.assertEqual(self.status(op)['executionState'], 'running')
        adapters = [runtime.adapters[c['adapterId']] for c in (a,b)]
        before = [copy.deepcopy(adapter._state()) for adapter in adapters]
        with runtime.journal._transaction():
            first = adapters[0]._request(hello())
            second = adapters[1]._request(hello())
        self.assertEqual(first.frame.sequence, before[0]['tx']+1)
        self.assertEqual(second.frame.sequence, before[1]['tx']+1)
        b_state = adapters[1]._state()
        local_presence = [tuple(r) for r in runtime.journal._db.execute('SELECT * FROM reg_presence WHERE adapter=?', (local['adapterId'],))]
        adapters[0]._fault('INDEPENDENT_FAULT')
        self.assertEqual(adapters[1]._state(), b_state)
        self.assertEqual(adapters[0]._state()['fault'], 'INDEPENDENT_FAULT')
        self.assertEqual(self.status(op)['executionState'], 'running')
        self.assertEqual([tuple(r) for r in runtime.journal._db.execute('SELECT * FROM reg_presence WHERE adapter=?', (local['adapterId'],))], local_presence)
        self.assertEqual(self.finish(op)['executionState'], 'completed')

    def test_replay_uses_historical_route_after_current_binding_moves(self):
        a, b = configuration('old-route'), configuration('new-route')
        runtime = self.open([a,b], create=True)
        request = self.prepare(a, 'historical-replay')
        op = self.invoke(request)
        final = self.finish(op)
        binding, _ = runtime.registry._binding(a['instances']['fan'])
        binding.update(generation='independent:replacement', adapterId=b['adapterId'])
        runtime.registry.bind(self.owner, canonical(binding))
        self.assertEqual(self.invoke(request), final)
        self.assertEqual(runtime.route_for_operation(runtime.journal._operation(op['operationId'])), a['adapterId'])
        self.assertFalse(runtime.work_items(b['adapterId'], ('completed',), limit=1))
        self.assertEqual(runtime.adapters[a['adapterId']].plant.observe(a['instances']['fan'])['effectCount'], 1)
        self.assertEqual(runtime.adapters[b['adapterId']].plant.observe(b['instances']['fan'])['effectCount'], 0)


class SyntheticJournal:
    def __init__(self):
        self._db = sqlite3.connect(':memory:', isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA foreign_keys=ON')

    @contextlib.contextmanager
    def _transaction(self):
        self._db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self._db.execute('COMMIT')
        except BaseException:
            self._db.execute('ROLLBACK')
            raise


class MigrationCases(unittest.TestCase):
    def legacy(self):
        journal = SyntheticJournal()
        self.addCleanup(journal._db.close)
        db = journal._db
        db.executescript('''CREATE TABLE operations(id TEXT PRIMARY KEY);
            CREATE TABLE rt_adapters(adapter TEXT PRIMARY KEY);
            CREATE TABLE ep_state(singleton INTEGER PRIMARY KEY, document BLOB NOT NULL);
            CREATE TABLE ep_commands(operation_id TEXT PRIMARY KEY REFERENCES operations(id), payload BLOB NOT NULL,
                tx_sequence INTEGER NOT NULL,mapping BLOB NOT NULL,receipt BLOB,retired INTEGER NOT NULL,
                retire_intent INTEGER NOT NULL,result BLOB);
            CREATE TABLE ep_packets(id INTEGER PRIMARY KEY,direction TEXT NOT NULL,boot TEXT NOT NULL,sequence INTEGER NOT NULL,wire BLOB NOT NULL);''')
        db.execute('INSERT INTO rt_adapters VALUES (?)',(ADAPTER,))
        db.execute('INSERT INTO operations VALUES (?)',('opaque-op',))
        db.execute('INSERT INTO ep_state VALUES (1,?)',(b'\x00opaque-state\xff',))
        db.execute('INSERT INTO ep_commands(rowid,operation_id,payload,tx_sequence,mapping,receipt,retired,retire_intent,result) VALUES (27,?,?,?,?,?,?,?,?)',
            ('opaque-op',b'\x00payload\xff',4294967294,b'mapping\x00',b'\xffreceipt',0,1,b'result\x00'))
        db.execute('INSERT INTO ep_packets VALUES (51,?,?,?,?)',('tx','18446744073709551615',4294967294,b'\x00wire\xff'))
        return journal

    @staticmethod
    def snapshot(db):
        return {t:[tuple(r) for r in db.execute('SELECT rowid,* FROM '+t)]
                for t in ('ep_state','ep_commands','ep_packets')}

    def test_legacy_migration_preserves_opaque_bytes_rowids_and_is_idempotent(self):
        journal = self.legacy()
        before = self.snapshot(journal._db)
        ensure_endpoint_schema(journal)
        db = journal._db
        self.assertEqual(tuple(db.execute('SELECT rowid,operation_id,payload,tx_sequence,mapping,receipt,retired,retire_intent,result FROM ep_commands').fetchone()), before['ep_commands'][0])
        self.assertEqual(tuple(db.execute('SELECT rowid,id,direction,boot,sequence,wire FROM ep_packets').fetchone()), before['ep_packets'][0])
        self.assertEqual(db.execute('SELECT document FROM ep_state').fetchone()[0], before['ep_state'][0][-1])
        for table in before:
            self.assertEqual(db.execute('SELECT adapter FROM '+table).fetchone()[0], ADAPTER)
        after = self.snapshot(db)
        ensure_endpoint_schema(journal)
        self.assertEqual(self.snapshot(db), after)
        self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_failure_after_copy_rolls_back_renames_and_bytes(self):
        journal = self.legacy()
        db = journal._db
        before, schema = self.snapshot(db), list(db.iterdump())
        def deny_drop(action, first, second, database, trigger):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DROP_TABLE and first == 'ep_packets_before_routes' else sqlite3.SQLITE_OK
        db.set_authorizer(deny_drop)
        with self.assertRaises(sqlite3.DatabaseError):
            ensure_endpoint_schema(journal)
        db.set_authorizer(None)
        self.assertEqual(self.snapshot(db), before)
        self.assertEqual(list(db.iterdump()), schema)
        ensure_endpoint_schema(journal)

    def test_partial_schema_and_mixed_route_columns_rejected_without_mutation(self):
        for ddl in ('DROP TABLE ep_packets', 'ALTER TABLE ep_packets ADD COLUMN adapter TEXT'):
            with self.subTest(ddl=ddl):
                journal = self.legacy()
                journal._db.execute(ddl)
                before = list(journal._db.iterdump())
                with self.assertRaisesRegex(JournalError, 'ENDPOINT_SCHEMA_INCOMPLETE'):
                    ensure_endpoint_schema(journal)
                self.assertEqual(list(journal._db.iterdump()), before)


def check_pins():
    rows = json.loads((BASE/'frozen-sources.json').read_text())
    for row in rows:
        assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
    return rows


if __name__ == '__main__':
    pins = check_pins()
    started = time.time()
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    check_pins()
    (BASE/'independent-probe-output.txt').write_text(output.getvalue())
    record = {'passed':result.wasSuccessful(), 'tests':result.testsRun,
        'failures':len(result.failures), 'errors':len(result.errors),
        'elapsed_seconds':round(time.time()-started,3), 'source_pins_checked_before_and_after':len(pins),
        'scope':'Original Python host probes and SQLite schema fixtures; no hardware, AVR or emulator execution.'}
    (BASE/'independent-probe-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(output.getvalue())
    print(json.dumps(record))
    sys.exit(0 if result.wasSuccessful() else 1)
