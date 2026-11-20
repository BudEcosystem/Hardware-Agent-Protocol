"""Authority/publication controls using a declared substitute semantic oracle.

No worker executes. These tests do not establish physical or actual-matrix
success; the inherited real reducer and vault bytes are unchanged.
"""
from pathlib import Path
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, JournalError
from hms_qualification.evidence import archive, reducer
from hms_qualification.evidence_vault import EvidenceVault, descriptor
from hms_qualification.evidence_authority import VaultEvidenceStore
from hms_qualification.evidence_authority import contracts as c
from test_io_evidence_import import IoEvidenceImportTests


class VaultAuthorityTests(IoEvidenceImportTests):
    def store(self, **options):
        folder = self.parent / 'vault'
        folder.mkdir(mode=0o700)
        self.expected_vault = descriptor(self.runtime.journal.authority_id,
            max_pages=options.pop('vault_pages', 2048))
        self.vault = EvidenceVault(folder / 'hms_qualification.evidence.db', self.expected_vault, create=True)
        self.addCleanup(self.vault.close)
        self.evidence = VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner, **options)
        return self.evidence

    def sizes_evidence(self):
        return tuple(self.db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
            for name in ('evi_intents', 'evi_publications')) + (
            self.vault._db.execute('SELECT count(*) FROM ev_manifests').fetchone()[0],)

    def pending(self):
        return self.evidence.pending(self.owner, self.config['evaluatorId'], 'run:1')

    def assert_preserved(self, expected):
        self.assertEqual(self.sizes_evidence(), expected)
        self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(self.bound._owned, {})
        self.emit('retained-state', dict(intents=expected[0], publications=expected[1], manifests=expected[2],
            workerExecuted=False, semanticsVerified=False, attemptId=self.fixture_root.name,
            pending=self.pending(), authorityId=self.runtime.journal.authority_id,
            storeId=self.expected_vault['storeId'], physicalCapacityReserved=False))

    def interrupt(self, phase):
        def checkpoint(current, value):
            if current == phase:
                self.emit('interruption', dict(phase=phase, value=value))
                raise RuntimeError('publication interruption')
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(RuntimeError, 'publication interruption'):
                self.import_fixture()

    def test_mount_requires_real_authority_and_admin_and_exact_vault(self):
        self.create()
        parent = self.parent / 'wrong-vault'; parent.mkdir(mode=0o700)
        wrong = EvidenceVault(parent / 'hms_qualification.evidence.db', descriptor('0' * 32), create=True)
        self.addCleanup(wrong.close)
        with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'):
            VaultEvidenceStore(self.service, wrong, create=True, owner=self.owner)
        for value in ({}, self.bound, self.runtime.journal):
            with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'):
                VaultEvidenceStore(value, wrong)
        self.store()
        for value in ({}, self.vault._path, self.expected_vault):
            with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'):
                VaultEvidenceStore(self.service, value)
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'):
            VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner)
        with self.assertRaisesRegex(JournalError, 'REOPEN_OPTIONS'):
            VaultEvidenceStore(self.service, self.vault, max_intents=1)
        self.assertIs(self.evidence._db, self.runtime.journal._db)
        self.assertIsNot(self.evidence._db, self.vault._db)
        other = Context('ungranted', self.owner.deployment)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            VaultEvidenceStore(self.service, self.vault, create=True, owner=other)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.evidence.lookup(other, self.config['evaluatorId'], 'run:1')
        self.emit('mount', dict(authorityId=self.runtime.journal.authority_id, descriptor=self.expected_vault,
            separateConnections=True, administratorRequired=True))

    def test_publication_and_cold_replay_preserve_original_receipt(self):
        self.fixture(); first = self.import_fixture()
        self.assertEqual(first['intent']['anchor']['attemptId'], self.fixture_root.name)
        self.assertEqual(first['intent']['anchor']['authorityId'], self.runtime.journal.authority_id)
        self.assert_preserved((1, 1, 1))
        self.vault.close(); self.reopened(runtime=True)
        self.vault = EvidenceVault(self.parent / 'vault/evidence.db', self.expected_vault)
        self.addCleanup(self.vault.close)
        self.evidence = VaultEvidenceStore(self.service, self.vault)
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive replay')),
              patch.object(reducer, 'reduce_original', side_effect=AssertionError('semantic replay')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('worker replay'))):
            self.assertEqual(self.import_call(), first)
            self.assertEqual(self.evidence_lookup(), first)
        self.assert_preserved((1, 1, 1)); self.emit('published', first)

    def test_transport_success_does_not_publish_without_semantic_success(self):
        self.fixture()
        with self.assertRaises((JournalError, ValueError)): self.import_call()
        self.assert_preserved((1, 0, 0))

    def test_before_intent_commit_rolls_back_without_evidence(self):
        self.fixture(); self.interrupt('before_intent_commit')
        self.assert_preserved((0, 0, 0))

    def test_after_intent_commit_resumes_same_intent(self):
        self.fixture(); self.interrupt('after_intent_commit')
        self.assert_preserved((1, 0, 0)); pending = self.pending()
        first = self.import_fixture()
        self.assertEqual(first['intentDigest'], pending['intentDigest'])
        self.assert_preserved((1, 1, 1)); self.emit('published', first)

    def test_after_seal_resumes_without_original_archive_or_new_worker(self):
        self.fixture(); self.interrupt('after_evidence_seal')
        self.assert_preserved((1, 0, 1)); pending = self.pending()
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive repair')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('worker repair'))):
            first = self.import_fixture()
        self.assertEqual(first['intentDigest'], pending['intentDigest'])
        self.assert_preserved((1, 1, 1)); self.emit('published', first)

    def test_before_publication_commit_keeps_unpublished_manifest(self):
        self.fixture(); self.interrupt('before_publication_commit')
        self.assert_preserved((1, 0, 1))
        self.assertIsNone(self.evidence_lookup())
        self.assertIsNone(self.vault._lease); self.assertFalse(self.vault._db.in_transaction)

    def test_lost_publication_reply_reconciles_exact_receipt(self):
        self.fixture(); self.interrupt('after_publication_commit')
        self.assert_preserved((1, 1, 1))
        first = self.evidence_lookup()
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive replay')),
              patch.object(reducer, 'reduce_original', side_effect=AssertionError('semantic replay'))):
            self.assertEqual(self.import_call(), first)
        self.emit('published', first)

    def test_expired_snapshot_before_commit_rolls_back_publication(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'before_publication_commit':
                self.assertTrue(self.db.in_transaction)
                self.assertTrue(self.vault._db.in_transaction)
                self.vault._lease._deadline = 0
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'SNAPSHOT_UNAVAILABLE'): self.import_fixture()
        self.assert_preserved((1, 0, 1)); self.assertIsNone(self.vault._lease)

    def test_revocation_after_inspection_keeps_intent_unpublished(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_inspection':
                self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.import_fixture()
        self.assertEqual(self.sizes_evidence(), (1, 0, 0)); self.assertEqual(self.sizes(), (1, 1))
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.import_call()
        self.emit('revoked', dict(intents=1, publications=0, manifests=0, workerExecuted=False))

    def test_configuration_change_after_seal_prevents_publication(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_evidence_seal':
                self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2},
                    expected_revision=1, runtime=self.runtime)
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'CONFIGURATION_CHANGED'): self.import_fixture()
        self.assert_preserved((1, 0, 1))
        with patch.object(archive, 'read_original', side_effect=AssertionError('archive repair')):
            with self.assertRaisesRegex(JournalError, 'CONFIGURATION_CHANGED'): self.import_fixture()
        self.assert_preserved((1, 0, 1))

    def test_original_attempt_change_after_seal_prevents_publication(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_evidence_seal':
                self.bound.ledger.db.execute('UPDATE qs_attempts SET return_bytes=?', (b'{}',))
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaises(JournalError): self.import_fixture()
        self.assert_preserved((1, 0, 1))

    def test_corrupt_published_body_is_refused_without_repair(self):
        self.fixture(); self.import_fixture()
        self.vault._db.execute("UPDATE ev_bodies SET body=? WHERE digest=(SELECT digest FROM ev_documents WHERE path='inspection/summary.json')", (b'{}',))
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive repair')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('worker repair'))):
            with self.assertRaises(JournalError): self.import_call()
            with self.assertRaises(JournalError): self.evidence_lookup()
        self.assert_preserved((1, 1, 1))

    def test_unavailable_vault_does_not_become_novelty_or_replacement(self):
        self.fixture(); first = self.import_fixture(); self.vault.close()
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive repair')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('worker repair'))):
            with self.assertRaises(JournalError): self.import_call()
            with self.assertRaises(JournalError): self.evidence_lookup()
        status = self.pending()
        self.assertTrue(status['published']); self.assertEqual(status['intentDigest'], first['intentDigest'])
        self.emit('unavailable', dict(status=status, replacementCreated=False, workerExecuted=False))

    def test_intent_capacity_refuses_second_run_before_archive_read(self):
        original_store = self.store
        with patch.object(self, 'store', side_effect=lambda: original_store(max_intents=1)):
            self.fixture()
        self.import_fixture(); self.reserve('run:2')
        second_call = lambda: self.service.execute(self.owner, self.config['evaluatorId'], 'run:2',
            runtime=self.runtime, installed_configuration=self.config)
        with (patch.object(self, 'create', return_value=self.service),
              patch.object(self, 'call', side_effect=second_call),
              patch.object(self, 'store', return_value=self.evidence)):
            self.fixture()
        with patch.object(archive, 'read_original', side_effect=AssertionError('capacity read')):
            with self.assertRaisesRegex(JournalError, 'LIMIT'):
                self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:2')
        self.assertEqual(self.sizes_evidence(), (1, 1, 1)); self.assertEqual(self.sizes(), (2, 2))
        self.emit('capacity', dict(intents=1, publications=1, manifests=1, attempts=2,
            workerExecuted=False, physicalCapacityReserved=False, logicalCharge=c.INTENT_CHARGE))

    def test_supervisor_source_and_archive_reads_stay_outside_control_transaction(self):
        self.fixture(); original_row = self.service._row; original_open = Path.open
        def checked_row(*args, **kwargs):
            self.assertFalse(self.db.in_transaction)
            return original_row(*args, **kwargs)
        def checked_open(path, *args, **kwargs):
            self.assertFalse(self.db.in_transaction)
            return original_open(path, *args, **kwargs)
        with (patch.object(self.service, '_row', side_effect=checked_row),
              patch.object(Path, 'open', new=checked_open)):
            first = self.import_fixture()
            self.assertEqual(self.import_call(), first)
        self.assert_preserved((1, 1, 1)); self.emit('published', first)

    def test_temporary_shadow_refuses(self):
        self.fixture(); self.import_fixture()
        self.db.execute('CREATE TEMP TABLE evi_intents (record BLOB)')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.import_call()
        self.emit('retained-temp-schema', [list(row) for row in self.db.execute('SELECT name,type,sql FROM sqlite_temp_master')])

    def test_no_paths_callbacks_or_transaction_reentry(self):
        self.fixture()
        for name, value in dict(path=str(self.fixture_root), callback=self.oracle, result={}, archive={}).items():
            with self.assertRaises(JournalError):
                self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:1', **{name: value})
        with self.runtime.journal._transaction():
            with self.assertRaisesRegex(JournalError, 'TRANSACTION_REENTRY'): self.import_call()
        self.assert_preserved((0, 0, 0))

    def test_bulk_full_keeps_original_intent_and_no_publication(self):
        original_store = self.store
        with patch.object(self, 'store', side_effect=lambda: original_store(vault_pages=32)):
            self.fixture()
        with self.assertRaisesRegex(JournalError, 'CAPACITY'): self.import_fixture()
        self.assert_preserved((1, 0, 0))
        self.assertFalse(self.db.in_transaction); self.assertFalse(self.vault._db.in_transaction)

    def test_revocation_after_seal_preserves_authority_refusal(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_evidence_seal':
                self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.import_fixture()
        self.assertEqual(self.sizes_evidence(), (1, 0, 1)); self.assertEqual(self.sizes(), (1, 1))
        self.assertIsNone(self.vault._lease); self.assertFalse(self.vault._db.in_transaction)
        self.assertFalse(self.db.in_transaction)
        self.emit('revoked-after-seal', dict(intents=1, publications=0, manifests=1,
            authorityErrorPreserved=True, leasesReleased=True, workerExecuted=False))
