"""Seal complete synthetic captures and preserve the preceding failures."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-encoding'
R = B / 'results'
D = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt37-encoding'
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

names = ('attempt01-passed96', 'attempt02-passed-cutoff', 'attempt03-passed-gpio', 'attempt04-passed-pwm')
passed, identities = set(), {}
for name in names:
    folder = R / name
    proof = read(folder / 'proof.json'); result = read(folder / 'attempt/result.json')
    assert proof['status'] == 'passed' and result['childState'] == 'exited'
    assert not (Path('/proc') / str(result['pid'])).exists()
    assert result['errors'] == result['childErrors'] == []
    assert proof['sourceFilesVerified'] == 222 and proof['frozenFilesVerified'] == 225 and proof['externalPinsVerified'] == 159
    passed.update(read(folder / 'attempt/actual-tests.json')['executed'])
    raw = Path(proof['rawScratch']['path']); info = raw.lstat()
    assert stat.S_ISDIR(info.st_mode) and info.st_ino == proof['rawScratch']['inode']
    rows = inventory(raw)
    assert rows == read(folder / 'attempt/scratch-index.json') == inventory(folder / 'attempt/scratch')
    assert len(rows) == proof['rawScratchFiles']
    assert sum(row['bytes'] for row in rows) == proof['rawScratchBytes'] <= 16 * 1024 * 1024
    for label in ('compiler', 'driver'):
        value = read(folder / 'attempt' / (label + '-before.json'))
        assert value == read(folder / 'attempt' / (label + '-after.json'))
        if label in identities: assert value == identities[label]
        else: identities[label] = value
assert len(passed) == 99
rows = inventory(R)
assert len(rows) == 9179
write(R / 'index.json', dict(scope='99 distinct passing methods, complete GPIO and PWM synthetic capture under original limits. Independent qualification remains incomplete.', files=rows))

entries = [(B / 'implementation01', '61a0f9ac76a93364ad66277cb4f7eda6a5d80435c7d117f9385ced068b4c9032', True)]
pins = ('bc4d91eecc4e39374f6113274a27102995181d465ce6f2a5d27cc47a72034e00',
    '5c5c740bf1cb31ed951ed82b7f52e0d1991b24ca1ebb388f36e1696c810213b0',
    'c1f7e954c5ff7f7dfef97a395931fbf2f88c87bd603dbde5472e570f1cbe9cdb',
    'a7c655f023118c55d42a6a717651b5ab980d876a7d127dd2f680444b34f17869',
    'fda728d12729ee61437ffd0e9d3827993bb093431ca90776b543e10618270308')
entries += [(B / ('harness%02d' % i), pin, False) for i, pin in enumerate(pins, 1)]
entries.append((R, sha(R / 'index.json'), False))
old = ROOT / 'artifacts/implementation/pat-io-group-efficiency'
entries += [(old / 'implementation01', 'cd3593c1c6aec73eb74bdbac9ea48c5d9f5b835818a4095b27fd6d13616b58d5', True),
    (old / 'results', '17abd3c1b985bd42e73c1ffe87aaaa7281d64f5513ec5ff7ce1afb013c098857', False)]
counts = {}
for folder, pin, rooted in entries:
    assert sha(folder / 'index.json') == pin
    records = read(folder / 'index.json')['files']
    for row in records: verify((ROOT if rooted else folder) / row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(records)
report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
D.mkdir(exist_ok=False)
sources = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
    'artifacts/verification/project-links.json', 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(B / name).relative_to(ROOT).as_posix() for name in ('DESIGN.md', 'GROUP-ANALYSIS.json', 'prepare.py',
    'implementation.patch', 'acquire.py', 'acquire.py.patch', 'audit-states.py', 'audit-states.py.patch',
    'audit-storage.py', 'audit-storage.py.patch', 'write-results.py', 'write-docs.py', 'finish-stage.py')]
sources += [(folder / 'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries]
copies = []
for name in sources:
    source = ROOT / name; dest = D / 'inputs' / name
    dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, dest)
    row = dict(source=name, copy=dest.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source))
    verify(dest, row); copies.append(row)
write(D / 'index.json', dict(scope='Complete synthetic GPIO/PWM capture, exact encoding preservation and remaining independent qualification work reconciled. Full goal remains active.',
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked'], missing=[],
    artifactEntriesReverified=counts, reportFileHashesVerified=len(report['files']), files=copies))
print(json.dumps(dict(results=dict(files=len(rows), indexSha256=sha(R / 'index.json')),
    documents=dict(indexSha256=sha(D / 'index.json'), copies=len(copies), artifactEntriesVerified=sum(counts.values()),
    markdownFiles=report['project_markdown_files'], localLinks=report['local_links_checked']))))
