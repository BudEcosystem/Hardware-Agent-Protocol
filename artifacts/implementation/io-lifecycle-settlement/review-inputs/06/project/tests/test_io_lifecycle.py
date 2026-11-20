"""Original staged Journal/Registry/board lifecycle integration; execution held."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import ContractError, canonical
from hms.journal import Context, JournalError
from hms.registry import Registry, RegistryPolicy
from hms.resource_topology import generation_change_claims
from hms.synthetic_io_adapter import link_digest
from hms.synthetic_lifecycle_contracts import PROFILE, digest, normalize
from hms.synthetic_lifecycle_runtime import LifecycleRuntime
from test_io_synthetic_provider import installation as ordinary_installation
from test_resource_topology import node, pin, generations
from io_evidence_capture import EvidenceWorkspace, snapshot_databases, close_retaining

EVIDENCE_DIRECTORY = None


def installation():
    io = ordinary_installation(); graph = io['topology']
    graph['nodes']['hub']['contains'].append('svcC')
    graph['nodes']['svcC'] = node('service',{'serviceProfile':'synthetic-service/0.1'},contains=('driverC',),requires=('hub',))
    graph['nodes']['driverC'] = node('driver',{'driverProfile':'synthetic-io-hub/0.1','implementationDigest':'sha256:'+'a'*64},requires=('svcC',))
    graph['nodes']['board']['contains'].extend(['pin7','gpio7'])
    graph['nodes']['pin7'] = pin(); graph['nodes']['gpio7'] = node('gpio_access',{'pin':'pin7'},requires=('driverC',))
    for name in ('svcC','driverC','pin7'):
        graph['atoms']['atom:'+name] = {'node':name,'purpose':'exclusive_hardware' if name=='pin7' else 'lifecycle'}
    graph['aliases']['alias:gpio7'] = {'node':'gpio7','includes':['atom:pin7']}
    graph['consumers'].extend([
        {'instanceId':'sim:gpio7','actionId':'gpio_pulse','rootAliases':['alias:gpio7'],'requires':[]},
        {'instanceId':'sim:gpio5','actionId':'gpio_sibling','rootAliases':['alias:gpio6'],'requires':[]}])
    io['routes']['adapters']['io:routeB'].append('sim:gpio7')
    io['handlers'].extend([{'instanceId':'sim:gpio7','actionId':'gpio_pulse','primitive':'gpio_pulse'},
        {'instanceId':'sim:gpio5','actionId':'gpio_sibling','primitive':'gpio_pulse'}])
    io['initialGenerations'] = generations(graph)
    return {'profile':PROFILE,'io':io,'management':[{'instanceId':'sim:management','adapterId':'io:management',
        'actions':{'advance_A':'svcA','advance_C':'svcC','advance_driver':'driverA'}}]}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = EvidenceWorkspace(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/'runtime'; self.wall = self.mono = 1000
        self.owner = Context('owner','simulation:io-hub'); self.configuration = installation()
        self.runtime = None; self._capture_number = 0; self._final_captured = False
        self.addCleanup(self.capture)
        self.runtime = LifecycleRuntime(self.directory,create=True,owner=self.owner,installation=self.configuration,
            wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono)
        self.addCleanup(lambda:close_retaining(self.temp,self.runtime))
        self.namespace = self.runtime.journal.issue_namespace(self.owner,100000)['token']

    def tearDown(self):
        self.capture()

    def capture(self, label='final'):
        if EVIDENCE_DIRECTORY is None or not self.directory.exists():
            return
        if label == 'final' and self._final_captured:
            return
        target = EVIDENCE_DIRECTORY/self._testMethodName/('%02d-'%self._capture_number+label)
        self._capture_number += 1
        try:
            snapshot_databases(self.directory,target,{'wallMs':self.wall,'monotonicMs':self.mono,
                'installation':self.configuration,'scope':'Original controlled-clock SQLite model; no physical/native timing proof.'})
        except BaseException as exc:
            self.temp.failed(exc)
            raise
        if label == 'final':
            self._final_captured = True

    @property
    def adapter(self):
        return self.runtime.adapters['io:management']

    def current(self, operation):
        return self.runtime.journal._operation(operation['id'])

    def advance(self, amount):
        self.wall += amount; self.mono += amount

    def refresh(self):
        for backend in self.runtime.adapters.values():
            backend.refresh(force=True)

    def request(self, *, instance='sim:management', action='advance_A', key='lifecycle:1', new='generation:2'):
        self.refresh()
        description = self.runtime.registry.describe(self.owner,instance); binding = description['binding']
        if instance == 'sim:management':
            target = self.configuration['management'][0]['actions'][action]
            saved = self.runtime.catalog.resources.snapshot(self.owner)
            args = {'expectedGeneration':saved['generations']['nodes'][target],'newGeneration':new,'expectedRevision':saved['revision']}
        else:
            args = {'durationMs':20,'level':1} if action != 'pwm_burst' else {
                'durationMs':20,'frequencyHz':1000,'dutyPermille':500,'resolutionBits':8}
        return {'protocol':'hms.invoke/0.1','replayNamespace':self.namespace,'operationKey':key,'intent':{
            'instanceId':instance,'actionId':action,'arguments':args,'requiredEffect':'capability_completion',
            'descriptionDigest':description['descriptionDigest'],'bindingGeneration':binding['generation'],
            'controlGeneration':binding['controlGeneration'],'calibrationRevision':binding['calibrationRevision'],
            'endpointSession':description['presence']['session'],'timing':{'notBeforeUnixMs':self.wall,
                'latestStartUnixMs':self.wall+1000,'maxRunMs':2000,'latestCompletionUnixMs':self.wall+3000}}}

    def submit(self, **kwargs):
        request = self.request(**kwargs)
        return self.runtime.journal.submit(self.owner,canonical(request))

    def effect_only(self, operation):
        with self.runtime.journal._mutex:
            origin = self.runtime.registry._monotonic()
            ticket = self.runtime.journal.claim_dispatch(operation['id'],
                _reserve=lambda op,ticket,now:self.adapter._reserve(op,ticket,now,origin))
            current = self.current(operation); link,dispatch = self.adapter._association(current)
            receipt = self.runtime.io_board.advance_generation(current,link,dispatch,
                guard=lambda:self.adapter._guard(current,link,link['checkpoint'],start=True))
            return ticket,receipt

    def reopen(self):
        self.runtime.close()
        self.runtime = LifecycleRuntime(self.directory,installation=self.configuration,
            wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono)

    def test_exact_all_sibling_claims_and_no_admin_publication_shortcut(self):
        operation = self.submit(); claims = {row['resource'] for row in operation['claims']}
        self.assertEqual(claims,{'atom:pin5','atom:pin6','atom:timer0','atom:chan0','atom:svcA'})
        with self.assertRaisesRegex(JournalError,'RESOURCE_CLAIMS_UNRESOLVED'):
            self.runtime.catalog.resources.publish_generation(self.owner,'svcA','generation:1','generation:3',expected_revision=1)
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)
        self.assertEqual(self.current(operation)['claims'],operation['claims'])

    def test_sibling_active_blocks_lifecycle_through_original_journal(self):
        sibling = self.submit(instance='sim:gpio5',action='gpio_sibling',key='sibling')
        self.runtime.tick(); self.assertEqual(self.current(sibling)['state'],'running')
        with self.assertRaisesRegex(JournalError,'RESOURCE_BUSY'):
            self.submit()
        self.advance(20); self.runtime.tick()
        lifecycle = self.submit(); self.runtime.tick()
        self.assertEqual(self.current(lifecycle)['state'],'completed')
        self.assertEqual(self.current(lifecycle)['claims'],[])

    def test_unrelated_pad_progress_and_generation_identity_stays_scoped(self):
        before = self.runtime.registry.describe(self.owner,'sim:gpio7')['binding']
        unrelated = self.submit(instance='sim:gpio7',action='gpio_pulse',key='unrelated')
        lifecycle = self.submit(); self.runtime.tick()
        self.assertEqual(self.current(lifecycle)['state'],'completed')
        self.assertEqual(self.current(unrelated)['state'],'running')
        self.assertEqual(self.runtime.registry.describe(self.owner,'sim:gpio7')['binding'],before)
        self.advance(20); self.runtime.tick(); self.assertEqual(self.current(unrelated)['claims'],[])

    def test_same_pad_cross_route_gpio_pwm_cannot_bypass_lifecycle_scope(self):
        lifecycle = self.submit()
        for instance,action in [('sim:gpio5:other-route','gpio_pulse'),('sim:pwm5','pwm_burst')]:
            with self.subTest(instance=instance),self.assertRaisesRegex(JournalError,'RESOURCE_BUSY'):
                self.submit(instance=instance,action=action,key=instance)
        self.runtime.tick(); self.assertEqual(self.current(lifecycle)['state'],'completed')

    def test_one_effect_and_one_publication_on_request_and_settlement_replay(self):
        request = self.request(); operation = self.runtime.journal.submit(self.owner,canonical(request))
        self.runtime.tick(); first = self.adapter.settle(operation['id'])
        replay = self.runtime.journal.submit(self.owner,canonical(request))
        self.assertEqual(replay['id'],operation['id']); self.assertEqual(self.adapter.settle(operation['id']),first)
        self.assertEqual(self.runtime.io_board.db.execute('SELECT count(*) FROM io_lc_receipts').fetchone()[0],1)
        self.assertEqual(self.runtime.journal._db.execute('SELECT count(*) FROM lc_publications').fetchone()[0],1)
        self.assertEqual(self.runtime.journal._db.execute("SELECT count(*) FROM events WHERE operation_id=? AND kind='resources_released'",(operation['id'],)).fetchone()[0],1)
        changed = copy.deepcopy(request); changed['intent']['arguments']['newGeneration'] = 'generation:other'
        with self.assertRaisesRegex(JournalError,'KEY_CONFLICT'):
            self.runtime.journal.submit(self.owner,canonical(changed))

    def test_new_gpio_pwm_work_old_fresh_refuses_old_receipts_survive_reopen(self):
        old_request = self.request(instance='sim:gpio5',action='gpio_pulse',key='old-pulse')
        old = self.runtime.journal.submit(self.owner,canonical(old_request)); self.runtime.tick(); self.advance(20); self.runtime.tick()
        old_receipt = self.runtime.io_board.validated_receipt(old['id'])
        lifecycle = self.submit(); self.runtime.tick()
        stale = copy.deepcopy(old_request); stale['operationKey'] = 'stale-new'
        with self.assertRaisesRegex(JournalError,'BINDING_CHANGED'):
            self.runtime.journal.submit(self.owner,canonical(stale))
        for instance,action in [('sim:gpio5','gpio_pulse'),('sim:pwm5','pwm_burst')]:
            operation = self.submit(instance=instance,action=action,key='new:'+instance)
            self.runtime.tick(); self.advance(20); self.runtime.tick()
            self.assertEqual(self.current(operation)['state'],'completed')
        self.reopen()
        self.assertEqual(self.runtime.io_board.validated_receipt(old['id']),old_receipt)
        self.assertEqual(self.runtime.journal.submit(self.owner,canonical(old_request))['id'],old['id'])
        self.assertEqual(self.adapter.settle(lifecycle['id'])['terminalState'],'completed')

    def test_post_effect_invalidation_is_preserved_in_atomic_publication(self):
        operation = self.submit(); self.effect_only(operation); self.capture('provider-committed')
        self.runtime.registry.invalidate(self.owner,'sim:gpio5')
        self.adapter.settle(operation['id'])
        binding,active = self.runtime.registry._binding('sim:gpio5')
        self.assertFalse(active); self.assertEqual(self.current(operation)['state'],'completed')
        self.assertEqual(self.current(operation)['claims'],[])
        self.reopen(); self.assertFalse(self.runtime.registry._binding('sim:gpio5')[1])
        self.assertEqual(self.runtime.registry._binding('sim:gpio5')[0],binding)

    def test_revoked_submitter_and_unknown_clock_do_not_regrant_or_block_truth(self):
        operation = self.submit(); self.effect_only(operation)
        self.runtime.registry.grant(self.owner,'rescue','*','admin')
        self.runtime.registry.grant(self.owner,self.owner.principal,'*','admin',enabled=False)
        self.runtime.journal.clock_ms = lambda: (_ for _ in ()).throw(ValueError('controlled clock loss'))
        self.adapter.settle(operation['id'])
        self.assertEqual(self.current(operation)['state'],'completed'); self.assertEqual(self.current(operation)['claims'],[])
        with self.assertRaisesRegex(JournalError,'ACCESS_DENIED'):
            self.runtime.journal.issue_namespace(self.owner,200000)

    def test_scoped_rebase_keeps_disjoint_publication_and_no_global_hub_claim(self):
        operation = self.submit(); self.effect_only(operation)
        other = self.runtime.catalog.resources.publish_generation(self.owner,'svcC','generation:1','generation:C2',expected_revision=1)
        settled = self.adapter.settle(operation['id'])
        self.assertEqual(other['revision'],2); self.assertEqual(settled['publication']['dispatchRevision'],1)
        self.assertEqual(settled['publication']['baseRevision'],2); self.assertEqual(settled['publication']['revision'],3)
        saved = self.runtime.catalog.resources.snapshot(self.owner)
        self.assertEqual(saved['generations']['nodes']['svcC'],'generation:C2')
        self.assertEqual(saved['generations']['nodes']['svcA'],'generation:2')

    def test_rebound_consumer_refuses_settlement_with_claims_retained(self):
        operation = self.submit(); self.effect_only(operation)
        binding,_ = self.runtime.registry._binding('sim:gpio5'); binding['generation'] = 'rogue:generation'
        self.runtime.registry.bind(self.owner,canonical(binding))
        with self.assertRaises(JournalError):
            self.adapter.settle(operation['id'])
        self.assertTrue(self.current(operation)['claims']); self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)

    def test_fault_after_generation_write_rolls_back_binding_terminal_and_release(self):
        operation = self.submit(); self.effect_only(operation)
        original = self.runtime.registry._bind_recorded_effect_in_tx
        def fail(binding):
            original(binding); raise RuntimeError('controlled publication failure')
        with patch.object(self.runtime.registry,'_bind_recorded_effect_in_tx',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'controlled'):
                self.adapter.settle(operation['id'])
        self.capture('authority-rolled-back')
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)
        self.assertEqual(self.current(operation)['state'],'dispatching'); self.assertTrue(self.current(operation)['claims'])
        self.assertEqual(self.runtime.journal._db.execute('SELECT count(*) FROM lc_receipts').fetchone()[0],0)
        self.adapter.settle(operation['id']); self.assertEqual(self.current(operation)['claims'],[])

    def test_fault_after_release_is_also_rolled_back_before_commit(self):
        operation = self.submit(); self.effect_only(operation)
        original = self.runtime.journal._release_resources_in_tx
        def fail(*args):
            original(*args); raise RuntimeError('controlled release failure')
        with patch.object(self.runtime.journal,'_release_resources_in_tx',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'controlled'):
                self.adapter.settle(operation['id'])
        self.assertEqual(self.current(operation)['state'],'dispatching'); self.assertTrue(self.current(operation)['claims'])
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)
        self.adapter.settle(operation['id'])

    def test_owner_reopen_after_provider_commit_settles_without_second_effect(self):
        operation = self.submit(); self.effect_only(operation); self.capture('before-owner-close')
        self.reopen(); self.assertEqual(self.current(operation)['state'],'outcome_unknown')
        self.runtime.tick(); self.assertEqual(self.current(operation)['state'],'completed')
        self.assertEqual(self.current(operation)['claims'],[])
        self.assertEqual(self.runtime.io_board.db.execute('SELECT count(*) FROM io_lc_receipts').fetchone()[0],1)

    def test_unknown_without_provider_receipt_never_reexecutes_or_clears_claims(self):
        operation = self.submit(); origin = self.mono
        self.runtime.journal.claim_dispatch(operation['id'],_reserve=lambda op,ticket,now:self.adapter._reserve(op,ticket,now,origin))
        self.reopen(); self.runtime.tick()
        self.assertEqual(self.current(operation)['state'],'outcome_unknown'); self.assertTrue(self.current(operation)['claims'])
        self.assertEqual(self.runtime.io_board.db.execute('SELECT count(*) FROM io_lc_receipts').fetchone()[0],0)

    def test_current_nonidle_corruption_blocks_old_terminal_receipt(self):
        operation = self.submit(); self.effect_only(operation)
        self.runtime.io_board.db.execute('UPDATE io_resources SET state=? WHERE resource=?',
            (canonical({'kind':'pin','mode':'push_pull_output','level':1}),'atom:pin5'))
        with self.assertRaisesRegex(JournalError,'IO_QUIESCENCE_UNKNOWN'):
            self.adapter.settle(operation['id'])
        self.assertTrue(self.current(operation)['claims']); self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)

    def test_missing_generation_history_blocks_receipt_settlement(self):
        operation = self.submit(); self.effect_only(operation)
        self.runtime.io_board.db.execute('DELETE FROM io_lc_snapshots WHERE revision=1')
        with self.assertRaises(JournalError):self.adapter.settle(operation['id'])
        self.assertTrue(self.current(operation)['claims'])

    def test_cancel_before_dispatch_and_after_effect_have_distinct_truth(self):
        first = self.submit(); self.runtime.journal.request_cancel(self.owner,first['id']); self.runtime.tick()
        self.assertEqual(self.current(first)['state'],'canceled')
        self.assertEqual(self.runtime.io_board.db.execute('SELECT count(*) FROM io_lc_receipts').fetchone()[0],0)
        second = self.submit(key='after-effect'); self.effect_only(second)
        self.runtime.journal.request_cancel(self.owner,second['id']); self.adapter.settle(second['id'])
        self.assertEqual(self.current(second)['state'],'completed'); self.assertEqual(self.current(second)['cancel_state'],'requested')
        self.assertTrue(self.runtime.io_board.lifecycle_receipt(second['id'])['generationApplied'])

    def test_generation_token_nonreuse_and_stable_management_binding(self):
        before = self.runtime.registry._binding('sim:management')[0]
        first = self.submit(); self.runtime.tick()
        self.assertEqual(self.runtime.registry._binding('sim:management')[0],before)
        with self.assertRaisesRegex(JournalError,'RESOURCE_GENERATION_REUSED'):
            self.submit(key='reused',new='generation:1')
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],2)

    def test_bad_typed_revision_and_ordinary_grants_do_not_authorize_management(self):
        request = self.request(); request['intent']['arguments']['expectedRevision'] = True
        with self.assertRaises(ContractError):self.runtime.journal.submit(self.owner,canonical(request))
        user = Context('gpio-user',self.owner.deployment)
        self.runtime.registry.grant(self.owner,user.principal,'*','namespace')
        self.runtime.registry.grant(self.owner,user.principal,'sim:gpio5','read')
        self.runtime.registry.grant(self.owner,user.principal,'sim:gpio5','invoke:gpio_pulse')
        request = self.request(); request['replayNamespace'] = self.runtime.journal.issue_namespace(user,100000)['token']
        with self.assertRaisesRegex(JournalError,'ACCESS_DENIED'):
            self.runtime.journal.submit(user,canonical(request))
        self.assertEqual(self.runtime.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0],0)

    def test_omitted_or_empty_managed_inventory_cannot_fall_back_to_flat_root(self):
        request = self.request()
        for inventory in (None,()):
            policy = RegistryPolicy(**({} if inventory is None else {'managed_resource_adapters':inventory}))
            policy.registry = self.runtime.registry
            with self.assertRaisesRegex(JournalError,'RESOURCE_RESOLVER_REQUIRED'):
                policy.admit(self.owner,request['intent'],self.wall)

    def test_actual_old_registry_refuses_lifecycle_storage_profile(self):
        path = Path(__file__).parent/'fixtures/lifecycle_registry_696/hms/registry.py'
        spec = importlib.util.spec_from_file_location('hms._registry696_lifecycle_proof',path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with self.assertRaisesRegex(JournalError,'UNSUPPORTED_REGISTRY'):
            module.Registry(self.runtime.journal,monotonic_ms=lambda:self.mono)

    def test_tampered_dispatch_attempt_or_claims_cannot_authorize_settlement(self):
        operation = self.submit(); self.effect_only(operation)
        row = self.runtime.journal._db.execute('SELECT document FROM io_dispatch_links WHERE operation=?',(operation['id'],)).fetchone()
        changed = json.loads(row[0]); changed['attemptId'] = 'other:attempt'
        self.runtime.journal._db.execute('UPDATE io_dispatch_links SET document=?,digest=? WHERE operation=?',
            (canonical(changed),link_digest(changed),operation['id']))
        with self.assertRaisesRegex(JournalError,'IO_DISPATCH_ATTEMPT_CHANGED'):
            self.adapter.settle(operation['id'])
        self.assertTrue(self.current(operation)['claims'])

    def test_oversized_lifecycle_receipt_refuses_before_host_body_fetch(self):
        operation = self.submit(); self.effect_only(operation); db = self.runtime.io_board.db
        db.execute('UPDATE io_lc_receipts SET document=? WHERE operation=?',(b' '*65537,operation['id']))
        observed = []; original = db.row_factory
        def factory(cursor,row):
            observed.extend(item for item in row if type(item) is bytes and len(item)>65536)
            return sqlite3.Row(cursor,row)
        db.row_factory = factory
        try:
            with self.assertRaisesRegex(JournalError,'IO_STORAGE_SHAPE'):self.adapter.settle(operation['id'])
        finally:db.row_factory = original
        self.assertEqual(observed,[]); self.assertTrue(self.current(operation)['claims'])

    def test_slow_validation_rechecks_original_start_budget_before_generation_effect(self):
        operation = self.submit(); original = self.runtime.io_board._binding_rows
        def slow(value):
            result = original(value); self.advance(1000); return result
        with patch.object(self.runtime.io_board,'_binding_rows',side_effect=slow):
            self.runtime.tick()
        current = self.current(operation)
        self.assertEqual(current['state'],'rejected_before_start'); self.assertEqual(current['claims'],[])
        self.assertFalse(self.runtime.io_board.lifecycle_receipt(operation['id'])['generationApplied'])
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)

    def test_rehashed_publication_cannot_substitute_valid_old_proof_or_bool_revision(self):
        operation = self.submit(); self.runtime.tick(); db = self.runtime.journal._db
        original = json.loads(db.execute('SELECT document FROM lc_publications WHERE operation=?',(operation['id'],)).fetchone()[0])
        link,dispatch = self.adapter._association(self.current(operation))
        old = dispatch['affected']['sim:gpio5']
        variants = []
        substituted = copy.deepcopy(original)
        substituted['publication']['bindings']['sim:gpio5'] = {'generation':old['binding']['generation'],
            'proofDigest':digest('HMS-LIFECYCLE-PUBLISHED-PROOF-v1',old['proof'])}
        variants.append(substituted)
        boolean = copy.deepcopy(original); boolean['publication']['dispatchRevision'] = True; variants.append(boolean)
        carrier = copy.deepcopy(original); carrier['publication']['bindings'] = list(carrier['publication']['bindings']); variants.append(carrier)
        for invalid in variants:
            with self.subTest(invalid=invalid['publication']['dispatchRevision']):
                db.execute('UPDATE lc_publications SET document=?,digest=? WHERE operation=?',
                    (canonical(invalid),digest('HMS-LIFECYCLE-SETTLEMENT-v1',invalid),operation['id']))
                with self.assertRaisesRegex(JournalError,'LIFECYCLE_SETTLEMENT_CHANGED'):
                    self.adapter.settle(operation['id'])
        db.execute('UPDATE lc_publications SET document=?,digest=? WHERE operation=?',
            (canonical(original),digest('HMS-LIFECYCLE-SETTLEMENT-v1',original),operation['id']))
        self.assertEqual(self.adapter.settle(operation['id']),original)
        self.assertEqual(db.execute('SELECT count(*) FROM lc_publications').fetchone()[0],1)

    def test_commit_failure_keeps_generation_state_and_claims_atomic(self):
        operation = self.submit(); self.effect_only(operation); journal = self.runtime.journal; original = journal._db
        class CommitFailure:
            armed = True
            def __getattr__(self,name):return getattr(original,name)
            def execute(self,sql,*args):
                if sql == 'COMMIT' and self.armed:
                    self.armed = False
                    raise sqlite3.OperationalError('controlled authority commit failure')
                return original.execute(sql,*args)
        journal._db = CommitFailure()
        try:
            with self.assertRaisesRegex(sqlite3.OperationalError,'controlled authority commit failure'):
                self.adapter.settle(operation['id'])
        finally:journal._db = original
        self.assertEqual(self.current(operation)['state'],'dispatching'); self.assertTrue(self.current(operation)['claims'])
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)
        self.assertEqual(original.execute('SELECT count(*) FROM lc_publications').fetchone()[0],0)
        self.capture('commit-refused'); self.adapter.settle(operation['id'])

    def test_missing_owned_atom_cannot_be_exempted_by_the_operation_id(self):
        operation = self.submit(); self.effect_only(operation)
        self.runtime.journal._db.execute('DELETE FROM claims WHERE operation_id=? AND resource=?',(operation['id'],'atom:pin6'))
        with self.assertRaisesRegex(JournalError,'IO_AUTHORITY_CLAIMS_CHANGED'):
            self.adapter.settle(operation['id'])
        self.assertTrue(self.current(operation)['claims'])
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)

    def test_final_guard_operation_lookup_delay_cannot_escape_start_deadline(self):
        operation = self.submit(); original_guard = self.adapter._guard; original_lookup = self.runtime.journal._operation
        calls = []
        def guarded(*args,**kwargs):
            calls.append(True)
            if len(calls) == 2:
                def delayed(identifier):
                    value = original_lookup(identifier); self.advance(1000); return value
                with patch.object(self.runtime.journal,'_operation',side_effect=delayed):
                    return original_guard(*args,**kwargs)
            return original_guard(*args,**kwargs)
        with patch.object(self.adapter,'_guard',side_effect=guarded):
            self.runtime.tick()
        self.assertEqual(len(calls),2)
        self.assertEqual(self.current(operation)['state'],'rejected_before_start')
        self.assertFalse(self.runtime.io_board.lifecycle_receipt(operation['id'])['generationApplied'])
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['revision'],1)

    def test_static_future_generation_scope_does_not_grant_fresh_cas(self):
        future = self.request(key='future-generation',new='generation:3')
        future['intent']['arguments'].update(expectedRevision=2,expectedGeneration='generation:2')
        self.runtime.policy.validate_bound(self.owner,future['intent'],self.wall)
        with self.assertRaisesRegex(JournalError,'RESOURCE_GENERATION_CONFLICT'):
            self.runtime.journal.submit(self.owner,canonical(future))
        first = self.submit(); self.runtime.tick(); self.assertEqual(self.current(first)['state'],'completed')
        second = self.runtime.journal.submit(self.owner,canonical(future)); self.runtime.tick()
        self.assertEqual(self.current(second)['state'],'completed')
        self.assertEqual(self.runtime.catalog.resources.snapshot(self.owner)['generations']['nodes']['svcA'],'generation:3')

    def test_shared_internal_helpers_refuse_without_transaction(self):
        binding,_ = self.runtime.registry._binding('sim:gpio5')
        with self.assertRaisesRegex(JournalError,'BINDING_TRANSACTION_REQUIRED'):
            self.runtime.registry._bind_checked_in_tx(binding,self.owner.deployment)
        with self.assertRaisesRegex(JournalError,'RELEASE_TRANSACTION_REQUIRED'):
            self.runtime.journal._release_resources_in_tx('not:an:operation',None)
