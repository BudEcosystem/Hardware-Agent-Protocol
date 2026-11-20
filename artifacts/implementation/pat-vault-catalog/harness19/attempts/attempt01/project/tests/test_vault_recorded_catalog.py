"""Vault/catalog admission controls with an explicitly substituted oracle.

No qualification worker runs. Fixture success establishes control behavior,
not semantic qualification of the original matrix or physical hardware.
"""
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from hms.journal import JournalError
from hms.pat_catalog import PatCatalog
from hms.pat_compiler import compiler_digest
from hms.pat_contracts import pat_digest
from hms.pat_execution import PatExecutionStore
from evidence import reducer
from test_vault_authority import VaultAuthorityTests
from test_io_service_authority import business
from test_pat_io_contracts import program
from vault_recorded_io import contracts
from vault_recorded_io.bridge import VaultRecordedIoBridge
from vault_recorded_io.catalog import VaultRecordedPatCatalog
from vault_recorded_io.execution import VaultRecordedPatExecutionStore


class VaultRecordedCatalogTests(VaultAuthorityTests):
    def installed(self, *, byte_limit=contracts.MAX_MEMO_BYTES):
        self.fixture(); self.imported = self.import_fixture()
        self.program = json.loads(self.original['preparedRun']['bundle']['documents']['inputs/candidate.json'])
        self.digest = pat_digest(self.program)
        self.bridge = VaultRecordedIoBridge(self.evidence, self.runtime, (self.config['evaluatorId'],), byte_limit=byte_limit)
        self.catalog = VaultRecordedPatCatalog(self.bridge, create=True, owner=self.owner)
        self.catalog.publish(self.owner, self.program)

    def record(self):
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            self.recorded = self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1')
        return self.recorded

    def promote(self):
        entry = self.catalog.describe(self.owner, self.digest)
        self.assertTrue(entry['eligibleForPromotion'], entry)
        return self.catalog.transition(self.owner, self.digest, expected_revision=entry['catalogRevision'], target='active')

    def executor(self):
        return VaultRecordedPatExecutionStore(self.runtime.journal, self.catalog, self.runtime.procedures)

    def request(self):
        token = self.runtime.journal.issue_namespace(self.owner, 60000)['token']
        return dict(protocol='hms.pat-run/0.1', replayNamespace=token, runKey='application:1',
            taskKind=self.program['taskKind'], inputProfile=self.program['inputProfile'], parameters={},
            evidenceMode='simulation', originUnixMs=1000, latestCompletionUnixMs=11000)

    def unavailable(self):
        entry = self.catalog.describe(self.owner, self.digest)
        self.assertFalse(entry['eligibleForPromotion']); self.assertFalse(entry['eligibleForNewInstances'])
        self.assertEqual(entry['eligibilityReason'], 'PAT_EVIDENCE_UNAVAILABLE')
        return entry

    def expire_at_commit(self, phase, value):
        if phase == 'before_catalog_commit':
            self.assertTrue(self.db.in_transaction)
            self.vault._lease._deadline = 0

    def assert_no_admission(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_triggers').fetchone()[0], 0)
        self.assertEqual(business(self.runtime), self.before_business)
        self.assertIsNone(self.vault._lease)

    def test_original_receipt_records_vault_identity_and_promotes(self):
        self.installed(); recorded = self.record(); active = self.promote()
        inv = recorded['receipt']['invocation']
        self.assertEqual(inv['original'], self.imported['intent']['anchor'])
        self.assertEqual(inv['publicationDigest'], self.imported['receiptDigest'])
        self.assertEqual(inv['importIntentDigest'], self.imported['intentDigest'])
        self.assertEqual(inv['vaultStoreId'], self.expected_vault['storeId'])
        self.assertEqual(inv['manifestDigest'], self.imported['receipt']['manifestDigest'])
        self.assertTrue(active['eligibleForNewInstances'])
        self.assertEqual(business(self.runtime), self.before_business)
        self.emit('vault-catalog-record', dict(recorded=recorded, active=active,
            workerExecuted=False, semanticsVerified=False, physicalObjectiveVerified=False))

    def test_admission_and_commit_do_no_external_reads(self):
        self.installed(); self.record()
        reads = []; original_read = Path.read_bytes
        def read(path):
            self.assertFalse(self.db.in_transaction, str(path))
            reads.append(str(path)); return original_read(path)
        denied = []
        def sql_guard(action, first, second, database, source):
            if self.db.in_transaction:
                denied.append((action, first, second)); return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.vault._db.set_authorizer(sql_guard)
        try:
            with (patch.object(Path, 'read_bytes', read),
                  patch.object(self.evidence, '_state', side_effect=AssertionError('consumer reread')),
                  patch.object(self.bound.ledger, 'get', side_effect=AssertionError('supervisor reread')),
                  patch.object(reducer, 'reduce_original', side_effect=AssertionError('reduction during admission'))):
                self.promote(); executor = self.executor(); result = executor.run(self.owner, self.request())
        finally:
            self.vault._db.set_authorizer(None)
        self.assertEqual(denied, []); self.assertTrue(reads)
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
        self.emit('pure-admission', dict(instanceId=result['instanceId'], vaultSqlDuringTransaction=denied,
            sourceReadsOutsideTransaction=len(reads), workerExecuted=False, semanticsVerified=False))

    def test_expired_recording_view_rolls_back_evaluation(self):
        self.installed()
        with patch.object(self.bridge, '_checkpoint', side_effect=self.expire_at_commit):
            with self.assertRaisesRegex(JournalError, 'SNAPSHOT_UNAVAILABLE'): self.record()
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT state FROM pc_entries').fetchone()[0], 'candidate')
        self.assertEqual(business(self.runtime), self.before_business)
        self.assertIsNone(self.vault._lease)

    def test_expired_promotion_view_rolls_back_decision(self):
        self.installed(); self.record()
        entry = self.catalog.describe(self.owner, self.digest)
        with patch.object(self.bridge, '_checkpoint', side_effect=self.expire_at_commit):
            with self.assertRaisesRegex(JournalError, 'SNAPSHOT_UNAVAILABLE'):
                self.catalog.transition(self.owner, self.digest, expected_revision=entry['catalogRevision'], target='active')
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_decisions').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT state FROM pc_entries').fetchone()[0], 'evaluated')
        self.assertIsNone(self.vault._lease)

    def test_expired_admission_view_rolls_back_instance_and_procedure(self):
        self.installed(); self.record(); self.promote(); executor = self.executor(); request = self.request()
        with patch.object(self.bridge, '_checkpoint', side_effect=self.expire_at_commit):
            with self.assertRaisesRegex(JournalError, 'SNAPSHOT_UNAVAILABLE'): executor.run(self.owner, request)
        self.assert_no_admission()

    def test_cold_history_works_with_closed_vault_and_fresh_admission_refuses(self):
        self.installed(); recorded = self.record(); self.promote(); executor = self.executor(); request = self.request()
        admitted = executor.run(self.owner, request)
        self.bridge = VaultRecordedIoBridge(self.evidence, self.runtime, (self.config['evaluatorId'],))
        self.catalog = VaultRecordedPatCatalog(self.bridge); executor = self.executor(); self.vault.close()
        with (patch.object(self.bridge, 'prepare', side_effect=AssertionError('historical preparation')),
              patch.object(self.vault, 'snapshot_many', side_effect=AssertionError('historical vault access')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('historical worker'))):
            self.assertEqual(self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1'), recorded)
            self.assertEqual(executor.run(self.owner, request), admitted)
        with self.assertRaises(JournalError) as caught:
            executor.run(self.owner, request | {'runKey':'application:2'})
        self.assertNotEqual(caught.exception.code, 'PAT_NO_MATCH')
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
        self.emit('historical-replay', dict(instanceId=admitted['instanceId'], freshRefusal=caught.exception.code,
            workerExecuted=False, semanticsVerified=False))

    def test_configuration_drift_preserves_history_and_refuses_new_use(self):
        self.installed(); recorded = self.record(); self.promote(); executor = self.executor(); request = self.request()
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision':2}, expected_revision=1, runtime=self.runtime)
        self.unavailable()
        self.assertEqual(self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1'), recorded)
        with self.assertRaises(JournalError) as caught: executor.run(self.owner, request)
        self.assertNotEqual(caught.exception.code, 'PAT_NO_MATCH'); self.assert_no_admission()

    def test_missing_evidence_is_not_novelty_or_automatic_requalification(self):
        self.installed(); self.record(); self.promote(); executor = self.executor(); request = self.request()
        key = self.vault._db.execute("SELECT digest FROM ev_documents WHERE path='inspection/summary.json'").fetchone()[0]
        self.vault._db.execute('DELETE FROM ev_bodies WHERE digest=?', (key,))
        with patch.object(self.bound, '_launch', side_effect=AssertionError('replacement qualification')):
            self.unavailable()
            with self.assertRaises(JournalError) as caught: executor.run(self.owner, request)
        self.assertNotEqual(caught.exception.code, 'PAT_NO_MATCH'); self.assert_no_admission()
        self.assertIsNone(self.vault._db.execute('SELECT 1 FROM ev_bodies WHERE digest=?', (key,)).fetchone())

    def test_revoked_admin_before_publication_cannot_record(self):
        self.installed()
        def revoke(phase, value):
            if phase == 'before_catalog_publication':
                self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.bridge, '_checkpoint', side_effect=revoke):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.record()
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 0)

    def test_inactive_source_cannot_fall_through_to_no_match(self):
        self.installed(); self.record(); self.promote(); executor = self.executor(); request = self.request()
        self.db.execute('UPDATE reg_bindings SET active=0 WHERE instance=?',
            (self.recorded['receipt']['applicability']['roleInstances']['io'],))
        with self.assertRaisesRegex(JournalError, 'PAT_EVIDENCE_UNAVAILABLE'): executor.run(self.owner, request)
        self.assert_no_admission()

    def test_legacy_catalog_and_execution_mounts_are_refused(self):
        self.installed(); self.executor()
        with self.assertRaisesRegex(JournalError, 'UNSUPPORTED_PAT_CATALOG'):
            PatCatalog(self.runtime.journal, compiler_digest=compiler_digest, environment=lambda *args: {}, evaluators=())
        with self.assertRaisesRegex(JournalError, 'UNSUPPORTED_PAT_EXECUTION'):
            PatExecutionStore(self.runtime.journal, self.catalog, self.runtime.procedures, resolver=self.catalog.resolve)
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'):
            VaultRecordedPatCatalog(self.bridge, create=True, owner=self.owner)

    def test_small_preparation_budget_publishes_no_receipt(self):
        self.installed(byte_limit=1)
        with self.assertRaisesRegex(JournalError, 'PREPARATION_CAPACITY'): self.record()
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 0)
        self.assertEqual(self.bridge.usage()['entries'], 0)

    def test_changed_catalog_inventory_before_selection_refuses(self):
        self.installed(); self.record(); self.promote(); executor = self.executor(); request = self.request()
        def alter(phase, value):
            if phase == 'after_snapshot_ready': self.catalog.publish(self.owner, program(pwm=True, literal=True))
        with patch.object(self.bridge, '_checkpoint', side_effect=alter):
            with self.assertRaisesRegex(JournalError, 'SELECTION_CHANGED'): executor.run(self.owner, request)
        self.assert_no_admission()

    def test_unresolved_original_run_prevents_reuse_after_repreparation(self):
        self.installed(); self.record(); self.promote(); self.reserve(run='run:2')
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            self.bridge.prepare(self.owner, self.digest, self.config['evaluatorId'], 'run:1')
        self.unavailable(); executor = self.executor(); request = self.request()
        with self.assertRaisesRegex(JournalError, 'PAT_EVIDENCE_UNAVAILABLE'): executor.run(self.owner, request)
        self.assert_no_admission()
