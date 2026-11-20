"""Exact shared-body controls; worker/semantic success is explicitly a fixture."""
import json
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from test_io_evidence_import_history import IoEvidenceImportHistoryTests
from evidence import archive, reducer
from evidence.contracts import sha, closure, identity as legacy_identity, MAX_STORE_BYTES
from evidence.store import IoEvidenceStore as LegacyIoEvidenceStore
from evidence_compact.store import CompactIoEvidenceStore
from evidence_compact import contracts as compact_contracts


class CompactIoEvidenceTests(IoEvidenceImportHistoryTests):
    def store(self, **options):
        options = dict(getattr(self, 'creation_options', {}), **options)
        self.evidence = CompactIoEvidenceStore(self.service, create=True, owner=self.owner, **options)
        return self.evidence

    def evidence_counts(self):
        return tuple(self.db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                     for name in ('ioec_runs', 'ioec_documents', 'ioec_bodies'))

    def joined_files(self, sequence=1):
        return dict(self.db.execute('SELECT d.path,b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest WHERE d.sequence=?', (sequence,)))

    def test_exact_reconstruction_deduplicates_without_dropping_references(self):
        self.fixture(); receipt = self.import_fixture()
        runs, references, objects = self.evidence_counts()
        self.assertEqual(runs, 1); self.assertLess(objects, references)
        files = self.joined_files()
        self.assertEqual(len(files), references)
        self.assertEqual(closure(files), receipt['receipt']['closure'])
        self.assertEqual(len([path for path in files if path.startswith('inspection/case-')]), 30)
        self.assertEqual(self.import_call(), receipt)
        self.emit('compact-reconstruction', dict(references=references, objects=objects,
            closure=closure(files), exactReferencesPreserved=True, workerExecuted=False))

    def test_two_runs_share_exact_bodies_and_keep_distinct_receipts(self):
        self.fixture(); first = self.import_fixture(); first_objects = self.evidence_counts()[2]
        second = self.second_fixture(); counts = self.evidence_counts()
        self.assertEqual(counts[0], 2); self.assertLess(counts[2], 2*first_objects)
        self.assertEqual(second['receipt']['previousReceiptDigest'], first['receiptDigest'])
        self.assertNotEqual(second['evaluation']['anchor']['attemptId'], first['evaluation']['anchor']['attemptId'])
        self.evidence = CompactIoEvidenceStore(self.service)
        with patch.object(archive, 'read_original', side_effect=AssertionError('archive replay')):
            self.assertEqual(self.import_call(), first)
            self.assertEqual(self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:2'), second)
        self.emit('compact-shared-history', dict(runs=counts[0], references=counts[1], bodies=counts[2],
            firstReceipt=first['receiptDigest'], secondReceipt=second['receiptDigest'], workerExecuted=False))

    def test_legacy_mount_and_identity_remain_separate_and_usable(self):
        before = legacy_identity(); self.fixture(); compact = self.import_fixture()
        legacy = LegacyIoEvidenceStore(self.service, create=True, owner=self.owner)
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            old = legacy.import_run(self.owner, self.config['evaluatorId'], 'run:1')
        self.assertEqual(before, legacy_identity())
        self.assertEqual(before, compact_contracts._LEGACY_IDENTITY)
        self.assertNotEqual(compact['receipt']['consumerIdentity'], old['receipt']['consumerIdentity'])
        self.assertNotEqual(compact['receipt']['profile'], old['receipt']['profile'])
        self.assertEqual(legacy.lookup(self.owner, self.config['evaluatorId'], 'run:1'), old)
        self.assertEqual(self.evidence_lookup(), compact)
        self.emit('explicit-profile-coexistence', dict(legacy=old['receiptDigest'], compact=compact['receiptDigest'],
            legacyIdentityUnchanged=True, migrationPerformed=False, workerExecuted=False))

    def test_corrupt_shared_body_refuses_fresh_reuse_without_repair(self):
        self.fixture(); self.import_fixture()
        digest, body = self.db.execute("SELECT b.digest,b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest WHERE d.path='inspection/case-00.json'").fetchone()
        bad = b'x' * len(body); self.db.execute('UPDATE ioec_bodies SET body=? WHERE digest=?', (bad, digest))
        with self.assertRaisesRegex(JournalError, 'BODY_CHANGED'): self.second_fixture()
        self.assertEqual(self.evidence_counts()[0], 1)
        self.assertEqual(self.db.execute('SELECT body FROM ioec_bodies WHERE digest=?', (digest,)).fetchone()[0], bad)
        self.emit('corrupt-shared-body', dict(digest=digest, freshImportRefused=True, mutationRetained=True, workerExecuted=False))

    def test_missing_body_refuses_without_reconstructing_worker_output(self):
        self.fixture(); self.import_fixture()
        digest = self.db.execute("SELECT digest FROM ioec_documents WHERE path='inspection/summary.json'").fetchone()[0]
        self.db.execute('DELETE FROM ioec_bodies WHERE digest=?', (digest,))
        with patch.object(archive, 'read_original', side_effect=AssertionError('repair')):
            with self.assertRaisesRegex(JournalError, 'BODY_MISSING'): self.import_call()
        self.assertIsNone(self.db.execute('SELECT body FROM ioec_bodies WHERE digest=?', (digest,)).fetchone())

    def test_orphan_body_is_retained_and_refused(self):
        self.fixture(); self.import_fixture(); body = b'orphan-control'
        self.db.execute('INSERT INTO ioec_bodies VALUES(?,?)', (sha(body), body))
        with self.assertRaisesRegex(JournalError, 'ORPHAN_BODY'): self.evidence_lookup()
        self.assertEqual(self.db.execute('SELECT body FROM ioec_bodies WHERE digest=?', (sha(body),)).fetchone()[0], body)

    def test_rehashed_cross_run_reference_still_refuses_authority_mismatch(self):
        self.fixture(); self.import_fixture(); self.second_fixture()
        borrowed = self.db.execute("SELECT digest FROM ioec_documents WHERE sequence=1 AND path='original/control/handoff.json'").fetchone()[0]
        replaced = self.db.execute("SELECT digest FROM ioec_documents WHERE sequence=2 AND path='original/control/handoff.json'").fetchone()[0]
        old_body = self.db.execute('SELECT body FROM ioec_bodies WHERE digest=?', (replaced,)).fetchone()[0]
        (self.parent/'retained-original-second-handoff.json').write_bytes(old_body)
        self.db.execute("UPDATE ioec_documents SET digest=? WHERE sequence=2 AND path='original/control/handoff.json'", (borrowed,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ioec_documents WHERE digest=?', (replaced,)).fetchone()[0], 0)
        self.db.execute('DELETE FROM ioec_bodies WHERE digest=?', (replaced,))
        receipt = json.loads(self.db.execute('SELECT receipt FROM ioec_runs WHERE sequence=2').fetchone()[0])
        receipt['closure'] = closure(self.joined_files(2))
        self.db.execute('UPDATE ioec_runs SET receipt=? WHERE sequence=2', (canonical(receipt),))
        with self.assertRaisesRegex(JournalError, 'ASSOCIATION_CHANGED'):
            self.evidence.lookup(self.owner, self.config['evaluatorId'], 'run:2')
        self.assertEqual(self.db.execute("SELECT digest FROM ioec_documents WHERE sequence=2 AND path='original/control/handoff.json'").fetchone()[0], borrowed)

    def test_rollback_publishes_no_objects_references_or_receipt(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'before_import_commit': raise RuntimeError('compact commit interruption')
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(RuntimeError, 'compact commit interruption'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0, 0))

    def test_lost_reply_replays_original_without_duplicate_bodies(self):
        self.fixture(); committed = []
        def checkpoint(phase, value):
            if phase == 'after_import_commit':
                committed.append(value); raise RuntimeError('compact reply lost')
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(RuntimeError, 'compact reply lost'): self.import_fixture()
        counts = self.evidence_counts(); self.evidence = CompactIoEvidenceStore(self.service)
        with patch.object(archive, 'read_original', side_effect=AssertionError('rebuild')):
            self.assertEqual(self.import_call(), committed[0])
        self.assertEqual(counts, self.evidence_counts())

    def test_lower_object_quota_refuses_atomic_publication(self):
        self.creation_options = dict(max_objects=1); self.fixture()
        with self.assertRaisesRegex(JournalError, 'CAPACITY'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0, 0))

    def test_lower_expanded_quota_is_not_bypassed_by_deduplication(self):
        self.creation_options = dict(max_expanded_data_bytes=2048); self.fixture()
        with self.assertRaisesRegex(JournalError, 'CAPACITY'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0, 0))

    def test_invalid_body_type_refuses_before_fetching_payloads(self):
        self.fixture(); self.import_fixture()
        digest = self.db.execute("SELECT digest FROM ioec_documents WHERE path='inspection/case-00.json'").fetchone()[0]
        self.db.execute('UPDATE ioec_bodies SET body=? WHERE digest=?', ('wrong type', digest))
        statements = []; self.db.set_trace_callback(statements.append)
        try:
            with self.assertRaisesRegex(JournalError, 'INVALID_RETAINED'): self.evidence_lookup()
        finally: self.db.set_trace_callback(None)
        self.assertFalse(any('SELECT d.path,b.body' in value or 'SELECT body FROM ioec_bodies' in value for value in statements))
        self.emit('body-type-preflight', dict(bodyFetchExecuted=False, statements=statements))

    def test_missing_body_table_with_anchor_is_not_reinitialized(self):
        self.fixture(); self.db.execute('DROP TABLE ioec_bodies')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.evidence_lookup()
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.store()
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='ioec_bodies'").fetchone())

    def test_temporary_body_shadow_is_refused(self):
        self.fixture(); self.db.execute('CREATE TEMP TABLE ioec_bodies(digest TEXT,body BLOB)')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.evidence_lookup()
        self.emit('retained-shadow-schema', [list(row) for row in self.db.execute('SELECT name,type,sql FROM sqlite_temp_master')])

    def test_extra_body_index_is_retained_and_refused(self):
        self.fixture(); self.db.execute('CREATE INDEX ioec_extra ON ioec_bodies(body)')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.evidence_lookup()
        self.assertIsNotNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='ioec_extra'").fetchone())

    def test_creation_limits_never_widen_and_reopen_options_refuse(self):
        self.create()
        for options in (dict(max_objects=True), dict(max_data_bytes=MAX_STORE_BYTES+1), dict(max_documents=0)):
            with self.assertRaises(JournalError): self.store(**options)
        self.store()
        with self.assertRaisesRegex(JournalError, 'REOPEN_OPTIONS'):
            CompactIoEvidenceStore(self.service, max_objects=1)

    def test_authorization_is_rechecked_after_compact_inspection(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_inspection': self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0, 0))

    def test_reinspection_uses_reconstructed_bytes_outside_journal_transaction(self):
        self.fixture(); original = self.import_fixture()
        with (patch.object(reducer, 'inspect_io_group', side_effect=self.oracle),
              patch.object(archive, 'read_original', side_effect=AssertionError('worker directory'))):
            self.assertEqual(self.evidence.reinspect(self.owner, self.config['evaluatorId'], 'run:1'), original)
