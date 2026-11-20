"""Authority-vault controls: exact sources, no worker or physical effect."""
import hashlib
import fcntl
import json
import os
import re
from pathlib import Path
import sys
import sysconfig
import traceback
import resource
import stat
import threading
from urllib.parse import urlsplit, unquote

MAX_JSON = 4 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MAX_ORIGINS = 8192
resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE, MAX_FILE))
resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
configuration = Path(sys.argv[1])
if configuration.stat().st_size > MAX_JSON:
    raise RuntimeError('Oversized child configuration')
config = json.loads(configuration.read_text())
root = Path(config['project']).resolve()
out = Path(config['attempt']).resolve()
sys.path[:0] = [str(root), str(root / 'tests')] + config['externalRoots']
sys.dont_write_bytecode = True
acquired = {str((root / value['path']).resolve()): value['sha256'] for value in config['expectedInputs']}
external = {value['resolvedPath']: value['sha256'] for value in config['expectedExternalInputs']}
stdlib = Path(sysconfig.get_path('stdlib')).resolve()
executed, resource_reads, denied_bytecode = set(), set(), set()
prohibited = []
current_test = None
sqlite_connections = []
scratch = Path(config['scratch']).resolve()
errors = []
counts = origins = None
loaded_ids, executed_ids = [], []
own_path = Path(__file__).resolve()


def sha(path):
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise RuntimeError('Origin file missing or exceeds acquisition bound')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


if sha(own_path) != config['childSha256']:
    raise RuntimeError('Retained child bytes differ from launcher pin')


def remember(collection, value):
    collection.add(value)
    if len(collection) > MAX_ORIGINS:
        raise RuntimeError('Actual-origin inventory exceeds fixed bound')


def is_stdlib(path):
    return path.is_relative_to(stdlib) and not {'site-packages', 'dist-packages'}.intersection(path.parts)


CONTROL_TARGETS = ['test_vault_catalog_inventory.VaultCatalogInventoryTests.test_unprepared_second_program_cannot_manufacture_unique_selection']

# The native open audit event omits dir_fd. Preserve the original os.open
# call and expose its resolved pathname only to this synchronous audit hook.
# This is a cooperative fixture guard, not an OS isolation boundary.
native_open = os.open
open_context = threading.local()
def checked_os_open(path, flags, mode=0o777, *, dir_fd=None):
    name = os.fsdecode(path)
    target = Path(name)
    if dir_fd is not None and not target.is_absolute():
        if type(dir_fd) is not int or not stat.S_ISDIR(os.fstat(dir_fd).st_mode):
            raise RuntimeError('Invalid directory descriptor')
        parent = Path(os.readlink('/proc/self/fd/' + str(dir_fd)))
        if not parent.is_absolute():
            raise RuntimeError('Unresolved directory descriptor')
        target = parent / target
    previous = getattr(open_context, 'current', None)
    open_context.current = (name, target.resolve())
    try:
        return native_open(path, flags, mode, dir_fd=dir_fd)
    finally:
        open_context.current = previous
os.open = checked_os_open


native_load = None
native_image = None
native_scans = {}
NATIVE_DIGEST = 'ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff'

def verify_native_image(value):
    descriptor = value['descriptor']
    info = os.fstat(descriptor)
    required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 0 and info.st_uid == os.getuid()
        and info.st_dev == value['device'] and info.st_ino == value['inode']
        and 0 < info.st_size <= 65536 and not os.get_inheritable(descriptor)
        and fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & required == required
        and hashlib.sha256(os.pread(descriptor, 65537, 0)).hexdigest() == NATIVE_DIGEST)

