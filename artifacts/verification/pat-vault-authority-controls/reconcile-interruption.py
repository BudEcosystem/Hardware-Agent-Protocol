"""Record missing process/raw state without inventing a result or restoring it."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
OLD = BASE / 'harness03'
NEW = BASE / 'harness12'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path, value): write(path, json.dumps(value, indent=2) + '\n')

attempt = OLD / 'attempts/attempt01'
started = json.loads((attempt / 'started.json').read_bytes())
config = json.loads((attempt / 'child-config.json').read_bytes())
assert not (attempt / 'result.json').exists()
assert not Path('/proc', str(started['pid'])).exists()
assert not Path(config['scratch']).exists()
retained = []
for path in sorted(attempt.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): retained.append(dict(path=path.relative_to(attempt).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
completed = []
for name in ('harness01', 'harness02'):
    folder = BASE / name / 'attempts/attempt01'
    result = json.loads((folder / 'result.json').read_bytes())
    inventory = json.loads((folder / 'scratch-index.json').read_bytes())
    assert result['status'] == 'passed' and result['childState'] == 'exited'
    for row in inventory['files']:
        path = folder / 'scratch' / row['path']
        assert row['kind'] == 'file' and path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    completed.append(dict(scope=name, historicalTerminalStatus=result['status'],
        retainedCopiesMatch=True, originalRawPath=result['rawScratch'], originalRawCurrentlyAvailable=Path(result['rawScratch']).exists()))
dump(BASE / 'interruption-observation.json', dict(status='interrupted-unverified', observationDate='2026-11-08',
    originalScope='harness03', toolSession=81303, toolHandleMissing=True,
    recordedChildPid=started['pid'], processPresent=False, parentAndChildCommandsAbsentFromProcessTable=True,
    terminalReceiptPresent=False, originalRawPath=config['scratch'], originalRawAvailable=False,
    cause='Not established; process and temporary state absence observed after continuation',
    noExitCodeInvented=True, originalScopeNotRestarted=True, rawStateNotReconstructed=True,
    retainedFiles=retained, completedScopes=completed,
    continuation='harness12: same two methods on unchanged production, fresh isolated state and original bounds'))
NEW.mkdir()
for row in json.loads((OLD / 'index.json').read_bytes())['files']:
    source = OLD / row['path']; raw = source.read_bytes()
    assert len(raw) == row['bytes'] and sha(source) == row['sha256']
    if row['path'] in ('README.md', 'SCOPE.md'): continue
    write(NEW / row['path'], raw)
write(NEW / 'README.md', '# Fresh continuation after unavailable process/state\n\n'
    '[Targets](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md). The original harness03 remains interrupted and unverified.\n')
write(NEW / 'SCOPE.md', (OLD / 'SCOPE.md').read_text() + '\nThis fresh scope follows a confirmed missing process and unavailable original temporary state. No original exit status, completed result or raw state is invented. The same targets, production and bounds remain in effect.\n')
files = []
for path in sorted(NEW.rglob('*')):
    if path.is_file(): files.append(dict(path=path.relative_to(NEW).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
dump(NEW / 'index.json', dict(scope='Fresh verification continuation; interrupted scope retained separately', files=files))
print(json.dumps(dict(interruptedScope='harness03', freshScope='harness12', originalRawRestored=False,
    sourceUnchanged=True, boundsUnchanged=True, completedCopiesVerified=True)))
