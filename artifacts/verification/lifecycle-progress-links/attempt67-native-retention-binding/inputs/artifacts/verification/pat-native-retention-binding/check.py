"""Bounded original-code checks. Each mode runs in its own fresh interpreter."""
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import threading
import time
import traceback

BASE = Path(__file__).resolve().parent
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
kind, output = sys.argv[1:]
assert kind in ('production', 'instrumented')
OUT = Path(output)
OUT.mkdir(mode=0o700, exist_ok=False)
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
resource.setrlimit(resource.RLIMIT_FSIZE, (16777216, 16777216))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
sys.path.insert(0, str(BASE))
from loader import load
from reference import tree_usage, SupervisorError
native = load(kind)
assert hasattr(native, 'configure') == (kind == 'instrumented')
rows = []
events = []
veto = False

class Veto(Exception):
    pass

def audit(event, args):
    if event == 'hms.retention.scan.v1':
        assert len(args) == 3 and type(args[0]) is bytes
        assert type(args[1]) is int and type(args[2]) is int
        events.append([os.fsdecode(args[0]), args[1], args[2]])
        if veto:
            raise Veto('explicit pre-open veto')
    if event.startswith('socket.') or event in ('sqlite3.connect', 'subprocess.Popen', 'os.system', 'os.exec', 'os.fork'):
        raise AssertionError('unplanned operation: ' + event)

sys.addaudithook(audit)

def directory(name):
    path = OUT / name
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path

def file(path, size=8):
    with path.open('xb') as stream:
        stream.write(b'x' * size)
    path.chmod(0o600)

def fds():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            target = os.readlink('/proc/self/fd/' + name)
            if target != '/proc/' + str(os.getpid()) + '/fd':
                result[name] = target
        except FileNotFoundError:
            pass
    return result

def call(path, files=8192, bytes_=67108864):
    before = fds()
    result = native.scan(os.fsencode(path), files, bytes_)
    assert fds() == before, ('descriptor leak', before, fds())
    return result

def reference(path, files, bytes_):
    try:
        result = tree_usage(path, max_files=files, max_bytes=bytes_)
        return dict(reason='OK', errno=0, files=result['files'], logicalBytes=result['logicalBytes'])
    except (SupervisorError, OSError) as error:
        return dict(reason=error.code if isinstance(error, SupervisorError) else 'OS_ERROR',
                    errno=error.errno if isinstance(error, OSError) else 0)

def check(name, path, files=8192, bytes_=67108864):
    expected = reference(path, files, bytes_)
    result = call(path, files, bytes_)
    assert {key: result[key] for key in expected} == expected, (name, expected, result)
    assert result['cleanupErrno'] == 0
    rows.append(dict(name=name, result=result, expected=expected))

def assert_exception(name, args, cls):
    before = fds()
    count = len(events)
    try:
        native.scan(*args)
    except cls as error:
        rows.append(dict(name=name, exception=type(error).__name__))
    else:
        raise AssertionError(name)
    assert fds() == before and len(events) == count