def native_boundary(event, args):
    global native_load, native_image
    if current_test not in config['targets']:
        prohibited.append(event)
        raise RuntimeError('Native retention is only authorized inside an exact selected control')
    expected = scratch / current_test.split('.')[-1] / 'supervisor'
    if event == 'hms.retention.load.v1':
        artifact = root / 'hms_qualification/supervisor/retention_scan.so'
        if (native_load is not None or args != (str(artifact), NATIVE_DIGEST, 'hms.retention.linux-cpython312-x86_64/1')
                or acquired.get(str(artifact)) != NATIVE_DIGEST or sha(artifact) != NATIVE_DIGEST):
            prohibited.append(event)
            raise RuntimeError('Native artifact differs from exact acquired image')
        native_load = dict(artifactOrigin=str(artifact), sha256=NATIVE_DIGEST, profile=args[2])
    elif event == 'hms.retention.image.v1':
        if (native_load is None or native_image is not None or len(args) != 5
                or type(args[0]) is not str or re.fullmatch(r'/proc/self/fd/[0-9]+', args[0]) is None
                or args[1] != NATIVE_DIGEST or any(type(value) is not int for value in args[2:])):
            prohibited.append(event)
            raise RuntimeError('Unexpected native memory image')
        value = dict(origin=args[0], descriptor=int(args[0].rsplit('/', 1)[1]), sha256=args[1],
                     device=args[2], inode=args[3], requestedSeals=args[4])
        if not verify_native_image(value):
            prohibited.append(event)
            raise RuntimeError('Native memory image is not the exact sealed artifact')
        native_image = value
    elif event == 'hms.retention.scan.v1':
        valid = (native_image is not None and len(args) == 3 and type(args[0]) is bytes
                 and type(args[1]) is int and type(args[2]) is int)
        if valid:
            path = Path(os.fsdecode(args[0]))
            root_scan = path == expected
            attempt_scan = path.parent == expected and re.fullmatch(r'[0-9a-f]{32}', path.name) is not None
            valid = ((root_scan or attempt_scan) and 0 <= args[1] <= (262144 if root_scan else 8192)
                     and 0 <= args[2] <= (268435456 if root_scan else 67108864))
        if not valid:
            prohibited.append(event)
            raise RuntimeError('Native scan is outside the owned supervisor scope')
        key = str(path)
        entry = native_scans.setdefault(key, dict(path=key, calls=0, maxFiles=0, maxBytes=0))
        entry['calls'] += 1
        entry['maxFiles'] = max(entry['maxFiles'], args[1])
        entry['maxBytes'] = max(entry['maxBytes'], args[2])
    else:
        prohibited.append(event)
        raise RuntimeError('Unknown native retention event')


def audit(event, args):
    if event.startswith('hms.retention.'):
        native_boundary(event, args)
        return
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Control selection forbids network and subprocesses')
    if event == 'sqlite3.connect':
        supplied = str(args[0])
        parsed = urlsplit(supplied)
        if supplied.startswith('file:'):
            path = Path(unquote(parsed.path)).resolve()
            if parsed.netloc or parsed.fragment or parsed.query not in ('mode=rw', 'mode=ro&immutable=1'):
                raise RuntimeError('Undeclared SQLite URI')
        else:
            path = Path(supplied).resolve()
        if current_test is None:
            raise RuntimeError('SQLite before selected method')
        parent = scratch / current_test.split('.')[-1]
        allowed = ['runtime/authority.db', 'runtime/synthetic-io-board-859169b38185780daa5497983ff20d2994390058d8a71f2847ac7846f970971e.db', 'supervisor/attempts.db', 'vault/evidence.db', 'wrong-vault/evidence.db']
        if path not in {parent / name for name in allowed}:
            raise RuntimeError('SQLite outside declared current control fixture')
        sqlite_connections.append(dict(test=current_test, path=str(path), supplied=supplied))
        if len(sqlite_connections) > 64:
            raise RuntimeError('SQLite connection bound')
    if event == 'exec':
        origin = args[0].co_filename
        remember(executed, origin)
        if isinstance(origin, str) and not origin.startswith('<'):
            path = Path(origin).resolve()
            expected = acquired.get(str(path), external.get(str(path)))
            if expected is not None:
                if sha(path) != expected:
                    raise RuntimeError('Executable source changed after acquisition')
            elif path != own_path and not is_stdlib(path):
                raise RuntimeError('Executable origin outside acquired source/selected dependencies')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0]))
        if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            opened = getattr(open_context, 'current', None)
            target = opened[1] if opened is not None and opened[0] == os.fsdecode(args[0]) else path.resolve()
            receipts = {'child-runtime.json', 'compiler-before.json', 'compiler-after.json',
                'driver-before.json', 'driver-after.json', 'host-before.json', 'host-after.json', 'loader-errors.json', 'imports.json',
                'sqlite-connections.json', 'actual-tests.json', 'test-return.json', 'child-errors.json'}
            if not (target.is_relative_to(scratch) or target.parent == out and target.name in receipts):
                raise RuntimeError('Write outside fresh scratch or named receipts')
        if path.suffix == '.pyc':
            remember(denied_bytecode, str(path))
            raise FileNotFoundError(2, 'Use exact retained source, not cached bytecode', str(path))
        if path.is_absolute() and any(path.is_relative_to(Path(base)) for base in config['externalRoots']):
            remember(resource_reads, str(path))


