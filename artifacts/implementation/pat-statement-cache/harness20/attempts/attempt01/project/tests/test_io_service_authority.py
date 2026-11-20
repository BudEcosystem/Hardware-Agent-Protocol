"""Durable authority configuration, refusal retention and actual owned worker."""
import copy
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
from hms.synthetic_io_runtime import IoRuntime
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_io_service_configuration import configuration
from test_io_supervisor_process import IoSupervisorProcessTests
import hms_qualification.supervisor.io_services as services
import hms_qualification.supervisor.io_service_store as store
import hms_qualification.supervisor.supervisor_contracts as contracts


def runtime_at(path, document, *, create=True):
    return IoRuntime(path, create=create, owner=Context('owner', 'simulation:io-hub') if create else None,
        installation=document, wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000,
        storage_profile='hms.sqlite.compact/0.1')


def business(runtime):
    journal = runtime.journal._db; board = runtime.io_board.db
    return dict(authority={name: [list(row) for row in journal.execute('SELECT * FROM ' + name)]
                          for name in ('operations', 'claims', 'events', 'replay_keys')},
                board={name: [list(row) for row in board.execute('SELECT * FROM ' + name)]
                       for name in ('io_effects', 'io_owners', 'io_receipts', 'io_receipt_versions')})


class IoServiceAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = normalize_installation(installation())
        cls.config = configuration(cls.document, bindings(cls.document))

    def setUp(self):
        self.parent = Path(os.environ['TMPDIR']) / self._testMethodName
        self.parent.mkdir(mode=0o700)
        self.runtime = runtime_at(self.parent / 'runtime', self.document)
        self.addCleanup(lambda: self.runtime.close())
        self.owner = Context('owner', 'simulation:io-hub')
        self.db = self.runtime.journal._db

    def create(self, **options):
        self.store = store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry,
            create=True, owner=self.owner, **options)
        return self.store

    def configure(self, config=None, key='config:1', prior=0):
        return self.store.configure(self.owner, key, self.config if config is None else config,
            expected_revision=prior, runtime=self.runtime)

    def prepare(self, **options):
        args = dict(runtime=self.runtime, installed_configuration=self.config); args.update(options)
        return self.store.prepare_run(self.owner, self.config['evaluatorId'], program(literal=True), 'run:authority', **args)

    def reopen(self):
        self.runtime.close()
        self.runtime = runtime_at(self.parent / 'runtime', self.document, create=False)
        self.db = self.runtime.journal._db
        self.store = store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry)

    def counts(self):
        return [self.db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                for name in ('iosc_versions', 'iosc_mutations', 'iosc_heads')]

    def fingerprint(self):
        rows = []
        for schema in ('sqlite_master', 'sqlite_temp_master'):
            rows.extend([schema, list(row)] for row in self.db.execute(
                "SELECT name,type,tbl_name,sql FROM " + schema + " WHERE name GLOB 'iosc_*' OR tbl_name GLOB 'iosc_*' ORDER BY name"))
        for name in store._DDL:
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (name,)).fetchone():
                rows.append([name, [[{'blobSha256': hashlib.sha256(v).hexdigest(), 'bytes': len(v)} if type(v) is bytes else v
                    for v in row] for row in self.db.execute('SELECT * FROM main.' + name + ' ORDER BY 1')]])
        rows.append(['anchor', [list(row) for row in self.db.execute('SELECT * FROM reg_meta WHERE key=?', (store.ANCHOR,))]])
        return hashlib.sha256(canonical(rows)).hexdigest()

    def corrupt(self, statement, args=()):
        self.create(); original = self.configure()
        (self.parent / 'original-receipt.json').write_bytes(canonical(original))
        self.db.execute(statement, args)
        before = self.fingerprint()
        with self.assertRaises(JournalError): self.store.read(self.owner, self.config['evaluatorId'])
        with self.assertRaises(JournalError):
            store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry, create=True, owner=self.owner)
        after = self.fingerprint(); self.assertEqual(after, before)
        (self.parent / 'corruption-check.json').write_bytes(canonical(dict(before=before, after=after, reset=False)))

    def test_creation_is_explicit_and_reopen_uses_no_new_connection(self):
        with self.assertRaisesRegex(store.IoServiceStoreError, 'SCHEMA'):
            store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry)
        self.assertIsNone(self.db.execute('SELECT 1 FROM reg_meta WHERE key=?', (store.ANCHOR,)).fetchone())
        with patch.object(sqlite3, 'connect', side_effect=AssertionError('store opened SQL')):
            self.create()
            other = store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry)
            self.assertIsNone(other.lookup_mutation(self.owner, 'absent'))
        with self.assertRaisesRegex(store.IoServiceStoreError, 'ALREADY_EXISTS'): self.create()
        with self.assertRaisesRegex(store.IoServiceStoreError, 'REOPEN_OPTIONS'):
            store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry, max_revisions=128)

    def test_canonical_authority_bound_record_survives_runtime_reopen(self):
        self.create(); original = self.configure(); self.reopen()
        retained = self.store.read(self.owner, self.config['evaluatorId'])
        self.assertEqual(retained['receiptDigest'], original['receiptDigest'])
        self.assertEqual(retained['configuration'], canonical(services.parse_configuration(self.config)))
        pin = services.parse_service_pin(retained['servicePin'])
        self.assertEqual(pin['profile'], services.AUTHORITY_PIN_PROFILE)
        self.assertEqual(pin['authorityId'], self.runtime.journal.authority_id)
        self.assertEqual(self.configure(), original)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_exact_replay_precedes_source_runtime_and_later_revision_checks(self):
        self.create(); first = self.configure(); second = self.configure(self.config | {'revision': 2}, key='config:2', prior=1)
        with patch.object(services, 'prepare_service_pin', side_effect=AssertionError('fresh pin')):
            self.assertEqual(self.store.configure(self.owner, 'config:1', self.config, expected_revision=0), first)
            self.assertEqual(self.store.lookup_mutation(self.owner, 'config:2'), second)
            self.assertEqual(self.store.read(self.owner, self.config['evaluatorId'], revision=1)['receiptDigest'], first['receiptDigest'])
        self.assertEqual(second['receipt']['previousReceiptDigest'], first['receiptDigest'])
        first['receipt']['sequence'] = 999
        self.assertEqual(self.store.lookup_mutation(self.owner, 'config:1')['receipt']['sequence'], 1)

    def test_changed_same_key_refuses_before_any_fresh_work(self):
        self.create(); self.configure()
        with patch.object(services, 'prepare_service_pin', side_effect=AssertionError('fresh pin')):
            for config, prior in [(self.config | {'revision': 2}, 1), (self.config, 1)]:
                with self.assertRaisesRegex(store.IoServiceStoreError, 'KEY_CONFLICT'):
                    self.store.configure(self.owner, 'config:1', config, expected_revision=prior)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_revision_compare_and_swap_and_per_evaluator_chains(self):
        self.create(); first = self.configure()
        with self.assertRaisesRegex(store.IoServiceStoreError, 'REVISION_CONFLICT'):
            self.configure(self.config | {'revision': 2}, key='config:stale', prior=0)
        other = self.configure(self.config | {'evaluatorId': 'eval:other'}, key='config:other')
        last = self.configure(self.config | {'revision': 2}, key='config:2', prior=1)
        self.assertEqual([first['receipt']['sequence'], other['receipt']['sequence'], last['receipt']['sequence']], [1, 2, 3])
        self.assertIsNone(other['receipt']['previousReceiptDigest'])
        self.assertEqual(last['receipt']['previousReceiptDigest'], first['receiptDigest'])
        self.assertIsNone(self.store.lookup_mutation(self.owner, 'config:stale'))

    def test_creation_and_history_require_current_admin_authority(self):
        visitor = Context('visitor', self.owner.deployment)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'):
            store.IoServiceConfigurationStore(self.runtime.journal, self.runtime.registry, create=True, owner=visitor)
        self.create(); self.configure()
        for fn in (lambda: self.store.read(visitor, self.config['evaluatorId']),
                   lambda: self.store.lookup_mutation(visitor, 'config:1'),
                   lambda: self.store.configure(visitor, 'config:1', self.config, expected_revision=0)):
            with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): fn()
        self.runtime.registry.grant(self.owner, self.owner.principal, '*', 'admin', enabled=False)
        with self.assertRaisesRegex(JournalError, 'ACCESS_DENIED'): self.configure()

    def test_cross_authority_runtime_and_deployment_cannot_supply_configuration(self):
        self.create(); other = runtime_at(self.parent / 'runtime-other', self.document); self.addCleanup(other.close)
        with self.assertRaisesRegex(store.IoServiceStoreError, 'AUTHORITY_MISMATCH'):
            self.store.configure(self.owner, 'config:1', self.config, expected_revision=0, runtime=other)
        with self.assertRaisesRegex(store.IoServiceStoreError, 'AUTHORITY_MISMATCH'):
            self.store.configure(Context('owner', 'simulation:other'), 'config:1', self.config, expected_revision=0, runtime=self.runtime)
        self.assertEqual(self.counts(), [0, 0, 0])

    def test_identical_layouts_in_distinct_authorities_have_distinct_pins(self):
        self.create(); self.configure(); other = runtime_at(self.parent / 'runtime-other', self.document); self.addCleanup(other.close)
        remote = store.IoServiceConfigurationStore(other.journal, other.registry, create=True, owner=self.owner)
        remote.configure(self.owner, 'config:1', self.config, expected_revision=0, runtime=other)
        a = services.parse_service_pin(self.store.read(self.owner, self.config['evaluatorId'])['servicePin'])
        b = services.parse_service_pin(remote.read(self.owner, self.config['evaluatorId'])['servicePin'])
        self.assertNotEqual(a['authorityId'], b['authorityId']); self.assertNotEqual(a['configurationDigest'], b['configurationDigest'])

    def test_before_commit_failure_rolls_back_all_configuration_rows(self):
        self.create()
        def fail(phase, value):
            if phase == 'before_commit': raise RuntimeError('commit fault')
        with patch.object(self.store, '_checkpoint', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'commit fault'): self.configure()
        self.assertEqual(self.counts(), [0, 0, 0]); self.assertIsNone(self.store.lookup_mutation(self.owner, 'config:1'))
        self.reopen(); self.assertEqual(self.counts(), [0, 0, 0])
        self.assertEqual(self.configure()['receipt']['sequence'], 1)

    def test_lost_commit_reply_replays_original_after_reopen(self):
        self.create(); retained = []
        def fail(phase, value):
            if phase == 'after_commit': retained.append(value); raise RuntimeError('lost reply')
        with patch.object(self.store, '_checkpoint', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'lost reply'): self.configure()
        self.reopen()
        with patch.object(services, 'prepare_service_pin', side_effect=AssertionError('fresh pin')):
            self.assertEqual(self.configure(), retained[0])
        self.assertEqual(self.counts(), [1, 1, 1])

    def race(self, changed):
        self.create(); gate = threading.Barrier(2); values = []; failures = []
        def invoke(index):
            try:
                gate.wait(timeout=10)
                config = self.config | ({'evaluatorId': 'eval:changed'} if changed and index else {})
                values.append(self.configure(config))
            except BaseException as error: failures.append(error)
        threads = [threading.Thread(target=invoke, args=(index,)) for index in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(self.counts(), [1, 1, 1])
        return values, failures

    def test_concurrent_exact_mutations_commit_one_version(self):
        values, failures = self.race(False)
        self.assertEqual(failures, []); self.assertEqual(len(values), 2); self.assertEqual(values[0], values[1])

    def test_concurrent_changed_same_key_has_one_winner_and_one_conflict(self):
        values, failures = self.race(True)
        self.assertEqual(len(values), 1); self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], store.IoServiceStoreError); self.assertIn('KEY_CONFLICT', str(failures[0]))

    def test_lowered_record_capacity_preserves_exact_replay_at_full(self):
        self.create(max_revisions=2); first = self.configure()
        self.configure(self.config | {'revision': 2}, key='config:2', prior=1)
        with self.assertRaisesRegex(store.IoServiceStoreError, 'CAPACITY'):
            self.configure(self.config | {'revision': 3}, key='config:3', prior=2)
        self.assertEqual(self.configure(), first); self.assertEqual(self.counts(), [2, 2, 1])

    def test_lowered_byte_capacity_refuses_before_configuration_writes(self):
        self.create(max_data_bytes=2048)
        with self.assertRaisesRegex(store.IoServiceStoreError, 'CAPACITY'): self.configure()
        self.assertEqual(self.counts(), [0, 0, 0])

    def test_metadata_capacity_tampering_is_not_a_limit_change(self):
        self.create(max_revisions=2); self.configure()
        meta = json.loads(self.db.execute('SELECT record FROM iosc_meta').fetchone()[0]); meta['maxRevisions'] = 128
        self.db.execute('UPDATE iosc_meta SET record=?', (canonical(meta),))
        before = self.fingerprint()
        with self.assertRaisesRegex(store.IoServiceStoreError, 'INVALID_RETAINED'):
            self.store.read(self.owner, self.config['evaluatorId'])
        self.assertEqual(self.fingerprint(), before)

    def test_missing_head_refuses_and_is_never_rebuilt(self): self.corrupt('DELETE FROM iosc_heads')
    def test_non_object_receipt_refuses_and_is_retained(self): self.corrupt('UPDATE iosc_versions SET receipt=?', (b'[]',))
    def test_oversized_configuration_refuses_before_parsing(self): self.corrupt('UPDATE iosc_versions SET configuration=?', (b' ' * 65537,))
    def test_noncanonical_pin_refuses_and_is_retained(self): self.corrupt("UPDATE iosc_versions SET pin=CAST(pin || ' ' AS BLOB)")
    def test_mutation_header_mismatch_refuses_and_is_retained(self): self.corrupt('UPDATE iosc_mutations SET request=?', (b'{}',))
    def test_partial_schema_refuses_and_is_never_recreated(self): self.corrupt('DROP TABLE iosc_heads')
    def test_added_index_refuses_and_is_retained(self): self.corrupt('CREATE INDEX iosc_unreviewed ON iosc_versions(revision)')
    def test_temp_shadow_table_refuses_before_reading_it(self): self.corrupt('CREATE TEMP TABLE iosc_versions(sequence INTEGER)')

    def test_all_owned_tables_missing_with_anchor_never_reinitialize(self):
        self.create(); original = self.configure()
        (self.parent / 'original-receipt.json').write_bytes(canonical(original))
        for table in store._DDL: self.db.execute('DROP TABLE ' + table)
        before = self.fingerprint()
        with self.assertRaisesRegex(store.IoServiceStoreError, 'SCHEMA'): self.create()
        self.assertEqual(self.fingerprint(), before)

    def test_legacy_unbound_pin_cannot_enter_authority_history(self):
        pin = services.prepare_service_pin(self.config, self.document)
        self.corrupt('UPDATE iosc_versions SET pin=?', (canonical(pin),))

    def test_complete_descriptor_snapshot_requires_transaction_and_is_read_only(self):
        self.create(); self.configure(); pin = services.parse_service_pin(self.store.read(self.owner, self.config['evaluatorId'])['servicePin'])
        resolver = self.store._resolver(self.runtime, self.config, pin)
        with self.assertRaisesRegex(JournalError, 'TRANSACTION_REQUIRED'): resolver.configured_snapshot(self.owner)
        with self.runtime.journal._transaction():
            before = self.db.total_changes; snapshot = resolver.configured_snapshot(self.owner)
            self.assertEqual(self.db.total_changes, before)
            self.assertEqual(set(snapshot), {row['instanceId'] for row in self.config['registrations']})
            snapshot['sim:gpio5']['argumentMetadata'].clear()
            self.assertTrue(resolver.configured_snapshot(self.owner)['sim:gpio5']['argumentMetadata'])

    def test_missing_permission_on_one_registration_refuses_whole_snapshot(self):
        self.create(); self.configure(); pin = services.parse_service_pin(self.store.read(self.owner, self.config['evaluatorId'])['servicePin'])
        resolver = self.store._resolver(self.runtime, self.config, pin); reader = Context('reader', self.owner.deployment)
        for row in self.config['registrations']:
            self.runtime.registry.grant(self.owner, 'reader', row['instanceId'], 'read')
            if row['instanceId'] != 'sim:gpio6':
                for action in row['argumentMetadata']: self.runtime.registry.grant(self.owner, 'reader', row['instanceId'], 'invoke:' + action)
        with self.runtime.journal._transaction():
            with self.assertRaisesRegex(JournalError, 'UNAVAILABLE'): resolver.configured_snapshot(reader)

    def test_configuration_and_plan_do_not_create_device_effects_or_claims(self):
        before = business(self.runtime); self.create(); result = self.configure(); prepared = self.prepare()
        self.assertEqual(prepared['configurationReceipt'], result)
        self.assertEqual(prepared['preparedRun']['request']['context']['configurationDigest'], result['receipt']['configurationDigest'])
        self.assertEqual(business(self.runtime), before)
        (self.parent / 'business-before-after.json').write_bytes(canonical(before))

    def test_external_configuration_drift_refuses_before_planning(self):
        self.create(); self.configure()
        with patch.object(services.ConfiguredIoService, 'prepare_run', side_effect=AssertionError('planned')):
            with self.assertRaisesRegex(store.IoServiceStoreError, 'CONFIGURATION_CHANGED'):
                self.prepare(installed_configuration=self.config | {'revision': 2})

    def test_source_drift_blocks_fresh_plan_but_not_history_or_exact_replay(self):
        self.create(); result = self.configure()
        with patch.object(services, 'prepare_service_pin', side_effect=services.IoServiceError('PIN_CHANGED')):
            self.assertEqual(self.configure(), result)
            self.assertEqual(self.store.read(self.owner, self.config['evaluatorId'])['receiptDigest'], result['receiptDigest'])
            with self.assertRaisesRegex(services.IoServiceError, 'PIN_CHANGED'): self.prepare()

    def test_configuration_change_during_planning_refuses_returned_plan(self):
        self.create(); self.configure()
        def change(phase, value):
            if phase == 'prepared': self.configure(self.config | {'revision': 2}, key='config:2', prior=1)
        with patch.object(self.store, '_checkpoint', side_effect=change):
            with self.assertRaisesRegex(store.IoServiceStoreError, 'CONFIGURATION_CHANGED'): self.prepare()
        self.assertEqual(self.counts(), [2, 2, 1])

    def test_session_change_during_planning_refuses_returned_plan(self):
        self.create(); self.configure()
        def change(phase, value):
            if phase == 'prepared':
                self.runtime.registry.report_presence('sim:gpio5', adapter_id='io:routeA', endpoint_session='session:changed', ttl_ms=3000)
        with patch.object(self.store, '_checkpoint', side_effect=change):
            with self.assertRaisesRegex(store.IoServiceStoreError, 'AUTHORITY_CHANGED'): self.prepare()
        self.assertEqual(self.db.execute("SELECT session FROM reg_presence WHERE instance='sim:gpio5'").fetchone()[0], 'session:changed')


