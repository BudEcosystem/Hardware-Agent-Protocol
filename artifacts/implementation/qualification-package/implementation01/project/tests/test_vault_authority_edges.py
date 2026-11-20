"""Additional authority boundaries; declared synthetic oracle, no actual worker."""
from unittest.mock import patch

from hms.journal import JournalError
from hms_qualification.evidence import archive, reducer
from hms_qualification.evidence_vault import EvidenceVault, descriptor
from hms_qualification.evidence_vault.connection import _Snapshot
from hms_qualification.evidence_authority import VaultEvidenceStore
from hms_qualification.evidence_authority import contracts as c
from test_vault_authority import VaultAuthorityTests

EXPECTED_CONSUMER = 'sha256:0e7ff6440fdb93e941ff4b5b0f2f275558f67f1e63a3c719c66756f81b7971d5'


class VaultAuthorityEdgeTests(VaultAuthorityTests):
    def bare_vault(self):
        self.create()
        folder = self.parent / 'vault'; folder.mkdir(mode=0o700)
        self.expected_vault = descriptor(self.runtime.journal.authority_id, max_pages=2048)
        self.vault = EvidenceVault(folder / 'hms_qualification.evidence.db', self.expected_vault, create=True)
        self.addCleanup(self.vault.close)
        return self.vault

    def installation_state(self):
        return dict(schema=[list(row) for row in self.db.execute(
            "SELECT name,type,sql FROM sqlite_master WHERE name GLOB 'evi_*' OR tbl_name GLOB 'evi_*' ORDER BY name")],
            anchors=[list(row) for row in self.db.execute("SELECT key,value FROM reg_meta WHERE key='vault_evidence_import'")])

    def test_current_consumer_identity_change_refuses_replay(self):
        self.fixture(); first = self.import_fixture()
        self.assertEqual(self.evidence.consumer_identity, EXPECTED_CONSUMER)
        with (patch.object(c, 'identity', return_value='sha256:' + '0' * 64),
              patch.object(archive, 'read_original', side_effect=AssertionError('archive repair')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('worker repair'))):
            with self.assertRaisesRegex(JournalError, 'IMPLEMENTATION_CHANGED'): self.import_call()
            with self.assertRaisesRegex(JournalError, 'IMPLEMENTATION_CHANGED'): self.evidence_lookup()
        self.assert_preserved((1, 1, 1))
        self.emit('identity-refusal', dict(detectorResultInjected=True, sourceFilesUnchanged=True,
            originalIntent=first['intentDigest'], replacementCreated=False))

    def test_malformed_authority_record_refuses_before_body_fetch_without_repair(self):
        self.fixture(); self.import_fixture()
        self.db.execute("UPDATE evi_intents SET record='retained invalid text type'")
        statements = []; self.db.set_trace_callback(lambda sql: statements.append(sql) if 'evi_intents' in sql else None)
        try:
            with patch.object(archive, 'read_original', side_effect=AssertionError('archive repair')):
                with self.assertRaises(JournalError): self.import_call()
                with self.assertRaises(JournalError): VaultEvidenceStore(self.service, self.vault)
                with self.assertRaises(JournalError): VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner)
        finally: self.db.set_trace_callback(None)
        self.assertFalse(any('SELECT sequence,evaluator,run,intent,record FROM evi_intents' in sql for sql in statements))
        retained = self.db.execute('SELECT typeof(record),record FROM evi_intents').fetchone()
        self.assertEqual(tuple(retained), ('text', 'retained invalid text type'))
        self.assertEqual(self.sizes_evidence(), (1, 1, 1)); self.assertEqual(self.sizes(), (1, 1))
        self.emit('malformed-authority', dict(recordType='text', retainedValue=retained[1],
            bodyFetchExecuted=False, reconstructed=False, statements=statements))

    def test_installation_failure_before_commit_retains_uninstalled_vault(self):
        self.bare_vault(); original = self.vault.descriptor()
        self.assertEqual(self.installation_state(), dict(schema=[], anchors=[]))
        with patch.object(VaultEvidenceStore, '_state', side_effect=RuntimeError('installation validation interruption')):
            with self.assertRaisesRegex(RuntimeError, 'installation validation interruption'):
                VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner)
        self.assertEqual(self.installation_state(), dict(schema=[], anchors=[]))
        self.assertEqual(self.vault.descriptor(), original)
        self.assertEqual(self.vault._db.execute('SELECT count(*) FROM ev_manifests').fetchone()[0], 0)
        self.assertIsNone(self.vault._lease); self.assertFalse(self.vault._db.in_transaction)
        self.assertFalse(self.db.in_transaction)
        self.emit('installation-rollback', dict(installed=False, vaultRetained=True,
            descriptor=original, authorityRecordsRetained=0, noRetry=True))

    def test_lost_installation_reply_reopens_original_association(self):
        self.bare_vault(); original = self.vault.descriptor(); check = _Snapshot.check; checks = []
        def interrupted(snapshot, owner):
            check(snapshot, owner); checks.append(1)
            if len(checks) == 2: raise RuntimeError('lost installation reply')
        with patch.object(_Snapshot, 'check', new=interrupted):
            with self.assertRaisesRegex(RuntimeError, 'lost installation reply'):
                VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner)
        self.assertEqual(len(checks), 2)
        before = self.installation_state(); self.assertEqual(len(before['anchors']), 1)
        self.assertIsNone(self.vault._lease); self.assertFalse(self.db.in_transaction)
        self.evidence = VaultEvidenceStore(self.service, self.vault)
        self.assertEqual(self.evidence.descriptor, original)
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'):
            VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner)
        self.assertEqual(self.installation_state(), before)
        self.assertEqual(self.sizes_evidence(), (0, 0, 0)); self.assertEqual(self.sizes(), (0, 0))
        self.emit('installation-reconciled', dict(descriptor=original, originalAssociationUnchanged=True,
            newIdentityCreated=False, attempts=0, schema=before))

    def test_published_history_survives_configuration_drift_without_replanning(self):
        self.fixture(); first = self.import_fixture()
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2},
            expected_revision=1, runtime=self.runtime)
        with (patch.object(archive, 'read_original', side_effect=AssertionError('archive replay')),
              patch.object(reducer, 'reduce_original', side_effect=AssertionError('semantic replay')),
              patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replanning')),
              patch.object(self.bound, '_launch', side_effect=AssertionError('worker replay'))):
            self.assertEqual(self.import_call(), first)
            self.assertEqual(self.evidence_lookup(), first)
        self.assert_preserved((1, 1, 1))
        self.emit('configuration-history', dict(published=first, currentConfigurationRevision=2,
            historicalOnly=True, catalogEligibilityEstablished=False, workerExecuted=False))
