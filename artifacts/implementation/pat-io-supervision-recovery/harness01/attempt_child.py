"""IoRecovery171 child: isolated startup, exact selected tests and scoped origin evidence."""
import hashlib
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


CONTROL_TARGETS = ['test_io_supervisor_recovery.IoControlRecoveryTests.test_admission_replay_conflict_and_detachment', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_caller_mapping_mutation_cannot_change_retained_launch_input', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_concurrent_replay_and_conflict_do_not_launch_twice', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_each_corrupt_control_record_is_refused_and_left_unrestored', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_exit_eof_after_selector_wait_still_fails_parent_deadline', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_held_missing_and_replaced_leases_remain_unknown', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_malformed_return_bytes_are_preserved_without_success', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_one_active_attempt_and_owner_are_preserved', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_partial_schema_refuses_without_reinitialization', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_retention_and_image_reservation_refuse_before_admission', 'test_io_supervisor_recovery.IoControlRecoveryTests.test_unarmed_owner_loss_is_terminal_and_replays_without_fresh_setup']
CONTROL_LABELS = ['supervisor', 'held', 'missing', 'replaced', 'case-00', 'case-01', 'case-02', 'case-03', 'case-04', 'case-05', 'case-06', 'case-07', 'case-08', 'case-09', 'case-10']

def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Control selection forbids network and subprocesses')
    if event == 'sqlite3.connect':
        path=Path(os.fsdecode(os.fspath(args[0])))
        allowed=current_test in CONTROL_TARGETS
        method=current_test.rsplit('.',1)[1] if allowed else 'invalid'
        if not allowed or path.parent.parent!=scratch/method or path.parent.name not in CONTROL_LABELS or path.name!='attempts.db':
            prohibited.append(event); raise RuntimeError('Only declared control fixture ledgers may open')
        if len(sqlite_connections)>=32 or sum(c['testId']==current_test for c in sqlite_connections)>=16:
            raise RuntimeError('Declared control ledger inventory bound')
        sqlite_connections.append({'testId':current_test,'database':str(path)})
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


def actual_origins():
    rows, violations, seen = [], [], set()
    def add(label, origin):
        if not isinstance(origin, str) or origin.startswith('<') or origin in {'built-in', 'frozen'}:
            rows.append({'source': label, 'origin': str(origin), 'kind': 'interpreter_or_synthetic'})
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
        if (name == 'hms' or name.startswith('hms.') or name.startswith('test_')) and origin:
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
            len(config['targets']) != 171 or len(set(config['targets'])) != 171):
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
    if loaded_ids != config['targets']:
        raise RuntimeError('Loaded methods do not exactly match the reviewed recovery171 selection')
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
passed = (not errors and counts is not None and counts['testsRun'] == 171 and
    all(counts[key] == 0 for key in counts if key != 'testsRun') and
    loaded_ids == config['targets'] == executed_ids and origins is not None and
    origins['summary']['allOriginsMatched'])
raise SystemExit(0 if passed else 1)
