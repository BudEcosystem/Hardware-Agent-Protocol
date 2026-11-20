"""Fresh compact-store layout, retained state, rollback and owner recovery."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import Context, Journal, JournalError
from hms.synthetic_io_board import SyntheticIoBoard
from hms.synthetic_io_runtime import IoRuntime
from test_io_synthetic_provider import SyntheticIoProviderTests
from test_pat_io_group_worker import GroupFixture

PROFILE='hms.sqlite.compact/0.1'


class StorageProfileInputTests(unittest.TestCase):
    def test_unsupported_profiles_and_page_sizes_refuse_before_opening_state(self):
        with patch('os.open',side_effect=AssertionError('state open')):
            for value in (False,True,1024,{},'unsupported'):
                with self.subTest(profile=value),self.assertRaisesRegex(JournalError,'IO_STORAGE_PROFILE'):
                    IoRuntime('/unused',storage_profile=value)
            for value in (False,True,1024.0,'1024',4096,512):
                with self.subTest(pageSize=value),self.assertRaisesRegex(JournalError,'UNSUPPORTED_DATABASE_PAGE_SIZE'):
                    Journal('/unused',None,clock_ms=lambda:1000,page_size=value)
                with self.subTest(boardPageSize=value),self.assertRaisesRegex(JournalError,'IO_BOARD_PAGE_SIZE'):
                    SyntheticIoBoard('/unused',{},authority_id='a',owner_epoch=1,clock_epoch='c',page_size=value)


class CompactStorageTests(GroupFixture,unittest.TestCase):
    request=SyntheticIoProviderTests.request
    submit=SyntheticIoProviderTests.submit
    status=SyntheticIoProviderTests.status
    receipt=SyntheticIoProviderTests.receipt
    assert_idle=SyntheticIoProviderTests.assert_idle

    def setUp(self):
        self.workspace=Path(tempfile.gettempdir())/self._testMethodName;self.workspace.mkdir(mode=0o700)
        self.runtime=None;self.wall=self.mono=1000;self.owner=Context('owner','simulation:io-hub')
        self.addCleanup(lambda:self.runtime.close()if self.runtime is not None else None)

    def open(self,*,compact=True,label='compact'):
        parent=self.workspace/label;parent.mkdir(mode=0o700);self.directory=parent/'state'
        self.runtime=IoRuntime(self.directory,create=True,owner=self.owner,installation=self.document,
            wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono,storage_profile=PROFILE if compact else None)
        self.namespace=self.runtime.journal.issue_namespace(self.owner,100000)['token']

    def reopen(self,*,compact=True):
        self.runtime.close();self.runtime=None
        self.runtime=IoRuntime(self.directory,installation=self.document,
            wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono,storage_profile=PROFILE if compact else None)

    def pins(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in self.directory.glob('*.db')}

    def assert_layout(self,size):
        for db in (self.runtime.journal._db,self.runtime.io_board.db):
            self.assertEqual(db.execute('PRAGMA page_size').fetchone()[0],size)
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'delete')
            self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],3)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.runtime.journal._db.execute('PRAGMA foreign_keys').fetchone()[0],1)
        for p in self.directory.glob('*.db'):
            with p.open('rb')as stream:header=stream.read(100)
            self.assertEqual(header[:16],b'SQLite format 3\0');self.assertEqual(int.from_bytes(header[16:18],'big'),size)

    def test_fresh_compact_layout_keeps_durability_owner_exclusion_and_rollback(self):
        self.open();self.assert_layout(1024);authority=self.runtime.journal.authority_id
        with self.assertRaisesRegex(JournalError,'OWNER_BUSY'):
            Journal(self.directory/'authority.db',self.runtime.policy,clock_ms=lambda:self.wall,page_size=1024)
        with self.assertRaisesRegex(RuntimeError,'rollback'):
            with self.runtime.journal._transaction():
                self.runtime.journal._db.execute("INSERT INTO meta VALUES ('probe','rollback')")
                raise RuntimeError('rollback')
        self.assertIsNone(self.runtime.journal._db.execute("SELECT 1 FROM meta WHERE key='probe'").fetchone())
        self.reopen();self.assertEqual(self.runtime.journal.authority_id,authority);self.assert_layout(1024)

    def test_default_store_refuses_compact_expectation_without_database_rewrite(self):
        self.open(compact=False,label='default');self.assert_layout(4096)
        self.runtime.close();self.runtime=None;before=self.pins()
        with self.assertRaisesRegex(JournalError,'UNSUPPORTED_DATABASE_PAGE_SIZE'):
            IoRuntime(self.directory,installation=self.document,storage_profile=PROFILE,
                wall_clock_ms=lambda:self.wall,monotonic_ms=lambda:self.mono)
        self.assertEqual(self.pins(),before)

    def test_board_mismatch_refuses_without_rewriting_retained_board(self):
        self.open(compact=False,label='default');self.assert_layout(4096)
        board=self.runtime.io_board;args=dict(authority_id=board.authority_id,owner_epoch=board.owner_epoch,clock_epoch=board.clock_epoch)
        path=board.path;self.runtime.close();self.runtime=None;before=self.pins()
        with self.assertRaisesRegex(JournalError,'IO_BOARD_PAGE_SIZE'):
            SyntheticIoBoard(path,self.document,page_size=1024,**args)
        self.assertEqual(self.pins(),before)

    def test_default_opener_preserves_existing_compact_layout(self):
        self.open();authority=self.runtime.journal.authority_id
        self.reopen(compact=False);self.assert_layout(1024);self.assertEqual(self.runtime.journal.authority_id,authority)

    def test_pending_effects_reopen_stop_once_and_reconcile_with_original_claims(self):
        self.open();first=self.submit(duration=100);second=self.submit('sim:gpio6',key='second:active',duration=100)
        self.runtime.tick();session=self.runtime.io_board.session;epoch=self.runtime.journal.owner_epoch
        self.reopen();self.assert_layout(1024)
        self.assertEqual(self.runtime.journal.owner_epoch,epoch+1);self.assertNotEqual(self.runtime.io_board.session,session)
        for operation in (first,second):
            self.assertEqual(self.status(operation)['state'],'outcome_unknown');self.assertTrue(self.status(operation)['claims'])
            self.assertEqual(self.receipt(operation)['result']['reason'],'board_owner_reopened')
            self.assertEqual(self.receipt(operation)['sequence'],2);self.assert_idle(self.receipt(operation))
        self.runtime.tick()
        for operation in (first,second):
            self.assertEqual(self.status(operation)['state'],'canceled');self.assertEqual(self.status(operation)['claims'],[])
        self.assertEqual(self.runtime.io_board.db.execute('SELECT sum(activations),sum(completed),sum(canceled) FROM io_effects').fetchone()[:],(2,0,2))
        self.assertEqual(self.runtime.io_board.db.execute('SELECT count(*) FROM io_receipt_versions').fetchone()[0],4)

    def test_completed_original_key_replays_after_reopen_without_new_effect(self):
        self.open();wire=canonical(self.request());operation=self.runtime.journal.submit(self.owner,wire)
        self.runtime.tick();self.wall+=20;self.mono+=20;self.runtime.tick()
        self.assertEqual(self.status(operation)['state'],'completed');self.reopen();self.assert_layout(1024)
        self.assertEqual(self.runtime.journal.submit(self.owner,wire)['id'],operation['id'])
        self.assertEqual(self.status(operation)['state'],'completed')
        self.assertEqual(self.runtime.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0],1)
        self.assertEqual(self.runtime.io_board.db.execute('SELECT sum(activations),sum(completed),sum(canceled) FROM io_effects').fetchone()[:],(1,1,0))