error = None
try:
    empty = directory('empty')
    ordinary = directory('ordinary')
    file(ordinary / 'first', 8)
    file(ordinary / '.hidden', 3)
    (ordinary / 'nested').mkdir(mode=0o700)
    file(ordinary / 'nested' / 'third', 5)
    single = directory('single')
    file(single / 'entry')
    if kind == 'production':
        strange = directory('byte-name')
        fd = os.open(os.fsencode(strange) + b'/name-\xff', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        root_link = OUT / 'root-link'
        root_link.symlink_to(ordinary, target_is_directory=True)
        symlink = directory('symlink')
        (symlink / 'entry').symlink_to(ordinary / 'first')
        dirlink = directory('dirlink')
        (dirlink / 'entry').symlink_to(ordinary / 'nested', target_is_directory=True)
        hardlink = directory('hardlink')
        file(hardlink / 'first')
        os.link(hardlink / 'first', hardlink / 'second')
        bad_file = directory('file-mode')
        file(bad_file / 'entry')
        (bad_file / 'entry').chmod(0o644)
        sticky_file = directory('file-sticky')
        file(sticky_file / 'entry')
        (sticky_file / 'entry').chmod(0o1600)
        bad_dir = directory('directory-mode')
        (bad_dir / 'entry').mkdir(mode=0o700)
        (bad_dir / 'entry').chmod(0o755)
        sgid_dir = directory('directory-sgid')
        (sgid_dir / 'entry').mkdir(mode=0o700)
        (sgid_dir / 'entry').chmod(0o2700)
        fifo = directory('fifo')
        os.mkfifo(fifo / 'entry', 0o600)
        depth = {}
        for limit in (10, 11):
            depth[limit] = directory('depth' + str(limit))
            current = depth[limit]
            for _ in range(limit):
                current = current / 'next'
                current.mkdir(mode=0o700)
            file(current / 'end', 1)
        for name, path, files, bytes_ in [
            ('empty-zero', empty, 0, 0), ('ordinary', ordinary, 8192, 67108864),
            ('byte-name', strange, 8192, 67108864), ('root-link', root_link, 8192, 67108864),
            ('missing', OUT / 'missing', 8192, 67108864), ('root-file', single / 'entry', 8192, 67108864),
            ('symlink', symlink, 8192, 67108864), ('dirlink', dirlink, 8192, 67108864),
            ('hardlink', hardlink, 8192, 67108864), ('file-mode', bad_file, 8192, 67108864),
            ('file-sticky', sticky_file, 8192, 67108864), ('directory-mode', bad_dir, 8192, 67108864),
            ('directory-sgid', sgid_dir, 8192, 67108864), ('fifo', fifo, 8192, 67108864),
            ('depth10', depth[10], 8192, 67108864), ('depth11', depth[11], 8192, 67108864),
            ('count-zero', single, 0, 67108864), ('count-exact', single, 1, 8),
            ('bytes-below', single, 8192, 7), ('bytes-exact', single, 8192, 8)]:
            check(name, path, files, bytes_)
        bad_root = directory('bad-root')
        bad_root.chmod(0o755)
        assert reference(bad_root, 0, 0)['reason'] == 'OK'
        result = call(bad_root, 0, 0)
        assert result['reason'] == 'QUALIFICATION_UNSAFE_FILE'
        rows.append(dict(name='strengthened-root-mode', result=result))
        class Integer(int):
            pass
        class ByteString(bytes):
            pass
        class Trap:
            def __index__(self):
                raise AssertionError('must not run __index__')
            def __fspath__(self):
                raise AssertionError('must not run __fspath__')
        p = os.fsencode(empty)
        for name, args, cls in [
            ('text-path', (str(empty), 0, 0), TypeError),
            ('pathlike', (Trap(), 0, 0), TypeError),
            ('bytes-subclass', (ByteString(p), 0, 0), TypeError),
            ('empty-path', (b'', 0, 0), ValueError),
            ('nul-path', (p + b'\0x', 0, 0), ValueError),
            ('long-path', (b'x' * 4096, 0, 0), ValueError),
            ('bool-files', (p, True, 0), TypeError),
            ('float-bytes', (p, 0, 1.0), TypeError),
            ('integer-subclass', (p, Integer(0), 0), TypeError),
            ('index-hook', (p, Trap(), 0), TypeError),
            ('negative-limit', (p, -1, 0), OverflowError),
            ('overflow-limit', (p, 1 << 100, 0), OverflowError),
            ('files-cap', (p, 262145, 0), ValueError),
            ('bytes-cap', (p, 0, 268435457), ValueError),
            ('arity', (p, 0), TypeError)]:
            assert_exception(name, args, cls)
        check('exact-profile-ceilings', empty, 262144, 268435456)
        veto = True
        before = fds()
        try:
            native.scan(p, 0, 0)
        except Veto:
            rows.append(dict(name='audit-veto', exception='Veto'))
        else:
            raise AssertionError('audit veto was ignored')
        finally:
            veto = False
        assert fds() == before
        # Real descriptor pressure with repeated failed traversals; no fake syscall here.
        before = fds()
        previous = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (8, previous[1]))
        for _ in range(30):
            result = call(depth[10])
            assert result['reason'] == 'OS_ERROR' and result['errno'] == errno.EMFILE
        resource.setrlimit(resource.RLIMIT_NOFILE, previous)
        assert fds() == before
        check('post-exhaustion-recovery', depth[10])
        rows.append(dict(name='actual-fd-exhaustion-30', result=result, attempts=30))
        many = directory('signals')
        for number in range(1024):
            file(many / str(number), 0)
        baseline = fds()
        observed = []
        class Cancelled(BaseException):
            pass
        def handler(number, frame):
            open_dirs = [target for target in fds().values() if target.startswith(str(many))]
            observed.append(bool(open_dirs))
        signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, .0005, .0005)
        try:
            result = call(many)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        assert result['reason'] == 'OK' and any(observed) and fds() == baseline
        rows.append(dict(name='nonraising-signals', calls=len(observed), signalWhileDirectoryOpen=True))
        observed = []
        def raising(number, frame):
            handler(number, frame)
            if observed[-1]:
                raise Cancelled('cancel inside native scan')
        signal.signal(signal.SIGALRM, raising)
        signal.setitimer(signal.ITIMER_REAL, .0005, .0005)
        try:
            native.scan(os.fsencode(many), 8192, 67108864)
        except Cancelled as caught:
            assert str(caught) == 'cancel inside native scan'
        else:
            raise AssertionError('signal did not interrupt native scan')
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        assert fds() == baseline and any(observed)
        rows.append(dict(name='raising-signal-cleanup', signalWhileDirectoryOpen=True))
        # Observe a second Python thread while the scanner owns a directory.
        start = threading.Event()
        stop = threading.Event()
        overlap = []
        def observer():
            start.wait()
            while not stop.is_set():
                if any(target.startswith(str(many)) for target in fds().values()):
                    overlap.append(True)
                time.sleep(.0001)
        thread = threading.Thread(target=observer)
        thread.start()
        start.set()
        try:
            assert call(many)['reason'] == 'OK'
        finally:
            stop.set()
            thread.join(timeout=2)
        assert not thread.is_alive() and overlap and fds() == baseline
        rows.append(dict(name='gil-release-overlap', observations=len(overlap)))
    else:
        # Separate instrumented DSO. Counters concern original scanner call sites.
        for name, op, nth, number, target, action, expected, cleanup_number in [
            ('root-open', 0, 1, errno.EACCES, ordinary, 0, errno.EACCES, 0),
            ('child-open', 0, 2, errno.EACCES, ordinary, 0, errno.EACCES, 0),
            ('entry-stat', 1, 1, errno.ENOENT, ordinary, 0, errno.ENOENT, 0),
            ('root-fstat', 2, 1, errno.EIO, ordinary, 0, errno.EIO, 0),
            ('child-fstat', 2, 2, errno.EIO, ordinary, 0, errno.EIO, 0),
            ('root-fdopendir', 3, 1, errno.ENOMEM, ordinary, 0, errno.ENOMEM, 0),
            ('child-fdopendir', 3, 2, errno.ENOMEM, ordinary, 0, errno.ENOMEM, 0),
            ('readdir-eio', 4, 1, errno.EIO, ordinary, 0, errno.EIO, 0),
            ('readdir-eintr-refusal', 4, 1, errno.EINTR, ordinary, 0, errno.EINTR, 0),
            ('closedir-eio', 6, 1, errno.EIO, ordinary, 0, errno.EIO, errno.EIO),
            ('closedir-eintr-no-retry', 6, 1, errno.EINTR, empty, 0, errno.EINTR, errno.EINTR),
            ('primary-error-survives-close-eintr', 3, 1, errno.ENOMEM, ordinary, 3, errno.ENOMEM, errno.EINTR)]:
            native.configure(op, nth, number, action)
            result = call(target)
            assert result['reason'] == 'OS_ERROR' and result['errno'] == expected, (name, result)
            assert result['cleanupErrno'] == cleanup_number, (name, result)
            counts = native.counters()
            if name == 'closedir-eintr-no-retry':
                assert counts[6] == 1
            if action == 3:
                assert counts[5] == 1
            rows.append(dict(name=name, result=result, callCounts=counts))
        for op in (0, 1, 2):
            native.configure(op, 1, errno.EINTR, 0)
            result = call(ordinary)
            assert result['reason'] == 'OK' and result['files'] == 4 and result['logicalBytes'] == 16
            rows.append(dict(name='eintr-retry-' + str(op), result=result, callCounts=native.counters()))
        unsafe = directory('unsafe')
        file(unsafe / 'entry')
        (unsafe / 'entry').chmod(0o644)
        native.configure(6, 1, errno.EIO, 0)
        result = call(unsafe)
        assert result['reason'] == 'QUALIFICATION_UNSAFE_FILE' and result['cleanupErrno'] == errno.EIO
        rows.append(dict(name='policy-primary-cleanup-secondary', result=result, callCounts=native.counters()))
        race = directory('race/root')
        (race / 'target').mkdir(mode=0o700)
        (race.parent / 'spare').mkdir(mode=0o700)
        before_target = (race / 'target').stat().st_ino
        before_spare = (race.parent / 'spare').stat().st_ino
        native.configure(0, 2, 0, 1)
        result = call(race)
        assert result['reason'] == 'QUALIFICATION_RETENTION_UNKNOWN' and result['directoryReplaced'] is True
        assert (race / 'target').stat().st_ino == before_spare
        assert (race / 'retired').stat().st_ino == before_target
        rows.append(dict(name='deterministic-directory-replacement', result=result, callCounts=native.counters()))
        disappearing = directory('disappearance')
        file(disappearing / 'entry')
        native.configure(1, 1, 0, 2)
        result = call(disappearing)
        assert result['reason'] == 'OS_ERROR' and result['errno'] == errno.ENOENT
        assert not (disappearing / 'entry').exists()
        rows.append(dict(name='deterministic-entry-disappearance', result=result, callCounts=native.counters()))
        for _ in range(100):
            native.configure(3, 2, errno.ENOMEM, 0)
            assert call(ordinary)['reason'] == 'OS_ERROR'
        rows.append(dict(name='repeated-child-stream-failure-100', attempts=100))
        native.configure(-1, 0, 0, 0)
        veto = True
        try:
            native.scan(os.fsencode(empty), 0, 0)
        except Veto:
            assert native.counters() == [0] * 7
            rows.append(dict(name='veto-before-any-native-io', callCounts=native.counters()))
        else:
            raise AssertionError('audit veto was ignored')
        finally:
            veto = False
except BaseException as caught:
    error = dict(type=type(caught).__name__, message=str(caught), traceback=traceback.format_exc())
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
receipt = dict(status='passed' if error is None else 'failed', kind=kind, checks=rows, error=error,
               auditEvents=events, nativeSyscallsCoveredByPythonAudit=False,
               productionIntegration=False, actualWorkerRun=False, physicalEffects=False)
with (OUT / 'result.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(status=receipt['status'], kind=kind, checks=len(rows), error=error)))
raise SystemExit(1 if error else 0)
