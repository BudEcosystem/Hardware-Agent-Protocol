"""Bounded fresh-invoke observation against original native simulation routes."""
from contextlib import contextmanager
import copy
import threading
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.endpoint_wire import Opcode
from hms.journal import Context, JournalError, PresenceAgeExpired
from protocol.serial.frame import Decoder
from test_multi_adapter import MultiHarness, installation, scenario


LAST_REPORT = {'schema': 'hms-compact-admission-tests/1', 'cases': {}}


class DelayedConnection:
    """Actual SQLite passthrough with logical elapsed time at COMMIT return."""
    def __init__(self, connection, move, delay):
        self.connection, self.move, self.delay = connection, move, delay
        self.writes = []
        self.commits = []

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, *args, **kwargs):
        result = self.connection.execute(sql, *args, **kwargs)
        if sql.startswith('BEGIN'):
            self.writes = []
        elif sql.startswith(('INSERT', 'UPDATE', 'DELETE')):
            self.writes.append(sql)
        elif sql == 'COMMIT':
            amount = self.delay(tuple(self.writes))
            self.commits.append({'delayMs': amount, 'writes': list(self.writes)})
            self.move(amount)
            self.writes = []
        return result


class CompactAdmissionTests(MultiHarness):
    def setUp(self):
        super().setUp()
        self.local = installation('admission-local')
        self.other = installation('admission-c1', compact=True)
        self.target = installation('admission-c2', compact=True)
        self.open([self.local, self.other, self.target], create=True)
        self.backend = self.runtime.adapters[self.target['adapterId']]
        self.request = self.prepare(self.target, 'focus', key='fresh-observation')
        self.wire = canonical(self.request)
        self.trace = {'checks': []}
        LAST_REPORT['cases'][self._testMethodName] = self.trace

    def move(self, amount):
        self.wall += amount
        self.mono += amount
        if amount:
            for endpoint in self.endpoints.values():
                self.assertEqual(endpoint.command(1, self.mono), self.mono)

    @contextmanager
    def delayed_commits(self, delay):
        journal, registry = self.runtime.journal, self.runtime.registry
        proxy = DelayedConnection(journal._db, self.move, delay)
        other = self.runtime.adapters[self.other['adapterId']]
        with patch.object(journal, '_db', proxy), patch.object(registry, '_db', proxy), \
                patch.object(self.backend, 'db', proxy), patch.object(other, 'db', proxy):
            yield proxy

    def packets(self):
        values = []
        with self.runtime.journal._mutex:
            rows = self.runtime.journal._db.execute(
                "SELECT id,adapter,wire FROM ep_packets WHERE direction='tx' ORDER BY id").fetchall()
        for row in rows:
            decoder, frames = Decoder(), []
            for byte in row['wire']:
                event = decoder.feed(byte)
                if event and event[0] == 'frame':
                    frames.append(event[1])
            self.assertEqual(len(frames), 1)
            values.append((row['id'], row['adapter'], int(frames[0].payload[1])))
        return values

    def counts(self):
        with self.runtime.journal._mutex:
            db = self.runtime.journal._db
            return {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                    for name in ('operations', 'claims', 'ep_commands', 'replay_keys')}

    def counters(self):
        return {route: {'dispatches': endpoint.command(4), 'effects': endpoint.command(5)}
                for route, endpoint in self.endpoints.items()}

    def snapshot_authority(self):
        return {name: [tuple(row) for row in self.runtime.journal._db.execute('SELECT * FROM ' + name)]
                for name in ('reg_grants', 'reg_bindings', 'resource_floors')}

    def invoke_as(self, context=None, request=None):
        return self.runtime.request(context or self.owner, 'invoke', {'request': request or self.request})

    def no_io_refusal(self, code, *, context=None, request=None):
        packets, counts, counters = self.packets(), self.counts(), self.counters()
        with self.assertRaisesRegex(JournalError, '^' + code + '$'):
            self.invoke_as(context, request)
        self.assertEqual(self.packets(), packets)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.counters(), counters)
        self.trace['checks'].append({'refusal': code, 'noExtraPackets': True, 'counts': counts})

    def delegate(self, expires=150000):
        actor = Context('admission-delegate', self.owner.deployment)
        instance, action, _ = scenario(self.target, 'focus')
        for target, verb in [('*', 'namespace'), (instance, 'read'), (instance, 'invoke:' + action)]:
            self.runtime.registry.grant(self.owner, actor.principal, target, verb)
        token = self.runtime.request(actor, 'namespace', {'expiresUnixMs': expires})['token']
        request = copy.deepcopy(self.request)
        request['replayNamespace'] = token
        return actor, request

    def test_fresh_presence_does_not_refresh(self):
        before = self.packets()
        accepted = self.invoke_as()
        self.assertEqual(accepted['executionState'], 'accepted')
        self.assertEqual(self.packets(), before)

    def test_other_route_delay_refreshes_only_target_then_one_worker_dispatch(self):
        with self.delayed_commits(lambda _writes: 150) as proxy:
            self.runtime.adapters[self.other['adapterId']].refresh(force=True)
        self.assertEqual(len(proxy.commits), 8)
        self.assertEqual(self.wall, 101200)
        self.assertIsNone(self.runtime.adapters[self.other['adapterId']]._state()['fault'])
        before, counters = self.packets(), self.counters()
        authority = self.snapshot_authority()
        calls = []
        original = self.runtime.journal.submit
        def submit(context, wire, **kwargs):
            calls.append(wire)
            return original(context, wire, **kwargs)
        with patch.object(self.runtime.journal, 'submit', submit):
            accepted = self.invoke_as()
        self.assertEqual(calls, [self.wire] * 3)
        self.assertEqual(self.packets()[len(before):],
                         [(self.packets()[-1][0], self.target['adapterId'], Opcode.HELLO)])
        self.assertEqual(self.counters(), counters)
        after = self.snapshot_authority()
        self.assertEqual(after['reg_grants'], authority['reg_grants'])
        self.assertEqual(after['reg_bindings'], authority['reg_bindings'])
        self.assertEqual(self.counts(), {'operations': 1, 'claims': 1, 'ep_commands': 0, 'replay_keys': 1})
        self.assertEqual(canonical(self.request), self.wire)
        done = self.finish([accepted])[0]
        self.assertEqual(done['executionState'], 'completed')
        self.assertEqual(self.packet_count(self.target['adapterId']), 1)
        self.assertEqual(self.endpoints[self.target['adapterId']].command(4), 1)
        self.assertEqual(self.endpoints[self.target['adapterId']].command(5), 1)
        self.trace.update(logicalOtherRouteDelayMs=1200, submitCalls=3, refreshHellos=1,
                          dispatches=1, effects=1, sameRequestBytes=True)

    def test_final_publication_delay_still_refuses_without_refresh_loop(self):
        self.move(1100)
        before = self.packets()
        seen = []
        def delay(writes):
            if any('reg_presence' in sql for sql in writes):
                seen.append(True)
                return 1100
            return 0
        with self.delayed_commits(delay):
            with self.assertRaises(PresenceAgeExpired):
                self.invoke_as()
        self.assertEqual(seen, [True])
        self.assertEqual([p[2] for p in self.packets()[len(before):]], [Opcode.HELLO])
        self.assertEqual(self.counts(), {'operations': 0, 'claims': 0, 'ep_commands': 0, 'replay_keys': 0})
        self.assertTrue(all(value == {'dispatches': 0, 'effects': 0} for value in self.counters().values()))
        self.assertLess(self.wall, self.request['intent']['timing']['latestStartUnixMs'])
        self.trace.update(refreshHellos=1, finalRefusal='DEVICE_UNAVAILABLE', counts=self.counts())

    def test_missing_presence_does_not_refresh(self):
        with self.runtime.journal._transaction():
            self.runtime.journal._db.execute('DELETE FROM reg_presence WHERE instance=?',
                                           (self.target['instances']['focus'],))
        self.no_io_refusal('DEVICE_UNAVAILABLE')

    def test_changed_session_does_not_refresh(self):
        self.move(1100)
        request = copy.deepcopy(self.request)
        request['intent']['endpointSession'] = 'compact-boot:other'
        self.no_io_refusal('ENDPOINT_SESSION_CHANGED', request=request)

    def test_changed_binding_does_not_refresh(self):
        self.move(1100)
        request = copy.deepcopy(self.request)
        request['intent']['bindingGeneration'] = 'changed:binding'
        self.no_io_refusal('BINDING_CHANGED', request=request)

    def test_invalid_arguments_does_not_refresh(self):
        self.move(1100)
        request = copy.deepcopy(self.request)
        request['intent']['arguments']['position'] = 101
        self.no_io_refusal('ARGUMENT_SCHEMA_MISMATCH', request=request)

    def test_denied_invoke_does_not_refresh(self):
        actor, request = self.delegate()
        self.runtime.registry.grant(self.owner, actor.principal, self.target['instances']['focus'],
                                    'invoke:move_absolute', enabled=False)
        self.move(1100)
        self.no_io_refusal('ACCESS_DENIED', context=actor, request=request)

    def test_revoked_read_does_not_refresh(self):
        actor, request = self.delegate()
        self.runtime.registry.grant(self.owner, actor.principal, self.target['instances']['focus'],
                                    'read', enabled=False)
        self.move(1100)
        self.no_io_refusal('ACCESS_DENIED', context=actor, request=request)

    def test_missing_exact_action_grant_does_not_refresh(self):
        actor, request = self.delegate()
        instance = self.target['instances']['focus']
        self.runtime.registry.grant(self.owner, actor.principal, instance, 'invoke:move_absolute', enabled=False)
        self.runtime.registry.grant(self.owner, actor.principal, instance, 'invoke:other')
        self.move(1100)
        self.no_io_refusal('ACCESS_DENIED', context=actor, request=request)

    def test_presence_owned_by_other_adapter_does_not_refresh(self):
        self.move(1100)
        with self.runtime.journal._transaction():
            self.runtime.journal._db.execute('UPDATE reg_presence SET adapter=? WHERE instance=?',
                (self.other['adapterId'], self.target['instances']['focus']))
        self.no_io_refusal('DEVICE_UNAVAILABLE')

    def test_faulted_route_does_not_refresh(self):
        self.move(1100)
        with self.runtime.journal._transaction():
            state = self.backend._state()
            state['fault'] = 'ENDPOINT_INHIBITED'
            self.backend._save(state)
        self.no_io_refusal('ENDPOINT_INHIBITED')

    def test_unready_route_cannot_provision_during_invoke(self):
        self.move(1100)
        with patch.dict(self.runtime.catalog.ready, {self.target['adapterId']: False}):
            self.no_io_refusal('ENDPOINT_INSTALLATION_REQUIRED')

    def test_offline_route_does_not_refresh(self):
        self.move(1100)
        with patch.object(self.backend, 'stream', None):
            self.no_io_refusal('ENDPOINT_DISCONNECTED')

    def test_expired_namespace_does_not_refresh(self):
        self.move(50000)
        self.no_io_refusal('EXPIRED_REPLAY_NAMESPACE')

    def test_invalid_clock_does_not_refresh(self):
        self.move(1100)
        with patch.object(self.runtime.journal, 'clock_ms', lambda: None):
            self.no_io_refusal('INVALID_CLOCK')

    def test_invalid_monotonic_clock_does_not_send_hello(self):
        self.move(1100)
        with patch.object(self.runtime.registry, 'monotonic_ms', lambda: None):
            self.no_io_refusal('CLOCK_MAPPING_INVALID')

    def test_retained_accepted_terminal_and_conflict_do_not_refresh(self):
        accepted = self.invoke_as()
        self.move(50000)
        before = self.packets()
        self.assertEqual(self.invoke_as(), accepted)
        self.assertEqual(self.packets(), before)
        conflict = copy.deepcopy(self.request)
        conflict['intent']['arguments']['position'] = 43
        self.no_io_refusal('KEY_CONFLICT', request=conflict)
        self.call('cancel', operationId=accepted['operationId'])
        terminal = self.invoke_as()
        self.assertEqual(terminal['executionState'], 'canceled')
        self.assertEqual(terminal['operationId'], accepted['operationId'])
        self.assertEqual(self.packets(), before)

    def test_unknown_handoff_replay_after_restart_does_not_refresh(self):
        accepted = self.invoke_as()
        self.runtime.journal.claim_dispatch(accepted['operationId'])
        self.reopen()
        self.backend = self.runtime.adapters[self.target['adapterId']]
        before = self.packets()
        self.move(50000)
        replay = self.invoke_as()
        self.assertEqual(replay['operationId'], accepted['operationId'])
        self.assertEqual(replay['executionState'], 'outcome_unknown')
        self.assertTrue(replay['mayHaveActed'])
        self.assertEqual(self.packets(), before)

    def wait_at_route_lock(self, context, request, mutation):
        initial, finished = threading.Event(), threading.Event()
        result = []
        original = self.runtime.journal.submit
        def submit(actor, wire, **kwargs):
            try:
                return original(actor, wire, **kwargs)
            except PresenceAgeExpired:
                initial.set()
                raise
        def invoke():
            try:
                result.append(self.invoke_as(context, request))
            except BaseException as error:
                result.append(error)
            finally:
                finished.set()
        worker = threading.Thread(target=invoke)
        try:
            with self.runtime._route_locks[self.target['adapterId']], \
                    patch.object(self.runtime.journal, 'submit', submit):
                worker.start()
                self.assertTrue(initial.wait(3))
                self.assertFalse(finished.is_set())
                mutation(original)
                before = self.packets()
        finally:
            if worker.ident is not None:
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertTrue(finished.is_set())
        self.assertEqual(self.packets(), before)
        self.assertEqual(len(result), 1)
        return result[0]

    def test_read_revoked_while_waiting_is_rechecked_before_io(self):
        actor, request = self.delegate()
        self.move(1100)
        result = self.wait_at_route_lock(actor, request, lambda _submit:
            self.runtime.registry.grant(self.owner, actor.principal, self.target['instances']['focus'],
                                        'read', enabled=False))
        self.assertIsInstance(result, JournalError)
        self.assertEqual(result.code, 'ACCESS_DENIED')
        self.assertEqual(self.counts()['operations'], 0)

    def test_concurrent_same_key_admission_returns_replay_without_refresh(self):
        self.move(1100)
        admitted = []
        def mutation(submit):
            self.backend.refresh(force=True)
            admitted.append(submit(self.owner, self.wire))
        result = self.wait_at_route_lock(self.owner, self.request, mutation)
        self.assertEqual(result['operationId'], admitted[0]['id'])
        self.assertEqual(self.counts()['operations'], 1)
        self.assertEqual(self.counts()['ep_commands'], 0)

    def test_concurrent_conflicting_key_does_not_refresh(self):
        self.move(1100)
        conflict = copy.deepcopy(self.request)
        conflict['intent']['arguments']['position'] = 43
        def mutation(submit):
            self.backend.refresh(force=True)
            submit(self.owner, canonical(conflict))
        result = self.wait_at_route_lock(self.owner, self.request, mutation)
        self.assertIsInstance(result, JournalError)
        self.assertEqual(result.code, 'KEY_CONFLICT')
        self.assertEqual(self.counts()['operations'], 1)

    def test_expiry_during_refresh_allocates_nothing(self):
        self.move(1100)
        before = self.packets()
        original = self.backend.refresh_for_admission
        def refresh():
            original()
            self.move(2000)
        with patch.object(self.backend, 'refresh_for_admission', refresh):
            with self.assertRaisesRegex(JournalError, '^START_EXPIRED$'):
                self.invoke_as()
        self.assertEqual([p[2] for p in self.packets()[len(before):]], [Opcode.HELLO])
        self.assertEqual(self.counts(), {'operations': 0, 'claims': 0, 'ep_commands': 0, 'replay_keys': 0})

    def test_namespace_expiry_during_refresh_allocates_nothing(self):
        actor, request = self.delegate(expires=101800)
        self.move(1100)
        before = self.packets()
        original = self.backend.refresh_for_admission
        def refresh():
            original()
            self.move(800)
        with patch.object(self.backend, 'refresh_for_admission', refresh):
            with self.assertRaisesRegex(JournalError, '^EXPIRED_REPLAY_NAMESPACE$'):
                self.invoke_as(actor, request)
        self.assertLess(self.wall, request['intent']['timing']['latestStartUnixMs'])
        self.assertEqual([p[2] for p in self.packets()[len(before):]], [Opcode.HELLO])
        self.assertEqual(self.counts(), {'operations': 0, 'claims': 0, 'ep_commands': 0, 'replay_keys': 0})

    def test_prepare_and_direct_journal_submission_do_not_auto_refresh(self):
        self.move(1100)
        before = self.packets()
        with self.assertRaisesRegex(JournalError, '^DEVICE_UNAVAILABLE$'):
            self.prepare(self.target, 'focus', key='prepare-only')
        with self.assertRaises(PresenceAgeExpired):
            self.runtime.journal.submit(self.owner, self.wire)
        self.assertEqual(self.packets(), before)
        self.assertEqual(self.counts()['operations'], 0)


if __name__ == '__main__':
    unittest.main()
