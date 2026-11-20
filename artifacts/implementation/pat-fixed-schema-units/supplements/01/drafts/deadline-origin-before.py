"""Original isolated pure34 runner. Execute only after parent review/release.

No project imports occur in this launcher. Seven selected distribution closures
are acquired independently of the compiler's five-package identity.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import _sqlite3

PACKAGES = ('jsonschema', 'referencing', 'jsonschema-specifications', 'attrs',
            'rpds-py', 'typing_extensions', 'idna')
FROZEN_INDEX = 'f9c8c2b6a12c2e5bd055338b15791f8f41e75b787a78c583d65f15a9411cab14'
PREFIX = 'artifacts/implementation/pat-fixed-schema-units/'
MAX_FILE = 16 * 1024 * 1024
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_FILES = 8192
MAX_JSON = 4 * 1024 * 1024
MAX_LOG = 8 * 1024 * 1024
MAX_SCRATCH_BYTES = 16 * 1024 * 1024
OWN_FILES = ('run_attempt.py', 'attempt_child.py', 'targets.json', 'ERRATUM.md',
             'references/approved-external-roots.json', 'borrowed-inputs.json')


def digest(path):
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('File is missing or exceeds acquisition bound: ' + str(path))
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def row(path, relative):
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Only regular non-symlink input files are supported: ' + str(path))
    return {'path': relative, 'bytes': path.stat().st_size, 'sha256': digest(path)}


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise ValueError('JSON receipt is missing, linked or oversized: ' + str(path))
    return json.loads(path.read_text())


def write_json(path, value):
    encoded = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    if len(encoded) > MAX_JSON:
        raise ValueError('JSON receipt exceeds emission bound: ' + str(path))
    path.write_bytes(encoded)


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {'..', '.'} for part in path.parts):
        raise ValueError('Unsafe retained relative path')
    return path


def inventory(directory, *, max_bytes=MAX_INPUT_BYTES):
    rows, total = [], 0
    for base, directories, filenames in os.walk(directory, followlinks=False):
        for name in directories:
            if (Path(base) / name).is_symlink():
                raise ValueError('Linked directory in retained tree')
        for name in filenames:
            path = Path(base) / name
            record = row(path, str(path.relative_to(directory)))
            rows.append(record)
            total += record['bytes']
            if len(rows) > MAX_FILES or total > max_bytes:
                raise ValueError('Retained tree exceeds collection bound')
    return sorted(rows, key=lambda value: value['path'])


def frozen_inputs(stage):
    index = stage / 'index.json'
    if digest(index) != FROZEN_INDEX:
        raise ValueError('Frozen source-preparation index changed')
    value = read_json(index)
    expected = value['files']
    if len(expected) != 336:
        raise ValueError('Frozen inventory count changed')
    actual = []
    for expected_row in expected:
        name = expected_row['path']
        if not name.startswith(PREFIX):
            raise ValueError('Input escaped frozen stage prefix')
        relative = safe_relative(name[len(PREFIX):])
        acquired = row(stage / relative, name)
        if acquired != expected_row:
            raise ValueError('Frozen input changed: ' + name)
        actual.append(acquired)
    return actual


def selected_external(approved):
    metadata = {value['package']: value for value in approved['selectedMetadata']}
    if set(metadata) != set(PACKAGES):
        raise ValueError('Selected distribution set is not the closed seven-package set')
    approved_roots = {str(Path(value).resolve()) for value in approved['roots']}
    rows, exclusions, roots, total = [], [], set(), 0
    for package in PACKAGES:
        distribution = importlib.metadata.distribution(package)
        root = Path(distribution.locate_file('')).resolve()
        pin = metadata[package]
        if str(root) not in approved_roots or distribution.version != pin['version']:
            raise ValueError('Selected distribution root/version differs from reviewed pin')
        metadata_path = Path(pin['metadataPath'])
        if row(metadata_path, str(metadata_path)) != {
                'path': str(metadata_path), 'bytes': pin['bytes'], 'sha256': pin['sha256']}:
            raise ValueError('Selected metadata differs from reviewed pin')
        roots.add(str(root))
        if not distribution.files:
            raise ValueError('Selected distribution has no inventoried files')
        for item in sorted(distribution.files, key=str):
            if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts or item.suffix == '.pyc':
                exclusions.append({'package': package, 'path': str(item),
                                   'reason': 'non-package-path-or-bytecode-cache'})
                continue
            path = Path(distribution.locate_file(item))
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError('Selected file resolves outside reviewed package root')
            acquired = row(path, str(item))
            acquired.update(package=package, version=distribution.version, resolvedPath=str(resolved))
            rows.append(acquired)
            total += acquired['bytes']
            if len(rows) > MAX_FILES or total > MAX_INPUT_BYTES:
                raise ValueError('Selected dependencies exceed acquisition bound')
    for label, path in [('python', Path(sys.executable).resolve()),
                        ('sqlite-extension', Path(_sqlite3.__file__).resolve())]:
        acquired = row(path, str(path))
        acquired.update(runtime=label, resolvedPath=str(path))
        rows.append(acquired)
    return {'files': rows, 'roots': sorted(roots), 'excludedRecords': exclusions,
            'pythonVersion': sys.version, 'sqliteVersion': _sqlite3.sqlite_version}


def stop_owned(process, record):
    if process is None:
        record['childState'] = 'not_started'
        return
    for action in ('terminate', 'kill'):
        if process.poll() is not None:
            break
        try:
            getattr(process, action)()
            record.setdefault('signalsAttempted', []).append(action)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            break
    record['exitCode'] = process.poll()
    record['childState'] = 'exited' if process.returncode is not None else 'termination_unconfirmed'


def collect(process, log, deadline):
    """Bound retained pipe bytes and wall wait; only this owned child is stopped."""
    count = 0
    with selectors.DefaultSelector() as selector:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Pure34 child exceeded original harness deadline')
            for key, _ in selector.select(min(remaining, 0.1)):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                if count + len(block) > MAX_LOG:
                    log.write(block[:MAX_LOG - count])
                    log.flush()
                    raise ValueError('Child output exceeded fixed retained log bound')
                log.write(block)
                count += len(block)
            if time.monotonic() >= deadline:
                raise TimeoutError('Pure34 child crossed harness deadline during pipe collection')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Pure34 child crossed harness deadline at EOF')
    process.wait(timeout=remaining)
    if time.monotonic() >= deadline:
        raise TimeoutError('Pure34 child crossed harness deadline at process exit')
    return count


def counts_pass(value):
    names = {'testsRun', 'failures', 'errors', 'skips', 'expectedFailures', 'unexpectedSuccesses'}
    return (type(value) is dict and set(value) == names and
            all(type(value[key]) is int and value[key] >= 0 for key in names) and
            value['testsRun'] == 34 and all(value[key] == 0 for key in names - {'testsRun'}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt')
    parser.add_argument('--parent-released', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=180)
    args = parser.parse_args()
    if not args.parent_released:
        raise SystemExit('Execution remains held: explicit parent source-review release is required.')
    if (not args.attempt or len(args.attempt) > 64 or
            not args.attempt.replace('-', '').replace('_', '').isalnum() or
            not 1 <= args.timeout_seconds <= 600):
        raise SystemExit('Invalid attempt name or bounded timeout')
    here = Path(__file__).resolve().parent
    stage = here.parents[1]
    attempt = here / 'attempts' / args.attempt
    attempt.mkdir(parents=True, mode=0o700, exist_ok=False)
    tree = attempt / 'project'
    process = None
    scratch = None
    before = external_before = frozen_before = own_before = None
    started = time.monotonic()
    record = {'profile': 'hms.fixed-unit-pure-attempt/1', 'attempt': args.attempt,
              'status': 'preparing', 'currentPass': False, 'childState': 'not_started',
              'exitCode': None, 'counts': None, 'errors': [], 'expectedTests': 34,
              'projectInputCount': 152, 'frozenPreparationInputCount': 336,
              'timeoutSeconds': args.timeout_seconds, 'totalDiskQuotaEnforced': False,
              'limits': {'singleAcquiredFileBytes': MAX_FILE, 'inventoryFiles': MAX_FILES,
                         'inputInventoryBytes': MAX_INPUT_BYTES, 'jsonReceiptBytes': MAX_JSON,
                         'retainedLogBytes': MAX_LOG, 'scratchRetentionBytes': MAX_SCRATCH_BYTES},
              'scope': 'Pure compiler/validation tests only; no Runtime construction, SQLite connection, network, native endpoints, model or hardware execution.'}
    write_json(attempt / 'started.json', record)
    try:
        own_before = [row(here / name, name) for name in OWN_FILES]
        write_json(attempt / 'harness-before.json', own_before)
        for name in OWN_FILES:
            target = attempt / 'harness' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(here / name, target)
        frozen_before = frozen_inputs(stage)
        write_json(attempt / 'frozen-before.json', frozen_before)
        selected = [value for value in frozen_before if value['path'].startswith(PREFIX + 'staged/')]
        if len(selected) != 152:
            raise ValueError('Candidate project closure must contain exactly 152 files')
        for value in selected:
            relative = safe_relative(value['path'][len(PREFIX + 'staged/'):])
            target = tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / 'staged' / relative, target)
        before = inventory(tree)
        expected = [dict(value, path=value['path'][len(PREFIX + 'staged/'):]) for value in selected]
        if before != sorted(expected, key=lambda value: value['path']):
            raise ValueError('Copied project differs from frozen candidate inputs')
        write_json(attempt / 'inputs-before.json', before)
        approved = read_json(attempt / 'harness/references/approved-external-roots.json')
        external_before = selected_external(approved)
        write_json(attempt / 'external-before.json', external_before)
        targets = read_json(attempt / 'harness/targets.json')
        if (targets['testCount'] != 34 or len(targets['targets']) != 34 or
                len(set(targets['targets'])) != 34 or
                sum(name.startswith('test_pat_compiler.PatCompilerTests.') for name in targets['targets']) != 20 or
                sum(name.startswith('test_pat_fixed_schema_units.FixedSchemaUnitTests.') for name in targets['targets']) != 14 or
                any('test_all_three_families_compile_and_execute_across_two_local_aliases' in name for name in targets['targets'])):
            raise ValueError('Closed pure34 method selection changed')
        scratch = Path(tempfile.mkdtemp(prefix='hms-fixed-units-', dir='/tmp'))
        os.chmod(scratch, 0o700)
        environment = {'PATH': os.pathsep.join((str(Path(sys.executable).parent), '/usr/bin', '/bin')),
                       'TMPDIR': str(scratch), 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}
        config = {'project': str(tree), 'attempt': str(attempt), 'targets': targets['targets'],
                  'externalRoots': external_before['roots'], 'expectedInputs': before,
                  'expectedExternalInputs': external_before['files'],
                  'childSha256': digest(attempt / 'harness/attempt_child.py')}
        write_json(attempt / 'child-config.json', config)
        command = [sys.executable, '-I', '-S', '-B', str(attempt / 'harness/attempt_child.py'),
                   str(attempt / 'child-config.json')]
        write_json(attempt / 'command.json', {'argv': command, 'cwd': str(tree), 'environment': environment})
        write_json(attempt / 'parent-runtime.json', {'executable': sys.executable, 'version': sys.version,
                   'flags': repr(sys.flags), 'cwd': str(Path.cwd()), 'sqliteVersion': _sqlite3.sqlite_version})
        record['status'] = 'launching'
        with (attempt / 'output.log').open('xb') as log:
            process = subprocess.Popen(command, cwd=tree, env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            # Keep direct-child ownership before any fallible receipt write.
            record['childState'] = 'running'
            record['pid'] = process.pid
            write_json(attempt / 'owned-child.json', {'pid': process.pid, 'ownedByThisAttempt': True})
            record['status'] = 'running'
            record['retainedLogBytes'] = collect(process, log, time.monotonic() + args.timeout_seconds)
            record['exitCode'] = process.returncode
    except BaseException as exc:
        record['status'] = 'timed_out' if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else 'failed'
        record['errors'].append({'phase': 'execution', 'type': type(exc).__name__, 'message': str(exc)[:4096]})
        try:
            (attempt / 'runner-error.txt').write_text(traceback.format_exc()[-65536:])
        except BaseException:
            pass
    finally:
        def finalize(label, callback):
            try:
                callback()
            except BaseException as exc:
                record['errors'].append({'phase': label, 'type': type(exc).__name__, 'message': str(exc)[:4096]})
        finalize('owned-child-cleanup', lambda: stop_owned(process, record))
        if process is not None and process.stdout is not None:
            finalize('pipe-close', process.stdout.close)
        def sources_after():
            if before is not None:
                after = inventory(tree)
                write_json(attempt / 'inputs-after.json', after)
                record['inputsUnchanged'] = before == after
            if frozen_before is not None:
                after = frozen_inputs(stage)
                write_json(attempt / 'frozen-after.json', after)
                record['frozenPreparationUnchanged'] = frozen_before == after
            if own_before is not None:
                after = [row(here / name, name) for name in OWN_FILES]
                write_json(attempt / 'harness-after.json', after)
                record['harnessUnchanged'] = own_before == after
                record['retainedHarnessUnchanged'] = own_before == [row(attempt / 'harness' / name, name) for name in OWN_FILES]
        def external_after():
            if external_before is not None:
                after = selected_external(read_json(attempt / 'harness/references/approved-external-roots.json'))
                write_json(attempt / 'external-after.json', after)
                record['externalInputsUnchanged'] = external_before == after
                record['externalInputCount'] = len(external_before['files'])
        def retain_scratch():
            if scratch is None:
                return
            record['scratchPath'] = str(scratch)
            if record['childState'] != 'exited':
                raise RuntimeError('Scratch remains in place because producer termination is unconfirmed')
            rows = inventory(scratch, max_bytes=MAX_SCRATCH_BYTES)
            shutil.copytree(scratch, attempt / 'scratch')
            if inventory(attempt / 'scratch', max_bytes=MAX_SCRATCH_BYTES) != rows:
                raise RuntimeError('Scratch retention changed bytes')
            write_json(attempt / 'scratch-index.json', rows)
            record['scratchRetained'] = True
            record['scratchRetainedBytes'] = sum(value['bytes'] for value in rows)
            shutil.rmtree(scratch)
        def child_receipts():
            record['counts'] = read_json(attempt / 'test-return.json')
            record['actualTests'] = read_json(attempt / 'actual-tests.json')
            record['originSummary'] = read_json(attempt / 'imports.json')['summary']
            record['childErrors'] = read_json(attempt / 'child-errors.json')
            left = read_json(attempt / 'compiler-before.json')
            right = read_json(attempt / 'compiler-after.json')
            record['compilerIdentityUnchanged'] = left == right
        for label, callback in [('sources-after', sources_after), ('external-after', external_after),
                                ('scratch-retention', retain_scratch), ('child-receipts', child_receipts)]:
            finalize(label, callback)
        flags = ('inputsUnchanged', 'frozenPreparationUnchanged', 'harnessUnchanged',
                 'retainedHarnessUnchanged', 'externalInputsUnchanged', 'compilerIdentityUnchanged', 'scratchRetained')
        record['currentPass'] = (record['exitCode'] == 0 and record['childState'] == 'exited' and
            not record['errors'] and counts_pass(record['counts']) and not record.get('childErrors', [1]) and
            all(record.get(flag) is True for flag in flags) and
            record.get('originSummary', {}).get('allOriginsMatched') is True and
            record.get('actualTests', {}).get('exactSelection') is True)
        if record['currentPass']:
            record['status'] = 'passed'
        elif record['status'] in {'preparing', 'launching', 'running'}:
            record['status'] = 'failed'
        record['elapsedSeconds'] = time.monotonic() - started
        try:
            write_json(attempt / 'result.json', record)
        except BaseException as exc:
            record['currentPass'] = False
            print('Final result write failed:', type(exc).__name__, str(exc), file=sys.stderr)
        print(json.dumps({key: record[key] for key in ('attempt', 'status', 'currentPass', 'counts', 'errors')}, indent=2))
    return 0 if record['currentPass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
