"""Run one fresh bounded probe, retain every output and terminal status."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

source = Path(__file__).resolve().parent
base = source.parent
pin_path = source / 'index.json'
pin = json.loads(pin_path.read_bytes())
def verify():
    for row in pin['files']:
        path = source / row['path']
        assert path.stat().st_size == row['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
verify()
os.umask(0o077)
attempt = base / 'attempts/attempt01'
attempt.mkdir(parents=True, exist_ok=False)
scratch = attempt / 'scratch'
scratch.mkdir()
started = time.monotonic()
child = subprocess.Popen([sys.executable, '-I', '-S', str(source / 'probe.py'), str(scratch)],
    cwd=scratch, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TMPDIR': str(scratch),
                      'SQLITE_TMPDIR': str(scratch)}, stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
selector = selectors.DefaultSelector()
for name, pipe in (('stdout', child.stdout), ('stderr', child.stderr)):
    os.set_blocking(pipe.fileno(), False)
    selector.register(pipe, selectors.EVENT_READ, name)
outputs = {'stdout': bytearray(), 'stderr': bytearray()}
errors = []
killed_at = None
while selector.get_map():
    elapsed = time.monotonic() - started
    if elapsed > 30 and killed_at is None:
        errors.append('30 second deadline')
        child.kill()
        killed_at = time.monotonic()
    if killed_at is not None and time.monotonic() - killed_at > 5:
        errors.append('post-kill pipe observation deadline')
        break
    for key, events in selector.select(0.1):
        chunk = os.read(key.fileobj.fileno(), 4096)
        if not chunk:
            selector.unregister(key.fileobj)
            key.fileobj.close()
            continue
        stream = outputs[key.data]
        if len(stream) + len(chunk) > 65536:
            if killed_at is None:
                errors.append(key.data + ' exceeded 64 KiB')
                child.kill()
                killed_at = time.monotonic()
            stream.extend(chunk[:max(0, 65536 - len(stream))])
        else:
            stream.extend(chunk)
selector.close()
try:
    exit_code = child.wait(timeout=max(0.1, 30 - (time.monotonic() - started)))
except subprocess.TimeoutExpired:
    errors.append('terminal observation deadline')
    child.kill()
    exit_code = child.wait(timeout=5)
elapsed = time.monotonic() - started
for name, body in outputs.items():
    with (attempt / (name + '.log')).open('xb') as stream:
        stream.write(body)
report = None
try:
    assert exit_code == 0 and not outputs['stderr']
    report = json.loads(outputs['stdout'])
    assert report['status'] == 'passed' and len(report['cases']) == 5
    assert report['sqliteConnections'] == 6 and report['attachedDatabases'] == 1
except Exception as exc:
    errors.append('child/report: ' + repr(exc))
files = []
for path in sorted(scratch.iterdir()):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size <= 1024 * 1024
    files.append(dict(path=path.name, bytes=path.stat().st_size,
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(files) <= 32 and sum(row['bytes'] for row in files) <= 8 * 1024 * 1024
if report is not None and files != report['files']:
    errors.append('parent/child file inventory disagreement')
verify()
result = dict(status='passed' if not errors else 'failed', errors=errors,
    exitCode=exit_code, childState='exited', elapsedSeconds=elapsed, pid=child.pid,
    sourceIndexSha256=hashlib.sha256(pin_path.read_bytes()).hexdigest(),
    timeoutSeconds=30, maxSingleFileBytes=1024 * 1024, maxScratchBytes=8 * 1024 * 1024,
    maxOutputBytesPerStream=65536, sourcesUnchanged=True, scratchRetained=True, files=files)
with (attempt / 'result.json').open('x') as stream:
    stream.write(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
sys.exit(0 if not errors else 1)
