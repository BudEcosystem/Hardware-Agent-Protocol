"""Seal exact regression evidence after quiescence, audits and link verification."""
import hashlib
import json
import shutil
import stat
from pathlib import Path

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-service-config'; R = B / 'results'
O = ROOT / 'artifacts/implementation/pat-io-installation-reuse'
D = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt46-io-service-config'
assert not (R / 'index.json').exists() and not D.exists()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
def verify(path, row):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)
def inventory(folder):
    rows = []
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file(): rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return sorted(rows, key=lambda row: row['path'])
def identity(path):
    value = path.lstat(); assert stat.S_ISDIR(value.st_mode)
    return dict(path=str(path), device=value.st_dev, inode=value.st_ino, uid=value.st_uid, gid=value.st_gid, mode=stat.S_IMODE(value.st_mode))

pins = ['4568504bbb6c6e9156749644bfeee02b61e2e5d2d753a404aa070a7dd6974e31', '657a640faf3ccfae937533f9c45655bd170b412a3024ea63fba62fe8ad5584c9', 'f887a576b2d20884bf2204dbdcb5343978087eaea2fcfcd95c70aa5e3ec24eec', '07f87f9fba405ca2970f64f32888ce53b73e5a6997e2831e8dc02a3f55df0ead', '827db14f74b3fab86c250cd8d5a8ba60a792fca006ea2fb00043b74387ce1482', '0f38e29357ea9d6e77ec6a9101a748d1a2a2a2bbd1ec149168c0edc88bc7d212', '5d2bdacd5bf665b57af81ad60c95bc08fa80caf3faf6d0c8dc7e101b63fb5a19', '45a646a4c7993415d188a8501e70ca5fa8df9eda1622ac8a7162d28dc7d4226d', 'c0221af9afdba25744d2cc76befd2ded08e844ad058381cf715933e63ce261c8', '265ef7a458947b782e07dac77ee9045ba27536a8d9d896e82711f80870f63dc4', '18333437df316cc76371d2ad903bca65d5b47fc5577334c3f866e7d5a8b7f0be']
entries = [(O / 'implementation01', '0d4f87812d08c1ee4494cfa3e9ee117c0aca7b69827761e2a5053523c77622f8', True),
           (B / 'implementation01', 'a242d84d16919fe15da783397642d1ae7ed9b07cc14a4a5ce1de78ebabae3f65', True),
           (O / 'results', 'ab0a28ddce26af74537f62dd63b080d673bdbcd16944348d42dc3ef24e97fee5', False)]
