"""Audit completed scopes and original/copy bytes without rerunning code."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-definition-build'
STAGE = BASE / 'implementation01'
PIN = '7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc'
OLD = ROOT / 'artifacts/implementation/pat-io-recorded-catalog/implementation04/project'

def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path, row):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size == row['bytes']
    assert sha(path) == row['sha256'], str(path)
def inventory(folder):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row:row['path'])

assert sha(STAGE / 'index.json') == PIN
frozen = read(STAGE / 'index.json')['files']; assert len(frozen) == 278
for row in frozen: verify(ROOT / row['path'], row)
baseline = read(STAGE / 'baseline-inputs.json')['inheritedProjectInputs']; assert len(baseline) == 274
changed = []
for row in baseline:
    origin = ROOT / row['path']; verify(origin, row)
    relative = origin.relative_to(OLD)
    if sha(STAGE / 'project' / relative) != row['sha256']: changed.append(relative.as_posix())
assert changed == ['hms/synthetic_io_installation.py']
assert sha(STAGE / 'project/supervisor/worker_entry.py') == sha(OLD / 'supervisor/worker_entry.py')
for number in range(1, 5):
    harness = BASE / ('harness%02d' % number)
    for row in read(harness / 'index.json')['files']: verify(harness / row['path'], row)
assert not (BASE / 'harness01/attempts').exists()
attempts = []
for number, name, count in ((3, 'attempt01-pure21', None), (4, 'attempt01-pure21', 21), (2, 'attempt01-actual', 1)):
    harness = BASE / ('harness%02d' % number); attempt = harness / 'attempts' / name
    result = read(attempt / 'result.json'); review = read(harness / 'review.json')
    assert review['sourceIndexSha256'] == PIN and result['childState'] == 'exited'
    assert result['status'] == ('failed' if count is None else 'passed')
    assert result['currentPass'] == (count is not None)
    assert result['timeoutSeconds'] == 180 and result['limits']['singleAcquiredFileBytes'] == 16*1024*1024
    for label, folder in [('inputs', attempt / 'project'), ('frozen', ROOT), ('harness', attempt / 'harness')]:
        before = read(attempt / (label + '-before.json'))
        assert before == read(attempt / (label + '-after.json'))
        for row in before: verify(folder / row['path'], row)
    assert read(attempt / 'external-before.json') == read(attempt / 'external-after.json')
    for row in read(attempt / 'external-before.json')['files']: verify(Path(row['resolvedPath']), row)
    if count is not None:
        assert result['exitCode'] == 0 and result['errors'] == result['childErrors'] == []
        assert result['counts'] == dict(testsRun=count, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
        targets = read(harness / 'targets.json')['targets']
        assert len(targets) == count and result['actualTests'] == dict(loaded=targets, executed=targets, exactSelection=True)
        for label in ('compiler', 'driver'):
            assert read(attempt / (label + '-before.json')) == read(attempt / (label + '-after.json'))
    else:
        assert result['counts'] is None and result['scratchRetainedBytes'] == 0
        assert 'Required child isolation flags or exact target count missing' in (attempt / 'output.log').read_text()
    origins = read(attempt / 'imports.json'); assert origins['violations'] == origins['prohibitedAttempts'] == []
    for row in origins['records']:
        if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
    connections = read(attempt / 'sqlite-connections.json')
    assert len(connections) <= review['sqliteConnectionsMaximum']
    if number in (3, 4): assert connections == []
    raw = Path(result['scratchPath']); identity = read(attempt / 'raw-scratch-before.json')['identity']; info = raw.lstat()
    assert stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) == (
        identity['device'], identity['inode'], identity['uid'], identity['mode'])
    rows = inventory(raw)
    assert rows == inventory(attempt / 'scratch') == read(attempt / 'scratch-index.json')
    assert sum(row['bytes'] for row in rows) == result['scratchRetainedBytes'] <= review['scratchBytesCeiling']
    assert all(row['bytes'] <= 16*1024*1024 for row in rows)
    attempts.append(dict(harness=harness.name, attempt=name, status=result['status'], counts=result['counts'],
        elapsedSeconds=result['elapsedSeconds'], rawFiles=len(rows), rawBytes=result['scratchRetainedBytes'], sqliteOpens=len(connections)))
    if number == 4:
        observed = read(raw / 'test_original_bundles_bindings_and_proofs_match_with_half_the_derivations/derivation-counts.json')
        assert observed['legacyDerivations'] == 8 and observed['candidateDerivations'] == 4 and observed['exactCanonicalOutputEqual']
    if number == 2:
        archive = read(raw / 'test_actual_original_matrix_catalog_execution_and_historical_replay/worker-archive.json')
        phases = archive['phases']

actual = read(BASE / 'actual-catalog-audit.json')
assert actual['actualScopePassed'] and actual['completeMatrixCases'] == 30
assert actual['historicalReplayVerified'] and actual['changedContextRefusedWithoutNovelty'] and actual['oneOriginalWorker']
assert actual['applicationActivations'] == actual['applicationCompletions'] == 1
assert actual['applicationCancellations'] == actual['currentClaims'] == actual['boardOwners'] == 0
assert actual['sourceIdentitiesIndependentlyRecomputed'] and actual['authorityDatabaseBytes'] <= 16*1024*1024
assert sha(ROOT/'artifacts/implementation/pat-io-recorded-catalog/index.json') == '6c8eb11be9274354d4a31f280fa7f579aae8fe31473e0fc33bd51790ee4e489e'
assert sha(ROOT/'artifacts/implementation/pat-io-catalog-worker-profile/index.json') == 'bc87c178516e2187a8aaca22d9bade060318d84e95e0d834d967b0753b614ec3'
report = dict(goalStatus='active', sourceIndexSha256=PIN, changedProductionFiles=changed,
    unchangedInheritedProjectFiles=273, newPureControlsPassed=7, inheritedPureControlsPassed=14,
    completedMethodsPassed=22, passingScopes=2, failedStartupScopes=1, actualIntegrationScopePassed=True,
    completeWorkerCases=30, actualAudit='actual-catalog-audit.json', attempts=attempts, phases=phases,
    derivationObservation=observed, authorityDatabaseBytes=actual['authorityDatabaseBytes'], headroomBytes=actual['headroomBytes'],
    exactOriginalKeyReplay=True, changedConfigurationRefusedWithoutNovelty=True, coldHistoricalReplayAfterSessionChange=True,
    originalSourceAndScratchBytesVerified=True, previousFailuresPreserved=True, diagnosticSignalHandlerAbsent=True,
    previousTimeoutCauseEstablished=False, publicCatalogMounted=False, protectedControlCapacityQualified=False,
    performanceOrPhysicalGuarantee=False, independentReview=False)
with (BASE / 'RESULTS.json').open('x') as stream: stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps({key:report[key] for key in ('completedMethodsPassed','passingScopes','failedStartupScopes',
    'actualIntegrationScopePassed','authorityDatabaseBytes','headroomBytes')}))
