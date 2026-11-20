"""Real complete worker/reducer through the authority-owned evidence vault."""
import time
from unittest.mock import patch

from test_io_service_execution import IoServiceExecutionTests

from evidence import archive, reducer
from evidence_authority import VaultEvidenceStore
from evidence_vault import EvidenceVault, descriptor
from test_io_service_authority import business
import supervisor_contracts as contracts


class VaultOriginalRunTests(IoServiceExecutionTests):
    def test_actual_original_matrix_import_and_cold_vault_history(self):
        started=time.monotonic(); phases=[]
        def mark(phase):
            phases.append(dict(phase=phase,elapsedMs=int((time.monotonic()-started)*1000)))
            self.emit('phase-times',phases)
        mark('test_body_started')
        self.emit('scope',dict(actualWorkerRequired=True,actualSemanticReducerRequired=True,
            matrixCases=30,workerMaxWallMs=60000,outerMaxSeconds=180,
            maxSingleFileBytes=16777216,maxVaultBytes=15728640,maxParentSqliteOpens=6,
            snapshotMaxMs=5000,plannedApplicationInvocations=0,
            coldVaultReopen=True,coldRuntimeAndSupervisorReopen=False,
            sessionDriftTested=False,catalogActivated=False,physicalDeviceExecuted=False))
        self.create()
        folder=self.parent/'vault'; folder.mkdir(mode=0o700)
        expected=descriptor(self.runtime.journal.authority_id)
        self.vault=EvidenceVault(folder/'evidence.db',expected,create=True)
        self.addCleanup(self.vault.close)
        consumer=VaultEvidenceStore(self.service,self.vault,create=True,owner=self.owner)
        self.assertEqual(consumer.consumer_identity,'sha256:d71915ba422d711245669bf2e076378527f276d8e716b2be772ec0379dbbb76d')
        mark('installation_complete')
        self.emit('installed-vault',expected)
        def worker_checkpoint(phase,row):
            mark('worker_'+phase)
            if phase=='launching':
                retained=self.lookup()
                self.assertEqual(retained['association']['receipt']['attemptId'],row['record']['attemptId'])
                self.emit('original-handoff',retained)
        with patch.object(self.bound,'_checkpoint',side_effect=worker_checkpoint):
            execution=self.call()
        mark('worker_complete')
        row=execution['attempt']
        self.emit('worker-archive',dict(record=row['record'],association=execution['association']))
        self.assertTrue(row['record']['archive']['transportComplete'],row['record']['archive'])
        self.assertEqual(contracts.document(row['returnBytes'])['status'],'captured')
        self.assertEqual(len(row['request']['bundleHeader']['caseIds']),30)
        evaluator=self.config['evaluatorId']; original_run='run:1'
        def publication_checkpoint(phase,value): mark('import_'+phase)
        mark('import_started')
        with patch.object(consumer,'_checkpoint',side_effect=publication_checkpoint):
            imported=consumer.import_run(self.owner,evaluator,original_run)
        mark('import_complete')
        self.assertEqual(imported['evaluation']['inspectedCases'],30)
        self.assertEqual(imported['evaluation']['unresolvedEffects'],0)
        self.assertEqual(imported['intent']['anchor']['attemptId'],row['record']['attemptId'])
        self.assertTrue(all(imported['evaluation'][name] is False for name in
            ('physicalObjectiveVerified','wallDeadlineAttested','aggregateDiskQuotaEnforced','catalogActivated')))
        self.emit('original-import',imported)
        self.assertEqual(business(self.runtime),self.before_business)

        # These traps apply only after real import. Initial archive reading and
        # semantic reduction above use their unchanged production implementations.
        with (patch.object(self.bound,'_launch',side_effect=AssertionError('replacement worker')),
              patch.object(archive,'read_original',side_effect=AssertionError('archive replay')),
              patch.object(reducer,'reduce_original',side_effect=AssertionError('semantic replay')),
              patch.object(self.configurations,'prepare_run',side_effect=AssertionError('replanning'))):
            self.assertEqual(consumer.import_run(self.owner,evaluator,original_run),imported)
            mark('warm_replay_complete')
            self.configurations.configure(self.owner,'config:2',self.config|{'revision':2},
                expected_revision=1,runtime=self.runtime)
            mark('configuration_drift_committed')
            self.vault.close()
            self.vault=EvidenceVault(folder/'evidence.db',expected)
            self.addCleanup(self.vault.close)
            consumer=VaultEvidenceStore(self.service,self.vault)
            mark('cold_vault_reopened')
            self.assertEqual(consumer.lookup(self.owner,evaluator,original_run),imported)
            self.assertEqual(consumer.import_run(self.owner,evaluator,original_run),imported)
            mark('cold_changed_configuration_history_complete')
        self.assertEqual(self.sizes(),(1,1))
        self.assertEqual(tuple(self.db.execute('SELECT count(*) FROM '+name).fetchone()[0]
            for name in ('evi_intents','evi_publications')),(1,1))
        self.assertEqual(self.vault._db.execute('SELECT count(*) FROM ev_manifests').fetchone()[0],1)
        self.assertEqual(business(self.runtime),self.before_business)
        storage=dict(authorityBytes=(self.parent/'runtime/authority.db').stat().st_size,
            vaultBytes=(folder/'evidence.db').stat().st_size,
            references=self.vault._db.execute('SELECT count(*) FROM ev_documents').fetchone()[0],
            bodies=self.vault._db.execute('SELECT count(*) FROM ev_bodies').fetchone()[0])
        self.assertLessEqual(storage['authorityBytes'],16777216)
        self.assertLessEqual(storage['vaultBytes'],15728640)
        self.emit('actual-vault-checks',dict(originalAttemptId=row['record']['attemptId'],
            importReceiptDigest=imported['receiptDigest'],intentDigest=imported['intentDigest'],
            completeCases=30,oneQualificationWorker=True,realReducerUsed=True,
            exactOriginalKeyReplay=True,coldVaultHistoryAfterConfigurationDrift=True,
            coldRuntimeAndSupervisorReopen=False,sessionDriftTested=False,
            authorityBusinessRowsUnchanged=True,sourceApplicationInvocations=0,
            storage=storage,catalogIntegrated=False,physicalObjectiveVerified=False,
            aggregateDiskQuotaEnforced=False,physicalCapacityReserved=False))
        mark('test_body_complete')
