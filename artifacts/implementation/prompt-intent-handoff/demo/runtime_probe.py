#!/usr/bin/env python3
"""Original bounded read-tool demonstration; root reviews before execution.

Run directly using the pinned Python with -I -B. This process creates a NEW
legacy synthetic Runtime and calls only discover, describe and observe. It
never imports the handoff's private hms closure or starts Runtime workers.
"""
from pathlib import Path
import hashlib
import json
import os
import resource
import signal
import sqlite3
import stat
import sys
import threading
import time
import traceback

ROOT = Path('/home/bud/Desktop/bud/hms')
HERE = ROOT / 'artifacts/implementation/prompt-intent-handoff/demo'
BASELINE = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASELINE_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
ATTEMPT = HERE / 'runtime-probe-attempt01'
PROMPT_PATH = HERE / 'prompt.txt'
LIMITS = {'wallSeconds': 30, 'cpuSeconds': 30, 'addressSpaceBytes': 512 * 1024 * 1024,
          'perFileBytes': 1024 * 1024, 'openFiles': 64, 'coreBytes': 0,
          'outputFiles': 16, 'aggregateOutputBytes': 4 * 1024 * 1024}
WORK_TABLES = ('operations', 'claims', 'events', 'replay_keys', 'namespaces',
               'series', 'resource_floors', 'pr_procedures', 'pr_steps',
               'pr_keys', 'pr_events')
DENIED_EVENTS = frozenset({'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.exec',
                          'os.system', 'subprocess.Popen', 'pty.spawn',
                          'socket.__new__', 'socket.connect', 'socket.bind'})
