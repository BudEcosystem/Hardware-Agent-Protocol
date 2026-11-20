"""Fixed two-process evaluation, preserving both success and failure outputs."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
OUT = BASE / 'attempt01'
OUT.mkdir(mode=0o700, exist_ok=False)
inputs = json.loads((BASE / 'inputs.json').read_bytes())
def verify():
    for row in inputs['files']:
        path = BASE / row['path']
        assert path.stat().st_size == row['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
verify()
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_FSIZE, (16777216, 16777216))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
rows = []
deadline = time.monotonic() + 60
for kind in ('production', 'instrumented'):
    argv = [sys.executable, '-I', '-S', '-B', str(BASE / 'check.py'), kind, str(OUT / kind)]
    result = subprocess.run(argv, cwd=BASE, env=environment, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=min(25, max(.001, deadline-time.monotonic())))
    assert len(result.stdout) + len(result.stderr) <= 1048576
    for channel in ('stdout', 'stderr'):
        with (OUT / (kind + '.' + channel)).open('xb') as stream:
            stream.write(getattr(result, channel))
    rows.append(dict(kind=kind, argv=argv, exitCode=result.returncode))
verify()
with (OUT / 'result.json').open('x') as stream:
    json.dump(dict(status='passed' if all(row['exitCode'] == 0 for row in rows) else 'failed',
                   processes=rows, inputsUnchanged=True, environment=environment,
                   timeoutSeconds=60, perChildTimeoutSeconds=25), stream, indent=2)
    stream.write('\n')
print(json.dumps(rows))
raise SystemExit(0 if all(row['exitCode'] == 0 for row in rows) else 1)
