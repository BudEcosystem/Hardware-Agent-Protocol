"""Explicit owned control/bulk roots; no quota or physical-reservation claim."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import uuid

from hms.contracts import canonical
from hms.journal import JournalError
from hms.state_path import private_state_directory
from .authority_ledger import AuthorityAttemptLedger, authority_id
from .attempt_ledger import ATTEMPT_SQL, INDEX_SQL, tree_usage
from .supervisor_contracts import SupervisorError, require, document, read_file, write_file, safe_file

PROFILE = 'hms.supervisor.storage-split/0.1'
MAX_BINDING_BYTES = 16384
META_SQL = 'CREATE TABLE qs_meta(version INTEGER NOT NULL CHECK(version=3), authority TEXT NOT NULL CHECK(length(authority)=43), binding BLOB NOT NULL CHECK(length(binding) BETWEEN 1 AND 16384))'


def _object(info):
    return dict(device=str(info.st_dev), inode=str(info.st_ino))


def _identity(value):
    require(type(value) is dict and set(value) == {'device','inode'}, 'QUALIFICATION_STORAGE_BINDING')
    for v in value.values():
        require(type(v) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}',v) is not None and int(v)<2**64,
                'QUALIFICATION_STORAGE_BINDING')


def _path(value):
    require(type(value) is str and 1<=len(value.encode())<=4095 and '\0' not in value and
            os.path.abspath(value)==value and value!='/', 'QUALIFICATION_STORAGE_BINDING')
    return Path(value)


def _root_record(path, fd):
    info=os.fstat(fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,
            'QUALIFICATION_STORAGE_BINDING')
    return dict(path=str(path), uid=info.st_uid, **_object(info))


def _open_root(record):
    path=private_state_directory(record['path'])
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        require(_root_record(path,fd)==record,'QUALIFICATION_STORAGE_CHANGED')
        return fd
    except BaseException:
        os.close(fd);raise


def _manifest(binding):
    return {k:binding[k] for k in ('profile','bindingId','control','bulk')}


def parse_binding(value):
    require(type(value) is dict and set(value)=={'profile','bindingId','control','bulk','bulkOwner','bulkManifest','manifestSha256'},
            'QUALIFICATION_STORAGE_BINDING')
    wire=canonical(value)
    require(len(wire)<=MAX_BINDING_BYTES,'QUALIFICATION_STORAGE_BINDING')
    require(value['profile']==PROFILE and type(value['bindingId']) is str and
            re.fullmatch(r'[0-9a-f]{32}',value['bindingId']) is not None,'QUALIFICATION_STORAGE_BINDING')
    for name in ('control','bulk'):
        row=value[name]
        require(type(row) is dict and set(row)=={'path','uid','device','inode'},'QUALIFICATION_STORAGE_BINDING')
        _path(row['path']);_identity({k:row[k] for k in ('device','inode')})
        require(type(row['uid']) is int and row['uid']==os.getuid(),'QUALIFICATION_STORAGE_BINDING')
    control,bulk=(_path(value[n]['path']) for n in ('control','bulk'))
    require(control!=bulk and control not in bulk.parents and bulk not in control.parents,
            'QUALIFICATION_STORAGE_OVERLAP')
    require((value['control']['device'],value['control']['inode']) !=
            (value['bulk']['device'],value['bulk']['inode']),'QUALIFICATION_STORAGE_OVERLAP')
    _identity(value['bulkOwner']);_identity(value['bulkManifest'])
    require(value['manifestSha256']==hashlib.sha256(canonical(_manifest(value))).hexdigest(),
            'QUALIFICATION_STORAGE_BINDING')
    return document(wire)


def install_binding(control_directory,bulk_directory):
    """Trusted explicit setup of fresh roots; failed setup is retained, never reset."""
    control,bulk=(Path(os.path.abspath(os.fspath(p))) for p in (control_directory,bulk_directory))
    require(control!=bulk and control not in bulk.parents and bulk not in control.parents,
            'QUALIFICATION_STORAGE_OVERLAP')
    control=private_state_directory(control,create=True)
    bulk=private_state_directory(bulk,create=True)
    require(not any(control.iterdir()) and not any(bulk.iterdir()),'QUALIFICATION_STORAGE_NOT_EMPTY')
    fds=[]
    try:
        for path in (control,bulk):fds.append(os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC))
        cfd,bfd=fds
        value=dict(profile=PROFILE,bindingId=uuid.uuid4().hex,
                   control=_root_record(control,cfd),bulk=_root_record(bulk,bfd))
        owner=os.open('bulk.owner',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=bfd)
        fds.append(owner);safe_file(owner,maximum=0);fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.fsync(owner);os.fsync(bfd)
        body=canonical(value);write_file(bfd,'storage.json',body)
        marker=os.open('storage.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=bfd);fds.append(marker)
        value.update(bulkOwner=_object(os.fstat(owner)),bulkManifest=_object(safe_file(marker,maximum=MAX_BINDING_BYTES)),
                     manifestSha256=hashlib.sha256(body).hexdigest())
        os.fsync(cfd)
        for parent in {control.parent,bulk.parent}:
            parent_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:os.fsync(parent_fd)
            finally:os.close(parent_fd)
        return parse_binding(value)
    finally:
        for fd in reversed(fds):os.close(fd)


class _Bulk:
    def __init__(self,binding):
        self.binding=binding;self.fds=[]
        try:
            self.fd=_open_root(binding['bulk']);self.fds.append(self.fd)
            self.owner=os.open('bulk.owner',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.fd);self.fds.append(self.owner)
            require(_object(safe_file(self.owner,maximum=0))==binding['bulkOwner'],'QUALIFICATION_STORAGE_CHANGED')
            try:fcntl.flock(self.owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise SupervisorError('QUALIFICATION_BULK_OWNER_BUSY') from error
            self.check()
        except BaseException:
            self.close();raise

    def check(self):
        row=self.binding['bulk'];path=Path(row['path'])
        require(_root_record(path,self.fd)==row,'QUALIFICATION_STORAGE_CHANGED')
        current=path.stat(follow_symlinks=False)
        require(stat.S_ISDIR(current.st_mode) and _object(current)==_object(os.fstat(self.fd)) and
                current.st_uid==row['uid'] and stat.S_IMODE(current.st_mode)==0o700,'QUALIFICATION_STORAGE_CHANGED')
        require(_object(safe_file(self.owner,maximum=0))==self.binding['bulkOwner'],'QUALIFICATION_STORAGE_CHANGED')
        for name,expected in [('bulk.owner',self.binding['bulkOwner']),('storage.json',self.binding['bulkManifest'])]:
            info=os.stat(name,dir_fd=self.fd,follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid() and
                    stat.S_IMODE(info.st_mode)==0o600 and _object(info)==expected,'QUALIFICATION_STORAGE_CHANGED')
        require(read_file(self.fd,'storage.json',maximum=MAX_BINDING_BYTES)==canonical(_manifest(self.binding)),
                'QUALIFICATION_STORAGE_CHANGED')

    def close(self):
        for fd in reversed(self.fds):os.close(fd)
        self.fds=[]


class StorageAttemptLedger(AuthorityAttemptLedger):
    """Version 3 binds bulk identity without opening it during control startup."""
    def __init__(self,root,*,storage_binding,create=False,expected_authority=None):
        self._storage=parse_binding(storage_binding)
        self._storage_wire=canonical(self._storage)
        self._bulk_owner=None
        require(str(Path(os.path.abspath(os.fspath(root))))==self._storage['control']['path'],
                'QUALIFICATION_STORAGE_CHANGED')
        control=_open_root(self._storage['control'])
        try:
            # No automatic hot-journal recovery is qualified by this profile.
            for suffix in ('-journal','-wal','-shm'):
                try:os.stat('attempts.db'+suffix,dir_fd=control,follow_symlinks=False)
                except FileNotFoundError:continue
                raise SupervisorError('QUALIFICATION_STORAGE_RECOVERY_REQUIRED')
            super().__init__(root,create=create,expected_authority=expected_authority)
        finally:os.close(control)

    def storage_binding(self):
        return document(self._storage_wire)

    def _control_current(self):
        require(self.db is not None and self.fd is not None,'QUALIFICATION_LEDGER_CLOSED')
        row=self._storage['control']
        require(_root_record(self.root,self.fd)==row,'QUALIFICATION_STORAGE_CHANGED')
        info=self.root.stat(follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and _object(info)==_object(os.fstat(self.fd)) and
                info.st_uid==row['uid'] and stat.S_IMODE(info.st_mode)==0o700,'QUALIFICATION_STORAGE_CHANGED')

    def _create_metadata(self):
        require(self._creating_authority,'QUALIFICATION_LEDGER_MISSING')
        self._control_current()
        self._created_authority='supervisor:'+uuid.uuid4().hex
        self._expected_authority=self._created_authority
        self.db.execute(META_SQL)
        self.db.execute('INSERT INTO qs_meta VALUES(3,?,?)',(self._created_authority,self._storage_wire))

    def _check_metadata(self):
        self._control_current()
        require(not self._creating_authority or self._created_authority is not None,'QUALIFICATION_AUTHORITY_ALREADY_EXISTS')
        require(self.db.execute('SELECT 1 FROM sqlite_temp_master LIMIT 1').fetchone() is None,'QUALIFICATION_SCHEMA_INVALID')
        rows=self.db.execute("SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),length(CAST(sql AS BLOB)) FROM sqlite_master LIMIT 7").fetchall()
        require(len(rows)==5,'QUALIFICATION_SCHEMA_INVALID')
        for row in rows:
            require(all(row[i]=='text' and type(row[i+1]) is int and 1<=row[i+1]<=128 for i in (0,2,4)),
                    'QUALIFICATION_SCHEMA_INVALID')
            require((row[6]=='null' and row[7] is None) or (row[6]=='text' and type(row[7]) is int and 1<=row[7]<=4096),
                    'QUALIFICATION_SCHEMA_INVALID')
        expected={('qs_meta','table','qs_meta',META_SQL),('qs_attempts','table','qs_attempts',ATTEMPT_SQL),
                  ('qs_singleflight','index','qs_attempts',INDEX_SQL),('sqlite_autoindex_qs_attempts_1','index','qs_attempts',None),
                  ('sqlite_autoindex_qs_attempts_2','index','qs_attempts',None)}
        require(set(self.db.execute('SELECT name,type,tbl_name,sql FROM sqlite_master LIMIT 7'))==expected,
                'QUALIFICATION_SCHEMA_INVALID')
        meta=self.db.execute("SELECT typeof(version),CASE WHEN typeof(version)='integer' THEN version ELSE NULL END,typeof(authority),length(CAST(authority AS BLOB)),typeof(binding),length(binding) FROM qs_meta LIMIT 2").fetchall()
        require(meta==[('integer',3,'text',43,'blob',len(self._storage_wire))],'QUALIFICATION_STORAGE_BINDING')
        actual,wire=self.db.execute('SELECT authority,binding FROM qs_meta').fetchone()
        require(authority_id(actual)==self._expected_authority,'QUALIFICATION_AUTHORITY_MISMATCH')
        require(wire==self._storage_wire,'QUALIFICATION_STORAGE_CHANGED')

    def _bulk(self):
        with self.lock:
            self._check_metadata()
            try:
                if self._bulk_owner is None:self._bulk_owner=_Bulk(self._storage)
                self._bulk_owner.check()
                return self._bulk_owner
            except OSError as error:raise SupervisorError('QUALIFICATION_BULK_UNAVAILABLE') from error
            except JournalError as error:
                if isinstance(error,SupervisorError):raise
                raise SupervisorError('QUALIFICATION_BULK_UNAVAILABLE') from error

    @property
    def bulk_root(self):
        self._bulk()
        return Path(self._storage['bulk']['path'])

    @property
    def bulk_fd(self):
        return self._bulk().fd

    def _retained_usage(self,*,max_files,max_bytes):
        bulk=self.bulk_root
        control=tree_usage(self.root,max_files=max_files,max_bytes=max_bytes)
        value=tree_usage(bulk,max_files=max_files-control['files'],max_bytes=max_bytes-control['logicalBytes'])
        self._bulk()
        return dict(files=control['files']+value['files'],logicalBytes=control['logicalBytes']+value['logicalBytes'],
                    totalDiskQuotaEnforced=False)

    def close(self):
        try:super().close()
        finally:
            if self._bulk_owner is not None:self._bulk_owner.close();self._bulk_owner=None
