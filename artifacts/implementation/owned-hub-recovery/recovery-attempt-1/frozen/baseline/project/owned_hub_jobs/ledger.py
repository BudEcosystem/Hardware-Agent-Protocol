"""Bounded private snapshot authority; not the public HMS storage profile."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat

IMPORTED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

from .contracts import (JobError, MAX_KEYS, STATE_BYTES, canonical, parse, exact,
                        require, integer, request, request_digest, identifier,
                        typed_result, expected_result)

PHASES = {'admitted': {'launching', 'settled'},
          'launching': {'associated', 'stopping', 'settled'},
          'associated': {'released', 'stopping', 'settled'},
          'released': {'stopping', 'settled'},
          'stopping': {'settled'}, 'settled': set()}
ROW_FIELDS = {'id', 'request', 'digest', 'nonce', 'phase', 'history', 'lease',
              'ownerSession', 'pid', 'releaseIntent', 'cancelRequested', 'reason', 'receipt'}


def safe(fd, maximum=STATE_BYTES):
    s = os.fstat(fd)
    require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and
            stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1 and
            0 <= s.st_size <= maximum, 'UNSAFE_FILE')
    return s


def read(directory, name, maximum=STATE_BYTES):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        s = safe(fd, maximum)
        body = bytearray()
        while len(body) <= s.st_size:
            part = os.read(fd, min(4096, s.st_size + 1 - len(body)))
            if not part:
                break
            body.extend(part)
        require(len(body) == s.st_size, 'FILE_CHANGED')
        return bytes(body)
    finally:
        os.close(fd)


def write_all(fd, body):
    view = memoryview(body)
    while view:
        amount = os.write(fd, view)
        require(amount > 0, 'SHORT_WRITE')
        view = view[amount:]


def validate_row(row):
    exact(row, ROW_FIELDS)
    require(len(canonical(row)) <= 3500, 'ROW_CAPACITY')
    r = request(row['request'])
    require(row['id'] == identifier(r['key']) and row['digest'] == request_digest(r), 'ROW_ASSOCIATION')
    for name in ('nonce', 'ownerSession'):
        require(type(row[name]) is str and re.fullmatch(r'[0-9a-f]{32}', row[name]), 'ROW_IDENTITY')
    history = row['history']
    require(type(history) is list and 1 <= len(history) <= 6 and
            history[0] == 'admitted' and history[-1] == row['phase'], 'ROW_HISTORY')
    require(all(type(x) is str and x in PHASES for x in history), 'ROW_PHASE')
    require(all(b in PHASES[a] for a, b in zip(history, history[1:])), 'ROW_TRANSITION')
    require(type(row['releaseIntent']) is bool and type(row['cancelRequested']) is bool, 'ROW_BOOLEAN')
    require(row['releaseIntent'] == ('released' in history), 'ROW_RELEASE')
    require(row['reason'] is None or type(row['reason']) is str and
            re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', row['reason']), 'ROW_REASON')
    if row['lease'] is not None:
        exact(row['lease'], ('device', 'inode'))
        for value in row['lease'].values():
            integer(value, 0, 2**64-1)
    require((row['lease'] is not None) == ('launching' in history), 'ROW_LEASE')
    if row['pid'] is not None:
        integer(row['pid'], 1, 2**31-1)
    require((row['pid'] is not None) == ('associated' in history), 'ROW_PROCESS')
    require((row['receipt'] is not None) == (row['phase'] == 'settled'), 'ROW_RECEIPT')
    if row['receipt'] is not None:
        value = row['receipt']
        exact(value, ('execution', 'cancellation', 'mayHaveActed', 'processExitCode',
                      'writerLeaseQuiescent', 'observedLiveGroupMembers', 'streamEof',
                      'outputValidated', 'result', 'reason', 'recovered', 'observedProcesses',
                      'evidenceKind', 'resourceReleased'))
        require(value['execution'] in ('completed', 'failed', 'canceled', 'unknown', 'not_started'), 'RECEIPT_EXECUTION')
        require(value['cancellation'] in ('none', 'confirmed', 'not_effective', 'unknown'), 'RECEIPT_CANCEL')
        require(value['evidenceKind'] == 'owned-host-process' and value['resourceReleased'] is True and
                value['writerLeaseQuiescent'] is True, 'RECEIPT_EVIDENCE')
        require(value['reason'] == row['reason'], 'RECEIPT_REASON')
        for name in ('mayHaveActed', 'outputValidated', 'recovered'):
            require(type(value[name]) is bool, 'RECEIPT_BOOLEAN')
        require(value['mayHaveActed'] == row['releaseIntent'], 'RECEIPT_RELEASE')
        require(value['streamEof'] is None or type(value['streamEof']) is bool, 'RECEIPT_STREAM')
        require(value['observedLiveGroupMembers'] is None or
                type(value['observedLiveGroupMembers']) is int and value['observedLiveGroupMembers'] == 0,
                'RECEIPT_GROUP')
        if value['processExitCode'] is not None:
            integer(value['processExitCode'], -128, 255)
        require(type(value['observedProcesses']) is list and len(value['observedProcesses']) <= 16, 'RECEIPT_PROCESSES')
        for process in value['observedProcesses']:
            exact(process, ('pid', 'startTicks', 'session'))
            integer(process['pid'], 1, 2**31-1)
            integer(process['startTicks'], 0, 2**64-1)
            integer(process['session'], 1, 2**31-1)
        if value['execution'] == 'completed':
            typed_result(value['result'])
            require(row['releaseIntent'] and value['outputValidated'] and value['processExitCode'] == 0 and
                    not value['recovered'] and value['streamEof'] is True and
                    value['observedLiveGroupMembers'] == 0 and
                    value['result'] == expected_result(r['input']), 'RECEIPT_SUCCESS')
        else:
            require(value['result'] is None and value['outputValidated'] is False, 'RECEIPT_RESULT')
        if value['execution'] == 'not_started':
            require(not row['releaseIntent'], 'RECEIPT_NOT_STARTED')
        if value['cancellation'] == 'confirmed':
            require(row['cancelRequested'] and value['execution'] == 'canceled' and not value['recovered'], 'RECEIPT_CANCEL')
    return row


def successor(old, new):
    require(set(old) <= set(new) and len(new) <= len(old)+1, 'STATE_REMOVED_KEY')
    changed = 0
    for name, before in old.items():
        after = new[name]
        if canonical(before) == canonical(after):
            continue
        changed += 1
        require(before['phase'] != 'settled', 'TERMINAL_IMMUTABLE')
        for field in ('id', 'request', 'digest', 'nonce', 'ownerSession'):
            require(canonical(before[field]) == canonical(after[field]), 'ORIGINAL_KEY_IMMUTABLE')
        require(after['history'][:len(before['history'])] == before['history'] and
                len(after['history']) <= len(before['history'])+1, 'HISTORY_ROLLBACK')
        require(not before['releaseIntent'] or after['releaseIntent'], 'RELEASE_ROLLBACK')
        require(not before['cancelRequested'] or after['cancelRequested'], 'CANCEL_ROLLBACK')
        for field in ('lease', 'pid', 'reason'):
            require(before[field] is None or before[field] == after[field], 'ASSOCIATION_IMMUTABLE')
    for name in set(new)-set(old):
        row = new[name]; changed += 1
        require(row['phase'] == 'admitted' and row['history'] == ['admitted'] and
                row['lease'] is None and row['pid'] is None and row['reason'] is None and
                not row['releaseIntent'] and not row['cancelRequested'], 'NEW_KEY_STATE')
    require(changed <= 1, 'MULTIPLE_ROW_CHANGE')


class Ledger:
    def __init__(self, root, *, create=False):
        self.root = Path(root).absolute()
        self.fd = self.owner = None
        self.poisoned = False
        try:
            if create:
                self.root.mkdir(mode=0o700)
            self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            s = os.fstat(self.fd)
            require(s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700, 'UNSAFE_DIRECTORY')
            self.owner = os.open('owner.lock', os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0),
                                 0o600, dir_fd=self.fd)
            safe(self.owner, 0)
            try:
                fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JobError('OWNER_BUSY') from error
            if create:
                self.state = {'profile': 'hms.host.cpu-ledger/0.1', 'generation': -1, 'rows': {}}
                self.commit({})
            else:
                self.state = self._load()
            self._inventory()
            # Only an uncommitted bounded temporary file may be discarded.
            try:
                read(self.fd, 'state.tmp')
            except FileNotFoundError:
                pass
            else:
                os.unlink('state.tmp', dir_fd=self.fd); os.fsync(self.fd)
        except BaseException:
            self.close()
            raise

    def _inventory(self):
        names = os.listdir(self.fd)
        require(len(names) <= MAX_KEYS+4, 'FILE_COUNT')
        for name in names:
            require(name in ('owner.lock', 'state.0', 'state.1', 'state.tmp') or
                    re.fullmatch(r'lease-[0-9a-f]{64}', name), 'UNEXPECTED_FILE')
            read(self.fd, name, 0 if name.startswith('lease-') or name == 'owner.lock' else STATE_BYTES)

    def _load(self):
        values = []
        for slot in (0, 1):
            try:
                body = read(self.fd, 'state.'+str(slot))
            except FileNotFoundError:
                continue
            envelope = parse(body); exact(envelope, ('state', 'sha256'))
            value = envelope['state']
            require(hashlib.sha256(canonical(value)).hexdigest() == envelope['sha256'], 'STATE_CHECKSUM')
            exact(value, ('profile', 'generation', 'rows'))
            require(value['profile'] == 'hms.host.cpu-ledger/0.1', 'STATE_PROFILE')
            integer(value['generation'], 0, 2**63-1)
            require(value['generation'] % 2 == slot, 'STATE_SLOT')
            self._rows(value['rows'])
            require(value['generation'] != 0 or value['rows'] == {}, 'STATE_ORIGIN')
            values.append(value)
        require(values, 'STATE_MISSING')
        values.sort(key=lambda value: value['generation'])
        require((len(values) == 1 and values[0]['generation'] == 0) or
                (len(values) == 2 and values[1]['generation'] == values[0]['generation']+1), 'STATE_GENERATION')
        if len(values) == 2:
            successor(values[0]['rows'], values[1]['rows'])
        return values[-1]

    @staticmethod
    def _rows(rows):
        require(type(rows) is dict and len(rows) <= MAX_KEYS, 'KEY_CAPACITY')
        for name, row in rows.items():
            validate_row(row); require(name == row['id'], 'STATE_KEY')
        require(sum(row['phase'] != 'settled' for row in rows.values()) <= 1, 'ACTIVE_CAPACITY')

    def commit(self, rows):
        require(not self.poisoned, 'CONTROL_STORAGE_UNRESOLVED')
        self._rows(rows)
        successor(self.state['rows'], rows)
        generation = self.state['generation']+1
        integer(generation, 0, 2**63-1)
        state = dict(profile='hms.host.cpu-ledger/0.1', generation=generation, rows=rows)
        body = canonical({'state': state, 'sha256': hashlib.sha256(canonical(state)).hexdigest()})
        require(len(body) <= STATE_BYTES, 'CONTROL_CAPACITY')
        fd = None
        try:
            fd = os.open('state.tmp', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            safe(fd, 0); write_all(fd, body); os.fsync(fd); os.close(fd); fd = None
            os.replace('state.tmp', 'state.'+str(generation % 2), src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
            self.state = parse(canonical(state))
        except BaseException:
            self.poisoned = True
            raise
        finally:
            if fd is not None:
                os.close(fd)

    def get(self, name):
        row = self.state['rows'].get(name)
        return None if row is None else parse(canonical(row))

    def save(self, row, phase=None):
        row = parse(canonical(row))
        old = self.get(row['id'])
        if phase is not None:
            require(old is not None and phase in PHASES[old['phase']], 'PHASE')
            row['phase'] = phase; row['history'].append(phase)
        elif old is not None:
            require(row['phase'] == old['phase'] and row['history'] == old['history'], 'PHASE')
        rows = parse(canonical(self.state['rows'])); rows[row['id']] = row
        self.commit(rows)
        return self.get(row['id'])

    def close(self):
        for name in ('owner', 'fd'):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd); setattr(self, name, None)
