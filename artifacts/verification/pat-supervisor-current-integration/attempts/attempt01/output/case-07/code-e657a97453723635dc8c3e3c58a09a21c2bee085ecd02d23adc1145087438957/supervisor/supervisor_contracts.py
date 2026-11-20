"""Trusted original-worker supervision contracts; no caller-selected code."""
import hashlib
import importlib.metadata
import os
from pathlib import Path
import re
import stat
from functools import wraps

from hms.contracts import ContractError, canonical, parse_json
from hms.journal import JournalError
from hms.pat_simulation_evidence import same, trusted_binding, document, exact, integer
from hms.pat_simulation_worker import parse_capsule, simulation_identities

PROFILE = 'hms.pat.qualification-attempt/0.1'
DEFAULT_LIMITS = {'maxRetainedBytes': 256*1024*1024, 'attemptReservationBytes': 64*1024*1024,
    'maxArchives': 32, 'maxFilesPerAttempt': 8192, 'maxStreamBytes': 65536,
    'maxFileBytes': 64*1024*1024, 'stopGraceMs': 1000, 'settleGraceMs': 1000}
SOURCE_FILES = ('supervisor_contracts.py', 'attempt_ledger.py', 'qualification_supervisor.py', 'worker_entry.py')
PACKAGES = ('jsonschema', 'referencing', 'jsonschema-specifications', 'attrs', 'rpds-py')

class SupervisorError(JournalError):
    pass

def require(ok, code='QUALIFICATION_INVALID'):
    if not ok: raise SupervisorError(code)

def digest(body):
    return 'sha256:'+hashlib.sha256(body).hexdigest()

def request_digest(request):
    return digest(b'HMS-PAT-QUALIFICATION-REQUEST-v0.1\0'+canonical(request))

def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except SupervisorError: raise
        except (ContractError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
            raise SupervisorError('QUALIFICATION_INVALID') from error
    return checked

@errors
def parse_limits(value):
    exact(value, DEFAULT_LIMITS)
    for name, ceiling in DEFAULT_LIMITS.items(): integer(value[name], 1, ceiling)
    require(value['attemptReservationBytes'] <= value['maxRetainedBytes'])
    return document(canonical(value))

@errors
def parse_request(value):
    # This structural replay parser deliberately does not consult current code.
    body=canonical(value);exact(value,{'profile','trust','supervisorIdentity','limits'})
    require(value['profile']==PROFILE)
    trust=value['trust'];exact(trust,{'profile','deployment','runId','evaluator','input'})
    exact(trust['evaluator'],{'evaluatorId','implementationDigest','policyDigest','requiredChecks','evidenceProfile'})
    for name in (trust['deployment'],trust['runId'],trust['evaluator']['evaluatorId']):
        require(type(name) is str and 1<=len(name)<=160)
    require(type(value['supervisorIdentity']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}',value['supervisorIdentity']) is not None)
    parse_limits(value['limits'])
    result=parse_json(body);require(same(value,result))
    return result

def supervisor_identity(worker_identities):
    rows=[{'path':name,'sha256':hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()} for name in SOURCE_FILES]
    require(rows == _IMPORTED_SOURCES, 'QUALIFICATION_IMPLEMENTATION_CHANGED')
    files = runtime_files()
    closure = hashlib.sha256(b''.join(canonical({'path':p,'sha256':h})+b'\n' for p,_,h in files)).hexdigest()
    return digest(b'HMS-PAT-QUALIFICATION-SUPERVISOR-v0.1\0'+canonical({'sources':rows,'worker':worker_identities,
        'runtimeFiles':len(files),'runtimeDigest':'sha256:'+closure}))

def prepare_request(trust, limits=None):
    trust=trusted_binding(trust);parse_capsule(trust['input'])
    limits=parse_limits(DEFAULT_LIMITS if limits is None else limits)
    require(limits['attemptReservationBytes'] >= trust['input']['limits']['maxOutputBytes']+2*limits['maxStreamBytes']+131072,
            'QUALIFICATION_RESERVATION_TOO_SMALL')
    return parse_request({'profile':PROFILE,'trust':trust,'limits':limits,
                          'supervisorIdentity':supervisor_identity(trust['input']['identities'])})

def validate_fresh(request):
    request=parse_request(request)
    require(same(prepare_request(request['trust'],request['limits']),request),'QUALIFICATION_IMPLEMENTATION_CHANGED')
    return request

def run_key(request):
    trust=request['trust'];return trust['deployment'],trust['evaluator']['evaluatorId'],trust['runId']

def safe_file(fd, *, mode=0o600, maximum=None):
    info=os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==mode and info.st_nlink==1,
            'QUALIFICATION_UNSAFE_FILE')
    if maximum is not None:require(0<=info.st_size<=maximum,'QUALIFICATION_FILE_LIMIT')
    return info

def read_file(directory, name, *, maximum=65536):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
    try:
        info=safe_file(fd,maximum=maximum);body=b''
        while len(body)<=info.st_size:
            chunk=os.read(fd,min(65536,info.st_size+1-len(body)))
            if not chunk:break
            body+=chunk
        require(len(body)==info.st_size,'QUALIFICATION_FILE_CHANGED')
        return body
    finally:os.close(fd)

def write_file(directory, name, body):
    require(type(body) is bytes and len(body)<=65536)
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    try:
        safe_file(fd)
        view=memoryview(body)
        while view:
            amount=os.write(fd,view);require(amount>0,'QUALIFICATION_SHORT_WRITE');view=view[amount:]
        os.fsync(fd)
    finally:os.close(fd)
    os.fsync(directory)


_IMPORTED_SOURCES = [{'path': name, 'sha256': hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()}
                     for name in SOURCE_FILES]

def _runtime_files():
    rows = {}; total = 0
    for package in PACKAGES:
        distribution = importlib.metadata.distribution(package)
        for item in sorted(distribution.files or [], key=str):
            # Console entry points outside the installed package tree are never
            # used by this fixed entry. Retain all in-tree runtime data, including
            # extensionless JSON Schema resources, plus distribution metadata.
            if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts: continue
            source = Path(distribution.locate_file(item))
            if not source.is_file(): continue
            size = source.stat().st_size
            require(size <= 4*1024*1024 and len(rows) < 4096 and total+size <= 32*1024*1024,
                    'QUALIFICATION_PACKAGE_LIMIT')
            body = source.read_bytes(); require(len(body) == size, 'QUALIFICATION_PACKAGE_CHANGED')
            key = str(item); fingerprint = hashlib.sha256(body).hexdigest()
            require(key not in rows or rows[key][1] == fingerprint, 'QUALIFICATION_PACKAGE_LAYOUT')
            rows[key] = (source, fingerprint); total += size
    return [(path, source, fingerprint) for path,(source,fingerprint) in sorted(rows.items())]

_IMPORTED_RUNTIME = [(path, fingerprint) for path, _, fingerprint in _runtime_files()]

def runtime_files():
    rows = _runtime_files()
    require([(path, fingerprint) for path, _, fingerprint in rows] == _IMPORTED_RUNTIME,
            'QUALIFICATION_IMPLEMENTATION_CHANGED')
    return rows
