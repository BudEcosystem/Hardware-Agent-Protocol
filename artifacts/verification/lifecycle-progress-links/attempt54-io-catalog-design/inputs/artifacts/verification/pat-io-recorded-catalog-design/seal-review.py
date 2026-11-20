"""Seal the source-informed catalog design and current status without test claims."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/verification/pat-io-recorded-catalog-design'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt54-io-catalog-design'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

def row(path, folder):
    assert path.is_file() and not path.is_symlink()
    return dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path))

assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
inputs = read(BASE / 'inputs.json')
assert sha(ROOT / inputs['sourceIndex']) == inputs['sourceIndexSha256']
for expected in inputs['files']:
    assert row(ROOT / expected['path'], ROOT) == expected
stage = ROOT / 'artifacts/implementation/pat-io-content-store/index.json'
previous = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt53-io-content-store/index.json'
assert sha(stage) == 'c9c19a06ff00462cbfdaeba347c692e19abac339d81f2dc828d5b0c19b71850b'
assert sha(previous) == '0bc2d78a37a56d7a1ef4080f8a956099d214079d5477dff82ada9fd9b0dab751'
links = read(ROOT / 'artifacts/verification/project-links.json')
assert not links['missing'] and links['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for expected in links['files']:
    assert sha(ROOT / expected['path']) == expected['sha256']
rows = sorted((row(path, BASE) for path in BASE.iterdir()), key=lambda item: item['path'])
write(BASE / 'index.json', dict(scope='Source-informed recorded-catalog invocation/applicability design; no production changes or new tests.',
    sourceInputs=len(inputs['files']), productionChanged=False, newTestsRun=0, independentReview=False, goalStatus='active', files=rows))
CHECKPOINT.mkdir()
names = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md', 'scripts/check_project_links.py',
    'artifacts/verification/project-links.json', stage.relative_to(ROOT).as_posix(), previous.relative_to(ROOT).as_posix()]
names += [path.relative_to(ROOT).as_posix() for path in BASE.iterdir()]
copies = []
for name in sorted(names):
    source = ROOT / name
    destination = CHECKPOINT / 'inputs' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    assert sha(destination) == sha(source)
    copies.append(dict(source=name, copy=destination.relative_to(ROOT).as_posix(), bytes=source.stat().st_size, sha256=sha(source)))
write(CHECKPOINT / 'index.json', dict(scope='Completed compact-store stage remains unchanged; next catalog design and active full-goal status.',
    reviewIndexSha256=sha(BASE / 'index.json'), sourceInputs=12, productionChanged=False, newTestsRun=0,
    goalStatus='active', markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'], missing=[], files=copies))
print(json.dumps(dict(reviewFiles=len(rows), reviewIndexSha256=sha(BASE / 'index.json'), documentCopies=len(copies),
    documentIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))
