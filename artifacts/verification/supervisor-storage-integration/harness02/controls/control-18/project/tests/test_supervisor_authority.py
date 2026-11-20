"""Versioned store identity and retained refusal fixtures; no producer launch."""
import hashlib
import os
from pathlib import Path
import unittest

from hms.contracts import canonical
from hms.journal import JournalError
from test_io_supervisor_contracts import IoSupervisorContractsTests, contracts
from hms_qualification.supervisor.attempt_ledger import AttemptLedger
from hms_qualification.supervisor.authority_ledger import AuthorityAttemptLedger
from hms_qualification.supervisor.io_service_execution import BoundQualificationSupervisor


class SupervisorAuthorityTests(IoSupervisorContractsTests):
    def setUp(self):
        self.parent = Path(os.environ['TMPDIR'])/self._testMethodName
        self.parent.mkdir(mode=0o700)

    def ledger(self, label='supervisor', **options):
        value = AuthorityAttemptLedger(self.parent/label, **options)
        self.addCleanup(value.close)
        return value

    def preserved(self, ledger, callback):
        path = ledger.root/'attempts.db'
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(JournalError): callback()
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        (self.parent/'refusal.json').write_bytes(canonical(dict(before=before, after=after, reset=False)))

    def test_generated_identity_is_unique_and_reopen_is_exact(self):
        first = self.ledger(create=True); identity = first.authority_id
        second = self.ledger('other', create=True)
        self.assertNotEqual(identity, second.authority_id)
        first.close(); reopened = self.ledger(expected_authority=identity)
        self.assertEqual(reopened.authority_id, identity)
        self.assertEqual(reopened.db.execute('SELECT version,authority FROM qs_meta').fetchall(), [(2, identity)])

    def test_create_identity_cannot_be_supplied_and_missing_reopen_does_not_create(self):
        with self.assertRaisesRegex(JournalError, 'CREATE_OPTIONS'):
            self.ledger(create=True, expected_authority='supervisor:'+'1'*32)
        for value in (None, '', True, 'supervisor:'+'X'*32):
            with self.assertRaises(JournalError): self.ledger(expected_authority=value)
        self.assertFalse((self.parent/'supervisor').exists())
        with self.assertRaises(JournalError): self.ledger(expected_authority='supervisor:'+'1'*32)
        self.assertFalse((self.parent/'supervisor').exists())

    def test_legacy_and_authority_profiles_refuse_each_others_store(self):
        legacy = AttemptLedger(self.parent/'legacy', create=True); legacy.close()
        with self.assertRaises(JournalError): self.ledger('legacy', expected_authority='supervisor:'+'1'*32)
        bound = self.ledger(create=True); bound.close()
        with self.assertRaisesRegex(JournalError, 'SCHEMA_INVALID'):
            AttemptLedger(self.parent/'supervisor')

    def test_wrong_reopen_identity_does_not_interrupt_existing_admission(self):
        value = self.ledger(create=True); row, _ = value.admit(self.request)
        identity = value.authority_id; value.close()
        wrong = 'supervisor:' + ('0'*32 if identity != 'supervisor:'+'0'*32 else '1'*32)
        path = self.parent/'supervisor/attempts.db'; before = path.read_bytes()
        with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'): self.ledger(expected_authority=wrong)
        self.assertEqual(path.read_bytes(), before)
        reopened = self.ledger(expected_authority=identity)
        self.assertEqual(reopened.get(row['record']['attemptId'])['record']['history'], ['admitted', 'interrupted'])

    def test_reopening_active_attempt_interrupts_once_and_never_resumes(self):
        value = self.ledger(create=True); row, _ = value.admit(self.request); identity = value.authority_id
        value.close(); value = self.ledger(expected_authority=identity)
        retained = value.get(row['record']['attemptId'])
        self.assertEqual(retained['record']['reason'], 'OWNER_LOST')
        self.assertEqual(retained['record']['history'], ['admitted', 'interrupted'])
        value.close(); value = self.ledger(expected_authority=identity)
        self.assertEqual(value.get(row['record']['attemptId']), retained)
        self.assertFalse((value.root/row['record']['attemptId']).exists())

    def test_create_existing_authority_refuses_without_reset(self):
        value = self.ledger(create=True); value.admit(self.request); value.close()
        path = self.parent/'supervisor/attempts.db'; before = path.read_bytes()
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'): self.ledger(create=True)
        self.assertEqual(path.read_bytes(), before)

    def test_changed_open_metadata_is_checked_even_for_absent_run(self):
        value = self.ledger(create=True)
        value.db.execute('UPDATE qs_meta SET authority=?', ('supervisor:'+'a'*32,))
        self.preserved(value, lambda: value.lookup('deployment', 'eval', 'absent'))

    def test_multibyte_identity_is_bounded_before_fetch(self):
        value = self.ledger(create=True)
        value.db.execute('UPDATE qs_meta SET authority=?', ('😀'*43,))
        self.preserved(value, lambda: value.authority_id)

    def test_added_trigger_is_not_trusted_on_lookup(self):
        value = self.ledger(create=True)
        value.db.execute('CREATE TRIGGER unexpected AFTER DELETE ON qs_attempts BEGIN SELECT 1; END')
        self.preserved(value, lambda: value.lookup('deployment', 'eval', 'absent'))

    def test_temporary_metadata_shadow_refuses(self):
        value = self.ledger(create=True)
        value.db.execute('CREATE TEMP TABLE qs_meta(version,authority)')
        self.preserved(value, lambda: value.authority_id)

    def test_partial_metadata_never_reinitializes(self):
        value = self.ledger(create=True); identity = value.authority_id
        value.db.execute('DROP TABLE qs_meta'); value.close()
        path = self.parent/'supervisor/attempts.db'; before = path.read_bytes()
        for options in (dict(create=True), dict(expected_authority=identity)):
            with self.assertRaises(JournalError): self.ledger(**options)
        self.assertEqual(path.read_bytes(), before)

    def test_owner_lease_remains_exclusive(self):
        value = self.ledger(create=True)
        with self.assertRaisesRegex(JournalError, 'OWNER_BUSY'):
            self.ledger(expected_authority=value.authority_id)

    def test_bound_supervisor_refuses_unassociated_legacy_execute(self):
        value = BoundQualificationSupervisor(self.parent/'supervisor', create=True)
        self.addCleanup(value.close)
        with self.assertRaisesRegex(JournalError, 'BOUND_SERVICE_REQUIRED'):
            value.execute(self.request, self.bundle)
        self.assertEqual(value.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (0,))
