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

ROOT = Path(__file__).resolve().parents[4]
HARNESS = Path(__file__).resolve().parent
BASE = HARNESS.parent
SOURCE = BASE / 'implementation01'
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
scratch = attempt / 'scratch'
scratch.mkdir(mode=0o700)
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
assert len(inputs) == 280
original = ROOT / 'artifacts/implementation/pat-io-definition-build/harness02/attempts/attempt01-actual/scratch/test_actual_original_matrix_catalog_execution_and_historical_replay/runtime/authority.db'
assert original.stat().st_size == 16199680 and sha(original) == 'f106c3312d0c05b69be52b5fae65edd19892b9c019bd62d6691ec3555cc93099'
fixture = attempt / 'original-authority.db'
with fixture.open('xb') as stream:
    stream.write(original.read_bytes())
fixture.chmod(0o400)
assert sha(fixture) == sha(original)
child_path = attempt / 'attempt_child.py'
with child_path.open('xb') as stream:
    stream.write((HARNESS / 'attempt_child.py').read_bytes())
targets = read(HARNESS / 'targets.json')
assert len(targets) == len(set(targets)) == 22
config = dict(project=str(project), attempt=str(attempt), scratch=str(scratch),
    originalDatabase=str(fixture), externalRoots=external['roots'], expectedExternalInputs=external['files'],
    expectedInputs=inputs, childSha256=sha(child_path), targets=targets)
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
    assert sha(fixture) == sha(original) == 'f106c3312d0c05b69be52b5fae65edd19892b9c019bd62d6691ec3555cc93099'
except BaseException as exc:
    errors.append('final inputs: ' + repr(exc))
counts = origins = actual = None
try:
    counts = read(attempt / 'test-return.json')
    origins = read(attempt / 'imports.json')
    actual = read(attempt / 'actual-tests.json')
    assert counts['testsRun'] == 22 and all(counts[key] == 0 for key in counts if key != 'testsRun')
    assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
    assert origins['summary']['allOriginsMatched'] and read(attempt / 'child-errors.json') == []
    assert read(attempt / 'compiler-before.json') == read(attempt / 'compiler-after.json')
    assert read(attempt / 'driver-before.json') == read(attempt / 'driver-after.json')
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
write(attempt / 'scratch-index.json', dict(files=files, bytes=total, retained=True))
result = dict(status='passed' if not errors else 'failed', errors=errors, counts=counts,
    childState='exited', exitCode=exit_code, pid=child.pid, elapsedSeconds=elapsed,
    sourceIndexSha256=sha(SOURCE / 'index.json'), harnessIndexSha256=sha(HARNESS / 'index.json'),
    sourceInputs=280, inputAndExternalVerificationPassed=not any(item.startswith('final inputs') for item in errors),
    timeoutSeconds=180, maxSingleFileBytes=MAX_FILE, maxTotalScratchBytes=MAX_TOTAL,
    scratchRetained=True, scratchBytes=total, scratchEntries=len(files),
    noWorkerLaunched=True, noPhysicalEffects=True, totalDiskQuotaEnforced=False,
    originalDataFileUnchanged=sha(fixture) == sha(original),
    origins=None if origins is None else origins['summary'])
write(attempt / 'result.json', result)
print(json.dumps(result))
raise SystemExit(0 if not errors else 1)
