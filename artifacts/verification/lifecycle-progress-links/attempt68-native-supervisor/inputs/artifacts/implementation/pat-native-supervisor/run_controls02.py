"""Six fresh loader controls; fixed original-code scope and retained outputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
OUT = BASE / 'controls02'
OUT.mkdir(mode=0o700, exist_ok=False)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
inputs = [BASE / 'control_child02.py', BASE / 'run_controls02.py']
inputs += [BASE / 'implementation02/project/supervisor' / name for name in
           ('retention_native.py', 'retention_scan.so', 'retention_scanmodule.c', 'attempt_ledger.py', 'supervisor_contracts.py')]
before = [dict(path=str(path.relative_to(BASE)), sha256=sha(path), bytes=path.stat().st_size) for path in inputs]
with (OUT / 'inputs.json').open('x') as stream:
    json.dump(before, stream, indent=2);stream.write('\n')
rows = []
deadline = time.monotonic() + 60
environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
for mode in ('normal', 'replace-after-verify', 'bad-digest', 'veto-load', 'veto-image', 'load-failure'):
    argv = [sys.executable, '-I', '-S', '-B', str(BASE / 'control_child02.py'), mode, str(OUT / mode)]
    completed = subprocess.run(argv, cwd=BASE, env=environment, stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=min(10, max(.001, deadline-time.monotonic())))
    assert len(completed.stdout) + len(completed.stderr) <= 65536
    for channel in ('stdout', 'stderr'):
        with (OUT / (mode + '.' + channel)).open('xb') as stream:
            stream.write(getattr(completed, channel))
    rows.append(dict(mode=mode, argv=argv, exitCode=completed.returncode))
assert before == [dict(path=str(path.relative_to(BASE)), sha256=sha(path), bytes=path.stat().st_size) for path in inputs]
with (OUT / 'result.json').open('x') as stream:
    json.dump(dict(status='passed' if all(row['exitCode'] == 0 for row in rows) else 'failed',
                   processes=rows, inputsUnchanged=True, environment=environment,
                   maxSeconds=60, maxChildSeconds=10), stream, indent=2);stream.write('\n')
print(json.dumps(rows))
raise SystemExit(0 if all(row['exitCode'] == 0 for row in rows) else 1)
