"""Retain the setup refusal; use fresh protected scratch with unchanged limits."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())

def dump(path, value):
    write(path, json.dumps(value, indent=2) + '\n')

failed = BASE / 'harness01/attempts/attempt01'
result = json.loads((failed / 'result.json').read_bytes())
assert result['status'] == 'failed' and result['childState'] == 'exited'
assert result['counts']['testsRun'] == result['counts']['errors'] == 10
assert result['scratchBytes'] == 0 and json.loads((failed / 'sqlite-connections.json').read_bytes()) == []
log = (failed / 'output.log').read_text()
assert log.count('hms.journal.JournalError: UNSAFE_STATE_ANCESTOR') == 10
assert not (BASE / 'harness02/attempts').exists()
for old_name, new_name in [('harness01', 'harness03'), ('harness02', 'harness04')]:
    old, new = BASE / old_name, BASE / new_name
    new.mkdir()
    for row in json.loads((old / 'index.json').read_bytes())['files']:
        path = old / row['path']; raw = path.read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        if row['path'] in ('run_attempt.py', 'README.md', 'SCOPE.md'): continue
        write(new / row['path'], raw)
    original = (old / 'run_attempt.py').read_text()
    parent = original.replace('import time\n', 'import time\nimport tempfile\n')
    before = "scratch = attempt / 'scratch'\nscratch.mkdir(mode=0o700)\n"
    after = """def directory_identity(path):
    info = path.lstat()
    assert stat.S_ISDIR(info.st_mode)
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
scratch_parent = Path('/tmp')
parent_identity = directory_identity(scratch_parent)
assert parent_identity[2] in (0, os.getuid()) and (not parent_identity[3] & 0o022 or parent_identity[3] & stat.S_ISVTX)
scratch = Path(tempfile.mkdtemp(prefix='hms-vault-authority-', dir=str(scratch_parent)))
scratch_identity = directory_identity(scratch)
assert scratch_identity[2:] == (os.getuid(), 0o700)
write(attempt / 'raw-scratch-before.json', dict(path=str(scratch), identity=scratch_identity, parentIdentity=parent_identity))
"""
    assert before in parent
    parent = parent.replace(before, after)
    before = "write(attempt / 'scratch-index.json', dict(files=files, bytes=total, retained=True))\n"
    after = """assert directory_identity(scratch) == scratch_identity and directory_identity(scratch_parent) == parent_identity
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
"""
    assert before in parent
    parent = parent.replace(before, after).replace("    scratchRetained=True, scratchBytes=total, scratchEntries=len(files),",
        "    scratchRetained=True, scratchBytes=total, scratchEntries=len(files), rawScratch=str(scratch), originalScratchRetained=True,")
    ast.parse(parent)
    write(new / 'run_attempt.py', parent)
    write(new / 'references/workspace-scratch-run_attempt.py', original)
    write(new / 'private-scratch.patch', ''.join(difflib.unified_diff(original.splitlines(True), parent.splitlines(True), fromfile=old_name, tofile=new_name)))
    dump(new / 'correction.json', dict(precedingHarness=old_name, productionUnchanged=True,
        correction='Fresh protected /tmp scratch; exact retained copies and original raw state after terminal child',
        failedSetup='UNSAFE_STATE_ANCESTOR', previousSqliteConnections=0,
        boundsUnchanged=True, fixtureReset=False, originalFailedScopeRetained=True))
    write(new / 'README.md', '# Private-scratch authority publication controls\n\n'
        '[Targets](targets.json), [scope](SCOPE.md), [correction](correction.json), [source](../implementation01/README.md).\n')
    write(new / 'SCOPE.md', (old / 'SCOPE.md').read_text() + '\nRuntime state is now created in a new owned 0700 directory under trusted sticky `/tmp`. The raw state and exact byte copies remain after the terminal child. No shared ancestor permission changes or state resets occur.\n')
    files = []
    for path in sorted(new.rglob('*')):
        if path.is_file():
            raw = path.read_bytes(); files.append(dict(path=path.relative_to(new).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    dump(new / 'index.json', dict(scope='Private-scratch correction; source and original bounds unchanged', files=files))
dump(BASE / 'setup-failure-audit.json', dict(status='verified', testsStarted=10, testBodiesEntered=0,
    errors=10, sqliteConnections=0, scratchBytes=0, originalFailureRetained=True,
    unexecutedSupersededScope='harness02', corrections=['harness03', 'harness04']))
print(json.dumps(dict(sourceUnchanged=True, privateScratchScopes=['harness03', 'harness04'], failedSetupRetained=True)))
