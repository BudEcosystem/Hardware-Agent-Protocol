"""Actual reserved/handoff worker through evidence import; no success fixtures."""
import time
from unittest.mock import patch

from hms.journal import JournalError
from test_io_service_execution import IoServiceExecutionTests
from test_io_service_runs import business
from evidence import archive as evidence_archive
from evidence_compact.store import CompactIoEvidenceStore
import supervisor_contracts as contracts


class CompactIoEvidenceProcessTests(IoServiceExecutionTests):
    def test_compact_bound_worker_import_and_historical_replay(self):
        self.create()
        consumer = CompactIoEvidenceStore(self.service, create=True, owner=self.owner)
        evaluator = self.config['evaluatorId']; run = 'run:1'
        self.emit('source-business-before', self.before_business)
        self.emit('run-reservation', {key: self.original[key] for key in ('reservation', 'reservationDigest')})
        self.emit('supervisor-authority', dict(authorityId=self.supervisor_id))
        self.emit('integration-scope', dict(actualWorkerRequired=True, actualSemanticInspectionRequired=True,
            matrixCases=30, workerMaxWallMs=60000, outerMaxSeconds=180,
            physicalDeviceExecuted=False, catalogAdmissionClaimed=False))
        started = time.monotonic(); phases = []
        def checkpoint(phase, row):
            phases.append(dict(phase=phase, elapsedMs=int((time.monotonic()-started)*1000)))
            if phase == 'launching':
                original = self.lookup()
                self.assertEqual(original['association']['receipt']['attemptId'], row['record']['attemptId'])
                self.assertEqual(original['association']['receipt']['reservationDigest'], self.original['reservationDigest'])
                self.emit('launching-handoff', original)
        with patch.object(self.bound, '_checkpoint', side_effect=checkpoint):
            execution = self.call()
        row = execution['attempt']; archive = row['record']['archive']
        self.emit('worker-archive', dict(association=execution['association'], record=row['record'], phases=phases))
        self.assertEqual(row['record']['state'], 'archived')
        if not archive['transportComplete'] or contracts.document(row['returnBytes'])['status'] != 'captured':
            with self.assertRaises(JournalError): consumer.import_run(self.owner, evaluator, run)
            sizes = [self.db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                     for name in ('ioec_runs', 'ioec_documents')]
            self.assertEqual(sizes, [0, 0])
            self.emit('failed-worker-import-refusal', dict(importRows=sizes[0], documentRows=sizes[1],
                sourceEffectsUnchanged=business(self.runtime)==self.before_business, replacementWorkerLaunched=False))
        self.assertTrue(archive['transportComplete'], archive)
        self.assertEqual(contracts.document(row['returnBytes'])['status'], 'captured')
        self.assertEqual([item['phase'] for item in phases], ['admitted', 'launching', 'spawned', 'producer_settled', 'archived'])
        result = consumer.import_run(self.owner, evaluator, run)
        self.emit('actual-import-receipt', result)
        evaluation = result['evaluation']; anchor = evaluation['anchor']
        self.assertEqual(evaluation['inspectedCases'], 30)
        self.assertEqual(evaluation['unresolvedEffects'], 0)
        self.assertFalse(evaluation['physicalObjectiveVerified'])
        self.assertFalse(evaluation['catalogActivated'])
        self.assertEqual(anchor['attemptId'], row['record']['attemptId'])
        self.assertEqual(anchor['handoffDigest'], execution['association']['receiptDigest'])
        self.assertEqual(anchor['supervisorAuthorityId'], self.supervisor_id)
        self.assertEqual(anchor['configurationReceiptDigest'], self.configuration_receipt['receiptDigest'])
        self.assertEqual(business(self.runtime), self.before_business)
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        self.reopened(runtime=True)
        consumer = CompactIoEvidenceStore(self.service)
        with (patch.object(self.bound, '_launch', side_effect=AssertionError('replacement launch')),
              patch.object(evidence_archive, 'read_original', side_effect=AssertionError('rebuilding historical evidence')),
              patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan'))):
            self.assertEqual(consumer.import_run(self.owner, evaluator, run), result)
            self.assertEqual(consumer.lookup(self.owner, evaluator, run), result)
            self.assertEqual(self.call(runtime=None, installed_configuration=None), execution)
        self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ioec_runs').fetchone()[0], 1)
        self.assertEqual(business(self.runtime), self.before_business)
        references = self.db.execute('SELECT count(*) FROM ioec_documents').fetchone()[0]
        bodies = self.db.execute('SELECT count(*) FROM ioec_bodies').fetchone()[0]
        self.assertLess(bodies, references)
        self.emit('compact-body-accounting', dict(references=references, bodies=bodies,
            expandedBytes=result['receipt']['closure']['bytes'],
            uniqueBodyBytes=self.db.execute('SELECT sum(length(body)) FROM ioec_bodies').fetchone()[0],
            originalSingleFileLimit=16*1024*1024, actualWorkerExecuted=True))
        self.emit('bound-import-replay-checks', dict(attemptId=row['record']['attemptId'],
            receiptDigest=result['receiptDigest'], exactReplayAfterConfigurationAndSessionDrift=True,
            completeCases=30, oneWorkerLaunched=True, sourceEffectsUnchanged=True,
            freshEligibilityUnderChangedConfigurationClaimed=False, physicalObjectiveVerified=False))
