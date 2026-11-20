"""Actual shared-board captures and rehashed attacks on request/schedule evidence."""
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
from hms import pat_io_resource_capture as worker
from hms.pat_io_resource_history import inspect_resource_transcript
from hms.pat_io_transcript import _read
from hms.pat_io_board_history import _Model, _tables, digest
from hms.pat_io_combined_matrix import IoCombinedMatrixPolicy
from hms.pat_io_contracts import IoSequencePolicy
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_conflict_history import rewrite


class IoResourceChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=normalize_installation(installation());cls.bindings=bindings(cls.document);cls.options={}
        for pwm in (False,True):
            descriptor=cls.bindings['pwm' if pwm else 'gpio']['descriptor'];candidate=program(pwm=pwm,literal=True)
            matrix=IoCombinedMatrixPolicy(cls.document).generate(candidate,descriptor,cls.bindings)
            cls.options[pwm]=dict(matrix=matrix,candidate=candidate,installation=cls.document,
                descriptor=descriptor,challenge_bindings=cls.bindings)

    def setUp(self):
        self.workspace=Path(tempfile.gettempdir())/self._testMethodName;self.workspace.mkdir(mode=0o700)

    def case(self,options):
        return next(c for c in options['matrix']['cases'] if c['kind']=='resource_challenge')

    def run_case(self,pwm):
        options=self.options[pwm];case=self.case(options)
        programs={p['digest']:p['artifact'] for p in options['matrix']['programs']};actors={}
        for role,info in case['actors'].items():
            a=programs[info['programDigest']];d=self.bindings[role]['descriptor']
            actors[role]=dict(artifact=a,original_descriptor=d,static_contract=IoSequencePolicy(self.document).qualify(a,d))
        setup=actors['gpio']|{'installation':self.document}
        (self.workspace/'requested-case.json').write_bytes(canonical(dict(testId=self.id(),case=case,expectedSetup=setup,expectedActors=actors)))
        directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        manifest=worker.run_resource_challenge(directory,**options,case_id=case['caseId'])
        (self.workspace/'trial-manifest.json').write_bytes(canonical(manifest))
        retained=dict(testId=self.id(),records=manifest['records'],configuration=manifest['configuration'],report=manifest['report'],
            directory=str(directory),closed=manifest['closed'],cleanupErrors=[],expectedCase=case)
        path=self.workspace/'engine-0.json';path.write_text(json.dumps(retained,indent=2)+'\n')
        data=dict(references=manifest['records'],files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']},
            configuration=manifest['configuration'],configuration_files={r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']},
            expected_setup=setup,expected_case=case,expected_actors=actors)
        try:
            checked=inspect_resource_transcript(**data)
            self.assertTrue(checked['exactResourceScheduleChecked']);self.assertTrue(checked['predeclaredProbeChecked'])
            for key in ('completeHistoryChecked','independentOutcomeChecked','expectedResponseVerified','qualificationPassed'):
                self.assertFalse(checked[key])
            for flags in ({},{'conflict_profile':True},{'clock_profile':True},{'clock_profile':True,'resource_profile':True}):
                with self.assertRaises(ValueError):_read(data['references'],data['files'],setup,**flags)
            trace=_read(data['references'],data['files'],setup,resource_profile=True)
            states={(c['value']['phase'],c['value']['label']):_tables(trace,c) for c in trace['checkpoints']}
            def state(phase,label):return states[phase,label]
            final=state(21,'test_final');ids=manifest['operationIds'];self.assertEqual(set(ids),set(actors))
            self.assertEqual(len(set(ids.values())),4);self.assertEqual(len(final['operations']),4)
            self.assertEqual({r['state'] for r in final['operations']},{'completed'})
            self.assertEqual(len(final['replay_keys']),4);self.assertEqual(len(final['io_dispatch_links']),4)
            self.assertEqual(len(final['io_receipts']),4);self.assertEqual(len(final['io_receipt_versions']),8)
            self.assertFalse(final['claims']);self.assertFalse(final['io_owners'])
            self.assertFalse(final['pr_procedures']);self.assertFalse(final['pr_steps']);self.assertFalse(final['pr_keys']);self.assertFalse(final['pr_events'])
            effects={r['instance']:(r['activations'],r['completed'],r['canceled']) for r in final['io_effects']}
            for actor in case['actors'].values():self.assertEqual(effects.pop(actor['instanceId']),(1,1,0))
            self.assertTrue(all(v==(0,0,0) for v in effects.values()))
            self.assertEqual(manifest['report']['unresolvedOperations'],[]);self.assertIsNone(manifest['report']['procedure'])
            self.assertEqual(manifest['report']['schedulerTicks'],7);self.assertEqual(manifest['childOperationReservation'],5)
            model=_Model(setup)
            self.assertEqual({r['resource']:json.loads(r['state']) for r in final['io_resources']},model.idle)
            wanted_fences={a:1 for a in case['actors']['pwm']['claims']+case['actors']['independent']['claims']}
            wanted_fences.update({a:3 for a in case['actors']['gpio']['claims']})
            self.assertEqual({r['resource']:r['fence'] for r in final['resource_floors']},wanted_fences)
            self.assertEqual({r['resource']:r['fence'] for r in final['io_fences']},wanted_fences)
            both=state(7,'drive:adapters:after')
            self.assertEqual({r['operation_id'] for r in both['claims']},{ids['gpio'],ids['independent']})
            self.assertEqual({r['operation'] for r in both['io_owners']},{ids['gpio'],ids['independent']})
            done=state(8,'drive:adapters:after');self.assertFalse(done['claims'])
            self.assertEqual({r['state'] for r in done['io_receipts']},{'completed'})
            alias=state(12,'read:gpio:after')
            self.assertEqual({r['operation_id'] for r in alias['claims']},{ids['alias']})
            self.assertEqual({r['operation'] for r in alias['io_owners']},{ids['alias']})
            old=next(c for c in trace['calls'] if c['label']=='read:gpio')['outcome']['result']
            self.assertEqual(old['operationId'],ids['gpio']);self.assertEqual(old['executionState'],'completed')
            self.assertTrue(old['result']['output']['result']['safeIdle'])
            live={r['resource']:json.loads(r['state']) for r in alias['io_resources']}
            for atom,idle in old['result']['output']['safeIdleState'].items():self.assertNotEqual(live[atom],idle)
            before_probe=state(16,'probe:gpio_while_pwm:before')
            self.assertEqual(len(before_probe['operations']),4)
            self.assertEqual({r['operation_id'] for r in before_probe['claims']},{ids['pwm']})
            self.assertEqual({r['caller_key'] for r in final['replay_keys']},{'trial:actor:'+r for r in actors})
            for c in trace['calls']:
                if c['label'].startswith('invoke:') and c['returned']:
                    role=c['label'].split(':')[1];self.assertEqual(c['outcome']['result']['id'],ids[role])
            attacks=self.attacks(data) if not pwm else 0
            retained.update(resourceInspection=checked,rehashedRefusals=attacks,
                targetedRuntimeAssertions=dict(operations=4,activations=4,completedCycles=4,canceledActivations=0,
                    zeroUnresolved=True,independentPadProgress=True,historicalIdleWhileAliasActive=True,
                    probeReachedResourceBusyAfterFourAdmissions=True,sharedFenceHistory=True))
        except BaseException as error:
            retained['inspectionError']=type(error).__name__+':'+str(error);raise
        finally:path.write_text(json.dumps(retained,indent=2)+'\n')

    def attacks(self,data):
        edits=[('resource_input',lambda v:v['case'].update(plannedChildOperations=4)),
            ('compiled_plan',lambda v:v['probes']['gpio_while_pwm'].update(operationKey='trial:actor:gpio')),
            ('compiled_plan',lambda v:v['actors']['alias']['request']['procedure']['steps'][0]['request']['intent']['arguments'].update(level=0)),
            ('resolver_configuration',lambda v:v['registrations'].pop()),
            ('call_failed',lambda v:v.update(code='PAT_IO_TRIAL_OPERATION_LIMIT')),
            ('clock_advanced',lambda v:v.update(to=v['to']+1))]
        for kind,edit in edits:
            def change(doc):
                if doc['kind']==kind:edit(doc['value'])
            with self.assertRaises(ValueError):inspect_resource_transcript(**rewrite(data,change))
        for edit in (lambda c:c.update(plannedChildOperations=4),lambda c:c['definition'].update(probes=[]),
                     lambda c:c['actors']['alias'].update(adapterId=c['actors']['gpio']['adapterId'])):
            changed=copy.deepcopy(data);c=changed['expected_case'];c.pop('caseId');edit(c)
            c['caseId']=digest(b'HMS-PAT-IO-COMBINED-CASE-v0.1',c)
            with self.assertRaises(ValueError):inspect_resource_transcript(**changed)
        def veto(*args,**kwargs):raise AssertionError('resource reader performed I/O or sampled time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_resource_transcript(**data)['exactResourceScheduleChecked'])
        return 9

    def test_shared_board_for_gpio_candidate(self):self.run_case(False)
    def test_shared_board_for_pwm_candidate(self):self.run_case(True)

    def test_undeclared_probe_or_unsupported_case_refuses_before_runtime(self):
        options=self.options[False];directory=self.workspace/'trial-0';directory.mkdir(mode=0o700)
        def veto(*args,**kwargs):raise AssertionError('invalid resource plan constructed runtime')
        with patch.object(worker,'ResourceIoTrialEngine',veto):
            other=next(c for c in options['matrix']['cases'] if c['kind']=='fixed_challenge')
            with self.assertRaisesRegex(PatError,'PAT_IO_RESOURCE_UNSUPPORTED_CASE'):
                worker.run_resource_challenge(directory,**options,case_id=other['caseId'])
            for edit in (lambda c:c.update(plannedChildOperations=4),lambda c:c['definition'].update(probes=[])):
                changed=copy.deepcopy(options);case=self.case(changed);edit(case)
                with self.assertRaisesRegex(PatError,'PAT_IO_MATRIX_PLAN_MISMATCH'):
                    worker.run_resource_challenge(directory,**changed,case_id=case['caseId'])
        self.assertFalse(list(directory.iterdir()))
        (self.workspace/'refusal-audit.json').write_text(json.dumps(dict(testId=self.id(),refusals=3,runtimeConstructed=False))+'\n')
