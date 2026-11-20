"""Original isolated io-active-revocation38 runner. Execute only after parent review/release.

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
FROZEN_INDEX = '766bf534925257030f48876678e8b0e2aed5c8d01b377b27f12aee528a429444'
PREFIX = 'artifacts/implementation/pat-io-active-revocation/implementation01/'
MAX_FILE = 16 * 1024 * 1024
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_FILES = 8192
MAX_JSON = 4 * 1024 * 1024
MAX_LOG = 8 * 1024 * 1024
MAX_SCRATCH_BYTES = 64 * 1024 * 1024
OWN_FILES = ('run_attempt.py', 'attempt_child.py', 'targets.json', 'SCOPE.md',
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
    if len(expected) != 5054:
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
                raise TimeoutError('IoActiveRevocation38 child exceeded original harness deadline')
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
                raise TimeoutError('IoActiveRevocation38 child crossed harness deadline during pipe collection')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('IoActiveRevocation38 child crossed harness deadline at EOF')
    process.wait(timeout=remaining)
    if time.monotonic() >= deadline:
        raise TimeoutError('IoActiveRevocation38 child crossed harness deadline at process exit')
    return count


def counts_pass(value):
    names = {'testsRun', 'failures', 'errors', 'skips', 'expectedFailures', 'unexpectedSuccesses'}
    return (type(value) is dict and set(value) == names and
            all(type(value[key]) is int and value[key] >= 0 for key in names) and
            value['testsRun'] == 38 and all(value[key] == 0 for key in names - {'testsRun'}))


def scratch_identity(path):
    """Identify the original private directory without following a root symlink."""
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError('Raw scratch must be an actual directory')
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
            'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}


def configuration_receipts(trial, manifest):
    """Collection/association checks only; no authorization attestation."""
    config = manifest['configuration']
    if (config['profile'] != 'hms.pat.io-configuration-manifest/0.1' or
            any(config[k] is not False for k in ('configurationAttested', 'independentOutcomeChecked', 'qualificationPassed'))):
        raise ValueError('Configuration profile or claim changed')
    refs = config['records']; legacy = manifest['records']; docs = {}
    names = ['%06d.json' % i for i in range(len(refs))]
    if ([r['path'] for r in refs] != names or
            sorted(p.name for p in (trial/'configuration').iterdir()) != names):
        raise ValueError('Configuration record inventory/order changed')
    for ref in refs:
        path = trial/'configuration'/ref['path']
        if row(path, ref['path']) != ref or ref['bytes'] > 65536:
            raise ValueError('Configuration record bytes changed')
        doc = read_json(path)
        if set(doc) != {'profile', 'kind', 'value'} or doc['profile'] != 'hms.pat.io-configuration-record/0.1':
            raise ValueError('Unexpected configuration record shape')
        docs[ref['path']] = doc
    if (config['configurationBytes'] != sum(r['bytes'] for r in refs) or
            config['combinedRecords'] != len(refs)+len(legacy) or
            config['combinedBytes'] != sum(r['bytes'] for r in refs+legacy) or
            config['combinedRecords'] > 4096 or config['combinedBytes'] > 16*1024*1024):
        raise ValueError('Configuration streams exceed original shared limits')
    header = docs['000000.json']
    if header != {'profile': 'hms.pat.io-configuration-record/0.1', 'kind': 'header', 'value': {
            'transcriptProfile': 'hms.pat.io-trial-record/0.1', 'setupRecords': legacy[:4],
            'registryMetadataKeys': ['deployment', 'revision', 'version'],
            'sharedLimits': {'records':4096, 'bytes':16*1024*1024, 'documentBytes':65536, 'schedulerTicks':2048}}}:
        raise ValueError('Configuration header differs from reviewed setup/bounds')
    checkpoints = [r for r in legacy if read_json(trial/'records'/r['path'])['kind'] == 'checkpoint']
    snapshots = [r for r in refs if docs[r['path']]['kind'] == 'snapshot']
    if config['snapshots'] != [{'checkpoint': c, 'configuration': s} for c, s in zip(checkpoints, snapshots)] or len(checkpoints) != len(snapshots):
        raise ValueError('Configuration snapshot/checkpoint pairing differs')
    inventory = set(('reg_meta reg_types reg_instances reg_capabilities reg_bindings reg_binding_history '
                     'reg_presence reg_endpoint_sessions reg_session_history reg_observations reg_streams '
                     'reg_stream_history reg_grants reg_resource_requirements reg_resource_instances').split())
    used = {'000000.json'}
    for cp_ref, snap_ref in zip(checkpoints, snapshots):
        cp = read_json(trial/'records'/cp_ref['path'])['value']; snap = docs[snap_ref['path']]['value']
        used.add(snap_ref['path'])
        if (snap['checkpoint'] != cp_ref or any(snap[k] != cp[k] for k in ('phase','label','wallMs','monotonicMs','clockEpoch')) or
                snap['clockEpoch'] != snap['authorityId']+':'+str(snap['ownerEpoch']) or
                len(snap['tables']) != 15 or {t['table'] for t in snap['tables']} != inventory):
            raise ValueError('Configuration checkpoint context/table inventory differs')
        def referenced(ref, kind):
            position = int(ref['path'][:6])
            if position >= int(snap_ref['path'][:6]) or refs[position] != ref or docs[ref['path']]['kind'] != kind:
                raise ValueError('Configuration reference provenance differs')
            used.add(ref['path']); return docs[ref['path']]['value']
        resolver = referenced(snap['resolver'], 'resolver_configuration')
        if (resolver['profile'] != 'hms.pat.io-resolver-configuration/0.1' or
                resolver['resolverProfile'] != 'hms.pat.bindings.sqlite-finite-io/0.1' or len(resolver['registrations']) != 1):
            raise ValueError('Configuration resolver inventory differs')
        for table in snap['tables']:
            count = 0; columns = None
            projection = 'public_registry_metadata' if table['table'] == 'reg_meta' else 'complete'
            if table['projection'] != projection or len(table['pages']) != max(1, (table['rowCount']+7)//8):
                raise ValueError('Configuration table projection or page inventory differs')
            for ref in table['pages']:
                page = referenced(ref, 'table_page')
                if (page['table'] != table['table'] or page['projection'] != projection or page['first'] != count or
                        page['totalRows'] != table['rowCount'] or len(page['rows']) != min(8, table['rowCount']-count) or
                        (columns is not None and page['columns'] != columns)):
                    raise ValueError('Configuration table page association differs')
                columns = page['columns']
                for cells in page['rows']:
                    if len(cells) != len(columns): raise ValueError('Configuration row width differs')
                    for cell in cells:
                        if (set(cell) != {'type','value'} or not (
                                cell['type'] in {'text','blob-utf8'} and type(cell['value']) is str or
                                cell['type'] == 'integer' and type(cell['value']) is int)):
                            raise ValueError('Configuration cell type differs')
                        if cell['type'] == 'blob-utf8': json.loads(cell['value'])
                count += len(page['rows'])
            if count != table['rowCount']: raise ValueError('Configuration table count differs')
    if used != set(docs): raise ValueError('Unused or extra configuration records')
    return {'records':len(refs), 'snapshots':len(snapshots), 'bytes':config['configurationBytes'],
            'combinedRecords':config['combinedRecords'], 'combinedBytes':config['combinedBytes'],
            'configurationAttested':False, 'qualificationPassed':False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt')
    parser.add_argument('--parent-released', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=600)
    args = parser.parse_args()
    if not args.parent_released:
        raise SystemExit('Execution remains held: explicit parent source-review release is required.')
    if (not args.attempt or len(args.attempt) > 64 or
            not args.attempt.replace('-', '').replace('_', '').isalnum() or
            not 1 <= args.timeout_seconds <= 600):
        raise SystemExit('Invalid attempt name or bounded timeout')
    here = Path(__file__).resolve().parent
    stage = here.parent / 'implementation01'
    attempt = here / 'attempts' / args.attempt
    attempt.mkdir(parents=True, mode=0o700, exist_ok=False)
    tree = attempt / 'project'
    process = None
    scratch = None
    scratch_before = scratch_parent_before = None
    before = external_before = frozen_before = own_before = None
    started = time.monotonic()
    record = {'profile': 'hms.io-trial-engine-attempt/1', 'attempt': args.attempt,
              'status': 'preparing', 'currentPass': False, 'childState': 'not_started',
              'exitCode': None, 'counts': None, 'errors': [], 'expectedTests': 38,
              'projectInputCount': 5051, 'frozenPreparationInputCount': 5054,
              'timeoutSeconds': args.timeout_seconds, 'totalDiskQuotaEnforced': False,
              'limits': {'singleAcquiredFileBytes': MAX_FILE, 'inventoryFiles': MAX_FILES,
                         'inputInventoryBytes': MAX_INPUT_BYTES, 'jsonReceiptBytes': MAX_JSON,
                         'retainedLogBytes': MAX_LOG, 'scratchRetentionBytes': MAX_SCRATCH_BYTES},
              'scope': 'Original private IoRuntime capture and active-revocation tests; SQLite and original simulator phases only. No model, network, subprocess child, physical device, public service or qualification decision.'}
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
        selected = [value for value in frozen_before if value['path'].startswith(PREFIX + 'project/')]
        if len(selected) != 5051:
            raise ValueError('Candidate project closure must contain exactly 5051 files')
        for value in selected:
            relative = safe_relative(value['path'][len(PREFIX + 'project/'):])
            target = tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / 'project' / relative, target)
        before = inventory(tree)
        expected = [dict(value, path=value['path'][len(PREFIX + 'project/'):]) for value in selected]
        if before != sorted(expected, key=lambda value: value['path']):
            raise ValueError('Copied project differs from frozen candidate inputs')
        write_json(attempt / 'inputs-before.json', before)
        approved = read_json(attempt / 'harness/references/approved-external-roots.json')
        external_before = selected_external(approved)
        write_json(attempt / 'external-before.json', external_before)
        targets = read_json(attempt / 'harness/targets.json')
        if (targets['testCount'] != 38 or len(targets['targets']) != 38 or
                len(set(targets['targets'])) != 38 or any(not name.startswith(('test_pat_io_trials.IoTrialTests.', 'test_pat_io_configuration_capture.IoConfigurationCaptureTests.', 'test_pat_io_active_revocation.IoActiveRevocationTests.')) for name in targets['targets'])):
            raise ValueError('Closed active-revocation38 method selection changed')
        # Reuse the reviewed source08 ancestor/ownership checks; never chmod
        # a shared ancestor or delete the original raw scratch root.
        scratch_parent = Path('/tmp')
        scratch_parent_before = scratch_identity(scratch_parent)
        if (scratch_parent_before['uid'] not in {0, os.getuid()} or
                (scratch_parent_before['mode'] & 0o022 and
                 not scratch_parent_before['mode'] & stat.S_ISVTX)):
            raise ValueError('Trusted /tmp scratch ancestor is unavailable')
        scratch = Path(tempfile.mkdtemp(prefix='hms-io-active-revocation-', dir=str(scratch_parent)))
        record['scratchPath'] = str(scratch)
        record['rawScratchPolicy'] = ('Never deleted by this runner; raw outputs must be '
                                      'explicitly acquired before operating-system /tmp cleanup.')
        scratch_before = scratch_identity(scratch)
        if (scratch_before['uid'] != os.getuid() or scratch_before['mode'] != 0o700 or
                scratch_identity(scratch_parent) != scratch_parent_before):
            raise ValueError('Original private scratch ownership or /tmp ancestor changed')
        write_json(attempt / 'raw-scratch-before.json', {
            'identity': scratch_before, 'parent': scratch_parent_before,
            'retentionPolicy': record['rawScratchPolicy']})
        environment = {'PATH': os.pathsep.join((str(Path(sys.executable).parent), '/usr/bin', '/bin')),
                       'TMPDIR': str(scratch), 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}
        config = {'project': str(tree), 'attempt': str(attempt), 'targets': targets['targets'],
                  'scratch': str(scratch), 'externalRoots': external_before['roots'], 'expectedInputs': before,
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
            child_deadline = time.monotonic() + args.timeout_seconds
            process = subprocess.Popen(command, cwd=tree, env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            # Keep direct-child ownership before any fallible receipt write.
            record['childState'] = 'running'
            record['pid'] = process.pid
            write_json(attempt / 'owned-child.json', {'pid': process.pid, 'ownedByThisAttempt': True})
            record['status'] = 'running'
            record['retainedLogBytes'] = collect(process, log, child_deadline)
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
            actual = scratch_identity(scratch)
            parent_actual = scratch_identity(scratch.parent)
            record['rawScratchRetained'] = True
            record['rawScratchIdentityUnchanged'] = actual == scratch_before
            record['rawScratchParentIdentityUnchanged'] = parent_actual == scratch_parent_before
            record['rawScratchInventoryTerminal'] = record['childState'] in {'exited', 'not_started'}
            write_json(attempt / 'raw-scratch-after.json', {
                'identity': actual, 'before': scratch_before, 'parent': parent_actual,
                'parentBefore': scratch_parent_before, 'childState': record['childState'],
                'retentionPolicy': record['rawScratchPolicy']})
            if actual != scratch_before or parent_actual != scratch_parent_before:
                raise RuntimeError('Raw scratch or ancestor identity changed; refuse replacement inventory')
            if not record['rawScratchInventoryTerminal']:
                raise RuntimeError('Original scratch retained; producer termination is unconfirmed')
            rows = inventory(scratch, max_bytes=MAX_SCRATCH_BYTES)
            shutil.copytree(scratch, attempt / 'scratch')
            if (inventory(attempt / 'scratch', max_bytes=MAX_SCRATCH_BYTES) != rows or
                    inventory(scratch, max_bytes=MAX_SCRATCH_BYTES) != rows or
                    scratch_identity(scratch) != scratch_before or
                    scratch_identity(scratch.parent) != scratch_parent_before):
                raise RuntimeError('Scratch identity or retained bytes changed during collection')
            write_json(attempt / 'scratch-index.json', rows)
            record['scratchRetained'] = True
            record['scratchRetainedBytes'] = sum(value['bytes'] for value in rows)
            record['rawScratchMayContainUnsettledFixtureWork'] = bool(rows)
            record['rawScratchCopyVerified'] = True
            # Keep the original root even after a complete copy, including on
            # failed tests/capture/close. This is not a claim of resolved work.
        def child_receipts():
            record['counts'] = read_json(attempt / 'test-return.json')
            record['actualTests'] = read_json(attempt / 'actual-tests.json')
            record['originSummary'] = read_json(attempt / 'imports.json')['summary']
            record['childErrors'] = read_json(attempt / 'child-errors.json')
            left = read_json(attempt / 'compiler-before.json')
            right = read_json(attempt / 'compiler-after.json')
            record['compilerIdentityUnchanged'] = left == right
            record['driverIdentityUnchanged'] = read_json(attempt / 'driver-before.json') == read_json(attempt / 'driver-after.json')
        def fixture_receipts():
            selection = read_json(attempt / 'harness/targets.json')
            expected = selection['expectedEngineStates']
            ids = {name.split('.')[-1]: name for name in selection['targets']}
            methods = set(ids)
            configured = set(selection['configurationMethods'])
            active = selection['activeGrantPhases']
            if len(active) != 6 or not set(active) <= configured:
                raise ValueError('Active grant-plan selection changed')
            if len(ids) != 38 or len(configured) != 18 or not configured <= methods:
                raise ValueError('Exact configuration method selection changed')
            if set(expected) != methods or sum(expected.values()) != 37:
                raise ValueError('Exact trial fixture selection changed')
            copied = attempt / 'scratch'
            if {p.name for p in copied.iterdir()} != methods:
                raise ValueError('Missing or extra retained test workspace')
            connections = read_json(attempt / 'imports.json')['sqliteConnections']
            actual_connections = {(row['testId'], row['database']) for row in connections}
            expected_connections, summaries = set(), []
            for method, count in sorted(expected.items()):
                workspace = copied / method
                if count == 0:
                    if (sorted(p.name for p in workspace.iterdir()) != ['nonempty'] or
                            sorted(p.name for p in (workspace/'nonempty').iterdir()) != ['marker'] or
                            (workspace/'nonempty/marker').read_text() != 'retain'):
                        raise ValueError('Directory-refusal fixture was changed')
                    continue
                if count != 1 or sorted(p.name for p in workspace.iterdir()) != ['engine-0.json', 'trial-0']:
                    raise ValueError('Trial fixture inventory changed')
                manifest = read_json(workspace/'engine-0.json')
                test_id = ids[method]
                source = scratch / method / 'trial-0'
                if (manifest['testId'] != test_id or manifest['directory'] != str(source) or
                        manifest['closed'] is not True or manifest['cleanupErrors'] != [] or
                        manifest['report']['qualificationPassed'] is not False or
                        manifest['report']['independentOutcomeChecked'] is not False):
                    raise ValueError('Missing closure/provenance or unexpected qualification claim')
                if method in active:
                    principal, deployment = 'pat-io-trial-worker', 'simulation:io-hub'
                    target = 'sim:pwm5' if method == 'test_active_pwm_revocation_restores_all_claimed_outputs' else 'sim:gpio5'
                    expected_authority = {'profile':'hms.pat.io-trusted-authority/0.1','principal':principal,'deployment':deployment,
                        'initialRegistryRevision':13,'initialGrants':[{'principal':principal,'deployment':deployment,'target':'*','verb':'admin'}],
                        'grantChanges':[{'phase':active[method],'label':'drive:adapters:before',
                            'grants':[{'principal':principal,'deployment':deployment,'target':target,'verb':'read'}]}]}
                    if manifest.get('expectedAuthority') != expected_authority:
                        raise ValueError('Trusted active grant plan differs from reviewed selection')
                trial = workspace/'trial-0'
                if sorted(p.name for p in trial.iterdir()) != (['configuration', 'records', 'state'] if method in configured else ['records', 'state']):
                    raise ValueError('Trial output layout changed')
                refs = manifest['records']
                if not isinstance(refs, list) or not 1 <= len(refs) <= 4096:
                    raise ValueError('Trial record inventory exceeds fixed bound')
                wanted = ['%06d.json' % index for index in range(len(refs))]
                if [r['path'] for r in refs] != wanted or sorted(p.name for p in (trial/'records').iterdir()) != wanted:
                    raise ValueError('Trial record order or file inventory differs')
                for reference in refs:
                    path = trial/'records'/reference['path']
                    if row(path, reference['path']) != reference or reference['bytes'] > 65536:
                        raise ValueError('Trial record bytes changed')
                    if read_json(path).get('profile') != 'hms.pat.io-trial-record/0.1':
                        raise ValueError('Unexpected trial record profile')
                configuration_summary = configuration_receipts(trial, manifest) if method in configured else None
                names = sorted(p.name for p in (trial/'state').iterdir())
                databases = [name for name in names if name.endswith('.db')]
                if (len(databases) != 2 or 'authority.db' not in databases or
                        not any(name.startswith('synthetic-io-board-') for name in databases) or
                        names != sorted(databases + [name+'.owner' for name in databases])):
                    raise ValueError('Retained closed database inventory differs')
                expected_connections.update((test_id, str(source/'state'/name)) for name in databases)
                summaries.append({'method': method, 'records': len(refs), 'databases': databases,
                                  'unresolvedOperations': manifest['report']['unresolvedOperations'],
                                  'configuration': configuration_summary})
            if actual_connections != expected_connections:
                raise ValueError('Database connections differ from exact per-method retained state')
            record['fixtureSummary'] = {'testWorkspaces': 38, 'engineStates': len(summaries),
                'databases': sum(len(v['databases']) for v in summaries),
                'records': sum(v['records'] for v in summaries),
                'configurationRecords': sum(v['configuration']['records'] for v in summaries if v['configuration']),
                'configurationSnapshots': sum(v['configuration']['snapshots'] for v in summaries if v['configuration']),
                'allExpectedRetained': True}
            write_json(attempt/'fixture-summary.json', {'summary': record['fixtureSummary'], 'states': summaries})
        for label, callback in [('sources-after', sources_after), ('external-after', external_after),
                                ('scratch-retention', retain_scratch), ('child-receipts', child_receipts),
                                ('fixture-receipts', fixture_receipts)]:
            finalize(label, callback)
        flags = ('inputsUnchanged', 'frozenPreparationUnchanged', 'harnessUnchanged',
                 'retainedHarnessUnchanged', 'externalInputsUnchanged', 'compilerIdentityUnchanged', 'driverIdentityUnchanged',
                 'scratchRetained', 'rawScratchRetained', 'rawScratchIdentityUnchanged',
                 'rawScratchParentIdentityUnchanged', 'rawScratchInventoryTerminal', 'rawScratchCopyVerified')
        record['currentPass'] = (record['exitCode'] == 0 and record['childState'] == 'exited' and
            not record['errors'] and counts_pass(record['counts']) and not record.get('childErrors', [1]) and
            all(record.get(flag) is True for flag in flags) and
            record.get('fixtureSummary', {}).get('allExpectedRetained') is True and
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
