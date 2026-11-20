"""Seal original controls, process failures, regressions and current documents."""
import ast
import copy
import hashlib
import json
import shutil
import stat
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-document-validation'
R = B/'results'
OLD = ROOT/'artifacts/implementation/pat-io-service-runs'
SCPI = ROOT/'research/instrumentation/scpi-parameters-followup'
D = ROOT/'artifacts/verification/lifecycle-progress-links/attempt49-io-document-validation'
PIN = '31118f7405fcce5f4828bf4d256faea21e61b6d5bae470632376d9c8c484c4c0'
assert not (R/'index.json').exists() and not D.exists()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')

def verify(path, row):
    assert not path.is_symlink() and path.is_file()
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)

def inventory(folder):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row:row['path'])

def identity(path):
    info = path.lstat()
    assert stat.S_ISDIR(info.st_mode)
    return dict(path=str(path), device=info.st_dev, inode=info.st_ino, uid=info.st_uid,
                gid=info.st_gid, mode=stat.S_IMODE(info.st_mode))

entries = [(OLD/'implementation01', '8086023d524443fb617b654ad7573f1ef25a7388e12f991d28457457a720ba8d', True),
           (B/'implementation01', PIN, True),
           (SCPI, '4454691c4e9ccfed0776e12d7e3aaa090c723bfd93f944e94262919161f2e13b', False)]
assert sha(OLD/'results/index.json') == '15116241febffbf79fe7d56278f1dcc77ce20c9ad62f38ac3f7ccddca70a4fe1'
for number in range(1, 18):
    harness = B/('harness%02d'%number)
    assert read(harness/'review.json')['sourceIndexSha256'] == PIN
    entries.append((harness, sha(harness/'index.json'), False))
