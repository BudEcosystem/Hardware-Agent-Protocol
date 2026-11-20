"""Execute both installed primitives against exact independent timing cases."""
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy
from hms.pat_io_contracts import IoSequencePolicy
from hms.pat_io_outcome_history import inspect_trial_outcome
from hms.pat_io_timing_history import inspect_timing_challenge
from hms import pat_io_timing_worker as worker
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program


class _TimingCases(unittest.TestCase):
    pwm = False

    @classmethod
    def setUpClass(cls):
        cls.document=normalize_installation(installation());cls.bindings=bindings(cls.document)
        cls.descriptor=cls.bindings['pwm' if cls.pwm else 'gpio']['descriptor']
        cls.candidate=program(pwm=cls.pwm,literal=True)
        cls.matrix=IoCombinedMatrixPolicy(cls.document).generate(cls.candidate,cls.descriptor,cls.bindings)

    def setUp(self):
        self.workspace=Path(tempfile.gettempdir())/self._testMethodName
        self.workspace.mkdir(mode=0o700)

    def options(self):
        return dict(matrix=self.matrix,candidate=self.candidate,installation=self.document,
                    descriptor=self.descriptor,challenge_bindings=self.bindings)

    def case(self,name):
        return next(c for c in self.matrix['cases'] if c['kind']=='fixed_challenge' and c['definition']['scenario']==name)

    def run_named(self,name):
        case=self.case(name);artifact=next(p['artifact'] for p in self.matrix['programs'] if p['digest']==case['programDigest'])
        setup=dict(artifact=artifact,installation=self.document,original_descriptor=self.descriptor,
            static_contract=IoSequencePolicy(self.document).qualify(artifact,self.descriptor))
        authority=dict(profile='hms.pat.io-trusted-authority/0.1',principal='pat-io-trial-worker',
            deployment=self.document['topology']['deployment'],initialRegistryRevision=13,
            initialGrants=[dict(principal='pat-io-trial-worker',deployment=self.document['topology']['deployment'],target='*',verb='admin')],grantChanges=[])
        directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        (self.workspace/'requested-case.json').write_bytes(canonical(dict(testId=self.id(),case=case,expectedSetup=setup,expectedAuthority=authority)))
        manifest=worker.run_timing_challenge(directory,**self.options(),case_id=case['caseId'])
        (self.workspace/'trial-manifest.json').write_bytes(canonical(manifest))
        retained=dict(testId=self.id(),directory=str(directory),records=manifest['records'],configuration=manifest['configuration'],
            report=manifest['report'],closed=manifest['closed'],cleanupErrors=[],expectedCase=case,expectedAuthority=authority)
        target=self.workspace/'engine-0.json';target.write_text(json.dumps(retained,indent=2)+'\n')
        files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']}
        config_files={r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']}
        data=dict(references=manifest['records'],files=files,configuration=manifest['configuration'],configuration_files=config_files,
            expected_setup=setup,expected_authority=authority)
        try:
            checked=inspect_timing_challenge(**data,expected_case=case)
            outcome=checked['trial']['outcome'];self.assertTrue(checked['expectedResponseVerified'])
            self.assertFalse(checked['qualificationPassed']);self.assertFalse(checked['requiredMatrixCoverageChecked'])
            self.assertEqual(outcome['contractStatus'],case['definition']['expected']['completionContract'])
            self.assertTrue(outcome['settledAndQuiescent']);self.assertEqual(outcome['unresolvedOperationIds'],[])
            # The worker uses one admission phase followed by the declared list;
            # no automatic nominal-time finish() substitutes for the challenge.
            expected_ticks={'not_before_boundary':6,'latest_start_before':4,'latest_start_equal':3,
                'run_completion_equal':4,'wall_completion_equal':4,'lease_wait_before':6,
                'lease_wait_equal':3,'late_parent_reporting':4}
            self.assertEqual(manifest['report']['schedulerTicks'],expected_ticks[name])
            for key in ('activations','completedCycles','canceledActivations'):
                self.assertEqual(outcome[key],case['definition']['expected'][key])
            attack_count=0
            if name=='late_parent_reporting':
                self.assertEqual(outcome['parentCompletedAtMs'],1001000)
                self.assertTrue(outcome['zeroLagChildScheduleMatched']);self.assertFalse(outcome['parentCompletionBeforeDeadline'])
                self.assertFalse(outcome['nominalCompletionSatisfied']);self.assertEqual(outcome['completedCycles'],1)
                if not self.pwm:attack_count=self.attacks(data,case)
            retained.update(independentTimingInspection=checked,rehashedCaseRefusals=attack_count)
        except BaseException as error:
            retained['inspectionError']=type(error).__name__+':'+str(error);raise
        finally:target.write_text(json.dumps(retained,indent=2)+'\n')

    def attacks(self,data,case):
        # The same fixed program can produce different valid histories. A
        # coherent completed cycle cannot stand in for the run-expiry challenge.
        other=self.case('run_completion_equal');self.assertEqual(other['programDigest'],case['programDigest'])
        self.assertEqual(inspect_trial_outcome(**data)['outcome']['contractStatus'],'satisfied')
        with self.assertRaisesRegex(ValueError,'CONTROL_SCHEDULE'):inspect_timing_challenge(**data,expected_case=other)
        edits=[lambda c:c['definition']['control'].update(parentReportOffsetMs=999),
            lambda c:c['definition']['expected'].update(completedCycles=0),
            lambda c:c['definition']['expected'].update(completionContract='failed'),
            lambda c:c['definition']['expected']['checks'].pop(),
            lambda c:c['definition'].update(stepCount=2),lambda c:c.update(plannedChildOperations=0),
            lambda c:c.update(schedulerTickCeiling=65),lambda c:c.update(targetRole='pwm'),
            lambda c:c.update(programDigest='sha256:'+'0'*64),lambda c:c.update(extra=True),
            lambda c:c.update(kind='candidate')]
        for number,edit in enumerate(edits):
            with self.subTest(attack=number):
                bad=copy.deepcopy(case);bad.pop('caseId');edit(bad)
                bad['caseId']='sha256:'+hashlib.sha256(b'HMS-PAT-IO-COMBINED-CASE-v0.1\0'+canonical(bad)).hexdigest()
                with self.assertRaises(ValueError):inspect_timing_challenge(**data,expected_case=bad)
        def veto(*args,**kwargs):raise AssertionError('pure timing checker performed I/O or clock access')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_timing_challenge(**data,expected_case=case)['expectedResponseVerified'])
        return len(edits)

    def test_timing_not_before_boundary(self):self.run_named('not_before_boundary')
    def test_timing_latest_start_before(self):self.run_named('latest_start_before')
    def test_timing_latest_start_equal(self):self.run_named('latest_start_equal')
    def test_timing_run_completion_equal(self):self.run_named('run_completion_equal')
    def test_timing_wall_completion_equal(self):self.run_named('wall_completion_equal')
    def test_timing_lease_wait_before(self):self.run_named('lease_wait_before')
    def test_timing_lease_wait_equal(self):self.run_named('lease_wait_equal')
    def test_timing_late_parent_reporting(self):self.run_named('late_parent_reporting')


