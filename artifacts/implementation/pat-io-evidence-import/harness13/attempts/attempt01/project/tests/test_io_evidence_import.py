"""Authority/reader/storage controls with an explicitly substituted oracle.

These fixtures create no worker and establish no semantic or physical success.
The independent full-group reducer is exercised separately on retained data.
"""
import fcntl
import hashlib
import os
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, JournalError
from test_io_service_execution import IoServiceExecutionTests
from bundle_io import retain_bundle, launch_input
import supervisor_contracts as contracts
from evidence import archive, reducer
from evidence.contracts import sha, EvidenceError
from evidence.store import IoEvidenceStore, ANCHOR


class IoEvidenceImportTests(IoServiceExecutionTests):
    def store(self, **options):
        self.evidence = IoEvidenceStore(self.service, create=True, owner=self.owner, **options)
        return self.evidence

    def fixture(self):
        self.create()
        def substitute_launch(row, bundle):
            identifier = row['record']['attemptId']; root = self.bound.ledger.root / identifier
            root.mkdir(mode=0o700); fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                retain_bundle(fd, row['request'], bundle)
                contracts.write_file(fd, 'input.json', canonical(launch_input(row['request'], identifier)))
                lease = os.open('writer.lease', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
                info = os.fstat(lease); os.close(lease)
                self.bound.ledger.change(identifier, 'launching', lease=dict(device=str(info.st_dev), inode=str(info.st_ino)))
                row = self.bound.ledger.change(identifier, 'running', pid=os.getpid())
                (root / 'output').mkdir(mode=0o700)
                raw = canonical(dict(fixture=True, workerExecuted=False, semanticsVerified=False))
                (root / 'output/result.json').write_bytes(raw); (root / 'output/result.json').chmod(0o600)
                returned = canonical(dict(profile='hms.pat.io-supervisor-return/0.1', attemptId=identifier,
                    requestDigest=row['record']['requestDigest'], bundleDigest=row['request']['bundleDigest'],
                    groupResultDigest=sha(raw), status='captured'))
                contracts.write_file(fd, 'worker-return.json', returned)
                return self.bound._archive(row, returned, 0, None, False,
                    archive.output_closure({'result.json': raw}), None,
                    dict(files=42, logicalBytes=4096, totalDiskQuotaEnforced=False))
            finally: os.close(fd)
        with patch.object(self.bound, '_launch', side_effect=substitute_launch):
            self.fixture_association = self.call()
        self.fixture_root = self.bound.ledger.root / self.fixture_association['attempt']['record']['attemptId']
        self.store()
        self.emit('fixture-provenance', dict(workerExecuted=False, semanticsVerified=False,
            purpose='Original-request, reader, authority and atomic-storage control only',
            association=self.fixture_association['association']))

    def oracle(self, *args, **kwargs):
        self.assertFalse(self.db.in_transaction)
        count = len(kwargs['expected_cases'])
        return dict(summary=dict(cases=[dict(fixture=True)] * count),
                    inspections=[dict(fixture=True)] * count)

    def import_fixture(self):
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            return self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:1')

    def import_call(self):
        return self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:1')

    def evidence_lookup(self):
        return self.evidence.lookup(self.owner, self.config['evaluatorId'], 'run:1')

    def evidence_counts(self):
        return tuple(self.db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                     for name in ('ioei_runs', 'ioei_documents'))

    def test_import_creation_requires_actual_execution_mount(self):
        self.create()
        for value in (self.bound, self.supervisor_id, {}, lambda: self.service):
            with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'):
                IoEvidenceStore(value, create=True, owner=self.owner)
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): IoEvidenceStore(self.service)
        self.store(); self.assertIs(self.evidence._db, self.db)
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'): self.store()

    def test_unlaunched_association_cannot_be_imported(self):
        self.associated(); self.store()
        with self.assertRaisesRegex(JournalError, 'TRANSPORT_INCOMPLETE'): self.import_call()
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_complete_transport_alone_cannot_pass_semantic_reducer(self):
        self.fixture()
        with self.assertRaises((JournalError, ValueError)): self.import_call()
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_fixture_publication_and_exact_replay_use_original_receipt(self):
        self.fixture(); original = self.import_fixture()
        self.assertEqual(original['evaluation']['anchor']['attemptId'], self.fixture_root.name)
        self.assertEqual(original['evaluation']['anchor']['configurationReceiptDigest'], self.configuration_receipt['receiptDigest'])
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive replay')),
              patch.object(reducer, 'reduce_original', side_effect=AssertionError('semantic replay'))):
            self.assertEqual(self.import_call(), original)
            self.assertEqual(self.evidence_lookup(), original)
        self.emit('fixture-import', original)

    def test_import_has_no_path_callback_archive_or_result_argument(self):
        self.fixture()
        for name, value in dict(path=str(self.fixture_root), callback=self.oracle, result={}, archive={}).items():
            with self.assertRaises(JournalError):
                self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:1', **{name: value})
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_current_authorization_required_even_for_replay(self):
        self.fixture(); self.import_fixture(); other = Context('ungranted', self.owner.deployment)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.evidence.import_run(other, self.config['evaluatorId'], 'run:1')
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.evidence.lookup(other, self.config['evaluatorId'], 'run:1')

    def test_authorization_rechecked_after_inspection(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_inspection': self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_import_rollback_leaves_no_published_documents(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'before_import_commit': raise RuntimeError('commit interruption')
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(RuntimeError, 'commit interruption'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0))
        self.assertEqual(self.sizes(), (1, 1))

    def test_lost_import_reply_resolves_committed_receipt(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_import_commit':
                self.emit('committed-fixture-receipt', value); raise RuntimeError('lost reply')
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(RuntimeError, 'lost reply'): self.import_fixture()
        self.assertEqual(self.evidence_counts()[0], 1)
        self.evidence = IoEvidenceStore(self.service)
        with patch.object(archive, 'read_original', side_effect=AssertionError('repair')):
            self.assertEqual(self.import_call(), self.evidence_lookup())

    def test_configuration_drift_keeps_historical_evaluation(self):
        self.fixture(); original = self.import_fixture()
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        self.assertEqual(self.import_call(), original)
        with (patch.object(reducer, 'inspect_io_group', side_effect=self.oracle),
              patch.object(archive, 'read_original', side_effect=AssertionError('archive read'))):
            self.assertEqual(self.evidence.reinspect(self.owner, self.config['evaluatorId'], 'run:1'), original)

    def test_reader_refuses_active_original_lease(self):
        self.fixture(); lease = os.open(self.fixture_root / 'writer.lease', os.O_RDWR)
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(JournalError, 'PRODUCER_ACTIVE'): self.import_fixture()
        finally: os.close(lease)
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_reader_refuses_replaced_original_lease(self):
        self.fixture(); original = self.fixture_root / 'writer.lease'
        original.rename(self.fixture_root / 'retained-original.lease')
        original.touch(mode=0o600)
        with self.assertRaisesRegex(JournalError, 'LEASE_CHANGED'): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_reader_refuses_changed_return(self):
        self.fixture(); target = self.fixture_root / 'worker-return.json'
        (self.fixture_root / 'retained-original-return.json').write_bytes(target.read_bytes())
        target.write_bytes(b'{}')
        with self.assertRaisesRegex(JournalError, 'RETURN_CHANGED'): self.import_fixture()

    def test_reader_refuses_changed_output_closure(self):
        self.fixture(); target = self.fixture_root / 'output/result.json'
        (self.fixture_root / 'retained-original-output.json').write_bytes(target.read_bytes())
        target.write_bytes(b'{}')
        with self.assertRaisesRegex(JournalError, 'OUTPUT_CHANGED'): self.import_fixture()

    def test_reader_refuses_hardlinked_output_file(self):
        self.fixture(); os.link(self.fixture_root / 'output/result.json', self.fixture_root / 'linked-output.json')
        with self.assertRaisesRegex(JournalError, 'UNSAFE_FILE'): self.import_fixture()

    def test_missing_imported_body_is_not_reconstructed(self):
        self.fixture(); self.import_fixture()
        self.db.execute("DELETE FROM ioei_documents WHERE path='inspection/summary.json'")
        before = self.evidence_counts()
        with patch.object(archive, 'read_original', side_effect=AssertionError('repair')):
            with self.assertRaises(JournalError): self.import_call()
            with self.assertRaises(JournalError): IoEvidenceStore(self.service, create=True, owner=self.owner)
        self.assertEqual(before, self.evidence_counts())

    def test_changed_imported_body_is_rejected_without_repair(self):
        self.fixture(); self.import_fixture()
        self.db.execute("UPDATE ioei_documents SET body=? WHERE path='inspection/summary.json'", (b'{}',))
        with patch.object(archive, 'read_original', side_effect=AssertionError('repair')):
            with self.assertRaises(JournalError): self.import_call()
        self.assertEqual(self.db.execute("SELECT body FROM ioei_documents WHERE path='inspection/summary.json'").fetchone()[0], b'{}')

    def test_invalid_body_type_refuses_before_document_fetch(self):
        self.fixture(); self.import_fixture()
        self.db.execute("UPDATE ioei_documents SET body='wrong type' WHERE path='inspection/summary.json'")
        statements = []; self.db.set_trace_callback(statements.append)
        try:
            with self.assertRaises(JournalError): self.evidence_lookup()
        finally: self.db.set_trace_callback(None)
        self.assertFalse(any('SELECT path,body FROM ioei_documents' in sql for sql in statements))
        self.emit('bounded-read-trace', dict(statements=statements, bodyFetchExecuted=False))

    def test_extra_schema_object_is_retained_and_refused(self):
        self.fixture(); self.db.execute('CREATE TABLE ioei_extra(body BLOB)')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.import_fixture()
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='ioei_extra'").fetchone())

    def test_temporary_shadow_is_refused(self):
        self.fixture(); self.db.execute('CREATE TEMP TABLE ioei_documents(body BLOB)')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.import_fixture()
        self.emit('retained-temp-schema', [list(row) for row in self.db.execute('SELECT name,type,sql FROM sqlite_temp_master')])

    def test_association_change_after_inspection_prevents_publication(self):
        self.fixture()
        def checkpoint(phase, value):
            if phase == 'after_inspection':
                self.bound.ledger.db.execute("UPDATE qs_attempts SET return_bytes=?", (b'{}',))
        with patch.object(self.evidence, '_checkpoint', side_effect=checkpoint):
            with self.assertRaises(JournalError): self.import_fixture()
        self.assertEqual(self.evidence_counts(), (0, 0))

    def test_current_consumer_identity_is_checked_before_replay(self):
        self.fixture(); self.import_fixture()
        with patch('evidence.store.identity', return_value='sha256:' + '0' * 64):
            with self.assertRaisesRegex(JournalError, 'IMPLEMENTATION_CHANGED'): self.import_call()

    def test_transaction_reentry_is_refused(self):
        self.fixture()
        with self.journal_transaction():
            with self.assertRaisesRegex(JournalError, 'TRANSACTION_REENTRY'): self.import_call()

    def journal_transaction(self): return self.runtime.journal._transaction()
