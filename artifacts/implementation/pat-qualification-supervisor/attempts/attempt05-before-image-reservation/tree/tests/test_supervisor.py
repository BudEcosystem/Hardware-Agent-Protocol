"""Durable ownership and archived replay tests; actual original SQLite worker only."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import signal
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms import pat_simulation_worker as worker
from hms.pat_simulation_contracts import CEILINGS
from hms.pat_simulation_evidence import reduce_attempt
from supervisor_contracts import parse_request, prepare_request, request_digest, run_key, DEFAULT_LIMITS
from supervisor_contracts import runtime_files, SOURCE_FILES
from attempt_ledger import AttemptLedger, tree_usage
from qualification_supervisor import QualificationSupervisor, _directory, _evidence
from fixture_support import request

LAST_REPORT = {'profile': 'hms.staged-supervisor-tests/0.1', 'workers': [], 'crashes': []}
BASE = None
ROOTS = []


def setUpModule():
    global BASE
    assert worker._ROOT.resolve() == Path(os.environ['EXPECTED_HMS_ROOT']).resolve()
    BASE = request()


def case_request(name):
    value = copy.deepcopy(BASE); value['trust']['runId'] = name
    return value


class SupervisorTests(unittest.TestCase):
    def root(self):
        path = Path(tempfile.mkdtemp(prefix='hms-qualification-case-'))
        ROOTS.append(path)
        return path

    def supervisor(self):
        value = QualificationSupervisor(self.root(), create=True)
        self.addCleanup(lambda: value.close() if value.ledger.db is not None and not value._owned else None)
        return value

    def code(self, code, function, *args):
        with self.assertRaises(JournalError) as caught: function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_imported_code_is_exact_copied_tree(self):
        self.assertEqual(worker._ROOT.resolve(), Path(os.environ['EXPECTED_HMS_ROOT']).resolve())
        self.assertNotIn('/home/bud/Desktop/bud/hms/hms', worker.__file__)

    def test_extensionless_runtime_resources_are_pinned_and_retained(self):
        rows = runtime_files()
        extensionless = [path for path, _, _ in rows if path.startswith('jsonschema_specifications/schemas/') and not Path(path).suffix]
        self.assertGreaterEqual(len(extensionless), 14)
        self.assertTrue(all(hashlib.sha256(source.read_bytes()).hexdigest() == expected for _,source,expected in rows))

    def test_closed_request_detached_and_exact_types(self):
        parsed = parse_request(BASE); parsed['trust']['runId'] = 'changed'
        self.assertNotEqual(parsed, BASE)
        for path, value in [(('command',), []), (('trust','evaluator'), []),
            (('limits','maxArchives'), True), (('limits','maxArchives'), 32.0),
            (('trust','input','configuration','revision'), 1.0)]:
            bad = copy.deepcopy(BASE); target = bad
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(JournalError): parse_request(bad)

    def test_exact_admission_replay_conflict_and_mutation_detachment(self):
        sup = self.supervisor(); original = case_request('exact')
        first, created = sup.ledger.admit(original); self.assertTrue(created)
        original['trust']['runId'] = 'mutated'
        replay, created = sup.ledger.admit(case_request('exact')); self.assertFalse(created)
        self.assertEqual(first, replay)
        changed = case_request('exact'); changed['trust']['input']['configuration']['revision'] = 2
        self.code('KEY_CONFLICT', sup.ledger.admit, changed)
        self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (1,))

    def test_one_active_and_one_owner(self):
        sup = self.supervisor(); sup.ledger.admit(case_request('one'))
        self.code('QUALIFICATION_BUSY', sup.ledger.admit, case_request('two'))
        self.code('QUALIFICATION_OWNER_BUSY', QualificationSupervisor, sup.ledger.root)

    def test_concurrent_exact_and_conflicting_calls_do_not_launch_twice(self):
        sup = self.supervisor(); value = case_request('concurrent')
        admitted = threading.Event(); release = threading.Event(); errors = []
        def checkpoint(phase, row):
            if phase == 'admitted':
                admitted.set(); release.wait(10); raise RuntimeError('original test stops before launch')
        sup._checkpoint = checkpoint
        def run():
            try: sup.execute(value)
            except Exception as error: errors.append(str(error))
        thread = threading.Thread(target=run); thread.start()
        try:
            self.assertTrue(admitted.wait(10))
            replay = sup.execute(value); self.assertEqual(replay['record']['state'],'admitted')
            changed = copy.deepcopy(value); changed['trust']['input']['configuration']['revision'] = 2
            self.code('KEY_CONFLICT',sup.execute,changed)
            self.code('QUALIFICATION_BUSY',sup.execute,case_request('concurrent-other'))
        finally: release.set(); thread.join(10)
        self.assertEqual(errors,['original test stops before launch'])
        self.assertFalse(thread.is_alive())
        self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(1,))
        self.assertFalse(sup.recover(replay['record']['attemptId'])['record']['archive']['transportComplete'])

    def test_retention_admission_is_logical_and_never_deletes(self):
        sup = self.supervisor(); original = case_request('quota')
        original['limits']['maxRetainedBytes'] = original['limits']['attemptReservationBytes']
        self.code('QUALIFICATION_RETENTION_FULL', sup.ledger.admit, original)
        self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (0,))

    def test_first_private_image_bytes_are_reserved_before_admission(self):
        sup=self.supervisor();value=case_request('image-reservation')
        image_bytes=sum((worker._ROOT/row['path']).stat().st_size for row in worker._IMPORTED_IDENTITY['sources'])
        image_bytes+=sum(source.stat().st_size for _,source,_ in runtime_files())
        image_bytes+=sum((Path(__file__).parents[1]/'src'/name).stat().st_size for name in SOURCE_FILES)
        usage=tree_usage(sup.ledger.root,max_files=10000,max_bytes=DEFAULT_LIMITS['maxRetainedBytes'])
        value['limits']['maxRetainedBytes']=usage['logicalBytes']+value['limits']['attemptReservationBytes']+image_bytes-1
        # Refusal must precede any attempt row or image/producer work. The old
        # implementation reaches this launch seam, proving under-reservation.
        with patch.object(sup,'_launch',return_value={'wrong':'admitted without image reservation'}) as launch:
            self.code('QUALIFICATION_RETENTION_FULL',sup.execute,value)
        launch.assert_not_called()
        self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(0,))
        self.assertEqual(list(sup.ledger.root.glob('code-*')),[])

    def test_partial_schema_and_symlink_root_refused(self):
        root = self.root(); db = root / 'attempts.db'
        conn = sqlite3.connect(db); conn.execute('CREATE TABLE qs_meta(version)'); conn.commit(); conn.close(); db.chmod(0o600)
        self.code('QUALIFICATION_SCHEMA_INVALID', lambda: QualificationSupervisor(root, create=True))
        link = self.root() / 'link'; link.symlink_to(root)
        with self.assertRaises(JournalError): QualificationSupervisor(link)

    def test_unarmed_recovery_is_terminal_and_never_reruns(self):
        sup = self.supervisor(); row, _ = sup.ledger.admit(case_request('unarmed'))
        root = sup.ledger.root; sup.close()
        sup = QualificationSupervisor(root); self.addCleanup(sup.close)
        self.assertEqual(sup.status(row['record']['attemptId'])['state'], 'interrupted')
        archived = sup.recover(row['record']['attemptId'])
        self.assertIsNone(archived['returnBytes'])
        self.assertFalse(archived['record']['archive']['transportComplete'])
        with patch('qualification_supervisor.validate_fresh', side_effect=AssertionError('must replay')):
            self.assertEqual(sup.execute(case_request('unarmed')), archived)

    def test_held_replaced_or_missing_armed_lease_never_means_stopped(self):
        sup = self.supervisor(); row, _ = sup.ledger.admit(case_request('lease'))
        identifier = row['record']['attemptId']; directory = _directory(sup.ledger.fd, identifier, create=True)
        fd = os.open('writer.lease', os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory)
        self.addCleanup(os.close, fd); self.addCleanup(os.close, directory)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); info = os.fstat(fd)
        sup.ledger.change(identifier, 'launching', lease={'device':str(info.st_dev),'inode':str(info.st_ino)})
        self.code('QUALIFICATION_PRODUCER_ACTIVE', sup.recover, identifier)
        os.unlink('writer.lease', dir_fd=directory)
        self.code('QUALIFICATION_OWNERSHIP_UNKNOWN', sup.recover, identifier)
        other = os.open('writer.lease', os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory); os.close(other)
        self.code('QUALIFICATION_OWNERSHIP_UNKNOWN', sup.recover, identifier)
        self.code('QUALIFICATION_BUSY', sup.ledger.admit, case_request('next'))

    def test_malformed_bounded_return_is_archived_exactly_without_success(self):
        for raw in (b'',b'not canonical JSON'):
            sup = self.supervisor(); row,_ = sup.ledger.admit(case_request('malformed'))
            identifier=row['record']['attemptId']; directory=_directory(sup.ledger.fd,identifier,create=True)
            try:
                fd=os.open('writer.lease',os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600,dir_fd=directory)
                info=os.fstat(fd);os.close(fd)
                sup.ledger.change(identifier,'launching',lease={'device':str(info.st_dev),'inode':str(info.st_ino)})
                fd=os.open('worker-return.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=directory)
                os.write(fd,raw);os.close(fd)
            finally:os.close(directory)
            result=sup.recover(identifier)
            self.assertEqual(result['returnBytes'],raw)
            self.assertFalse(result['record']['archive']['transportComplete'])
            self.assertIsNotNone(result['record']['archive']['returnValidationFailure'])

    def test_real_worker_archive_replay_restart_and_full_reduction(self):
        sup = self.supervisor(); value = case_request('pass')
        row = sup.execute(value); archive = row['record']['archive']
        LAST_REPORT['workers'].append({'kind':'complete','root':str(sup.ledger.root),'row':row['record'],
            'return':json.loads(row['returnBytes']) if row['returnBytes'] else None})
        self.assertTrue(archive['transportComplete'], row)
        self.assertFalse(archive['semanticQualificationVerified'])
        result = json.loads(row['returnBytes']); self.assertEqual(result['outcome'], 'passed')
        self.assertFalse(archive['totalDiskQuotaEnforced']); self.assertIsNone(archive['unresolvedEffects'])
        path = sup.ledger.root / row['record']['attemptId'] / 'output/evidence'
        files = [{'path':'evidence/'+p.name, 'body':p.read_bytes()} for p in sorted(path.glob('*.json'))]
        bundle = reduce_attempt(value['trust'], row['returnBytes'], files)
        manifest = json.loads(bundle['documents'][bundle['groupDigest']])
        self.assertEqual(len(manifest['cases']), 10)
        self.assertEqual(manifest['binding']['runId'], value['trust']['runId'])
        root = sup.ledger.root; identifier = row['record']['attemptId']; sup.close()
        sup = QualificationSupervisor(root); self.addCleanup(sup.close)
        with patch('qualification_supervisor.validate_fresh', side_effect=AssertionError('must replay')):
            replay = sup.execute(value)
        self.assertEqual(replay, row)
        (root / identifier / 'worker-return.json').write_bytes(b'corrupted external diagnostic')
        self.assertEqual(sup.execute(value)['returnBytes'], row['returnBytes'])
        self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (1,))

    def test_nonpassing_worker_return_retained_without_fabricating_zero(self):
        sup = self.supervisor(); value = request('nonpass', worker_limits={**CEILINGS,'maxOutputBytes':1})
        row = sup.execute(value)
        LAST_REPORT['workers'].append({'kind':'output-refusal','root':str(sup.ledger.root),'row':row['record'],
            'return':json.loads(row['returnBytes']) if row['returnBytes'] else None})
        self.assertIsNotNone(row['returnBytes'], row)
        result = json.loads(row['returnBytes']); self.assertEqual(result['outcome'], 'inconclusive')
        self.assertIsNone(result['unresolvedEffects']); self.assertIsNone(row['record']['archive']['unresolvedEffects'])
        self.assertFalse(row['record']['archive']['transportComplete'])
        self.assertFalse(row['record']['archive']['semanticQualificationVerified'])

    def test_parent_deadline_retains_unknown_and_stops_only_owned_handle(self):
        sup = self.supervisor(); value = request('deadline', worker_limits={**CEILINGS,'workerDeadlineMs':1})
        row = sup.execute(value)
        LAST_REPORT['workers'].append({'kind':'supervisor-deadline','root':str(sup.ledger.root),'row':row['record']})
        self.assertEqual(row['record']['state'], 'archived', row)
        self.assertEqual(row['record']['archive']['supervisorReason'], 'SUPERVISOR_DEADLINE')
        self.assertFalse(row['record']['archive']['transportComplete'])
        self.assertIsNone(row['record']['archive']['unresolvedEffects'])

    def test_pidfd_acquisition_failure_retains_live_process_ownership(self):
        sup=self.supervisor(); value=case_request('pidfd-failure'); captured=[]
        original=subprocess.Popen; open_pidfd=os.pidfd_open
        def spawn(*args,**kwargs):
            process=original(*args,**kwargs);captured.append(process);return process
        try:
            with patch('qualification_supervisor.subprocess.Popen',side_effect=spawn), \
                 patch('qualification_supervisor.os.pidfd_open',side_effect=OSError('controlled descriptor exhaustion')):
                with self.assertRaises(OSError):sup.execute(value)
            row=sup.lookup(*run_key(value));identifier=row['record']['attemptId']
            self.assertIn(identifier,sup._owned,'successful spawn must retain its original live Popen before pidfd creation')
            self.code('QUALIFICATION_PROCESS_UNSETTLED',sup.close)
        finally:
            # The original test retains the actual Popen even in the buggy
            # implementation. Acquire its pidfd before wait/reaping, never from
            # a persisted PID; this is controlled cleanup, not restart recovery.
            if captured:
                process=captured[0];fd=open_pidfd(process.pid,0)
                try:signal.pidfd_send_signal(fd,signal.SIGTERM);process.wait(timeout=5)
                finally:os.close(fd)
                for stream in (process.stdout,process.stderr):stream.close()
                if sup.ledger.db is not None:
                    row=sup.lookup(*run_key(value))
                    result=sup.recover(row['record']['attemptId'])
                    LAST_REPORT['workers'].append({'kind':'pidfd-acquisition-failure','root':str(sup.ledger.root),
                        'cleanupUsedOriginalPopen':True,'cleanupExitCode':process.returncode,'row':result['record']})

    def test_exit_eof_after_selector_wait_cannot_escape_deadline(self):
        sup=self.supervisor();row,_=sup.ledger.admit(case_request('late-eof'));identifier=row['record']['attemptId']
        sup.ledger.change(identifier,'launching');sup.ledger.change(identifier,'running')
        row=sup.ledger.get(identifier);directory=_directory(sup.ledger.fd,identifier,create=True)
        readers=[]
        for _ in range(2):
            read,write=os.pipe();os.close(write);readers.append(os.fdopen(read,'rb'))
        process=SimpleNamespace(stdout=readers[0],stderr=readers[1],poll=lambda:0)
        fd=os.open('/dev/null',os.O_RDONLY);sup._owned[identifier]=(process,fd)
        clock=[.9]
        class Selector:
            def __init__(self):self.items={}
            def register(self,stream,event,name):self.items[stream]=name
            def unregister(self,stream):self.items.pop(stream)
            def select(self,timeout):
                clock[0]=1.1
                return [(SimpleNamespace(fileobj=stream,data=name),1) for stream,name in list(self.items.items())]
            def get_map(self):return self.items
            def close(self):pass
        try:
            with patch('qualification_supervisor.selectors.DefaultSelector',Selector), \
                 patch('qualification_supervisor.time.monotonic',side_effect=lambda:clock[0]), \
                 patch('qualification_supervisor.signal.pidfd_send_signal',side_effect=AssertionError('already exited')), \
                 patch.object(sup,'_archive_if_quiescent',side_effect=lambda row,**kw:kw) as archive:
                # Default worker deadline is60s: starts at-59, prewait sample.9,
                # postwait sample1.1. The owned process is then exit0+EOF.
                result=sup._collect(row,directory,-59)
            self.assertEqual(result['reason'],'SUPERVISOR_DEADLINE')
        finally:
            os.close(directory)
            for stream in readers:
                if not stream.closed:stream.close()
            if identifier in sup._owned:os.close(sup._owned.pop(identifier)[1])

    def test_hard_process_crash_windows_no_replacement_and_exact_archive(self):
        for phase in ('admitted','launching','spawned','producer_settled','archived'):
            with self.subTest(phase=phase):
                root = self.root(); value = case_request('crash:'+phase)
                source = root / 'request.json'; source.write_bytes(canonical(value)); source.chmod(0o600)
                result = subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('crash_driver.py')),
                    str(root),str(source),phase], cwd=Path(__file__).parents[1], capture_output=True, timeout=90,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
                self.assertEqual(result.returncode,91,(phase,result.stdout,result.stderr))
                sup = QualificationSupervisor(root); self.addCleanup(sup.close)
                row = sup.lookup(*run_key(value)); identifier = row['record']['attemptId']
                if phase == 'spawned':
                    self.code('QUALIFICATION_PRODUCER_ACTIVE', sup.recover, identifier)
                deadline = time.monotonic()+70
                while row['record']['state'] != 'archived':
                    try: row = sup.recover(identifier)
                    except JournalError as error:
                        self.assertEqual(error.code,'QUALIFICATION_PRODUCER_ACTIVE')
                        self.assertLess(time.monotonic(),deadline)
                        time.sleep(.05)
                LAST_REPORT['crashes'].append({'phase':phase,'root':str(root),'row':row['record'],
                    'return':json.loads(row['returnBytes']) if row['returnBytes'] else None,
                    'crashExitCode':result.returncode,'stdout':result.stdout.decode(),'stderr':result.stderr.decode()})
                if phase == 'archived': self.assertTrue(row['record']['archive']['transportComplete'])
                else:
                    self.assertFalse(row['record']['archive']['transportComplete'])
                    self.assertIsNone(row['record']['archive']['exitCode'])
                if phase in ('spawned','producer_settled','archived'): self.assertIsNotNone(row['returnBytes'])
                with patch('qualification_supervisor.validate_fresh', side_effect=AssertionError('must replay')):
                    self.assertEqual(sup.execute(value),row)
                self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(1,))
                sup.close()
