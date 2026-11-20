"""Seal independent historical inspection and preserve incomplete fresh attempts."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-group-history'
R = B / 'results'
D = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt38-group-history'
assert not (R / 'index.json').exists() and not D.exists()

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    with p.open('x') as f: f.write(json.dumps(value, indent=2) + '\n')
def verify(p, row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], str(p)
def inventory(folder):
    rows = []
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file(): rows.append(dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    return rows
def identity(p):
    s = p.lstat()
    assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p), device=s.st_dev, inode=s.st_ino, uid=s.st_uid, gid=s.st_gid, mode=stat.S_IMODE(s.st_mode))

source_pins = (
    'e5d542ef3b80276050dc3346ffcb1ffd2bb98c2a81fb283b22286cd7274f689c',
    'e57ba4465307e2802c9bdba37e1777183336530bde3f5a1cc96db0d8a8bd08a3',
    'a53f84dcd3ce044ca63293555b4f06648868095efa708d68a622fb99b8467d4b',
    'ad22248967c7a163ccd108d13210331399e15ffb9e166541a80694dce649547c')
harness_pins = (
    '1804217bdba105025f44d7b053bb51abf4a084e1d04674465cbd93c353e05b07',
    'f400b3767e5de83d998187779191ce812013130561472ba60573ff6295e3e02a',
    'a811f40f8b3e57cfe758b6c221c191d243e98960ac3605212d69b5a5db035099',
    'ed61038cca33dbd1bdc673d17a45a45bc7608ead4b433a8c5c095fd1d3535774',
    '137ba7d0ecddb5dab23bfcfa69e0c72cac1061a969d1579213c6d92430b435d8',
    '3c7624920b3918895104eb21562f57a47825663ca1f144606acd78385b8e64e3',
    '13a4c340d1987977b495ff458ce530a804886213446427344536264786c2041a',
    '8172053cd8ed4c86a4b3e30b886eabe909e2315073e5f7e1df26ff5712f65081',
    'e1a7d1494166c74698a0c206b27dc7a410178783669290b9ed89775a3d7cecc3',
    '562c0d685a72e3da05444711dd9209670605187547319ab17c6737f052b6d6c3',
    '825b577dd6bebbd84fffe8b946e641422e671ea9518673517ae59bd5b7045a52',
    '4ab345693a67be24d37e955f0cc1c7122993c02a60be2405705d5bc496da3e79',
    'd167dd5fbe8cecdad9a33411128827d1537fec08fc8b2efe9d14e397a8a559f8',
    '101493e1f2bf826c23bf29cb53f661452f0ffa496a7af47ea67075daafaf0d7b')
entries = [(B / ('implementation%02d' % i), pin, True) for i, pin in enumerate(source_pins, 1)]
entries += [(B / ('harness%02d' % i), pin, False) for i, pin in enumerate(harness_pins, 1)]
old = ROOT / 'artifacts/implementation/pat-io-encoding'
entries += [(old / 'implementation01', '61a0f9ac76a93364ad66277cb4f7eda6a5d80435c7d117f9385ced068b4c9032', True),
    (old / 'results', 'fd198434a134e05a5765ce264f216782f17a555e1ef15beded69be0cc119f2d4', False)]
counts = {}
for folder, pin, rooted in entries:
    assert sha(folder / 'index.json') == pin
    records = read(folder / 'index.json')['files']
    for row in records: verify((ROOT if rooted else folder) / row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(records)
for number in (3, 5, 6, 14):
    directory = B / ('harness%02d' % number) / 'attempts'
    assert not directory.exists() or not any(directory.iterdir())

analysis = read(B / 'GROUP-ANALYSIS.json')
assert len(analysis['attempts']) == 10 and analysis['distinctPassingMethods'] == 108
assert analysis['inspectedFreshGroups'] == 0 and analysis['checkedHistoricalGroups'] == 1
assert analysis['qualificationPassed'] is False and analysis['currentSource04PwmExecuted'] is False
passed, identities, attempt_rows = set(), {}, {}
for item in analysis['attempts']:
    name = item['attempt']
    folder = R / name
    proof = read(folder / 'proof.json'); result = read(folder / 'attempt/result.json')
    if proof['status'] == 'refused_before_start':
        assert result['childState'] == 'not_started' and result['counts'] is None
        assert result.get('pid') is None and result['exitCode'] is None
        assert proof['childStarted'] is False and proof['rawScratchCreated'] is False
        assert not (folder / 'attempt/scratch').exists()
        original = B / proof['originalAttempt']
    else:
        assert result['childState'] == 'exited' and result['status'] == proof['status']
        assert result['exitCode'] in (0, 1) and not (Path('/proc') / str(result['pid'])).exists()
        assert result['errors'] == result['childErrors'] == []
        assert result['counts'] == proof['counts']
        source_index = source_pins.index(proof['sourceIndexSha256'])
        size = 225 if source_index < 2 else 4198
        assert proof['sourceFilesVerified'] == size and proof['frozenFilesVerified'] == size + 3
        assert proof['externalPinsVerified'] == 159
        for prefix, base, expected in (('inputs', folder / 'attempt/project', size),
                ('frozen', ROOT, size + 3), ('harness', folder / 'attempt/harness', 6)):
            rows = read(folder / 'attempt' / (prefix + '-before.json'))
            assert rows == read(folder / 'attempt' / (prefix + '-after.json')) and len(rows) == expected
            for row in rows: verify(base / row['path'], row)
        external = read(folder / 'attempt/external-before.json')
        assert external == read(folder / 'attempt/external-after.json') and len(external['files']) == 159
        for row in external['files']: verify(Path(row['resolvedPath']), row)
        if proof['status'] == 'passed':
            assert result['exitCode'] == proof['counts']['failures'] == proof['counts']['errors'] == 0
            passed.update(read(folder / 'attempt/actual-tests.json')['executed'])
        raw = Path(proof['rawScratch']['path'])
        assert identity(raw) == proof['rawScratch']
        rows = inventory(raw)
        assert rows == read(folder / 'attempt/scratch-index.json') == inventory(folder / 'attempt/scratch')
        assert len(rows) == proof['rawScratchFiles']
        assert sum(row['bytes'] for row in rows) == proof['rawScratchBytes'] <= 16 * 1024 * 1024
        for label in ('compiler', 'driver'):
            value = read(folder / 'attempt' / (label + '-before.json'))
            assert value == read(folder / 'attempt' / (label + '-after.json'))
            key = (proof['sourceIndexSha256'], label)
            if key in identities: assert value == identities[key]
            else: identities[key] = value
        original = B / proof['harness'] / 'attempts' / proof['attempt']
    rows = inventory(original)
    assert rows == inventory(folder / 'attempt') and len(rows) == proof['attemptFilesAcquired']
    attempt_rows[name] = len(rows)
assert len(passed) == 108

report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
rows = inventory(R)
write(R / 'index.json', dict(scope='108 distinct passing methods; independent complete retained GPIO inspection. Fresh source04 GPIO deadline failure and unexecuted PWM retained. No qualification.', files=rows))
counts[R.relative_to(ROOT).as_posix()] = len(rows)
entries.append((R, sha(R / 'index.json'), False))
D.mkdir(exist_ok=False)
sources = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
    'artifacts/verification/project-links.json', 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [p.relative_to(ROOT).as_posix() for p in sorted(B.iterdir()) if p.suffix in ('.md', '.py', '.patch') or p.name == 'GROUP-ANALYSIS.json']
sources += [(folder / 'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries]
assert len(sources) == len(set(sources))
copies = []
for name in sources:
    source = ROOT / name; dest = D / 'inputs' / name
    dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
    row = dict(source=name, copy=dest.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source))
    verify(dest, row); copies.append(row)
write(D / 'index.json', dict(scope='Historical semantic composition complete; fresh acceptance, run attestation and aggregate enforcement incomplete. Full goal remains active.',
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[],
    distinctPassingMethods=len(passed), originalAttemptFilesReverified=attempt_rows,
    artifactEntriesReverified=counts, reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(results=dict(files=len(rows), indexSha256=sha(R / 'index.json')),
    documents=dict(indexSha256=sha(D / 'index.json'), copies=len(copies), artifactEntriesVerified=sum(counts.values()),
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked']))))
