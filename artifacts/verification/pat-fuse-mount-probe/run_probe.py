"""One original mount attempt, retained outputs and owned-process cleanup."""
from pathlib import Path
import hashlib
import json
import os
import platform
import resource
import signal
import stat
import subprocess
import sys
import time
import traceback

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[2]
RESEARCH = ROOT / 'research/host-contract/fuse-storage-boundary'
ATTEMPT = STAGE / 'attempt01'
MOUNT = ATTEMPT / 'mount'
LIBRARY = Path('/usr/lib/x86_64-linux-gnu/libfuse3.so.3.14.0')
HELPER = Path('/usr/bin/fusermount3')
RECEIPT = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def save(name, value):
    with (ATTEMPT / name).open('x') as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.write('\n')


def mount_entry():
    matches = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        if fields[4] == str(MOUNT):
            split = fields.index('-')
            matches.append({'id': int(fields[0]), 'target': fields[4],
                            'options': fields[5].split(','),
                            'type': fields[split + 1], 'source': fields[split + 2],
                            'raw': line})
    if len(matches) > 1:
        raise RuntimeError('multiple mounts at probe path')
    return matches[0] if matches else None


def owned(entry):
    return (entry and entry['type'] == 'fuse.hmsprobe' and
            entry['source'] == 'hms-probe-81')


def command(name, argv, timeout):
    with (ATTEMPT / (name + '.stdout')).open('xb') as out, \
            (ATTEMPT / (name + '.stderr')).open('xb') as err:
        process = subprocess.Popen(argv, stdout=out, stderr=err, env=ENV)
        try:
            return_code = process.wait(timeout=timeout)
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            raise
    return {'argv': [str(x) for x in argv], 'returncode': return_code}


resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
os.umask(0o077)
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
       'PYTHONDONTWRITEBYTECODE': '1'}
ATTEMPT.mkdir(mode=0o700)
MOUNT.mkdir(mode=0o700)
assert stat.S_IMODE(ATTEMPT.stat().st_mode) == 0o700
assert MOUNT.stat().st_uid == os.getuid() and not list(MOUNT.iterdir())
assert mount_entry() is None

baseline = json.loads(RECEIPT.read_text())
assert digest(RECEIPT) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
assert baseline['passed'] and baseline['tests'] == 866
assert len(baseline['files_after']) == 244
for item in baseline['files_after']:
    assert digest(ROOT / item['path']) == item['sha256'], item['path']

inputs = sorted([STAGE / p for p in ['PLAN.md', 'probe.c', 'client.py',
                'libfuse_config.h', 'run_probe.py']] +
                list((RESEARCH / 'include').glob('*.h')) +
                [RESEARCH / 'sources.json', LIBRARY, HELPER,
                 Path('/usr/bin/cc').resolve(), RECEIPT])
before = [{'path': str(p), 'sha256': digest(p), 'bytes': p.stat().st_size}
          for p in inputs]
save('inputs-before.json', before)
save('host.json', {'uname': list(platform.uname()), 'uid': os.getuid(),
                  'gid': os.getgid(), 'helperMode': oct(HELPER.stat().st_mode),
                  'procStatus': [line for line in Path('/proc/self/status').read_text().splitlines()
                                 if line.startswith(('Cap', 'NoNewPrivs:', 'Seccomp'))]})

started = time.monotonic()
server = None
client = None
mount_identity = None
result = {'status': 'failed', 'totalDiskQuotaEnforced': False,
          'backedControlCapacity': False, 'durableStorage': False,
          'productionChanged': False, 'checks': [], 'cleanupErrors': []}
