"""Durable two-store handoff controls and a separate actual owned worker."""
import hashlib
import json
import os
import threading
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, JournalError
from test_io_service_runs import IoServiceRunTests, business
import hms_qualification.supervisor.io_service_execution as execution
import hms_qualification.supervisor.supervisor_contracts as contracts


class IoServiceExecutionTests(IoServiceRunTests):
    def setUp(self):
        super().setUp()
        IoServiceRunTests.create(self)
        self.original = self.reserve()
        self.bound = execution.BoundQualificationSupervisor(self.parent/'supervisor', create=True)
        self.supervisor_id = self.bound.ledger.authority_id
        self.addCleanup(self.close_bound)
        self.before_business = business(self.runtime)

    def close_bound(self):
        for identifier in list(self.bound._owned): self.bound.stop_owned(identifier)
        self.bound.close()

    def create(self, **options):
        self.service = execution.IoServiceExecutionStore(self.runs, self.bound, create=True,
                                                       owner=self.owner, **options)
        return self.service

    def call(self, **options):
        args = dict(runtime=self.runtime, installed_configuration=self.config); args.update(options)
        return self.service.execute(self.owner, self.config['evaluatorId'], 'run:1', **args)

    def lookup(self):
        return self.service.lookup(self.owner, self.config['evaluatorId'], 'run:1')

    def sizes(self):
        return (self.db.execute('SELECT count(*) FROM iose_handoffs').fetchone()[0],
                self.bound.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone()[0])

    def emit(self, name, value):
        (self.parent/(name+'.json')).write_bytes(canonical(value))

    def at_launch(self, row, bundle):
        self.assertFalse(self.db.in_transaction); self.assertFalse(self.bound.ledger.db.in_transaction)
        value = self.lookup()
        self.assertEqual(value['association']['receipt']['attemptId'], row['record']['attemptId'])
        self.assertEqual(value['association']['receipt']['reservationDigest'], self.original['reservationDigest'])
        self.assertEqual(value['association']['receipt']['requestDigest'], row['record']['requestDigest'])
        self.assertEqual(value['association']['receipt']['supervisorAuthorityId'], self.supervisor_id)
        self.assertEqual(bundle, self.original['preparedRun']['bundle'])
        self.assertEqual(business(self.runtime), self.before_business)
        self.emit('pre-launch-handoff', value)
        return row

    def associated(self):
        self.create()
        with patch.object(self.bound, '_launch', side_effect=self.at_launch) as launch:
            value = self.call()
        self.assertEqual(launch.call_count, 1); self.assertEqual(self.sizes(), (1, 1))
        self.emit('original-association', value)
        return value

    def reopened(self, *, runtime=False):
        self.bound.close()
        self.bound = execution.BoundQualificationSupervisor(self.parent/'supervisor', expected_authority=self.supervisor_id)
        if runtime: IoServiceRunTests.reopen(self)
        self.service = execution.IoServiceExecutionStore(self.runs, self.bound)

    def checkpoint_failure(self, phase):
        self.create()
        def fail(current, value):
            if current == phase:
                self.emit('interruption', dict(phase=current, value=value))
                raise RuntimeError('handoff interruption')
        with patch.object(self.service, '_checkpoint', side_effect=fail), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('unexpected launch')):
            with self.assertRaisesRegex(RuntimeError, 'handoff interruption'): self.call()

    def historical_only(self):
        with patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('relaunch')):
            result = self.call(runtime=None, installed_configuration=None)
        self.emit('replayed-association', result)
        return result

    def test_explicit_mount_creation_shares_journal_and_pins_actual_supervisor(self):
        with self.assertRaises(JournalError): execution.IoServiceExecutionStore(self.runs, self.bound)
        self.create()
        self.assertIs(self.service._db, self.db)
        self.assertEqual(self.lookup(), dict(association=None, attempt=None))
        with self.assertRaisesRegex(JournalError, 'ALREADY_EXISTS'): self.create()

    def test_path_or_claimed_identity_cannot_replace_actual_supervisor_object(self):
        for value in (self.parent/'supervisor', self.supervisor_id,
                      dict(authorityId=self.supervisor_id), lambda: self.bound):
            with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'):
                execution.IoServiceExecutionStore(self.runs, value, create=True, owner=self.owner)
        self.assertIsNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='iose_meta'").fetchone())

    def test_handoff_is_committed_before_any_launch_path(self):
        value = self.associated()
        self.assertEqual(value['attempt']['record']['history'], ['admitted'])
        self.assertEqual(value['association']['receipt']['principal'], 'owner')
        self.assertEqual(self.bound._owned, {})

    def test_exact_association_replay_needs_neither_source_files_nor_planning(self):
        value = self.associated()
        from pathlib import Path
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('source read')), \
             patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('relaunch')):
            self.assertEqual(self.call(runtime=None, installed_configuration=None), value)
        self.assertEqual(self.sizes(), (1, 1))

    def test_before_admission_failure_leaves_no_attempt_or_handoff(self):
        self.checkpoint_failure('before_admission'); self.assertEqual(self.sizes(), (0, 0))
        with patch.object(self.bound, '_launch', side_effect=self.at_launch): self.call()
        self.assertEqual(self.sizes(), (1, 1))

    def test_after_admission_interruption_reconciles_original_without_launch(self):
        self.checkpoint_failure('after_admission'); self.assertEqual(self.sizes(), (0, 1))
        self.reopened(runtime=True); result = self.historical_only()
        self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(result['attempt']['record']['history'], ['admitted', 'interrupted'])

    def test_association_rollback_retains_admission_and_reconciles_once(self):
        self.checkpoint_failure('before_association_commit'); self.assertEqual(self.sizes(), (0, 1))
        result = self.historical_only()
        self.assertEqual(self.sizes(), (1, 1)); self.assertEqual(result['association']['receipt']['sequence'], 1)

    def test_lost_association_commit_reply_never_launches_on_reopen(self):
        self.checkpoint_failure('after_association_commit'); self.assertEqual(self.sizes(), (1, 1))
        before = self.lookup()['association']; self.reopened(runtime=True)
        self.assertEqual(self.historical_only()['association'], before)

    def test_interruption_after_association_before_launch_never_resumes(self):
        self.checkpoint_failure('before_launch'); self.assertEqual(self.sizes(), (1, 1))
        before = self.lookup()['association']; self.reopened()
        self.assertEqual(self.historical_only()['association'], before)

    def test_launch_path_exception_preserves_association_and_does_not_retry(self):
        self.create()
        with patch.object(self.bound, '_launch', side_effect=RuntimeError('launch boundary')):
            with self.assertRaisesRegex(RuntimeError, 'launch boundary'): self.call()
        self.assertEqual(self.sizes(), (1, 1)); before = self.lookup()
        self.assertEqual(self.historical_only(), before)

    def test_configuration_change_preserves_historical_handoff(self):
        old = self.associated()
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        self.assertEqual(self.historical_only(), old)

    def test_session_change_preserves_association_and_original_attempt(self):
        old = self.associated(); self.reopened(runtime=True)
        replay = self.historical_only()
        self.assertEqual(replay['association'], old['association'])
        self.assertEqual(replay['attempt']['record']['attemptId'], old['attempt']['record']['attemptId'])
        self.assertEqual(replay['attempt']['record']['state'], 'interrupted')

    def test_create_lookup_and_replay_require_current_admin_authority(self):
        visitor = Context('visitor', self.owner.deployment)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            execution.IoServiceExecutionStore(self.runs, self.bound, create=True, owner=visitor)
        self.associated()
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            self.service.lookup(visitor, self.config['evaluatorId'], 'run:1')
        self.runtime.registry.grant(self.owner, 'owner', '*', 'admin', enabled=False)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.call()
        self.assertEqual(self.sizes(), (1, 1))

    def test_another_current_admin_resolves_same_original_association(self):
        old = self.associated(); other = Context('other', self.owner.deployment)
        self.runtime.registry.grant(self.owner, other.principal, '*', 'admin')
        with patch.object(self.bound, '_launch', side_effect=AssertionError('relaunch')):
            result = self.service.execute(other, self.config['evaluatorId'], 'run:1')
        self.assertEqual(result, old)

    def test_fresh_configuration_drift_refuses_before_supervisor_admission(self):
        self.create(); self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        with self.assertRaisesRegex(JournalError, 'CONFIGURATION_CHANGED'): self.call()
        self.assertEqual(self.sizes(), (0, 0))

    def test_fresh_session_drift_refuses_before_supervisor_admission(self):
        self.create(); self.reopened(runtime=True)
        with self.assertRaisesRegex(JournalError, 'INPUT_CHANGED'): self.call()
        self.assertEqual(self.sizes(), (0, 0))

    def test_configuration_drift_after_admission_prevents_association_and_launch(self):
        self.create()
        def change(phase, value):
            if phase == 'after_admission':
                self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        with patch.object(self.service, '_checkpoint', side_effect=change), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('launch')):
            with self.assertRaisesRegex(JournalError, 'CONFIGURATION_CHANGED'): self.call()
        self.assertEqual(self.sizes(), (0, 1)); self.historical_only()
        self.assertEqual(self.sizes(), (1, 1))

    def test_authorization_revoked_after_admission_prevents_launch(self):
        self.create()
        def change(phase, value):
            if phase == 'after_admission': self.runtime.registry.grant(self.owner, 'owner', '*', 'admin', enabled=False)
        with patch.object(self.service, '_checkpoint', side_effect=change), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('launch')):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.call()
        self.assertEqual(self.sizes(), (0, 1))

    def test_fresh_source_identity_change_cannot_admit(self):
        self.create()
        with patch.object(contracts, '_IMPORTED_SOURCES', []), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('launch')):
            with self.assertRaises(JournalError): self.call()
        self.assertEqual(self.sizes(), (0, 0))

    def test_preexisting_changed_request_cannot_be_associated(self):
        self.create(); request = json.loads(canonical(self.original['preparedRun']['request']))
        request['limits']['maxStreamBytes'] -= 1; self.bound.ledger.admit(request)
        with self.assertRaisesRegex(JournalError, 'REQUEST_CONFLICT'): self.call()
        self.assertEqual(self.sizes(), (0, 1))

    def test_missing_attempt_after_association_is_not_new_admission(self):
        self.associated(); self.bound.ledger.db.execute('DELETE FROM qs_attempts')
        with patch.object(self.bound.ledger, 'admit', side_effect=AssertionError('readmitted')):
            with self.assertRaisesRegex(JournalError, 'ATTEMPT_MISSING'): self.call()
        self.assertEqual(self.sizes(), (1, 0))

    def test_changed_attempt_id_under_same_request_is_refused(self):
        result = self.associated(); row = result['attempt']['record']
        changed = '0'*32 if row['attemptId'] != '0'*32 else '1'*32
        row = row | {'attemptId': changed}
        self.bound.ledger.db.execute('UPDATE qs_attempts SET id=?,record=?', (changed, canonical(row)))
        with self.assertRaisesRegex(JournalError, 'ATTEMPT_MISMATCH'): self.call()
        self.assertEqual(self.sizes(), (1, 1))

    def test_replacement_supervisor_cannot_take_over_mount(self):
        self.associated(); replacement = execution.BoundQualificationSupervisor(self.parent/'replacement', create=True)
        self.addCleanup(replacement.close)
        with self.assertRaisesRegex(JournalError, 'SUPERVISOR_MISMATCH'):
            execution.IoServiceExecutionStore(self.runs, replacement)
        self.assertEqual(replacement.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (0,))

    def corrupt(self, sql, args=()):
        self.associated(); self.db.execute(sql, args)
        before = hashlib.sha256(canonical([list(row) for row in self.db.execute('SELECT sequence,evaluator,run,hex(receipt) FROM iose_handoffs')])).hexdigest()
        with self.assertRaises(JournalError): self.lookup()
        with self.assertRaises(JournalError): execution.IoServiceExecutionStore(self.runs, self.bound, create=True, owner=self.owner)
        after = hashlib.sha256(canonical([list(row) for row in self.db.execute('SELECT sequence,evaluator,run,hex(receipt) FROM iose_handoffs')])).hexdigest()
        self.assertEqual(before, after); self.emit('corruption-check', dict(before=before, after=after, reset=False))

    def test_noncanonical_handoff_is_retained_and_not_repaired(self):
        self.corrupt("UPDATE iose_handoffs SET receipt=CAST(receipt || ' ' AS BLOB)")

    def test_oversize_handoff_refuses_before_document_parse(self):
        with patch.object(execution, '_document', wraps=execution._document) as parse:
            self.corrupt('UPDATE iose_handoffs SET receipt=?', (b' '*4097,))
        self.assertTrue(parse.call_args_list)
        self.assertTrue(all(len(call.args[0]) <= 4096 for call in parse.call_args_list))

    def test_non_object_handoff_refuses(self):
        self.corrupt('UPDATE iose_handoffs SET receipt=?', (b'[]',))

    def test_added_execution_trigger_refuses(self):
        self.corrupt('CREATE TRIGGER iose_extra AFTER DELETE ON iose_handoffs BEGIN SELECT 1; END')

    def test_temporary_execution_shadow_refuses(self):
        self.associated(); self.db.execute('CREATE TEMP TABLE iose_handoffs(sequence,evaluator,run,receipt)')
        with self.assertRaisesRegex(JournalError, 'SCHEMA'): self.lookup()
        self.emit('shadow-refusal', dict(refused=True, durableRows=self.db.execute('SELECT count(*) FROM main.iose_handoffs').fetchone()[0]))

    def test_missing_mount_tables_with_anchor_never_reinitialize(self):
        self.associated()
        for name in execution._DDL: self.db.execute('DROP TABLE '+name)
        with self.assertRaises(JournalError): execution.IoServiceExecutionStore(self.runs, self.bound, create=True, owner=self.owner)
        self.assertIsNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='iose_meta'").fetchone())
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM reg_meta WHERE key=?', (execution.ANCHOR,)).fetchone())

    def test_reentrant_journal_call_refuses_before_execution_lock(self):
        self.create()
        with self.runtime.journal._transaction():
            with self.assertRaisesRegex(JournalError, 'TRANSACTION_REENTRY'): self.call()
            with self.assertRaisesRegex(JournalError, 'TRANSACTION_REENTRY'):
                execution.IoServiceExecutionStore(self.runs, self.bound)
        self.assertEqual(self.sizes(), (0, 0))

    def test_concurrent_admission_refuses_busy_then_replays_original(self):
        self.create(); ready = threading.Event(); release = threading.Event(); values = []; failures = []
        def checkpoint(phase, value):
            if phase == 'before_admission':
                ready.set(); self.assertTrue(release.wait(10))
        def invoke():
            try: values.append(self.call())
            except BaseException as error: failures.append(error)
        with patch.object(self.service, '_checkpoint', side_effect=checkpoint), patch.object(self.bound, '_launch', side_effect=self.at_launch):
            thread = threading.Thread(target=invoke); thread.start()
            try:
                self.assertTrue(ready.wait(20))
                with self.assertRaisesRegex(JournalError, 'BUSY'): self.call()
            finally: release.set(); thread.join(30)
        self.assertFalse(thread.is_alive()); self.assertEqual(failures, []); self.assertEqual(len(values), 1)
        self.assertEqual(self.historical_only(), values[0]); self.assertEqual(self.sizes(), (1, 1))

    def test_recovery_archives_unlaunched_original_without_signaling_pid(self):
        self.checkpoint_failure('after_association_commit'); self.reopened()
        with patch.object(execution.signal, 'pidfd_send_signal', side_effect=AssertionError('stored PID signal')):
            result = self.service.recover(self.owner, self.config['evaluatorId'], 'run:1')
        self.assertEqual(result['attempt']['record']['state'], 'archived')
        self.assertIsNone(result['attempt']['returnBytes']); self.assertFalse(result['attempt']['record']['archive']['transportComplete'])
        self.assertEqual(self.historical_only(), result)


