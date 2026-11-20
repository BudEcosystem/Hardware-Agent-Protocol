"""Catalog boundary controls; successful qualification is an explicit fixture."""
from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms.pat_catalog import PatCatalog, _hash
from hms.pat_compiler import compiler_digest
from hms.pat_contracts import pat_digest
from test_io_evidence_compact import CompactIoEvidenceTests
from test_io_service_runs import business
from hms_qualification.evidence import reducer
from hms_qualification.evidence_compact.store import CompactIoEvidenceStore
from hms_qualification.recorded_io.bridge import RecordedIoBridge
from hms_qualification.recorded_io.catalog import RecordedPatCatalog, DOMAIN
from hms_qualification.recorded_io.execution import RecordedPatExecutionStore
from hms_qualification.recorded_io import contracts

class RecordedIoCatalogTests(CompactIoEvidenceTests):
    def installed(self, *, byte_limit=contracts.MAX_MEMO_BYTES):
        self.fixture(); self.imported = self.import_fixture()
        self.program = json.loads(self.original['preparedRun']['bundle']['documents']['inputs/candidate.json'])
        self.digest = pat_digest(self.program)
        self.bridge = RecordedIoBridge(self.evidence, self.runtime, (self.config['evaluatorId'],), byte_limit=byte_limit)
        self.catalog = RecordedPatCatalog(self.bridge, create=True, owner=self.owner)
        self.catalog.publish(self.owner, self.program)

    def record(self):
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            self.recorded = self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1')
        return self.recorded

    def promote(self):
        entry = self.catalog.describe(self.owner, self.digest)
        self.assertTrue(entry['eligibleForPromotion'], entry)
        return self.catalog.transition(self.owner, self.digest, expected_revision=entry['catalogRevision'], target='active')

    def request(self, key='application:1'):
        token = self.runtime.journal.issue_namespace(self.owner, 60000)['token']
        return dict(protocol='hms.pat-run/0.1', replayNamespace=token, runKey=key,
            taskKind=self.program['taskKind'], inputProfile=self.program['inputProfile'], parameters={},
            evidenceMode='simulation', originUnixMs=1000, latestCompletionUnixMs=11000)

    def unavailable(self):
        entry = self.catalog.describe(self.owner, self.digest)
        self.assertFalse(entry['eligibleForPromotion']); self.assertFalse(entry['eligibleForNewInstances'])
        self.assertEqual(entry['eligibilityReason'], 'PAT_EVIDENCE_UNAVAILABLE')
        return entry

    def test_original_invocation_records_and_promotes_with_static_compatibility(self):
        self.installed(); result = self.record(); active = self.promote()
        receipt = result['receipt']; inv = receipt['invocation']
        self.assertEqual(inv['importReceiptDigest'], self.imported['receiptDigest'])
        self.assertEqual(inv['original'], self.imported['receipt']['anchor'])
        self.assertEqual(receipt['environment']['profile'], 'hms.pat.environment/0.1')
        self.assertNotIn('endpointSession', receipt['environment']['roles']['io'])
        original = json.loads(self.original['preparedRun']['bundle']['documents']['inputs/descriptor.json'])
        self.assertEqual(receipt['applicability']['dependencies'][0]['endpointSession'], original['endpointSession'])
        self.assertTrue(active['eligibleForNewInstances']); self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(business(self.runtime), self.before_business)
        self.emit('recorded-fixture', dict(workerExecuted=False, semanticsVerified=False, recorded=result,
            active=active, preparation=self.bridge.usage(), originalImport=self.imported['receiptDigest']))

    def test_admission_verifier_uses_no_source_ledger_or_full_reducer(self):
        self.installed(); self.record()
        with (patch.object(Path, 'read_bytes', side_effect=AssertionError('filesystem during admission')),
              patch.object(self.evidence, '_state', side_effect=AssertionError('nested consumer transaction')),
              patch.object(self.bound.ledger, 'get', side_effect=AssertionError('external ledger')),
              patch.object(reducer, 'reduce_original', side_effect=AssertionError('semantic reduction during admission'))):
            self.promote()

    def test_cold_preparation_preserves_history_and_refuses_fresh_use(self):
        self.installed(); original = self.record(); self.promote()
        self.bridge = RecordedIoBridge(self.evidence, self.runtime, (self.config['evaluatorId'],))
        self.catalog = RecordedPatCatalog(self.bridge)
        with patch.object(self.bridge, 'prepare', side_effect=AssertionError('historical replay preparation')):
            self.assertEqual(self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1'), original)
            self.assertEqual(self.catalog.evaluation(self.owner, original['evaluationDigest']), original['receipt'])
            self.unavailable()

    def test_configuration_drift_allows_recording_history_but_not_promotion(self):
        self.installed()
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision':2}, expected_revision=1, runtime=self.runtime)
        result = self.record(); self.unavailable()
        self.assertEqual(result['receipt']['invocation']['original']['configurationRevision'], 1)
        self.assertEqual(self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1'), result)

    def test_changed_body_is_retained_and_never_becomes_eligibility(self):
        self.installed(); self.record(); self.promote()
        key, body = self.db.execute("SELECT b.digest,b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest WHERE d.path='inspection/case-00.json'").fetchone()
        bad = b'x' * len(body); self.db.execute('UPDATE ioec_bodies SET body=? WHERE digest=?', (bad, key))
        self.unavailable()
        self.assertEqual(self.db.execute('SELECT body FROM ioec_bodies WHERE digest=?', (key,)).fetchone()[0], bad)
        self.assertEqual(business(self.runtime), self.before_business)

    def test_missing_body_is_not_rebuilt_for_catalog_use(self):
        self.installed(); self.record()
        key = self.db.execute("SELECT digest FROM ioec_documents WHERE path='inspection/summary.json'").fetchone()[0]
        self.db.execute('DELETE FROM ioec_bodies WHERE digest=?', (key,))
        with patch.object(self.bound, '_launch', side_effect=AssertionError('replacement worker')):
            self.unavailable()
        self.assertIsNone(self.db.execute('SELECT 1 FROM ioec_bodies WHERE digest=?', (key,)).fetchone())

    def test_lower_preparation_capacity_publishes_no_evaluation(self):
        self.installed(byte_limit=1)
        with self.assertRaisesRegex(JournalError, 'PREPARATION_CAPACITY'):
            self.record()
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 0)
        self.assertEqual(self.bridge.usage()['entries'], 0)

    def test_explicit_mount_cannot_be_replaced_by_legacy_or_reinitialized(self):
        self.installed()
        with self.assertRaisesRegex(JournalError, 'UNSUPPORTED_PAT_CATALOG'):
            PatCatalog(self.runtime.journal, compiler_digest=compiler_digest, environment=lambda *args: {}, evaluators=())
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'):
            RecordedPatCatalog(self.bridge, create=True, owner=self.owner)
        self.db.execute('DROP TABLE pc_events')
        with self.assertRaisesRegex(JournalError, 'SCHEMA_CHANGED'):
            RecordedPatCatalog(self.bridge)
        self.assertIsNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='pc_events'").fetchone())

    def test_revocation_between_preparation_and_recording_prevents_publication(self):
        self.installed()
        def checkpoint(phase, value):
            if phase == 'before_catalog_publication':
                self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with patch.object(self.bridge, '_checkpoint', side_effect=checkpoint):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
                self.record()
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 0)

    def test_new_unimported_run_cannot_be_ignored_by_warming_old_success(self):
        self.installed(); self.record(); self.promote(); self.reserve(run='run:2')
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            self.bridge.prepare(self.owner, self.digest, self.config['evaluatorId'], 'run:1')
        self.unavailable()
        self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM iosr_runs').fetchone()[0], 2)

    def test_inactive_source_binding_is_unavailable_before_environment_filter(self):
        self.installed(); self.record(); self.promote()
        executor = RecordedPatExecutionStore(self.runtime.journal, self.catalog, self.runtime.procedures)
        request = self.request()
        self.db.execute('UPDATE reg_bindings SET active=0 WHERE instance=?',
                        (self.recorded['receipt']['applicability']['roleInstances']['io'],))
        with self.assertRaises(JournalError) as caught:
            executor.run(self.owner, request)
        self.assertEqual(caught.exception.code, 'PAT_EVIDENCE_UNAVAILABLE')
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 0)
        self.emit('selection-availability', dict(code=caught.exception.code, novelty=False,
            instanceRows=0, workerExecuted=False, semanticsVerified=False))

    def test_missing_presence_is_unavailable_without_creating_an_instance(self):
        self.installed(); self.record(); self.promote()
        executor = RecordedPatExecutionStore(self.runtime.journal, self.catalog, self.runtime.procedures)
        request = self.request(); self.db.execute('DELETE FROM reg_presence')
        with self.assertRaises(JournalError) as caught:
            executor.run(self.owner, request)
        self.assertEqual(caught.exception.code, 'PAT_BINDINGS_UNAVAILABLE')
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 0)

    def test_loaded_identity_change_prevents_fresh_eligibility(self):
        self.installed(); self.record()
        with patch.object(contracts, 'LOADED_IDENTITY', 'sha256:' + '0'*64):
            with self.assertRaisesRegex(JournalError, 'MOUNT_CHANGED'):
                self.catalog.describe(self.owner, self.digest)

    def test_impure_verifier_unwinds_even_if_sql_error_is_swallowed(self):
        self.installed(); self.record()
        before = self.db.total_changes
        def impure(context, receipt):
            try:
                self.db.execute("DELETE FROM pc_evaluations")
            except Exception:
                pass
            return True
        registered = self.catalog._evaluators[self.config['evaluatorId']]
        self.catalog._evaluators = MappingProxyType({registered.evaluator_id: replace(registered, verify_evidence=impure)})
        with self.assertRaisesRegex(JournalError, 'PAT_EVIDENCE_PROVIDER_IMPURE'):
            self.catalog.describe(self.owner, self.digest)
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 1)

    def test_same_original_key_concurrent_recording_has_one_receipt(self):
        self.installed(); inside = []; entered = [False]
        def checkpoint(phase, value):
            if phase == 'before_catalog_publication' and not entered[0]:
                entered[0] = True
                inside.append(self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1'))
        with patch.object(self.bridge, '_checkpoint', side_effect=checkpoint):
            result = self.record()
        self.assertEqual(inside, [result])
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pc_events WHERE kind='evaluation_recorded'").fetchone()[0], 1)

    def test_no_legacy_callback_or_caller_result_ingress(self):
        self.installed()
        with self.assertRaisesRegex(JournalError, 'EXPLICIT_INVOCATION_REQUIRED'):
            self.catalog.evaluate(self.owner, self.digest, self.config['evaluatorId'], 'run:1')
        for name in ('result', 'path', 'callback', 'attempt'):
            with self.assertRaises(JournalError):
                self.catalog.record_evaluation(self.owner, self.digest, self.config['evaluatorId'], 'run:1', **{name:{}})
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 0)

    def test_invalid_body_type_is_refused_before_payload_fetch(self):
        self.installed(); self.record()
        key = self.db.execute("SELECT digest FROM ioec_documents WHERE path='inspection/summary.json'").fetchone()[0]
        bad = 'x\0' + 'z' * 65536
        self.db.execute('UPDATE ioec_bodies SET body=? WHERE digest=?', (bad, key))
        statements = []; self.db.set_trace_callback(statements.append)
        try:
            self.unavailable()
        finally:
            self.db.set_trace_callback(None)
        self.assertFalse(any('SELECT d.path,b.body' in statement for statement in statements))
        self.assertEqual(self.db.execute('SELECT typeof(body) FROM ioec_bodies WHERE digest=?', (key,)).fetchone()[0], 'text')
        self.emit('body-preflight', dict(statements=statements, payloadFetched=False, mutationRetained=True))

    def test_temporary_source_shadow_is_rejected_by_the_admission_guard(self):
        self.installed(); self.record()
        self.db.execute('CREATE TEMP TABLE reg_presence AS SELECT * FROM main.reg_presence')
        with self.assertRaisesRegex(JournalError, 'PAT_EVIDENCE_PROVIDER_IMPURE'):
            self.catalog.describe(self.owner, self.digest)
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM sqlite_temp_master WHERE name='reg_presence'").fetchone())
        self.emit('temporary-shadow', dict(rows=[list(row) for row in self.db.execute('SELECT * FROM temp.reg_presence')],
            refused=True, removedDuringTest=False, workerExecuted=False))

    def test_rehashed_cross_run_invocation_cannot_borrow_another_import(self):
        self.installed(); original = self.record(); second = self.second_fixture()
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            self.bridge.prepare(self.owner, self.digest, self.config['evaluatorId'], 'run:1')
        receipt = json.loads(canonical(original['receipt']))
        receipt['invocation']['original'] = second['receipt']['anchor'] | {'runId':'run:1'}
        receipt['invocation']['importReceiptDigest'] = second['receiptDigest']
        changed = _hash(DOMAIN, receipt)
        self.db.execute('UPDATE pc_evaluations SET digest=?,document=? WHERE digest=?',
                        (changed, canonical(receipt), original['evaluationDigest']))
        self.db.execute('UPDATE pc_entries SET evaluation=? WHERE artifact=?', (changed, self.digest))
        self.unavailable()
        self.assertEqual(self.db.execute('SELECT document FROM pc_evaluations WHERE digest=?', (changed,)).fetchone()[0], canonical(receipt))
        self.emit('cross-run-catalog-refusal', dict(changedDigest=changed, claimedLogicalRun='run:1',
            borrowedAttempt=second['receipt']['anchor']['attemptId'], mutationRetained=True, workerExecuted=False))