try:
    compiled = command('compile', ['/usr/bin/cc', '-std=c11', '-D_DEFAULT_SOURCE',
        '-D_FILE_OFFSET_BITS=64', '-Wall', '-Wextra', '-Werror', '-O2',
        '-I', str(RESEARCH / 'include'), '-I', str(STAGE), str(STAGE / 'probe.c'),
        str(LIBRARY), '-o', str(ATTEMPT / 'probe')], 20)
    save('compile.json', compiled)
    assert compiled['returncode'] == 0, 'compile failed'
    result['binarySha256'] = digest(ATTEMPT / 'probe')
    with (ATTEMPT / 'server.stdout').open('xb') as out, \
            (ATTEMPT / 'server.stderr').open('xb') as err:
        server = subprocess.Popen([str(ATTEMPT / 'probe'), str(MOUNT)],
                                  stdout=out, stderr=err, env=ENV)
    result['serverPid'] = server.pid
    until = time.monotonic() + 5
    while time.monotonic() < until:
        entry = mount_entry()
        if entry is not None:
            assert owned(entry), 'unexpected mount identity'
            mount_identity = entry
            break
        assert server.poll() is None, 'server exited before mount'
        time.sleep(0.02)
    assert mount_identity, 'mount startup timed out'
    save('mounted.json', mount_identity)
    assert {'ro', 'nosuid', 'nodev', 'noexec'} <= set(mount_identity['options'])
    result['checks'].append('owned-readonly-mount-options')
    maps = Path(f'/proc/{server.pid}/maps').read_text()
    save('loaded-library.json', {'library': str(LIBRARY), 'sha256': digest(LIBRARY),
                                'mapped': str(LIBRARY) in maps})
    assert str(LIBRARY) in maps
    with (ATTEMPT / 'client.stdout').open('xb') as out, \
            (ATTEMPT / 'client.stderr').open('xb') as err:
        client = subprocess.Popen([sys.executable, '-B', str(STAGE / 'client.py'), str(MOUNT)],
                                  stdout=out, stderr=err, env=ENV)
    result['clientPid'] = client.pid
    assert client.wait(timeout=5) == 0, 'client failed'
    checks = json.loads((ATTEMPT / 'client.stdout').read_text())
    assert checks['status'] == 'passed' and len(checks['checks']) == 11
    result['checks'].extend(checks['checks'])
    assert mount_entry() == mount_identity, 'mount changed'
    unmounted = command('unmount', [str(HELPER), '-u', str(MOUNT)], 3)
    save('unmount.json', unmounted)
    assert unmounted['returncode'] == 0, 'ordinary unmount failed'
    assert server.wait(timeout=3) == 0, 'server exit failed'
    assert mount_entry() is None
    result['checks'].append('ordinary-unmount-and-server-reap')
    assert not list(MOUNT.iterdir())
    result['checks'].append('underlying-directory-empty')
    result['status'] = 'passed'
except BaseException:
    result['error'] = traceback.format_exc()
finally:
    # Only these child objects are signaled; never discover/kill unrelated PIDs.
    for process in [server, client]:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    result['cleanupErrors'].append('owned child could not be reaped')
    try:
        entry = mount_entry()
        if owned(entry) and (mount_identity is None or entry['id'] == mount_identity['id']):
            cleanup = command('cleanup-unmount', [str(HELPER), '-u', str(MOUNT)], 3)
            save('cleanup-unmount.json', cleanup)
        result['mountAfter'] = mount_entry()
        if result['mountAfter'] is not None:
            result['cleanupErrors'].append('mount remains at probe path')
    except BaseException:
        result['cleanupErrors'].append(traceback.format_exc())
    result['serverReturncode'] = server.returncode if server else None
    result['clientReturncode'] = client.returncode if client else None
    result['elapsedSeconds'] = time.monotonic() - started
    after = [{'path': str(p), 'sha256': digest(p), 'bytes': p.stat().st_size}
             for p in inputs]
    save('inputs-after.json', after)
    result['inputsStable'] = before == after
    result['publicInputsUnchanged'] = all(
        digest(ROOT / item['path']) == item['sha256'] for item in baseline['files_after'])
    if result['cleanupErrors'] or not result['inputsStable'] or not result['publicInputsUnchanged']:
        result['status'] = 'failed'
    save('RESULTS.json', result)
print(json.dumps(result, sort_keys=True))
sys.exit(0 if result['status'] == 'passed' else 1)