BLOCKED_ATTEMPTS = []


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def data(path, maximum=1024 * 1024):
    """Bounded ordinary-file read; detect replacement within this read."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'FILE_BOUND_OR_TYPE')
        chunks, remaining = [], maximum + 1
        while remaining:
            part = os.read(fd, min(65536, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'FILE_CHANGED')
        require(len(raw) == before.st_size <= maximum, 'FILE_SIZE_CHANGED')
        return raw
    finally:
        os.close(fd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8') + b'\n'


def save(name, value, *, raw=False):
    content = value if raw else encoded(value)
    require(type(content) is bytes and len(content) <= LIMITS['perFileBytes'], 'RECEIPT_BOUND')
    path = ATTEMPT / name
    with path.open('xb') as out:
        out.write(content)
        out.flush()
        os.fsync(out.fileno())
    return {'path': name, 'bytes': len(content), 'sha256': sha(content)}


def verify_inputs():
    pins = json.loads(data(HERE / 'runtime_probe.pins.json'))
    require(set(pins) == {'schema', 'source', 'interpreter', 'baseline', 'prompt'}, 'PIN_FIELDS')
    require(pins['schema'] == 'hms-read-runtime-probe-pins/1', 'PIN_SCHEMA')
    for key in ('source', 'interpreter', 'baseline', 'prompt'):
        item = pins[key]
        require(set(item) == {'path', 'bytes', 'sha256'}, 'PIN_ROW')
        raw = data(Path(item['path']), 16 * 1024 * 1024 if key == 'interpreter' else 1024 * 1024)
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'PIN_CHANGED:' + key)
    require(pins['source']['path'] == str(HERE / 'runtime_probe.py') and
            pins['interpreter']['path'] == str(Path(sys.executable).resolve()) and
            pins['baseline']['path'] == str(BASELINE) and
            pins['baseline']['sha256'] == BASELINE_SHA and
            pins['prompt']['path'] == str(PROMPT_PATH), 'PIN_ASSOCIATION')
    receipt = json.loads(data(BASELINE))
    require(receipt['passed'] is True and receipt['inputs_stable'] is True and
            receipt['tests'] == 866, 'PUBLIC_BASELINE')
    old = receipt['files_before']
    require(len(old) == 244 and len({r['path'] for r in old}) == 244, 'PUBLIC_COUNT')
    require({(r['path'], r['sha256'], r['bytes']) for r in old} ==
            {(r['path'], r['sha256'], r['bytes']) for r in receipt['files_after']}, 'BASELINE_JOIN')
    rows = []
    for row in sorted(old, key=lambda r: r['path']):
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'PUBLIC_PATH')
        raw = data(ROOT / relative)
        require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'PUBLIC_CHANGED:' + row['path'])
        rows.append({'path': row['path'], 'bytes': len(raw), 'sha256': sha(raw)})
    return {'pins': pins, 'publicInputs': rows}


def no_children_or_threads():
    tasks = sorted(p.name for p in Path('/proc/self/task').iterdir())
    require(tasks == [str(os.getpid())] and threading.active_count() == 1, 'UNEXPECTED_THREAD')
    children = (Path('/proc/self/task') / str(os.getpid()) / 'children').read_text().strip()
    require(children == '', 'UNEXPECTED_CHILD')
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    require(usage.ru_utime == 0 and usage.ru_stime == 0, 'CHILD_USAGE')
    return {'taskIds': tasks, 'children': [], 'childUserSeconds': usage.ru_utime,
            'childSystemSeconds': usage.ru_stime}


def deny_external(event, args):
    if event in DENIED_EVENTS:
        if len(BLOCKED_ATTEMPTS) < 8:
            BLOCKED_ATTEMPTS.append(event)
        raise RuntimeError('FORBIDDEN_PROCESS_OR_SOCKET:' + event)


def snapshot(state):
    """Evidence only: separate query-only connections; no authority API writes."""
    output = {}
    for filename in ('authority.db', 'simulated-plant.db'):
        db = sqlite3.connect((state / filename).as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            require(db.execute('PRAGMA query_only').fetchone()[0] == 1, 'QUERY_ONLY')
            tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            if filename == 'authority.db':
                require(set(WORK_TABLES) <= set(tables), 'WORK_SCHEMA')
                counts = {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                          for name in WORK_TABLES}
                require(all(count == 0 for count in counts.values()), 'WORK_WAS_CREATED')
                output['authority'] = {'tables': tables, 'workCounts': counts}
            else:
                require(tables == ['devices', 'fences', 'meta', 'receipts'], 'PLANT_SCHEMA')
                rows = [{'id': r[0], 'value': json.loads(r[1]), 'effects': r[2]}
                        for r in db.execute('SELECT id,value,effects FROM devices ORDER BY id')]
                require([r['id'] for r in rows] == ['sim:home-fan', 'sim:inspection-cell', 'sim:microscope'],
                        'PLANT_INVENTORY')
                require(all(type(r['value']) is int and r['value'] == 0 and
                            type(r['effects']) is int and r['effects'] == 0 for r in rows), 'PLANT_EFFECT')
                counts = {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                          for name in ('receipts', 'fences')}
                require(counts == {'receipts': 0, 'fences': 0}, 'PLANT_WORK')
                output['plant'] = {'devices': rows, 'workCounts': counts}
        finally:
            db.close()
    return output


def inventory():
    rows = []
    for path in sorted(ATTEMPT.rglob('*')):
        require(not path.is_symlink(), 'OUTPUT_SYMLINK')
        if path.is_file():
            raw = data(path)
            rows.append({'path': str(path.relative_to(ATTEMPT)), 'bytes': len(raw), 'sha256': sha(raw)})
    require(len(rows) <= LIMITS['outputFiles'] and
            sum(r['bytes'] for r in rows) <= LIMITS['aggregateOutputBytes'], 'OUTPUT_AGGREGATE_BOUND')
    return rows


def interrupted(number, frame):
    raise RuntimeError('PROBE_INTERRUPTED:' + str(number))


def main():
    require(sys.flags.isolated == 1 and sys.dont_write_bytecode and len(sys.argv) == 1, 'USE_PINNED_PYTHON_-I_-B')
    require(Path(__file__).resolve() == HERE / 'runtime_probe.py', 'FIXED_PROBE_SOURCE')
    os.umask(0o077)
    for kind, value in ((resource.RLIMIT_CPU, LIMITS['cpuSeconds']),
                        (resource.RLIMIT_AS, LIMITS['addressSpaceBytes']),
                        (resource.RLIMIT_FSIZE, LIMITS['perFileBytes']),
                        (resource.RLIMIT_NOFILE, LIMITS['openFiles']), (resource.RLIMIT_CORE, 0)):
        current = resource.getrlimit(kind)
        require(current[1] == resource.RLIM_INFINITY or current[1] >= value, 'INHERITED_LIMIT_TOO_SMALL')
        resource.setrlimit(kind, (value, value))
    ATTEMPT.mkdir(mode=0o700, exist_ok=False)
    started = time.monotonic_ns()
    runtime, before, after, zero_before, zero_after = None, None, None, None, None
    failures, modules, replies = [], [], []
    runtime_closed = False
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM, signal.SIGXCPU):
        signal.signal(sig, interrupted)
    signal.setitimer(signal.ITIMER_REAL, LIMITS['wallSeconds'])
    sys.addaudithook(deny_external)
    try:
        before = verify_inputs()
        save('public-inputs-before.json', before)
        no_children_or_threads()
        require(not any(k == 'hms' or k.startswith('hms.') for k in sys.modules), 'HMS_ALREADY_IMPORTED')
        sys.path.insert(0, str(ROOT))
        # -B prevents writes, not reads of old bytecode. An exclusive absent
        # prefix prevents importing an unpinned public __pycache__ image.
        sys.pycache_prefix = str(ATTEMPT / 'absent-bytecode-cache')
        require(not Path(sys.pycache_prefix).exists(), 'BYTECODE_CACHE_EXISTS')
        from hms.runtime import Runtime
        from hms.journal import Context
        context = Context('demo:prompt-reader', 'simulation:local')
        runtime = Runtime(ATTEMPT / 'state', create=True, owner=context)
        require(runtime.deployment == 'simulation:local' and set(runtime.adapters) == {'simulator:local'} and
                runtime.compact is None and runtime._procedure_thread is None and not runtime._threads,
                'READ_ONLY_LEGACY_PROFILE')
        zero_before = snapshot(ATTEMPT / 'state')
        def read(method, params):
            require(method in ('discover', 'describe', 'observe'), 'READ_METHOD_ONLY')
            reply = {'ok': True, 'result': runtime.request(context, method, params)}
            replies.append({'method': method, 'params': params, 'reply': reply,
                            'sessionId': None, 'callId': None})
            return reply['result']
        found = read('discover', {'capability': 'sim:home-fan', 'limit': 8})
        require(found['cursor'] is None and len(found['items']) == 1, 'ONE_INSTALLED_FAN')
        fan = found['items'][0]['instanceId']
        require(fan == 'sim:home-fan' and found['items'][0]['identityKind'] == 'simulation', 'SYNTHETIC_FAN')
        description = read('describe', {'instanceId': fan})
        require(description['binding']['mode'] == 'simulation' and description['bindingActive'] is True,
                'SIMULATED_BINDING')
        for prop, expected in (('value', 0), ('ready', True)):
            sample = read('observe', {'instanceId': fan, 'property': prop,
                                     'evidenceKind': 'simulation', 'maxAgeMs': 600000})
            require(sample['evidenceKind'] == 'simulation' and sample['quality'] == 'valid' and
                    type(sample['value']) is type(expected) and sample['value'] == expected, 'INITIAL_SAMPLE')
        require(len(encoded(replies)) <= 16384, 'DISCOVERY_ATTACHMENT_BOUND')
        save('discovery.json', replies)
        prompt = data(PROMPT_PATH, 8192)
        require(prompt.decode('utf-8').strip() != '', 'EMPTY_PROMPT')
        save('prompt.txt', prompt, raw=True)
        require(runtime._procedure_thread is None and not runtime._threads and runtime._thread is None,
                'WORKERS_NOT_STARTED')
        indexed = {row['path']: row for row in before['publicInputs']}
        for name, module in sorted(sys.modules.items()):
            if name == 'hms' or name.startswith('hms.'):
                path = Path(module.__file__).resolve()
                relative = str(path.relative_to(ROOT))
                require(relative in indexed and sha(data(path)) == indexed[relative]['sha256'], 'MIXED_HMS_ORIGIN')
                modules.append({'module': name, **indexed[relative]})
    except BaseException as error:
        failures.append({'phase': 'probe', 'type': type(error).__name__, 'message': str(error),
                         'traceback': traceback.format_exc(limit=12)})
    finally:
        # No pending terminal signal may turn a published success into failure.
        blocked = {signal.SIGINT, signal.SIGTERM, signal.SIGALRM, signal.SIGXCPU}
        signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            if runtime is not None:
                runtime.close()
                runtime_closed = True
                zero_after = snapshot(ATTEMPT / 'state')
                require(zero_after == zero_before, 'READ_CHANGED_WORK_STATE')
        except BaseException as error:
            failures.append({'phase': 'close-or-zero-effect', 'type': type(error).__name__, 'message': str(error)})
        process = None
        try:
            process = no_children_or_threads()
            after = verify_inputs()
            require(before == after, 'PUBLIC_INPUTS_CHANGED')
            save('public-inputs-after.json', after)
        except BaseException as error:
            failures.append({'phase': 'final-pins', 'type': type(error).__name__, 'message': str(error)})
        pending = sorted(int(s) for s in signal.sigpending() if s in blocked)
        elapsed = time.monotonic_ns() - started
        require(not BLOCKED_ATTEMPTS or failures, 'UNREPORTED_FORBIDDEN_EVENT')
        result = {'schema': 'hms-runtime-read-probe/1', 'passed': not failures and not pending and
                  not BLOCKED_ATTEMPTS and runtime_closed and elapsed <= LIMITS['wallSeconds'] * 10**9,
                  'failures': failures, 'pendingSignals': pending, 'limits': LIMITS,
                  'elapsedMonotonicNs': elapsed, 'pid': os.getpid(), 'parentPid': os.getppid(),
                  'pythonVersion': sys.version, 'sqliteVersion': sqlite3.sqlite_version, 'process': process,
                  'cpuUserSeconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime,
                  'cpuSystemSeconds': resource.getrusage(resource.RUSAGE_SELF).ru_stime,
                  'runtimeClosed': runtime_closed, 'public244Stable': before is not None and before == after,
                  'importedPublicModules': modules, 'readMethods': [r['method'] for r in replies],
                  'zeroEffectBefore': zero_before, 'zeroEffectAfter': zero_after,
                  'deniedExternalEvents': BLOCKED_ATTEMPTS,
                  'scope': {'profile': 'legacy-sqlite-simulation', 'realRuntimeReads': True,
                            'modelInvocation': False, 'harnessSession': False, 'qualification': False,
                            'physicalDevice': False, 'actuation': False, 'runtimeWorkersStarted': False,
                            'stdlibAndJsonschemaClosurePinned': False},
                  'outputsBeforeResult': inventory()}
        save('RESULTS.json', result)
        # This standalone process exits with INT/TERM/ALRM/XCPU still blocked;
        # it does not restore a caller's process-global disposition/mask.
        print(json.dumps({'passed': result['passed'], 'attempt': str(ATTEMPT),
                          'readCalls': len(replies), 'public244Stable': result['public244Stable']}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
