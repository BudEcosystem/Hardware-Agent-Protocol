"""Actual clock-fault captures plus structural reader attacks; no qualification."""
import builtins
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms import pat_io_clock_capture as worker
from hms.pat_io_clock_history import inspect_clock_transcript
from hms.pat_io_transcript import _read
from hms.pat_io_board_history import _tables, digest
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy
from hms.pat_io_contracts import IoSequencePolicy
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_conflict_history import rewrite


class IoClockChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=normalize_installation(installation());cls.bindings=bindings(cls.document)
        cls.options={}
        for pwm in (False,True):
            descriptor=cls.bindings['pwm' if pwm else 'gpio']['descriptor'];candidate=program(pwm=pwm,literal=True)
            matrix=IoCombinedMatrixPolicy(cls.document).generate(candidate,descriptor,cls.bindings)
            cls.options[pwm]=dict(matrix=matrix,candidate=candidate,installation=cls.document,descriptor=descriptor,challenge_bindings=cls.bindings)

    def setUp(self):
        self.workspace=Path(tempfile.gettempdir())/self._testMethodName;self.workspace.mkdir(mode=0o700)

    def case(self,options,name):
        return next(c for c in options['matrix']['cases'] if c['kind']=='fixed_challenge' and c['definition']['scenario']==name)

    def run_named(self,name,pwm=False):
        options=self.options[pwm];case=self.case(options,name)
        artifact=next(p['artifact'] for p in options['matrix']['programs'] if p['digest']==case['programDigest'])
        setup=dict(artifact=artifact,installation=self.document,original_descriptor=options['descriptor'],
            static_contract=IoSequencePolicy(self.document).qualify(artifact,options['descriptor']))
        authority=dict(profile='hms.pat.io-trusted-authority/0.1',principal='pat-io-trial-worker',
            deployment=self.document['topology']['deployment'],initialRegistryRevision=13,
            initialGrants=[dict(principal='pat-io-trial-worker',deployment=self.document['topology']['deployment'],target='*',verb='admin')],grantChanges=[])
        (self.workspace/'requested-case.json').write_bytes(canonical(dict(testId=self.id(),case=case,expectedSetup=setup,expectedAuthority=authority)))
        directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        manifest=worker.run_clock_challenge(directory,**options,case_id=case['caseId'])
        (self.workspace/'trial-manifest.json').write_bytes(canonical(manifest))
        retained=dict(testId=self.id(),directory=str(directory),records=manifest['records'],configuration=manifest['configuration'],
            report=manifest['report'],closed=manifest['closed'],cleanupErrors=[],expectedCase=case,expectedAuthority=authority)
        path=self.workspace/'engine-0.json';path.write_text(json.dumps(retained,indent=2)+'\n')
        data=dict(references=manifest['records'],files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']},
            configuration=manifest['configuration'],configuration_files={r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']},expected_setup=setup,expected_case=case)
        try:
            checked=inspect_clock_transcript(**data)
            self.assertTrue(checked['exactClockControlScheduleChecked']);self.assertFalse(checked['independentOutcomeChecked'])
            self.assertFalse(checked['expectedResponseVerified']);self.assertFalse(checked['qualificationPassed'])
            for conflict in (False,True):
                with self.assertRaises(ValueError):_read(data['references'],data['files'],setup,conflict_profile=conflict)
            trace=_read(data['references'],data['files'],setup,clock_profile=True)
            final=_tables(trace,trace['checkpoints'][-1]);operation,=final['operations']
            receipt=json.loads(final['io_receipts'][0]['document']);link=json.loads(final['io_dispatch_links'][0]['document'])
            self.assertEqual(len(final['io_dispatch_links']),1);self.assertEqual(len(final['io_receipts']),1)
            self.assertFalse(final['claims']);self.assertFalse(final['io_owners'])
            target='sim:pwm5' if pwm else 'sim:gpio5';effects={r['instance']:(r['activations'],r['completed'],r['canceled']) for r in final['io_effects']}
            self.assertEqual(effects.pop(target),(0,0,0) if name=='start_run_equal' else (1,0,1))
            self.assertTrue(all(v==(0,0,0) for v in effects.values()))
            self.assertEqual(len(final['operations']),1);self.assertEqual(manifest['report']['unresolvedOperations'],[])
            self.assertEqual({r['fence'] for r in final['resource_floors']},{1})
            if name=='start_run_equal':
                self.assertEqual(operation['state'],'rejected_before_start');self.assertEqual(operation['may_have_acted'],0)
                self.assertEqual(receipt['state'],'rejected_before_start');self.assertEqual(receipt['result']['reason'],'duration_budget_excluded')
                self.assertEqual(link['budgetOriginMonoMs'],1000000);self.assertFalse(final['io_fences'])
                self.assertEqual(manifest['report']['procedure']['executionState'],'failed')
                self.assertEqual(manifest['report']['schedulerTicks'],3)
            else:
                self.assertEqual(operation['state'],'canceled');self.assertEqual(receipt['state'],'canceled')
                self.assertEqual(receipt['result']['reason'],'board_owner_reopened');self.assertEqual(receipt['ownerEpoch'],1)
                self.assertEqual(receipt['clockEpoch'],trace['opened'][0]['authorityId']+':1')
                self.assertEqual(trace['opened'][1]['ownerEpoch'],2);self.assertNotEqual(trace['opened'][0]['session'],trace['opened'][1]['session'])
                self.assertEqual(receipt['intent']['endpointSession'],trace['opened'][0]['session'])
                self.assertEqual(len(final['io_receipt_versions']),2)
                self.assertEqual(manifest['report']['procedure']['executionState'],'canceled')
                self.assertEqual(manifest['report']['schedulerTicks'],5 if name=='wall_clock_regression' else 6)
                failures=[c for c in trace['checkpoints'] if c['value']['label']=='drive:adapters:after_error']
                self.assertEqual(len(failures),1 if name=='wall_clock_regression' else 2)
                for cp in failures:
                    table=_tables(trace,cp);old,=table['operations'];old_receipt=json.loads(table['io_receipts'][0]['document'])
                    self.assertEqual(old['state'],'running');self.assertTrue(table['claims']);self.assertTrue(table['io_owners'])
                    self.assertEqual(old_receipt['state'],'pending');self.assertEqual(old_receipt['sequence'],1)
                    self.assertEqual(dict((r['key'],r['value']) for r in table['meta'])['last_clock'],'1000000')
                before_reopen=next(c for c in trace['checkpoints'] if c['value']['label']=='before_reopen')
                self.assertEqual(_tables(trace,before_reopen)['pr_procedures'][0]['request'],final['pr_procedures'][0]['request'])
            attacks=self.attacks(data) if name=='clock_epoch_mismatch' and not pwm else 0
            retained.update(independentClockInspection=checked,rehashedControlRefusals=attacks)
        except BaseException as error:
            retained['inspectionError']=type(error).__name__+':'+str(error);raise
        finally:path.write_text(json.dumps(retained,indent=2)+'\n')

    def attacks(self,data):
        edits=[lambda v:v.update(phase=99),lambda v:v.update(point='unknown'),lambda v:v.update(ownerEpoch=2),
            lambda v:v['before'].update(wallMs=0),lambda v:v['after'].update(monotonicMs=1000001),lambda v:v.update(extra=True)]
        for edit in edits:
            def change(doc):
                if doc['kind']=='clock_control' and doc['value']['point']=='pending_mapping_invalidation':edit(doc['value'])
            with self.assertRaises(ValueError):inspect_clock_transcript(**rewrite(data,change))
        case_edits=[lambda c:c['definition']['control'].update(action='anything'),lambda c:c.update(plannedChildOperations=1),
            lambda c:c.update(targetRole='pwm'),lambda c:c['definition']['expected'].update(activations=0)]
        for edit in case_edits:
            altered=copy.deepcopy(data);case=altered['expected_case'];case.pop('caseId');edit(case)
            case['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',case)
            with self.assertRaises(ValueError):inspect_clock_transcript(**altered)
        def veto(*args,**kwargs):raise AssertionError('clock reader performed I/O or sampled time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_clock_transcript(**data)['exactClockControlScheduleChecked'])
        return len(edits)+len(case_edits)

    def test_gpio_guard_delay_excludes_equal_due(self):self.run_named('start_run_equal')
    def test_pwm_guard_delay_excludes_equal_due(self):self.run_named('start_run_equal',True)
    def test_gpio_wall_regression_reopens_retained_state(self):self.run_named('wall_clock_regression')
    def test_pwm_wall_regression_reopens_retained_state(self):self.run_named('wall_clock_regression',True)
    def test_gpio_invalid_mapping_stays_invalid_until_reopen(self):self.run_named('clock_epoch_mismatch')
    def test_pwm_invalid_mapping_stays_invalid_until_reopen(self):self.run_named('clock_epoch_mismatch',True)

    def test_unsupported_clock_plan_refuses_before_runtime(self):
        options=self.options[False];directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        def veto(*args,**kwargs):raise AssertionError('invalid clock plan constructed runtime')
        with patch.object(worker,'ClockIoTrialEngine',veto):
            with self.assertRaisesRegex(PatError,'PAT_IO_CLOCK_UNSUPPORTED_CASE'):
                worker.run_clock_challenge(directory,**options,case_id=self.case(options,'late_parent_reporting')['caseId'])
            changed=copy.deepcopy(options);case=self.case(changed,'start_run_equal');case['definition']['control']['guardDelayMs']=100
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                worker.run_clock_challenge(directory,**changed,case_id=case['caseId'])
        self.assertFalse(list(directory.iterdir()))
        (self.workspace/'refusal-audit.json').write_text(json.dumps(dict(testId=self.id(),refusals=2,runtimeConstructed=False))+'\n')
