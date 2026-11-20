"""Additional importer boundaries; successful runs are explicit fixtures."""
import json
import os
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from test_io_evidence_import import IoEvidenceImportTests
from bundle_io import retain_bundle, launch_input
from evidence import archive, reducer
from evidence.contracts import closure, sha, MAX_STORE_DOCUMENTS
from evidence.store import IoEvidenceStore
from io_service_execution import BoundQualificationSupervisor
import supervisor_contracts as contracts


class IoEvidenceImportHistoryTests(IoEvidenceImportTests):
    def second_fixture(self):
        self.second_reservation = self.reserve(run='run:2')
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
            self.second_execution = self.service.execute(self.owner, self.config['evaluatorId'], 'run:2',
                runtime=self.runtime, installed_configuration=self.config)
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            result = self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:2')
        self.emit('second-fixture-provenance', dict(workerExecuted=False, semanticsVerified=False,
            reservationDigest=self.second_reservation['reservationDigest'], association=self.second_execution['association']))
        return result

    def test_replaced_supervisor_authority_refuses_existing_import(self):
        self.fixture(); original = self.import_fixture()
        replacement = BoundQualificationSupervisor(self.parent/'replacement', create=True)
        try:
            self.assertNotEqual(replacement.ledger.authority_id, self.supervisor_id)
            self.service.supervisor = replacement
            with self.assertRaisesRegex(JournalError, 'SUPERVISOR_MISMATCH'): self.evidence_lookup()
            with self.assertRaisesRegex(JournalError, 'SUPERVISOR_MISMATCH'): self.import_call()
            self.assertEqual(self.evidence_counts()[0], 1)
            self.emit('replacement-refusal', dict(originalReceiptDigest=original['receiptDigest'],
                replacementAuthorityId=replacement.ledger.authority_id, replacementAttempts=0, originalImportPreserved=True))
        finally:
            replacement.close()

    def test_two_imports_keep_distinct_attempts_and_receipt_chain(self):
        self.fixture(); first = self.import_fixture(); second = self.second_fixture()
        self.assertNotEqual(first['evaluation']['anchor']['attemptId'], second['evaluation']['anchor']['attemptId'])
        self.assertEqual(second['receipt']['sequence'], 2)
        self.assertEqual(second['receipt']['previousReceiptDigest'], first['receiptDigest'])
        self.evidence = IoEvidenceStore(self.service)
        with patch.object(archive, 'read_original', side_effect=AssertionError('historical archive read')):
            self.assertEqual(self.import_call(), first)
            self.assertEqual(self.evidence.import_run(self.owner, self.config['evaluatorId'], 'run:2'), second)
        self.assertEqual(self.sizes(), (2, 2))
        self.emit('two-import-history', dict(first=first, second=second, workerExecuted=False))

    def test_cross_run_control_substitution_refuses_after_rehashing_closure(self):
        self.fixture(); self.import_fixture(); self.second_fixture()
        borrowed = self.db.execute("SELECT body FROM ioei_documents WHERE sequence=1 AND path='original/control/handoff.json'").fetchone()[0]
        self.db.execute("UPDATE ioei_documents SET body=?,digest=? WHERE sequence=2 AND path='original/control/handoff.json'", (borrowed, sha(borrowed)))
        # Keep the stored carrier checksum coherent so the authority join, not
        # just a stale checksum, must refuse a different real run's control.
        files = dict(self.db.execute('SELECT path,body FROM ioei_documents WHERE sequence=2'))
        receipt = json.loads(self.db.execute('SELECT receipt FROM ioei_runs WHERE sequence=2').fetchone()[0])
        receipt['closure'] = closure(files)
        self.db.execute('UPDATE ioei_runs SET receipt=? WHERE sequence=2', (canonical(receipt),))
        with patch.object(archive, 'read_original', side_effect=AssertionError('repair')):
            with self.assertRaisesRegex(JournalError, 'ASSOCIATION_CHANGED'):
                self.evidence.lookup(self.owner, self.config['evaluatorId'], 'run:2')
        self.assertEqual(self.db.execute("SELECT body FROM ioei_documents WHERE sequence=2 AND path='original/control/handoff.json'").fetchone()[0], borrowed)
        self.emit('cross-run-substitution', dict(substitutedPath='original/control/handoff.json',
            closureRehashed=True, mutationRetained=True, repaired=False, workerExecuted=False))

    def test_forged_second_import_receipt_chain_is_not_repaired(self):
        self.fixture(); self.import_fixture(); self.second_fixture()
        receipt = json.loads(self.db.execute('SELECT receipt FROM ioei_runs WHERE sequence=2').fetchone()[0])
        receipt['previousReceiptDigest'] = 'sha256:' + '0' * 64
        raw = canonical(receipt); self.db.execute('UPDATE ioei_runs SET receipt=? WHERE sequence=2', (raw,))
        with patch.object(archive, 'read_original', side_effect=AssertionError('repair')):
            with self.assertRaises(JournalError): self.evidence_lookup()
        self.assertEqual(self.db.execute('SELECT receipt FROM ioei_runs WHERE sequence=2').fetchone()[0], raw)

    def test_store_document_count_refuses_before_fetching_any_bodies(self):
        self.fixture()
        with self.runtime.journal._transaction():
            self.db.executemany('INSERT INTO ioei_documents VALUES(?,?,?,?)',
                [(1, 'excess/%05d.bin' % i, sha(b''), b'') for i in range(MAX_STORE_DOCUMENTS+1)])
        statements = []; self.db.set_trace_callback(statements.append)
        try:
            with self.assertRaisesRegex(JournalError, 'CAPACITY'): self.evidence_lookup()
        finally: self.db.set_trace_callback(None)
        self.assertFalse(any('SELECT path,body FROM ioei_documents' in sql for sql in statements))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ioei_documents').fetchone()[0], MAX_STORE_DOCUMENTS+1)
        self.emit('document-count-refusal', dict(actualRows=MAX_STORE_DOCUMENTS+1,
            configuredMaximum=MAX_STORE_DOCUMENTS, bodyFetchExecuted=False, mutationRetained=True,
            statements=statements))
