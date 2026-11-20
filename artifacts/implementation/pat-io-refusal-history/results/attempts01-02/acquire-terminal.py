"""One-shot standard-library retention of the actual refusal128 attempt."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-refusal-history'
OUT = BASE / 'results/attempts01-02'


def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)


def inventory(root):
    rows = []
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir(): continue
        assert stat.S_ISREG(path.stat().st_mode)
        rows.append(dict(path=path.relative_to(root).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return rows


def identity(path):
    value = path.lstat(); assert stat.S_ISDIR(value.st_mode)
    return dict(path=str(path), device=value.st_dev, inode=value.st_ino, uid=value.st_uid,
                gid=value.st_gid, mode=stat.S_IMODE(value.st_mode))


plan_path = BASE / 'selection-plan.json'
assert sha(plan_path) == '87ce18c5926154c353a784e62ded44a6404b23307e89734082572117bec9113d'
plan = read(plan_path); seals = []
entries = [(BASE / 'implementation01', plan['sourceIndexSha256'], True)]
entries += [(BASE / group['harness'], group['indexSha256'], False) for group in plan['groups']]
entries += [(ROOT / 'artifacts/implementation/pat-io-observation-history/implementation01',
             'df4991717a44ead0f2065a649afefe77822cca00352b54ee72add4deef996c20', True)]
for folder, expected, rooted in entries:
    assert sha(folder / 'index.json') == expected
    rows = read(folder / 'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder) / row['path'], row)
    seals.append(dict(path=(folder / 'index.json').relative_to(ROOT).as_posix(), sha256=expected, filesVerified=len(rows)))
baseline = read(BASE / 'implementation01/baseline-inputs.json')
assert baseline['sourceIndexSha256'] == seals[-1]['sha256'] and len(baseline['inheritedProjectInputs']) == 7058
old_project = ROOT / 'artifacts/implementation/pat-io-observation-history/implementation01/project'
changes = {'hms/pat_io_operation_history.py', 'hms/pat_io_procedure_history.py'}; unchanged = 0
for row in baseline['inheritedProjectInputs']:
    relative = (ROOT / row['path']).relative_to(old_project)
    if relative.as_posix() in changes: continue
    verify(BASE / 'implementation01/project' / relative, row); unchanged += 1
assert unchanged == 7056
selected = []
for group in plan['groups']:
    path = BASE / group['harness'] / 'targets.json'; assert sha(path) == group['targetsSha256']
    selected += read(path)['targets']
assert selected == plan['targets'] and len(selected) == len(set(selected)) == 128
assert sum('.IoRefusalHistoryTests.' in t for t in selected) == 29

proofs = []
for group, attempt in zip(plan['groups'], ['attempt01-regression72', 'attempt02-refusal56']):
    SOURCE = BASE / group['harness'] / 'attempts' / attempt
    result = read(SOURCE / 'result.json')
    assert result['childState'] == 'exited' and not Path('/proc/' + str(result['pid'])).exists()
    assert result['timeoutSeconds'] == 180
    for prefix, base, count in [('inputs', SOURCE / 'project', 7060), ('frozen', ROOT, 7065), ('harness', SOURCE / 'harness', 6)]:
        rows = read(SOURCE / (prefix + '-before.json'))
        assert rows == read(SOURCE / (prefix + '-after.json')) and len(rows) == count
        for row in rows: verify(base / row['path'], row)
    external = read(SOURCE / 'external-before.json')
    assert external == read(SOURCE / 'external-after.json') and len(external['files']) == 159
    for row in external['files']: verify(Path(row['resolvedPath']), row)
    targets = read(SOURCE / 'harness/targets.json')['targets']; log = (SOURCE / 'output.log').read_text()
    ok = [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')]
    details = dict(attempt=attempt, status=result['status'], counts=result['counts'], currentPass=result['currentPass'],
        elapsedSeconds=result['elapsedSeconds'], timeoutSeconds=180, projectFilesVerified=7060, frozenFilesVerified=7065,
        activeHarnessFilesVerified=6, externalFilesVerified=159)
    if group['testCount'] == 72:
        assert result['status'] == 'passed' and result['currentPass'] and result['exitCode'] == 0
        assert result['errors'] == result['childErrors'] == []
        assert result['counts'] == dict(testsRun=72, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
        actual = read(SOURCE / 'actual-tests.json'); assert actual['loaded'] == actual['executed'] == targets == ok
        match = re.search(r'Ran 72 tests in ([0-9.]+)s\n\nOK\n$', log); assert match
        origins = read(SOURCE / 'imports.json')
        assert origins['violations'] == origins['prohibitedAttempts'] == [] and origins['summary']['allOriginsMatched']
        for row in origins['records']:
            if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
        for name in ['compiler', 'driver']: assert read(SOURCE / (name + '-before.json')) == read(SOURCE / (name + '-after.json'))
        details.update(testSeconds=float(match.group(1)), actualOriginFileHashesRechecked=True, originSummary=origins['summary'],
            bytecodeReadsRefused=len(origins['deniedBytecodeReads']), compilerAndDriverStable=True, methodOrderVerified=True)
    else:
        assert result['status'] == 'timed_out' and result['currentPass'] is False and result['exitCode'] == -15 and result['counts'] is None
        assert result['signalsAttempted'] == ['terminate'] and len(result['errors']) == 2
        assert [(e['phase'], e['type']) for e in result['errors']] == [('execution', 'TimeoutError'), ('child-receipts', 'ValueError')]
        assert ok == targets[:37] and len(ok) == 37
        assert log.splitlines()[-1].endswith('test_namespace_expiry_precedes_permission_denial) ... ')
        absent = ['actual-tests.json', 'imports.json', 'test-return.json', 'child-errors.json', 'compiler-after.json', 'driver-after.json']
        assert all(not (SOURCE / name).exists() for name in absent)
        details.update(errors=result['errors'], childState='exited', exitCode=-15, loggedCompletedOkPrefix=37,
            nextLoggedMethod=targets[37], terminalMethodCountAvailable=False, actualOriginReceiptAvailable=False,
            compilerAndDriverFinalReceiptsAvailable=False, missingTerminalReceipts=absent)
    raw_before = read(SOURCE / 'raw-scratch-before.json'); raw = Path(result['scratchPath'])
    assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
    assert inventory(raw) == inventory(SOURCE / 'scratch') == read(SOURCE / 'scratch-index.json') == []
    before = inventory(SOURCE); shutil.copytree(SOURCE, OUT / attempt)
    assert inventory(OUT / attempt) == before == inventory(SOURCE)
    assert identity(raw) == raw_before['identity'] and not any(raw.iterdir())
    details.update(rawScratch=raw_before['identity'], rawScratchEmpty=True, rawScratchOriginalRetained=True, attemptFilesAcquired=len(before))
    proofs.append(details)

# Recheck the exact inherited fixture records against their original captures.
fixture_proofs = []
for group, source, digest, expected in [
    ('io-configuration', 'pat-io-configuration-capture/results/attempt01-passed32', 'ee98257543d28db76e77eed56f1b31f3a0934071e96492b3485551279fa6b122', (12, 1721, 504, 206)),
    ('io-active', 'pat-io-active-revocation/results/attempt01-passed38', 'a324f88d1425148f3913b0dc3ba3a19b6f99c55b53678e6a6edf68d5d1b1bbc3', (6, 608, 235, 92)),
    ('io-recovery', 'pat-io-pending-recovery/results/attempt01-passed46', '64f228609eb271c346ba18c4e4874e2417e032b9e30bf83e6498231cd738818b', (8, 823, 318, 136)),
]:
    prior = ROOT / 'artifacts/implementation' / source
    assert sha(prior / 'index.json') == digest
    frozen = {r['path']: r for r in read(prior / 'index.json')['files']}
    folder = SOURCE / 'project/tests/data' / group; catalog = read(folder / 'index.json')
    execution = configuration = snapshots = files = 0
    for fixture in catalog['fixtures']:
        original = prior / 'attempt/scratch' / fixture['method']
        copied = folder / fixture['method']; manifest = read(copied / 'manifest.json')
        p = original / 'engine-0.json'; verify(p, frozen[p.relative_to(prior).as_posix()])
        assert sha(p) == sha(copied / 'manifest.json'); files += 1
        for directory, refs in [('records', manifest['records']), ('configuration', manifest['configuration']['records'])]:
            for row in refs:
                p = original / 'trial-0' / directory / row['path']
                verify(p, frozen[p.relative_to(prior).as_posix()]); verify(p, row); verify(copied / directory / row['path'], row)
                files += 1
        execution += len(manifest['records']); configuration += len(manifest['configuration']['records'])
        snapshots += len(manifest['configuration']['snapshots'])
    assert (len(catalog['fixtures']), execution, configuration, snapshots) == expected
    fixture_proofs.append(dict(group=group, sourceIndexSha256=digest, fixtures=expected[0], executionRecords=execution,
                               configurationRecords=configuration, snapshots=snapshots, exactFilesReverified=files))


shutil.copyfile(plan_path, OUT / 'selection-plan.json'); assert sha(OUT / 'selection-plan.json') == sha(plan_path)
proof = dict(scope='Actual passing regression72 and terminated refusal56 attempts. No complete 128-method pass is established here.',
    allSelectionsPassed=False, attempts=proofs, preparationSeals=seals, selectionPlanSha256=sha(plan_path),
    inheritedInputsUnchanged=7056, changedInheritedInputs=sorted(changes), fixtureProvenance=fixture_proofs,
    independentReview=False, configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
    staticTimingPolicyChecked=False, allFaultScenariosChecked=False, independentOutcomeChecked=False, qualificationPassed=False,
    limitations=['The 56-method child reached its actual execution deadline and was terminated; final counts/origin receipts are absent.',
        'Thirty-seven logged ok completions are partial text evidence, not a terminal suite verdict.',
        'Original source, both harnesses, complete attempts and original empty scratch roots remain preserved.',
        'The unexecuted acquire.py expected terminal test receipts and was superseded by this terminal-state acquisition without deleting it.',
        'No Runtime, SQL connection, physical device, MCU/emulator, inference, public service or live source change.'])
with (OUT / 'proof.json').open('x') as stream: stream.write(json.dumps(proof, indent=2) + '\n')
print(json.dumps(dict(allSelectionsPassed=False, attempts=[dict(attempt=p['attempt'], status=p['status'], acquiredFiles=p['attemptFilesAcquired']) for p in proofs],fixtureFiles=sum(p['exactFilesReverified'] for p in fixture_proofs))))
