"""All 19 unchanged methods in disjoint small processes; no aggregate speed claim."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
OLD = BASE / 'harness05'

def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())

def dump(path, value):
    write(path, json.dumps(value, indent=2) + '\n')

profile = BASE / 'harness07/attempts/attempt01'
result = json.loads((profile / 'result.json').read_bytes())
assert result['status'] == 'failed' and result['childState'] == 'exited'
assert result['counts']['testsRun'] == result['counts']['errors'] == 1
assert 'PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE' in (profile / 'output.log').read_text()
timings = json.loads((profile / 'profile.json').read_bytes())
targets = json.loads((OLD / 'targets.json').read_bytes()) + json.loads((BASE / 'harness06/targets.json').read_bytes())
assert len(targets) == len(set(targets)) == 19
scopes = []
for offset in range(0, len(targets), 2):
    selection = targets[offset:offset + 2]
    name = 'harness%02d' % (8 + offset // 2)
    new = BASE / name; new.mkdir()
    for row in json.loads((OLD / 'index.json').read_bytes())['files']:
        path = OLD / row['path']; raw = path.read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
        if row['path'] in ('attempt_child.py', 'run_attempt.py', 'README.md', 'SCOPE.md', 'targets.json', 'correction.json'): continue
        write(new / row['path'], raw)
    child0 = (OLD / 'attempt_child.py').read_text()
    start = child0.index('CONTROL_TARGETS = '); end = child0.index('\n', start)
    child = child0[:start] + 'CONTROL_TARGETS = ' + repr(selection) + child0[end:]
    child = child.replace("len(config['targets']) != 10 or len(set(config['targets'])) != 10", "len(config['targets']) != %d or len(set(config['targets'])) != %d" % (len(selection), len(selection)))
    child = child.replace("counts['testsRun'] == 10 and", "counts['testsRun'] == %d and" % len(selection))
    parent0 = (OLD / 'run_attempt.py').read_text()
    parent = parent0.replace('len(targets) == len(set(targets)) == 10', 'len(targets) == len(set(targets)) == %d' % len(selection))
    parent = parent.replace("counts['testsRun'] == 10 and", "counts['testsRun'] == %d and" % len(selection))
    ast.parse(child); ast.parse(parent)
    for filename, before, after in [('attempt_child.py', child0, child), ('run_attempt.py', parent0, parent)]:
        write(new / filename, after)
        write(new / 'references' / ('ten-method-' + filename), before)
        write(new / ('selection-' + filename + '.patch'), ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='harness05/' + filename, tofile=name + '/' + filename)))
    dump(new / 'targets.json', selection)
    write(new / 'README.md', '# Disjoint authority publication controls\n\n'
        '[Targets](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md). Original failures remain failed.\n')
    write(new / 'SCOPE.md', '# Correctness selection\n\n'
        '%d unchanged methods, disjoint from the other nine selections. Together these selections cover all 19 original controls, including failures and full evidence payloads.\n\n' % len(selection) +
        'This does not replace or pass the failed ten-method aggregate timing scope. The profile reached installation only and is not an import performance measurement. '
        'Per process: parent 180 seconds, 4 MiB output, 16 MiB/file, 256 MiB scratch, 8,192 entries; child 120 CPU seconds, 512 MiB address space, 64 SQLite opens. '
        'The production snapshot remains five seconds. No source, document, domain, effect or operation limit changes. '
        'Fresh private state and exact copies remain. No network, worker or physical execution; declared substitute semantic oracle.\n')
    files = []
    for path in sorted(new.rglob('*')):
        if path.is_file():
            raw = path.read_bytes(); files.append(dict(path=path.relative_to(new).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    dump(new / 'index.json', dict(scope='Disjoint correctness coverage; original aggregate timing remains failed', files=files))
    scopes.append(dict(harness=name, targets=selection))
dump(BASE / 'control-selections.json', dict(originalMethods=targets, scopes=scopes,
    sourceUnchanged=True, originalAggregatePassed=False, originalFailuresRetained=True,
    changes='Process grouping only; no method omitted or altered', perProcessBoundsUnchanged=True))
dump(BASE / 'profile-findings.json', dict(scope='Diagnostic profile failed during installation, before import/reconciliation',
    result='PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE', profiledSeconds=timings['totalSeconds'],
    totalCalls=timings['totalCalls'], directMeasurements=timings['functions'][:28],
    importTimingsMeasured=False, snapshotLimitWidened=False,
    implication='Full fixture preparation dominates this instrumented run; obtain correctness receipts separately from the failed aggregate timing scope'))
print(json.dumps(dict(scopes=[row['harness'] for row in scopes], methods=19, sourceUnchanged=True)))
