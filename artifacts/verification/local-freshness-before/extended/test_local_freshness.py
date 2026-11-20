"""Original local simulation boundary tests with deterministic durable-I/O delay.

The real SQLite COMMIT runs first. A controlled clock then models its elapsed
time, without sleeps, widened freshness limits, or a replacement policy.
"""
from contextlib import contextmanager
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

from hms.journal import Context
from hms.runtime import Runtime


class CommitClock:
    def __init__(self, connection, after_commit):
        self.connection = connection
        self.after_commit = after_commit

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, *args, **kwargs):
        result = self.connection.execute(sql, *args, **kwargs)
        if sql == 'COMMIT':
            self.after_commit()
        return result


class LocalFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.wall = self.mono = 10000
        self.owner = Context('freshness-owner', 'simulation:local')
        self.runtime = Runtime(self.directory.name, create=True, owner=self.owner,
            wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.addCleanup(self.runtime.close)
        self.adapter = self.runtime.adapters['simulator:local']
        self.namespace = self.runtime.request(self.owner, 'namespace', {'expiresUnixMs': 100000})['token']

    def advance(self, delay):
        self.wall += delay
        self.mono += delay

    def operation(self, *, max_run=5000, completion=30000):
        prepared = self.runtime.request(self.owner, 'prepare', {
            'instanceId': 'sim:home-fan', 'actionId': 'set_level',
            'arguments': {'level': 37, 'unit': 'percent'}, 'operationKey': 'freshness:fan',
            'replayNamespace': self.namespace, 'requiredEffect': 'capability_completion',
            'timing': {'notBeforeUnixMs': 10000, 'latestStartUnixMs': min(20000, completion),
                       'maxRunMs': max_run, 'latestCompletionUnixMs': completion}})
        return self.runtime.request(self.owner, 'invoke', {'request': prepared['request']})

    def status(self, operation):
        return self.runtime.request(self.owner, 'operation', {'operationId': operation['operationId']})

    @contextmanager
    def commit_delay(self, *, delay=1100, every=False):
        journal = self.runtime.journal
        original = journal._db
        fired = []

        def committed():
            if every or not fired:
                fired.append(True)
                self.advance(delay)

        with patch.object(journal, '_db', CommitClock(original, committed)):
            yield fired

    def assert_no_effect(self, operation):
        status = self.status(operation)
        self.assertNotEqual(status['executionState'], 'completed', status)
        self.assertEqual(self.adapter.plant.observe('sim:home-fan')['effectCount'], 0)
        return status

    def test_expiry_checkpoint_delay_is_sampled_before_dispatch(self):
        operation = self.operation()
        original = self.runtime.expire_unstarted

        def delayed_expiry(adapter_id):
            with self.commit_delay() as fired:
                result = original(adapter_id)
            self.assertEqual(len(fired), 1)
            return result

        self.advance(1)
        with patch.object(self.runtime, 'expire_unstarted', delayed_expiry):
            self.adapter.tick()
        self.assertEqual(self.status(operation)['executionState'], 'running')
        self.advance(100)
        self.adapter.tick()
        self.assertEqual(self.status(operation)['executionState'], 'completed')
        self.assertEqual(self.adapter.plant.observe('sim:home-fan')['effectCount'], 1)

    def test_running_receipt_commit_delay_is_sampled_before_effect(self):
        operation = self.operation()
        original = self.runtime.journal.record_execution

        def delayed_running(ticket, state, evidence):
            if state == 'running':
                with self.commit_delay() as fired:
                    result = original(ticket, state, evidence)
                self.assertEqual(len(fired), 1)
                return result
            return original(ticket, state, evidence)

        with patch.object(self.runtime.journal, 'record_execution', delayed_running):
            self.adapter.tick()
        self.assertEqual(self.status(operation)['executionState'], 'completed')
        self.assertEqual(self.adapter.plant.observe('sim:home-fan')['effectCount'], 1)

    def test_snapshot_publication_delay_remains_stale_and_never_dispatches(self):
        operation = self.operation()
        original = self.runtime.registry.report_adapter_snapshot

        def delayed_publication(*args, **kwargs):
            with self.commit_delay():
                return original(*args, **kwargs)

        self.advance(200)
        with patch.object(self.runtime.registry, 'report_adapter_snapshot', delayed_publication):
            self.adapter.tick()
        status = self.assert_no_effect(operation)
        self.assertEqual(status['executionState'], 'rejected_before_dispatch')
        self.assertFalse(status['mayHaveActed'])
        self.assertIsNone(self.adapter.plant.receipt(operation['operationId']))

    def test_slow_effect_authority_checkpoint_cannot_hide_max_run_expiry(self):
        operation = self.operation(max_run=500)
        self.adapter.tick()
        self.assertEqual(self.status(operation)['executionState'], 'running')
        self.advance(100)
        original = self.runtime.journal.authority_time

        def delayed_checkpoint():
            with self.commit_delay(delay=450):
                return original()

        with patch.object(self.runtime.journal, 'authority_time', delayed_checkpoint):
            self.adapter.tick()
        status = self.assert_no_effect(operation)
        self.assertEqual(status['result']['output']['reason'], 'execution_deadline')

    def test_slow_effect_authority_checkpoint_cannot_hide_wall_completion(self):
        operation = self.operation(completion=10500)
        self.adapter.tick()
        self.assertEqual(self.status(operation)['executionState'], 'running')
        self.advance(100)
        original = self.runtime.journal.authority_time

        def delayed_checkpoint():
            with self.commit_delay(delay=450):
                return original()

        with patch.object(self.runtime.journal, 'authority_time', delayed_checkpoint):
            self.adapter.tick()
        status = self.assert_no_effect(operation)
        self.assertEqual(status['result']['output']['reason'], 'execution_deadline')

    def test_slow_effect_authority_checkpoint_cannot_hide_shorter_lease(self):
        original_admit = self.runtime.policy.admit

        def short_lease(*args, **kwargs):
            return replace(original_admit(*args, **kwargs), lease_expires_ms=10500)

        with patch.object(self.runtime.policy, 'admit', short_lease):
            operation = self.operation()
        self.adapter.tick()
        self.assertEqual(self.status(operation)['executionState'], 'running')
        self.advance(100)
        original = self.runtime.journal.authority_time

        def delayed_checkpoint():
            with self.commit_delay(delay=450):
                return original()

        with patch.object(self.runtime.journal, 'authority_time', delayed_checkpoint):
            self.adapter.tick()
        status = self.assert_no_effect(operation)
        self.assertEqual(status['result']['output']['reason'], 'lease_expired')


if __name__ == '__main__':
    unittest.main()
