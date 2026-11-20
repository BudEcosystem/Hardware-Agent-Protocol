"""Multiple logical runs and retained well-formed history forgeries."""
import hashlib
import json
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from test_io_service_execution import IoServiceExecutionTests
from test_io_service_runs import business
import io_service_execution as execution


class IoServiceExecutionHistoryTests(IoServiceExecutionTests):
    def pair(self):
        first = self.associated()
        settled = self.service.recover(self.owner, self.config['evaluatorId'], 'run:1')
        self.assertEqual(settled['attempt']['record']['state'], 'archived')
        second_reservation = self.reserve(run='run:2')
        def launch(row, bundle):
            joined = self.service.lookup(self.owner, self.config['evaluatorId'], 'run:2')
            receipt = joined['association']['receipt']
            self.assertEqual(receipt['sequence'], 2)
            self.assertEqual(receipt['previousHandoffDigest'], first['association']['receiptDigest'])
            self.assertEqual(receipt['reservationDigest'], second_reservation['reservationDigest'])
            self.assertEqual(receipt['attemptId'], row['record']['attemptId'])
            self.assertNotEqual(row['record']['attemptId'], first['attempt']['record']['attemptId'])
            self.assertEqual(bundle, second_reservation['preparedRun']['bundle'])
            self.assertEqual(self.sizes(), (2, 2)); self.assertFalse(self.db.in_transaction)
            return row
        with patch.object(self.bound, '_launch', side_effect=launch) as observed:
            second = self.service.execute(self.owner, self.config['evaluatorId'], 'run:2',
                runtime=self.runtime, installed_configuration=self.config)
        self.assertEqual(observed.call_count, 1)
        self.assertEqual(business(self.runtime), self.before_business)
        self.emit('history-baseline', dict(first=settled, second=second,
            firstReservationDigest=self.original['reservationDigest'], secondReservationDigest=second_reservation['reservationDigest'],
            launchBoundarySubstituted=True, actualWorkerExecuted=False))
        return settled, second

    def fingerprint(self):
        return hashlib.sha256(canonical([list(row) for row in self.db.execute(
            'SELECT sequence,evaluator,run,hex(receipt) FROM iose_handoffs ORDER BY sequence')])).hexdigest()

    def refusal(self):
        before = self.fingerprint()
        with self.assertRaises(JournalError): self.lookup()
        with self.assertRaises(JournalError):
            execution.IoServiceExecutionStore(self.runs, self.bound, create=True, owner=self.owner)
        after = self.fingerprint(); self.assertEqual(before, after)
        self.emit('history-refusal', dict(before=before, after=after, reset=False, handoffs=2, supervisorAttempts=2))

    def change_second(self, mutate):
        self.pair()
        receipt = json.loads(self.db.execute('SELECT receipt FROM iose_handoffs WHERE sequence=2').fetchone()[0])
        mutate(receipt)
        self.db.execute('UPDATE iose_handoffs SET receipt=? WHERE sequence=2', (canonical(receipt),))
        self.refusal()

    def test_two_logical_runs_keep_distinct_attempts_and_chain_on_reopen(self):
        first, second = self.pair(); self.reopened(runtime=True)
        with patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('relaunch')):
            old = self.service.execute(self.owner, self.config['evaluatorId'], 'run:1')
            recent = self.service.execute(self.owner, self.config['evaluatorId'], 'run:2')
        self.assertEqual(old, first)
        self.assertEqual(recent['association'], second['association'])
        self.assertEqual(recent['attempt']['record']['attemptId'], second['attempt']['record']['attemptId'])
        self.assertEqual(recent['attempt']['record']['state'], 'interrupted')
        self.assertEqual(self.sizes(), (2, 2))
        self.emit('history-replay', dict(first=old, second=recent, noNewLaunch=True, actualWorkerExecuted=False))

    def test_well_formed_second_receipt_cannot_forge_previous_link(self):
        self.change_second(lambda receipt: receipt.update(previousHandoffDigest='sha256:'+'0'*64))

    def test_second_run_cannot_borrow_first_attempt_id(self):
        self.pair()
        first, second = [json.loads(row[0]) for row in self.db.execute('SELECT receipt FROM iose_handoffs ORDER BY sequence')]
        second['attemptId'] = first['attemptId']
        self.db.execute('UPDATE iose_handoffs SET receipt=? WHERE sequence=2', (canonical(second),))
        self.refusal()

    def test_later_handoff_cannot_move_time_before_prior_receipt(self):
        self.change_second(lambda receipt: receipt.update(committedAtUnixMs=999))

    def test_reordering_committed_rows_is_not_a_new_valid_history(self):
        self.pair()
        with self.runtime.journal._transaction():
            self.db.execute('UPDATE iose_handoffs SET sequence=3 WHERE sequence=1')
            self.db.execute('UPDATE iose_handoffs SET sequence=1 WHERE sequence=2')
            self.db.execute('UPDATE iose_handoffs SET sequence=2 WHERE sequence=3')
        self.refusal()
