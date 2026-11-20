"""Actual paired captures of all ten fixed lifecycle cases on both primitives."""
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
from hms import pat_io_lifecycle_capture as worker
from hms.pat_io_lifecycle_history import inspect_lifecycle_transcript
from hms.pat_io_transcript import _read
from hms.pat_io_configuration_history import _configuration
from hms.pat_io_board_history import _Model, _tables, digest
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy
from hms.pat_io_contracts import IoSequencePolicy
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_conflict_history import rewrite


class IoLifecycleChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=normalize_installation(installation());cls.bindings=bindings(cls.document);cls.options={}
        for pwm in (False,True):
            d=cls.bindings['pwm' if pwm else 'gpio']['descriptor'];a=program(pwm=pwm,literal=True)
            cls.options[pwm]=dict(matrix=IoCombinedMatrixPolicy(cls.document).generate(a,d,cls.bindings),
                candidate=a,installation=cls.document,descriptor=d,challenge_bindings=cls.bindings)

    def setUp(self):
        self.workspace=Path(tempfile.gettempdir())/self._testMethodName;self.workspace.mkdir(mode=0o700)

    def case(self,options,name):
        return next(c for c in options['matrix']['cases'] if c['kind']=='fixed_challenge' and c['definition']['scenario']==name)

    def run_named(self,name,pwm=False):
        options=self.options[pwm];case=self.case(options,name)
        artifact=next(p['artifact'] for p in options['matrix']['programs'] if p['digest']==case['programDigest'])
        setup=dict(artifact=artifact,installation=self.document,original_descriptor=options['descriptor'],
            static_contract=IoSequencePolicy(self.document).qualify(artifact,options['descriptor']))
        owner=dict(principal='pat-io-trial-worker',deployment=self.document['topology']['deployment'])
        target=options['descriptor']['binding']['instanceId']
        phases={'permission_before_parent':(2,'submit:before'),'permission_before_dispatch':(4,'drive:adapters:before'),
            'permission_pending':(5,'drive:adapters:before'),'permission_after_completion':(6,'drive:adapters:before')}
        authority=owner|dict(profile='hms.pat.io-trusted-authority/0.1',initialRegistryRevision=13,
            initialGrants=[owner|dict(target='*',verb='admin')],grantChanges=[])
        if name in phases:
            phase,label=phases[name];authority['grantChanges']=[dict(phase=phase,label=label,grants=[owner|dict(target=target,verb='read')])]
        faults=[]
        if name in {'pending_reply_lost','completion_reply_lost','permission_after_completion'}:
            begin=name=='pending_reply_lost'
            faults=[dict(phase=4 if begin else 5,label='drive:adapters',point='board.begin.after_commit' if begin else
                'journal.record_execution.before_commit',exception='JournalError',code='injected:io_begin_reply_loss' if begin else
                'injected:io_lifecycle_completion_reply_loss',occurrences=1)]
        (self.workspace/'requested-case.json').write_bytes(canonical(dict(testId=self.id(),case=case,
            expectedSetup=setup,expectedAuthority=authority,expectedFaults=faults)))
        directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        manifest=worker.run_lifecycle_challenge(directory,**options,case_id=case['caseId'])
        (self.workspace/'trial-manifest.json').write_bytes(canonical(manifest))
        retained=dict(testId=self.id(),records=manifest['records'],configuration=manifest['configuration'],
            report=manifest['report'],directory=str(directory),closed=manifest['closed'],cleanupErrors=[],expectedCase=case)
        path=self.workspace/'engine-0.json';path.write_text(json.dumps(retained,indent=2)+'\n')
        data=dict(references=manifest['records'],files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']},
            configuration=manifest['configuration'],configuration_files={r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']},
            expected_setup=setup,expected_case=case,expected_authority=authority)
        try:
            checked=inspect_lifecycle_transcript(**data)
            self.assertTrue(checked['exactControlScheduleChecked']);self.assertTrue(checked['patCorrespondenceChecked'])
            for key in ('completeHistoryChecked','independentOutcomeChecked','expectedResponseVerified','qualificationPassed'):
                self.assertFalse(checked[key])
            trace=_read(data['references'],data['files'],setup)
            snapshots=_configuration(trace,data['references'],data['files'],data['configuration'],data['configuration_files'])
            states={(s['value']['phase'],s['value']['label']):_tables(trace,s['checkpoint']) for s in snapshots}
            final=states[len(trace['calls']),'test_final'];model=_Model(setup)
            plan,=[r['value'] for r in trace['records'] if r['kind']=='compiled_plan']
            no_parent=name=='permission_before_parent'
            self.assertEqual(len(final['operations']),0 if no_parent else 1)
            self.assertEqual(len(final['pr_procedures']),0 if no_parent else 1)
            self.assertFalse(final['claims']);self.assertFalse(final['io_owners'])
            self.assertEqual({r['resource']:json.loads(r['state']) for r in final['io_resources']},model.idle)
            effects={r['instance']:(r['activations'],r['completed'],r['canceled']) for r in final['io_effects']}
            expected=case['definition']['expected'];wanted=tuple(expected[k] for k in ('activations','completedCycles','canceledActivations'))
            self.assertEqual(effects.pop(target),wanted);self.assertTrue(all(v==(0,0,0) for v in effects.values()))
            self.assertEqual(manifest['report']['unresolvedOperations'],[])
            self.assertEqual(manifest['report']['schedulerTicks'],checked['schedulerTicks'])
            self.assertEqual(manifest['childOperationReservation'],len(artifact['steps']))
            self.assertTrue(manifest['closed']);self.assertFalse(manifest['qualificationPassed'])
            for frame in snapshots:
                self.assertEqual(frame['tables']['reg_bindings'],snapshots[0]['tables']['reg_bindings'])
                self.assertEqual(frame['tables']['reg_binding_history'],snapshots[0]['tables']['reg_binding_history'])
            if no_parent:
                for table in ('pr_steps','pr_keys','replay_keys','resource_floors','io_receipts','io_dispatch_links','io_fences'):
                    self.assertFalse(final[table])
                self.assertIsNone(manifest['report']['procedure'])
            else:
                op,=final['operations'];parent,=final['pr_procedures']
                self.assertEqual(json.loads(parent['request']),plan['request'])
                self.assertEqual(json.loads(op['intent']),plan['request']['procedure']['steps'][0]['request']['intent'])
                self.assertEqual({r['resource']:r['fence'] for r in final['resource_floors']},dict.fromkeys(model.details[model.target]['claims'],1))
                self.assertEqual(len(final['replay_keys']),1);self.assertEqual(final['replay_keys'][0]['caller_key'],'trial:child:0')
                self.assertEqual(len(final['pr_steps']),len(artifact['steps']))
                self.assertTrue(all(s['operation_id'] is None for s in final['pr_steps'] if s['ordinal']>0))
                parent_state=('completed' if name=='permission_after_completion' else 'failed' if name in
                    {'permission_before_dispatch','permission_pending','pending_reply_lost'} else 'canceled')
                self.assertEqual(parent['state'],parent_state)
                operation_state=('completed' if wanted[1] else 'failed' if name in {'permission_pending','pending_reply_lost'} else
                    'rejected_before_dispatch' if name=='permission_before_dispatch' else 'canceled')
                self.assertEqual(op['state'],operation_state)
                if wanted[0]:
                    receipt=json.loads(final['io_receipts'][0]['document'])
                    reason={'cancel_pending':'client_cancel','reopen_pending':'board_owner_reopened',
                        'pending_reply_lost':'reconciliation_stop','permission_pending':'authority_or_binding_lost'}.get(name)
                    self.assertEqual(receipt['result'],dict(activationCommitted=True,cycleCompleted=bool(wanted[1]),safeIdle=True,reason=reason))
                    self.assertEqual(receipt['state'],'completed' if wanted[1] else 'canceled')
                    self.assertEqual(len(final['io_receipt_versions']),2);self.assertEqual(receipt['sequence'],2)
                    self.assertEqual(receipt['ownerEpoch'],1);self.assertEqual(receipt['intent']['endpointSession'],trace['opened'][0]['session'])
                else:
                    for table in ('io_receipts','io_dispatch_links','io_fences'):self.assertFalse(final[table])
                    self.assertEqual(op['may_have_acted'],0)
                if len(trace['opened'])==2:
                    self.assertEqual(trace['opened'][1]['ownerEpoch'],2)
                    self.assertNotEqual(trace['opened'][1]['session'],trace['opened'][0]['session'])
                    after=next(v for (phase,label),v in states.items() if label=='after_reopen')
                    self.assertTrue(after['claims']);self.assertFalse(after['io_owners'])
                    self.assertEqual(after['operations'][0]['state'],'accepted' if name=='reopen_accepted' else 'outcome_unknown')
                    self.assertEqual(after['pr_procedures'][0]['state'],'interrupted')
            if faults:
                fault,=faults;phase=fault['phase'];begin=name=='pending_reply_lost'
                after=states[phase,'drive:adapters:after' if begin else 'drive:adapters:after_error']
                op,=after['operations'];self.assertEqual(op['state'],'outcome_unknown');self.assertTrue(after['claims'])
                self.assertEqual(json.loads(after['io_receipts'][0]['document'])['state'],'pending' if begin else 'completed')
                self.assertEqual(manifest['injectedFaults'],[fault|dict(operationId=op['id'])])
            else:self.assertEqual(manifest['injectedFaults'],[])
            attacks=self.attacks(data) if not pwm else 0
            retained.update(lifecycleInspection=checked,rehashedRefusals=attacks,
                targetedRuntimeAssertions=dict(operations=0 if no_parent else 1,activations=wanted[0],completedCycles=wanted[1],
                    canceledActivations=wanted[2],zeroUnresolved=True,noSuffix=True,oldRequestsPreserved=True))
        except BaseException as error:
            retained['inspectionError']=type(error).__name__+':'+str(error);raise
        finally:path.write_text(json.dumps(retained,indent=2)+'\n')

    def attacks(self,data):
        def coherent(doc):
            if doc['kind']=='compiled_plan':plan=doc['value']
            elif doc['kind']=='call_returned' and doc['value']['label']=='lower':plan=doc['value']['result']
            else:return
            plan['request']['procedure']['steps'][0]['request']['intent']['arguments']['durationMs']=11
        with self.assertRaises(ValueError):inspect_lifecycle_transcript(**rewrite(data,coherent))
        changed=copy.deepcopy(data);case=changed['expected_case'];case.pop('caseId');case['schedulerTickCeiling']=65
        case['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',case)
        with self.assertRaises(ValueError):inspect_lifecycle_transcript(**changed)
        changed=copy.deepcopy(data);changed['expected_authority']['initialRegistryRevision']=14
        with self.assertRaises(ValueError):inspect_lifecycle_transcript(**changed)
        def veto(*args,**kwargs):raise AssertionError('lifecycle reader performed I/O or sampled time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_lifecycle_transcript(**data)['exactControlScheduleChecked'])
        return 3

    def test_gpio_cancel_accepted(self):self.run_named('cancel_accepted')
    def test_pwm_cancel_accepted(self):self.run_named('cancel_accepted',True)
    def test_gpio_cancel_pending(self):self.run_named('cancel_pending')
    def test_pwm_cancel_pending(self):self.run_named('cancel_pending',True)
    def test_gpio_reopen_accepted(self):self.run_named('reopen_accepted')
    def test_pwm_reopen_accepted(self):self.run_named('reopen_accepted',True)
    def test_gpio_reopen_pending(self):self.run_named('reopen_pending')
    def test_pwm_reopen_pending(self):self.run_named('reopen_pending',True)
    def test_gpio_completion_reply_lost(self):self.run_named('completion_reply_lost')
    def test_pwm_completion_reply_lost(self):self.run_named('completion_reply_lost',True)
    def test_gpio_pending_reply_lost(self):self.run_named('pending_reply_lost')
    def test_pwm_pending_reply_lost(self):self.run_named('pending_reply_lost',True)
    def test_gpio_permission_before_parent(self):self.run_named('permission_before_parent')
    def test_pwm_permission_before_parent(self):self.run_named('permission_before_parent',True)
    def test_gpio_permission_before_dispatch(self):self.run_named('permission_before_dispatch')
    def test_pwm_permission_before_dispatch(self):self.run_named('permission_before_dispatch',True)
    def test_gpio_permission_pending(self):self.run_named('permission_pending')
    def test_pwm_permission_pending(self):self.run_named('permission_pending',True)
    def test_gpio_permission_after_completion(self):self.run_named('permission_after_completion')
    def test_pwm_permission_after_completion(self):self.run_named('permission_after_completion',True)

    def test_invalid_matrix_or_unsupported_case_refuses_before_runtime(self):
        options=self.options[False];directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        def veto(*args,**kwargs):raise AssertionError('invalid plan constructed runtime')
        with patch.object(worker,'ConfiguredIoTrialEngine',veto):
            other=self.case(options,'binding_pending')
            with self.assertRaisesRegex(PatError,'PAT_IO_LIFECYCLE_UNSUPPORTED_CASE'):
                worker.run_lifecycle_challenge(directory,**options,case_id=other['caseId'])
            changed=copy.deepcopy(options);case=self.case(changed,'cancel_pending');case['plannedChildOperations']=1
            with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                worker.run_lifecycle_challenge(directory,**changed,case_id=case['caseId'])
        self.assertFalse(list(directory.iterdir()))
        (self.workspace/'refusal-audit.json').write_text(json.dumps(dict(testId=self.id(),refusals=2,runtimeConstructed=False))+'\n')
