"""Original IoRuntime trials with retained raw state and bounded phase records."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms.pat_contracts import PatError
from hms.pat_io_trials import IoTrialEngine, ORIGIN
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_contracts import program, descriptor


class IoTrialTests(unittest.TestCase):
    def setUp(self):
        self.engines = []
        self.workspace = Path(tempfile.gettempdir()) / self._testMethodName
        self.workspace.mkdir(mode=0o700)
        self.addCleanup(self.retain_and_close)
        self.document = normalize_installation(installation())

    def retain_and_close(self):
        errors = []
        for index, engine in enumerate(self.engines):
            report = None
            try:
                if engine.runtime is not None:
                    engine.capture('test_final')
                    report = engine.report()
            except BaseException as error:
                errors.append(error)
            finally:
                try:
                    engine.close()
                except BaseException as error:
                    errors.append(error)
            (self.workspace / ('engine-%d.json' % index)).write_text(json.dumps({
                'testId': self.id(), 'directory': str(engine.directory), 'report': report,
                'records': engine.records, 'closed': engine.runtime is None,
                'cleanupErrors': [type(error).__name__ + ':' + str(error) for error in errors]}, indent=2)+'\n')
        # Never delete fixtures or evidence, including failed construction/tests.
        if errors:
            raise errors[0]

    def make(self, value=None, *, pwm=False, duration=20):
        value = value or program(pwm=pwm)
        directory = self.workspace / ('trial-%d' % len(self.engines)); directory.mkdir(mode=0o700)
        engine = IoTrialEngine(directory, value, self.document, descriptor(self.document, pwm=pwm))
        self.engines.append(engine)
        engine.lower({} if not value['parameters'] else {'duration': duration})
        engine.submit()
        return engine

    def first_pending(self, engine):
        engine.drive('procedure'); engine.drive('adapters')
        operation, = engine.operations()
        self.assertEqual(operation['state'], 'running')
        self.assertEqual(engine.runtime.io_board.receipt(operation['id'])['state'], 'pending')
        return operation

    def effects(self, engine, instance='sim:gpio5'):
        row = engine.runtime.io_board.db.execute('SELECT activations,completed,canceled FROM io_effects WHERE instance=?', (instance,)).fetchone()
        return tuple(row)

    def test_gpio_sequence_drains_progress_before_advancing_time(self):
        engine = self.make(program(count=2), duration=20)
        self.assertEqual(engine.finish()['executionState'], 'completed')
        operations = engine.operations()
        receipts = [engine.runtime.io_board.receipt(op['id']) for op in operations]
        self.assertEqual([r['startedMonoMs'] for r in receipts], [ORIGIN, ORIGIN+20])
        self.assertEqual([r['dueMonoMs'] for r in receipts], [ORIGIN+20, ORIGIN+40])
        self.assertEqual(engine.clock.value, ORIGIN+40)
        self.assertEqual(self.effects(engine), (2, 2, 0))
        self.assertTrue(all(not op['claims'] for op in operations))
        self.assertFalse(engine.report()['qualificationPassed'])

    def test_pwm_active_and_idle_states_are_retained(self):
        engine = self.make(pwm=True, duration=30)
        operation = self.first_pending(engine)
        receipt = engine.runtime.io_board.receipt(operation['id'])
        self.assertEqual(receipt['activeState']['atom:pin5']['mode'], 'pwm_output')
        self.assertEqual(receipt['activeState']['atom:timer0']['frequencyHz'], 1000)
        self.assertEqual(receipt['activeState']['atom:chan0']['dutyPermille'], 375)
        self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(self.effects(engine, 'sim:pwm5'), (1, 1, 0))
        for row in engine.runtime.io_board.db.execute('SELECT resource,state FROM io_resources'):
            self.assertEqual(json.loads(row['state']), engine.runtime.io_board._idle[row['resource']])

    def test_early_admission_lease_is_counted_while_waiting(self):
        value = program(literal=True)
        value['steps'][0]['arguments']['durationMs']['literal'] = 1
        value['steps'][0]['timing'].update(notBeforeOffsetMs=59998, latestStartOffsetMs=60001,
                                          maxRunMs=2, latestCompletionOffsetMs=70000)
        value['timingBudget'] = {'latestStartOffsetMs':60001, 'latestCompletionOffsetMs':70000, 'maxRunSumMs':2}
        engine = self.make(value)
        engine.drive('procedure')
        operation, = engine.operations()
        self.assertEqual(operation['admission']['lease_expires_ms'], ORIGIN+60000)
        self.assertEqual(engine.clock.value, ORIGIN)
        self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(engine.clock.value, ORIGIN+59999)
        self.assertLess(engine.ticks, 12)

    def test_observation_refresh_is_not_zero_time_progress(self):
        value = program()
        value['steps'][0]['timing']['notBeforeOffsetMs'] = 50
        engine = self.make(value, duration=1)
        self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(engine.clock.value, ORIGIN+51)
        self.assertLess(engine.ticks, 12)

    def test_cancel_accepted_has_no_board_effect_but_retains_authority_floor(self):
        engine = self.make(); engine.drive('procedure')
        engine.cancel(); engine.drive()
        operation, = engine.operations()
        self.assertEqual(operation['state'], 'canceled'); self.assertFalse(operation['claims'])
        self.assertIsNone(engine.runtime.io_board.receipt(operation['id']))
        self.assertEqual(self.effects(engine), (0, 0, 0))
        self.assertEqual(engine.runtime.journal._db.execute('SELECT fence FROM resource_floors').fetchone()[0], 1)
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_fences').fetchone()[0], 0)

    def test_cancel_pending_preserves_activation_and_proves_idle(self):
        engine = self.make(); operation = self.first_pending(engine)
        engine.cancel(); engine.drive()
        receipt = engine.runtime.io_board.receipt(operation['id'])
        self.assertEqual(receipt['sequence'], 2)
        self.assertEqual(receipt['result'], {'activationCommitted':True, 'cycleCompleted':False, 'safeIdle':True, 'reason':'client_cancel'})
        self.assertEqual(self.effects(engine), (1, 0, 1))
        self.assertFalse(engine.operations()[0]['claims'])

    def test_reopen_accepted_refuses_stale_session_without_rebinding(self):
        engine = self.make(); engine.drive('procedure')
        request = canonical(engine.plan['request']); session = engine.runtime.io_board.session
        engine.reopen()
        self.assertNotEqual(engine.runtime.io_board.session, session)
        self.assertEqual(engine.status()['executionState'], 'interrupted')
        with self.assertRaisesRegex(JournalError, 'IO_SESSION_CHANGED'):
            engine.resume()
        self.assertEqual(canonical(engine.plan['request']), request)
        engine.cancel(); engine.drive()
        self.assertEqual(self.effects(engine), (0, 0, 0))
        self.assertFalse(engine.operations()[0]['claims'])

    def test_reopen_pending_cancels_once_and_reconciles_historical_receipt(self):
        engine = self.make(); operation = self.first_pending(engine)
        epoch = engine.runtime.journal.owner_epoch; engine.reopen()
        self.assertEqual(engine.runtime.journal.owner_epoch, epoch+1)
        receipt = engine.runtime.io_board.receipt(operation['id'])
        self.assertEqual(receipt['result']['reason'], 'board_owner_reopened')
        self.assertEqual(engine.operations()[0]['state'], 'outcome_unknown')
        engine.drive('adapters')
        with self.assertRaisesRegex(JournalError, 'PROCEDURE_DEPENDENCY_UNRESOLVED'):
            engine.resume()
        engine.cancel(); engine.drive()
        self.assertEqual(self.effects(engine), (1, 0, 1))
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0], 2)
        self.assertFalse(engine.operations()[0]['claims'])

    def lose_completion(self, engine):
        operation = self.first_pending(engine)
        original = engine.runtime.journal.record_execution; lost = []
        def fail_once(ticket, state, evidence):
            if state == 'completed' and not lost:
                lost.append(ticket.operation_id)
                raise JournalError('injected:trial_commit_reply_loss')
            return original(ticket, state, evidence)
        engine.advance_to(engine.next_event())
        with patch.object(engine.runtime.journal, 'record_execution', side_effect=fail_once):
            with self.assertRaisesRegex(JournalError, 'injected:trial_commit_reply_loss'):
                engine.drive('adapters')
        self.assertEqual(lost, [operation['id']])
        self.assertEqual(engine.operations()[0]['state'], 'outcome_unknown')
        self.assertTrue(engine.operations()[0]['claims'])
        self.assertEqual(self.effects(engine), (1, 1, 0))
        return operation

    def test_committed_cycle_survives_lost_reply_and_single_step_reopen(self):
        engine = self.make(); operation = self.lose_completion(engine)
        engine.reopen(); engine.drive('adapters')
        self.assertEqual(engine.operations()[0]['state'], 'completed')
        engine.resume(); self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(engine.operations()[0]['id'], operation['id'])
        self.assertEqual(self.effects(engine), (1, 1, 0))

    def test_completed_prefix_does_not_rebind_remaining_step_after_reopen(self):
        engine = self.make(program(count=2)); self.lose_completion(engine)
        request = canonical(engine.plan['request'])
        engine.reopen(); engine.drive('adapters')
        with self.assertRaisesRegex(JournalError, 'IO_SESSION_CHANGED'):
            engine.resume()
        self.assertEqual(canonical(engine.plan['request']), request)
        engine.cancel(); engine.drive()
        self.assertEqual(len(engine.operations()), 1)
        self.assertEqual(engine.operations()[0]['state'], 'completed')
        self.assertEqual(self.effects(engine), (1, 1, 0))

    def test_started_cycle_can_finish_after_latest_start(self):
        value = program(); value['steps'][0]['timing']['latestStartOffsetMs'] = 50
        engine = self.make(value, duration=100)
        self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(engine.clock.value, ORIGIN+100)

    def test_run_deadline_equality_cancels_instead_of_claiming_completion(self):
        engine = self.make(); operation = self.first_pending(engine)
        engine.advance_to(ORIGIN+500); engine.drive('adapters')
        receipt = engine.runtime.io_board.receipt(operation['id'])
        self.assertEqual(receipt['result']['reason'], 'execution_deadline')
        self.assertFalse(receipt['result']['cycleCompleted'])
        self.assertEqual(engine.finish()['executionState'], 'failed')
        self.assertEqual(self.effects(engine), (1, 0, 1))

    def test_raw_checkpoints_retain_typed_versions_ownership_and_replay_rows(self):
        engine = self.make(); self.first_pending(engine); engine.finish()
        kinds = set(); checkpoints = []
        for reference in engine.records:
            body = (engine.record_directory/reference['path']).read_bytes()
            self.assertEqual(len(body), reference['bytes'])
            self.assertEqual(hashlib.sha256(body).hexdigest(), reference['sha256'])
            record = json.loads(body); kinds.add(record['kind'])
            if record['kind'] == 'checkpoint': checkpoints.append(record['value'])
        self.assertIn('call_started', kinds); self.assertIn('call_returned', kinds)
        final = checkpoints[-1]
        rows = {(t['store'],t['table']): t for t in final['tables']}
        self.assertEqual(rows[('board','io_receipt_versions')]['rowCount'], 2)
        self.assertEqual(rows[('board','io_owners')]['rowCount'], 0)
        self.assertEqual(rows[('board','io_fences')]['rowCount'], 1)
        self.assertEqual(rows[('authority','replay_keys')]['rowCount'], 1)
        page = json.loads((engine.record_directory/rows[('board','io_receipt_versions')]['pages'][0]['path']).read_bytes())
        self.assertEqual(page['value']['rows'][0][-1]['type'], 'blob-utf8')

    def test_exact_parent_replay_does_not_repeat_effect_or_admission(self):
        engine = self.make(); engine.finish()
        before = engine.operations(); identity = engine.procedure_id
        result = engine.submit()
        self.assertEqual(result['procedureId'], identity)
        self.assertEqual(engine.operations(), before)
        self.assertEqual(self.effects(engine), (1, 1, 0))
        self.assertEqual(engine.runtime.journal._db.execute('SELECT fence FROM resource_floors').fetchone()[0], 1)

    def test_tick_budget_refuses_before_an_extra_handoff(self):
        engine = self.make()
        with patch('hms.pat_io_trials.MAX_TICKS', 0):
            with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_TICK_LIMIT'):
                engine.drive()
        self.assertFalse(engine.operations()); self.assertEqual(self.effects(engine), (0, 0, 0))

    def test_nonempty_output_directory_is_not_opened_as_runtime_state(self):
        directory = self.workspace/'nonempty'; directory.mkdir(mode=0o700)
        (directory/'marker').write_text('retain')
        with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_DIRECTORY_NOT_EMPTY'):
            IoTrialEngine(directory, program(), self.document, descriptor(self.document))
        self.assertEqual(sorted(p.name for p in directory.iterdir()), ['marker'])

    def test_missing_current_receipt_remains_unresolved(self):
        engine = self.make(); operation = self.first_pending(engine)
        engine.runtime.io_board.db.execute('DELETE FROM io_receipts WHERE operation=?', (operation['id'],))
        with self.assertRaises(JournalError):
            engine.drive('adapters')
        report = engine.report()
        self.assertEqual(report['unresolvedOperations'], [operation['id']])
        self.assertFalse(report['qualificationPassed'])
        self.assertTrue(engine.operations()[0]['claims'])

    def test_output_budget_refusal_keeps_original_evidence(self):
        engine = self.make(); before = list(engine.records)
        with patch('hms.pat_io_trials.MAX_OUTPUT_BYTES', engine.output_bytes):
            with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_EVIDENCE_LIMIT'):
                engine.capture('cannot_fit')
        self.assertEqual(engine.records, before)
        self.assertFalse(engine.operations())

    def test_negative_lowering_retains_type_and_never_admits_work(self):
        directory = self.workspace/'trial-0'; directory.mkdir(mode=0o700)
        engine = IoTrialEngine(directory, program(), self.document, descriptor(self.document))
        self.engines.append(engine)
        with self.assertRaisesRegex(PatError, 'PAT_PARAMETER_OUT_OF_DOMAIN'):
            engine.lower({'duration': 20.0})
        self.assertFalse(engine.operations()); self.assertIsNone(engine.plan)
        inputs = [json.loads((engine.record_directory/r['path']).read_bytes()) for r in engine.records]
        typed, = [r['value'] for r in inputs if r['kind']=='lower_input']
        self.assertEqual(typed['parameters']['duration'], {'type':'number','value':20})
        with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_ALREADY_COMPILED'):
            engine.lower({'duration':20})

    def test_sixteen_steps_retain_all_receipt_versions_within_bounds(self):
        engine = self.make(program(count=16), duration=1)
        self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(len(engine.operations()), 16)
        self.assertEqual(engine.clock.value, ORIGIN+16)
        self.assertEqual(self.effects(engine), (16, 16, 0))
        self.assertEqual(engine.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0], 32)
        self.assertLessEqual(len(engine.records), 4096)
        self.assertLessEqual(engine.output_bytes, 16*1024*1024)