assert sha(B/'harness17/index.json') == '365338258f92cc408d143f210c9e54b39eeb760e7a96bb4cb7764fd71d395af0'
counts = {}
for folder, pin, rooted in entries:
    assert sha(folder/'index.json') == pin
    rows = read(folder/'index.json')['files']
    for row in rows:
        verify((ROOT if rooted else folder)/row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(rows)

baseline = read(B/'implementation01/baseline-inputs.json')['inheritedProjectInputs']
changed = []
for row in baseline:
    relative = (ROOT/row['path']).relative_to(OLD/'implementation01/project')
    if sha(B/'implementation01/project'/relative) != row['sha256']:
        changed.append(relative.as_posix())
assert len(baseline) == 246 and changed == ['hms/pat_io_configuration_capture.py']
old = ast.parse((OLD/'implementation01/project'/changed[0]).read_bytes())
new = ast.parse((B/'implementation01/project'/changed[0]).read_bytes())
old_class = next(node for node in old.body if isinstance(node,ast.ClassDef))
new_class = next(node for node in new.body if isinstance(node,ast.ClassDef))
old_method = next(node for node in old_class.body if isinstance(node,ast.FunctionDef) and node.name == '_configuration_table')
new_method = next(node for node in new_class.body if isinstance(node,ast.FunctionDef) and node.name == '_configuration_table')
old_cell = next(node for node in old_method.body if isinstance(node,ast.FunctionDef) and node.name == 'cell')
new_method.body = [copy.deepcopy(old_cell) if isinstance(node,ast.FunctionDef) and node.name == 'cell' else node for node in new_method.body]
new.body = [node for node in new.body if not (isinstance(node,ast.ImportFrom) and node.module == 'pat_io_canonical_blobs')]
assert ast.dump(old,include_attributes=False) == ast.dump(new,include_attributes=False)

analysis = read(B/'RESULTS.json')
assert analysis['goalStatus'] == 'active' and len(analysis['attempts']) == 17
assert analysis['selectedDistinctMethods'] == analysis['distinctTestedMethods'] == 298
assert analysis['totalMethodExecutions'] == 298 and analysis['unexecutedMethods'] == []
assert analysis['reservationControlsVerified'] and analysis['reservedWorkerEndToEndVerified']
assert analysis['canonicalControlsVerified'] and analysis['postWorkerConfigurationSessionReplayVerified']
assert analysis['canonicalControlMethods'] == 19 and analysis['allControlMethods'] == 286
assert not analysis['deploymentDeadlineGuarantee']
assert not analysis['publicServiceMounted'] and analysis['retainedFailedAttempts'] >= 2
passed, tested, originals = set(), set(), {}
identities = {}
for item in analysis['attempts']:
    folder = R/item['destination']
    attempt = folder/'attempt'
    proof, result = read(folder/'proof.json'), read(attempt/'result.json')
    harness = B/proof['harness']
    assert proof['status'] == result['status'] == item['status']
    assert proof['counts'] == result['counts'] == item['counts']
    assert result['childState'] == 'exited' and not (Path('/proc')/str(result['pid'])).exists()
    assert result['errors'] == result['childErrors'] == []
    assert proof['harnessIndexSha256'] == sha(harness/'index.json') and proof['sourceIndexSha256'] == PIN
    targets = read(harness/'targets.json')['targets']
    actual = read(attempt/'actual-tests.json')
    assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
    tested.update(targets)
    if proof['status'] == 'passed':
        assert not passed.intersection(targets)
        passed.update(targets)
    for prefix, directory, size in [('inputs', attempt/'project', 248), ('frozen', ROOT, 251), ('harness', attempt/'harness', 6)]:
        rows = read(attempt/(prefix+'-before.json'))
        assert rows == read(attempt/(prefix+'-after.json')) and len(rows) == size
        for row in rows:
            verify(directory/row['path'], row)
    external = read(attempt/'external-before.json')
    assert external == read(attempt/'external-after.json') and len(external['files']) == 159
    for row in external['files']:
        verify(Path(row['resolvedPath']), row)
    origins = read(attempt/'imports.json')
    assert origins['summary']['allOriginsMatched'] and origins['violations'] == origins['prohibitedAttempts'] == []
    for row in origins['records']:
        if 'sha256' in row:
            assert sha(Path(row['origin'])) == row['sha256']
    for label in ('compiler', 'driver'):
        value = read(attempt/(label+'-before.json'))
        assert value == read(attempt/(label+'-after.json'))
        if label in identities:
            assert value == identities[label]
        else:
            identities[label] = value
    raw = Path(proof['rawScratch']['path'])
    assert identity(raw) == proof['rawScratch']
    assert identity(raw.parent) == read(attempt/'raw-scratch-before.json')['parent']
    rows = inventory(raw)
    assert rows == inventory(attempt/'scratch') == read(attempt/'scratch-index.json')
    assert len(rows) == proof['rawScratchFiles']
    assert sum(row['bytes'] for row in rows) == proof['rawScratchBytes'] <= read(harness/'review.json')['scratchBytesCeiling']
    assert len(read(attempt/'sqlite-connections.json')) == proof['sqliteConnections'] == item['parentSqliteConnections']
    original = harness/'attempts'/proof['attempt']
    rows = inventory(original)
    assert rows == inventory(attempt) and len(rows) == proof['attemptFilesAcquired']
    originals[item['destination']] = len(rows)
    assert read(folder/'storage-audit.json')['databaseBytesUnchanged']
    if item['counts']['testsRun'] == 1:
        quiet = read(attempt/'writer-quiescence.json')
        assert quiet['ownerQuiescent'] and len(quiet['records']) == 1
        assert quiet['records'][0].get('writerQuiescent') or quiet['records'][0].get('launchIntentAbsent')
        process = read(folder/item['processAudit'])
        assert process['ledgerUnchanged'] and not process['qualificationPassed']
        assert process['archive']['unresolvedEffects'] is None
        if item['status'] == 'failed':
            assert (process.get('preCrashReason', process['archive']['supervisorReason']) in {'SUPERVISOR_DEADLINE', 'SUPERVISOR_RETENTION_UNKNOWN'}
                    or process.get('workerFailureCode') == 'PAT_IO_GROUP_WALL_LIMIT')
            assert not process['archive']['transportComplete']
        elif process['groupStatus'] == 'captured':
            assert process['codeImageExactClosure'] and process['codeImageFiles'] == 260
            assert process['completedCases'] == 30 and process['states'] == 26
            assert process['claims'] == process['owners'] == 0
            assert process['effects'] == dict(activations=21, completed=11, canceled=10)
assert len(tested) == 298 and len(passed) == analysis['distinctPassingMethods']
for destination, runs, documents in [('attempt06-passed-runs15', 9, 333), ('attempt07-passed-runs14', 6, 222),
                                     ('attempt03-passed-reserved-owned', 1, 37)]:
    run = read(R/destination/'run-audit.json')
    assert run['validatedRuns'] == runs and run['validatedDocuments'] == documents
    assert run['allDatabasesUnchanged'] and run['sourceAuthorityEffectsZero']
canonical = read(R/'attempt01-passed-canonical19/canonical-control-audit.json')
assert canonical['tests'] == 19 and canonical['sqliteConnections'] == 0
assert canonical['observation']['originalFullValidations'] == 1000
assert canonical['observation']['reuseFullValidations'] == 1
assert canonical['noFailedWriteRepair'] and not canonical['deploymentLatencyQualified']
report = read(ROOT/'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:
    assert sha(ROOT/row['path']) == row['sha256']

rows = inventory(R)
write(R/'index.json', dict(scope='Exact298-method candidate, reduced pure validation work, reserved-worker pass and retained deadline/retention failures; full goal active.', files=rows))
counts[R.relative_to(ROOT).as_posix()] = len(rows)
entries.append((R, sha(R/'index.json'), False))
D.mkdir()
names = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'docs/instrumentation-bindings.md',
         'research/PLAN.md', 'research/instrumentation/README.md', 'scripts/check_project_links.py',
         'artifacts/verification/project-links.json', 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names.extend(path.relative_to(ROOT).as_posix() for path in sorted(B.iterdir()) if path.is_file() and path.suffix in ('.md', '.py', '.json', '.patch', '.log'))
names.extend(path.relative_to(ROOT).as_posix() for path in sorted((B/'analysis').iterdir()) if path.is_file())
names.extend(path.relative_to(ROOT).as_posix() for path in sorted(SCPI.iterdir()) if path.is_file() and path.name != 'index.json')
names.extend((folder/'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries)
assert len(names) == len(set(names))
copies = []
for name in names:
    source, destination = ROOT/name, D/'inputs'/name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    row = dict(source=name, copy=destination.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source))
    verify(destination, row)
    copies.append(row)
write(D/'index.json', dict(scope='Exact-byte validation controls, complete reserved-worker scenario, retained process failures and partial SCPI parameter reading. Full goal active.',
    distinctTestedMethods=298, distinctPassingMethods=len(passed), reservedWorkerEndToEndVerified=True,
    publicServiceMounted=False, historicalFailuresPreserved=True, scpiCoveredLines=2780, scpiCoverageComplete=False,
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[],
    originalAttemptFilesReverified=originals, artifactEntriesReverified=counts,
    reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(resultsFiles=len(rows), resultsIndexSha256=sha(R/'index.json'),
    documentIndexSha256=sha(D/'index.json'), documentCopies=len(copies),
    artifactEntriesReverified=sum(counts.values()), markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'])))
