"""Complete relevant PAT inventory and original-key reconciliation controls.

Both qualifications are explicit synthetic oracle fixtures. No worker runs.
"""
from contextlib import contextmanager
from unittest.mock import patch

from hms.journal import Context, JournalError
from hms.pat_contracts import pat_digest
from evidence import reducer
from test_pat_io_contracts import program
from test_io_evidence_import_history import IoEvidenceImportHistoryTests
from test_vault_recorded_catalog import VaultRecordedCatalogTests


class VaultCatalogInventoryTests(VaultRecordedCatalogTests):
    def pair(self):
        self.installed()
        self.second_program = program(pwm=True, literal=True)
        self.second_digest = pat_digest(self.second_program)
        reserve = self.reserve
        def reserve_second(*, run):
            return reserve(run=run, candidate=self.second_program)
        with patch.object(self, 'reserve', side_effect=reserve_second):
            self.second_import = IoEvidenceImportHistoryTests.second_fixture(self)
        self.catalog.publish(self.owner, self.second_program)
        self.record(); self.promote()
        with patch.object(reducer, 'inspect_io_group', side_effect=self.oracle):
            self.second_recorded = self.catalog.record_evaluation(self.owner, self.second_digest,
                self.config['evaluatorId'], 'run:2')
        entry = self.catalog.describe(self.owner, self.second_digest)
        self.assertTrue(entry['eligibleForPromotion'], entry)
        self.catalog.transition(self.owner, self.second_digest,
            expected_revision=entry['catalogRevision'], target='active')
        self.assertNotEqual(self.digest, self.second_digest)
        self.assertEqual(self.bridge.usage()['entries'], 2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pc_entries WHERE state='active'").fetchone()[0], 2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM evi_publications').fetchone()[0], 2)

    def forget_second(self):
        with self.bridge._mutex:
            forgotten = self.bridge._entries.pop((self.config['evaluatorId'], 'run:2'))
            self.bridge._bytes -= forgotten.charge

    def test_two_eligible_programs_share_one_view_and_refuse_ambiguity(self):
        self.pair(); executor = self.executor(); request = self.request(); held = []
        def observe(phase, value):
            if phase == 'after_snapshot_ready':
                held.append(dict(keys=[list(key) for key in value], manifests=len(self.bridge._held.lease.keys()),
                    usage=self.bridge._held.lease.usage()))
        with patch.object(self.bridge, '_checkpoint', side_effect=observe):
            with self.assertRaisesRegex(JournalError, 'PAT_AMBIGUOUS'): executor.run(self.owner, request)
        self.assertEqual(len(held), 1); self.assertEqual(held[0]['manifests'], 2)
        self.assertEqual(held[0]['keys'], [[self.config['evaluatorId'], 'run:1'], [self.config['evaluatorId'], 'run:2']])
        self.assert_no_admission()
        self.emit('complete-inventory', dict(held=held, refusal='PAT_AMBIGUOUS',
            workerExecuted=False, semanticsVerified=False, physicalObjectiveVerified=False))

    def test_unprepared_second_program_cannot_manufacture_unique_selection(self):
        self.pair(); self.forget_second(); executor = self.executor(); request = self.request()
        with patch.object(self.vault, 'snapshot_many', side_effect=AssertionError('partial vault request')):
            with self.assertRaisesRegex(JournalError, 'PREPARATION_UNAVAILABLE'): executor.run(self.owner, request)
        self.assert_no_admission()
        self.emit('missing-member', dict(programs=2, prepared=1, admitted=0,
            novelty=False, workerExecuted=False, semanticsVerified=False))

    def test_missing_second_manifest_body_cannot_manufacture_unique_selection(self):
        self.pair(); executor = self.executor(); request = self.request()
        key = self.vault._db.execute("SELECT digest FROM ev_documents WHERE sequence=2 AND path='original/control/handoff.json'").fetchone()[0]
        self.assertEqual(self.vault._db.execute('SELECT count(*) FROM ev_documents WHERE digest=?', (key,)).fetchone()[0], 1)
        self.vault._db.execute('DELETE FROM ev_bodies WHERE digest=?', (key,))
        with patch.object(self.bound, '_launch', side_effect=AssertionError('replacement worker')):
            with self.assertRaises(JournalError) as caught: executor.run(self.owner, request)
        self.assertNotIn(caught.exception.code, ('PAT_NO_MATCH', 'PAT_AMBIGUOUS'))
        self.assert_no_admission()
        self.assertIsNone(self.vault._db.execute('SELECT 1 FROM ev_bodies WHERE digest=?', (key,)).fetchone())
        self.emit('missing-body', dict(refusal=caught.exception.code, retainedMissingDigest=key,
            programs=2, admitted=0, novelty=False, workerExecuted=False, semanticsVerified=False))

    def test_unauthorized_source_does_not_require_its_preparation(self):
        self.pair(); self.forget_second()
        user = Context('gpio-only', self.owner.deployment)
        source = self.recorded['receipt']['applicability']['roleInstances']['io']
        for target, verb in (('*', 'namespace'), (source, 'read'), (source, 'invoke:gpio_pulse')):
            self.runtime.registry.grant(self.owner, user.principal, target, verb)
        request = self.request() | {'replayNamespace':self.runtime.journal.issue_namespace(user, 60000)['token']}
        executor = self.executor(); held = []
        def observe(phase, value):
            if phase == 'after_snapshot_ready': held.append([list(key) for key in value])
        with patch.object(self.bridge, '_checkpoint', side_effect=observe): result = executor.run(user, request)
        self.assertEqual(held, [[[self.config['evaluatorId'], 'run:1']]])
        self.assertEqual(self.db.execute('SELECT artifact_digest FROM px_instances').fetchone()[0], self.digest)
        self.emit('authorized-inventory', dict(instanceId=result['instanceId'], held=held,
            unrelatedProgramPrepared=False, workerExecuted=False, semanticsVerified=False))

    def test_lost_reply_after_commit_reconciles_original_instance_without_view(self):
        self.installed(); self.record(); self.promote(); executor = self.executor(); request = self.request()
        original = self.vault.snapshot_many
        @contextmanager
        def lose_reply(*args, **kwargs):
            with original(*args, **kwargs) as lease:
                yield lease
                self.assertFalse(self.db.in_transaction)
                self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
                raise RuntimeError('reply lost after actual admission commit')
        with patch.object(self.vault, 'snapshot_many', side_effect=lose_reply):
            with self.assertRaisesRegex(RuntimeError, 'reply lost after actual admission commit'):
                executor.run(self.owner, request)
        original_id = self.db.execute('SELECT id FROM px_instances').fetchone()[0]
        with (patch.object(self.vault, 'snapshot_many', side_effect=AssertionError('fresh historical view')),
              patch.object(self.bridge, 'prepare', side_effect=AssertionError('fresh historical qualification'))):
            replay = executor.run(self.owner, request)
        self.assertEqual(replay['instanceId'], original_id)
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_triggers').fetchone()[0], 1)
        self.assertIsNone(self.vault._lease)
        self.emit('lost-reply', dict(instanceId=original_id, originalKeyReconciled=True,
            workerExecuted=False, semanticsVerified=False))