sys.addaudithook(audit)


def write(name, value):
    encoded = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    if len(encoded) > MAX_JSON:
        raise RuntimeError('Child JSON receipt exceeds fixed emission bound')
    (out / name).write_bytes(encoded)


def actual_origins():
    rows, violations, seen = [], [], set()
    def add(label, origin):
        if not isinstance(origin, str) or origin.startswith('<') or origin in {'built-in', 'frozen'}:
            rows.append({'source': label, 'origin': str(origin), 'kind': 'interpreter_or_synthetic'})
            return
        if label == 'module:_hms_retention_native_v1':
            if native_image is None or origin != native_image['origin'] or not verify_native_image(native_image):
                raise RuntimeError('Loaded native module has no exact held image')
            rows.append(dict(source=label, origin=origin, kind='sealed_native_image',
                sha256=NATIVE_DIGEST, artifactOrigin=native_load['artifactOrigin'],
                device=native_image['device'], inode=native_image['inode'], matchesBefore=True))
            return
        path = Path(origin).resolve()
        key = (label, str(path))
        if key in seen:
            return
        if len(rows) >= MAX_ORIGINS:
            raise RuntimeError('Actual-origin report exceeds fixed record bound')
        seen.add(key)
        value = {'source': label, 'origin': str(path)}
        if not path.is_file():
            value['kind'] = 'missing'
            violations.append(value.copy())
            rows.append(value)
            return
        value['sha256'] = sha(path)
        if path.is_relative_to(root):
            value['kind'] = 'project'
            value['matchesBefore'] = acquired.get(str(path)) == value['sha256']
            if not value['matchesBefore']:
                violations.append(value.copy())
        elif str(path) in external:
            value['kind'] = 'selected_external'
            value['matchesBefore'] = external[str(path)] == value['sha256']
            if not value['matchesBefore']:
                violations.append(value.copy())
        elif path == own_path:
            value['kind'] = 'retained_child_harness'
            value['matchesBefore'] = value['sha256'] == config['childSha256']
            if not value['matchesBefore']:
                violations.append(value.copy())
        elif is_stdlib(path):
            value['kind'] = 'stdlib_actual_file'
            value['preExecutionPin'] = False
        else:
            value['kind'] = 'unexpected_origin'
            violations.append(value.copy())
        rows.append(value)
    for name, module in sorted(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        if origin is None:
            origin = getattr(getattr(module, '__spec__', None), 'origin', None)
        if origin is not None:
            add('module:' + name, origin)
        if name in ['attempt_ledger', 'authority_ledger', 'bundle_io', 'evidence', 'evidence_authority', 'evidence_compact', 'evidence_vault', 'io_service_execution', 'io_service_runs', 'io_service_store', 'io_services', 'qualification_supervisor', 'recorded_io', 'retention_native', 'supervisor_contracts', 'vault_recorded_io', 'worker_entry']:
            violations.append({'module': name, 'reason': 'legacy_flat_import_forbidden'})
        if (name == 'hms' or name.startswith('hms.') or name == 'hms_qualification' or name.startswith('hms_qualification.') or name.startswith('test_') or name == 'evidence' or name.startswith('evidence.') or name == 'evidence_compact' or name.startswith('evidence_compact.') or name == 'recorded_io' or name.startswith('recorded_io.') or name == 'vault_recorded_io' or name.startswith('vault_recorded_io.') or name == 'evidence_authority' or name.startswith('evidence_authority.') or name == 'evidence_vault' or name.startswith('evidence_vault.')) and origin:
            if not Path(origin).resolve().is_relative_to(root):
                violations.append({'module': name, 'origin': str(origin), 'reason': 'project_name_outside_copy'})
    for origin in sorted(executed):
        add('executed_code', origin)
    # Snapshot before hash reads themselves emit further harmless open events.
    for origin in sorted(resource_reads):
        add('selected_external_read', origin)
    return {'profile': 'hms.io-correspondence-actual-origins/1',
            'summary': {'complete': True, 'allOriginsMatched': not violations and not prohibited,
                        'recordCount': len(rows), 'violationCount': len(violations),
                        'prohibitedAttemptCount': len(prohibited)},
            'records': rows, 'violations': violations, 'prohibitedAttempts': prohibited,
            'nativeRetention': dict(load=native_load, image=native_image, scans=list(native_scans.values())),
            'deniedBytecodeReads': sorted(denied_bytecode),
            'limits': 'Selected source/package origins are checked; startup stdlib and dynamically linked system libraries are not a full pre-execution closure. Frozen/synthetic code is distinct. Temporary identity-fixture resources are generated data, not imported code. Audit hooks are cooperative guardrails, not an OS sandbox.'}


def flatten(suite):
    import unittest
    result = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            result.extend(flatten(test))
        else:
            result.append(test.id())
    return result


try:
    if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode or
            len(config['targets']) != 1 or len(set(config['targets'])) != 1):
        raise RuntimeError('Required child isolation flags or exact target count missing')
    if config['targets'] != CONTROL_TARGETS:
        raise RuntimeError('Exact literal target selection changed')
    write('child-runtime.json', {'executable': sys.executable, 'version': sys.version,
        'flags': repr(sys.flags), 'path': sys.path, 'cwd': str(Path.cwd()),
        'environment': dict(os.environ), 'stdlib': str(stdlib)})
    import unittest
    from hms_qualification.vault_recorded_io.contracts import identity as host_identity
    assert host_identity() == config['expectedHost']
    write('host-before.json', {'host': host_identity()})
    from hms.pat_compiler import compiler_digest, compiler_manifest
    write('compiler-before.json', {'digest': compiler_digest(), 'manifest': compiler_manifest()})
    from hms.synthetic_io_installation import implementation_digest
    write('driver-before.json', {'digest': implementation_digest()})
    tests = unittest.defaultTestLoader.loadTestsFromNames(config['targets'])
    loaded_ids = flatten(tests)
    write('loader-errors.json', list(unittest.defaultTestLoader.errors))
    for detail in unittest.defaultTestLoader.errors: print(detail, file=sys.stderr, flush=True)
    if loaded_ids != config['targets']:
        raise RuntimeError('Loaded methods do not exactly match the reviewed vault selection')
    class RecordingResult(unittest.TextTestResult):
        def startTest(self, test):
            global current_test
            current_test = test.id()
            executed_ids.append(test.id())
            super().startTest(test)
        def stopTest(self, test):
            global current_test
            super().stopTest(test)
            current_test = None
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)
    counts = {'testsRun': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skips': len(result.skipped), 'expectedFailures': len(result.expectedFailures),
        'unexpectedSuccesses': len(result.unexpectedSuccesses)}
    write('compiler-after.json', {'digest': compiler_digest(), 'manifest': compiler_manifest()})
    write('driver-after.json', {'digest': implementation_digest()})
    write('host-after.json', {'host': host_identity()})
