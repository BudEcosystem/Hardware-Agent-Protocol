"""Original runtime captures of unknown authority outcomes with pending outputs."""
import copy
import json
from unittest.mock import patch

from hms.journal import JournalError
from test_pat_io_active_revocation import IoActiveRevocationTests


BEGIN = dict(phase=4,label='drive:adapters',point='board.begin.after_commit',
             exception='JournalError',code='injected:io_begin_reply_loss',occurrences=1)
FINISH = dict(phase=5,label='drive:adapters',point='board.finish.before_commit',
              exception='JournalError',code='injected:io_finish_before_commit',occurrences=1)
RECONCILE = dict(phase=5,label='drive:adapters',point='journal.reconcile.before_commit',
                 exception='JournalError',code='injected:io_recovery_authority_reply_loss',occurrences=1)
FAULTS = {
    'test_unknown_gpio_acceptance_stops_without_running_remaining_step':[BEGIN],
    'test_unknown_pwm_acceptance_stops_all_claimed_outputs':[BEGIN],
    'test_pending_finish_failure_keeps_output_active_until_recovery':[FINISH],
    'test_unknown_pending_at_due_time_stops_instead_of_completing':[BEGIN],
    'test_unknown_pending_recovery_survives_invocation_withdrawal':[BEGIN],
    'test_cancel_request_does_not_relabel_unknown_pending_recovery':[BEGIN],
    'test_recovery_stop_survives_authority_reconciliation_reply_loss':[BEGIN,RECONCILE],
    'test_failed_recovery_stop_retains_active_output_and_claims':[BEGIN,FINISH],
}
WITHDRAW = 'test_unknown_pending_recovery_survives_invocation_withdrawal'


