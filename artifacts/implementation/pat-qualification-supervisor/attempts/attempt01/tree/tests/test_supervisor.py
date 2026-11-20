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
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms import pat_simulation_worker as worker
from hms.pat_simulation_contracts import CEILINGS
from hms.pat_simulation_evidence import reduce_attempt
from supervisor_contracts import parse_request, prepare_request, request_digest, run_key, DEFAULT_LIMITS
from attempt_ledger import AttemptLedger
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

    def test_retention_admission_is_logical_and_never_deletes(self):
        sup = self.supervisor(); original = case_request('quota')
        original['limits']['maxRetainedBytes'] = original['limits']['attemptReservationBytes']
        self.code('QUALIFICATION_RETENTION_FULL', sup.ledger.admit, original)
        self.assertEqual(sup.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(), (0,))

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
        self.assertEqual(bundle['evaluatorResult']['unresolvedEffects'], 0)
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