class GpioTimingChallengeTests(_TimingCases):
    def test_timing_invalid_or_unsupported_plan_refuses_before_runtime(self):
        directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        def veto(*args,**kwargs):raise AssertionError('invalid challenge constructed a runtime')
        with patch.object(worker,'ConfiguredIoTrialEngine',veto):
            with self.assertRaisesRegex(PatError,'PAT_IO_TIMING_UNSUPPORTED_CASE'):
                worker.run_timing_challenge(directory,**self.options(),case_id=self.case('start_run_equal')['caseId'])
            with self.assertRaisesRegex(PatError,'PAT_IO_TIMING_CASE'):
                worker.run_timing_challenge(directory,**self.options(),case_id='sha256:'+'0'*64)
            for field,value in [('plannedChildOperations',0),('schedulerTickCeiling',1)]:
                options=self.options();options['matrix']=copy.deepcopy(self.matrix)
                selected=next(c for c in options['matrix']['cases'] if c['caseId']==self.case('late_parent_reporting')['caseId'])
                selected[field]=value
                with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                    worker.run_timing_challenge(directory,**options,case_id=selected['caseId'])
        self.assertEqual(list(directory.iterdir()),[])
        (self.workspace/'refusal-audit.json').write_text(json.dumps(dict(testId=self.id(),refusals=4,runtimeConstructed=False))+'\n')


class PwmTimingChallengeTests(_TimingCases):
    pwm = True
