"""One-shot standard-library retention of the actual observation27 attempt."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-observation-history'
SOURCE = BASE / 'harness01/attempts/attempt01-observation27'
OUT = BASE / 'results/attempt01'


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


seals = []
for folder, expected, rooted in [
    (BASE / 'implementation01', 'df4991717a44ead0f2065a649afefe77822cca00352b54ee72add4deef996c20', True),
    (BASE / 'harness01', '3efca182190e3a9db1b366c8044953d46a4c020e9eae098294395abfdd80b129', False),
    (ROOT / 'artifacts/implementation/pat-io-recovery-history/implementation01', '22f828d8ff40458ea657baa361a755199545cf4dbc3231ac088d7b10323e1baf', True),
]:
    assert sha(folder / 'index.json') == expected
    rows = read(folder / 'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder) / row['path'], row)
    seals.append(dict(path=(folder / 'index.json').relative_to(ROOT).as_posix(), sha256=expected, filesVerified=len(rows)))
baseline = read(BASE / 'implementation01/baseline-inputs.json')
assert baseline['sourceIndexSha256'] == seals[-1]['sha256'] and len(baseline['inheritedProjectInputs']) == 7056
old_project = ROOT / 'artifacts/implementation/pat-io-recovery-history/implementation01/project'
for row in baseline['inheritedProjectInputs']:
    verify(BASE / 'implementation01/project' / (ROOT / row['path']).relative_to(old_project), row)

result = read(SOURCE / 'result.json')
assert result['childState'] == 'exited' and result['errors'] == result['childErrors'] == []
assert not Path('/proc/' + str(result['pid'])).exists() and result['timeoutSeconds'] == 180
for prefix, base, count in [('inputs', SOURCE / 'project', 7058), ('frozen', ROOT, 7061), ('harness', SOURCE / 'harness', 6)]:
    rows = read(SOURCE / (prefix + '-before.json'))
    assert rows == read(SOURCE / (prefix + '-after.json')) and len(rows) == count
    for row in rows: verify(base / row['path'], row)
external = read(SOURCE / 'external-before.json')
assert external == read(SOURCE / 'external-after.json') and len(external['files']) == 159
for row in external['files']: verify(Path(row['resolvedPath']), row)
origins = read(SOURCE / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == [] and origins['summary']['allOriginsMatched']
assert len(origins['records']) == origins['summary']['recordCount']
for row in origins['records']:
    if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
for name in ['compiler', 'driver']:
    assert read(SOURCE / (name + '-before.json')) == read(SOURCE / (name + '-after.json'))
selection = read(SOURCE / 'harness/targets.json')['targets']; actual = read(SOURCE / 'actual-tests.json')
assert actual['loaded'] == actual['executed'] == selection and len(selection) == len(set(selection)) == 27
log = (SOURCE / 'output.log').read_text()
match = re.search(r'Ran 27 tests in ([0-9.]+)s\n\n(?:OK|FAILED[^\n]*)\n$', log)
assert match is not None
counts = result['counts']; assert counts['testsRun'] == 27
passed = all(counts[key] == 0 for key in counts if key != 'testsRun')
assert passed == result['currentPass'] == (result['exitCode'] == 0)
if passed:
    assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')] == selection

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

raw_before = read(SOURCE / 'raw-scratch-before.json'); raw = Path(result['scratchPath'])
assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
assert inventory(raw) == inventory(SOURCE / 'scratch') == read(SOURCE / 'scratch-index.json') == []
before = inventory(SOURCE); shutil.copytree(SOURCE, OUT / 'attempt')
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)
assert identity(raw) == raw_before['identity'] and not any(raw.iterdir())
proof = dict(scope='Actual focused observation27 pure attempt; inherited136 result remains historical.',
    currentPass=passed, counts=counts, testSeconds=float(match.group(1)), elapsedSeconds=result['elapsedSeconds'],
    projectFilesVerified=7058, frozenFilesVerified=7061, inheritedInputsUnchanged=7056,
    activeHarnessFilesVerified=6, externalFilesVerified=159, preparationSeals=seals,
    originSummary=origins['summary'], actualOriginFileHashesRechecked=True,
    bytecodeReadsRefused=len(origins['deniedBytecodeReads']), compilerAndDriverStable=True,
    methodOrderVerified=True, fixtureProvenance=fixture_proofs, rawScratch=raw_before['identity'],
    rawScratchEmpty=True, rawScratchOriginalRetained=True, attemptFilesAcquired=len(before),
    independentReview=False, configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
    staticTimingPolicyChecked=False, allFaultScenariosChecked=False, independentOutcomeChecked=False, qualificationPassed=False,
    limitations=['Finite immutable simulation counter samples only; not measured electrical state or task success.',
        'Sample component does not attest full operation/parent history; full composition preserves two permission-refusal limitations.',
        'No Runtime, SQL connection, physical device, MCU/emulator, live inference, public service or live source integration.',
        'Current compiler identity, wider fault/timing coverage, aggregate storage and public qualification remain incomplete.'])
if passed:
    proof['sampleAssertionsPassed'] = dict(fixtures=26, snapshots=434, producedSamples=1288, driveRefreshes=134,
        initialBatches=26, reopenBatches=1, cachedSnapshots=273, laggingSnapshots=72, valueReadings=1736)
with (OUT / 'proof.json').open('x') as stream: stream.write(json.dumps(proof, indent=2) + '\n')
print(json.dumps(dict(currentPass=passed, counts=counts, acquiredFiles=len(before), fixtureFiles=sum(p['exactFilesReverified'] for p in fixture_proofs))))
