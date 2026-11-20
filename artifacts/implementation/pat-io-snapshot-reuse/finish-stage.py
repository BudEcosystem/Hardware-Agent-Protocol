"""Seal complete current groups, independent checks and the preserved test failure."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-snapshot-reuse'; R = B / 'results'
D = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt40-snapshot-reuse'
assert not (R / 'index.json').exists() and not D.exists()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, v):
    with p.open('x') as f: f.write(json.dumps(v, indent=2) + '\n')
def verify(p, r):
    assert not p.is_symlink() and p.is_file() and p.stat().st_size == r['bytes'] and sha(p) == r['sha256'], str(p)
def inventory(folder):
    rows = []
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file(): rows.append(dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    return rows
def identity(p):
    s = p.lstat(); assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p), device=s.st_dev, inode=s.st_ino, uid=s.st_uid, gid=s.st_gid, mode=stat.S_IMODE(s.st_mode))

source_pins = ('121d71b66df982c9c0a530a56f5cea200b67339284fadd152e2e399e5aae58e3',
    '994feaf97781c64c8bc4b236bf426a7b29ff051eac798616d07bc0128d6ea306')
pins = ('7b0ec4096a6f48506d8c8f333da7d3c3f0728fdfd0928e4f68dc22b259913f43',
    '2b6e9a9dce62a2386d10616c20d8de2a9f05036a52ae4af4367448cf28dfdcad',
    '5421d1ee0bd308a4be133eb8d44d5c5507255b3947e318dc863a32811cc8b27c',
    '0072520526c0e6381d49b9cf586596303ca64ee82e60592046159754b2820085',
    'd7d61d76be5a17270760ba21fec078fb2e9d9a46e75d66a4a150bb567c15352e',
    'f76f1ac9257c62557ec76739f54dcfdaa9508d8bfc6da0c1810691ebaffd8c66',
    '7e39c2ac837ec54566bbb452afb06f6367c5f078892edfffe085c62b00b6e20b',
    'ff09d21b5b3c562121e2fe33168d46793a07c10eae8206dd2138831b4df5f595')
entries = [(B / ('implementation%02d' % i), pin, True) for i, pin in enumerate(source_pins, 1)]
entries += [(B / ('harness%02d' % i), pin, False) for i, pin in enumerate(pins, 1)]
old = ROOT / 'artifacts/implementation/pat-io-page-encoding'
entries += [(old / 'implementation01', 'ac3e2b660efa78ca9db68b3d0d7ff0cf90a8a38fe8693c982c9d0a077b9301b0', True),
    (old / 'results', '198145480a32fb86e47718dc57de1e120fa1da582ed8d14254498f2711a88fe4', False)]
counts = {}
for folder, pin, rooted in entries:
    assert sha(folder / 'index.json') == pin
    rows = read(folder / 'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder) / row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(rows)
for number in (2, 3, 4): assert not (B / ('harness%02d' % number) / 'attempts').exists()
analysis = read(B / 'GROUP-ANALYSIS.json')
assert analysis['sourceIndexSha256'] == source_pins[1] and analysis['qualificationPassed'] is False
assert analysis['currentGroupsIndependentlyInspected'] == 2 and len(analysis['attempts']) == 5
passed, identities, originals = set(), {}, {}
for item in analysis['attempts']:
    folder = R / item['attempt']; proof = read(folder / 'proof.json'); result = read(folder / 'attempt/result.json')
    assert proof['sourceIndexSha256'] in source_pins and result['childState'] == 'exited'
    assert result['status'] == proof['status'] and result['counts'] == proof['counts']
    assert result['errors'] == result['childErrors'] == [] and result['exitCode'] in (0, 1)
    assert not (Path('/proc') / str(result['pid'])).exists()
    assert proof['sourceFilesVerified'] == 228 and proof['frozenFilesVerified'] == 231 and proof['externalPinsVerified'] == 159
    if proof['status'] == 'passed':
        assert result['exitCode'] == proof['counts']['failures'] == proof['counts']['errors'] == 0
        passed.update(read(folder / 'attempt/actual-tests.json')['executed'])
    for prefix, base, size in (('inputs', folder / 'attempt/project', 228), ('frozen', ROOT, 231), ('harness', folder / 'attempt/harness', 6)):
        rows = read(folder / 'attempt' / (prefix + '-before.json'))
        assert rows == read(folder / 'attempt' / (prefix + '-after.json')) and len(rows) == size
        for row in rows: verify(base / row['path'], row)
    external = read(folder / 'attempt/external-before.json')
    assert external == read(folder / 'attempt/external-after.json') and len(external['files']) == 159
    for row in external['files']: verify(Path(row['resolvedPath']), row)
    origins = read(folder / 'attempt/imports.json')
    assert origins['summary']['allOriginsMatched'] and origins['violations'] == origins['prohibitedAttempts'] == []
    for row in origins['records']:
        if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
    raw = Path(proof['rawScratch']['path']); assert identity(raw) == proof['rawScratch']
    rows = inventory(raw)
    assert rows == read(folder / 'attempt/scratch-index.json') == inventory(folder / 'attempt/scratch')
    assert len(rows) == proof['rawScratchFiles'] and sum(r['bytes'] for r in rows) == proof['rawScratchBytes'] <= 16 * 1024 * 1024
    for label in ('compiler', 'driver'):
        value = read(folder / 'attempt' / (label + '-before.json'))
        assert value == read(folder / 'attempt' / (label + '-after.json'))
        # Both source versions have identical production; verify rather than
        # assuming their compiler/driver identities are equal across attempts.
        if label in identities: assert value == identities[label]
        else: identities[label] = value
    original = B / proof['harness'] / 'attempts' / proof['attempt']
    rows = inventory(original)
    assert rows == inventory(folder / 'attempt') and len(rows) == proof['attemptFilesAcquired']
    originals[item['attempt']] = len(rows)
assert len(passed) == analysis['distinctPassingMethods'] == 132
report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
rows = inventory(R)
write(R / 'index.json', dict(scope='132 distinct passing checks, complete current constant GPIO/PWM groups independently inspected; original test failure retained. No public/physical qualification.', files=rows))
counts[R.relative_to(ROOT).as_posix()] = len(rows)
entries.append((R, sha(R / 'index.json'), False))
D.mkdir(exist_ok=False)
sources = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
    'artifacts/verification/project-links.json', 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [p.relative_to(ROOT).as_posix() for p in sorted(B.iterdir()) if p.is_file() and p.suffix in ('.md', '.py', '.patch', '.json')]
sources += [(folder / 'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries]
assert len(sources) == len(set(sources))
copies = []
for name in sources:
    source = ROOT / name; dest = D / 'inputs' / name
    dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
    row = dict(source=name, copy=dest.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source))
    verify(dest, row); copies.append(row)
write(D / 'index.json', dict(scope='Complete current GPIO/PWM capture and independent group semantics reconciled; process/run attestation, aggregate enforcement and public qualification remain. Full goal stays active.',
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[], distinctPassingMethods=len(passed),
    originalAttemptFilesReverified=originals, artifactEntriesReverified=counts, reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(results=dict(files=len(rows), indexSha256=sha(R / 'index.json')),
    documents=dict(indexSha256=sha(D / 'index.json'), copies=len(copies), artifactEntriesVerified=sum(counts.values()),
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked']))))
