"""IoAuthority32 child: isolated startup, exact selected tests and scoped origin evidence."""
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


CONTROL_TARGETS = ['test_io_service_authority.IoServiceAuthorityTests.test_added_index_refuses_and_is_retained', 'test_io_service_authority.IoServiceAuthorityTests.test_all_owned_tables_missing_with_anchor_never_reinitialize', 'test_io_service_authority.IoServiceAuthorityTests.test_before_commit_failure_rolls_back_all_configuration_rows', 'test_io_service_authority.IoServiceAuthorityTests.test_canonical_authority_bound_record_survives_runtime_reopen', 'test_io_service_authority.IoServiceAuthorityTests.test_changed_same_key_refuses_before_any_fresh_work', 'test_io_service_authority.IoServiceAuthorityTests.test_complete_descriptor_snapshot_requires_transaction_and_is_read_only', 'test_io_service_authority.IoServiceAuthorityTests.test_concurrent_changed_same_key_has_one_winner_and_one_conflict', 'test_io_service_authority.IoServiceAuthorityTests.test_concurrent_exact_mutations_commit_one_version', 'test_io_service_authority.IoServiceAuthorityTests.test_configuration_and_plan_do_not_create_device_effects_or_claims', 'test_io_service_authority.IoServiceAuthorityTests.test_configuration_change_during_planning_refuses_returned_plan', 'test_io_service_authority.IoServiceAuthorityTests.test_creation_and_history_require_current_admin_authority', 'test_io_service_authority.IoServiceAuthorityTests.test_creation_is_explicit_and_reopen_uses_no_new_connection', 'test_io_service_authority.IoServiceAuthorityTests.test_cross_authority_runtime_and_deployment_cannot_supply_configuration', 'test_io_service_authority.IoServiceAuthorityTests.test_exact_replay_precedes_source_runtime_and_later_revision_checks', 'test_io_service_authority.IoServiceAuthorityTests.test_external_configuration_drift_refuses_before_planning', 'test_io_service_authority.IoServiceAuthorityTests.test_identical_layouts_in_distinct_authorities_have_distinct_pins', 'test_io_service_authority.IoServiceAuthorityTests.test_legacy_unbound_pin_cannot_enter_authority_history', 'test_io_service_authority.IoServiceAuthorityTests.test_lost_commit_reply_replays_original_after_reopen', 'test_io_service_authority.IoServiceAuthorityTests.test_lowered_byte_capacity_refuses_before_configuration_writes', 'test_io_service_authority.IoServiceAuthorityTests.test_lowered_record_capacity_preserves_exact_replay_at_full', 'test_io_service_authority.IoServiceAuthorityTests.test_metadata_capacity_tampering_is_not_a_limit_change', 'test_io_service_authority.IoServiceAuthorityTests.test_missing_head_refuses_and_is_never_rebuilt', 'test_io_service_authority.IoServiceAuthorityTests.test_missing_permission_on_one_registration_refuses_whole_snapshot', 'test_io_service_authority.IoServiceAuthorityTests.test_mutation_header_mismatch_refuses_and_is_retained', 'test_io_service_authority.IoServiceAuthorityTests.test_non_object_receipt_refuses_and_is_retained', 'test_io_service_authority.IoServiceAuthorityTests.test_noncanonical_pin_refuses_and_is_retained', 'test_io_service_authority.IoServiceAuthorityTests.test_oversized_configuration_refuses_before_parsing', 'test_io_service_authority.IoServiceAuthorityTests.test_partial_schema_refuses_and_is_never_recreated', 'test_io_service_authority.IoServiceAuthorityTests.test_revision_compare_and_swap_and_per_evaluator_chains', 'test_io_service_authority.IoServiceAuthorityTests.test_session_change_during_planning_refuses_returned_plan', 'test_io_service_authority.IoServiceAuthorityTests.test_source_drift_blocks_fresh_plan_but_not_history_or_exact_replay', 'test_io_service_authority.IoServiceAuthorityTests.test_temp_shadow_table_refuses_before_reading_it']

def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Control selection forbids network and subprocesses')
    if event == 'sqlite3.connect':
        path=Path(os.fsdecode(os.fspath(args[0])))
        method=current_test.rsplit('.',1)[1] if current_test in CONTROL_TARGETS else 'invalid'
        if (current_test not in CONTROL_TARGETS or path.parent.parent!=scratch/method or
                path.parent.name not in {'runtime','runtime-other'} or
                not(path.name=='authority.db' or re.fullmatch(r'synthetic-io-board-[0-9a-f]{64}\.db',path.name))):
            prohibited.append(event); raise RuntimeError('Only declared authority fixture databases may open')
        if len(sqlite_connections)>=74 or sum(c['testId']==current_test for c in sqlite_connections)>=4:
            raise RuntimeError('Declared authority database inventory bound')
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
            len(config['targets']) != 32 or len(set(config['targets'])) != 32):
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
        raise RuntimeError('Loaded methods do not exactly match the reviewed authority32 selection')
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
passed = (not errors and counts is not None and counts['testsRun'] == 32 and
    all(counts[key] == 0 for key in counts if key != 'testsRun') and
    loaded_ids == config['targets'] == executed_ids and origins is not None and
    origins['summary']['allOriginsMatched'])
raise SystemExit(0 if passed else 1)
