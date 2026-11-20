"""Actual complete worker → original import → catalog → deterministic PAT."""
import json
import time
from unittest.mock import patch

from hms.journal import JournalError
from hms.pat_contracts import pat_digest
from hms.synthetic_io_runtime import IoRuntime
from test_io_service_execution import IoServiceExecutionTests
from evidence_compact.store import CompactIoEvidenceStore
from recorded_io.bridge import RecordedIoBridge
from recorded_io.catalog import RecordedPatCatalog
from recorded_io.execution import RecordedPatExecutionStore
from io_service_store import IoServiceConfigurationStore
from io_service_runs import IoServiceRunStore
from io_service_execution import IoServiceExecutionStore, BoundQualificationSupervisor
import supervisor_contracts as contracts

class RecordedIoCatalogProcessTests(IoServiceExecutionTests):
    def test_actual_original_matrix_catalog_execution_and_historical_replay(self):
        self.create()
        consumer = CompactIoEvidenceStore(self.service, create=True, owner=self.owner)
        evaluator = self.config['evaluatorId']; original_run = 'run:1'
        started = time.monotonic(); phases = []
        def checkpoint(phase, row):
            phases.append(dict(phase=phase, elapsedMs=int((time.monotonic()-started)*1000)))
            if phase == 'launching':
                retained = self.lookup()
                self.assertEqual(retained['association']['receipt']['attemptId'], row['record']['attemptId'])
                self.emit('original-handoff', retained)
        self.emit('scope', dict(actualWorkerRequired=True, actualSemanticInspectionRequired=True, matrixCases=30,
            workerMaxWallMs=60000, outerMaxSeconds=180, originalSingleFileLimit=16*1024*1024,
            plannedApplicationInvocations=1, physicalDeviceExecuted=False))
        with patch.object(self.bound, '_checkpoint', side_effect=checkpoint):
            execution = self.call()
        row = execution['attempt']
        self.emit('worker-archive', dict(record=row['record'], association=execution['association'], phases=phases))
        self.assertTrue(row['record']['archive']['transportComplete'], row['record']['archive'])
        self.assertEqual(contracts.document(row['returnBytes'])['status'], 'captured')
        imported = consumer.import_run(self.owner, evaluator, original_run)
        self.assertEqual(imported['evaluation']['inspectedCases'], 30)
        self.assertEqual(imported['evaluation']['unresolvedEffects'], 0)
        self.emit('original-import', imported)
        program = json.loads(self.original['preparedRun']['bundle']['documents']['inputs/candidate.json'])
        digest = pat_digest(program)
        bridge = RecordedIoBridge(consumer, self.runtime, (evaluator,))
        catalog = RecordedPatCatalog(bridge, create=True, owner=self.owner)
        catalog.publish(self.owner, program)
        recorded = catalog.record_evaluation(self.owner, digest, evaluator, original_run)
        self.assertEqual(recorded['receipt']['invocation']['importReceiptDigest'], imported['receiptDigest'])
        self.assertEqual(recorded['receipt']['invocation']['original']['attemptId'], row['record']['attemptId'])
        entry = catalog.describe(self.owner, digest)
        self.assertTrue(entry['eligibleForPromotion'], entry)
        active = catalog.transition(self.owner, digest, expected_revision=entry['catalogRevision'], target='active')
        self.assertTrue(active['eligibleForNewInstances'], active)
        self.emit('recorded-evaluation', recorded)
        self.emit('catalog-active', active)

        # Drive one original simulated application with an explicit virtual
        # clock. No real device, background service or additional worker runs.
        clock = [1000]
        self.runtime.wall_clock_ms = self.runtime.monotonic_ms = lambda: clock[0]
        self.runtime.journal.clock_ms = self.runtime.registry.monotonic_ms = lambda: clock[0]
        executor = RecordedPatExecutionStore(self.runtime.journal, catalog, self.runtime.procedures)
        namespace = self.runtime.journal.issue_namespace(self.owner, 60000)['token']
        request = dict(protocol='hms.pat-run/0.1', replayNamespace=namespace, runKey='application:1',
            taskKind=program['taskKind'], inputProfile=program['inputProfile'], parameters={},
            evidenceMode='simulation', originUnixMs=1000, latestCompletionUnixMs=11000)
        admitted = executor.run(self.owner, request)
        self.emit('application-admission', admitted)
        statuses = []
        for tick in range(8):
            self.runtime.tick()
            status = executor.status(self.owner, admitted['instanceId']); statuses.append(status)
            if status['procedure']['executionState'] in ('completed','failed','canceled'):
                break
            clock[0] += 20
        self.emit('application-statuses', dict(statuses=statuses, ticks=len(statuses), clock=clock[0]))
        self.assertEqual(status['procedure']['executionState'], 'completed', status)
        self.assertEqual(status['procedure']['unresolvedOperations'], [], status)
        self.assertTrue(all(step['executionState'] == 'completed' for step in status['procedure']['steps']), status)
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM operations').fetchone()[0], 1)
        effects = [list(value) for value in self.runtime.io_board.db.execute('SELECT * FROM io_effects')]
        self.emit('application-effects', dict(effects=effects, physicalObjectiveVerified=False))
        expected_effects = {row[0]:list(row[1:]) for row in self.before_business['board']['io_effects']}
        selected_instance = recorded['receipt']['applicability']['roleInstances']['io']
        expected_effects[selected_instance][0] += 1
        expected_effects[selected_instance][1] += 1
        self.assertEqual({row[0]:row[1:] for row in effects}, expected_effects)
        self.emit('application-effect-delta', dict(selectedInstance=selected_instance, activations=1, completions=1, cancellations=0, otherCountersUnchanged=True))
        self.assertEqual(executor.run(self.owner, request), status)

        self.configurations.configure(self.owner, 'config:2', self.config | {'revision':2}, expected_revision=1, runtime=self.runtime)
        self.assertFalse(catalog.describe(self.owner, digest)['eligibleForNewInstances'])
        with patch.object(self.bound, '_launch', side_effect=AssertionError('replacement worker')):
            self.assertEqual(catalog.record_evaluation(self.owner, digest, evaluator, original_run), recorded)
            self.assertEqual(executor.run(self.owner, request), status)
            with self.assertRaises(JournalError) as refused:
                executor.run(self.owner, request | {'runKey':'application:2'})
            self.assertNotEqual(refused.exception.code, 'PAT_NO_MATCH')
        self.emit('changed-context-refusal', dict(code=refused.exception.code, newInstanceCreated=False, novelty=False))

        self.bound.close(); self.runtime.close()
        self.runtime = IoRuntime(self.parent/'runtime', create=False, installation=self.document,
            wall_clock_ms=lambda:clock[0], monotonic_ms=lambda:clock[0], storage_profile='hms.sqlite.compact/0.1')
        self.db = self.runtime.journal._db
        self.configurations = IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry)
        self.runs = IoServiceRunStore(self.configurations)
        self.bound = BoundQualificationSupervisor(self.parent/'supervisor', expected_authority=self.supervisor_id)
        self.service = IoServiceExecutionStore(self.runs, self.bound)
        consumer = CompactIoEvidenceStore(self.service)
        bridge = RecordedIoBridge(consumer, self.runtime, (evaluator,))
        catalog = RecordedPatCatalog(bridge)
        executor = RecordedPatExecutionStore(self.runtime.journal, catalog, self.runtime.procedures)
        with (patch.object(self.bound, '_launch', side_effect=AssertionError('replacement worker')),
              patch.object(bridge, 'prepare', side_effect=AssertionError('historical preparation'))):
            self.assertEqual(catalog.record_evaluation(self.owner, digest, evaluator, original_run), recorded)
            self.assertEqual(catalog.evaluation(self.owner, recorded['evaluationDigest']), recorded['receipt'])
            self.assertEqual(executor.run(self.owner, request)['instanceId'], admitted['instanceId'])
            self.assertFalse(catalog.describe(self.owner, digest)['eligibleForNewInstances'])
        self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM pc_evaluations').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM px_instances').fetchone()[0], 1)
        self.assertEqual([list(value) for value in self.runtime.io_board.db.execute('SELECT * FROM io_effects')], effects)
        self.emit('recorded-integration-checks', dict(originalAttemptId=row['record']['attemptId'],
            importReceiptDigest=imported['receiptDigest'], catalogEvaluationDigest=recorded['evaluationDigest'],
            applicationInstanceId=admitted['instanceId'], completeCases=30, oneQualificationWorker=True,
            oneApplicationInvocation=True, exactOriginalKeyReplay=True, historicalReplayAfterConfigurationAndSessionDrift=True,
            unavailableEvidenceIsNovelty=False, physicalObjectiveVerified=False))
