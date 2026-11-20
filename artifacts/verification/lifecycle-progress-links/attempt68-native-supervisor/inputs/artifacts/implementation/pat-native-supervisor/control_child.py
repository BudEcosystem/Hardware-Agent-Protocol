"""Owned-fixture controls for the exact loader, with no project-package imports."""
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import resource
import sys
import traceback
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
MODE, FOLDER = sys.argv[1:]
OUT = Path(FOLDER)
OUT.mkdir(mode=0o700, exist_ok=False)
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_FSIZE, (16777216, 16777216))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
source = BASE / 'implementation01/project/supervisor'
for name in ('retention_native.py', 'retention_native.so'):
    (OUT / name).write_bytes((source / name).read_bytes())
spec = importlib.util.spec_from_file_location('retention_native', OUT / 'retention_native.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fixture = OUT / 'fixture'
fixture.mkdir(mode=0o700)
(fixture / 'nested').mkdir(mode=0o700)
(fixture / 'a').write_bytes(b'123')
(fixture / 'nested/b').write_bytes(b'4')
for path in (fixture / 'a', fixture / 'nested/b'):
    path.chmod(0o600)
def fds():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            result[name] = os.readlink('/proc/self/fd/' + name)
        except FileNotFoundError:
            pass
    return result
before = fds()
events = []
class Veto(BaseException):
    pass
def audit(event, args):
    if event.startswith('hms.retention.'):
        events.append(dict(event=event, args=[os.fsdecode(v) if type(v) is bytes else v for v in args]))
        if (MODE == 'veto-load' and event == 'hms.retention.load.v1') or (MODE == 'veto-image' and event == 'hms.retention.image.v1'):
            raise Veto(event)
    if event.startswith('socket.') or event in ('subprocess.Popen', 'sqlite3.connect', 'os.system', 'os.exec', 'os.fork'):
        raise AssertionError('unexpected operation: ' + event)
sys.addaudithook(audit)
checks = []
error = None
try:
    if MODE == 'normal':
        invalid = [(True, 0), (0, 1.5), (-1, 0), (262145, 0), (0, 268435457)]
        for files, byte_limit in invalid:
            try:
                module.scan_usage(fixture, max_files=files, max_bytes=byte_limit)
            except (ValueError, TypeError):
                pass
            else:
                raise AssertionError('invalid limit accepted')
        class PathTrap:
            def __fspath__(self):
                raise AssertionError('path hook ran')
        for bad in (PathTrap(), b'', b'x\0y', b'x' * 4096):
            try:
                module.scan_usage(bad, max_files=1, max_bytes=1)
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError('invalid path accepted')
        assert events == [] and not module._ATTEMPTED and fds() == before
        checks.append('nine-invalid-inputs-before-load')
        for path in (fixture, str(fixture), os.fsencode(fixture), PurePosixPath(fixture)):
            assert module.scan_usage(path, max_files=3, max_bytes=4) == dict(files=3, logicalBytes=4, totalDiskQuotaEnforced=False)
        checks.append('four-path-types-exact-counts')
        fd = module._IMAGE_FD
        info = os.fstat(fd)
        assert module._NATIVE.__spec__.origin == '/proc/self/fd/' + str(fd)
        assert sys.modules[module.MODULE_NAME] is module._NATIVE and not os.get_inheritable(fd)
        assert len(fds()) == len(before) + 1 and info.st_nlink == 0
        sealed_before = os.pread(fd, 65537, 0)
        assert hashlib.sha256(sealed_before).hexdigest() == module.BINARY_SHA256
        for operation in (lambda: os.pwrite(fd, b'X', 0), lambda: os.ftruncate(fd, 0),
                          lambda: os.ftruncate(fd, info.st_size + 1),
                          lambda: fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE)):
            try:
                operation()
            except OSError as caught:
                assert caught.errno == errno.EPERM
            else:
                raise AssertionError('sealed image modified')
        assert os.pread(fd, 65537, 0) == sealed_before
        checks.append('kernel-refuses-write-shrink-grow-reseal')
        duplicate = os.open(module._IMAGE_RECORD['origin'], os.O_RDWR | os.O_CLOEXEC)
        try:
            assert fcntl.fcntl(duplicate, fcntl.F_GET_SEALS) == module._IMAGE_RECORD['seals']
            try:
                os.pwrite(duplicate, b'X', 0)
            except PermissionError:
                pass
            else:
                raise AssertionError('duplicate descriptor bypassed seals')
        finally:
            os.close(duplicate)
        checks.append('seals-apply-through-second-descriptor')
        for _ in range(30):
            module.scan_usage(fixture, max_files=3, max_bytes=4)
        assert len(fds()) == len(before) + 1
        assert sum(v['event'] == 'hms.retention.load.v1' for v in events) == 1
        assert sum(v['event'] == 'hms.retention.image.v1' for v in events) == 1
        checks.append('single-image-thirty-reuses')
        for path, files, byte_limit, reason in [(fixture, 2, 4, 'QUALIFICATION_RETENTION_UNKNOWN'),
                (fixture, 3, 3, 'QUALIFICATION_RETENTION_UNKNOWN')]:
            try:
                module.scan_usage(path, max_files=files, max_bytes=byte_limit)
            except module.NativeRetentionError as caught:
                assert caught.code == reason
            else:
                raise AssertionError('limit not enforced')
        checks.append('limit-error-mapping')
        fixture.chmod(0o755)
        try:
            module.scan_usage(fixture, max_files=3, max_bytes=4)
        except module.NativeRetentionError as caught:
            assert caught.code == 'QUALIFICATION_UNSAFE_FILE'
        else:
            raise AssertionError('unsafe root accepted')
        checks.append('unsafe-error-mapping')
        missing = OUT / 'missing'
        try:
            module.scan_usage(missing, max_files=3, max_bytes=4)
        except FileNotFoundError as caught:
            assert caught.errno == errno.ENOENT and caught.filename == str(missing)
        else:
            raise AssertionError('missing root accepted')
        checks.append('os-error-root-filename')
    elif MODE == 'replace-after-verify':
        original = module._read_binary
        def replaced():
            body = original()
            replacement = OUT / 'replacement'
            replacement.write_bytes(b'not a dynamic library')
            os.replace(replacement, module.BINARY)
            return body
        with patch.object(module, '_read_binary', replaced):
            assert module.scan_usage(fixture, max_files=3, max_bytes=4)['files'] == 3
        assert module.BINARY.read_bytes() == b'not a dynamic library'
        assert hashlib.sha256(os.pread(module._IMAGE_FD, 65537, 0)).hexdigest() == module.BINARY_SHA256
        checks.append('verified-bytes-loaded-despite-disk-replacement')
    else:
        if MODE == 'bad-digest':
            body = bytearray(module.BINARY.read_bytes());body[-1] ^= 1;module.BINARY.write_bytes(body)
        if MODE == 'load-failure':
            context = patch.object(module.importlib.machinery.ExtensionFileLoader, 'create_module',
                                   side_effect=ImportError('injected loader failure'))
        else:
            from contextlib import nullcontext
            context = nullcontext()
        try:
            with context:
                module.scan_usage(fixture, max_files=3, max_bytes=4)
        except (Veto, ImportError, module.NativeRetentionError) as caught:
            if MODE == 'bad-digest':
                assert caught.code == 'QUALIFICATION_IMPLEMENTATION_CHANGED'
            elif MODE == 'load-failure':
                assert type(caught) is ImportError
            else:
                assert type(caught) is Veto
        else:
            raise AssertionError('failure was ignored')
        after = fds()
        assert len(after) == len(before) + (1 if MODE == 'load-failure' else 0)
        assert (module._IMAGE_FD is not None) == (MODE == 'load-failure')
        old_events = len(events)
        for _ in range(10):
            try:
                module.scan_usage(fixture, max_files=3, max_bytes=4)
            except module.NativeRetentionError as caught:
                assert caught.code == 'QUALIFICATION_NATIVE_UNAVAILABLE'
            else:
                raise AssertionError('failed loader retried')
        assert fds() == after and len(events) == old_events
        checks.append(MODE + '-refusal-and-no-retry')
except BaseException as caught:
    error = dict(type=type(caught).__name__, message=str(caught), traceback=traceback.format_exc())
result = dict(status='passed' if error is None else 'failed', mode=MODE, checks=checks, error=error,
              events=events, image=module._IMAGE_RECORD, projectCodeChanged=False,
              originalWorkerStateTouched=False, physicalEffects=False)
with (OUT / 'result.json').open('x') as stream:
    json.dump(result, stream, indent=2);stream.write('\n')
print(json.dumps(dict(status=result['status'], mode=MODE, checks=len(checks), error=error)))
raise SystemExit(1 if error else 0)
