import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Journal
from journal_support import CONTEXT, TestPolicy, evidence, request
from evidence_vault import EvidenceVault, VaultError, descriptor
from evidence_vault import contracts as c
from evidence_vault.store import DOMAIN


AUTHORITY = '1' * 32
INTENT = c.sha(b'original import intent')
BINDING = c.sha(b'original run association')


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ['HMS_VAULT_TEST_ROOT']) / self._testMethodName
        self.root.mkdir(mode=0o700)
        self.handles = []

    def tearDown(self):
        for handle in reversed(self.handles):
            handle.close()

    def vault(self, name='bulk', **limits):
        parent = self.root / name
        parent.mkdir(mode=0o700)
        expected = descriptor(AUTHORITY, **limits)
        obj = EvidenceVault(parent / 'evidence.db', expected, create=True)
        self.handles.append(obj)
        return obj, parent / 'evidence.db', expected

    def reopen(self, path, expected):
        obj = EvidenceVault(path, expected)
        self.handles.append(obj)
        return obj

    def code(self, suffix, function, *args, **kwargs):
        with self.assertRaises(VaultError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, 'PAT_EVIDENCE_VAULT_' + suffix)

    def snapshot_files(self, vault, intent=INTENT, binding=BINDING):
        with vault.snapshot(intent, binding) as snapshot:
            return snapshot.manifest(), snapshot.documents()

    def test_create_reopen_exact_manifest_and_replay(self):
        vault, path, expected = self.vault(max_pages=64)
        files = {'input/a.json': b'{"value":1}', 'output/b.bin': b'\x00\xff'}
        first = vault.seal(INTENT, BINDING, files)
        initial = path.read_bytes()
        self.assertEqual(vault.seal(INTENT, BINDING, dict(reversed(list(files.items())))), first)
        self.assertEqual(path.read_bytes(), initial)
        vault.close()
        reopened = self.reopen(path, expected)
        self.assertEqual(reopened._scalar('PRAGMA max_page_count'), 64)
        self.assertEqual(self.snapshot_files(reopened), (first, files))
        self.assertEqual(reopened.seal(INTENT, BINDING, files), first)
        self.assertEqual(path.read_bytes(), initial)
        self.assertEqual(first['scope'], 'immutable-bytes-only')

    def test_descriptor_types_and_limits(self):
        for key, value in [('max_pages', True), ('max_pages', c.MAX_PAGES + 1),
                           ('max_manifests', 0), ('max_documents', False),
                           ('max_objects', c.MAX_STORE_DOCUMENTS + 1), ('max_data_bytes', -1)]:
            self.code('LIMIT', descriptor, AUTHORITY, **{key: value})
        self.code('IDENTITY', descriptor, 'unbound')

    def test_invalid_document_and_lease_inputs_do_not_publish(self):
        vault, path, expected = self.vault()
        before = path.read_bytes()
        self.code('INVALID', vault.seal, INTENT, BINDING, {'../escape': b'data'})
        self.code('DOCUMENT', vault.seal, INTENT, BINDING, {'a': 'not bytes'})
        self.code('DIGEST', vault.seal, 'not a digest', BINDING, {'a': b'a'})
        with self.assertRaises(VaultError) as caught:
            with vault.snapshot(INTENT, BINDING, lifetime_ms=True):
                self.fail('Invalid lease entered')
        self.assertEqual(caught.exception.code, 'PAT_EVIDENCE_VAULT_LIMIT')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(vault._scalar('SELECT count(*) FROM ev_manifests'), 0)

    def test_reopen_rejects_different_authority_or_store(self):
        vault, path, expected = self.vault()
        vault.seal(INTENT, BINDING, {'a': b'a'})
        vault.close()
        before = path.read_bytes()
        for field in ('authorityId', 'storeId'):
            changed = dict(expected, **{field: '2' * 32})
            self.code('MOUNT_CHANGED', EvidenceVault, path, changed)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_store_does_not_create_replacement(self):
        vault, path, expected = self.vault()
        vault.close()
        retained = path.with_name('retained.db')
        path.rename(retained)
        self.code('INVALID', EvidenceVault, path, expected)
        self.assertFalse(path.exists())
        self.assertTrue(retained.exists())

    def test_owner_busy_does_not_change_first_store(self):
        vault, path, expected = self.vault()
        self.code('OWNER_BUSY', EvidenceVault, path, expected)
        vault.seal(INTENT, BINDING, {'a': b'first owner'})
        self.assertEqual(self.snapshot_files(vault)[1], {'a': b'first owner'})

    def test_private_directory_required(self):
        parent = self.root / 'public'
        parent.mkdir(mode=0o700)
        parent.chmod(0o755)
        self.code('PRIVATE_DIRECTORY_REQUIRED', EvidenceVault, parent / 'evidence.db', descriptor(AUTHORITY), create=True)
        self.assertEqual(list(parent.iterdir()), [])

    def test_reopen_refuses_retained_or_dangling_sidefile(self):
        for name, dangling in [('journal', False), ('dangling', True)]:
            vault, path, expected = self.vault(name=name)
            vault.close()
            sidefile = Path(str(path) + '-journal')
            if dangling:
                sidefile.symlink_to(path.parent / 'missing-target')
            else:
                sidefile.write_bytes(b'retained unclassified journal')
            before = path.read_bytes()
            self.code('RECOVERY_REQUIRED', EvidenceVault, path, expected)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(os.path.lexists(sidefile))

    def test_live_path_replacement_refused(self):
        vault, path, expected = self.vault()
        vault.seal(INTENT, BINDING, {'a': b'original'})
        path.rename(path.with_name('original-retained.db'))
        path.write_bytes(b'replacement')
        self.code('FILE_IDENTITY', vault.seal, INTENT, BINDING, {'a': b'original'})
        self.assertEqual(path.read_bytes(), b'replacement')

    def test_exact_deduplication_keeps_each_reference_and_chain(self):
        vault, path, expected = self.vault()
        first = vault.seal(INTENT, BINDING, {'a': b'shared', 'b': b'shared'})
        second_intent = c.sha(b'second intent')
        second = vault.seal(second_intent, BINDING, {'c': b'shared', 'd': b'distinct'})
        self.assertEqual(second['sequence'], 2)
        self.assertEqual(second['previousManifestDigest'], c.hash_value(DOMAIN, first))
        self.assertEqual(vault._scalar('SELECT count(*) FROM ev_bodies'), 2)
        self.assertEqual(vault._scalar('SELECT count(*) FROM ev_documents'), 4)
        self.assertEqual(self.snapshot_files(vault, second_intent)[1], {'c': b'shared', 'd': b'distinct'})

    def test_original_intent_conflicts_preserve_data(self):
        vault, path, expected = self.vault()
        original = vault.seal(INTENT, BINDING, {'a': b'original'})
        before = path.read_bytes()
        self.code('KEY_CONFLICT', vault.seal, INTENT, c.sha(b'other binding'), {'a': b'original'})
        self.code('KEY_CONFLICT', vault.seal, INTENT, BINDING, {'a': b'changed'})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.snapshot_files(vault)[0], original)

    def test_document_object_and_manifest_capacity(self):
        limits = [('references', dict(max_documents=1), {'b': b'same'}, 'CAPACITY'),
                  ('objects', dict(max_objects=1), {'b': b'new'}, 'CAPACITY'),
                  ('manifests', dict(max_manifests=1), {'b': b'same'}, 'LIMIT')]
        for name, options, files, error in limits:
            vault, path, expected = self.vault(name=name, **options)
            vault.seal(INTENT, BINDING, {'a': b'same'})
            before = path.read_bytes()
            self.code(error, vault.seal, c.sha(b'new'), BINDING, files)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(self.snapshot_files(vault)[1], {'a': b'same'})

    def test_page_capacity_rolls_back_and_control_still_completes(self):
        policy = TestPolicy()
        with Journal(self.root / 'authority.db', policy, clock_ms=lambda: 1000, create=True) as journal:
            namespace = journal.issue_namespace(CONTEXT, 3000)['token']
            operation = journal.submit(CONTEXT, request(namespace))
            ticket = journal.claim_dispatch(operation['id'])
            vault, path, expected = self.vault(max_pages=32)
            vault.seal(INTENT, BINDING, {'a': b'original'})
            before = path.read_bytes()
            self.code('CAPACITY', vault.seal, c.sha(b'large'), BINDING, {'large.bin': b'x' * 65536})
            self.assertFalse(vault._db.in_transaction)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(self.snapshot_files(vault)[1], {'a': b'original'})
            journal.record_execution(ticket, 'completed', evidence('completed'))
            current = journal.status(CONTEXT, operation['id'])
            self.assertEqual(current['state'], 'completed')
            self.assertEqual(len(current['claims']), 1)
            journal.release_resources(operation['id'], evidence('resources_quiescent'))
            current = journal.status(CONTEXT, operation['id'])
            self.assertFalse(current['claims'])
            self.assertEqual(journal.submit(CONTEXT, request(namespace))['id'], operation['id'])
            self.assertEqual(policy.admissions, 1)
            self.assertLessEqual(path.stat().st_size, 32 * 1024)

    def test_changed_connection_cap_refused_then_original_cap_reapplied(self):
        vault, path, expected = self.vault(max_pages=32)
        self.assertEqual(vault._scalar('PRAGMA max_page_count=16'), 16)
        self.code('FILE_CAPACITY', vault.seal, INTENT, BINDING, {'a': b'a'})
        vault.close()
        reopened = self.reopen(path, expected)
        self.assertEqual(reopened._scalar('PRAGMA max_page_count'), 32)
        reopened.seal(INTENT, BINDING, {'a': b'a'})

    def test_snapshot_is_read_only_detached_and_expires_on_release(self):
        vault, path, expected = self.vault()
        record = vault.seal(INTENT, BINDING, {'a': b'original'})
        with vault.snapshot(INTENT, BINDING) as snapshot:
            files = snapshot.documents(); files['a'] = b'changed'
            result = snapshot.manifest(); result['scope'] = 'forged'
            self.assertEqual(snapshot.documents(), {'a': b'original'})
            self.assertEqual(snapshot.manifest(), record)
            with self.assertRaises(sqlite3.OperationalError):
                vault._db.execute("UPDATE ev_bodies SET body=x'00'")
            self.code('LEASE_ACTIVE', vault.close)
            self.code('TRANSACTION_REENTRY', vault.seal, c.sha(b'new'), BINDING, {'b': b'b'})
            snapshot.check(vault)
        self.code('SNAPSHOT_UNAVAILABLE', snapshot.documents)
        vault.seal(c.sha(b'new'), BINDING, {'b': b'b'})

    def test_snapshot_time_bound_invalidates_handle_and_cleans_transaction(self):
        vault, path, expected = self.vault()
        vault.seal(INTENT, BINDING, {'a': b'a'})
        ticks = [1000000000]
        with patch('evidence_vault.connection.time.monotonic_ns', side_effect=lambda: ticks[0]):
            with self.assertRaises(VaultError) as caught:
                with vault.snapshot(INTENT, BINDING, lifetime_ms=1) as snapshot:
                    ticks[0] += 1000000
                    snapshot.check(vault)
            self.assertEqual(caught.exception.code, 'PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE')
        self.assertFalse(vault._db.in_transaction)
        self.assertIsNone(vault._lease)
        self.assertEqual(vault._scalar('PRAGMA query_only'), 0)
        self.assertEqual(self.snapshot_files(vault)[1], {'a': b'a'})

    def test_snapshot_owner_and_sqlite_reader_lock(self):
        vault, path, expected = self.vault()
        other, _, _ = self.vault(name='other')
        vault.seal(INTENT, BINDING, {'a': b'original'})
        with vault.snapshot(INTENT, BINDING) as snapshot:
            self.code('SNAPSHOT_UNAVAILABLE', snapshot.check, other)
            competitor = sqlite3.connect(str(path), isolation_level=None, timeout=0.01)
            try:
                competitor.execute('BEGIN IMMEDIATE')
                competitor.execute('UPDATE ev_bodies SET body=?', (b'not committed',))
                with self.assertRaises(sqlite3.OperationalError):
                    competitor.execute('COMMIT')
                self.assertTrue(competitor.in_transaction)
                competitor.execute('ROLLBACK')
            finally:
                competitor.close()
            self.assertEqual(snapshot.documents(), {'a': b'original'})
        self.assertEqual(self.snapshot_files(vault)[1], {'a': b'original'})

    def test_body_corruption_refuses_snapshot_and_reuse_without_repair(self):
        vault, path, expected = self.vault()
        vault.seal(INTENT, BINDING, {'a': b'original'})
        vault._db.execute('UPDATE ev_bodies SET body=?', (b'corrupt!',))
        before = path.read_bytes()
        self.code('BODY_CHANGED', self.snapshot_files, vault)
        self.code('BODY_CHANGED', vault.seal, c.sha(b'new'), BINDING, {'b': b'original'})
        self.assertEqual(path.read_bytes(), before)

    def test_schema_shadow_and_typed_manifest_corruption_refused(self):
        vault, path, expected = self.vault(name='schema')
        vault._db.execute('CREATE TABLE shadow(value TEXT)')
        before = path.read_bytes()
        self.code('SCHEMA', vault.seal, INTENT, BINDING, {'a': b'a'})
        self.assertEqual(path.read_bytes(), before)
        typed, typed_path, _ = self.vault(name='typed')
        record = typed.seal(INTENT, BINDING, {'a': b'a'})
        record['closure']['documents'] = True
        typed._db.execute('UPDATE ev_manifests SET record=?', (canonical(record),))
        before = typed_path.read_bytes()
        self.code('INVALID_RETAINED', self.snapshot_files, typed)
        self.assertEqual(typed_path.read_bytes(), before)

    def test_before_commit_failure_retains_no_partial_manifest(self):
        vault, path, expected = self.vault()
        before = path.read_bytes()
        def fail(phase, value):
            if phase == 'before_manifest_commit':
                raise RuntimeError('original injected precommit failure')
        vault._checkpoint = fail
        with self.assertRaisesRegex(RuntimeError, 'precommit'):
            vault.seal(INTENT, BINDING, {'a': b'original'})
        self.assertEqual(path.read_bytes(), before)
        self.code('MANIFEST_UNAVAILABLE', self.snapshot_files, vault)
        self.assertFalse(vault._db.in_transaction)

    def test_after_commit_reply_failure_reopens_original_manifest(self):
        vault, path, expected = self.vault()
        def fail(phase, value):
            if phase == 'after_manifest_commit':
                raise RuntimeError('original injected lost seal reply')
        vault._checkpoint = fail
        with self.assertRaisesRegex(RuntimeError, 'lost seal reply'):
            vault.seal(INTENT, BINDING, {'a': b'original'})
        vault.close()
        reopened = self.reopen(path, expected)
        before = path.read_bytes()
        record = reopened.seal(INTENT, BINDING, {'a': b'original'})
        self.assertEqual(record['sequence'], 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(reopened._scalar('SELECT count(*) FROM ev_manifests'), 1)


class VaultOriginalEvidenceTests(VaultTests):
    # The harness selects only the method below from this subclass.
    def test_complete_retained_original_evidence_bytes(self):
        source = Path(os.environ['HMS_VAULT_ORIGINAL_DATABASE'])
        self.assertEqual(source.stat().st_size, 16199680)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         'f106c3312d0c05b69be52b5fae65edd19892b9c019bd62d6691ec3555cc93099')
        db = sqlite3.connect(source.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM ioec_documents').fetchone()[0], 4011)
            self.assertEqual(db.execute('SELECT count(*) FROM ioec_bodies').fetchone()[0], 2798)
            self.assertEqual(db.execute('SELECT sum(length(body)) FROM ioec_bodies').fetchone()[0], 13638563)
            receipt = db.execute('SELECT receipt FROM ioec_runs WHERE sequence=1').fetchone()[0]
            rows = db.execute('SELECT d.path,b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest '
                              'WHERE d.sequence=1 LIMIT 4012').fetchall()
            self.assertEqual(len(rows), 4011)
            files = dict(rows)
            self.assertEqual(len(files), 4011)
        finally:
            db.close()
        vault, path, expected = self.vault()
        intent = c.sha(receipt)
        binding = c.sha(canonical(json.loads(receipt)['anchor']))
        record = vault.seal(intent, binding, files)
        self.assertEqual(record['closure'], json.loads(receipt)['closure'])
        self.assertEqual(self.snapshot_files(vault, intent, binding), (record, files))
        self.assertEqual(vault._scalar('SELECT count(*) FROM ev_documents'), 4011)
        self.assertEqual(vault._scalar('SELECT count(*) FROM ev_bodies'), 2798)
        self.assertEqual(vault._scalar('SELECT sum(length(body)) FROM ev_bodies'), 13638563)
        before = path.read_bytes()
        vault.close()
        reopened = self.reopen(path, expected)
        self.assertEqual(reopened.seal(intent, binding, files), record)
        self.assertEqual(self.snapshot_files(reopened, intent, binding), (record, files))
        self.assertEqual(path.read_bytes(), before)
        self.assertLessEqual(path.stat().st_size, 15 * 1024 * 1024)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         'f106c3312d0c05b69be52b5fae65edd19892b9c019bd62d6691ec3555cc93099')
        (self.root / 'actual-evidence.json').write_text(json.dumps(dict(
            scope='exact retained bytes from preceding complete 30-case scope; no new worker or qualification',
            references=4011, uniqueBodies=2798, uniqueBodyBytes=13638563,
            databaseBytes=path.stat().st_size, maximumDatabaseBytes=15 * 1024 * 1024,
            originalInputUnchanged=True, replayAddsNoManifest=True, authorityPublished=False,
            physicalObjectiveVerified=False, manifest=record), indent=2) + '\n')
