"""Seal bounded page encoding and retain incomplete capture/profile evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-page-encoding'; R = B / 'results'
D = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt39-page-encoding'
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

source_pin = 'ac3e2b660efa78ca9db68b3d0d7ff0cf90a8a38fe8693c982c9d0a077b9301b0'
pins = ('773ae80fdb51d81a3a5ed05b60c3f752d81c5fb54de0def21d840e0315fa824b',
    '07ad59ea603020b6bd55046593374086ae50ccee396148a7247350ce25752e41',
    '71ab75814eeb2b93cf91332e6346eca977775af80c88dbab2922058789b6d5ce',
    '06c88ab69f64c4859f60b99e5433c07f1dc4beb0d6d801cf4e16da3c68c557db',
    '6fbeea40a02fa5fbe7b6cb45e87c384ffe760230f6f43db9e4b7ca0e8a3d82a6')
entries = [(B / 'implementation01', source_pin, True)]
entries += [(B / ('harness%02d' % i), pin, False) for i, pin in enumerate(pins, 1)]
old = ROOT / 'artifacts/implementation/pat-io-group-history'
entries += [(old / 'implementation04', 'ad22248967c7a163ccd108d13210331399e15ffb9e166541a80694dce649547c', True),
    (old / 'results', '1cbbd1135a6161cceed87cf11edb27e37459afec396bfda3bc165fafe0f8239f', False)]
counts = {}
for folder, pin, rooted in entries:
    assert sha(folder / 'index.json') == pin
    rows = read(folder / 'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder) / row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(rows)
assert not (B / 'harness04/attempts').exists()
analysis = read(B / 'GROUP-ANALYSIS.json')
assert analysis['sourceIndexSha256'] == source_pin and analysis['qualificationPassed'] is False
assert analysis['currentPwmExecuted'] is False and analysis['independentlyInspectedCurrentGroups'] == 0
passed, identities, originals = set(), {}, {}
for item in analysis['attempts']:
    folder = R / item['attempt']; proof = read(folder / 'proof.json'); result = read(folder / 'attempt/result.json')
    assert proof['sourceIndexSha256'] == source_pin and result['childState'] == 'exited'
    assert result['status'] == proof['status'] and result['counts'] == proof['counts']
    assert result['errors'] == result['childErrors'] == [] and result['exitCode'] in (0, 1)
    assert not (Path('/proc') / str(result['pid'])).exists()
    assert proof['sourceFilesVerified'] == 227 and proof['frozenFilesVerified'] == 230 and proof['externalPinsVerified'] == 159
    if proof['status'] == 'passed':
        assert result['exitCode'] == proof['counts']['failures'] == proof['counts']['errors'] == 0
        passed.update(read(folder / 'attempt/actual-tests.json')['executed'])
    for prefix, base, size in (('inputs', folder / 'attempt/project', 227), ('frozen', ROOT, 230), ('harness', folder / 'attempt/harness', 6)):
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
        if label in identities: assert value == identities[label]
        else: identities[label] = value
    original = B / proof['harness'] / 'attempts' / proof['attempt']
    rows = inventory(original)
    assert rows == inventory(folder / 'attempt') and len(rows) == proof['attemptFilesAcquired']
    originals[item['attempt']] = len(rows)
assert len(passed) == analysis['distinctPassingMethods'] == 118
report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
rows = inventory(R)
write(R / 'index.json', dict(scope='118 distinct passing checks; fresh GPIO deadline and instrumented failure retained, PWM unexecuted. Current qualification remains incomplete.', files=rows))
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
write(D / 'index.json', dict(scope='Exact page encoding checks pass; current capture/inspection remains incomplete with all failures retained. Full goal remains active.',
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[], distinctPassingMethods=len(passed),
    originalAttemptFilesReverified=originals, artifactEntriesReverified=counts, reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(results=dict(files=len(rows), indexSha256=sha(R / 'index.json')),
    documents=dict(indexSha256=sha(D / 'index.json'), copies=len(copies), artifactEntriesVerified=sum(counts.values()),
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked']))))
