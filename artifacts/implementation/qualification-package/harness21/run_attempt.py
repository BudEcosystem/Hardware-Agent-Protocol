"""One bounded child, exact frozen inputs, retained failures, no automatic retry."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import sys
import time
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HARNESS = Path(__file__).resolve().parent
BASE = HARNESS.parent
SOURCE = BASE / 'implementation03'
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    assert path.stat().st_size <= MAX_FILE
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    wire = json.dumps(value, indent=2).encode() + b'\n'
    assert len(wire) <= 4 * 1024 * 1024
    with path.open('xb') as stream:
        stream.write(wire)

assert sha(SOURCE / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
source_pin = read(SOURCE / 'index.json')
harness_pin = read(HARNESS / 'index.json')
external = read(HARNESS / 'references/external-inputs.json')
def verify():
    for row in source_pin['files']:
        path = ROOT / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in harness_pin['files']:
        path = HARNESS / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in external['files']:
        path = Path(row['resolvedPath'])
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
verify()
os.umask(0o077)
attempt = HARNESS / 'attempts/attempt01'
attempt.mkdir(parents=True, exist_ok=False)
def directory_identity(path):
    info = path.lstat()
    assert stat.S_ISDIR(info.st_mode)
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
scratch_parent = Path('/tmp')
parent_identity = directory_identity(scratch_parent)
assert parent_identity[2] in (0, os.getuid()) and (not parent_identity[3] & 0o022 or parent_identity[3] & stat.S_ISVTX)
scratch = Path(tempfile.mkdtemp(prefix='hms-vault-catalog-', dir=str(scratch_parent)))
scratch_identity = directory_identity(scratch)
assert scratch_identity[2:] == (os.getuid(), 0o700)
write(attempt / 'raw-scratch-before.json', dict(path=str(scratch), identity=scratch_identity, parentIdentity=parent_identity))
project = attempt / 'project'
project.mkdir(mode=0o700)
inputs = []
for row in source_pin['files']:
    path = ROOT / row['path']
    try:
        relative = path.relative_to(SOURCE / 'project')
    except ValueError:
        continue
    destination = project / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(path.read_bytes())
    inputs.append(dict(path=relative.as_posix(), bytes=row['bytes'], sha256=row['sha256']))
assert len(inputs) == 304
child_path = attempt / 'attempt_child.py'
with child_path.open('xb') as stream:
    stream.write((HARNESS / 'attempt_child.py').read_bytes())
targets = read(HARNESS / 'targets.json')
assert len(targets) == len(set(targets)) == 1
config = dict(project=str(project), attempt=str(attempt), scratch=str(scratch),
    externalRoots=external['roots'], expectedExternalInputs=external['files'],
    expectedInputs=inputs, childSha256=sha(child_path), targets=targets, expectedHost=read(SOURCE / 'identity-pins.json')['host'])
write(attempt / 'child-config.json', config)
write(attempt / 'inputs-before.json', inputs)
environment = dict(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1',
                   TMPDIR=str(scratch), SQLITE_TMPDIR=str(scratch))
command = [sys.executable, '-I', '-S', '-B', str(child_path), str(attempt / 'child-config.json')]
write(attempt / 'command.json', dict(command=command, cwd=str(project), environment=environment,
    timeoutSeconds=180, maxSingleFileBytes=MAX_FILE, maxTotalScratchBytes=MAX_TOTAL,
    maxOutputBytes=4 * 1024 * 1024, sourceIndexSha256=sha(SOURCE / 'index.json'),
    harnessIndexSha256=sha(HARNESS / 'index.json')))
started = time.monotonic()
child = subprocess.Popen(command, cwd=project, env=environment, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
write(attempt / 'started.json', dict(pid=child.pid, state='running'))
os.set_blocking(child.stdout.fileno(), False)
selector = selectors.DefaultSelector()
selector.register(child.stdout, selectors.EVENT_READ)
output = bytearray()
errors = []
killed = None
while selector.get_map():
    now = time.monotonic()
    if now - started > 180 and killed is None:
        errors.append('original 180 second deadline')
        child.kill(); killed = now
    if killed is not None and now - killed > 5:
        errors.append('post-kill output observation deadline')
        break
    for key, events in selector.select(0.2):
        chunk = os.read(key.fileobj.fileno(), 4096)
        if not chunk:
            selector.unregister(key.fileobj); key.fileobj.close()
            continue
        room = 4 * 1024 * 1024 - len(output)
        output.extend(chunk[:room])
        if len(chunk) > room and killed is None:
            errors.append('4 MiB output limit')
            child.kill(); killed = time.monotonic()
selector.close()
try:
    exit_code = child.wait(timeout=max(0.1, 180 - (time.monotonic() - started)))
except subprocess.TimeoutExpired:
    errors.append('terminal observation deadline')
    child.kill(); exit_code = child.wait(timeout=5)
elapsed = time.monotonic() - started
with (attempt / 'output.log').open('xb') as stream:
    stream.write(output)
try:
    verify()
    for row in inputs:
        path = project / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
except BaseException as exc:
    errors.append('final inputs: ' + repr(exc))
counts = origins = actual = None
try:
    counts = read(attempt / 'test-return.json')
    origins = read(attempt / 'imports.json')
    actual = read(attempt / 'actual-tests.json')
    assert counts['testsRun'] == 1 and all(counts[key] == 0 for key in counts if key != 'testsRun')
    assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
    assert origins['summary']['allOriginsMatched'] and read(attempt / 'child-errors.json') == []
    assert read(attempt / 'compiler-before.json') == read(attempt / 'compiler-after.json')
    assert read(attempt / 'driver-before.json') == read(attempt / 'driver-after.json')
    assert read(attempt / 'host-before.json') == read(attempt / 'host-after.json') == {'host': config['expectedHost']}
    assert exit_code == 0
except BaseException as exc:
    errors.append('child receipts: ' + repr(exc))
files = []
total = 0
for path in sorted(scratch.rglob('*')):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(path)
        assert len(target.encode()) <= 4096 and Path(target).is_relative_to(scratch)
        files.append(dict(path=path.relative_to(scratch).as_posix(), kind='retained-negative-symlink', target=target,
                          bytes=info.st_size, sha256=hashlib.sha256(target.encode()).hexdigest()))
    elif stat.S_ISREG(info.st_mode):
        assert info.st_size <= MAX_FILE
        files.append(dict(path=path.relative_to(scratch).as_posix(), kind='file', bytes=info.st_size, sha256=sha(path)))
    else:
        assert stat.S_ISDIR(info.st_mode)
        continue
    total += info.st_size
    assert len(files) <= 8192 and total <= MAX_TOTAL
assert directory_identity(scratch) == scratch_identity and directory_identity(scratch_parent) == parent_identity
retained = attempt / 'scratch'
retained.mkdir(mode=0o700)
for row in files:
    assert row['kind'] == 'file'
    source = scratch / row['path']
    target = retained / row['path']
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(source.read_bytes())
    target.chmod(stat.S_IMODE(source.stat().st_mode))
    assert sha(source) == sha(target) == row['sha256'] and target.stat().st_size == row['bytes']
write(attempt / 'raw-scratch-after.json', dict(path=str(scratch), identity=directory_identity(scratch), parentIdentity=directory_identity(scratch_parent), retainedOriginal=True))
write(attempt / 'scratch-index.json', dict(files=files, bytes=total, retained=True, rawPath=str(scratch), originalRetained=True))
result = dict(status='passed' if not errors else 'failed', errors=errors, counts=counts,
    childState='exited', exitCode=exit_code, pid=child.pid, elapsedSeconds=elapsed,
    sourceIndexSha256=sha(SOURCE / 'index.json'), harnessIndexSha256=sha(HARNESS / 'index.json'),
    sourceInputs=304, inputAndExternalVerificationPassed=not any(item.startswith('final inputs') for item in errors),
    timeoutSeconds=180, maxSingleFileBytes=MAX_FILE, maxTotalScratchBytes=MAX_TOTAL,
    scratchRetained=True, scratchBytes=total, scratchEntries=len(files), rawScratch=str(scratch), originalScratchRetained=True,
    noWorkerLaunched=True, noPhysicalEffects=True, totalDiskQuotaEnforced=False,
    origins=None if origins is None else origins['summary'])
write(attempt / 'result.json', result)
print(json.dumps(result))
raise SystemExit(0 if not errors else 1)
