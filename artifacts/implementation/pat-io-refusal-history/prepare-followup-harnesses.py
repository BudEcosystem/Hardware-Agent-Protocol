"""Prepare smaller, disjoint selections without importing project code."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-refusal-history'
OLD = BASE / 'harness02-refusal56'
OLD_PIN = '978d13e806d755896022d2bed36649bb761ab63ea4f3bc52dcf5fe60a607655f'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
assert sha(OLD / 'index.json') == OLD_PIN
for row in read(OLD / 'index.json')['files']:
    path = OLD / row['path']
    assert not path.is_symlink() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
original = read(OLD / 'targets.json')['targets']
selected = []
for folder, label, count, cls in [
    ('harness03-observation27', 'ObservationHistory27', 27, 'test_pat_io_observation_history.IoObservationHistoryTests.'),
    ('harness04-refusal29', 'RefusalHistory29', 29, 'test_pat_io_refusal_history.IoRefusalHistoryTests.'),
]:
    new = BASE / folder; new.mkdir(exist_ok=False)
    (new / 'references').mkdir()
    targets = [name for name in original if name.startswith(cls)]
    assert len(targets) == len(set(targets)) == count
    selected += targets
    write(new / 'targets.json', dict(testCount=count, targets=targets))
    borrowed = []
    for name in ['run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json']:
        src = OLD / name
        relative = 'references/' + ('refusal56-' if '/' not in name else '') + src.name
        dst = new / relative; shutil.copyfile(src, dst)
        borrowed.append(dict(source=src.relative_to(ROOT).as_posix(), copy=relative, bytes=src.stat().st_size, sha256=sha(src)))
    write(new / 'borrowed-inputs.json', borrowed)
    lower = folder.split('-', 1)[1]
    for name in ['run_attempt.py', 'attempt_child.py']:
        before = (OLD / name).read_text()
        after = before.replace('RefusalHistory56', label).replace('refusal56', lower)
        if name == 'run_attempt.py':
            old_check = """sum(name.startswith('test_pat_io_observation_history.IoObservationHistoryTests.') for name in targets['targets']) != 27 or
                sum(name.startswith('test_pat_io_refusal_history.IoRefusalHistoryTests.') for name in targets['targets']) != 29"""
            assert after.count(old_check) == 1
            after = after.replace(old_check, "sum(name.startswith(%r) for name in targets['targets']) != %d" % (cls, count))
        for old, replacement in [('!= 56', '!= ' + str(count)), ('== 56', '== ' + str(count)), ("'expectedTests': 56", "'expectedTests': " + str(count))]:
            after = after.replace(old, replacement)
        ast.parse(after)
        (new / name).write_text(after)
        (new / (name + '.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=(OLD / name).relative_to(ROOT).as_posix(), tofile=(new / name).relative_to(ROOT).as_posix())))
    (new / 'README.md').write_text('# Isolated ' + lower + ' follow-up\n\nRun exactly ' + str(count) + ' unchanged methods from the timed-out 56-method\nselection on the same [frozen source](../implementation01/README.md). See\n[scope](SCOPE.md) and [selection](targets.json). Results remain separate from the\noriginal failed attempt and the earlier passing 72-method regression.\n')
    (new / 'SCOPE.md').write_text('# Follow-up ' + lower + ' scope\n\nThe original combined 56-method invocation timed out. This selection contains\nexactly ' + str(count) + ' unchanged methods from it, on the unchanged 7,060-file project\nclosure. Together, the two follow-up selections cover the original 56 methods;\nthe earlier passing 72-method invocation remains separate. No method is removed.\n\nEach invocation retains the original 180-second execution deadline, 16 MiB\nscratch, 8,192 inventory files, 256 MiB input collection, 16 MiB file, 4 MiB\nreceipt and 8 MiB log limits. The child uses -I -S -B with exact package and\norigin checks. Cooperative hooks forbid SQLite connections, network and\nsubprocesses; these are not an OS sandbox. Evidence bounds remain unchanged.\n\nOnly labels, exact counts and the closed class selection change in the reviewed\nparent/child harness. Source, tests, fixtures, protocol and effect bounds remain\nunchanged. Original failed evidence and private scratch remain retained. No\nRuntime, physical port/device, MCU/emulator, inference, public service or\nacquired controller executes. Full qualification flags remain false. No live\nHMS or adjacent Harness changes. Primary-agent adaptation review is required\nbefore release; independent helpers remain unavailable.\n')
assert selected == original
print(json.dumps(dict(prepared=['harness03-observation27', 'harness04-refusal29'], selected=len(selected), projectImported=False)))
