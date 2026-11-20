"""Exact current group attempts, shared cutoffs and retained partial evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy, CEILINGS
from hms.pat_io_group_budget import IoGroupBudget
from hms.pat_io_group_worker import run_io_group
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings, REQUIRED
from test_pat_io_contracts import program


class GroupFixture:
    @classmethod
    def setUpClass(cls):
        cls.document=normalize_installation(installation())
        cls.bindings=bindings(cls.document)

    def options(self,pwm=False):
        return dict(candidate=program(pwm=pwm,literal=True),installation=self.document,
            descriptor=self.bindings['pwm' if pwm else 'gpio']['descriptor'],challenge_bindings=self.bindings)

    def matrix(self,limits=None):
        o=self.options()
        return IoCombinedMatrixPolicy(self.document).generate(o['candidate'],o['descriptor'],self.bindings,limits=limits)


class IoGroupBudgetTests(GroupFixture,unittest.TestCase):
    def budget(self,limits=None):
        return IoGroupBudget(self.matrix(limits),started=time.monotonic())

    def test_negative_preflight_distinguishes_refused_and_not_applicable(self):
        from hms.pat_io_group_worker import _candidate
        options=self.options(); cases=[c for c in self.matrix()['cases'] if c['kind']=='candidate' and
                                      c['domainCase']['expected']['staticOutcome']!='applicable']
        self.assertEqual(len(cases),4)
        with patch('hms.pat_io_group_worker.ConflictIoTrialEngine',side_effect=AssertionError('negative runtime')):
            for case in cases:
                result=_candidate(None,case,options,None);expected=case['domainCase']['expected']
                self.assertEqual(result['staticOutcome'],expected['staticOutcome'])
                self.assertEqual(result['errorCode'],'PAT_NOT_APPLICABLE' if expected['staticOutcome']=='not_applicable' else expected['errorCode'])
                self.assertFalse(result['executionPerformed']);self.assertEqual(result['operationIds'],[])

    def test_exact_case_order_cannot_skip_or_run_two_engines(self):
        b=self.budget();cases=self.matrix()['cases']
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_CASE_ORDER'):b.begin(cases[1]['caseId'])
        t=b.begin(cases[0]['caseId']);t.bind(cases[0]['programDigest'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_ENGINE_REUSE'):t.bind(cases[0]['programDigest'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_CASE_ORDER'):b.begin(cases[1]['caseId'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_CASE_MISMATCH'):t.assert_case(cases[1]['caseId'])

    def test_program_mismatch_and_stale_ticket_refuse(self):
        b=self.budget();cases=self.matrix()['cases'];t=b.begin(cases[0]['caseId'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_PROGRAM_MISMATCH'):t.bind('sha256:'+'0'*64)
        t.bind(cases[0]['programDigest']);b.end(t,operation_count=0,scheduler_ticks=0)
        b.begin(cases[1]['caseId'])
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_STALE_TICKET'):t.record(1)

    def test_combined_records_include_reserved_terminal_and_span_cases(self):
        b=self.budget(CEILINGS|{'maxRecords':3});cases=self.matrix()['cases']
        t=b.begin(cases[0]['caseId']);t.bind(cases[0]['programDigest']);t.record(1)
        b.end(t,operation_count=0,scheduler_ticks=0)
        b.begin(cases[1]['caseId']);b.record(1)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_EVIDENCE_LIMIT'):b.record(1)
        self.assertEqual(b.snapshot()['charged']['records'],3)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_STOPPED'):b.record(1)
        b.terminal(1,success=False)

    def test_combined_bytes_are_charged_before_any_writer(self):
        b=self.budget(CEILINGS|{'maxProducerBytes':65538});b.record(2)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_EVIDENCE_LIMIT'):b.record(1)
        self.assertEqual(b.snapshot()['charged']['producerBytes'],65538)

    def test_closed_state_counts_toward_derived_closure_and_stops_on_overflow(self):
        b=self.budget(CEILINGS|{'maxDerivedBytes':65538});b.observe_state(2)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_DERIVED_LIMIT'):b.observe_state(1)
        self.assertEqual(b.snapshot()['charged']['observedStateBytes'],2)
        self.assertFalse(b.snapshot()['hardAggregateFilesystemQuota'])

    def test_case_tick_and_admission_limits_include_rejected_probe_reservations(self):
        b=self.budget();case=self.matrix()['cases'][0];t=b.begin(case['caseId']);t.bind(case['programDigest'])
        t.admission(0)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_OPERATION_LIMIT'):t.admission(case['plannedChildOperations'])
        for _ in range(case['schedulerTickCeiling']):t.tick()
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_TICK_LIMIT'):t.tick()
        self.assertEqual(b.snapshot()['charged']['schedulerTicks'],case['schedulerTickCeiling'])

    def test_deadline_is_group_origin_and_regression_also_refuses(self):
        matrix=self.matrix()
        with patch('hms.pat_io_group_budget.time.monotonic',return_value=100):
            b=IoGroupBudget(matrix,started=100)
            t=b.begin(matrix['cases'][0]['caseId']);t.bind(matrix['cases'][0]['programDigest'])
            b.end(t,operation_count=0,scheduler_ticks=0)
        with patch('hms.pat_io_group_budget.time.monotonic',return_value=160):
            with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_WALL_LIMIT'):b.begin(matrix['cases'][1]['caseId'])
        b.terminal(1,success=False)
        with patch('hms.pat_io_group_budget.time.monotonic',return_value=100):b=IoGroupBudget(matrix,started=100)
        with patch('hms.pat_io_group_budget.time.monotonic',return_value=99):
            with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_WALL_LIMIT'):b.check()

    def test_incomplete_group_cannot_emit_success_or_reuse_terminal_reservation(self):
        b=self.budget()
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_INCOMPLETE'):b.terminal(1,success=True)
        b.stop();b.terminal(1,success=False)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_ALREADY_TERMINAL'):b.terminal(1,success=False)

    def test_mismatched_evidence_and_ticks_cannot_finish_a_ticket(self):
        b=self.budget();case=self.matrix()['cases'][0];t=b.begin(case['caseId']);t.bind(case['programDigest']);t.record(7)
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_EVIDENCE_ACCOUNTING'):t.assert_evidence(dict(combinedRecords=0,combinedBytes=7))
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_TICK_ACCOUNTING'):b.end(t,operation_count=0,scheduler_ticks=True)
        t.assert_evidence(dict(combinedRecords=1,combinedBytes=7))


class IoGroupWorkerTests(GroupFixture,unittest.TestCase):
    def setUp(self):
        self.workspace=Path(tempfile.gettempdir())/self._testMethodName
        self.workspace.mkdir(mode=0o700)
        self.directory=self.workspace/'group';self.directory.mkdir(mode=0o700)

    def capture(self,**options):
        result=run_io_group(self.directory,**options)
        self.assertEqual(result,json.loads((self.directory/'result.json').read_bytes()))
        return result

    def full(self,pwm):
        options=self.options(pwm);result=self.capture(**options)
        self.assertEqual(result['status'],'captured',result['error'])
        self.assertTrue(result['allMatrixCasesCaptured']);self.assertIsNone(result['error'])
        for flag in ('requiredMatrixCoverageChecked','independentOutcomeChecked','configurationAttested',
                     'implementationIdentityAttested','actualAggregateStorageEnforced','qualificationPassed','physicalMeasurementChecked'):
            self.assertFalse(result[flag])
        matrix=json.loads((self.directory/'matrix.json').read_bytes())
        self.assertEqual([c['caseId'] for c in result['cases']],[c['caseId'] for c in matrix['cases']])
        self.assertEqual(len(result['cases']),30)
        scenarios={c['definition']['scenario'] for c in matrix['cases'] if c['kind']!='candidate'}
        self.assertEqual(scenarios,REQUIRED)
        total_records=1;total_bytes=65536;state_bytes=0;operations=ticks=0
        def read(ref):
            data=(self.directory/ref['path']).read_bytes()
            self.assertEqual(len(data),ref['bytes']);self.assertEqual(hashlib.sha256(data).hexdigest(),ref['sha256'])
            return json.loads(data)
        for ref in result['inputs']:
            read(ref);total_records+=1;total_bytes+=ref['bytes']
        for index,(case,row) in enumerate(zip(matrix['cases'],result['cases'])):
            manifest=read(row['manifest']);total_records+=1;total_bytes+=row['manifest']['bytes']
            self.assertEqual(manifest['caseId'],case['caseId'])
            state_bytes+=row['retainedStateBytes'];operations+=row['operationCount'];ticks+=row['schedulerTicks']
            if not manifest['executionPerformed']:
                expected=case['domainCase']['expected']
                self.assertEqual(manifest['staticOutcome'],expected['staticOutcome'])
                self.assertEqual(manifest['errorCode'],'PAT_NOT_APPLICABLE' if expected['staticOutcome']=='not_applicable' else expected['errorCode'])
                self.assertFalse((self.directory/('case-%02d'%index)/'state').exists());continue
            self.assertTrue(manifest['closed']);self.assertFalse(manifest['report']['unresolvedOperations'])
            for stream,records in [('records',manifest['records']),('configuration',manifest['configuration']['records'])]:
                for ref in records:
                    read(ref|{'path':'case-%02d/%s/%s'%(index,stream,ref['path'])})
                    total_records+=1;total_bytes+=ref['bytes']
        charged=result['accounting']['charged']
        self.assertEqual(charged,dict(records=total_records,producerBytes=total_bytes,
            derivedBytes=total_bytes+state_bytes,observedStateBytes=state_bytes,reservedChildOperations=44,
            actualChildOperations=operations,schedulerTicks=ticks,completedCases=30))
        self.assertLessEqual(total_records,4096);self.assertLessEqual(total_bytes,16*1024*1024)
        self.assertLessEqual(total_bytes+state_bytes,20*1024*1024)
        self.assertEqual(operations,28)
        self.assertEqual(result['identities']['storageProfile'],'hms.sqlite.compact/0.1')
        databases=list(self.directory.glob('case-*/state/*.db'));self.assertEqual(len(databases),52)
        for path in databases:
            with path.open('rb')as stream:header=stream.read(100)
            self.assertEqual(header[:16],b'SQLite format 3\0')
            self.assertEqual(int.from_bytes(header[16:18],'big'),1024)
        self.assertTrue(all(p.is_file() for p in self.directory.glob('case-*/manifest.json')))

    def test_complete_gpio_group(self):self.full(False)
    def test_complete_pwm_group(self):self.full(True)

    def test_record_limit_retains_partial_attempt_and_stops_later_cases(self):
        result=self.capture(**self.options(),limits=CEILINGS|{'maxRecords':250})
        self.assertEqual(result['status'],'failed');self.assertFalse(result['allMatrixCasesCaptured'])
        self.assertEqual(result['error']['code'],'PAT_IO_GROUP_EVIDENCE_LIMIT')
        self.assertTrue(result['accounting']['stopped']);self.assertFalse(result['qualificationPassed'])
        self.assertLess(len(result['cases']),30)
        self.assertEqual(result['accounting']['charged']['records'],250)
        files=[p for p in self.directory.rglob('*.json') if p.is_file()]
        self.assertLessEqual(len(files),250)
        self.assertTrue(any(self.directory.glob('case-*/state/authority.db')))
        with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_DIRECTORY_NOT_EMPTY'):
            run_io_group(self.directory,**self.options())

    def test_parameterized_matrix_refuses_before_runtime_or_output(self):
        options=self.options();options['candidate']=program()
        with patch('hms.pat_io_trials.IoRuntime',side_effect=AssertionError('unexpected runtime')):
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_COMBINED_LIMIT'):
                run_io_group(self.directory,**options)
        self.assertFalse(any(self.directory.iterdir()))

    def test_changed_implementation_refuses_before_group_output(self):
        with patch('hms.pat_io_group_worker._source_identity',return_value={'changed':True}):
            with self.assertRaisesRegex(PatError,'PAT_IO_GROUP_IMPLEMENTATION_CHANGED'):
                run_io_group(self.directory,**self.options())
        self.assertFalse(any(self.directory.iterdir()))
