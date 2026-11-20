"""Original simulation start boundaries, exact refusal replay and process loss."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hms.journal import Context, JournalError
from hms.runtime import Runtime
from test_local_freshness import StatementClock


OWNER = Context('start-owner', 'simulation:local')


def prepare(runtime, namespace):
    return runtime.request(OWNER, 'prepare', {
        'instanceId': 'sim:home-fan', 'actionId': 'set_level',
        'arguments': {'level': 37, 'unit': 'percent'},
        'operationKey': 'start:one', 'replayNamespace': namespace,
        'requiredEffect': 'capability_completion',
        'timing': {'notBeforeUnixMs': 4999, 'latestStartUnixMs': 5000,
                   'maxRunMs': 4000, 'latestCompletionUnixMs': 20000}})['request']


class LocalStartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.wall = self.mono = 4999
        self.runtime = Runtime(self.directory.name, create=True, owner=OWNER,
            wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.addCleanup(self.runtime.close)
        self.adapter = self.runtime.adapters['simulator:local']
        namespace = self.runtime.request(OWNER, 'namespace', {'expiresUnixMs': 30000})['token']
        self.request = prepare(self.runtime, namespace)
        self.operation = self.runtime.request(OWNER, 'invoke', {'request': self.request})

    def advance(self, delay=2000):
        self.wall += delay
        self.mono += delay

    def status(self):
        return self.runtime.request(OWNER, 'operation', {'operationId': self.operation['operationId']})

    def assert_excluded(self, reason):
        status = self.status()
        self.assertEqual(status['executionState'], 'rejected_before_start')
        self.assertFalse(status['mayHaveActed'])
        self.assertEqual(status['resourceClaims'], [])
        self.assertEqual(status['cancellationState'], 'not_requested')
        self.assertIsNone(status['result'])
        receipt = self.adapter.plant.receipt(status['operationId'])
        self.assertEqual(receipt['state'], 'canceled')
        self.assertEqual(receipt['result'], {'reason': reason, 'effectCommitted': False, 'startExcluded': True})
        self.assertEqual(self.adapter.plant.observe('sim:home-fan')['effectCount'], 0)
        self.assertEqual(self.adapter.plant.db.execute('SELECT count(*) FROM fences').fetchone()[0], 0)
        events = self.runtime.journal.events(OWNER, status['operationId'])['events']
        self.assertFalse(any(event['payload'].get('state') == 'running' for event in events))
        self.assertTrue(any('start_excluded' in event['payload'].get('hms_qualification.evidence', {}).get('assertions', [])
                            for event in events))
        floors = [tuple(row) for row in self.runtime.journal._db.execute('SELECT * FROM resource_floors')]
        self.assertEqual(self.runtime.request(OWNER, 'invoke', {'request': self.request}), status)
        self.assertEqual([tuple(row) for row in self.runtime.journal._db.execute('SELECT * FROM resource_floors')], floors)

    def test_claim_commit_delay_excludes_late_start_without_new_fence_or_effect(self):
        original = self.runtime.journal.claim_dispatch

        def delayed_claim(*args, **kwargs):
            with patch.object(self.runtime.journal, '_db',
                    StatementClock(self.runtime.journal._db, self.advance)):
                return original(*args, **kwargs)

        with patch.object(self.runtime.journal, 'claim_dispatch', delayed_claim):
            self.adapter.tick()
        self.assert_excluded('start_deadline')

    def test_plant_begin_delay_excludes_late_start(self):
        with patch.object(self.adapter.plant, 'db',
                StatementClock(self.adapter.plant.db, self.advance, 'BEGIN IMMEDIATE')):
            self.adapter.tick()
        self.assert_excluded('start_deadline')

    def test_delay_in_start_policy_check_is_vetoed_by_final_start_clock(self):
        original = self.runtime.policy.recheck

        def delayed_check(context, operation, now):
            result = original(context, operation, now)
            if operation['state'] == 'dispatching':
                self.advance()
            return result

        with patch.object(self.runtime.policy, 'recheck', delayed_check):
            self.adapter.tick()
        self.assert_excluded('start_deadline')

    def test_grant_revocation_after_claim_is_checked_before_pending_registration(self):
        self.runtime.registry.grant(OWNER, OWNER.principal, 'sim:home-fan', 'read')
        original = self.runtime.journal.claim_dispatch

        def claim_then_revoke(*args, **kwargs):
            ticket = original(*args, **kwargs)
            # Model a trusted authority change in the handoff gap. Explicit
            # read access remains so exact result replay is still authorized.
            self.runtime.registry.grant(OWNER, OWNER.principal, '*', 'admin', enabled=False)
            return ticket

        with patch.object(self.runtime.journal, 'claim_dispatch', claim_then_revoke):
            self.adapter.tick()
        self.assert_excluded('authority_or_precondition_lost')

    def test_start_before_latest_start_can_complete_afterward(self):
        original = self.adapter._start_guard
        called = []

        def checked_guard(*args):
            called.append(True)
            self.assertTrue(self.adapter.plant.db.in_transaction)
            self.assertFalse(self.runtime.journal._db.in_transaction)
            return original(*args)

        with patch.object(self.adapter, '_start_guard', checked_guard):
            self.adapter.tick()
        self.assertEqual(len(called), 1)
        self.assertEqual(self.status()['executionState'], 'running')
        self.advance(100)
        self.adapter.tick()
        self.assertEqual(self.status()['executionState'], 'completed')
        self.assertEqual(self.adapter.plant.observe('sim:home-fan')['effectCount'], 1)

    def test_invalid_wall_clock_at_start_is_explicitly_excluded(self):
        with patch.object(self.adapter.plant, 'db', StatementClock(self.adapter.plant.db,
                lambda: setattr(self, 'wall', True), 'BEGIN IMMEDIATE')):
            self.adapter.tick()
        self.assert_excluded('clock_authority_lost')
        self.assertEqual(int(self.runtime.journal._meta('last_clock')), 4999)

    def test_regressed_wall_clock_at_start_is_explicitly_excluded(self):
        with patch.object(self.adapter.plant, 'db', StatementClock(self.adapter.plant.db,
                lambda: setattr(self, 'wall', 3999), 'BEGIN IMMEDIATE')):
            self.adapter.tick()
        self.assert_excluded('clock_authority_lost')
        self.assertEqual(int(self.runtime.journal._meta('last_clock')), 4999)

    def test_invalid_monotonic_mapping_at_start_is_explicitly_excluded(self):
        with patch.object(self.adapter.plant, 'db', StatementClock(self.adapter.plant.db,
                lambda: setattr(self, 'mono', True), 'BEGIN IMMEDIATE')):
            self.adapter.tick()
        self.assert_excluded('clock_authority_lost')

    def test_guard_exception_keeps_unknown_identity_without_receipt_or_new_start(self):
        with patch.object(self.adapter, '_start_guard', side_effect=RuntimeError('guard fault')):
            self.adapter.tick()
        status = self.status()
        self.assertEqual(status['executionState'], 'outcome_unknown')
        self.assertTrue(status['mayHaveActed'])
        self.assertTrue(status['resourceClaims'])
        self.assertIsNone(self.adapter.plant.receipt(status['operationId']))
        self.assertEqual(self.adapter.plant.db.execute('SELECT count(*) FROM fences').fetchone()[0], 0)
        self.adapter.tick()
        self.assertEqual(self.status()['executionState'], 'outcome_unknown')
        self.assertEqual(self.runtime.request(OWNER, 'invoke', {'request': self.request})['operationId'], status['operationId'])
        self.assertEqual(self.adapter.plant.observe('sim:home-fan')['effectCount'], 0)

    def test_malformed_no_start_markers_never_become_exclusion_evidence(self):
        operation = self.runtime.journal._operation(self.operation['operationId'])
        valid = {'digest': operation['digest'], 'intent': operation['intent'], 'state': 'canceled',
                 'result': {'reason': 'start_deadline', 'effectCommitted': False, 'startExcluded': True}}
        cases = [('state', 'pending'), ('state', 'completed'), ('effectCommitted', 0),
                 ('effectCommitted', True), ('startExcluded', 1), ('startExcluded', False), ('reason', 1)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                receipt = copy.deepcopy(valid)
                target = receipt if field == 'state' else receipt['result']
                target[field] = value
                with self.assertRaisesRegex(JournalError, 'INVALID_SIMULATOR_RECEIPT'):
                    self.adapter._validate_receipt(operation, receipt)


def crash_worker(directory, phase='receipt'):
    clock = {'wall': 4999, 'mono': 4999}
    runtime = Runtime(directory, create=True, owner=OWNER,
        wall_clock_ms=lambda: clock['wall'], monotonic_ms=lambda: clock['mono'])
    adapter = runtime.adapters['simulator:local']
    namespace = runtime.request(OWNER, 'namespace', {'expiresUnixMs': 30000})['token']
    request = prepare(runtime, namespace)
    operation = runtime.request(OWNER, 'invoke', {'request': request})
    print(json.dumps({'request': request, 'operation': operation}), flush=True)
    original = adapter.plant.begin
    original_record = runtime.journal.record_execution

    def delay():
        clock['wall'] += 2000
        clock['mono'] += 2000

    def begin_then_die(*args, **kwargs):
        with patch.object(adapter.plant, 'db',
                StatementClock(adapter.plant.db, delay, 'BEGIN IMMEDIATE')):
            receipt = original(*args, **kwargs)
        if receipt['state'] == 'canceled' and receipt['result'].get('startExcluded') is True:
            if phase == 'receipt':
                os._exit(47)
            return receipt
        os._exit(48)

    def record_then_die(ticket, state, evidence):
        result = original_record(ticket, state, evidence)
        if phase == 'host_exclusion' and state == 'rejected_before_start':
            os._exit(57)
        return result

    with patch.object(adapter.plant, 'begin', begin_then_die), \
            patch.object(runtime.journal, 'record_execution', record_then_die):
        adapter.tick()
    os._exit(49)


class LocalStartProcessTests(unittest.TestCase):
    def test_process_loss_after_no_start_receipt_reconciles_exact_identity_after_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'state'
            completed = subprocess.run([sys.executable, __file__, '--crash-worker', str(directory)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 47, completed.stderr)
            payload = json.loads(completed.stdout)
            operation_id = payload['operation']['operationId']
            runtime = Runtime(directory, wall_clock_ms=lambda: 6999, monotonic_ms=lambda: 6999)
            try:
                adapter = runtime.adapters['simulator:local']
                status = runtime.request(OWNER, 'operation', {'operationId': operation_id})
                self.assertEqual(status['executionState'], 'outcome_unknown')
                self.assertTrue(status['resourceClaims'])
                receipt = adapter.plant.receipt(operation_id)
                self.assertEqual(receipt['result'], {'reason': 'start_deadline', 'effectCommitted': False, 'startExcluded': True})
                runtime.tick()
                status = runtime.request(OWNER, 'operation', {'operationId': operation_id})
                self.assertEqual(status['executionState'], 'rejected_before_start')
                self.assertFalse(status['mayHaveActed'])
                self.assertEqual(status['resourceClaims'], [])
                self.assertIsNone(status['result'])
                floors = [tuple(row) for row in runtime.journal._db.execute('SELECT * FROM resource_floors')]
                self.assertEqual(runtime.request(OWNER, 'invoke', {'request': payload['request']}), status)
                self.assertEqual([tuple(row) for row in runtime.journal._db.execute('SELECT * FROM resource_floors')], floors)
                self.assertEqual(adapter.plant.db.execute('SELECT count(*) FROM receipts').fetchone()[0], 1)
                self.assertEqual(adapter.plant.db.execute('SELECT count(*) FROM fences').fetchone()[0], 0)
                self.assertEqual(adapter.plant.observe('sim:home-fan')['effectCount'], 0)
            finally:
                runtime.close()

    def test_process_loss_after_host_exclusion_commit_has_no_stranded_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'state'
            completed = subprocess.run([
                sys.executable, __file__, '--crash-worker', str(directory), 'host_exclusion'],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 57, completed.stderr)
            payload = json.loads(completed.stdout)
            operation_id = payload['operation']['operationId']
            # Inspect the durable database BEFORE opening any runtime recovery
            # path. State, mayHaveActed and claim deletion share one commit.
            with sqlite3.connect('file:' + str(directory / 'authority.db') + '?mode=ro', uri=True) as database:
                row = database.execute('SELECT state,may_have_acted FROM operations WHERE id=?',
                                       (operation_id,)).fetchone()
                self.assertEqual(row, ('rejected_before_start', 0))
                self.assertEqual(database.execute('SELECT count(*) FROM claims WHERE operation_id=?',
                                                 (operation_id,)).fetchone()[0], 0)
            runtime = Runtime(directory, wall_clock_ms=lambda: 6999, monotonic_ms=lambda: 6999)
            try:
                adapter = runtime.adapters['simulator:local']
                status = runtime.request(OWNER, 'operation', {'operationId': operation_id})
                self.assertEqual(status['executionState'], 'rejected_before_start')
                self.assertFalse(status['mayHaveActed'])
                self.assertEqual(status['resourceClaims'], [])
                runtime.tick()
                self.assertEqual(runtime.request(OWNER, 'operation', {'operationId': operation_id}), status)
                self.assertEqual(runtime.request(OWNER, 'invoke', {'request': payload['request']}), status)
                self.assertEqual(adapter.plant.db.execute('SELECT count(*) FROM receipts').fetchone()[0], 1)
                self.assertEqual(adapter.plant.db.execute('SELECT count(*) FROM fences').fetchone()[0], 0)
                self.assertEqual(adapter.plant.observe('sim:home-fan')['effectCount'], 0)
            finally:
                runtime.close()


if __name__ == '__main__':
    if len(sys.argv) in {3, 4} and sys.argv[1] == '--crash-worker':
        crash_worker(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else 'receipt')
    else:
        unittest.main()
