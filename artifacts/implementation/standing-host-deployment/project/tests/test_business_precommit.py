"""Real Journal business-commit checks; no device or worker effects."""
import json
import os
from pathlib import Path
import sqlite3
import threading
import tempfile
import unittest
from unittest.mock import patch

from hms.journal import Journal, JournalError
from journal_support import CONTEXT, TestPolicy, request


TABLES = ('operations', 'replay_keys', 'resource_floors', 'claims', 'events')


class _CommitReply:
    """Test-only connection proxy: one failure before or after actual COMMIT."""
    def __init__(self, connection, after):
        self.connection, self.after, self.armed = connection, after, True

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, *args):
        if sql == 'COMMIT' and self.armed:
            self.armed = False
            if self.after:
                self.connection.execute(sql, *args)
            raise OSError('injected commit reply failure')
        return self.connection.execute(sql, *args)


class BusinessCommitTests(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get('HMS_PRECOMMIT_TEST_ROOT')
        if retained is None:
            temporary = tempfile.TemporaryDirectory(prefix='hms-precommit-')
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        else:
            self.root = Path(retained) / self._testMethodName
            self.root.mkdir(mode=0o700)
        self.now = 1000
        self.policy = TestPolicy()
        self.journal = Journal(self.root/'authority.db', self.policy, clock_ms=lambda: self.now, create=True)
        self.namespace = self.journal.issue_namespace(CONTEXT, 4000)['token']
        self.wire = request(self.namespace)
        self.trace, self.calls = [], []
        self.journal._db.set_trace_callback(self.trace.append)

    def tearDown(self):
        counts = self.counts()
        self.assertIsNone(self.journal._commit_checks)
        self.assertFalse(self.journal._db.in_transaction)
        retained = dict(counts=counts, calls=self.calls, trace=self.trace,
            authority=self.journal.authority_id, floor=self.journal._meta('last_clock'),
            inTransaction=False, checkStateCleared=True)
        self.journal.close()
        with (self.root/'observations.json').open('x') as stream:
            json.dump(retained, stream, indent=2); stream.write('\n')

    def counts(self):
        return {name:len(self.journal._db.execute('SELECT * FROM '+name+' LIMIT 1024').fetchall()) for name in TABLES}

    def empty(self):
        self.assertEqual(self.counts(), dict.fromkeys(TABLES, 0))

    def code(self, expected, function, *args):
        with self.assertRaises(JournalError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, expected)

    def submit(self):
        return self.journal.submit(CONTEXT, self.wire)

    def arm(self, check):
        original = self.policy.admit
        def admit(*args):
            admission = original(*args)
            self.journal._require_at_commit(check)
            return admission
        self.policy.admit = admit

    def record(self):
        self.calls.append('checked')

    def late(self, action):
        original = self.journal._event
        def event(*args):
            original(*args)
            action()
        self.journal._event = event

    def test_check_sees_complete_admission_and_precedes_commit(self):
        def check():
            self.assertEqual(self.counts(), dict.fromkeys(TABLES, 1))
            self.assertTrue(self.journal._db.in_transaction)
            self.trace.append('CHECK_FINISHED')
            self.record()
        self.arm(check)
        result = self.submit()
        self.assertEqual(result['state'], 'accepted')
        self.assertEqual(self.calls, ['checked'])
        position = self.trace.index('CHECK_FINISHED')
        self.assertEqual(self.trace[position + 1], 'COMMIT')

    def test_valid_early_but_invalid_at_commit_rolls_back_every_business_row(self):
        valid = [True]
        def check():
            self.record()
            if not valid[0]:
                raise JournalError('EVIDENCE_EXPIRED')
        check()
        self.arm(check)
        self.late(lambda: valid.__setitem__(0, False))
        self.code('EVIDENCE_EXPIRED', self.submit)
        self.empty()
        self.assertEqual(self.calls, ['checked', 'checked'])

    def test_floor_commit_survives_business_refusal(self):
        self.now = 1200
        def refuse():
            self.record()
            raise JournalError('EVIDENCE_EXPIRED')
        self.arm(refuse)
        self.code('EVIDENCE_EXPIRED', self.submit)
        self.empty()
        self.assertEqual(self.journal._meta('last_clock'), '1200')
        self.assertEqual(self.calls, ['checked'])
        self.assertEqual(self.trace.count('COMMIT'), 1)
        self.assertEqual(self.trace.count('ROLLBACK'), 1)
        self.now = 1100
        self.code('CLOCK_REGRESSION', self.submit)

    def test_registration_survives_clock_floor_transaction_restart(self):
        self.now = 1200
        with self.journal._transaction():
            self.journal._require_at_commit(self.record)
            self.assertEqual(self.journal._now(), 1200)
            self.assertEqual(self.calls, [])
            self.journal._set_meta('test', 'ignored missing row')
        self.assertEqual(self.calls, ['checked'])
        self.assertEqual(self.trace.count('COMMIT'), 2)

    def test_observed_clock_retained_on_refused_recording_transaction(self):
        def refuse():
            self.record()
            raise JournalError('EVIDENCE_EXPIRED')
        with self.assertRaises(JournalError):
            with self.journal._transaction():
                self.journal._require_at_commit(refuse)
                self.now = 1500
                self.journal._record_now()
                self.journal._db.execute("INSERT INTO meta VALUES ('business','refused')")
        self.assertEqual(self.journal._meta('last_clock'), '1500')
        self.assertIsNone(self.journal._db.execute("SELECT value FROM meta WHERE key='business'").fetchone())
        self.assertEqual(self.calls, ['checked'])

    def test_body_exception_never_runs_commit_checks_and_next_scope_is_clean(self):
        with self.assertRaisesRegex(OSError, 'body'):
            with self.journal._transaction():
                self.journal._require_at_commit(self.record)
                raise OSError('body')
        self.assertEqual(self.calls, [])
        self.submit()
        self.assertEqual(self.calls, [])

    def test_check_baseexception_rolls_back_and_releases_scope(self):
        def interrupt():
            self.record()
            raise KeyboardInterrupt('test only')
        self.arm(interrupt)
        with self.assertRaises(KeyboardInterrupt):
            self.submit()
        self.empty()
        self.assertIsNone(self.journal._commit_checks)

    def test_same_callable_registration_is_idempotent(self):
        callback = self.record
        with self.journal._transaction():
            for _ in range(100):
                self.journal._require_at_commit(callback)
        self.assertEqual(self.calls, ['checked'])

    def test_multiple_checks_run_in_registration_order(self):
        with self.journal._transaction():
            for number in range(64):
                self.journal._require_at_commit(lambda number=number: self.calls.append(number))
        self.assertEqual(self.calls, list(range(64)))

    def test_swallowed_registration_limit_taints_transaction(self):
        with self.assertRaises(JournalError) as caught:
            with self.journal._transaction():
                for _ in range(64):
                    self.journal._require_at_commit(lambda: None)
                self.code('COMMIT_CHECK_LIMIT', self.journal._require_at_commit, lambda: None)
                self.journal._db.execute("INSERT INTO meta VALUES ('business','refused')")
        self.assertEqual(caught.exception.code, 'COMMIT_CHECK_IMPURE')
        self.assertIsNone(self.journal._db.execute("SELECT value FROM meta WHERE key='business'").fetchone())

    def test_invalid_registration_cannot_be_swallowed_into_commit(self):
        with self.assertRaises(JournalError) as caught:
            with self.journal._transaction():
                self.code('COMMIT_CHECK_INVALID', self.journal._require_at_commit, None)
        self.assertEqual(caught.exception.code, 'COMMIT_CHECK_IMPURE')

    def test_outside_transaction_registration_refused(self):
        self.code('COMMIT_CHECK_TRANSACTION_REQUIRED', self.journal._require_at_commit, self.record)
        self.submit()
        self.assertEqual(self.calls, [])

    def test_other_thread_cannot_register_into_owner_transaction(self):
        started, finished = threading.Event(), threading.Event()
        result = []
        def other():
            started.set()
            try:
                self.journal._require_at_commit(self.record)
            except JournalError as error:
                result.append(error.code)
            finally:
                finished.set()
        with self.journal._transaction():
            worker = threading.Thread(target=other)
            worker.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.is_set())
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ['COMMIT_CHECK_TRANSACTION_REQUIRED'])
        self.assertEqual(self.calls, [])

    def test_non_none_result_is_not_success(self):
        self.arm(lambda: True)
        self.code('COMMIT_CHECK_INVALID_RESPONSE', self.submit)
        self.empty()

    def test_swallowed_sql_write_and_transaction_attempts_cannot_commit(self):
        statements = ["INSERT INTO meta VALUES ('bad','write')", "UPDATE meta SET value=value",
            "DELETE FROM meta WHERE key='absent'", 'COMMIT', 'ROLLBACK', 'SAVEPOINT injected',
            'BEGIN', 'PRAGMA user_version', "ATTACH DATABASE ':memory:' AS other",
            'CREATE TEMP TABLE extra(a)', 'SELECT random()']
        for sql in statements:
            with self.subTest(sql=sql):
                def check():
                    try:
                        self.journal._db.execute(sql).fetchall()
                    except sqlite3.DatabaseError:
                        self.calls.append(sql)
                self.policy = TestPolicy()
                self.journal.policy = self.policy
                self.arm(check)
                self.code('COMMIT_CHECK_IMPURE', self.submit)
                self.empty()
        self.assertEqual(self.calls, statements)

    def test_bounded_main_reads_and_metadata_functions_allowed(self):
        def check():
            row = self.journal._db.execute('SELECT typeof(intent),length(intent) FROM main.operations LIMIT 1').fetchone()
            self.assertEqual(row[0], 'blob')
            self.assertGreater(row[1], 1)
            self.record()
        self.arm(check)
        self.submit()
        self.assertEqual(self.calls, ['checked'])

    def test_temp_reads_denied_even_when_swallowed(self):
        self.journal._db.execute('CREATE TEMP TABLE untrusted(a)')
        def check():
            try:
                self.journal._db.execute('SELECT a FROM temp.untrusted').fetchall()
            except sqlite3.DatabaseError:
                self.record()
        self.arm(check)
        self.code('COMMIT_CHECK_IMPURE', self.submit)
        self.empty()

    def test_swallowed_reentry_close_clock_and_registration_refused(self):
        def transaction():
            with self.journal._transaction():
                self.fail('reentered')
        actions = [transaction, self.journal.close, self.journal._clock,
            self.journal._check_business_commit, lambda: self.journal._require_at_commit(self.record)]
        for action in actions:
            with self.subTest(action=action.__name__):
                def check():
                    self.code('COMMIT_CHECK_REENTRANCY', action)
                self.policy = TestPolicy()
                self.journal.policy = self.policy
                self.arm(check)
                self.code('COMMIT_CHECK_IMPURE', self.submit)
                self.empty()

    def test_commit_failure_before_sql_commit_rolls_back(self):
        self.arm(self.record)
        self.journal._db = _CommitReply(self.journal._db, False)
        with self.assertRaisesRegex(OSError, 'reply'):
            self.submit()
        self.empty()
        self.assertEqual(self.calls, ['checked'])
        self.assertFalse(self.journal._poisoned)

    def test_lost_reply_after_commit_replays_original_without_rechecking(self):
        self.arm(self.record)
        self.journal._db = _CommitReply(self.journal._db, True)
        with self.assertRaisesRegex(OSError, 'reply'):
            self.submit()
        self.assertEqual(self.counts(), dict.fromkeys(TABLES, 1))
        operation = self.journal._db.execute('SELECT id FROM operations').fetchone()[0]
        def forbidden(*args):
            self.fail('original key replay must not readmit')
        self.policy.admit = forbidden
        self.journal.clock_ms = forbidden
        self.assertEqual(self.submit()['id'], operation)
        self.assertEqual(self.calls, ['checked'])

    def test_cold_original_key_replay_does_not_install_old_checks(self):
        self.arm(self.record)
        first = self.submit()
        self.journal.close()
        self.journal = Journal(self.root/'authority.db', self.policy, clock_ms=lambda: self.now)
        self.policy.denied.add('invoke')
        self.assertEqual(self.submit()['id'], first['id'])
        self.assertEqual(self.calls, ['checked'])
        self.assertEqual(self.counts(), dict.fromkeys(TABLES, 1))

    def test_readonly_guard_removed_after_success_and_refusal(self):
        self.arm(self.record)
        first = self.submit()
        self.journal.request_cancel(CONTEXT, first['id'])
        self.assertEqual(self.journal.status(CONTEXT, first['id'])['state'], 'canceled')
        def refuse():
            raise JournalError('EXPIRED')
        self.arm(refuse)
        self.wire = request(self.namespace, 'second')
        self.code('EXPIRED', self.submit)
        with self.journal._transaction():
            self.journal._db.execute("INSERT INTO meta VALUES ('after','available')")
        self.assertEqual(self.journal._meta('after'), 'available')

    def test_existing_evidence_authorizer_scope_is_not_replaced(self):
        self.arm(self.record)
        marker = {'denied': False}
        self.late(lambda: setattr(self.journal, '_pat_evidence_guard', marker))
        try:
            self.code('COMMIT_CHECK_TRANSACTION_REQUIRED', self.submit)
            self.empty()
            self.assertEqual(self.calls, [])
            self.assertIs(self.journal._pat_evidence_guard, marker)
        finally:
            self.journal._pat_evidence_guard = None

    def test_nested_catalog_verifier_cannot_replace_commit_authorizer(self):
        from types import SimpleNamespace
        from hms.pat_catalog import PatCatalog
        catalog = object.__new__(PatCatalog)
        catalog.journal, catalog._db = self.journal, self.journal._db
        evaluator = SimpleNamespace(verify_evidence=lambda *args: self.fail('nested verifier entered'))
        def check():
            self.code('PAT_EVIDENCE_REENTRANT', catalog._verify_evidence, evaluator, CONTEXT, {})
            # Even after swallowing the nested failure, COMMIT remains denied.
            with self.assertRaises(sqlite3.DatabaseError):
                self.journal._db.execute('COMMIT')
            self.record()
        self.arm(check)
        self.code('COMMIT_CHECK_IMPURE', self.submit)
        self.empty()
        self.assertEqual(self.calls, ['checked'])
        self.assertIsNone(self.journal._pat_evidence_guard)

