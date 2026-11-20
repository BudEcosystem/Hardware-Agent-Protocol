"""One-shot standard-library acquisition; no project import or test execution."""
from pathlib import Path
import hashlib
import json
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-correspondence'
SOURCE = BASE / 'harness01/attempts/attempt01-focused41'
OUT = BASE / 'results/attempt01-passed41'


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
    ('implementation01', '67e5263419b5bfe51559f0a3ff0492bb1eee73a6751ac2b7322306c9913acdca', True),
    ('harness01', '5ee530cc67c415b5c71a24b622f0bd1499a989db3dc7e0aaad24c19f5e78bfca', False),
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
assert result['counts'] == dict(testsRun=41, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
for name, base, count in [('inputs', SOURCE / 'project', 2808), ('frozen', ROOT, 2811), ('harness', SOURCE / 'harness', 6)]:
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
assert len(origins['records']) == origins['summary']['recordCount']
assert origins['deniedBytecodeReads']
for row in origins['records']:
    if 'sha256' in row:
        assert sha(Path(row['origin'])) == row['sha256']
for name in ['compiler', 'driver']:
    assert read(SOURCE / (name + '-before.json')) == read(SOURCE / (name + '-after.json'))
selection = read(SOURCE / 'harness/targets.json')['targets']
actual = read(SOURCE / 'actual-tests.json')
assert actual['loaded'] == actual['executed'] == selection and len(selection) == 41
log = (SOURCE / 'output.log').read_text()
import re
match = re.search(r'Ran 41 tests in ([0-9.]+)s\n\nOK\n$', log)
assert match is not None
test_seconds = float(match.group(1))
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
previous_reader = ROOT / 'artifacts/implementation/pat-io-procedure-history/results/attempt01-passed146'
assert sha(previous_reader / 'index.json') == '9afd4965fd04e138fd7c42961f36aebcb07d50c09a0ea95670a513bbb74e8320'
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
proof = {'scope': 'Actual focused41 original-host PAT correspondence and four retained-history regression methods over previously executed trial20 data; no new runtime or effect execution.',
    'counts': result['counts'], 'testSeconds': test_seconds, 'elapsedSeconds': result['elapsedSeconds'],
    'projectFilesVerified': 2808, 'frozenFilesVerified': 2811, 'activeHarnessFilesVerified': 6,
    'externalFilesVerified': 159, 'preparationSeals': seals,
    'originSummary': origins['summary'], 'actualOriginFileHashesRechecked': True, 'bytecodeReadsRefused': len(origins['deniedBytecodeReads']),
    'compilerAndDriverStable': True, 'methodOrderAndLogVerified': True,
    'historicalResultFilesReverified': len(history), 'previousProcedureResultFilesReverified': len(reader_rows),
    'exactHistoricalFixtureStates': 19, 'coherentBoardHistoriesCheckedByTests': 18, 'corruptBoardHistoriesRejectedByTests': 1, 'authorityHistoriesCheckedByTests': 19,
    'focusedSelection': {'newCorrespondenceMethods': 37, 'retainedHistoryMethods': 4, 'fullPrior146Rerun': False},
    'correspondenceCountsAssertedInProcess': {'lowered': 18, 'refused': 1, 'emittedChildRequests': 35},
    'procedureCountsAssertedInProcess': {'parents': 18, 'events': 105, 'completed': 9, 'canceled': 5, 'failed': 1, 'running': 1, 'accepted': 2, 'unsubmittedTrials': 1},
    'authorityCountsAssertedInProcess': {'operations': 32, 'events': 156, 'heldClaims': 1, 'unresolvedOperations': 1},
    'coherentHistoryCountersAssertedInProcess': {'activations': 29, 'completedCycles': 26, 'canceledActivations': 3},
    'exactHistoricalFixtureRecords': fixture_records, 'historicalCheckpointsInspectedByTests': 352,
    'rawScratch': raw_before['identity'], 'rawScratchEmpty': True, 'rawScratchOriginalRetained': True,
    'attemptFilesAcquired': len(before), 'independentReview': False,
    'independentOutcomeChecked': False, 'qualificationPassed': False,
    'limitations': ['Finite correspondence/history components only; current compiler/configuration attestation, complete failure causes, fault matrix and qualification remain unfinished.',
        'Mutation and purity assertions are in-process; no standalone semantic outcome verdict is emitted.',
        'Historical transcript identities are not qualified as current driver/compiler identities; full prior146 is not rerun.',
        'Static timing recurrence is associated with trusted setup but not reproved by this component.',
        'No live source integration, new Runtime construction, physical device or model execution.']}
with (OUT / 'proof.json').open('x') as f:
    f.write(json.dumps(proof, indent=2) + '\n')
print(json.dumps({'attemptFiles': len(before), 'fixtureStates': 19, 'fixtureRecords': fixture_records,
                  'historicalFilesReverified': len(history), 'counts': result['counts']}))
