"""One real original matrix through vault publication and deterministic PAT.

No oracle substitution; no physical device or additional qualification worker.
"""
import json
import time
from unittest.mock import patch

from hms.journal import JournalError
from hms.pat_contracts import pat_digest
from hms_qualification.evidence import archive, reducer
from hms_qualification.evidence_authority import VaultEvidenceStore
from hms_qualification.evidence_vault import EvidenceVault, descriptor
from hms_qualification.vault_recorded_io.bridge import VaultRecordedIoBridge
from hms_qualification.vault_recorded_io.catalog import VaultRecordedPatCatalog
from hms_qualification.vault_recorded_io.execution import VaultRecordedPatExecutionStore
from test_io_service_execution import IoServiceExecutionTests
from test_io_service_authority import business
import hms_qualification.supervisor.supervisor_contracts as contracts


class VaultCatalogProcessTests(IoServiceExecutionTests):
    def test_actual_original_matrix_catalog_admission_and_cold_history(self):
        started = time.monotonic(); phases = []
        def mark(phase):
            phases.append(dict(phase=phase, elapsedMs=int((time.monotonic()-started)*1000)))
            self.emit('phase-times', phases)
        mark('test_body_started')
        self.emit('scope', dict(actualWorkerRequired=True, actualSemanticReducerRequired=True,
            matrixCases=30, workerMaxWallMs=60000, outerMaxSeconds=180,
            maxSingleFileBytes=16777216, maxVaultBytes=15728640, maxParentSqliteOpens=6,
            snapshotMaxMs=5000, plannedApplicationInvocations=1,
            coldVaultAndBridgeReopen=True, coldRuntimeAndSupervisorReopen=False,
            sessionDriftTested=False, catalogIntegrationRequired=True, physicalDeviceExecuted=False))
        self.create(); folder = self.parent/'vault'; folder.mkdir(mode=0o700)
        expected = descriptor(self.runtime.journal.authority_id)
        self.vault = EvidenceVault(folder/'evidence.db', expected, create=True)
        self.addCleanup(self.vault.close)
        consumer = VaultEvidenceStore(self.service, self.vault, create=True, owner=self.owner)
        self.assertEqual(consumer.consumer_identity, 'sha256:f4479f6d5b40c38e1c0645515633be63faaed2c8b1e913a1c16c522152fc6738')
        self.emit('installed-vault', expected); mark('installation_complete')
        def worker_checkpoint(phase, row):
            mark('worker_'+phase)
            if phase == 'launching':
                retained = self.lookup()
                self.assertEqual(retained['association']['receipt']['attemptId'], row['record']['attemptId'])
                self.emit('original-handoff', retained)
        with patch.object(self.bound, '_checkpoint', side_effect=worker_checkpoint): execution = self.call()
        mark('worker_complete'); row = execution['attempt']
        self.emit('worker-archive', dict(record=row['record'], association=execution['association']))
        self.assertTrue(row['record']['archive']['transportComplete'], row['record']['archive'])
        self.assertEqual(contracts.document(row['returnBytes'])['status'], 'captured')
        self.assertEqual(len(row['request']['bundleHeader']['caseIds']), 30)
        evaluator = self.config['evaluatorId']; original_run = 'run:1'
        def publication_checkpoint(phase, value): mark('import_'+phase)
        mark('import_started')
        with patch.object(consumer, '_checkpoint', side_effect=publication_checkpoint):
            imported = consumer.import_run(self.owner, evaluator, original_run)
        mark('import_complete')
        self.assertEqual(imported['evaluation']['inspectedCases'], 30)
        self.assertEqual(imported['evaluation']['unresolvedEffects'], 0)
        self.assertEqual(imported['intent']['anchor']['attemptId'], row['record']['attemptId'])
        self.emit('original-import', imported)
        self.assertEqual(business(self.runtime), self.before_business)

        program = json.loads(self.original['preparedRun']['bundle']['documents']['inputs/candidate.json'])
        digest = pat_digest(program)
        bridge = VaultRecordedIoBridge(consumer, self.runtime, (evaluator,))
        self.assertEqual(bridge._identity, 'sha256:c7bf48920c56d1e62b146e145bbf7ac377eb7ba18c4175d792738693885e2951')
        catalog = VaultRecordedPatCatalog(bridge, create=True, owner=self.owner)
        catalog.publish(self.owner, program)
        recorded = catalog.record_evaluation(self.owner, digest, evaluator, original_run)
        mark('catalog_recorded')
        self.assertEqual(recorded['receipt']['invocation']['publicationDigest'], imported['receiptDigest'])
        self.assertEqual(recorded['receipt']['invocation']['original']['attemptId'], row['record']['attemptId'])
        entry = catalog.describe(self.owner, digest)
        self.assertTrue(entry['eligibleForPromotion'], entry)
        active = catalog.transition(self.owner, digest, expected_revision=entry['catalogRevision'], target='active')
        self.assertTrue(active['eligibleForNewInstances'], active)
        self.emit('recorded-evaluation', recorded); self.emit('catalog-active', active)
        mark('catalog_activated')

        clock = [1000]
        self.runtime.wall_clock_ms = self.runtime.monotonic_ms = lambda: clock[0]
        self.runtime.journal.clock_ms = self.runtime.registry.monotonic_ms = lambda: clock[0]
        executor = VaultRecordedPatExecutionStore(self.runtime.journal, catalog, self.runtime.procedures)
        namespace = self.runtime.journal.issue_namespace(self.owner, 60000)['token']
        request = dict(protocol='hms.pat-run/0.1', replayNamespace=namespace, runKey='application:1',
            taskKind=program['taskKind'], inputProfile=program['inputProfile'], parameters={},
            evidenceMode='simulation', originUnixMs=1000, latestCompletionUnixMs=11000)
        admitted = executor.run(self.owner, request); mark('application_admitted')
        self.emit('application-admission', admitted); statuses = []
        for tick in range(8):
            self.runtime.tick()
            status = executor.status(self.owner, admitted['instanceId']); statuses.append(status)
            if status['procedure']['executionState'] in ('completed','failed','canceled'): break
            clock[0] += 20
        self.emit('application-statuses', dict(statuses=statuses, ticks=len(statuses), clock=clock[0]))
        self.assertEqual(status['procedure']['executionState'], 'completed', status)
        self.assertEqual(status['procedure']['unresolvedOperations'], [], status)
        self.assertTrue(all(step['executionState']=='completed' for step in status['procedure']['steps']))
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM operations').fetchone()[0], 1)
        effects = [list(value) for value in self.runtime.io_board.db.execute('SELECT * FROM io_effects')]
        expected_effects = {value[0]:list(value[1:]) for value in self.before_business['board']['io_effects']}
        selected = recorded['receipt']['applicability']['roleInstances']['io']
        expected_effects[selected][0] += 1; expected_effects[selected][1] += 1
        self.assertEqual({value[0]:value[1:] for value in effects}, expected_effects)
        self.emit('application-effects', dict(effects=effects, selectedInstance=selected,
            activations=1, completions=1, cancellations=0, physicalObjectiveVerified=False))
        mark('application_completed')

        # Historical requests must resolve the original admitted operation even
        # after configuration drift and loss of all prepared bridge entries.
        with (patch.object(self.bound, '_launch', side_effect=AssertionError('replacement worker')),
              patch.object(archive, 'read_original', side_effect=AssertionError('archive replay')),
              patch.object(reducer, 'reduce_original', side_effect=AssertionError('semantic replay')),
              patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replanning'))):
            self.assertEqual(executor.run(self.owner, request), status)
            self.assertEqual(catalog.record_evaluation(self.owner, digest, evaluator, original_run), recorded)
            self.configurations.configure(self.owner, 'config:2', self.config | {'revision':2}, expected_revision=1, runtime=self.runtime)
            self.assertFalse(catalog.describe(self.owner, digest)['eligibleForNewInstances'])
            with self.assertRaises(JournalError) as changed: executor.run(self.owner, request | {'runKey':'application:2'})
            self.assertNotEqual(changed.exception.code, 'PAT_NO_MATCH')
            mark('changed_configuration_refused')
            self.vault.close(); self.vault = EvidenceVault(folder/'evidence.db', expected)
            self.addCleanup(self.vault.close)
            consumer = VaultEvidenceStore(self.service, self.vault)
            bridge = VaultRecordedIoBridge(consumer, self.runtime, (evaluator,))
            catalog = VaultRecordedPatCatalog(bridge)
            executor = VaultRecordedPatExecutionStore(self.runtime.journal, catalog, self.runtime.procedures)
            with (patch.object(bridge, 'prepare', side_effect=AssertionError('cold historical preparation')),
                  patch.object(self.vault, 'snapshot_many', side_effect=AssertionError('cold historical view'))):
                self.assertEqual(catalog.record_evaluation(self.owner, digest, evaluator, original_run), recorded)
                self.assertEqual(executor.run(self.owner, request), status)
            self.assertEqual(consumer.import_run(self.owner, evaluator, original_run), imported)
            self.assertFalse(catalog.describe(self.owner, digest)['eligibleForNewInstances'])
            with self.assertRaises(JournalError) as cold: executor.run(self.owner, request | {'runKey':'application:3'})
            self.assertNotEqual(cold.exception.code, 'PAT_NO_MATCH')
            mark('cold_history_complete')
        self.assertEqual(tuple(self.db.execute('SELECT count(*) FROM '+name).fetchone()[0]
            for name in ('evi_intents','evi_publications','pc_evaluations','pc_decisions','px_instances','px_triggers','operations')),
            (1,1,1,1,1,1,1))
        self.assertEqual([list(value) for value in self.runtime.io_board.db.execute('SELECT * FROM io_effects')], effects)
        storage = dict(authorityBytes=(self.parent/'runtime/authority.db').stat().st_size,
            vaultBytes=(folder/'evidence.db').stat().st_size,
            references=self.vault._db.execute('SELECT count(*) FROM ev_documents').fetchone()[0],
            bodies=self.vault._db.execute('SELECT count(*) FROM ev_bodies').fetchone()[0])
        self.assertLessEqual(storage['authorityBytes'], 16777216); self.assertLessEqual(storage['vaultBytes'], 15728640)
        self.emit('actual-vault-catalog-checks', dict(originalAttemptId=row['record']['attemptId'],
            importReceiptDigest=imported['receiptDigest'], evaluationDigest=recorded['evaluationDigest'],
            instanceId=admitted['instanceId'], completeCases=30, oneQualificationWorker=True, realReducerUsed=True,
            exactOriginalKeyReplay=True, coldVaultAndBridgeHistory=True, sourceApplicationInvocations=1,
            freshConfigurationRefusal=changed.exception.code, freshColdRefusal=cold.exception.code,
            storage=storage, catalogIntegrated=True, physicalObjectiveVerified=False,
            aggregateDiskQuotaEnforced=False, physicalCapacityReserved=False))
        mark('test_body_complete')