class IoAuthorityProcessTests(IoSupervisorProcessTests):
    @classmethod
    def setUpClass(cls):
        cls.document = normalize_installation(installation())
        cls.config = configuration(cls.document, bindings(cls.document))

    def root(self, label='root'):
        result = self.parent / label; result.mkdir(mode=0o700); return result

    def test_authority_configured_owned_group_reopens_and_replays(self):
        self.parent = Path(os.environ['TMPDIR']) / self._testMethodName; self.parent.mkdir(mode=0o700)
        runtime = runtime_at(self.parent / 'runtime', self.document); owner = Context('owner', 'simulation:io-hub')
        try:
            configured = store.IoServiceConfigurationStore(runtime.journal, runtime.registry, create=True, owner=owner)
            receipt = configured.configure(owner, 'config:1', self.config, expected_revision=0, runtime=runtime)
        finally: runtime.close()
        runtime = runtime_at(self.parent / 'runtime', self.document, create=False)
        try:
            configured = store.IoServiceConfigurationStore(runtime.journal, runtime.registry)
            self.assertEqual(configured.lookup_mutation(owner, 'config:1'), receipt)
            before = business(runtime)
            value = configured.prepare_run(owner, self.config['evaluatorId'], program(literal=True), 'run:authority-owned',
                runtime=runtime, installed_configuration=self.config)
            self.assertEqual(value['configurationReceipt'], receipt); self.assertEqual(business(runtime), before)
            self.prepared = value['preparedRun']; self.bundle, self.request = self.prepared['bundle'], self.prepared['request']
            self.context = self.request['context']; fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for name, body in [('service-configuration.json', self.prepared['configuration']),
                    ('service-pin.json', self.prepared['servicePin']), ('service-configuration-receipt.json', canonical(receipt)),
                    ('service-request-digest.json', canonical(dict(requestDigest=self.prepared['requestDigest']))),
                    ('authority-business.json', canonical(before))]: contracts.write_file(fd, name, body)
            finally: os.close(fd)
        finally: runtime.close()
        IoSupervisorProcessTests.test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays(self)
