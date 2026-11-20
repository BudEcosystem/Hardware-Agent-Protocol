"""IoService1 child: isolated startup, exact selected tests and scoped origin evidence."""
import hashlib
import fcntl
import stat
import json
import os
import re
from pathlib import Path
import sys
import sysconfig
import traceback

MAX_JSON = 4 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MAX_ORIGINS = 8192
import resource
resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_FILE,MAX_FILE))
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
accounting_launch_audit = []
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
    if current_test != config['targets'][0]:
        prohibited.append(event)
        raise RuntimeError('Native retention is only authorized inside the exact actual test')
    expected = scratch / 'test_actual_original_matrix_catalog_admission_and_cold_history' / 'supervisor-bulk'
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
            root_scan = path in (expected,expected.with_name('supervisor-control'))
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
    if event == 'subprocess.Popen':
        executable, argv, cwd, environment = args
        expected = scratch / 'test_actual_original_matrix_catalog_admission_and_cold_history' / 'supervisor-bulk'
        entry = Path(argv[3]) if type(argv) in (list,tuple) and len(argv)==7 else Path('/invalid')
        valid = (current_test == config['targets'][0] and executable == sys.executable and
            argv[0] == sys.executable and argv[1:3] == ['-I','-B'] and
            entry.name == 'worker_entry.py' and entry.parent.name == 'supervisor' and
            entry.parent.parent.name == 'hms_qualification' and entry.parents[3] == expected and re.fullmatch(r'code-[0-9a-f]{64}',entry.parents[2].name) and
            str(cwd) == str(entry.parents[2]) and all(type(v) is str and v.isdecimal() for v in argv[4:]) and
            environment == {'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        if not valid: prohibited.append(event); raise RuntimeError('Only exact owned I/O entry may launch')
        if accounting_launch_audit:
            prohibited.append(event); raise RuntimeError('Diagnostic permits exactly one original worker launch')
        accounting_launch_audit.append({'argv': list(argv), 'cwd': str(cwd), 'testId': current_test})
    elif event.startswith('socket.') or event in {'os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Network or other subprocess forbidden')
    if event == 'sqlite3.connect':
        supplied = os.fsdecode(os.fspath(args[0]))
        work=scratch/'test_actual_original_matrix_catalog_admission_and_cold_history'
        vault = work/'vault'/'evidence.db'
        path = vault if supplied == vault.as_uri() + '?mode=rw' else Path(supplied)
        valid=(path==work/'vault'/'evidence.db' or path==work/'supervisor-control'/'attempts.db' or (path.parent==work/'runtime' and
            (path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\.db',path.name))))
        if current_test!=config['targets'][0] or not valid:
            prohibited.append(event); raise RuntimeError('Only exact authority/runtime/supervisor/vault databases may open')
        if len(sqlite_connections)>=6: raise RuntimeError('Declared six parent database opens exceeded')
        sqlite_connections.append({'testId':current_test,'database':str(path),'supplied':supplied})
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


# BEGIN FROZEN HARNESS OBSERVER
"""Harness-only observations; no PID lookup, extra wait, or scheduling change."""
import os
import resource
import stat
import time


_RU_FIELDS = ('ru_utime', 'ru_stime', 'ru_maxrss', 'ru_ixrss', 'ru_idrss',
    'ru_isrss', 'ru_minflt', 'ru_majflt', 'ru_nswap', 'ru_inblock',
    'ru_oublock', 'ru_msgsnd', 'ru_msgrcv', 'ru_nsignals', 'ru_nvcsw', 'ru_nivcsw')
_ADDITIVE_FIELDS = ('ru_utime', 'ru_stime', 'ru_minflt', 'ru_majflt',
    'ru_inblock', 'ru_oublock', 'ru_nvcsw', 'ru_nivcsw')


def _pressure_read(path):
    with open(path, 'rb') as stream:
        body = stream.read(4097)
    if len(body) > 4096:
        raise ValueError('Pressure file exceeds 4096-byte observation bound')
    return body.decode('ascii')


def _usage_snapshot(get_usage=resource.getrusage, clock=time.monotonic_ns,
                    read_pressure=_pressure_read):
    value = {'beforeMonotonicNs': clock(), 'usage': {}, 'pressure': {}}
    for name, selector in (('self', resource.RUSAGE_SELF), ('children', resource.RUSAGE_CHILDREN)):
        try:
            usage = get_usage(selector)
            value['usage'][name] = {'available': True,
                'raw': {field: getattr(usage, field) for field in _RU_FIELDS}}
        except Exception as error:
            value['usage'][name] = {'available': False, 'errorType': type(error).__name__}
    for name in ('cpu', 'memory', 'io'):
        try:
            raw = read_pressure('/proc/pressure/' + name)
            if type(raw) is not str or len(raw.encode('ascii')) > 4096:
                raise ValueError('Pressure observation is not bounded ASCII text')
            value['pressure'][name] = {'available': True, 'raw': raw}
        except Exception as error:
            value['pressure'][name] = {'available': False, 'errorType': type(error).__name__}
    value['afterMonotonicNs'] = clock()
    return value


def _usage_delta(before, after):
    result = {}
    for scope in ('self', 'children'):
        first, last = before['usage'][scope], after['usage'][scope]
        if not first['available'] or not last['available']:
            result[scope] = {'available': False}
            continue
        counters = {field: last['raw'][field] - first['raw'][field] for field in _ADDITIVE_FIELDS}
        if any(value < 0 for value in counters.values()):
            result[scope] = {'available': False, 'reason': 'counter_regression'}
            continue
        result[scope] = {'available': True, 'additiveCounters': counters}
    return result


def _descriptor_identity(fd, get_stat=os.fstat):
    try:
        info = get_stat(fd)
        return {'available': True, 'descriptor': fd, 'device': info.st_dev,
            'inode': info.st_ino, 'uid': info.st_uid, 'mode': stat.S_IMODE(info.st_mode),
            'fileType': stat.S_IFMT(info.st_mode), 'size': info.st_size}
    except Exception as error:
        return {'available': False, 'descriptor': fd, 'errorType': type(error).__name__}


class _WorkerAccounting:
    def __init__(self, snapshot=_usage_snapshot, clock=time.monotonic_ns,
                 identify=_descriptor_identity, persist=lambda name, value: None):
        self.snapshot, self.clock, self.identify, self.persist = snapshot, clock, identify, persist
        self.test_id = None
        self.start = self.finish = None
        self.launch = None
        self.process = None
        self.errors = []

    def note_error(self, phase, error):
        if len(self.errors) < 32:
            self.errors.append({'phase': phase, 'errorType': type(error).__name__})

    def emit(self, name):
        try:
            self.persist(name, self.report())
        except Exception as error:
            self.note_error('persist:' + name, error)

    def start_test(self, test_id):
        if self.start is not None:
            raise RuntimeError('Exactly one original test is permitted')
        self.test_id = test_id
        self.start = self.snapshot()
        self.emit('worker-accounting-start.json')

    def before_launch(self, argv):
        if self.start is None or self.launch is not None:
            raise RuntimeError('Exactly one original launch is permitted')
        # The unchanged subprocess audit separately validates the complete argv.
        if type(argv) not in (list, tuple) or len(argv) != 7:
            raise RuntimeError('Unexpected original worker arguments')
        descriptors = {name: self.identify(int(argv[index])) for name, index in
            (('attemptDirectory', 4), ('input', 5), ('writerLease', 6))}
        self.launch = {'argv': list(argv), 'descriptors': descriptors,
            'before': self.snapshot(), 'pid': None, 'launchedMonotonicNs': None,
            'terminal': None, 'launchFailure': None}
        self.emit('worker-accounting-launch.json')

    def launched(self, process):
        self.process = process
        self.launch['pid'] = process.pid
        self.launch['launchedMonotonicNs'] = self.clock()

    def failed_launch(self, error):
        self.launch['launchFailure'] = type(error).__name__
        self.emit('worker-accounting-launch-failed.json')

    def observed_return(self, process, code, via):
        if process is not self.process:
            self.note_error('foreign-process-object', RuntimeError())
            return
        if code is None or self.launch['terminal'] is not None:
            return
        self.launch['terminal'] = {'returnCode': code, 'observedBy': via,
            'snapshot': self.snapshot()}
        self.emit('worker-accounting-terminal.json')

    def stop_test(self):
        self.finish = self.snapshot()
        self.emit('worker-accounting.json')

    def report(self):
        result = {'profile': 'hms.worker-resource-observation/1', 'testId': self.test_id,
            'testStart': self.start, 'testFinish': self.finish, 'launch': self.launch,
            'errors': list(self.errors), 'testDelta': None, 'launchToReapDelta': None,
            'units': {'ru_utime': 'seconds', 'ru_stime': 'seconds', 'ru_maxrss': 'KiB on Linux',
                'ru_inblock': 'filesystem input operations', 'ru_oublock': 'filesystem output operations',
                'ru_nvcsw': 'voluntary switches', 'ru_nivcsw': 'involuntary switches'},
            'limits': {'pressureScope': 'global host context; no process attribution',
                'childScope': 'terminated and waited-for direct child plus its waited-for descendants',
                'requiresExternalLaunchAndArchiveAudit': True, 'pidBasedSampling': False,
                'peakRssIsNotAdditive': True, 'waitCauseMeasured': False,
                'unmaintainedLinuxFieldsMayBeZero': True, 'physicalEffectsAttested': False}}
        if self.start is not None and self.finish is not None:
            result['testDelta'] = _usage_delta(self.start, self.finish)
        if self.launch is not None and self.launch['terminal'] is not None:
            result['launchToReapDelta'] = _usage_delta(self.launch['before'], self.launch['terminal']['snapshot'])
        return result


def _observed_popen(original, observer):
    class ObservedPopen(original):
        def __init__(self, args, *positional, **keywords):
            observer.before_launch(args)
            try:
                super().__init__(args, *positional, **keywords)
            except BaseException as error:
                observer.failed_launch(error)
                raise
            observer.launched(self)

        def poll(self):
            code = super().poll()
            if code is not None:
                try:
                    observer.observed_return(self, code, 'original-poll')
                except Exception as error:
                    observer.note_error('terminal-poll-observation', error)
            return code

        def wait(self, timeout=None):
            code = super().wait(timeout=timeout)
            try:
                observer.observed_return(self, code, 'original-wait')
            except Exception as error:
                observer.note_error('terminal-wait-observation', error)
            return code
    return ObservedPopen

import subprocess
worker_accounting = _WorkerAccounting(persist=write)
subprocess.Popen = _observed_popen(subprocess.Popen, worker_accounting)
# END FROZEN HARNESS OBSERVER

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
        if (name == 'hms' or name.startswith('hms.') or name == 'hms_qualification' or name.startswith('hms_qualification.') or name.startswith('test_') or name == 'evidence' or name.startswith('evidence.') or name == 'evidence_compact' or name.startswith('evidence_compact.') or name == 'evidence_vault' or name.startswith('evidence_vault.') or name == 'evidence_authority' or name.startswith('evidence_authority.') or name == 'vault_recorded_io' or name.startswith('vault_recorded_io.') or name == 'recorded_io' or name.startswith('recorded_io.')) and origin:
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
    write('child-runtime.json', {'executable': sys.executable, 'version': sys.version,
        'flags': repr(sys.flags), 'path': sys.path, 'cwd': str(Path.cwd()),
        'environment': dict(os.environ), 'stdlib': str(stdlib)})
    import unittest
    from hms.pat_compiler import compiler_digest, compiler_manifest
    write('compiler-before.json', {'digest': compiler_digest(), 'manifest': compiler_manifest()})
    from hms.synthetic_io_installation import implementation_digest
    write('driver-before.json', {'digest': implementation_digest()})
    tests = unittest.defaultTestLoader.loadTestsFromNames(config['targets'])
    loaded_ids = flatten(tests)
    write('loader-errors.json', list(unittest.defaultTestLoader.errors))
    for detail in unittest.defaultTestLoader.errors: print(detail, file=sys.stderr, flush=True)
    if loaded_ids != config['targets']:
        raise RuntimeError('Loaded methods do not exactly match the reviewed service1 selection')
    class RecordingResult(unittest.TextTestResult):
        def startTest(self, test):
            global current_test
            current_test = test.id()
            executed_ids.append(test.id())
            worker_accounting.start_test(test.id())
            super().startTest(test)
        def stopTest(self, test):
            global current_test
            super().stopTest(test)
            worker_accounting.stop_test()
            current_test = None
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)
    counts = {'testsRun': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skips': len(result.skipped), 'expectedFailures': len(result.expectedFailures),
        'unexpectedSuccesses': len(result.unexpectedSuccesses)}
    write('compiler-after.json', {'digest': compiler_digest(), 'manifest': compiler_manifest()})
    write('driver-after.json', {'digest': implementation_digest()})
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
    finalize('accounting-launch-audit', lambda: write('worker-accounting-launch-audit.json', accounting_launch_audit))
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
