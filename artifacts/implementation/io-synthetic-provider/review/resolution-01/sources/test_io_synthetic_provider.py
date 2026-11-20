"""Original staged integration tests. Not executed while root test hold is active."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, Evidence, JournalError
from hms.synthetic_io_board import receipt_digest
from hms.synthetic_io_adapter import link_digest
from hms.synthetic_io_installation import DRIVER, PROFILE, implementation_digest, normalize_installation
from hms.synthetic_io_runtime import IoRuntime
from io_fixtures import topology, generations

EVIDENCE_DIRECTORY = None


def installation():
    graph = topology()
    graph['consumers'] = [row for row in graph['consumers'] if row['instanceId'] != 'sim:timer0']
    for row in graph['consumers']:
        row['actionId'] = 'pwm_burst' if row['instanceId'] == 'sim:pwm5' else 'gpio_pulse'
    graph['consumers'].append({'instanceId':'sim:gpio5:other-route','actionId':'gpio_pulse','rootAliases':['alias:gpio5'],'requires':[]})
    return {'profile':PROFILE,'driver':DRIVER,'driverDigest':implementation_digest(),'boardId':'board','topology':graph,
        'initialGenerations':generations(graph),'routes':{'profile':'hms.resource-route-inventory/0.1','adapters':{
            'io:routeA':['sim:gpio5','sim:pwm5'],'io:routeB':['sim:gpio6','sim:gpio5:other-route']}},
        'handlers':[{'instanceId':row['instanceId'],'actionId':row['actionId'],
            'primitive':'pwm_burst' if row['instanceId'] == 'sim:pwm5' else 'gpio_pulse'} for row in graph['consumers']]}


class SyntheticIoProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/'runtime'
        self._captured = False; self.addCleanup(self.capture)
        self.wall = 1000; self.mono = 1000
        self.owner = Context('owner','simulation:io-hub')
        self.configuration = installation()
        self.runtime = IoRuntime(self.directory,create=True,owner=self.owner,installation=self.configuration,
            wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono)
        self.addCleanup(lambda:self.runtime.close() if self.runtime is not None else None)
        self.namespace = self.runtime.journal.issue_namespace(self.owner,100000)['token']

    def tearDown(self):
        self.capture()

    def capture(self):
        if EVIDENCE_DIRECTORY is None:
            return
        if self._captured:
            return
        self._captured = True
        target = EVIDENCE_DIRECTORY/self._testMethodName; target.mkdir()
        for path in sorted(self.directory.glob('*.db')):
            with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as source:
                with sqlite3.connect(target/path.name) as copy_db:
                    source.backup(copy_db)
        (target/'context.json').write_text(json.dumps({'wallMs':getattr(self,'wall',None),'monotonicMs':getattr(self,'mono',None),
            'installation':getattr(self,'configuration',None),'databaseFiles':sorted(path.name for path in self.directory.glob('*.db'))},indent=2)+'\n')

    def advance(self, amount):
        self.wall += amount; self.mono += amount

    def request(self, instance='sim:gpio5', *, key='operation:1', duration=20):
        action = 'pwm_burst' if instance == 'sim:pwm5' else 'gpio_pulse'
        args = {'durationMs':duration,'frequencyHz':1000,'dutyPermille':500,'resolutionBits':8} if action == 'pwm_burst' else {'durationMs':duration,'level':1}
        description = self.runtime.registry.describe(self.owner,instance)
        binding,presence = description['binding'],description['presence']
        return {'protocol':'hms.invoke/0.1','replayNamespace':self.namespace,'operationKey':key,'intent':{
            'instanceId':instance,'actionId':action,'arguments':args,'requiredEffect':'capability_completion',
            'descriptionDigest':description['descriptionDigest'],'bindingGeneration':binding['generation'],
            'controlGeneration':binding['controlGeneration'],'calibrationRevision':binding['calibrationRevision'],
            'endpointSession':presence['session'],'timing':{'notBeforeUnixMs':self.wall,'latestStartUnixMs':self.wall+1000,
                'maxRunMs':2000,'latestCompletionUnixMs':self.wall+3000}}}

    def submit(self, instance='sim:gpio5', **kwargs):
        return self.runtime.journal.submit(self.owner,canonical(self.request(instance,**kwargs)))

    def status(self, operation):
        return self.runtime.journal.status(self.owner,operation['id'])

    def receipt(self, operation):
        return self.runtime.io_board.receipt(operation['id'])

    def assert_idle(self, receipt):
        self.assertIs(receipt['result']['safeIdle'],True)
        for atom,state in receipt['idleState'].items():
            stored = self.runtime.io_board.db.execute('SELECT state FROM io_resources WHERE resource=?',(atom,)).fetchone()[0]
            self.assertEqual(json.loads(stored),state)
            self.assertIsNone(self.runtime.io_board.db.execute('SELECT 1 FROM io_owners WHERE resource=?',(atom,)).fetchone())

    def reopen(self):
        self.runtime.close()
        self.runtime = IoRuntime(self.directory,installation=self.configuration,
            wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono)

    def test_shared_board_gpio_pwm_exclusion_and_independent_pad_progress(self):
        first = self.submit()
        with self.assertRaisesRegex(JournalError,'RESOURCE_BUSY'):
            self.submit('sim:pwm5',key='pwm:busy')
        other = self.submit('sim:gpio6',key='other:free')
        self.assertIs(self.runtime.adapters['io:routeA'].board,self.runtime.adapters['io:routeB'].board)
        self.runtime.tick()
        self.assertEqual(self.status(first)['state'],'running'); self.assertEqual(self.status(other)['state'],'running')
        self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['resources']['atom:pin5']['mode'],'push_pull_output')
        self.advance(20); self.runtime.tick()
        for operation in (first,other):
            self.assertEqual(self.status(operation)['state'],'completed'); self.assertEqual(self.status(operation)['claims'],[])
            self.assert_idle(self.receipt(operation))

    def test_pwm_tracks_timer_channel_and_pin_then_safe_idle(self):
        operation = self.submit('sim:pwm5')
        self.runtime.tick(); receipt = self.receipt(operation)
        self.assertEqual([row['resource'] for row in receipt['claims']],['atom:chan0','atom:pin5','atom:timer0'])
        self.assertEqual(receipt['activeState']['atom:timer0']['frequencyHz'],1000)
        self.assertTrue(receipt['activeState']['atom:chan0']['enabled'])
        self.advance(20); self.runtime.tick(); self.assert_idle(self.receipt(operation))

    def test_cross_route_alias_uses_one_board_fence_and_receipt_replay(self):
        request = self.request(); first = self.runtime.journal.submit(self.owner,canonical(request))
        self.runtime.tick(); self.advance(20); self.runtime.tick()
        again = self.runtime.journal.submit(self.owner,canonical(request))
        self.assertEqual(again['id'],first['id'])
        self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['value'],1)
        second = self.submit('sim:gpio5:other-route',key='cross:route')
        self.runtime.tick()
        self.assertEqual(self.receipt(second)['claims'],[{'resource':'atom:pin5','fence':2}])
        floor = self.runtime.io_board.db.execute("SELECT fence,operation FROM io_fences WHERE resource='atom:pin5'").fetchone()
        self.assertEqual(tuple(floor),(2,second['id']))
        # The old terminal receipt remains historical evidence while a valid
        # different owner now drives the same pad.
        self.assertEqual(self.runtime.operation(self.owner,first['id'])['executionState'],'completed')

    def test_cancellation_before_dispatch_has_no_provider_receipt_or_activation(self):
        operation = self.submit(); self.runtime.journal.request_cancel(self.owner,operation['id']); self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'canceled'); self.assertEqual(self.status(operation)['claims'],[])
        self.assertIsNone(self.receipt(operation)); self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['value'],0)

    def test_interrupted_pulse_keeps_activation_fact_and_idle_before_release(self):
        operation = self.submit(duration=100); self.runtime.tick()
        self.runtime.journal.request_cancel(self.owner,operation['id']); self.runtime.tick()
        receipt = self.receipt(operation)
        self.assertEqual(self.status(operation)['state'],'canceled')
        self.assertEqual(receipt['result'],{'activationCommitted':True,'cycleCompleted':False,'safeIdle':True,'reason':'client_cancel'})
        self.assert_idle(receipt); self.assertEqual(self.status(operation)['claims'],[])

    def test_slow_validation_vetoes_start_before_output_activation(self):
        operation = self.submit()
        backend = self.runtime.adapters['io:routeA']; original = backend._guard
        def slow_guard(*args,**kwargs):
            self.advance(1000)
            return original(*args,**kwargs)
        with patch.object(backend,'_guard',side_effect=slow_guard):
            self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'rejected_before_start')
        receipt = self.receipt(operation)
        self.assertFalse(receipt['result']['activationCommitted']); self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['value'],0)

    def test_recheck_delay_is_sampled_again_before_effect_decision(self):
        operation = self.submit(duration=100); self.runtime.tick()
        original = self.runtime.policy.recheck
        def slow(context,op,now):
            original(context,op,now); self.advance(2000)
        with patch.object(self.runtime.policy,'recheck',side_effect=slow):
            self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'failed')
        self.assertEqual(self.receipt(operation)['result']['reason'],'execution_deadline')
        self.assert_idle(self.receipt(operation)); self.assertEqual(self.status(operation)['claims'],[])

    def test_owner_reopen_cancels_once_and_rotates_shared_session(self):
        first = self.submit(duration=100); second = self.submit('sim:gpio6',key='second:active',duration=100)
        self.runtime.tick(); session = self.runtime.io_board.session; epoch = self.runtime.journal.owner_epoch
        self.reopen()
        self.assertEqual(self.runtime.journal.owner_epoch,epoch+1)
        self.assertNotEqual(self.runtime.io_board.session,session)
        for operation in (first,second):
            self.assertEqual(self.status(operation)['state'],'outcome_unknown')
            self.assertEqual(self.receipt(operation)['result']['reason'],'board_owner_reopened')
            self.assertEqual(self.receipt(operation)['sequence'],2)
        self.runtime.tick()
        for operation in (first,second):
            self.assertEqual(self.status(operation)['state'],'canceled'); self.assertEqual(self.status(operation)['claims'],[])
        self.assertEqual(self.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0],4)

    def test_board_commit_then_authority_failure_reconciles_without_reactivation(self):
        operation = self.submit(); self.runtime.tick(); self.advance(20)
        backend = self.runtime.adapters['io:routeA']; original = backend._retain_receipt
        def fail_terminal(op,receipt):
            if receipt['state'] == 'completed':
                raise JournalError('injected:authority_receipt_failure')
            return original(op,receipt)
        with patch.object(backend,'_retain_receipt',side_effect=fail_terminal):
            with self.assertRaisesRegex(JournalError,'injected:authority_receipt_failure'):
                self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'outcome_unknown')
        self.assertTrue(self.status(operation)['claims']); self.assert_idle(self.receipt(operation))
        self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'completed'); self.assertEqual(self.status(operation)['claims'],[])
        self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['value'],1)

    def test_lost_acceptance_ack_stops_exact_pending_receipt_without_continuing(self):
        operation = self.submit(duration=100)
        backend = self.runtime.adapters['io:routeA']; original = backend._retain_receipt; once = []
        def lose_once(op,receipt):
            if not once:
                once.append(True); raise JournalError('injected:lost_acceptance')
            return original(op,receipt)
        with patch.object(backend,'_retain_receipt',side_effect=lose_once):
            self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'outcome_unknown'); self.assertEqual(self.receipt(operation)['state'],'pending')
        self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'failed')
        self.assertEqual(self.receipt(operation)['result']['reason'],'reconciliation_stop'); self.assert_idle(self.receipt(operation))

    def test_missing_receipt_is_not_quiescence_and_claims_remain(self):
        operation = self.submit(duration=100); self.runtime.tick()
        ticket = self.runtime.journal.monitoring_ticket(operation['id'])
        self.runtime.journal.mark_unknown(ticket,'injected:receipt_loss')
        self.runtime.adapters['io:routeA']._pending.pop(operation['id'])
        self.runtime.io_board.db.execute('DELETE FROM io_receipts WHERE operation=?',(operation['id'],))
        self.runtime.tick()  # Unchanged virtual time may throttle periodic sampling.
        with self.assertRaisesRegex(JournalError,'IO_OWNERSHIP_UNKNOWN'):
            self.runtime.adapters['io:routeA'].refresh(force=True)
        self.assertEqual(self.status(operation)['state'],'outcome_unknown'); self.assertTrue(self.status(operation)['claims'])
        self.assertTrue(self.runtime.io_board.db.execute('SELECT 1 FROM io_owners WHERE operation=?',(operation['id'],)).fetchone())

    def test_contradictory_active_state_refuses_stop_and_preserves_unknown(self):
        operation = self.submit(duration=100); self.runtime.tick()
        self.runtime.io_board.db.execute("UPDATE io_resources SET state=? WHERE resource='atom:pin5'",(canonical({'kind':'pin','mode':'high_impedance','level':None}),))
        self.runtime.journal.request_cancel(self.owner,operation['id'])
        with self.assertRaises(JournalError):
            self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'outcome_unknown'); self.assertTrue(self.status(operation)['claims'])
        self.assertEqual(self.receipt(operation)['state'],'pending')

    def test_terminal_receipt_does_not_mask_current_unknown_quiescence(self):
        operation = self.submit(); self.runtime.tick(); self.advance(20)
        backend = self.runtime.adapters['io:routeA']
        with patch.object(backend,'_retain_receipt',side_effect=JournalError('injected:after_board_commit')):
            with self.assertRaises(JournalError):
                self.runtime.tick()
        self.assertEqual(self.receipt(operation)['state'],'completed')
        self.runtime.io_board.db.execute("UPDATE io_resources SET state=? WHERE resource='atom:pin5'",
            (canonical({'kind':'pin','mode':'push_pull_output','level':1}),))
        with self.assertRaisesRegex(JournalError,'IO_QUIESCENCE_UNKNOWN'):
            self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'outcome_unknown'); self.assertTrue(self.status(operation)['claims'])

    def test_binding_invalidation_does_not_prevent_reopen_stop_or_historical_reconciliation(self):
        old_request = self.request(duration=100)
        operation = self.runtime.journal.submit(self.owner,canonical(old_request)); self.runtime.tick()
        self.runtime.registry.invalidate(self.owner,'sim:gpio5')
        self.reopen()
        self.assert_idle(self.receipt(operation)); self.assertEqual(self.receipt(operation)['result']['reason'],'board_owner_reopened')
        self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'canceled'); self.assertEqual(self.status(operation)['claims'],[])
        new_key = copy.deepcopy(old_request); new_key['operationKey'] = 'invalidated:new'
        with self.assertRaisesRegex(JournalError,'BINDING_INACTIVE'):
            self.runtime.journal.submit(self.owner,canonical(new_key))

    def test_admin_grant_loss_does_not_prevent_installed_historical_recovery(self):
        operation = self.submit(duration=100); self.runtime.tick()
        rescue = Context('rescue',self.owner.deployment)
        self.runtime.registry.grant(self.owner,rescue.principal,'*','admin')
        self.runtime.registry.grant(self.owner,self.owner.principal,'*','admin',enabled=False)
        self.reopen(); self.runtime.tick()
        # Registry admin permission does not bypass the Journal's principal-
        # ownership check. Inspect recovery internally, then prove both public
        # read paths still enforce their existing authority boundaries.
        with self.runtime.journal._mutex:
            current = self.runtime.journal._operation(operation['id'])
        for context in (rescue,self.owner):
            with self.assertRaisesRegex(JournalError,'ACCESS_DENIED'):
                self.runtime.journal.status(context,operation['id'])
        self.assertEqual(current['state'],'canceled'); self.assertEqual(current['claims'],[])
        self.assert_idle(self.receipt(operation))
        with self.assertRaisesRegex(JournalError,'ACCESS_DENIED'):
            self.runtime.journal.issue_namespace(self.owner,200000)

    def test_rehashed_wrong_dispatch_attempt_is_not_exact_evidence(self):
        operation = self.submit(duration=100); self.runtime.tick()
        row = self.runtime.journal._db.execute('SELECT document FROM io_dispatch_links WHERE operation=?',(operation['id'],)).fetchone()
        changed = json.loads(row[0]); changed['attemptId'] = 'forged:attempt'
        self.runtime.journal._db.execute('UPDATE io_dispatch_links SET document=?,digest=? WHERE operation=?',
            (canonical(changed),link_digest(changed),operation['id']))
        with self.assertRaisesRegex(JournalError,'IO_DISPATCH_ATTEMPT_CHANGED'):
            self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'outcome_unknown'); self.assertTrue(self.status(operation)['claims'])
        self.assertEqual(self.receipt(operation)['state'],'pending')

    def test_oversized_receipt_is_refused_before_body_reaches_row_factory(self):
        operation = self.submit(duration=100); self.runtime.tick()
        db = self.runtime.io_board.db
        db.execute('UPDATE io_receipts SET document=? WHERE operation=?',(b' ' * 65537,operation['id']))
        observed = []
        def inspect(cursor,row):
            observed.extend(value for value in row if type(value) is bytes and len(value) > 65536)
            return sqlite3.Row(cursor,row)
        db.row_factory = inspect
        try:
            with self.assertRaisesRegex(JournalError,'IO_STORAGE_SHAPE'):
                self.runtime.io_board.receipt(operation['id'])
        finally:
            db.row_factory = sqlite3.Row
        self.assertEqual(observed,[]); self.assertTrue(self.status(operation)['claims'])

    def test_extra_authority_receipt_sequence_is_bounded_and_refused(self):
        operation = self.submit(duration=100); self.runtime.tick()
        receipt = self.receipt(operation)
        for sequence in (2,3):
            self.runtime.journal._db.execute('INSERT INTO io_authority_receipts VALUES (?,?,?,?)',
                (operation['id'],sequence,canonical(receipt),receipt_digest(receipt)))
        with self.assertRaisesRegex(JournalError,'IO_STORAGE_SHAPE'):
            self.runtime.journal.release_resources(operation['id'],
                Evidence('simulation','io:routeA','io-receipt:'+receipt_digest(receipt).split(':')[1],('resources_quiescent',)))
        self.assertTrue(self.status(operation)['claims'])

    def test_wrong_or_extra_fences_never_create_provider_receipt(self):
        operation = self.submit('sim:pwm5'); backend = self.runtime.adapters['io:routeA']
        guard = lambda:{'reason':None,'nowMonoMs':self.mono,'budgetOriginMonoMs':self.mono,'clockEpoch':self.runtime.registry.receipt_epoch}
        for claims in ([{'resource':'atom:pin5','fence':1}],operation['claims']+[{'resource':'atom:extra','fence':1}],
                       [row|{'fence':0} for row in operation['claims']]):
            with self.assertRaisesRegex(JournalError,'IO_CLAIM_CLOSURE'):
                self.runtime.io_board.begin(operation|{'claims':claims},backend.adapter_id,guard=guard)
        self.assertIsNone(self.receipt(operation)); self.assertEqual(self.runtime.io_board.observe('sim:pwm5')['value'],0)

    def test_unretained_or_forged_quiescence_evidence_cannot_release(self):
        operation = self.submit(duration=100); self.runtime.tick()
        with self.assertRaisesRegex(JournalError,'IO_RETAINED_RECEIPT_MISSING'):
            self.runtime.journal.release_resources(operation['id'],Evidence('simulation','io:routeA','io-receipt:'+'0'*64,('resources_quiescent',)))
        pending = self.receipt(operation)
        with self.assertRaisesRegex(JournalError,'IO_EVIDENCE_ASSERTION'):
            self.runtime.journal.release_resources(operation['id'],Evidence('simulation','io:routeA','io-receipt:'+receipt_digest(pending).split(':')[1],('resources_quiescent',)))
        self.assertTrue(self.status(operation)['claims'])

    def test_admin_generation_publication_does_not_execute_or_update_provider(self):
        old_request = self.request()
        self.runtime.catalog.resources.publish_generation(self.owner,'svcA','generation:1','generation:2',expected_revision=1)
        binding,_ = self.runtime.registry._binding('sim:gpio5')
        self.assertFalse(self.runtime.io_board.supports_binding(binding))
        with self.assertRaisesRegex(JournalError,'BINDING_CHANGED'):
            self.runtime.journal.submit(self.owner,canonical(old_request))
        self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['value'],0)

    def test_unavailable_or_changed_store_never_reinitializes_effect_history(self):
        operation = self.submit(); self.runtime.tick(); self.advance(20); self.runtime.tick()
        board_path = self.runtime.io_board.path
        self.runtime.close(); self.runtime = None
        board_path.unlink()
        with self.assertRaisesRegex(JournalError,'IO_BOARD_MISSING'):
            IoRuntime(self.directory,installation=self.configuration,wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono)
        self.assertFalse(board_path.exists())

    def test_installation_identity_and_integer_configuration_are_checked(self):
        changed = copy.deepcopy(self.configuration); changed['driverDigest'] = 'sha256:'+'0'*64
        with self.assertRaisesRegex(JournalError,'IO_DRIVER_CHANGED'):
            normalize_installation(changed)
        changed = copy.deepcopy(self.configuration); changed['topology']['nodes']['pin5']['properties']['electrical']['nominalMilliVolt'] = 3300.0
        with self.assertRaisesRegex(JournalError,'IO_INTEGER_CONFIGURATION_REQUIRED'):
            normalize_installation(changed)

    def test_old_session_and_wrong_installed_route_refuse_before_effect(self):
        old = self.request(); self.reopen()
        with self.assertRaisesRegex(JournalError,'ENDPOINT_SESSION_CHANGED'):
            self.runtime.journal.submit(self.owner,canonical(old))
        request = self.request(); binding,_ = self.runtime.registry._binding('sim:gpio5')
        with self.assertRaisesRegex(JournalError,'IO_INSTALLATION_UNSUPPORTED'):
            self.runtime.adapters['io:routeB'].validate_admission(request['intent'],binding,('atom:pin5',))
        self.assertEqual(self.runtime.io_board.observe('sim:gpio5')['value'],0)
