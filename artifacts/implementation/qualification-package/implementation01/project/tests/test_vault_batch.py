"""Complete bounded manifest inventories and their real Journal commit boundary."""
import json
import os
from pathlib import Path
import sqlite3
import threading
from unittest.mock import patch

from hms_qualification.evidence_vault import EvidenceVault, VaultError, descriptor
from hms_qualification.evidence_vault import contracts as c
from hms.contracts import canonical
from hms.journal import Journal
from journal_support import CONTEXT, TestPolicy, request
from test_evidence_vault import VaultTests


class BatchVaultTests(VaultTests):
    def setUp(self):
        self.root = Path(os.environ['HMS_BATCH_VAULT_TEST_ROOT']) / self._testMethodName
        self.root.mkdir(mode=0o700)
        self.handles, self.notes = [], []

    def tearDown(self):
        for handle in reversed(self.handles):
            if not handle._closed:
                self.assertFalse(handle._db.in_transaction)
                if isinstance(handle, EvidenceVault):
                    self.assertIsNone(handle._lease)
                    self.assertEqual(handle._scalar('PRAGMA query_only'), 0)
            handle.close()
        with (self.root/'observations.json').open('x') as stream:
            json.dump(dict(notes=self.notes,handlesClosed=True),stream,indent=2);stream.write('\n')

    def populated(self, *, shared=False, journal=None):
        if journal is None:
            vault, path, expected = self.vault(max_pages=128)
        else:
            parent=self.root/'bulk';parent.mkdir(mode=0o700)
            expected=descriptor(journal.authority_id,max_pages=128)
            path=parent/'hms_qualification.evidence.db';vault=EvidenceVault(path,expected,create=True)
            self.handles.append(vault)
        keys=tuple((c.sha(('intent:'+name).encode()),c.sha(('binding:'+name).encode())) for name in ('one','two'))
        files=({'a':b'alpha','same':b'shared'}, {'b':b'alpha' if shared else b'bravo','same':b'shared'})
        records=tuple(vault.seal(*key,documents=value) for key,value in zip(keys,files))
        return vault,path,expected,keys,files,records

    def joint(self):
        policy=TestPolicy();journal=Journal(self.root/'authority.db',policy,clock_ms=lambda:1000,create=True)
        self.handles.append(journal)
        namespace=journal.issue_namespace(CONTEXT,4000)['token']
        return journal,policy,request(namespace)

    def arm(self,journal,policy,callback):
        original=policy.admit
        def admit(*args):
            value=original(*args);journal._require_at_commit(callback);return value
        policy.admit=admit

    def view(self,vault,keys,**limits):
        with vault.snapshot_many(keys,**limits) as view:
            return view.keys(),[view.manifest(*key) for key in keys],[view.documents(*key) for key in keys],view.usage()

    def test_all_members_exact_in_one_order_independent_view(self):
        vault,path,expected,keys,files,records=self.populated()
        before=path.read_bytes()
        first=self.view(vault,keys)
        self.assertEqual(first[:3],(tuple(sorted(keys)),list(records),list(files)))
        second=self.view(vault,tuple(reversed(keys)))
        self.assertEqual(second[0],first[0]);self.assertEqual(second[3],first[3])
        self.assertEqual(second[1],list(reversed(records)))
        self.assertEqual(path.read_bytes(),before)
        self.notes.append(first[3])

    def test_single_member_matches_existing_snapshot(self):
        vault,_,_,keys,files,records=self.populated()
        result=self.view(vault,(keys[0],))
        self.assertEqual(result[1:3],([records[0]],[files[0]]))
        with vault.snapshot(*keys[0]) as single:
            self.assertEqual((single.manifest(),single.documents()),(records[0],files[0]))

    def test_detached_maps_and_shared_immutable_body_objects(self):
        vault,_,_,keys,files,records=self.populated(shared=True)
        with vault.snapshot_many(keys) as view:
            one,two=(view.documents(*key) for key in keys)
            self.assertIs(one['a'],two['b']);self.assertIs(one['same'],two['same'])
            one['a']=b'changed';one.clear()
            record=view.manifest(*keys[0]);record['scope']='forged'
            usage=view.usage();usage['documents']=0
            self.assertEqual(view.documents(*keys[0]),files[0])
            self.assertEqual(view.manifest(*keys[0]),records[0])
            self.assertEqual(view.usage()['documents'],4)
            self.assertEqual(view.usage()['uniqueBodies'],2)
            self.assertEqual(view.usage()['expandedBodyBytes'],22)
            self.assertEqual(view.usage()['uniqueBodyBytes'],11)
            self.notes.append(view.usage())

    def test_duplicate_intents_refused_without_fetching_bodies(self):
        vault,_,_,keys,_,_=self.populated()
        for pair in (keys[0],(keys[0][0],c.sha(b'different binding'))):
            with patch.object(vault,'_read',side_effect=AssertionError('body fetch before complete preflight')):
                self.code('DUPLICATE_INTENT',self.view,vault,(keys[0],pair))

    def test_closed_request_shapes_do_not_invoke_custom_hooks(self):
        vault,_,_,keys,_,_=self.populated();calls=[]
        class Custom(tuple):
            def __iter__(self):calls.append('iter');raise AssertionError('custom iteration')
            def __len__(self):calls.append('len');raise AssertionError('custom length')
        for value in ([keys[0]],Custom(keys),(list(keys[0]),),(Custom(keys[0]),),(('one',),)):
            self.code('REQUESTS',self.view,vault,value)
        self.assertEqual(calls,[])
        self.code('LIMIT',self.view,vault,())
        self.code('DIGEST',self.view,vault,((True,keys[0][1]),))

    def test_every_missing_member_prevents_any_view_or_body_fetch(self):
        vault,path,_,keys,_,_=self.populated();before=path.read_bytes()
        missing=(c.sha(b'missing'),keys[0][1])
        with patch.object(vault,'_read',side_effect=AssertionError('partial materialization')):
            self.code('MANIFEST_UNAVAILABLE',self.view,vault,(keys[0],missing))
        self.assertEqual(path.read_bytes(),before)
        self.assertIsNone(vault._lease);self.assertFalse(vault._db.in_transaction)

    def test_wrong_member_binding_prevents_any_body_fetch(self):
        vault,_,_,keys,_,_=self.populated()
        with patch.object(vault,'_read',side_effect=AssertionError('partial materialization')):
            self.code('KEY_CONFLICT',self.view,vault,(keys[0],(keys[1][0],keys[0][1])))

    def test_aggregate_document_limit_precedes_body_fetch(self):
        vault,_,_,keys,_,_=self.populated()
        with patch.object(vault,'_read',side_effect=AssertionError('capacity preflight missing')):
            self.code('SNAPSHOT_CAPACITY',self.view,vault,keys,max_documents=3)
        result=self.view(vault,keys,max_documents=4)
        self.assertEqual(result[3]['documents'],result[3]['documentLimit'])

    def test_exact_aggregate_byte_boundary_counts_every_reference(self):
        vault,_,_,keys,files,records=self.populated(shared=True)
        charge=sum(len(canonical(record))+512 for record in records)
        charge+=sum(len(body)+len(name.encode())+512 for values in files for name,body in values.items())
        result=self.view(vault,keys,max_bytes=charge)
        self.assertEqual(result[3]['chargedBytes'],charge)
        self.assertEqual(result[3]['byteLimit'],charge)
        with patch.object(vault,'_read',side_effect=AssertionError('capacity preflight missing')):
            self.code('SNAPSHOT_CAPACITY',self.view,vault,keys,max_bytes=charge-1)
        self.notes.append(result[3])

    def test_invalid_limit_types_and_ranges(self):
        vault,_,_,keys,_,_=self.populated()
        for options in ({'max_bytes':True},{'max_bytes':0},{'max_bytes':c.MAX_STORE_BYTES+1},
                        {'max_documents':True},{'max_documents':0},{'max_documents':c.MAX_STORE_DOCUMENTS+1},
                        {'lifetime_ms':False},{'lifetime_ms':0},{'lifetime_ms':c.MAX_LEASE_MS+1}):
            self.code('LIMIT',self.view,vault,keys,**options)

    def test_request_count_bound_checked_before_state_scan(self):
        vault,_,_,_,_,_=self.populated()
        keys=tuple((c.sha(str(i).encode()),c.sha(b'fixed binding')) for i in range(c.MAX_MANIFESTS+1))
        with patch.object(vault,'_state',side_effect=AssertionError('oversized request reached SQLite state scan')):
            self.code('LIMIT',self.view,vault,keys)

    def test_maximum_manifest_set_retained_completely(self):
        vault,_,_=self.vault(max_pages=256)
        keys=tuple((c.sha(str(i).encode()),c.sha(b'bound')) for i in range(c.MAX_MANIFESTS))
        for key in keys:vault.seal(*key,documents={'same':b'one shared body'})
        with vault.snapshot_many(keys) as view:
            self.assertEqual(view.keys(),tuple(sorted(keys)))
            self.assertEqual(view.usage()['manifests'],32)
            self.assertEqual(view.usage()['documents'],32)
            self.assertEqual(view.usage()['uniqueBodies'],1)
            self.assertTrue(all(view.documents(*key)=={'same':b'one shared body'} for key in keys))
            self.notes.append(view.usage())

    def test_unknown_or_mismatched_member_cannot_borrow_another_manifest(self):
        vault,_,_,keys,_,_=self.populated()
        with vault.snapshot_many(keys) as view:
            for key in ((c.sha(b'absent'),keys[0][1]),(keys[0][0],keys[1][1])):
                self.code('SNAPSHOT_MEMBER_UNAVAILABLE',view.documents,*key)
                self.code('SNAPSHOT_MEMBER_UNAVAILABLE',view.manifest,*key)
            self.assertEqual(len(view.keys()),2)

    def test_single_and_batch_leases_mutually_exclude(self):
        vault,_,_,keys,_,_=self.populated()
        with vault.snapshot_many(keys) as view:
            self.code('TRANSACTION_REENTRY',self.snapshot_files,vault,*keys[0])
            self.code('TRANSACTION_REENTRY',self.view,vault,keys)
            self.code('TRANSACTION_REENTRY',vault.seal,c.sha(b'new'),keys[0][1],{'n':b'new'})
            self.code('LEASE_ACTIVE',vault.close)
            view.check(vault)
        with vault.snapshot(*keys[0]):self.code('TRANSACTION_REENTRY',self.view,vault,keys)

    def test_batch_holds_actual_sqlite_reader_lock_and_query_only(self):
        vault,path,_,keys,files,_=self.populated()
        with vault.snapshot_many(keys) as view:
            with self.assertRaises(sqlite3.OperationalError):vault._db.execute('DELETE FROM ev_bodies')
            other=sqlite3.connect(str(path),isolation_level=None,timeout=0.01)
            try:
                other.execute('BEGIN IMMEDIATE')
                other.execute('UPDATE ev_bodies SET body=body')
                with self.assertRaises(sqlite3.OperationalError):other.execute('COMMIT')
                other.execute('ROLLBACK')
            finally:other.close()
            self.assertEqual(view.documents(*keys[1]),files[1])

    def test_expiry_invalidates_entire_view_and_restores_connection(self):
        vault,_,_,keys,_,_=self.populated();tick=[1000]
        with patch('hms_qualification.evidence_vault.connection.time.monotonic_ns',side_effect=lambda:tick[0]):
            with self.assertRaises(VaultError) as caught:
                with vault.snapshot_many(keys,lifetime_ms=1) as view:
                    tick[0]+=1000000
                    for function,args in ((view.keys,()),(view.usage,()),(view.manifest,keys[0]),(view.documents,keys[1])):
                        self.code('SNAPSHOT_UNAVAILABLE',function,*args)
            self.assertEqual(caught.exception.code,'PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE')
        self.assertIsNone(vault._lease);self.assertFalse(vault._db.in_transaction)
        self.assertEqual(self.view(vault,keys)[3]['manifests'],2)

    def test_owner_thread_replacement_and_release_checks(self):
        vault,_,_,keys,_,_=self.populated();foreign=[]
        with vault.snapshot_many(keys) as view:
            self.code('SNAPSHOT_UNAVAILABLE',view.check,object())
            def read_elsewhere():
                try:view.keys()
                except VaultError as error:foreign.append(error.code)
            thread=threading.Thread(target=read_elsewhere);thread.start();thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(foreign,['PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE'])
            vault._lease=object()
            try:self.code('SNAPSHOT_UNAVAILABLE',view.documents,*keys[0])
            finally:vault._lease=view
        self.code('SNAPSHOT_UNAVAILABLE',view.keys)
        self.code('SNAPSHOT_UNAVAILABLE',view.documents,*keys[1])

    def test_selected_body_corruption_never_yields_partial_inventory(self):
        vault,path,_,keys,_,_=self.populated()
        vault._db.execute('UPDATE ev_bodies SET body=? WHERE digest=?',(b'wrong',c.sha(b'bravo')))
        before=path.read_bytes();self.code('BODY_CHANGED',self.view,vault,keys)
        self.assertEqual(path.read_bytes(),before);self.assertIsNone(vault._lease)

    def test_manifest_corruption_is_retained_and_refused(self):
        vault,path,_,keys,_,records=self.populated()
        changed=dict(records[1],scope='forged')
        vault._db.execute('UPDATE ev_manifests SET record=? WHERE sequence=2',(canonical(changed),))
        before=path.read_bytes();self.code('INVALID_RETAINED',self.view,vault,keys)
        self.assertEqual(path.read_bytes(),before)

    def test_prepared_view_access_needs_no_file_or_sql_reads(self):
        vault,_,_,keys,files,records=self.populated()
        with vault.snapshot_many(keys) as view:
            vault._db.set_authorizer(lambda *args:sqlite3.SQLITE_DENY)
            try:
                with patch.object(Path,'open',side_effect=AssertionError('file access in held view')):
                    view.check(vault)
                    self.assertEqual(view.keys(),tuple(sorted(keys)))
                    self.assertEqual(view.manifest(*keys[0]),records[0])
                    self.assertEqual(view.documents(*keys[1]),files[1])
                    self.assertEqual(view.usage()['manifests'],2)
            finally:vault._db.set_authorizer(None)

    def test_joint_commit_checks_complete_batch_after_admission_rows(self):
        journal,policy,wire=self.joint();vault,_,_,keys,_,_=self.populated(journal=journal)
        with vault.snapshot_many(keys) as view:
            def check():
                self.assertEqual(len(journal._db.execute('SELECT id FROM operations LIMIT 2').fetchall()),1)
                self.assertEqual(view.keys(),tuple(sorted(keys)));view.check(vault)
                self.notes.append('whole batch checked after admission writes')
            self.arm(journal,policy,check)
            result=journal.submit(CONTEXT,wire)
        self.assertEqual(result['state'],'accepted')
        self.assertEqual(journal.submit(CONTEXT,wire)['id'],result['id'])

    def test_joint_missing_member_never_admits_available_member_alone(self):
        journal,policy,wire=self.joint();vault,_,_,keys,_,_=self.populated(journal=journal)
        with self.assertRaises(VaultError) as caught:
            with vault.snapshot_many((keys[0],(c.sha(b'missing'),keys[1][1]))) as view:
                self.arm(journal,policy,lambda:view.check(vault));journal.submit(CONTEXT,wire)
        self.assertEqual(caught.exception.code,'PAT_EVIDENCE_VAULT_MANIFEST_UNAVAILABLE')
        self.assertEqual(journal._db.execute('SELECT count(*) FROM operations').fetchone()[0],0)
        self.notes.append('no partial selection or admission')

    def test_joint_expiry_at_commit_rolls_back_all_admission_rows(self):
        journal,policy,wire=self.joint();vault,_,_,keys,_,_=self.populated(journal=journal);tick=[1000]
        with patch('hms_qualification.evidence_vault.connection.time.monotonic_ns',side_effect=lambda:tick[0]):
            with self.assertRaises(VaultError) as caught:
                with vault.snapshot_many(keys,lifetime_ms=1) as view:
                    self.arm(journal,policy,lambda:view.check(vault))
                    journal.submission_record=lambda *args:tick.__setitem__(0,1001000)
                    journal.submit(CONTEXT,wire)
            self.assertEqual(caught.exception.code,'PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE')
        counts={name:journal._db.execute('SELECT count(*) FROM '+name).fetchone()[0]
            for name in ('operations','claims','resource_floors','replay_keys','events')}
        self.assertTrue(all(value==0 for value in counts.values()));self.notes.append(counts)

    def test_joint_lease_cleanup_failure_after_commit_preserves_original_replay(self):
        journal,policy,wire=self.joint();vault,_,_,keys,_,_=self.populated(journal=journal);tick=[1000]
        with patch('hms_qualification.evidence_vault.connection.time.monotonic_ns',side_effect=lambda:tick[0]):
            with self.assertRaises(VaultError) as caught:
                with vault.snapshot_many(keys,lifetime_ms=1) as view:
                    self.arm(journal,policy,lambda:view.check(vault))
                    original=journal.submit(CONTEXT,wire)
                    tick[0]+=1000000
            self.assertEqual(caught.exception.code,'PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE')
        def forbidden(*args):self.fail('historical replay attempted fresh admission')
        policy.admit=forbidden;journal.clock_ms=forbidden
        self.assertEqual(journal.submit(CONTEXT,wire)['id'],original['id'])
        self.assertEqual(journal._db.execute('SELECT count(*) FROM operations').fetchone()[0],1)
        self.notes.append(dict(originalId=original['id'],originalReplay=True))

    def test_body_exception_cleans_batch_without_mutating_store(self):
        vault,path,_,keys,_,_=self.populated();before=path.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'original body error'):
            with vault.snapshot_many(keys):raise RuntimeError('original body error')
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(self.view(vault,keys)[3]['documents'],4)
