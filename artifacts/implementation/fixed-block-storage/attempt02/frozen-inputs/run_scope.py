"""One bounded original control run; never retries a failed attempt."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import time

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[2]
name = sys.argv[1] if len(sys.argv) == 2 else 'attempt01'
if name not in {'attempt01', 'attempt02'}:
    raise ValueError('explicit reviewed attempt required')
ATTEMPT = STAGE / name


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    with (ATTEMPT / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (20,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128,) * 2)


os.umask(0o077)
ATTEMPT.mkdir(mode=0o700)
work = ATTEMPT / 'images'
work.mkdir(mode=0o700)
receipt = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
assert digest(receipt) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
baseline = json.loads(receipt.read_text())
assert baseline['passed'] and baseline['tests'] == 866
for item in baseline['files_after']:
    assert digest(ROOT / item['path']) == item['sha256'], item['path']
inputs = [STAGE / name for name in ['fixed_block.py', 'test_fixed_block.py',
                                    'PLAN.md', 'REVIEW.md', 'run_scope.py']]
before = [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p)} for p in inputs]
save('inputs-before.json', before)
env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
       'PYTHONDONTWRITEBYTECODE': '1', 'HMS_BLOCK_TEST_ROOT': str(work)}
started = time.monotonic()
error = None
with (ATTEMPT / 'stdout.log').open('xb') as out, (ATTEMPT / 'stderr.log').open('xb') as err:
    process = subprocess.Popen([sys.executable, '-B', str(STAGE / 'test_fixed_block.py')],
        stdout=out, stderr=err, env=env, preexec_fn=limits, start_new_session=True)
    save('started.json', {'pid': process.pid, 'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          'wallLimitSeconds': 60, 'cpuLimitSeconds': 20,
                          'perFileLimitBytes': 16 * 1024 * 1024,
                          'scratchLimitBytes': 256 * 1024 * 1024,
                          'scratchEnforcement': 'finite original file inventory, post-run verification; no global quota'})
    try:
        process.wait(timeout=60)
    except BaseException as caught:
        error = repr(caught)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
after = [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p)} for p in inputs]
save('inputs-after.json', after)
files = []
for p in sorted(ATTEMPT.rglob('*')):
    if p.is_file():
        info = p.stat()
        files.append({'path': str(p.relative_to(ATTEMPT)), 'bytes': info.st_size,
                      'allocatedBytes': info.st_blocks * 512, 'sha256': digest(p)})
runtime_stable = all(digest(ROOT / item['path']) == item['sha256'] for item in baseline['files_after'])
summary = None
try:
    summary = json.loads((ATTEMPT / 'stdout.log').read_text())
except (ValueError, OSError):
    pass
passed = (process.returncode == 0 and error is None and before == after and runtime_stable
          and summary == {'tests': 24, 'failures': 0, 'errors': 0, 'passed': True}
          and sum(x['allocatedBytes'] for x in files) < 256 * 1024 * 1024
          and all(x['bytes'] <= 16 * 1024 * 1024 for x in files))
report = {'status': 'passed' if passed else 'failed', 'returncode': process.returncode,
          'error': error, 'elapsedSeconds': time.monotonic() - started, 'tests': summary,
          'inputsStable': before == after, 'publicInputsUnchanged': runtime_stable,
          'publicInputCount': len(baseline['files_after']), 'files': files,
          'physicalPowerLossTested': False, 'filesystemIntegrated': False,
          'serviceStorageEnforced': False, 'backedControlCapacity': False,
          'productionChanged': False, 'acquiredCodeExecuted': False}
save('RESULTS.json', report)
print(json.dumps({k: v for k, v in report.items() if k != 'files'}, sort_keys=True))
sys.exit(0 if passed else 1)
