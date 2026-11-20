"""One-shot standard-library acquisition; no project import or test execution."""
from pathlib import Path
import hashlib
import json
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-board-history'
SOURCE = BASE / 'harness01/attempts/attempt01-pure74'
OUT = BASE / 'results/attempt01-passed74'


def read(p):
    return json.loads(p.read_bytes())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(p, row):
    assert p.is_file() and not p.is_symlink()
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], str(p)


def inventory(root):
    rows = []
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink()
        if p.is_dir():
            continue
        assert stat.S_ISREG(p.stat().st_mode)
        rows.append({'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
    return rows


def identity(p):
    s = p.lstat()
    assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p), device=s.st_dev, inode=s.st_ino, uid=s.st_uid, gid=s.st_gid, mode=stat.S_IMODE(s.st_mode))


seals = []
for name, expected, relative_to_root in [
    ('implementation01', '971667f453515d82102853c68b442b78499209193fefb73a55f4fd32fc304fbc', True),
    ('harness01', '44868cd388744cd584d8782b5ef2c3f565e970a98c986ea80e158050a4619b42', False),
]:
    p = BASE / name
    assert sha(p / 'index.json') == expected
    rows = read(p / 'index.json')['files']
    for row in rows:
        verify((ROOT if relative_to_root else p) / row['path'], row)
    seals.append({'path': (p / 'index.json').relative_to(ROOT).as_posix(), 'sha256': expected, 'filesVerified': len(rows)})

result = read(SOURCE / 'result.json')
assert result['currentPass'] is True and result['childState'] == 'exited'
assert result['exitCode'] == 0 and result['errors'] == result['childErrors'] == []
assert not Path('/proc/' + str(result['pid'])).exists()
assert result['counts'] == dict(testsRun=74, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
for name, base, count in [('inputs', SOURCE / 'project', 2802), ('frozen', ROOT, 2805), ('harness', SOURCE / 'harness', 6)]:
    rows = read(SOURCE / (name + '-before.json'))
    assert rows == read(SOURCE / (name + '-after.json')) and len(rows) == count
    for row in rows:
        verify(base / row['path'], row)
external = read(SOURCE / 'external-before.json')
assert external == read(SOURCE / 'external-after.json') and len(external['files']) == 159
for row in external['files']:
    verify(Path(row['resolvedPath']), row)
origins = read(SOURCE / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == []
assert len(origins['records']) == 659 and len(origins['deniedBytecodeReads']) == 193
for row in origins['records']:
    if 'sha256' in row:
        assert sha(Path(row['origin'])) == row['sha256']
for name in ['compiler', 'driver']:
    assert read(SOURCE / (name + '-before.json')) == read(SOURCE / (name + '-after.json'))
selection = read(SOURCE / 'harness/targets.json')['targets']
actual = read(SOURCE / 'actual-tests.json')
assert actual['loaded'] == actual['executed'] == selection and len(selection) == 74
log = (SOURCE / 'output.log').read_text()
assert log.endswith('Ran 74 tests in 65.925s\n\nOK\n')
assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')] == selection

historical = ROOT / 'artifacts/implementation/pat-io-trial-engine/results/attempt01-passed20'
assert sha(historical / 'index.json') == 'fecc27074ba81e1e333bbb31b595d57bdcb3e3253d0994fbe89258703d931cd9'
history = read(historical / 'index.json')['files']
for row in history:
    verify(historical / row['path'], row)
fixtures = SOURCE / 'project/tests/data/io-transcript'
catalog = read(fixtures / 'index.json')
assert len(catalog['fixtures']) == 19
fixture_records = 0
for entry in catalog['fixtures']:
    old = ROOT / entry['sourceManifest']
    new = fixtures / entry['method'] / 'engine-0.json'
    assert sha(old) == sha(new) == entry['manifestSha256']
    manifest = read(new)
    assert len(manifest['records']) == entry['records']
    for row in manifest['records']:
        verify(new.parent / 'trial-0/records' / row['path'], row)
        verify(old.parent / 'trial-0/records' / row['path'], row)
    fixture_records += len(manifest['records'])
assert fixture_records == 2619
previous_reader = ROOT / 'artifacts/implementation/pat-io-transcript/results/attempt01-passed39'
assert sha(previous_reader / 'index.json') == '01ac201d0b8378e457a35f3074cc3b72168b8d97a8d1d0f8f66a68664d0a916c'
reader_rows = read(previous_reader / 'index.json')['files']
for row in reader_rows:
    verify(previous_reader / row['path'], row)
raw_before = read(SOURCE / 'raw-scratch-before.json')
raw = Path(result['scratchPath'])
assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
assert inventory(raw) == inventory(SOURCE / 'scratch') == read(SOURCE / 'scratch-index.json') == []
before = inventory(SOURCE)
shutil.copytree(SOURCE, OUT / 'attempt')
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)
assert identity(raw) == raw_before['identity'] and not any(raw.iterdir())
proof = {'scope': 'Actual pure74 original-host semantic board-history and reader checks over previously executed trial20 data; no new runtime or effect execution.',
    'counts': result['counts'], 'testSeconds': 65.925, 'elapsedSeconds': result['elapsedSeconds'],
    'projectFilesVerified': 2802, 'frozenFilesVerified': 2805, 'activeHarnessFilesVerified': 6,
    'externalFilesVerified': 159, 'preparationSeals': seals,
    'originSummary': origins['summary'], 'actualOriginFileHashesRechecked': True, 'bytecodeReadsRefused': 193,
    'compilerAndDriverStable': True, 'methodOrderAndLogVerified': True,
    'historicalResultFilesReverified': len(history), 'previousReaderResultFilesReverified': len(reader_rows),
    'exactHistoricalFixtureStates': 19, 'coherentHistoriesCheckedByTests': 18, 'corruptHistoriesRejectedByTests': 1,
    'coherentHistoryCountersAssertedInProcess': {'activations': 29, 'completedCycles': 26, 'canceledActivations': 3},
    'exactHistoricalFixtureRecords': fixture_records, 'historicalCheckpointsInspectedByTests': 352,
    'rawScratch': raw_before['identity'], 'rawScratchEmpty': True, 'rawScratchOriginalRetained': True,
    'attemptFilesAcquired': len(before), 'independentReview': False,
    'independentOutcomeChecked': False, 'qualificationPassed': False,
    'limitations': ['Board-history semantics only; complete authority/procedure/event/replay/floor semantics and qualification remain unfinished.',
        'Mutation and purity assertions are in-process; no standalone semantic outcome verdict is emitted.',
        'Historical transcript identities are not qualified as current driver/compiler identities.',
        'No live source integration, new Runtime construction, physical device or model execution.']}
with (OUT / 'proof.json').open('x') as f:
    f.write(json.dumps(proof, indent=2) + '\n')
print(json.dumps({'attemptFiles': len(before), 'fixtureStates': 19, 'fixtureRecords': fixture_records,
                  'historicalFilesReverified': len(history), 'counts': result['counts']}))
