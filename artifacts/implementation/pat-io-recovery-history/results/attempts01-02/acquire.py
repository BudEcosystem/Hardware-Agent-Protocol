"""Acquire two isolated pure attempts using only the standard library.

This does not execute project code or turn a failed result into a pass.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-recovery-history'
OUT = BASE / 'results/attempts01-02'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, row):
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)


def inventory(root):
    rows = []
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir():
            continue
        assert stat.S_ISREG(path.stat().st_mode)
        rows.append(dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return rows


def identity(path):
    value = path.lstat()
    assert stat.S_ISDIR(value.st_mode)
    return dict(path=str(path), device=value.st_dev, inode=value.st_ino,
                uid=value.st_uid, gid=value.st_gid, mode=stat.S_IMODE(value.st_mode))


def sealed(path, expected, rooted=False):
    assert sha(path / 'index.json') == expected
    rows = read(path / 'index.json')['files']
    for row in rows:
        verify((ROOT if rooted else path) / row['path'], row)
    return dict(path=(path / 'index.json').relative_to(ROOT).as_posix(), sha256=expected, filesVerified=len(rows))


assert sha(BASE / 'selection-plan.json') == '67a7367e565602200b073b5799e2dc7022534dded394f74708326ba6ac9e4a56'
plan = read(BASE / 'selection-plan.json')
seals = [sealed(BASE / 'implementation01', plan['sourceIndexSha256'], True)]
seals += [sealed(BASE / group['harness'], group['indexSha256']) for group in plan['groups']]
prior = ROOT / 'artifacts/implementation/pat-io-authorized-history'
seals.append(sealed(prior / 'harness01', '30f85a1e8806811043ec99747940589bea2b6485ef9ba95376c80f38cffbeda8'))
old_targets = read(prior / 'harness01/targets.json')['targets']
selection = []
for group in plan['groups']:
    path = BASE / group['harness'] / 'targets.json'
    assert sha(path) == group['targetsSha256']
    selection += read(path)['targets']
assert selection == plan['targets'] and len(selection) == len(set(selection)) == 136
assert len(old_targets) == 103 and set(old_targets) <= set(selection)
assert len(set(selection) - set(old_targets)) == 33

capture = ROOT / 'artifacts/implementation/pat-io-pending-recovery/results/attempt01-passed46'
seals.append(sealed(capture, '64f228609eb271c346ba18c4e4874e2417e032b9e30bf83e6498231cd738818b'))
source_project = BASE / 'implementation01/project'
fixtures = source_project / 'tests/data/io-recovery'
catalog = read(fixtures / 'index.json')
assert catalog['sourceIndexSha256'] == seals[-1]['sha256']
assert len(catalog['fixtures']) == 8 and len(catalog['files']) == 1149
for row in catalog['files']:
    verify(fixtures / row['path'], row)
trusted = read(capture / 'attempt/harness/targets.json')
execution_records = configuration_records = snapshots = fault_count = 0
for fixture in catalog['fixtures']:
    name = fixture['method']
    original = ROOT / fixture['source']
    acquired = fixtures / name
    assert original == capture / 'attempt/scratch' / name
    assert sha(original / 'engine-0.json') == sha(acquired / 'manifest.json')
    manifest = read(acquired / 'manifest.json')
    # The reviewed selection supplies the schedule, not injectedFaults output.
    assert fixture['expectedFaults'] == trusted['pendingFaultPlans'][name] == manifest['expectedFaults']
    grants = []
    if name in trusted['pendingWithdrawalPhase']:
        grants = [dict(phase=trusted['pendingWithdrawalPhase'][name], label='drive:adapters:before',
                       grants=[dict(principal='pat-io-trial-worker', deployment='simulation:io-hub',
                                    target='sim:gpio5', verb='read')])]
    authority = dict(profile='hms.pat.io-trusted-authority/0.1', principal='pat-io-trial-worker',
                     deployment='simulation:io-hub', initialRegistryRevision=13,
                     initialGrants=[dict(principal='pat-io-trial-worker', deployment='simulation:io-hub',
                                         target='*', verb='admin')], grantChanges=grants)
    assert fixture['expectedAuthority'] == manifest['expectedAuthority'] == authority
    for directory, refs in [('records', manifest['records']), ('configuration', manifest['configuration']['records'])]:
        for row in refs:
            verify(original / 'trial-0' / directory / row['path'], row)
            verify(acquired / directory / row['path'], row)
    execution_records += len(manifest['records'])
    configuration_records += len(manifest['configuration']['records'])
    snapshots += len(manifest['configuration']['snapshots'])
    fault_count += len(fixture['expectedFaults']['faults'])
assert (execution_records, configuration_records, snapshots, fault_count) == (823, 318, 136, 10)

proofs = []
for group, attempt in zip(plan['groups'], ['attempt01-regression83', 'attempt02-recovery53']):
    source = BASE / group['harness'] / 'attempts' / attempt
    result = read(source / 'result.json')
    assert result['childState'] == 'exited' and result['errors'] == result['childErrors'] == []
    assert not Path('/proc/' + str(result['pid'])).exists()
    assert result['timeoutSeconds'] == 180
    for prefix, base, count in [('inputs', source / 'project', 7056), ('frozen', ROOT, 7061), ('harness', source / 'harness', 6)]:
        rows = read(source / (prefix + '-before.json'))
        assert rows == read(source / (prefix + '-after.json')) and len(rows) == count
        for row in rows:
            verify(base / row['path'], row)
    external = read(source / 'external-before.json')
    assert external == read(source / 'external-after.json') and len(external['files']) == 159
    for row in external['files']:
        verify(Path(row['resolvedPath']), row)
    origins = read(source / 'imports.json')
    assert origins['violations'] == origins['prohibitedAttempts'] == []
    assert len(origins['records']) == origins['summary']['recordCount']
    assert origins['summary']['allOriginsMatched'] and origins['deniedBytecodeReads']
    for row in origins['records']:
        if 'sha256' in row:
            assert sha(Path(row['origin'])) == row['sha256']
    for name in ['compiler', 'driver']:
        assert read(source / (name + '-before.json')) == read(source / (name + '-after.json'))
    targets = read(source / 'harness/targets.json')['targets']
    actual = read(source / 'actual-tests.json')
    assert actual['loaded'] == actual['executed'] == targets and len(targets) == group['testCount']
    log = (source / 'output.log').read_text()
    match = re.search(r'Ran ' + str(group['testCount']) + r' tests in ([0-9.]+)s\n\n(?:OK|FAILED[^\n]*)\n$', log)
    assert match is not None
    counts = result['counts']
    assert counts['testsRun'] == group['testCount']
    passed = all(counts[key] == 0 for key in counts if key != 'testsRun')
    assert passed == result['currentPass'] == (result['exitCode'] == 0)
    if passed:
        assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')] == targets
    raw_before = read(source / 'raw-scratch-before.json')
    raw = Path(result['scratchPath'])
    assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
    assert inventory(raw) == inventory(source / 'scratch') == read(source / 'scratch-index.json') == []
    before = inventory(source)
    shutil.copytree(source, OUT / attempt)
    assert inventory(OUT / attempt) == before == inventory(source)
    assert identity(raw) == raw_before['identity'] and not any(raw.iterdir())
    proofs.append(dict(attempt=attempt, currentPass=passed, counts=counts, testSeconds=float(match.group(1)),
                       elapsedSeconds=result['elapsedSeconds'], timeoutSeconds=result['timeoutSeconds'],
                       projectFilesVerified=7056, frozenFilesVerified=7061, activeHarnessFilesVerified=6,
                       externalFilesVerified=159, originSummary=origins['summary'], actualOriginFileHashesRechecked=True,
                       bytecodeReadsRefused=len(origins['deniedBytecodeReads']), compilerAndDriverStable=True,
                       methodOrderVerified=True, rawScratch=raw_before['identity'], rawScratchEmpty=True,
                       rawScratchOriginalRetained=True, attemptFilesAcquired=len(before)))

all_passed = all(p['currentPass'] for p in proofs)
shutil.copyfile(BASE / 'selection-plan.json', OUT / 'selection-plan.json')
assert sha(OUT / 'selection-plan.json') == sha(BASE / 'selection-plan.json')
proof = dict(scope='Two disjoint pure selections of the same frozen recovery-history source; separate original 180-second deadlines.',
             attempts=proofs, allSelectionsPassed=all_passed, distinctMethodsExecuted=136, priorMethodsIncluded=103,
             newMethodsIncluded=33, preparationSeals=seals, selectionPlanSha256=sha(BASE / 'selection-plan.json'),
             exactRecoveryFixtureFiles=1149, recoveryExecutionRecords=execution_records,
             recoveryConfigurationRecords=configuration_records, recoveryConfigurationSnapshots=snapshots,
             trustedFaultsFromReviewedSelection=fault_count, independentReview=False,
             configurationAttested=False, compilerIdentityAttested=False, observationSampleSemanticsChecked=False,
             staticTimingPolicyChecked=False, allFaultScenariosChecked=False,
             independentOutcomeChecked=False, qualificationPassed=False,
             limitations=['No live integration, Runtime construction, SQLite connection, hardware or inference execution.',
                          'Pure assertions inspect retained data; this is not a standalone complete outcome verdict.',
                          'One immutable synthetic installation; no full read withdrawal, clock/reopen recovery or auxiliary actors.',
                          'Current compiler identity, intermediate sampling, full fault matrix, aggregate storage and public qualification remain incomplete.'])
if all_passed:
    proof['recoveryAssertionsPassed'] = dict(fixtures=8, activations=8, completedCycles=0, canceledActivations=8,
                                           faults=10, recoveryStops=8, settlements=8, guardPhases=10,
                                           parents=dict(failed=7, canceled=1), heldClaims=0)
with (OUT / 'proof.json').open('x') as stream:
    stream.write(json.dumps(proof, indent=2) + '\n')
print(json.dumps(dict(allSelectionsPassed=all_passed, attempts=[dict(attempt=p['attempt'], counts=p['counts'],
                       acquiredFiles=p['attemptFilesAcquired']) for p in proofs], preparationSeals=seals)))
