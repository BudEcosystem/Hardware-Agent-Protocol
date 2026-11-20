"""Durable run input identity, retained refusal fixtures and original worker."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, JournalError
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_io_service_configuration import configuration
from test_io_service_authority import runtime_at, business
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_io_supervisor_process import IoSupervisorProcessTests
import hms_qualification.supervisor.io_services as services
import hms_qualification.supervisor.io_service_store as config_store
import hms_qualification.supervisor.io_service_runs as run_store
import hms_qualification.supervisor.supervisor_contracts as contracts
import hms_qualification.supervisor.qualification_supervisor as supervision


class IoServiceRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = normalize_installation(installation())
        cls.config = configuration(cls.document, bindings(cls.document))

    def setUp(self):
        self.parent = Path(os.environ['TMPDIR']) / self._testMethodName; self.parent.mkdir(mode=0o700)
        self.runtime = runtime_at(self.parent / 'runtime', self.document)
        self.addCleanup(lambda: self.runtime.close())
        self.owner = Context('owner', 'simulation:io-hub'); self.db = self.runtime.journal._db
        self.configurations = config_store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry, create=True, owner=self.owner)
        self.configuration_receipt = self.configurations.configure(self.owner, 'config:1', self.config, expected_revision=0, runtime=self.runtime)

    def create(self, **options):
        self.runs = run_store.IoServiceRunStore(self.configurations, create=True, owner=self.owner, **options)
        return self.runs

    def reserve(self, run='run:1', candidate=None, **options):
        args = dict(expected_configuration_receipt_digest=self.configuration_receipt['receiptDigest'],
                    runtime=self.runtime, installed_configuration=self.config); args.update(options)
        return self.runs.reserve(self.owner, self.config['evaluatorId'], run,
                                program(literal=True) if candidate is None else candidate, **args)

    def lookup(self, run='run:1'):
        return self.runs.lookup(self.owner, self.config['evaluatorId'], run)

    def reopen(self):
        self.runtime.close(); self.runtime = runtime_at(self.parent / 'runtime', self.document, create=False)
        self.db = self.runtime.journal._db
        self.configurations = config_store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry)
        self.runs = run_store.IoServiceRunStore(self.configurations)

    def counts(self):
        return [self.db.execute('SELECT count(*) FROM ' + name).fetchone()[0] for name in ('iosr_runs', 'iosr_documents')]

    def fingerprint(self):
        rows = []
        for schema in ('sqlite_master', 'sqlite_temp_master'):
            rows.extend([schema, list(row)] for row in self.db.execute("SELECT name,type,tbl_name,sql FROM " + schema + " WHERE name GLOB 'iosr_*' OR tbl_name GLOB 'iosr_*' ORDER BY name"))
        for name in run_store._DDL:
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (name,)).fetchone():
                rows.append([name, [[{'sha256': hashlib.sha256(v).hexdigest(), 'bytes': len(v)} if type(v) is bytes else v for v in row]
                    for row in self.db.execute('SELECT * FROM main.' + name + ' ORDER BY 1,2')]])
        rows.append(['anchor', [list(row) for row in self.db.execute('SELECT * FROM reg_meta WHERE key=?', (run_store.ANCHOR,))]])
        return hashlib.sha256(canonical(rows)).hexdigest()

    def corrupt(self, statement, args=()):
        self.create(); original = self.reserve()
        (self.parent / 'original-reservation.json').write_bytes(canonical(original['reservation']))
        (self.parent / 'original-request.json').write_bytes(canonical(original['preparedRun']['request']))
        self.db.execute(statement, args); before = self.fingerprint()
        with self.assertRaises(JournalError): self.lookup()
        with self.assertRaises(JournalError): run_store.IoServiceRunStore(self.configurations, create=True, owner=self.owner)
        after = self.fingerprint(); self.assertEqual(before, after)
        (self.parent / 'corruption-check.json').write_bytes(canonical(dict(before=before, after=after, restored=False)))

    def test_creation_is_explicit_and_uses_the_existing_connection(self):
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'SCHEMA'): run_store.IoServiceRunStore(self.configurations)
        with patch.object(sqlite3, 'connect', side_effect=AssertionError('opened SQL')):
            self.create(); other = run_store.IoServiceRunStore(self.configurations)
            self.assertIsNone(other.lookup(self.owner, self.config['evaluatorId'], 'run:absent'))
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'ALREADY_EXISTS'): self.create()
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'REOPEN_OPTIONS'):
            run_store.IoServiceRunStore(self.configurations, max_runs=32)

    def test_reopen_replay_retains_complete_original_inputs_without_source_io(self):
        self.create(); original = self.reserve(); self.reopen()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('source read')), \
             patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('opened SQL')):
            self.assertEqual(self.reserve(runtime=None, installed_configuration=None), original)
            self.assertEqual(self.lookup(), original)
        self.assertEqual(self.counts(), [1, len(original['preparedRun']['bundle']['documents'])])
        current = self.runtime.registry.describe(self.owner, 'sim:gpio5')['presence']['session']
        old = json.loads(original['preparedRun']['bundle']['documents']['inputs/descriptor.json'])['endpointSession']
        self.assertNotEqual(current, old)

    def test_configuration_change_preserves_old_run_and_refuses_old_pin_for_new_run(self):
        self.create(); original = self.reserve()
        new_config = self.config | {'revision': 2}
        new_receipt = self.configurations.configure(self.owner, 'config:2', new_config, expected_revision=1, runtime=self.runtime)
        with patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')):
            self.assertEqual(self.reserve(runtime=None, installed_configuration=None), original)
            with self.assertRaisesRegex(run_store.IoServiceRunError, 'CONFIGURATION_CHANGED'): self.reserve(run='run:2')
        fresh = self.reserve(run='run:2', expected_configuration_receipt_digest=new_receipt['receiptDigest'], installed_configuration=new_config)
        self.assertEqual(fresh['reservation']['configurationSequence'], 2)
        self.assertEqual(fresh['reservation']['previousReservationDigest'], original['reservationDigest'])

    def test_changed_candidate_or_configuration_same_key_refuses_before_planning(self):
        self.create(); self.reserve()
        with patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')):
            with self.assertRaisesRegex(run_store.IoServiceRunError, 'KEY_CONFLICT'): self.reserve(candidate=program(pwm=True, literal=True))
            with self.assertRaisesRegex(run_store.IoServiceRunError, 'KEY_CONFLICT'):
                self.reserve(expected_configuration_receipt_digest='sha256:' + '0' * 64)
        self.assertEqual(self.counts()[0], 1)

    def test_current_administrator_can_resolve_shared_logical_run_key(self):
        self.create(); original = self.reserve(); other = Context('other-admin', self.owner.deployment)
        self.runtime.registry.grant(self.owner, other.principal, '*', 'admin')
        replay = self.runs.reserve(other, self.config['evaluatorId'], 'run:1', program(literal=True),
            expected_configuration_receipt_digest=self.configuration_receipt['receiptDigest'])
        self.assertEqual(replay, original); self.assertEqual(replay['reservation']['principal'], 'owner')

    def test_current_authorization_is_required_for_create_lookup_and_replay(self):
        visitor = Context('visitor', self.owner.deployment)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            run_store.IoServiceRunStore(self.configurations, create=True, owner=visitor)
        self.create(); self.reserve()
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.runs.lookup(visitor, self.config['evaluatorId'], 'run:1')
        self.runtime.registry.grant(self.owner, 'owner', '*', 'admin', enabled=False)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.reserve()

    def test_cross_authority_runtime_cannot_supply_fresh_run(self):
        self.create(); other = runtime_at(self.parent / 'runtime-other', self.document); self.addCleanup(other.close)
        with self.assertRaisesRegex(JournalError, 'AUTHORITY_MISMATCH'): self.reserve(runtime=other)
        self.assertEqual(self.counts(), [0, 0])

    def test_before_commit_failure_rolls_back_run_and_all_input_documents(self):
        self.create()
        def fail(phase, value):
            if phase == 'before_commit': raise RuntimeError('commit fault')
        with patch.object(self.runs, '_checkpoint', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'commit fault'): self.reserve()
        self.assertEqual(self.counts(), [0, 0]); self.reopen(); self.assertIsNone(self.lookup())
        self.assertEqual(self.reserve()['reservation']['sequence'], 1)

    def test_lost_reply_after_commit_replays_exact_reservation_on_reopen(self):
        self.create(); values = []
        def fail(phase, value):
            if phase == 'after_commit': values.append(value); raise RuntimeError('lost reply')
        with patch.object(self.runs, '_checkpoint', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'lost reply'): self.reserve()
        self.reopen()
        with patch.object(self.configurations, 'prepare_run', side_effect=AssertionError('replan')):
            self.assertEqual(self.reserve(), values[0])

    def race(self, changed):
        self.create(); gate = threading.Barrier(2); values = []; failures = []
        def invoke(index):
            try:
                gate.wait(timeout=10); values.append(self.reserve(candidate=program(pwm=bool(changed and index), literal=True)))
            except BaseException as error: failures.append(error)
        threads = [threading.Thread(target=invoke, args=(i,)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads)); self.assertEqual(self.counts()[0], 1)
        return values, failures

    def test_concurrent_exact_reservations_keep_one_input_set(self):
        values, failures = self.race(False); self.assertEqual(failures, [])
        self.assertEqual(len(values), 2); self.assertEqual(values[0], values[1])

    def test_concurrent_changed_same_key_has_one_reservation_and_one_conflict(self):
        values, failures = self.race(True); self.assertEqual(len(values), 1); self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], run_store.IoServiceRunError); self.assertIn('KEY_CONFLICT', str(failures[0]))

    def test_lowered_run_capacity_still_allows_exact_replay(self):
        self.create(max_runs=1); original = self.reserve()
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'CAPACITY'): self.reserve(run='run:2')
        self.assertEqual(self.reserve(), original)

    def test_lowered_byte_capacity_commits_no_partial_input_set(self):
        self.create(max_data_bytes=2048)
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'CAPACITY'): self.reserve()
        self.assertEqual(self.counts(), [0, 0])

    def test_returned_mutation_cannot_change_retained_request_or_documents(self):
        self.create(); first = self.reserve(); retained = self.lookup()
        first['reservation']['sequence'] = 99; first['preparedRun']['request']['limits']['maxArchives'] = 1
        first['preparedRun']['bundle']['documents'].clear()
        self.assertEqual(self.lookup(), retained)

    def test_source_drift_refuses_new_run_without_breaking_historical_replay(self):
        self.create(); original = self.reserve()
        with patch.object(services, 'prepare_service_pin', side_effect=services.IoServiceError('PIN_CHANGED')):
            self.assertEqual(self.reserve(), original)
            with self.assertRaisesRegex(JournalError, 'PIN_CHANGED'): self.reserve(run='run:2')
        self.assertEqual(self.counts()[0], 1)

    def test_configuration_changes_after_preparation_prevent_commit(self):
        self.create()
        def change(phase, value):
            if phase == 'prepared': self.configurations.configure(self.owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=self.runtime)
        with patch.object(self.runs, '_checkpoint', side_effect=change):
            with self.assertRaisesRegex(run_store.IoServiceRunError, 'CONFIGURATION_CHANGED'): self.reserve()
        self.assertEqual(self.counts(), [0, 0])

    def test_session_changes_after_preparation_prevent_commit(self):
        self.create()
        def change(phase, value):
            if phase == 'prepared': self.runtime.registry.report_presence('sim:gpio5', adapter_id='io:routeA', endpoint_session='session:changed', ttl_ms=3000)
        with patch.object(self.runs, '_checkpoint', side_effect=change):
            with self.assertRaisesRegex(run_store.IoServiceRunError, 'AUTHORITY_CHANGED'): self.reserve()
        self.assertEqual(self.counts(), [0, 0])

    def test_reservation_performs_no_device_effects_and_claims_no_execution(self):
        self.create(); before = business(self.runtime); value = self.reserve()
        self.assertEqual(business(self.runtime), before)
        self.assertNotIn('executionStatus', value); self.assertNotIn('passed', value['reservation'])
        self.assertEqual(value['preparedRun']['requestDigest'], value['reservation']['requestDigest'])
        self.assertEqual(value['reservation']['configurationReceiptDigest'], self.configuration_receipt['receiptDigest'])
        (self.parent / 'authority-business.json').write_bytes(canonical(before))

    def test_missing_document_refuses_without_reconstruction(self):
        self.corrupt("DELETE FROM iosr_documents WHERE path='inputs/descriptor.json'")

    def test_changed_input_bytes_refuse_and_remain_retained(self):
        self.corrupt("UPDATE iosr_documents SET body=? WHERE path='inputs/descriptor.json'", (b'{}',))

    def test_oversized_input_document_refuses_before_payload_read(self):
        self.corrupt("UPDATE iosr_documents SET body=? WHERE path='inputs/descriptor.json'", (b' ' * 65537,))

    def test_non_blob_request_refuses_and_remains_retained(self): self.corrupt("UPDATE iosr_runs SET request='{}'")
    def test_non_object_receipt_refuses_and_remains_retained(self): self.corrupt('UPDATE iosr_runs SET receipt=?', (b'[]',))
    def test_wrong_configuration_reference_refuses_and_remains_retained(self): self.corrupt('UPDATE iosr_runs SET configuration_sequence=128')
    def test_partial_schema_refuses_without_recreation(self): self.corrupt('DROP TABLE iosr_documents')
    def test_added_trigger_refuses_before_any_further_reservation(self): self.corrupt('CREATE TRIGGER iosr_extra AFTER INSERT ON iosr_runs BEGIN SELECT 1; END')
    def test_temp_shadow_refuses_before_reading_its_contents(self): self.corrupt('CREATE TEMP TABLE iosr_runs(sequence INTEGER)')

    def test_metadata_limit_tampering_cannot_widen_capacity(self):
        self.create(max_runs=1); self.reserve()
        meta = json.loads(self.db.execute('SELECT record FROM iosr_meta').fetchone()[0]); meta['maxRuns'] = 32
        self.db.execute('UPDATE iosr_meta SET record=?', (canonical(meta),)); before = self.fingerprint()
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'INVALID_RETAINED'): self.lookup()
        self.assertEqual(self.fingerprint(), before)

    def test_all_run_tables_missing_with_anchor_are_never_recreated(self):
        self.create(); original = self.reserve()
        (self.parent / 'original-reservation.json').write_bytes(canonical(original['reservation']))
        for name in run_store._DDL: self.db.execute('DROP TABLE ' + name)
        before = self.fingerprint()
        with self.assertRaisesRegex(run_store.IoServiceRunError, 'SCHEMA'): self.create()
        self.assertEqual(self.fingerprint(), before)


class IoReservedProcessTests(IoSupervisorProcessTests):
    @classmethod
    def setUpClass(cls):
        cls.document = normalize_installation(installation())
        cls.config = configuration(cls.document, bindings(cls.document))

    def root(self, label='root'):
        result = self.parent / label; result.mkdir(mode=0o700); return result

    def test_reserved_owned_group_replays_after_config_and_session_change(self):
        self.parent = Path(os.environ['TMPDIR']) / self._testMethodName; self.parent.mkdir(mode=0o700)
        owner = Context('owner', 'simulation:io-hub'); runtime = runtime_at(self.parent / 'runtime', self.document)
        try:
            configs = config_store.IoServiceConfigurationStore(runtime.journal, runtime.registry, create=True, owner=owner)
            receipt = configs.configure(owner, 'config:1', self.config, expected_revision=0, runtime=runtime)
            run_store.IoServiceRunStore(configs, create=True, owner=owner)
        finally: runtime.close()
        runtime = runtime_at(self.parent / 'runtime', self.document, create=False)
        try:
            configs = config_store.IoServiceConfigurationStore(runtime.journal, runtime.registry); runs = run_store.IoServiceRunStore(configs)
            retained = runs.reserve(owner, self.config['evaluatorId'], 'run:reserved-owned', program(literal=True),
                expected_configuration_receipt_digest=receipt['receiptDigest'], runtime=runtime, installed_configuration=self.config)
            before = business(runtime); self.prepared = retained['preparedRun']
            self.bundle, self.request = self.prepared['bundle'], self.prepared['request']; self.context = self.request['context']
            fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for name, body in [('service-configuration.json', self.prepared['configuration']), ('service-pin.json', self.prepared['servicePin']),
                    ('service-configuration-receipt.json', canonical(receipt)), ('service-request-digest.json', canonical(dict(requestDigest=self.prepared['requestDigest']))),
                    ('run-reservation.json', canonical(dict(reservation=retained['reservation'], reservationDigest=retained['reservationDigest']))),
                    ('authority-business.json', canonical(before))]: contracts.write_file(fd, name, body)
            finally: os.close(fd)
        finally: runtime.close()
        IoSupervisorProcessTests.test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays(self)
        runtime = runtime_at(self.parent / 'runtime', self.document, create=False)
        try:
            configs = config_store.IoServiceConfigurationStore(runtime.journal, runtime.registry); runs = run_store.IoServiceRunStore(configs)
            new_receipt = configs.configure(owner, 'config:2', self.config | {'revision': 2}, expected_revision=1, runtime=runtime)
            with patch.object(configs, 'prepare_run', side_effect=AssertionError('replanned')):
                replay = runs.reserve(owner, self.config['evaluatorId'], 'run:reserved-owned', program(literal=True),
                    expected_configuration_receipt_digest=receipt['receiptDigest'])
            self.assertEqual(replay, retained); self.assertEqual(business(runtime), before)
            supervisor = supervision.QualificationSupervisor(self.parent / 'supervisor')
            try:
                with patch.object(supervision, 'validate_fresh', side_effect=AssertionError('replanned')):
                    result = supervisor.execute(replay['preparedRun']['request'])
                self.assertEqual(result['record']['state'], 'archived')
                self.assertEqual(supervisor.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (1,))
            finally: supervisor.close()
            (self.parent / 'run-replay-checks.json').write_bytes(canonical(dict(reservationDigest=retained['reservationDigest'],
                requestDigest=result['record']['requestDigest'], attemptId=result['record']['attemptId'],
                activeConfigurationReceiptDigest=new_receipt['receiptDigest'], originalConfigurationReceiptDigest=receipt['receiptDigest'],
                replayWithoutPlanning=True, sameSupervisorAttempt=True, sourceEffectsUnchanged=True)))
        finally: runtime.close()