except BaseException as exc:
    errors.append({'type': type(exc).__name__, 'message': str(exc)[:4096]})
    traceback.print_exc()
finally:
    def finalize(label, callback):
        try:
            callback()
        except BaseException as exc:
            errors.append({'phase': label, 'type': type(exc).__name__, 'message': str(exc)[:4096]})
    def origins_receipt():
        global origins
        origins = actual_origins()
        write('imports.json', origins)
    finalize('actual-origins', origins_receipt)
    finalize('sqlite-connections', lambda: write('sqlite-connections.json', sqlite_connections))
    finalize('exact-methods', lambda: write('actual-tests.json', {'loaded': loaded_ids, 'executed': executed_ids,
        'exactSelection': loaded_ids == config['targets'] == executed_ids}))
    if counts is not None:
        finalize('test-return', lambda: write('test-return.json', counts))
    try:
        write('child-errors.json', errors)
    except BaseException:
        errors.append({'phase': 'child-errors', 'type': 'ReceiptWriteFailure'})
passed = (not errors and counts is not None and counts['testsRun'] == 1 and
    all(counts[key] == 0 for key in counts if key != 'testsRun') and
    loaded_ids == config['targets'] == executed_ids and origins is not None and
    origins['summary']['allOriginsMatched'])
raise SystemExit(0 if passed else 1)
