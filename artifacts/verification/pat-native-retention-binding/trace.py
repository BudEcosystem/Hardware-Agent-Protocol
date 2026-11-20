"""Collect three bounded unmodified-production syscall traces, without injected effects."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

BASE = Path(__file__).resolve().parent
OUT = BASE / 'trace01'
OUT.mkdir(mode=0o700, exist_ok=False)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
prior = json.loads((BASE.parent / 'pat-native-retention-prototype' / 'trace02' / 'started.json').read_bytes())
tracer = Path('/usr/bin/strace').resolve()
assert sha(tracer) == prior['tracerSha256']
for row in json.loads((BASE / 'inputs.json').read_bytes())['files']:
    assert sha(BASE / row['path']) == row['sha256']
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
paths = []
for name in ('ordinary', 'fifo', 'empty'):
    root = BASE / 'attempt01' / 'production' / name
    paths.extend([root, *root.rglob('*')])
def metadata():
    return [dict(path=str(path), **{key: getattr(path.lstat(), key) for key in
            ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
            for path in paths]
before = metadata()
rows = []
for mode in ('ordinary', 'fifo', 'veto'):
    argv = [str(tracer), '--kill-on-exit', '-I', '2', '-s', '512', '-o', str(OUT / (mode + '.trace')),
            sys.executable, '-I', '-S', '-B', str(BASE / 'trace_probe.py'), mode]
    completed = subprocess.run(argv, cwd=BASE, env=environment, stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=10)
    for channel in ('stdout', 'stderr'):
        assert len(getattr(completed, channel)) <= 65536
        with (OUT / (mode + '.' + channel)).open('xb') as stream:
            stream.write(getattr(completed, channel))
    rows.append(dict(mode=mode, argv=argv, exitCode=completed.returncode))
    assert completed.returncode == 0 and completed.stderr == b''
after = metadata()
assert before == after
with (OUT / 'collection.json').open('x') as stream:
    json.dump(dict(status='collected-not-yet-audited', rows=rows, tracerSha256=sha(tracer),
                   probeSha256=sha(BASE / 'trace_probe.py'), scriptSha256=sha(Path(__file__)),
                   environment=environment, metadataBefore=before, metadataAfter=after,
                   binarySha256=json.loads((BASE / 'build01/production/build.json').read_bytes())['binarySha256']),
              stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(scopes=len(rows), fixtureMetadataUnchanged=before == after)))
