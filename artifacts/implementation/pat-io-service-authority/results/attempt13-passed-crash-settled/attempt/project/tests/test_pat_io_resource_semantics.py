"""Retained real resource captures, coherent attacks and pure-reader boundaries."""
import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_io_resource_semantics import inspect_resource_challenge, _SharedModel, _decisions, _configuration_history
from hms.pat_io_resource_history import inspect_resource_transcript
from hms.pat_io_configuration_history import _configuration
from hms.pat_io_correspondence import _Program
from hms.pat_io_transcript import _read
from test_pat_io_conflict_history import rewrite
from test_pat_io_clock_semantics import rows, receipt_attack

FIXTURES=Path(__file__).parent/'data/io-resource'


def load(primitive='gpio'):
    directory=FIXTURES/('test_shared_board_for_'+primitive+'_candidate')
    manifest=json.loads((directory/'manifest.json').read_bytes());requested=json.loads((directory/'requested-case.json').read_bytes())
    setup=requested['expectedSetup'];deployment=setup['installation']['topology']['deployment']
    authority=dict(profile='hms.pat.io-trusted-authority/0.1',principal='pat-io-trial-worker',deployment=deployment,
        initialRegistryRevision=13,initialGrants=[dict(principal='pat-io-trial-worker',deployment=deployment,target='*',verb='admin')],grantChanges=[])
    return dict(references=manifest['records'],files={r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']},
        configuration=manifest['configuration'],configuration_files={r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']},
        expected_setup=setup,expected_case=requested['case'],expected_actors=requested['expectedActors'],expected_authority=authority)


def structural(case):
    return inspect_resource_transcript(**{k:v for k,v in case.items() if k!='expected_authority'})


def call_result(phase,change):
    def edit(doc):
        if doc['kind']=='call_returned' and doc['value']['phase']==phase:change(doc['value']['result'])
    return edit


class IoResourceSemanticsTests(unittest.TestCase):
    def checked(self,primitive):
        value=inspect_resource_challenge(**load(primitive))
        for k in ('exactResourceScheduleChecked','expectedResponseVerified','completeHistoryChecked','independentOutcomeChecked',
                  'staticTimingPolicyChecked','wholeDeclaredDomainChecked'):self.assertTrue(value[k])
        for k in ('configurationAttested','compilerIdentityAttested','requiredMatrixCoverageChecked','allFaultScenariosChecked',
                  'actualAggregateStorageEnforced','physicalMeasurementChecked','qualificationPassed'):self.assertFalse(value[k])
        h=value['history'];self.assertEqual(h['decisions'],dict(admissions=4,busyRefusals=3,replays=5,historicalReads=1,dispatches=4))
        self.assertEqual(h['operations']['operationsChecked'],4);self.assertEqual(h['operations']['eventsChecked'],20)
        self.assertEqual(h['board']['receiptVersionsChecked'],8);self.assertEqual(h['board']['checkpointsChecked'],44)
        self.assertEqual(h['configuration']['configurationSnapshots'],44);self.assertEqual(h['sampling']['driveSampleBatches'],7)
        self.assertEqual(h['sampling']['initialSampleBatches'],1);self.assertTrue(h['parentAbsenceChecked'])
        self.assertTrue(value['outcome']['settledAndQuiescent']);self.assertEqual(value['outcome']['unresolvedOperationIds'],[])
        self.assertEqual((value['outcome']['activations'],value['outcome']['completedCycles'],value['outcome']['canceledActivations']),(4,4,0))
        self.assertEqual(value['outcome']['completionContract'],'provider_challenge');self.assertFalse(value['outcome']['physicalObjectiveVerified'])

    def test_gpio_matrix_shared_resource_history(self):self.checked('gpio')
    def test_pwm_matrix_shared_resource_history(self):self.checked('pwm')

    def rejected(self,edit,*,structure_passes=False):
        case=rewrite(load(),edit)
        if structure_passes:self.assertTrue(structural(case)['exactResourceScheduleChecked'])
        with self.assertRaises(ValueError):inspect_resource_challenge(**case)

    def test_replay_cannot_return_another_operation(self):
        self.rejected(call_result(9,lambda r:r.update(id='op:'+'0'*32)),structure_passes=True)

    def test_admission_reply_cannot_forge_a_claim_fence(self):
        self.rejected(call_result(2,lambda r:r['claims'][0].update(fence=99)),structure_passes=True)

    def test_admission_reply_cannot_claim_completion(self):
        self.rejected(call_result(2,lambda r:r.update(state='completed')),structure_passes=True)

    def test_historical_gpio_result_is_not_a_current_idle_claim(self):
        self.rejected(call_result(12,lambda r:r['result']['output']['result'].update(safeIdle=False)),structure_passes=True)

    def test_historical_result_cannot_relabel_the_owner(self):
        self.rejected(call_result(12,lambda r:r.update(instanceId='sim:gpio5:other-route')),structure_passes=True)

    def test_historical_result_cannot_replace_its_receipt(self):
        self.rejected(call_result(12,lambda r:r['result']['output'].update(receiptDigest='sha256:'+'0'*64)),structure_passes=True)

    def test_hidden_instance_activation_is_rejected(self):
        def change(r):
            if r['instance']=='sim:gpio6':r['activations']+=1
        self.rejected(rows('io_effects',change))

    def test_alias_completion_cannot_omit_its_activation(self):
        case=receipt_attack(load(),lambda r:r['result'].update(activationCommitted=False) if r['intent']['instanceId']=='sim:gpio5:other-route' else None)
        with self.assertRaises(ValueError):inspect_resource_challenge(**case)

    def test_pwm_receipt_cannot_claim_an_uncompleted_cycle(self):
        case=receipt_attack(load(),lambda r:r['result'].update(cycleCompleted=False) if r['intent']['instanceId']=='sim:pwm5' and r['state']=='completed' else None)
        with self.assertRaises(ValueError):inspect_resource_challenge(**case)

    def test_alias_cannot_use_the_gpio_route_receipt(self):
        case=load();gpio=case['expected_actors']['gpio']['original_descriptor']['binding']['adapterId']
        changed=receipt_attack(case,lambda r:r.update(adapterId=gpio) if r['intent']['instanceId']=='sim:gpio5:other-route' else None)
        with self.assertRaises(ValueError):inspect_resource_challenge(**changed)

    def test_shared_authority_floor_cannot_be_reset(self):
        self.rejected(rows('resource_floors',lambda r:r.update(fence=2) if r['fence']==3 else None))

    def test_board_floor_cannot_be_route_local(self):
        self.rejected(rows('io_fences',lambda r:r.update(fence=1) if r['fence']==3 else None))

    def test_active_board_owner_cannot_be_forged(self):
        self.rejected(rows('io_owners',lambda r:r.update(operation='op:'+'0'*32)))

    def test_active_pad_value_must_match_the_admitted_actor(self):
        def change(r):
            v=json.loads(r['state'])
            if v.get('mode')=='push_pull_output':v['level']=0;r['state']=canonical(v).decode()
        self.rejected(rows('io_resources',change))

    def test_accepted_event_time_is_derived_from_its_call(self):
        self.rejected(rows('events',lambda r:r.update(time_ms=r['time_ms']+1) if r['kind']=='accepted' else None))

    def test_replay_namespace_cannot_be_extended(self):
        self.rejected(rows('namespaces',lambda r:r.update(expires_ms=r['expires_ms']+1)))

    def test_probe_cannot_become_a_hidden_retained_key(self):
        self.rejected(rows('replay_keys',lambda r:r.update(caller_key='trial:probe:gpio_busy') if r['caller_key']=='trial:actor:gpio' else None))

    def test_registry_revision_cannot_authorize_admission_from_another_revision(self):
        def change(r):
            v=json.loads(r['admission']);v['policy_revision']='registry:99';r['admission']=canonical(v).decode()
        self.rejected(rows('operations',change))

    def test_trusted_grants_cannot_be_inferred_from_captured_success(self):
        case=load();case['expected_authority']['initialGrants']=[]
        self.assertTrue(structural(case)['exactResourceScheduleChecked'])
        with self.assertRaises(ValueError):inspect_resource_challenge(**case)

    def test_unplanned_grant_changes_are_refused(self):
        case=load();case['expected_authority']['grantChanges']=[dict(phase=1,label='lower:before',grants=[])]
        with self.assertRaises(ValueError):inspect_resource_challenge(**case)

    def test_alias_binding_cannot_change_between_captures(self):
        def change(r):
            if r['instance']=='sim:gpio5:other-route':
                v=json.loads(r['document']);v['calibrationRevision']='synthetic:another';r['document']=canonical(v).decode()
        self.rejected(rows('reg_bindings',change))

    def test_sample_counts_cannot_ignore_prior_activations(self):
        def change(r):
            if r['property']=='value':
                v=json.loads(r['document']);v['value']=0;r['document']=canonical(v).decode()
        self.rejected(rows('reg_observations',change))

    def test_final_observation_cannot_hide_known_operations(self):
        def edit(doc):
            if doc['kind']=='trial_observation':doc['value']['operationIds'].pop()
        self.rejected(edit,structure_passes=True)

    def test_original_probe_request_cannot_reuse_the_completed_gpio_key(self):
        def edit(doc):
            if doc['kind']=='compiled_plan':plan=doc['value']
            elif doc['kind']=='call_returned' and doc['value']['label']=='lower':plan=doc['value']['result']
            else:return
            plan['probes']['gpio_while_pwm']['operationKey']='trial:actor:gpio'
        self.rejected(edit)

    def test_validated_shared_model_still_rejects_undeclared_actors(self):
        case=load();programs={r:_Program(a|{'installation':case['expected_setup']['installation']}) for r,a in case['expected_actors'].items()}
        model=_SharedModel(programs);request=programs['gpio'].request({},'namespace:test','session:test')
        intent=request['procedure']['steps'][0]['request']['intent'];intent['instanceId']='hidden:actor'
        with self.assertRaisesRegex(ValueError,'UNDECLARED_ACTOR'):model.intent(intent)

    def test_eligible_dispatch_cannot_be_silently_skipped(self):
        case=load();trace=_read(case['references'],case['files'],case['expected_setup'],resource_profile=True)
        snapshots=_configuration(trace,case['references'],case['files'],case['configuration'],case['configuration_files'])
        programs={r:_Program(a|{'installation':case['expected_setup']['installation']}) for r,a in case['expected_actors'].items()}
        frames,_,_=_configuration_history(trace,snapshots,programs,case['expected_authority'])
        plans=next(r['value'] for r in trace['records'] if r['kind']=='compiled_plan')
        requests={r:p['request']['procedure']['steps'][0]['request'] for r,p in plans['actors'].items()}
        frames[3,'drive:adapters:after']['execution']['io_dispatch_links']=[]
        with self.assertRaisesRegex(ValueError,'DISPATCH_INVENTORY'):
            _decisions(trace,frames,requests,plans['probes']['gpio_while_pwm'],_SharedModel(programs))

    def test_old_public_transcript_modes_reject_resource_data(self):
        case=load()
        for flags in ({},{'clock_profile':True},{'conflict_profile':True}):
            with self.assertRaises(ValueError):_read(case['references'],case['files'],case['expected_setup'],**flags)

    def test_semantic_module_has_no_runtime_or_producer_import(self):
        path=Path(__file__).parents[1]/'hms/pat_io_resource_semantics.py';tree=ast.parse(path.read_bytes())
        modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        forbidden={'pat_compiler','pat_io_trials','pat_io_resource_capture','pat_io_combined_matrix','journal','registry','synthetic_io_runtime','sqlite3'}
        self.assertFalse(set(modules)&forbidden);self.assertFalse(any(isinstance(n,ast.Import) for n in ast.walk(tree)))

    def test_pure_checker_performs_no_io_or_clock_read(self):
        case=load()
        def veto(*args,**kwargs):raise AssertionError('resource semantics used I/O or time')
        with patch.object(builtins,'open',veto),patch.object(Path,'open',veto),patch.object(sqlite3,'connect',veto),patch.object(time,'time',veto),patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_resource_challenge(**case)['completeHistoryChecked'])
