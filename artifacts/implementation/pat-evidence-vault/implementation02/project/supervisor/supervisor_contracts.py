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
from hms.pat_simulation_evidence import same, document, exact, integer
from hms.pat_io_run_bundle import (bundle_digest, parse_io_run_bundle,
    validate_fresh_io_run_bundle, _context, _paths, _hash, CEILINGS)

PROFILE = 'hms.pat.io-supervisor-request/0.1'
DEFAULT_LIMITS = {'maxRetainedBytes': 256*1024*1024, 'attemptReservationBytes': 64*1024*1024,
    'maxArchives': 32, 'maxFilesPerAttempt': 8192, 'maxStreamBytes': 65536,
    'maxFileBytes': 64*1024*1024, 'stopGraceMs': 1000, 'settleGraceMs': 1000}
SOURCE_FILES = ('supervisor_contracts.py', 'attempt_ledger.py', 'qualification_supervisor.py', 'worker_entry.py', 'bundle_io.py', 'io_services.py', 'io_service_store.py', 'io_service_runs.py', 'authority_ledger.py', 'io_service_execution.py')
PACKAGES = ('jsonschema', 'referencing', 'jsonschema-specifications', 'attrs', 'rpds-py', 'typing_extensions', 'idna')

class SupervisorError(JournalError):
    pass

def require(ok, code='QUALIFICATION_INVALID'):
    if not ok: raise SupervisorError(code)

def digest(body):
    return 'sha256:'+hashlib.sha256(body).hexdigest()

def request_digest(request):
    return digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1\0'+canonical(request))

def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except SupervisorError: raise
        except (JournalError, ContractError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
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
    body=canonical(value);exact(value,{'profile','context','bundleHeader','bundleDigest','supervisorIdentity','limits','groupLimits','implementation'})
    require(value['profile']==PROFILE)
    context=_context(value['context']);header=value['bundleHeader']
    exact(header, {'profile','context','manifest','inputBytes','caseIds','matrixDigest','inputSetDigest'})
    require(header['profile']=='hms.pat.io-run-bundle/0.1' and same(header['context'],context))
    require(bundle_digest(canonical(header))==value['bundleDigest'])
    integer(header['inputBytes'],1,39*65536)
    ids=header['caseIds'];require(type(ids) is list and 1<=len(ids)<=32)
    require(all(type(v) is str and re.fullmatch(r'sha256:[0-9a-f]{64}',v) for v in ids) and len(set(ids))==len(ids))
    paths=_paths(len(ids));manifest=header['manifest'];require(type(manifest) is list and len(manifest)==len(paths))
    for path,row in zip(paths,manifest):
        exact(row,{'path','bytes','sha256'});integer(row['bytes'],1,65536)
        require(row['path']==path and type(row['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}',row['sha256']))
    require(sum(row['bytes'] for row in manifest)==header['inputBytes'] and
        header['inputSetDigest']==_hash(b'HMS-PAT-IO-INPUT-SET-v0.1',manifest))
    require(type(header['matrixDigest']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}',header['matrixDigest']))
    exact(value['groupLimits'],CEILINGS)
    for key,maximum in CEILINGS.items():integer(value['groupLimits'][key],1,maximum)
    exact(value['implementation'],{'compilerDigest','driverDigest','workerDigest','storageProfile'})
    for key in ('compilerDigest','driverDigest','workerDigest'):
        require(type(value['implementation'][key]) is str and re.fullmatch(r'sha256:[0-9a-f]{64}',value['implementation'][key]))
    require(value['implementation']['storageProfile']=='hms.sqlite.compact/0.1')
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

@errors
def snapshot_bundle(value):
    exact(value, {'header','documents','bundleDigest'})
    require(type(value['header']) is bytes and type(value['documents']) is dict and 1<=len(value['documents'])<=39)
    require(all(type(k) is str and type(v) is bytes and 0<len(v)<=65536 for k,v in value['documents'].items()))
    return dict(header=value['header'],documents=dict(value['documents']),bundleDigest=value['bundleDigest'])

@errors
def prepare_request(bundle, *, context, limits=None):
    bundle=snapshot_bundle(bundle)
    parsed=validate_fresh_io_run_bundle(bundle['header'],bundle['documents'],expected_context=context,
        expected_bundle_digest=bundle['bundleDigest'])
    header=document(bundle['header']);inputs=parsed['expected_inputs']
    limits=parse_limits(DEFAULT_LIMITS if limits is None else limits)
    require(limits['attemptReservationBytes'] >= inputs['matrix']['limits']['maxDerivedBytes']+
        header['inputBytes']+len(bundle['header'])+2*limits['maxStreamBytes']+3*65536,
            'QUALIFICATION_RESERVATION_TOO_SMALL')
    return parse_request(dict(profile=PROFILE,context=parsed['context'],bundleHeader=header,bundleDigest=bundle['bundleDigest'],
        limits=limits,groupLimits=inputs['matrix']['limits'],implementation=inputs['implementation'],
        supervisorIdentity=supervisor_identity(inputs['implementation'])))

def validate_fresh(request, bundle):
    request=parse_request(request)
    require(same(prepare_request(bundle,context=request['context'],limits=request['limits']),request),'QUALIFICATION_IMPLEMENTATION_CHANGED')
    return request

def run_key(request):
    context=request['context'];return context['deployment'],context['evaluatorId'],context['runId']

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
