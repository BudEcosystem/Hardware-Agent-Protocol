"""Preserve a harness refusal; resolve dir_fd opens without changing their semantics."""
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

failed = BASE / 'harness03/attempts/attempt01'
result = json.loads((failed / 'result.json').read_bytes())
assert result['status'] == 'failed' and result['childState'] == 'exited'
assert result['counts']['testsRun'] == result['counts']['errors'] == 10
assert (failed / 'output.log').read_text().count('RuntimeError: Write outside fresh scratch or named receipts') == 10
assert len(json.loads((failed / 'sqlite-connections.json').read_bytes())) == 20
assert not (BASE / 'harness04/attempts').exists()
for old_name, new_name in [('harness03', 'harness05'), ('harness04', 'harness06')]:
    old, new = BASE / old_name, BASE / new_name
    new.mkdir()
    for row in json.loads((old / 'index.json').read_bytes())['files']:
        source = old / row['path']; raw = source.read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        if row['path'] in ('attempt_child.py', 'README.md', 'SCOPE.md', 'correction.json'): continue
        write(new / row['path'], raw)
    original = (old / 'attempt_child.py').read_text()
    body = original.replace('import resource\n', 'import resource\nimport stat\nimport threading\n')
    marker = 'def audit(event, args):\n'
    helper = '''# The native open audit event omits dir_fd. Preserve the original os.open
# call and expose its resolved pathname only to this synchronous audit hook.
# This is a cooperative fixture guard, not an OS isolation boundary.
native_open = os.open
open_context = threading.local()
def checked_os_open(path, flags, mode=0o777, *, dir_fd=None):
    name = os.fsdecode(path)
    target = Path(name)
    if dir_fd is not None and not target.is_absolute():
        if type(dir_fd) is not int or not stat.S_ISDIR(os.fstat(dir_fd).st_mode):
            raise RuntimeError('Invalid directory descriptor')
        parent = Path(os.readlink('/proc/self/fd/' + str(dir_fd)))
        if not parent.is_absolute():
            raise RuntimeError('Unresolved directory descriptor')
        target = parent / target
    previous = getattr(open_context, 'current', None)
    open_context.current = (name, target.resolve())
    try:
        return native_open(path, flags, mode, dir_fd=dir_fd)
    finally:
        open_context.current = previous
os.open = checked_os_open


'''
    assert marker in body
    body = body.replace(marker, helper + marker)
    old_target = '            target = path.resolve()\n            receipts = '
    new_target = "            opened = getattr(open_context, 'current', None)\n            target = opened[1] if opened is not None and opened[0] == os.fsdecode(args[0]) else path.resolve()\n            receipts = "
    assert old_target in body
    body = body.replace(old_target, new_target)
    ast.parse(body)
    write(new / 'attempt_child.py', body)
    write(new / 'references/dirfd-refusal-attempt_child.py', original)
    write(new / 'directory-fd-audit.patch', ''.join(difflib.unified_diff(original.splitlines(True), body.splitlines(True), fromfile=old_name, tofile=new_name)))
    dump(new / 'correction.json', dict(precedingHarness=old_name, productionUnchanged=True,
        correction='Preserve dir_fd os.open semantics; resolve native audit event against actual directory FD instead of cwd',
        boundsUnchanged=True, writesStillRestrictedToFreshScratchAndNamedReceipts=True,
        originalFailedScopeRetained=True, priorTestBodiesEntered=0, priorRuntimeSqliteConnections=20))
    write(new / 'README.md', '# Directory-descriptor-aware authority controls\n\n'
        '[Targets](targets.json), [scope](SCOPE.md), [correction](correction.json), [source](../implementation01/README.md).\n')
    write(new / 'SCOPE.md', (old / 'SCOPE.md').read_text() + '\nThe open audit now resolves directory-relative calls through their actual directory FD; it preserves the original call and restricts writes to the same fresh scratch or named receipts. No write directory or execution/storage bound is broadened.\n')
    files = []
    for path in sorted(new.rglob('*')):
        if path.is_file():
            raw = path.read_bytes(); files.append(dict(path=path.relative_to(new).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    dump(new / 'index.json', dict(scope='Directory-FD audit correction; production and bounds unchanged', files=files))
dump(BASE / 'directory-fd-failure-audit.json', dict(status='verified', testsStarted=10, testBodiesEntered=0,
    errors=10, runtimeSqliteConnections=20, scratchBytes=result['scratchBytes'], originalFailureRetained=True,
    unexecutedSupersededScope='harness04', corrections=['harness05', 'harness06']))
print(json.dumps(dict(sourceUnchanged=True, correctedScopes=['harness05', 'harness06'], failedSetupRetained=True)))