entries += [(B / ('harness%02d' % number), pin, False) for number, pin in enumerate(pins, 1)]
entries.append((ROOT / 'artifacts/implementation/pat-io-supervision-recovery/results', 'a6fa56b9d35af5c9b6b29a0c00eea5f3f0ef3ec8d0045a9b2d132a583fe4d3a4', False))
counts = {}
for folder, pin, rooted in entries:
    assert sha(folder / 'index.json') == pin
    rows = read(folder / 'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder) / row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(rows)
base = read(B / 'implementation01/baseline-inputs.json')['inheritedProjectInputs']; changed = []
for row in base:
    relative = (ROOT / row['path']).relative_to(O / 'implementation01/project')
    if sha(B / 'implementation01/project' / relative) != row['sha256']: changed.append(relative.as_posix())
assert len(base) == 240 and changed == ['supervisor/supervisor_contracts.py']
analysis = read(B / 'RESULTS.json'); assert analysis['goalStatus'] == 'active' and len(analysis['attempts']) == 11
assert analysis['distinctTestedMethods'] == 216 and analysis['productionAuthorityConfigurationInstalled'] is False
originals = {}; identities = {}; executed = set()
for item in analysis['attempts']:
    F = R / item['destination']; A = F / 'attempt'; proof = read(F / 'proof.json'); result = read(A / 'result.json'); H = B / proof['harness']
    assert proof['status'] == result['status'] == item['status'] and proof['counts'] == result['counts'] == item['counts']
    assert result['childState'] == 'exited' and not (Path('/proc') / str(result['pid'])).exists()
    assert result['errors'] == result['childErrors'] == []
    targets = read(H / 'targets.json')['targets']; actual = read(A / 'actual-tests.json')
    assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
    assert not executed.intersection(targets); executed.update(targets)
    for prefix, folder, size in [('inputs', A / 'project', 242), ('frozen', ROOT, 245), ('harness', A / 'harness', 6)]:
        rows = read(A / (prefix + '-before.json')); assert rows == read(A / (prefix + '-after.json')) and len(rows) == size
        for row in rows: verify(folder / row['path'], row)
    external = read(A / 'external-before.json'); assert external == read(A / 'external-after.json') and len(external['files']) == 159
    for row in external['files']: verify(Path(row['resolvedPath']), row)
    origins = read(A / 'imports.json'); assert origins['summary']['allOriginsMatched'] and origins['violations'] == origins['prohibitedAttempts'] == []
    for row in origins['records']:
        if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
    for label in ('compiler', 'driver'):
        value = read(A / (label + '-before.json')); assert value == read(A / (label + '-after.json'))
        if label in identities: assert value == identities[label]
        else: identities[label] = value
    raw = Path(proof['rawScratch']['path']); assert identity(raw) == proof['rawScratch']
    assert identity(raw.parent) == read(A / 'raw-scratch-before.json')['parent']
    rows = inventory(raw); assert rows == inventory(A / 'scratch') == read(A / 'scratch-index.json') and len(rows) == proof['rawScratchFiles']
    assert sum(row['bytes'] for row in rows) == proof['rawScratchBytes'] <= read(H / 'review.json')['scratchBytesCeiling']
    assert len(read(A / 'sqlite-connections.json')) == proof['sqliteConnections'] == item['parentSqliteConnections']
    original = H / 'attempts' / proof['attempt']; rows = inventory(original)
    assert rows == inventory(A) and len(rows) == proof['attemptFilesAcquired']; originals[item['destination']] = len(rows)
    storage = read(F / 'storage-audit.json'); assert storage['databaseBytesUnchanged']
    if H.name == 'harness01':
        control = read(F / 'control-audit.json'); assert control['databasesUnchanged'] and not control['corruptStateRepaired']
        assert len(control['corruptRecords']) == 11 and len(control['unknownLeases']) == len(control['malformedReturns']) == 3
    else:
        quiescence = read(A / 'writer-quiescence.json'); assert quiescence['ownerQuiescent'] and len(quiescence['records']) == 1
        q = quiescence['records'][0]; assert q.get('writerQuiescent') or q.get('launchIntentAbsent')
        if proof['status'] == 'passed':
            process = read(F / 'process-audit.json'); assert process['ledgerUnchanged'] and not process['qualificationPassed']
            assert process['archive']['unresolvedEffects'] is None
            if process['groupStatus'] == 'captured':
                assert process['codeImageExactClosure'] and process['completedCases'] == 30 and process['states'] == 26
                assert process['claims'] == process['owners'] == 0
        else: assert read(F / 'failure-audit.json')['qualificationPassed'] is False
assert len(executed) == 216
configured = next(item for item in analysis['attempts'] if item['harness'] == 'harness11')
if configured['status'] == 'passed':
    joined = read(R / configured['destination'] / 'service-audit.json')
    assert joined['ledgerUnchanged'] and joined['sourceImageFiles'] == 257 and joined['completeCases'] == 30
    assert joined['configurationPersistedByProductionAuthority'] is False

report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
rows = inventory(R); write(R / 'index.json', dict(scope='Trusted service configuration and exact regression evidence; full goal active.', files=rows))
counts[R.relative_to(ROOT).as_posix()] = len(rows); entries.append((R, sha(R / 'index.json'), False))
D.mkdir(); names = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'scripts/check_project_links.py', 'artifacts/verification/project-links.json', 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names += [path.relative_to(ROOT).as_posix() for path in sorted(B.iterdir()) if path.is_file() and path.suffix in ('.md', '.py', '.json', '.patch', '.log')]
names += [(folder / 'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries]
assert len(names) == len(set(names)); copies = []
for name in names:
    source = ROOT / name; dest = D / 'inputs' / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
    row = dict(source=name, copy=dest.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source)); verify(dest, row); copies.append(row)
write(D / 'index.json', dict(scope='Trusted configuration and exact216-method regression; goal active, no authority installation or physical/public qualification.', distinctTestedMethods=analysis['distinctTestedMethods'], distinctPassingMethods=analysis['distinctPassingMethods'], configuredGroupPass=analysis['configuredGroupPass'], historicalFailuresPreserved=True, markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[], originalAttemptFilesReverified=originals, artifactEntriesReverified=counts, reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(resultsFiles=len(rows), resultsIndexSha256=sha(R / 'index.json'), documentIndexSha256=sha(D / 'index.json'), documentCopies=len(copies), artifactEntriesReverified=sum(counts.values()), markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'])))
