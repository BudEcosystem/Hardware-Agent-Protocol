"""Actual original-runtime permission withdrawal after a modeled activation."""
import json
from unittest.mock import patch

from hms.journal import JournalError
from hms.pat_io_configuration_capture import ConfiguredIoTrialEngine
from test_pat_io_configuration_capture import IoConfigurationCaptureTests
from test_pat_io_contracts import program, descriptor


# Trusted test plan, separate from the captured registry rows. The effective
# changes are grant read on the actor and remove the original wildcard admin.
GRANT_PHASES = {
    'test_active_gpio_revocation_stops_and_prevents_remaining_step': 5,
    'test_active_pwm_revocation_restores_all_claimed_outputs': 5,
    'test_active_revocation_at_due_time_precedes_completion': 5,
    'test_completed_effect_reconciles_after_permission_withdrawal': 6,
    'test_committed_revocation_stop_survives_authority_reply_loss': 5,
    'test_prior_cancel_request_keeps_its_cause_after_revocation': 6,
}


class IoActiveRevocationTests(IoConfigurationCaptureTests):
    def make(self, *, pwm=False, count=1):
        directory = self.workspace/'trial-0'; directory.mkdir(mode=0o700)
        engine = ConfiguredIoTrialEngine(directory,program(count=count,pwm=pwm),self.document,
                                         descriptor(self.document,pwm=pwm))
        self.engines.append(engine); engine.lower({'duration':20}); engine.submit()
        return engine

    def pending(self, engine):
        engine.drive('procedure'); engine.drive('adapters')
        operation, = engine.operations()
        self.assertEqual(operation['state'],'running')
        self.assertEqual(engine.runtime.io_board.receipt(operation['id'])['state'],'pending')
        self.assertTrue(operation['claims'])
        return operation

    def withdraw(self, engine, *, pwm=False):
        self.assertEqual(engine.phase+1,GRANT_PHASES[self._testMethodName])
        registry,owner = engine.runtime.registry,engine.owner; target = 'sim:pwm5' if pwm else 'sim:gpio5'
        self.authority_plan = {'profile':'hms.pat.io-trusted-authority/0.1','principal':owner.principal,
            'deployment':owner.deployment,'initialRegistryRevision':13,
            'initialGrants':[{'principal':owner.principal,'deployment':owner.deployment,'target':'*','verb':'admin'}],
            'grantChanges':[{'phase':GRANT_PHASES[self._testMethodName],'label':'drive:adapters:before',
                'grants':[{'principal':owner.principal,'deployment':owner.deployment,'target':target,'verb':'read'}]}]}
        registry.grant(owner,owner.principal,target,'read')
        registry.grant(owner,owner.principal,'*','admin',enabled=False)
        self.assertTrue(registry.allowed(owner,'read',target))
        self.assertFalse(registry.allowed(owner,'invoke:'+('pwm_burst' if pwm else 'gpio_pulse'),target))

    def assert_idle(self, engine, operation, reason):
        receipt = engine.runtime.io_board.receipt(operation['id'])
        self.assertEqual(receipt['sequence'],2); self.assertEqual(receipt['state'],'canceled')
        self.assertEqual(receipt['result'],{'activationCommitted':True,'cycleCompleted':False,'safeIdle':True,'reason':reason})
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_owners').fetchone()[0],0)
        for resource,state in engine.runtime.io_board.db.execute('SELECT resource,state FROM io_resources'):
            self.assertEqual(json.loads(state),engine.runtime.io_board._idle[resource])
        return receipt

    def retain_and_close(self):
        # Super retains partial output and errors; no repair or state deletion.
        try: super().retain_and_close()
        finally:
            for index,_ in enumerate(self.engines):
                path = self.workspace/('engine-%d.json'%index)
                if path.is_file():
                    value = json.loads(path.read_bytes()); value['expectedAuthority'] = getattr(self,'authority_plan',None)
                    path.write_text(json.dumps(value,indent=2)+'\n')

    def test_active_gpio_revocation_stops_and_prevents_remaining_step(self):
        engine = self.make(count=2); operation = self.pending(engine); self.withdraw(engine)
        engine.drive('adapters'); self.assert_idle(engine,operation,'authority_or_binding_lost')
        current, = engine.operations(); self.assertEqual(current['state'],'failed'); self.assertFalse(current['claims'])
        engine.drive('procedure'); self.assertEqual(engine.status()['executionState'],'failed')
        engine.drive('adapters'); self.assertEqual(len(engine.operations()),1)
        self.assertEqual(self.effects(engine),(1,0,1))
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0],2)

    def test_active_pwm_revocation_restores_all_claimed_outputs(self):
        engine = self.make(pwm=True); operation = self.pending(engine); self.withdraw(engine,pwm=True)
        self.assertEqual(len(operation['claims']),3)
        engine.drive('adapters'); receipt = self.assert_idle(engine,operation,'authority_or_binding_lost')
        self.assertEqual(set(receipt['idleState']),{'atom:pin5','atom:chan0','atom:timer0'})
        current, = engine.operations(); self.assertEqual(current['state'],'failed'); self.assertFalse(current['claims'])
        engine.drive('procedure'); self.assertEqual(engine.status()['executionState'],'failed')
        self.assertEqual(self.effects(engine,'sim:pwm5'),(1,0,1))

    def test_active_revocation_at_due_time_precedes_completion(self):
        engine = self.make(); operation = self.pending(engine)
        engine.advance_to(engine.runtime.io_board.receipt(operation['id'])['dueMonoMs'])
        self.withdraw(engine); engine.drive('adapters')
        self.assert_idle(engine,operation,'authority_or_binding_lost')
        self.assertEqual(self.effects(engine),(1,0,1))
        self.assertFalse(engine.operations()[0]['claims'])
        engine.drive('procedure'); self.assertEqual(engine.status()['executionState'],'failed')

    def test_completed_effect_reconciles_after_permission_withdrawal(self):
        engine = self.make(); operation = self.pending(engine); original = engine.runtime.journal.record_execution; lost=[]
        def lose(ticket,state,evidence):
            if state=='completed' and not lost:
                lost.append(ticket.operation_id); raise JournalError('injected:active_revocation_completion_reply_loss')
            return original(ticket,state,evidence)
        engine.advance_to(engine.runtime.io_board.receipt(operation['id'])['dueMonoMs'])
        with patch.object(engine.runtime.journal,'record_execution',side_effect=lose):
            with self.assertRaisesRegex(JournalError,'injected:active_revocation_completion_reply_loss'): engine.drive('adapters')
        self.assertEqual(lost,[operation['id']]); self.assertEqual(self.effects(engine),(1,1,0))
        self.assertEqual(engine.operations()[0]['state'],'outcome_unknown'); self.assertTrue(engine.operations()[0]['claims'])
        self.withdraw(engine); engine.drive('adapters')
        current, = engine.operations(); self.assertEqual(current['state'],'completed'); self.assertFalse(current['claims'])
        engine.drive('procedure'); self.assertEqual(engine.status()['executionState'],'completed')
        receipt = engine.runtime.io_board.receipt(operation['id']); self.assertTrue(receipt['result']['cycleCompleted'])
        self.assertEqual(self.effects(engine),(1,1,0)); self.assertEqual(receipt['sequence'],2)

    def test_committed_revocation_stop_survives_authority_reply_loss(self):
        engine = self.make(); operation = self.pending(engine); self.withdraw(engine)
        original = engine.runtime.journal.record_execution; lost=[]
        def lose(ticket,state,evidence):
            if state=='failed' and not lost:
                lost.append(ticket.operation_id); raise JournalError('injected:active_revocation_stop_reply_loss')
            return original(ticket,state,evidence)
        with patch.object(engine.runtime.journal,'record_execution',side_effect=lose):
            with self.assertRaisesRegex(JournalError,'injected:active_revocation_stop_reply_loss'): engine.drive('adapters')
        self.assertEqual(lost,[operation['id']]); self.assert_idle(engine,operation,'authority_or_binding_lost')
        current, = engine.operations(); self.assertEqual(current['state'],'outcome_unknown'); self.assertTrue(current['claims'])
        engine.drive('adapters'); self.assert_idle(engine,operation,'authority_or_binding_lost')
        current, = engine.operations(); self.assertEqual(current['state'],'failed'); self.assertFalse(current['claims'])
        engine.drive('procedure'); self.assertEqual(engine.status()['executionState'],'failed')
        self.assertEqual(self.effects(engine),(1,0,1))
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0],2)

    def test_prior_cancel_request_keeps_its_cause_after_revocation(self):
        engine = self.make(); operation = self.pending(engine); engine.cancel(); self.withdraw(engine)
        engine.drive('adapters'); self.assert_idle(engine,operation,'client_cancel')
        current, = engine.operations(); self.assertEqual(current['state'],'canceled'); self.assertFalse(current['claims'])
        engine.drive('procedure'); self.assertEqual(engine.status()['executionState'],'canceled')
        self.assertEqual(self.effects(engine),(1,0,1))