class IoServiceExecutionProcessTests(IoServiceExecutionTests):
    def test_owned_group_persists_handoff_before_launch_and_replays_after_drift(self):
        from hms.pat_io_group_history import inspect_io_group
        from hms.pat_io_run_bundle import parse_io_run_bundle
        import hms_qualification.supervisor.bundle_io as bundle_io
        self.create(); phases = []; saved = self.original['preparedRun']
        self.emit('source-business-before', self.before_business)
        self.emit('run-reservation', {k:self.original[k] for k in ('reservation', 'reservationDigest')})
        self.emit('supervisor-authority', dict(authorityId=self.supervisor_id))
        def checkpoint(phase, row):
            phases.append(phase)
            if phase == 'launching':
                joined = self.lookup()
                self.assertEqual(joined['association']['receipt']['attemptId'], row['record']['attemptId'])
                self.assertEqual(joined['association']['receipt']['requestDigest'], saved['requestDigest'])
                fd = execution.supervision._directory(self.bound.ledger.fd, row['record']['attemptId'])
                try: self.assertEqual(bundle_io.load_bundle(fd, saved['request']), saved['bundle'])
                finally: os.close(fd)
                self.emit('launching-handoff', joined)
        with patch.object(self.bound, '_checkpoint', side_effect=checkpoint):
            result = self.call()
        row = result['attempt']; archive = row['record']['archive']
        self.emit('worker-archive', dict(association=result['association'], record=row['record'], phases=phases))
        self.assertEqual(row['record']['state'], 'archived'); self.assertTrue(archive['transportComplete'], archive)
        self.assertEqual(contracts.document(row['returnBytes'])['status'], 'captured')
        self.assertEqual(phases, ['admitted', 'launching', 'spawned', 'producer_settled', 'archived'])
        output = self.parent/'supervisor'/row['record']['attemptId']/'output'
        files = {p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
        parsed = parse_io_run_bundle(saved['bundle']['header'], saved['bundle']['documents'],
            expected_context=saved['request']['context'], expected_bundle_digest=saved['bundle']['bundleDigest'])
        checked = inspect_io_group(files, expected_inputs=parsed['expected_inputs'], expected_cases=parsed['expected_cases'])
        self.assertTrue(checked['summary']['independentOutcomeChecked']); self.assertEqual(len(checked['inspections']), 30)
        self.assertFalse(checked['summary']['qualificationPassed'])
        folder = self.parent/'inspection'; folder.mkdir(mode=0o700)
        (folder/'summary.json').write_bytes(canonical(checked['summary']))
        for i, value in enumerate(checked['inspections']): (folder/('case-%02d.json'%i)).write_bytes(canonical(value))
        self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        self.reopened(runtime=True)
        with patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')), \
             patch.object(self.bound, '_launch', side_effect=AssertionError('relaunch')):
            replay = self.call(runtime=None, installed_configuration=None)
        self.assertEqual(replay, result); self.assertEqual(self.sizes(), (1, 1))
        self.assertEqual(business(self.runtime), self.before_business)
        self.emit('handoff-replay-checks', dict(attemptId=row['record']['attemptId'],
            reservationDigest=self.original['reservationDigest'], associationDigest=result['association']['receiptDigest'],
            supervisorAuthorityId=self.supervisor_id, exactReplayAfterDrift=True,
            completeCases=30, oneWorkerLaunched=True, sourceEffectsUnchanged=True, qualificationPassed=False))
