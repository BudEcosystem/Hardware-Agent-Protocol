"""Real isolated binding/all-grant withdrawal captures and rehashed reader attacks."""
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
from hms import pat_io_authority_capture as worker
from hms.pat_io_authority_history import inspect_authority_transcript
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


class IoAuthorityChallengeTests(unittest.TestCase):
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
        options=self.options[pwm];case=self.case(options,name);before=name=='binding_before_dispatch'
        withdrawal=name=='full_authority_withdrawal';pending=name=='binding_pending'
        artifact=next(p['artifact'] for p in options['matrix']['programs'] if p['digest']==case['programDigest'])
        setup=dict(artifact=artifact,installation=self.document,original_descriptor=options['descriptor'],
            static_contract=IoSequencePolicy(self.document).qualify(artifact,options['descriptor']))
        # Retained separately from the untrusted capture for the later semantic fold.
        trusted=dict(principal='pat-io-trial-worker',deployment=self.document['topology']['deployment'],
            initialRegistryRevision=13,initialGrants=[dict(principal='pat-io-trial-worker',
                deployment=self.document['topology']['deployment'],target='*',verb='admin')],
            action=case['definition']['control']['action'],phase=4 if before else 5,
            target=setup['original_descriptor']['binding']['instanceId'])
        (self.workspace/'requested-case.json').write_bytes(canonical(dict(testId=self.id(),case=case,
            expectedSetup=setup,expectedAuthorityChange=trusted)))
        directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        manifest=worker.run_authority_challenge(directory,**options,case_id=case['caseId'])
        (self.workspace/'trial-manifest.json').write_bytes(canonical(manifest))
        retained=dict(testId=self.id(),records=manifest['records'],configuration=manifest['configuration'],
            report=manifest['report'],directory=str(directory),closed=manifest['closed'],cleanupErrors=[],expectedCase=case)
        path=self.workspace/'engine-0.json';path.write_text(json.dumps(retained,indent=2)+'\n')
        data=dict(references=manifest['records'],files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']},
            configuration=manifest['configuration'],configuration_files={r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']},
            expected_setup=setup,expected_case=case)
        try:
            checked=inspect_authority_transcript(**data)
            self.assertTrue(checked['exactAuthorityScheduleChecked']);self.assertTrue(checked['initialPatCorrespondenceChecked'])
            for key in ('completeHistoryChecked','independentOutcomeChecked','expectedResponseVerified','qualificationPassed'):
                self.assertFalse(checked[key])
            for flags in ({},{'conflict_profile':True},{'clock_profile':True},{'resource_profile':True},
                          {'authority_profile':True,'clock_profile':True}):
                with self.assertRaises(ValueError):_read(data['references'],data['files'],setup,**flags)
            trace=_read(data['references'],data['files'],setup,authority_profile=True)
            snapshots=_configuration(trace,data['references'],data['files'],data['configuration'],data['configuration_files'])
            states={(s['value']['phase'],s['value']['label']):(_tables(trace,s['checkpoint']),s['tables']) for s in snapshots}
            final,config=states[len(trace['calls']),'test_final'];op,=final['operations'];parent,=final['pr_procedures']
            self.assertEqual(len(final['replay_keys']),1);self.assertEqual(len(final['pr_keys']),3)
            self.assertEqual(len(final['pr_steps']),2);self.assertIsNone(final['pr_steps'][1]['operation_id'])
            self.assertEqual(final['replay_keys'][0]['caller_key'],'trial:child:0')
            self.assertFalse(final['claims']);self.assertFalse(final['io_owners'])
            self.assertEqual({r['fence'] for r in final['resource_floors']},{1})
            self.assertEqual({r['resource'] for r in final['resource_floors']},set(_Model(setup).details[_Model(setup).target]['claims']))
            self.assertEqual({r['resource']:json.loads(r['state']) for r in final['io_resources']},_Model(setup).idle)
            effects={r['instance']:(r['activations'],r['completed'],r['canceled']) for r in final['io_effects']}
            self.assertEqual(effects.pop(trusted['target']),(0,0,0) if before else (1,0,1))
            self.assertTrue(all(v==(0,0,0) for v in effects.values()))
            self.assertEqual(parent['state'],'failed' if before else 'canceled')
            self.assertEqual(manifest['report']['statusAccess'],'privileged_trial_observation')
            self.assertEqual(manifest['report']['unresolvedOperations'],[])
            self.assertEqual(manifest['report']['schedulerTicks'],3)
            self.assertEqual(manifest['childOperationReservation'],3 if pending else 2)
            self.assertEqual(config['reg_grants'],[] if withdrawal else trusted['initialGrants'])
            target_binding=next(r for r in config['reg_bindings'] if r['instance']==trusted['target'])
            self.assertEqual(target_binding['active'],1 if withdrawal else 0)
            if not withdrawal:self.assertFalse([r for r in config['reg_presence'] if r['instance']==trusted['target']])
            initial_bindings=snapshots[0]['tables']['reg_bindings']
            for snapshot in snapshots:
                current=snapshot['tables'];phase=snapshot['value']['phase'];label=snapshot['value']['label']
                changed=phase>trusted['phase'] or phase==trusted['phase'] and label!='change:'+('authority' if withdrawal else 'binding')+':before'
                wanted_bindings=copy.deepcopy(initial_bindings)
                if changed and not withdrawal:
                    next(r for r in wanted_bindings if r['instance']==trusted['target'])['active']=0
                self.assertEqual(current['reg_bindings'],wanted_bindings)
                self.assertEqual(current['reg_binding_history'],snapshots[0]['tables']['reg_binding_history'])
                self.assertEqual(current['reg_grants'],[] if changed and withdrawal else trusted['initialGrants'])
            if before:
                self.assertEqual(op['state'],'rejected_before_dispatch');self.assertEqual(op['may_have_acted'],0)
                self.assertFalse(final['io_dispatch_links']);self.assertFalse(final['io_receipts']);self.assertFalse(final['io_fences'])
                event=next(r for r in final['events'] if r['kind']=='rejected_before_dispatch')
                self.assertIn('BINDING_INACTIVE',event['payload'].decode())
            else:
                self.assertEqual(op['state'],'canceled');self.assertEqual(op['may_have_acted'],1)
                receipt=json.loads(final['io_receipts'][0]['document'])
                self.assertEqual(receipt['state'],'canceled');self.assertEqual(receipt['result']['reason'],'board_owner_reopened')
                self.assertEqual(receipt['ownerEpoch'],1);self.assertEqual(receipt['intent']['endpointSession'],trace['opened'][0]['session'])
                self.assertEqual(len(final['io_receipt_versions']),2)
                self.assertEqual(trace['opened'][1]['ownerEpoch'],2);self.assertIsNone(trace['opened'][1]['workerEnvironment'])
                self.assertEqual(trace['opened'][1]['bindingResolution']['code'],'PAT_BINDING_NOT_APPLICABLE')
                reopen_phase=9 if withdrawal else 5
                after,_=states[reopen_phase,'after_reopen'];self.assertEqual(after['operations'][0]['state'],'outcome_unknown')
                self.assertTrue(after['claims']);self.assertFalse(after['io_owners'])
                self.assertEqual(after['pr_procedures'][0]['request'],parent['request'])
                self.assertEqual(json.loads(op['intent'])['endpointSession'],trace['opened'][0]['session'])
                self.assertEqual(len(final['namespaces']),1);self.assertEqual(final['series'][0]['next_epoch'],2)
            attacks=self.attacks(data) if not pwm and not before else 0
            retained.update(authorityInspection=checked,rehashedRefusals=attacks,
                targetedRuntimeAssertions=dict(operations=1,activations=0 if before else 1,completedCycles=0,
                    canceledActivations=0 if before else 1,zeroUnresolved=True,noSuffix=True,
                    bindingDocumentUnchanged=True,publicDenials=8 if withdrawal else 0))
        except BaseException as error:
            retained['inspectionError']=type(error).__name__+':'+str(error);raise
        finally:path.write_text(json.dumps(retained,indent=2)+'\n')

    def attacks(self,data):
        edits=[('runtime_opened',lambda v:v.update(bindingResolution=dict(status='resolved',exception=None,code=None)) if not v['create'] else None),
            ('trial_observation',lambda v:v.update(statusAccess='public_status')),
            ('call_failed',lambda v:v.update(code='PAT_IO_TRIAL_OPERATION_LIMIT')),
            ('authority_input',lambda v:v['case'].update(plannedChildOperations=1)),
            ('resolver_configuration',lambda v:v['registrations'].clear())]
        if data['expected_case']['definition']['scenario']=='binding_pending':
            edits.append(('authority_input',lambda v:v['probes']['inactive_binding'].update(operationKey='trial:child:1')))
        for kind,edit in edits:
            def change(doc):
                if doc['kind']==kind:edit(doc['value'])
            with self.assertRaises(ValueError):inspect_authority_transcript(**rewrite(data,change))
        # Coherently forge both lower reply and plan: request correspondence must reject.
        def coherent(doc):
            if doc['kind']=='compiled_plan':plan=doc['value']
            elif doc['kind']=='call_returned' and doc['value']['label']=='lower':plan=doc['value']['result']
            else:return
            plan['request']['procedure']['steps'][0]['request']['intent']['arguments']['durationMs']=11
        with self.assertRaises(ValueError):inspect_authority_transcript(**rewrite(data,coherent))
        changed=copy.deepcopy(data);case=changed['expected_case'];case.pop('caseId');case['plannedChildOperations']=1
        case['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',case)
        with self.assertRaises(ValueError):inspect_authority_transcript(**changed)
        def veto(*args,**kwargs):raise AssertionError('authority reader performed I/O or sampled time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_authority_transcript(**data)['exactAuthorityScheduleChecked'])
        return len(edits)+2

    def test_gpio_binding_before_dispatch(self):self.run_named('binding_before_dispatch')
    def test_pwm_binding_before_dispatch(self):self.run_named('binding_before_dispatch',True)
    def test_gpio_binding_pending_recovery(self):self.run_named('binding_pending')
    def test_pwm_binding_pending_recovery(self):self.run_named('binding_pending',True)
    def test_gpio_full_authority_withdrawal(self):self.run_named('full_authority_withdrawal')
    def test_pwm_full_authority_withdrawal(self):self.run_named('full_authority_withdrawal',True)

    def test_undeclared_probe_or_unsupported_case_refuses_before_runtime(self):
        options=self.options[False];directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        def veto(*args,**kwargs):raise AssertionError('invalid plan constructed runtime')
        with patch.object(worker,'AuthorityIoTrialEngine',veto):
            other=self.case(options,'cancel_pending')
            with self.assertRaisesRegex(PatError,'PAT_IO_AUTHORITY_UNSUPPORTED_CASE'):
                worker.run_authority_challenge(directory,**options,case_id=other['caseId'])
            for edit in (lambda c:c.update(plannedChildOperations=2),lambda c:c['definition'].update(probes=[])):
                changed=copy.deepcopy(options);case=self.case(changed,'binding_pending');edit(case)
                with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                    worker.run_authority_challenge(directory,**changed,case_id=case['caseId'])
        self.assertFalse(list(directory.iterdir()))
        (self.workspace/'refusal-audit.json').write_text(json.dumps(dict(testId=self.id(),refusals=3,runtimeConstructed=False))+'\n')
