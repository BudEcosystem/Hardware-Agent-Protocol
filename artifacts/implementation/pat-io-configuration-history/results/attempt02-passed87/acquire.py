"""One-shot standard-library acquisition; no project import or test execution."""
from pathlib import Path
import hashlib
import json
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-configuration-history'
SOURCE = BASE / 'harness02/attempts/attempt02-configuration87'
OUT = BASE / 'results/attempt02-passed87'


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
    ('implementation02', '55e0ac491f54e7af6f05467bf7ad8eb6be4ce0633d910224b2b6b66e07569f29', True),
    ('harness02', 'c65c1bec46c2a74791cac7f94d64f38df46ffb35a630a86ceb7647c07937f271', False),
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
assert result['counts'] == dict(testsRun=87, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
for name, base, count in [('inputs', SOURCE / 'project', 5050), ('frozen', ROOT, 5054), ('harness', SOURCE / 'harness', 6)]:
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
assert actual['loaded'] == actual['executed'] == selection and len(selection) == 87
log = (SOURCE / 'output.log').read_text()
import re
match = re.search(r'Ran 87 tests in ([0-9.]+)s\n\nOK\n$', log)
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
capture = ROOT / 'artifacts/implementation/pat-io-configuration-capture/results/attempt01-passed32'
assert sha(capture/'index.json') == 'ee98257543d28db76e77eed56f1b31f3a0934071e96492b3485551279fa6b122'
capture_rows = read(capture/'index.json')['files']
for row in capture_rows: verify(capture/row['path'],row)
new_fixtures = SOURCE/'project/tests/data/io-configuration'
new_catalog = read(new_fixtures/'index.json')
assert len(new_catalog['fixtures']) == 12 and len(new_catalog['files']) == 2237
for row in new_catalog['files']:
    verify(ROOT/row['source'],row); verify(new_fixtures/row['copy'],row)
assert sum(f['records'] for f in new_catalog['fixtures']) == 1721
assert sum(f['configurationRecords'] for f in new_catalog['fixtures']) == 504
failed = BASE/'results/attempt01-failed87'
assert sha(failed/'index.json') == 'ae67829818b7fff4a6347d4a1fd0bd3c9137dcc72d8b07f59e52b32e509fbd28'
failed_rows = read(failed/'index.json')['files']
for row in failed_rows: verify(failed/row['path'],row)
raw_before = read(SOURCE / 'raw-scratch-before.json')
raw = Path(result['scratchPath'])
assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
assert inventory(raw) == inventory(SOURCE / 'scratch') == read(SOURCE / 'scratch-index.json') == []
before = inventory(SOURCE)
shutil.copytree(SOURCE, OUT / 'attempt')
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)
assert identity(raw) == raw_before['identity'] and not any(raw.iterdir())
proof = {'scope':'Actual pure configuration87 run: 48 configuration/permission methods and all39 transcript regressions; no new runtime/effect execution.',
    'counts':result['counts'],'testSeconds':test_seconds,'elapsedSeconds':result['elapsedSeconds'],
    'projectFilesVerified':5050,'frozenFilesVerified':5054,'activeHarnessFilesVerified':6,'externalFilesVerified':159,
    'preparationSeals':seals,'originSummary':origins['summary'],'actualOriginFileHashesRechecked':True,
    'bytecodeReadsRefused':len(origins['deniedBytecodeReads']),'compilerAndDriverStable':True,'methodOrderAndLogVerified':True,
    'trial20ResultFilesReverified':len(history),'configuration32ResultFilesReverified':len(capture_rows),
    'failed87ResultFilesReverified':len(failed_rows),'exactLegacyFixtureStates':19,'exactLegacyFixtureRecords':fixture_records,
    'exactConfigurationFixtureStates':12,'exactConfigurationFixtureFiles':2237,'configurationSnapshotsAssertedInProcess':206,
    'configurationRecordsAssertedInProcess':504,'executionRecordsInConfigurationFixtures':1721,
    'decisionsAssertedInProcess':dict(namespaces=12,parents=11,parentSteps=27,admissions=21,dispatches=20,parentRefusals=1,dispatchRefusals=1),
    'rawScratch':raw_before['identity'],'rawScratchEmpty':True,'rawScratchOriginalRetained':True,
    'attemptFilesAcquired':len(before),'independentReview':False,'configurationAttested':False,'compilerIdentityAttested':False,
    'activeRevocationChecked':False,'observationSampleSemanticsChecked':False,'independentOutcomeChecked':False,'qualificationPassed':False,
    'limitations':['Trusted grant plans required separately; captured permissions do not authorize themselves.',
        'Finite immutable installation and new authorization decisions only; active permission withdrawal refuses.',
        'Observation provenance/order checked, intermediate sample semantics not reconstructed.',
        'No independent current compiler identity, complete timing/fault/auxiliary-actor composition, storage enforcement or public qualification.',
        'Pure checks are in-process assertions over retained data, not a standalone complete outcome verdict.',
        'No live integration, hardware, MCU/emulator, live inference or new Runtime execution.']}
with (OUT/'proof.json').open('x') as stream: stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'attemptFiles':len(before),'configurationFixtureFiles':2237,'counts':result['counts'],
                  'priorFilesReverified':len(history)+len(capture_rows)+len(failed_rows)}))
