"""Control availability and object ownership; these do not establish quotas."""
import copy
import fcntl
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms_qualification.supervisor.authority_ledger import AuthorityAttemptLedger
from hms_qualification.supervisor.io_service_execution import BoundQualificationSupervisor
from hms_qualification.supervisor import storage_binding as storage
from hms_qualification.supervisor import qualification_supervisor as supervision
from hms_qualification.supervisor.supervisor_contracts import write_file,run_key
from test_io_supervisor_contracts import IoSupervisorContractsTests


class StorageBindingTests(IoSupervisorContractsTests):
    def setUp(self):
        self.parent=Path(os.environ['TMPDIR'])/self._testMethodName
        self.parent.mkdir(mode=0o700)

    def fixture(self,label='one'):
        root=self.parent/label;root.mkdir(mode=0o700)
        binding=storage.install_binding(root/'control',root/'bulk')
        service=BoundQualificationSupervisor(root/'control',create=True,storage_binding=binding)
        self.addCleanup(service.close)
        return service,binding

    def reopen(self,service,binding):
        identity=service.ledger.authority_id;service.close()
        reopened=BoundQualificationSupervisor(binding['control']['path'],expected_authority=identity,storage_binding=binding)
        self.addCleanup(reopened.close)
        return reopened

    def arm(self,service):
        row,_=service.ledger.admit(self.request);identifier=row['record']['attemptId']
        directory=supervision._directory(service.ledger.bulk_fd,identifier,create=True)
        write_file(directory,'writer.lease',b'')
        lease=os.open('writer.lease',os.O_RDWR|os.O_NOFOLLOW,dir_fd=directory)
        info=os.fstat(lease)
        service.ledger.change(identifier,'launching',lease=dict(device=str(info.st_dev),inode=str(info.st_ino)))
        return identifier,directory,lease

    def test_setup_rejects_same_nested_and_nonempty_roots(self):
        for control,bulk in [(self.parent/'same',self.parent/'same'),(self.parent/'outer',self.parent/'outer/inner')]:
            with self.assertRaisesRegex(JournalError,'STORAGE_OVERLAP'):storage.install_binding(control,bulk)
            self.assertFalse(control.exists())
        root=self.parent/'occupied';root.mkdir(mode=0o700);(root/'kept').write_bytes(b'original')
        with self.assertRaisesRegex(JournalError,'STORAGE_NOT_EMPTY'):storage.install_binding(root,self.parent/'empty')
        self.assertEqual((root/'kept').read_bytes(),b'original')

    def test_binding_is_detached_versioned_and_in_worker_image(self):
        service,binding=self.fixture()
        self.assertEqual(service.ledger.db.execute('SELECT version,binding FROM qs_meta').fetchall(),[(3,canonical(binding))])
        binding['bulk']['path']='changed'
        detached=service.ledger.storage_binding();detached['control']['path']='changed'
        self.assertNotEqual(service.ledger.storage_binding()['control']['path'],'changed')
        self.assertTrue(service.ledger.bulk_root.is_dir())
        self.assertIn('hms_qualification/supervisor/storage_binding.py',[r[0] for r in supervision._image_rows()])

    def test_wrong_binding_and_authority_leave_active_database_exact(self):
        service,binding=self.fixture();service.ledger.admit(self.request)
        identity=service.ledger.authority_id;service.close()
        path=Path(binding['control']['path'])/'attempts.db';before=path.read_bytes()
        changed=copy.deepcopy(binding);changed['bulkOwner']['inode']=str(int(changed['bulkOwner']['inode'])+1)
        for desc,authority in [(changed,identity),(binding,'supervisor:'+'0'*32)]:
            with self.assertRaises(JournalError):storage.StorageAttemptLedger(path.parent,storage_binding=desc,expected_authority=authority)
            self.assertEqual(path.read_bytes(),before)

    def test_legacy_profiles_and_version_three_refuse_mutual_open(self):
        service,binding=self.fixture();identity=service.ledger.authority_id;service.close()
        path=Path(binding['control']['path'])/'attempts.db';before=path.read_bytes()
        with self.assertRaises(JournalError):AuthorityAttemptLedger(path.parent,expected_authority=identity)
        self.assertEqual(path.read_bytes(),before)
        root=self.parent/'legacy';root.mkdir(mode=0o700)
        second=storage.install_binding(root/'control',root/'bulk')
        legacy=AuthorityAttemptLedger(root/'control',create=True);identity=legacy.authority_id;legacy.close()
        before=(root/'control/attempts.db').read_bytes()
        with self.assertRaises(JournalError):storage.StorageAttemptLedger(root/'control',expected_authority=identity,storage_binding=second)
        self.assertEqual((root/'control/attempts.db').read_bytes(),before)

    def test_sidecars_refused_before_sqlite_open(self):
        for suffix in ('-journal','-wal','-shm'):
            service,binding=self.fixture(suffix);identity=service.ledger.authority_id;service.close()
            root=Path(binding['control']['path']);before=(root/'attempts.db').read_bytes()
            side=root/('attempts.db'+suffix);side.write_bytes(b'retained-unknown-sidecar');side.chmod(0o600)
            with patch.object(sqlite3,'connect',side_effect=AssertionError('automatic recovery')):
                with self.assertRaisesRegex(JournalError,'STORAGE_RECOVERY_REQUIRED'):
                    storage.StorageAttemptLedger(root,expected_authority=identity,storage_binding=binding)
            self.assertEqual((root/'attempts.db').read_bytes(),before)
            self.assertEqual(side.read_bytes(),b'retained-unknown-sidecar')

    def test_cold_control_status_and_original_replay_never_open_missing_bulk(self):
        service,binding=self.fixture();row,_=service.ledger.admit(self.request)
        identity=service.ledger.authority_id;service.close()
        bulk=Path(binding['bulk']['path']);bulk.rename(bulk.with_name('retained-bulk'))
        original=storage._open_root
        def control_only(record):
            self.assertEqual(record,binding['control']);return original(record)
        with patch.object(storage,'_open_root',side_effect=control_only),patch.object(storage,'_Bulk',side_effect=AssertionError('bulk opened')):
            service=BoundQualificationSupervisor(binding['control']['path'],expected_authority=identity,storage_binding=binding)
            self.addCleanup(service.close)
            identifier=row['record']['attemptId'];record=service.status(identifier)
            self.assertEqual(record['history'],['admitted','interrupted'])
            retained=service.ledger.lookup(*run_key(self.request))
            replay,created=service.ledger.admit(self.request)
            self.assertFalse(created);self.assertEqual(replay,retained)
            archived=service.recover(identifier)
            self.assertEqual(archived['record']['archive']['supervisorReason'],'OWNER_LOST')
            self.assertFalse(archived['record']['archive']['transportComplete'])

    def test_missing_bulk_refuses_fresh_admission_before_control_row(self):
        service,binding=self.fixture();bulk=Path(binding['bulk']['path']);bulk.rename(bulk.with_name('retained-bulk'))
        with patch.object(supervision.subprocess,'Popen',side_effect=AssertionError('launch')):
            with self.assertRaisesRegex(JournalError,'BULK_UNAVAILABLE'):service.ledger.admit(self.request)
        self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(0,))

    def test_replaced_bulk_root_cannot_substitute_for_original(self):
        service,binding=self.fixture();bulk=Path(binding['bulk']['path']);bulk.rename(bulk.with_name('retained-bulk'));bulk.mkdir(mode=0o700)
        with self.assertRaisesRegex(JournalError,'STORAGE_CHANGED'):service.ledger.admit(self.request)
        self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(0,))

    def test_bulk_owner_excludes_other_open_file_description(self):
        service,binding=self.fixture();fd=os.open(Path(binding['bulk']['path'])/'bulk.owner',os.O_RDWR)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(JournalError,'BULK_OWNER_BUSY'):service.ledger.bulk_fd
        finally:os.close(fd)

    def test_held_bulk_owner_replacement_is_refused(self):
        service,binding=self.fixture();root=service.ledger.bulk_root;held=service.ledger.bulk_fd
        (root/'bulk.owner').rename(root/'retained-owner');write_file(held,'bulk.owner',b'')
        with self.assertRaisesRegex(JournalError,'STORAGE_CHANGED'):service.ledger.bulk_fd
        self.assertTrue((root/'retained-owner').exists())

    def test_marker_content_mode_and_identity_changes_are_refused(self):
        for kind in ('content','mode','identity'):
            service,binding=self.fixture(kind);root=service.ledger.bulk_root;path=root/'storage.json'
            if kind=='content':path.write_bytes(b'{}')
            elif kind=='mode':path.chmod(0o644)
            else:
                raw=path.read_bytes();path.rename(root/'retained-marker');write_file(service.ledger._bulk_owner.fd,'storage.json',raw)
            with self.assertRaisesRegex(JournalError,'STORAGE_CHANGED'):service.ledger.bulk_fd

    def test_retention_accounts_for_both_roots_and_has_no_quota_claim(self):
        service,binding=self.fixture();bulk=service.ledger.bulk_root
        write_file(service.ledger.fd,'control-extra',b'c'*17);write_file(service.ledger.bulk_fd,'bulk-extra',b'b'*31)
        roots=[Path(binding['control']['path']),bulk]
        files=[p for root in roots for p in root.rglob('*') if p.is_file()]
        usage=service.ledger._retained_usage(max_files=8192,max_bytes=256*1024*1024)
        self.assertEqual(usage,dict(files=len(files),logicalBytes=sum(p.stat().st_size for p in files),totalDiskQuotaEnforced=False))
        request=copy.deepcopy(self.request)
        request['limits']['maxRetainedBytes']=usage['logicalBytes']+request['limits']['attemptReservationBytes']-1
        with self.assertRaisesRegex(JournalError,'RETENTION_FULL'):service.ledger.admit(request)
        self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(0,))

    def test_armed_missing_bulk_retains_uncertainty_and_original_key(self):
        service,binding=self.fixture();identifier,directory,lease=self.arm(service);os.close(lease);os.close(directory)
        bulk=Path(binding['bulk']['path']);bulk.rename(bulk.with_name('retained-bulk'))
        service=self.reopen(service,binding);before=service.ledger.get(identifier)
        with patch.object(supervision.subprocess,'Popen',side_effect=AssertionError('relaunch')):
            with self.assertRaisesRegex(JournalError,'BULK_UNAVAILABLE'):service.recover(identifier)
            replay,created=service.ledger.admit(self.request)
        self.assertFalse(created);self.assertEqual(replay,before)
        self.assertEqual(before['record']['state'],'interrupted');self.assertIsNone(before['record']['archive'])

    def test_inherited_writer_lease_survives_control_owner_loss(self):
        service,binding=self.fixture();identifier,directory,lease=self.arm(service)
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        child=subprocess.Popen([sys.executable,'-I','-B','-c',"import sys; print('held',flush=True); sys.stdin.buffer.read(1)"],
            pass_fds=(lease,),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        os.close(lease);os.close(directory)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout,selectors.EVENT_READ);self.assertTrue(selector.select(5))
                self.assertEqual(child.stdout.readline(),b'held\n')
            service=self.reopen(service,binding)
            with patch.object(supervision.signal,'pidfd_send_signal',side_effect=AssertionError('stored PID authority')):
                with self.assertRaisesRegex(JournalError,'PRODUCER_ACTIVE'):service.recover(identifier)
            self.assertEqual(service.status(identifier)['state'],'interrupted')
            child.stdin.write(b'x');child.stdin.flush();self.assertEqual(child.wait(timeout=5),0)
            result=service.recover(identifier)
            self.assertFalse(result['record']['archive']['transportComplete'])
            self.assertIsNone(result['record']['archive']['unresolvedEffects'])
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
            for pipe in (child.stdin,child.stdout,child.stderr):pipe.close()

    def test_changed_control_root_and_closed_access_refuse(self):
        service,binding=self.fixture();root=Path(binding['control']['path']);root.rename(root.with_name('retained-control'));root.mkdir(mode=0o700)
        with self.assertRaisesRegex(JournalError,'STORAGE_CHANGED'):service.ledger.lookup(*run_key(self.request))
        service.close()
        with self.assertRaisesRegex(JournalError,'LEDGER_CLOSED'):service.ledger.bulk_fd
