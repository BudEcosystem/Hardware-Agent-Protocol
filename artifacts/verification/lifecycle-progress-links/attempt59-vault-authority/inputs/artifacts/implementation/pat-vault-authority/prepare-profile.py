"""One diagnostic method, unchanged production and bounds; never replaces scope05."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
OLD = BASE / 'harness05'
NEW = BASE / 'harness07'
TARGET = 'test_vault_authority.VaultAuthorityTests.test_after_seal_resumes_without_original_archive_or_new_worker'

def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())

def dump(path, value):
    write(path, json.dumps(value, indent=2) + '\n')

result = json.loads((OLD / 'attempts/attempt01/result.json').read_bytes())
assert result['status'] == 'failed' and result['childState'] == 'exited' and result['exitCode'] == -9
NEW.mkdir()
for row in json.loads((OLD / 'index.json').read_bytes())['files']:
    path = OLD / row['path']; raw = path.read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    if row['path'] in ('attempt_child.py', 'run_attempt.py', 'README.md', 'SCOPE.md', 'targets.json', 'correction.json'): continue
    write(NEW / row['path'], raw)
child0 = (OLD / 'attempt_child.py').read_text()
child = child0.replace('import threading\n', 'import threading\nimport cProfile\nimport pstats\n')
start = child.index('CONTROL_TARGETS = '); end = child.index('\n', start)
child = child[:start] + 'CONTROL_TARGETS = ' + repr([TARGET]) + child[end:]
child = child.replace("len(config['targets']) != 10 or len(set(config['targets'])) != 10", "len(config['targets']) != 1 or len(set(config['targets'])) != 1")
child = child.replace("counts['testsRun'] == 10 and", "counts['testsRun'] == 1 and")
child = child.replace("'sqlite-connections.json', 'actual-tests.json', 'test-return.json', 'child-errors.json'}", "'sqlite-connections.json', 'actual-tests.json', 'test-return.json', 'child-errors.json', 'profile.json'}")
child = child.replace('    class RecordingResult(unittest.TextTestResult):\n', '    profiler = cProfile.Profile()\n    class RecordingResult(unittest.TextTestResult):\n')
child = child.replace('            super().startTest(test)\n', '            super().startTest(test)\n            profiler.enable()\n')
child = child.replace('            super().stopTest(test)\n', '''            profiler.disable()
            stats = pstats.Stats(profiler)
            rows = []
            for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
                rows.append(dict(file=filename, line=line, function=name, primitiveCalls=primitive,
                    calls=calls, ownSeconds=own, cumulativeSeconds=cumulative))
            rows.sort(key=lambda row: row['cumulativeSeconds'], reverse=True)
            write('profile.json', dict(scope='Diagnostic single control method, not qualification or real-time evidence',
                method=test.id(), totalCalls=stats.total_calls, primitiveCalls=stats.prim_calls,
                totalSeconds=stats.total_tt, functions=rows[:160]))
            super().stopTest(test)
''')
parent0 = (OLD / 'run_attempt.py').read_text()
parent = parent0.replace('len(targets) == len(set(targets)) == 10', 'len(targets) == len(set(targets)) == 1')
parent = parent.replace("counts['testsRun'] == 10 and", "counts['testsRun'] == 1 and")
ast.parse(child); ast.parse(parent)
for name, old, new in [('attempt_child.py', child0, child), ('run_attempt.py', parent0, parent)]:
    write(NEW / name, new); write(NEW / 'references' / ('unprofiled-' + name), old)
    write(NEW / ('profile-' + name + '.patch'), ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='harness05/' + name, tofile='harness07/' + name)))
dump(NEW / 'targets.json', [TARGET])
write(NEW / 'README.md', '# Bounded publication/reconciliation profile\n\n'
    '[Target](targets.json), [scope](SCOPE.md), [source](../implementation01/README.md). This diagnostic does not replace the failed ten-method scope.\n')
write(NEW / 'SCOPE.md', '# Diagnostic scope\n\nOne original after-seal reconciliation method on unchanged production. '
    'cProfile runs around the method and writes at most 160 function records after it stops. '
    'The parent remains bounded to 180 seconds, 4 MiB output, 16 MiB/file, 256 MiB scratch and 8,192 entries. '
    'The child retains 120 CPU seconds, 512 MiB address space and 64 SQLite connections. '
    'Fresh private raw state and exact retained copies remain. No network, qualification worker or physical execution. '
    'The declared semantic oracle is a substitute. The original ten-method SIGKILL failure remains failed, with missing final receipts.\n')
files = []
for path in sorted(NEW.rglob('*')):
    if path.is_file():
        raw = path.read_bytes(); files.append(dict(path=path.relative_to(NEW).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
dump(NEW / 'index.json', dict(scope='One diagnostic method under original bounds; no aggregate pass claim', files=files))
dump(BASE / 'execution-limit-audit.json', dict(status='retained-failure', harness='harness05', exitCode=-9,
    elapsedSeconds=result['elapsedSeconds'], finalCountsMissing=True, finalOriginsMissing=True,
    loggedSuccessfulMethods=5, interruptedMethod=TARGET, parentWallDeadlineExceeded=False,
    childCpuLimitSeconds=120, cause='SIGKILL observed; CPU-limit exhaustion is consistent with the configured hard limit but no kernel/rusage receipt proves cause',
    noReplacementWorker=True, originalStateRetained=True))
print(json.dumps(dict(diagnostic='harness07', sourceUnchanged=True, boundsUnchanged=True)))
