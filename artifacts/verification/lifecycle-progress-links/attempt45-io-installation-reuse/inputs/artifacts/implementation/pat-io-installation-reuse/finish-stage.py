"""Seal exact regression evidence after quiescence, audits and link verification."""
import hashlib
import json
import shutil
import stat
from pathlib import Path

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-installation-reuse'; R = B / 'results'
O = ROOT / 'artifacts/implementation/pat-io-supervision-recovery'
D = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt45-io-installation-reuse'
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

pins = [
    '48f4d00693b875d74c3260c3bbf99e9f1e82cb4e98a2f0a8ab5373320fa23656',
    'ec7d5fad6fe6a30ffef76e79624ed669180e174d60eed6d9fc8a9bdaaaebab2c',
    '1401e3e9e098319331d6d3587421de406bbedfa317a8995be2b7806e76d27b32',
    'ec43699a119c4bbc69c4c380847ab7dbc88b127bd8448dde1da3a6427e3d3a09',
    '4e2e586f0f487b1d9c54113f59989f0ca67c3b79e200569249ca6de4b588cb0c',
    '9dc2fda001ff397b66c9b0c7a5540b0c027cf4b678187e78cf6284cb3173586b',
    '61586547d7455d5f541a00a67573e38abc5db76fa0d80956a1bda805b8c6454b',
    '275dfc8dc8a8ea058299892ca7121f6d8f25bc037605dcba2404ca373c21d404',
    '66cfa75bd8b7db45000a2e0ef2efb5eadb5e6ea7f0f89a0d55eaa9afbcd813e0',
    '614af065b9b076a3b9b2df3248953d0dd8fbf18b8f0f7588a0df0b7d6a184a12',
]
entries = [(O / 'implementation01', 'd1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c', True),
           (B / 'implementation01', '0d4f87812d08c1ee4494cfa3e9ee117c0aca7b69827761e2a5053523c77622f8', True),
           (O / 'results', 'a6fa56b9d35af5c9b6b29a0c00eea5f3f0ef3ec8d0045a9b2d132a583fe4d3a4', False)]
entries += [(B / ('harness%02d' % number), pin, False) for number, pin in enumerate(pins, 1)]
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
assert len(base) == 239 and changed == ['hms/synthetic_io_installation.py']
analysis = read(B / 'RESULTS.json'); assert analysis['goalStatus'] == 'active' and len(analysis['attempts']) == 10
assert analysis['distinctTestedMethods'] == 194 and analysis['liveAuthorityCached'] is False
originals = {}; identities = {}; executed = set()
for item in analysis['attempts']:
    F = R / item['destination']; A = F / 'attempt'; proof = read(F / 'proof.json'); result = read(A / 'result.json'); H = B / proof['harness']
    assert proof['status'] == result['status'] == item['status'] and proof['counts'] == result['counts'] == item['counts']
    assert result['childState'] == 'exited' and not (Path('/proc') / str(result['pid'])).exists()
    assert result['errors'] == result['childErrors'] == []
    targets = read(H / 'targets.json')['targets']; actual = read(A / 'actual-tests.json')
    assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
    assert not executed.intersection(targets); executed.update(targets)
    for prefix, folder, size in [('inputs', A / 'project', 240), ('frozen', ROOT, 243), ('harness', A / 'harness', 6)]:
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
assert len(executed) == 194
report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
rows = inventory(R); write(R / 'index.json', dict(scope='Pure normalization reuse regression evidence; historical failures preserved, full goal active.', files=rows))
counts[R.relative_to(ROOT).as_posix()] = len(rows); entries.append((R, sha(R / 'index.json'), False))
D.mkdir(); names = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'scripts/check_project_links.py', 'artifacts/verification/project-links.json', 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names += [path.relative_to(ROOT).as_posix() for path in sorted(B.iterdir()) if path.is_file() and path.suffix in ('.md', '.py', '.json', '.patch', '.log')]
names += [(folder / 'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries]
assert len(names) == len(set(names)); copies = []
for name in names:
    source = ROOT / name; dest = D / 'inputs' / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
    row = dict(source=name, copy=dest.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source)); verify(dest, row); copies.append(row)
write(D / 'index.json', dict(scope='Pure installation memo and exact194-method regression; goal active, no physical/public qualification.', distinctTestedMethods=analysis['distinctTestedMethods'], distinctPassingMethods=analysis['distinctPassingMethods'], currentNominalPwmAndArchiveCommitPass=analysis['currentNominalPwmAndArchiveCommitPass'], historicalFailuresPreserved=True, markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[], originalAttemptFilesReverified=originals, artifactEntriesReverified=counts, reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(resultsFiles=len(rows), resultsIndexSha256=sha(R / 'index.json'), documentIndexSha256=sha(D / 'index.json'), documentCopies=len(copies), artifactEntriesReverified=sum(counts.values()), markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'])))