class IoPendingRecoveryTests(IoActiveRevocationTests):
    def make(self, *, pwm=False, count=1):
        self.fault_plan = {'profile':'hms.pat.io-trusted-fault-plan/0.1',
                           'faults':copy.deepcopy(FAULTS[self._testMethodName])}
        self.injected = []
        engine = super().make(pwm=pwm,count=count)
        owner = engine.owner
        self.authority_plan = {'profile':'hms.pat.io-trusted-authority/0.1','principal':owner.principal,
            'deployment':owner.deployment,'initialRegistryRevision':13,
            'initialGrants':[{'principal':owner.principal,'deployment':owner.deployment,'target':'*','verb':'admin'}],
            'grantChanges':[]}
        if self._testMethodName == WITHDRAW:
            self.authority_plan['grantChanges'] = [{'phase':5,'label':'drive:adapters:before',
                'grants':[{'principal':owner.principal,'deployment':owner.deployment,'target':'sim:gpio5','verb':'read'}]}]
        return engine

    def fault(self, engine, point, operation_id):
        planned, = [f for f in self.fault_plan['faults'] if f['point']==point]
        self.assertEqual(engine.phase,planned['phase'])
        self.assertFalse(any(f['point']==point for f in self.injected))
        self.injected.append({'phase':engine.phase,'point':point,'operationId':operation_id})
        raise JournalError(planned['code'])

    def unknown_begin(self, engine):
        engine.drive('procedure'); original=engine.runtime.io_board.begin
        def lose(*args,**kwargs):
            receipt=original(*args,**kwargs)
            self.assertEqual(receipt['state'],'pending')
            self.fault(engine,'board.begin.after_commit',receipt['operationId'])
        with patch.object(engine.runtime.io_board,'begin',side_effect=lose):
            engine.drive('adapters')
        operation,=engine.operations(); self.assert_unknown_active(engine,operation)
        self.assertEqual(engine.runtime.journal._db.execute('SELECT count(*) FROM io_authority_receipts').fetchone()[0],0)
        return operation

    def assert_unknown_active(self, engine, operation):
        current,=engine.operations(); self.assertEqual(current['id'],operation['id'])
        self.assertEqual(current['state'],'outcome_unknown'); self.assertTrue(current['claims'])
        receipt=engine.runtime.io_board.receipt(operation['id'])
        self.assertEqual((receipt['sequence'],receipt['state']),(1,'pending'))
        self.assertEqual(receipt['result'],dict(activationCommitted=True,cycleCompleted=False,safeIdle=False,reason=None))
        owners=list(engine.runtime.io_board.db.execute('SELECT resource,operation,fence FROM io_owners'))
        self.assertEqual({(r[0],r[1],r[2]) for r in owners},
                         {(c['resource'],operation['id'],c['fence']) for c in receipt['claims']})
        states={r[0]:json.loads(r[1]) for r in engine.runtime.io_board.db.execute('SELECT resource,state FROM io_resources')}
        self.assertEqual({a:states[a] for a in receipt['activeState']},receipt['activeState'])
        self.assertEqual(self.effects(engine,receipt['intent']['instanceId']),(1,0,0))
        return receipt

    def settled(self, engine, operation, *, pwm=False, canceled_parent=False):
        receipt=self.assert_idle(engine,operation,'reconciliation_stop')
        current,=engine.operations(); self.assertEqual(current['state'],'failed'); self.assertFalse(current['claims'])
        self.assertTrue(current['may_have_acted'])
        engine.drive('procedure')
        self.assertEqual(engine.status()['executionState'],'canceled' if canceled_parent else 'failed')
        self.assertEqual(len(engine.operations()),1)
        self.assertEqual(self.effects(engine,'sim:pwm5' if pwm else 'sim:gpio5'),(1,0,1))
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0],2)
        engine.drive('adapters')
        self.assertEqual(engine.runtime.io_board.receipt(operation['id']),receipt)
        self.assertEqual(self.effects(engine,'sim:pwm5' if pwm else 'sim:gpio5'),(1,0,1))

    def retain_and_close(self):
        try: super().retain_and_close()
        finally:
            for index,_ in enumerate(self.engines):
                path=self.workspace/('engine-%d.json'%index)
                if path.is_file():
                    value=json.loads(path.read_bytes())
                    value['expectedFaults']=getattr(self,'fault_plan',None)
                    value['injectedFaults']=getattr(self,'injected',[])
                    path.write_text(json.dumps(value,indent=2)+'\n')

    def test_unknown_gpio_acceptance_stops_without_running_remaining_step(self):
        engine=self.make(count=2); operation=self.unknown_begin(engine)
        engine.drive('adapters'); self.settled(engine,operation)

    def test_unknown_pwm_acceptance_stops_all_claimed_outputs(self):
        engine=self.make(pwm=True); operation=self.unknown_begin(engine)
        self.assertEqual(len(operation['claims']),3)
        engine.drive('adapters'); self.settled(engine,operation,pwm=True)

    def test_pending_finish_failure_keeps_output_active_until_recovery(self):
        engine=self.make(); operation=self.pending(engine)
        def fail(operation_id,**kwargs): self.fault(engine,'board.finish.before_commit',operation_id)
        with patch.object(engine.runtime.io_board,'finish',side_effect=fail):
            with self.assertRaisesRegex(JournalError,'injected:io_finish_before_commit'): engine.drive('adapters')
        self.assert_unknown_active(engine,operation)
        engine.drive('adapters'); self.settled(engine,operation)

    def test_unknown_pending_at_due_time_stops_instead_of_completing(self):
        engine=self.make(); operation=self.unknown_begin(engine)
        engine.advance_to(engine.runtime.io_board.receipt(operation['id'])['dueMonoMs'])
        engine.drive('adapters'); self.settled(engine,operation)

    def test_unknown_pending_recovery_survives_invocation_withdrawal(self):
        engine=self.make(); operation=self.unknown_begin(engine)
        self.assertEqual(engine.phase+1,5)
        engine.runtime.registry.grant(engine.owner,engine.owner.principal,'sim:gpio5','read')
        engine.runtime.registry.grant(engine.owner,engine.owner.principal,'*','admin',enabled=False)
        self.assertFalse(engine.runtime.registry.allowed(engine.owner,'invoke:gpio_pulse','sim:gpio5'))
        engine.drive('adapters'); self.settled(engine,operation)

    def test_cancel_request_does_not_relabel_unknown_pending_recovery(self):
        engine=self.make(); operation=self.unknown_begin(engine); engine.cancel()
        self.assertEqual(engine.operations()[0]['cancel_state'],'requested')
        engine.drive('adapters'); self.settled(engine,operation,canceled_parent=True)
        self.assertEqual(engine.operations()[0]['cancel_state'],'requested')

    def test_recovery_stop_survives_authority_reconciliation_reply_loss(self):
        engine=self.make(); operation=self.unknown_begin(engine)
        def lose(operation_id,state,evidence):
            self.assertEqual(state,'failed'); self.assert_idle(engine,operation,'reconciliation_stop')
            self.fault(engine,'journal.reconcile.before_commit',operation_id)
        with patch.object(engine.runtime.journal,'reconcile',side_effect=lose):
            with self.assertRaisesRegex(JournalError,'injected:io_recovery_authority_reply_loss'): engine.drive('adapters')
        current,=engine.operations(); self.assertEqual(current['state'],'outcome_unknown'); self.assertTrue(current['claims'])
        receipt=self.assert_idle(engine,operation,'reconciliation_stop')
        engine.drive('adapters'); self.settled(engine,operation)
        self.assertEqual(engine.runtime.io_board.receipt(operation['id']),receipt)

    def test_failed_recovery_stop_retains_active_output_and_claims(self):
        engine=self.make(); operation=self.unknown_begin(engine)
        def fail(operation_id,**kwargs): self.fault(engine,'board.finish.before_commit',operation_id)
        with patch.object(engine.runtime.io_board,'finish',side_effect=fail):
            with self.assertRaisesRegex(JournalError,'injected:io_finish_before_commit'): engine.drive('adapters')
        self.assert_unknown_active(engine,operation)
        engine.drive('adapters'); self.settled(engine,operation)
