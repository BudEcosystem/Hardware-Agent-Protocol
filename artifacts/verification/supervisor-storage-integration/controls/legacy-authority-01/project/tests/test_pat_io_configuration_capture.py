"""Actual private runtime configuration capture; no authorization attestation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms.pat_contracts import PatError
from hms import pat_io_trials as trials
from hms.pat_io_configuration_capture import ConfiguredIoTrialEngine, TABLES, PUBLIC_META
from hms.pat_io_transcript import inspect_transcript
from hms.pat_io_board_history import inspect_board_history
from hms.pat_io_operation_history import inspect_operation_history
from hms.pat_io_procedure_history import inspect_procedure_history
from hms.pat_io_correspondence import inspect_pat_correspondence
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_contracts import program, descriptor


class IoConfigurationCaptureTests(unittest.TestCase):
    def setUp(self):
        self.engines = []
        self.verify_legacy = False
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
                    self.assert_pairing(engine)
                    if self.verify_legacy:
                        files = {r['path']: (engine.record_directory/r['path']).read_bytes() for r in engine.records}
                        setup = {'artifact': engine.artifact, 'installation': engine.document,
                                 'original_descriptor': engine.original_descriptor, 'static_contract': engine.contract}
                        for check, flag in [(inspect_transcript, 'serializationChecked'),
                            (inspect_board_history, 'boardHistoryChecked'),
                            (inspect_operation_history, 'operationHistoryChecked'),
                            (inspect_procedure_history, 'procedureHistoryChecked'),
                            (inspect_pat_correspondence, 'patCorrespondenceChecked')]:
                            result = check(engine.records, files, expected_setup=setup)
                            self.assertTrue(result[flag]); self.assertFalse(result['qualificationPassed'])
            except BaseException as error:
                errors.append(error)
            finally:
                try: engine.close()
                except BaseException as error: errors.append(error)
            (self.workspace / ('engine-%d.json' % index)).write_text(json.dumps({
                'testId': self.id(), 'directory': str(engine.directory), 'report': report,
                'records': engine.records, 'configuration': engine.configuration_manifest(),
                'closed': engine.runtime is None,
                'cleanupErrors': [type(error).__name__ + ':' + str(error) for error in errors]}, indent=2)+'\n')
        if errors: raise errors[0]

    def make(self, *, count=1, pwm=False, submit=True):
        directory = self.workspace/'trial-0'; directory.mkdir(mode=0o700)
        engine = ConfiguredIoTrialEngine(directory, program(count=count, pwm=pwm), self.document,
                                         descriptor(self.document, pwm=pwm))
        self.engines.append(engine); engine.lower({'duration': 1})
        if submit: engine.submit()
        return engine

    def docs(self, engine):
        return {r['path']: json.loads((engine.directory/'configuration'/r['path']).read_bytes())
                for r in engine.configuration_records}

    def snapshot(self, engine):
        docs = self.docs(engine)
        return docs[engine.configuration_manifest()['snapshots'][-1]['configuration']['path']]['value']

    def table(self, engine, name, snapshot=None):
        docs = self.docs(engine); snapshot = snapshot or self.snapshot(engine)
        table, = [t for t in snapshot['tables'] if t['table'] == name]
        return [[c['value'] for c in row] for r in table['pages'] for row in docs[r['path']]['value']['rows']]

    def assert_pairing(self, engine):
        docs = self.docs(engine); pairs = engine.configuration_manifest()['snapshots']
        expected = [r for r in engine.records if json.loads((engine.record_directory/r['path']).read_bytes())['kind'] == 'checkpoint']
        self.assertEqual([p['checkpoint'] for p in pairs], expected)
        for pair in pairs:
            snapshot = docs[pair['configuration']['path']]['value']
            cp = json.loads((engine.record_directory/pair['checkpoint']['path']).read_bytes())['value']
            self.assertEqual(snapshot['checkpoint'], pair['checkpoint'])
            for key in ('phase', 'label', 'wallMs', 'monotonicMs', 'clockEpoch'):
                self.assertEqual(snapshot[key], cp[key])
            self.assertEqual({t['table'] for t in snapshot['tables']}, set(TABLES))
            self.assertEqual(len(snapshot['tables']), len(TABLES))

    def effects(self, engine, instance='sim:gpio5'):
        return tuple(engine.runtime.io_board.db.execute('SELECT activations,completed,canceled FROM io_effects WHERE instance=?', (instance,)).fetchone())

    def revoke_invoke(self, engine):
        registry, owner = engine.runtime.registry, engine.owner
        registry.grant(owner, owner.principal, 'sim:gpio5', 'read')
        registry.grant(owner, owner.principal, '*', 'admin', enabled=False)

    def test_configuration_gpio_retains_all_tables_and_legacy_semantics(self):
        engine = self.make(count=2); self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(self.effects(engine), (2, 2, 0))
        self.assertEqual({r[0] for r in self.table(engine, 'reg_instances')},
                         {r['instanceId'] for r in self.document['handlers']})
        self.verify_legacy = True

    def test_configuration_pwm_retains_typed_bindings_and_routes(self):
        engine = self.make(pwm=True); engine.drive('procedure'); engine.drive('adapters')
        self.assertEqual(self.effects(engine, 'sim:pwm5'), (1, 0, 0))
        self.assertEqual(len(self.table(engine, 'reg_bindings')), 4)
        self.assertEqual({r[1] for r in self.table(engine, 'reg_resource_instances')}, {'io:routeA', 'io:routeB'})
        self.assertTrue(all(json.loads(r[1])['execution']['actions'] for r in self.table(engine, 'reg_types')))
        self.assertEqual(engine.finish()['executionState'], 'completed')

    def test_configuration_reopen_retains_session_and_epoch_changes(self):
        engine = self.make(); engine.drive('procedure'); engine.drive('adapters')
        before = self.snapshot(engine); old_sessions = self.table(engine, 'reg_session_history', before)
        engine.reopen(); after = self.snapshot(engine)
        self.assertEqual(after['ownerEpoch'], before['ownerEpoch']+1)
        self.assertEqual(after['authorityId'], before['authorityId'])
        self.assertNotEqual(after['session'], before['session'])
        self.assertTrue(set(map(tuple, old_sessions)) < set(map(tuple, self.table(engine, 'reg_session_history'))))
        self.assertEqual({r[1] for r in self.table(engine, 'reg_presence')}, {after['session']})
        engine.drive('adapters'); engine.cancel(); engine.drive()
        self.assertEqual(self.effects(engine), (1, 0, 1))

    def test_configuration_revoked_grant_prevents_parent_admission(self):
        engine = self.make(submit=False); self.revoke_invoke(engine)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): engine.submit()
        self.assertIsNone(engine.procedure_id); self.assertFalse(engine.operations())
        self.assertEqual(self.effects(engine), (0, 0, 0))
        self.assertEqual(self.table(engine, 'reg_grants'), [[engine.owner.principal, engine.owner.deployment, 'sim:gpio5', 'read']])

    def test_configuration_revoked_grant_after_admission_prevents_effect(self):
        engine = self.make(); engine.drive('procedure'); self.revoke_invoke(engine)
        engine.drive('adapters'); op, = engine.operations()
        self.assertEqual(op['state'], 'rejected_before_dispatch'); self.assertFalse(op['claims'])
        self.assertFalse(op['may_have_acted']); self.assertIsNone(engine.runtime.io_board.receipt(op['id']))
        self.assertEqual(self.effects(engine), (0, 0, 0))
        self.assertFalse(any(r[-1] == 'admin' for r in self.table(engine, 'reg_grants')))

    def test_configuration_and_execution_share_record_ceiling(self):
        engine = self.make(); before = engine.configuration_manifest()
        with patch.object(trials, 'MAX_RECORDS', before['combinedRecords']):
            with self.assertRaisesRegex(PatError, 'PAT_IO_CONFIGURATION_EVIDENCE_LIMIT'): engine.capture('test_final')
        self.assertEqual(engine.configuration_manifest(), before)

    def test_configuration_and_execution_share_byte_ceiling(self):
        engine = self.make(); before = engine.configuration_manifest()
        with patch.object(trials, 'MAX_OUTPUT_BYTES', before['combinedBytes']):
            with self.assertRaisesRegex(PatError, 'PAT_IO_CONFIGURATION_EVIDENCE_LIMIT'): engine.capture('test_final')
        self.assertEqual(engine.configuration_manifest(), before)

    def test_configuration_unchanged_pages_and_resolver_are_reused(self):
        engine = self.make(); before = self.snapshot(engine); count = len(engine.configuration_records)
        engine.capture('test_final'); after = self.snapshot(engine)
        self.assertEqual(before['tables'], after['tables']); self.assertEqual(before['resolver'], after['resolver'])
        self.assertEqual(len(engine.configuration_records), count+1)

    def test_configuration_open_transaction_refuses_without_output(self):
        engine = self.make(); before = engine.configuration_manifest(); db = engine.runtime.journal._db
        db.execute('BEGIN')
        try:
            with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_UNCOMMITTED_CAPTURE'): engine.capture('test_final')
        finally:
            db.execute('ROLLBACK')  # Empty test transaction; no business writes.
        self.assertEqual(engine.configuration_manifest(), before)

    def test_configuration_both_locks_remain_held_and_capture_is_read_only(self):
        engine = self.make(); original = engine._configuration_table; seen = []
        db, board = engine.runtime.journal._db, engine.runtime.io_board.db
        before = (db.total_changes, board.total_changes)
        def inspect(*args):
            self.assertTrue(engine.runtime.journal._mutex._is_owned())
            self.assertTrue(engine.runtime.io_board.lock._is_owned())
            self.assertFalse(db.in_transaction or board.in_transaction); seen.append(args[1])
            return original(*args)
        with patch.object(engine, '_configuration_table', side_effect=inspect): engine.capture('test_final')
        self.assertEqual(seen, list(TABLES)); self.assertEqual((db.total_changes, board.total_changes), before)

    def test_configuration_excludes_cursor_secret_and_retains_registration_identity(self):
        engine = self.make(); secret = engine.runtime.journal._db.execute("SELECT value FROM reg_meta WHERE key='cursor_key'").fetchone()[0]
        self.assertEqual({r[0] for r in self.table(engine, 'reg_meta')}, set(PUBLIC_META))
        for directory in ('records', 'configuration'):
            self.assertTrue(all(secret.encode() not in p.read_bytes() for p in (engine.directory/directory).iterdir()))
        resolver = self.docs(engine)[self.snapshot(engine)['resolver']['path']]['value']; registration, = resolver['registrations']
        identity = {'profile': resolver['resolverProfile'], 'installationDigest': registration['installationDigest'],
                    'driverDigest': registration['driverDigest'], 'registrations': [registration]}
        self.assertEqual(resolver['registrationIdentity'], 'sha256:'+hashlib.sha256(b'HMS-PAT-IO-BINDING-REGISTRATIONS-v1\0'+canonical(identity)).hexdigest())

    def test_configuration_sixteen_steps_stay_within_original_shared_limits(self):
        engine = self.make(count=16); self.assertEqual(engine.finish()['executionState'], 'completed')
        self.assertEqual(self.effects(engine), (16, 16, 0)); self.assertEqual(engine.clock.value, trials.ORIGIN+16)
        manifest = engine.configuration_manifest()
        self.assertLessEqual(manifest['combinedRecords'], 4096)
        self.assertLessEqual(manifest['combinedBytes'], 16*1024*1024)
        self.assertFalse(manifest['configurationAttested']); self.assertFalse(manifest['qualificationPassed'])
