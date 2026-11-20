"""Seal the actual follow-up result and reconcile the documentation evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-refusal-history'
RESULT = BASE / 'results/attempts03-05'
DOCS = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt20-io-refusal128'
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
def verify(path, row):
    assert not path.is_symlink() and path.is_file()
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']

proof = read(RESULT / 'proof.json')
assert proof['totalDistinctPassingMethods'] == 128 and proof['allSelectedMethodsHavePassingInvocation']
assert not proof['single128MethodInvocation'] and not proof['qualificationPassed']
assert [p['status'] for p in proof['attempts']] == ['failed', 'passed', 'passed']
assert proof['earlierTimedOutAttemptRetained']['status'] == 'timed_out'
assert not (RESULT / 'index.json').exists()
rows = []
for path in sorted(RESULT.rglob('*')):
    assert not path.is_symlink()
    if path.is_dir(): continue
    assert stat.S_ISREG(path.stat().st_mode)
    rows.append(dict(path=path.relative_to(RESULT).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
assert len(rows) == 21267
write(RESULT / 'index.json', dict(scope='Retained failed launcher setup and passing27+29 follow-ups, with verified reused72 and retained original timeout; three separate successful invocations cover128 distinct methods.', files=rows))
result_digest = sha(RESULT / 'index.json')

plan = read(BASE / 'followup-selection-plan.json')
original = read(BASE / 'selection-plan.json')
entries = [(BASE / 'implementation01', plan['sourceIndexSha256'], True)]
entries += [(BASE / g['harness'], g['indexSha256'], False) for g in original['groups'] + plan['groups']]
entries += [(BASE / 'results/attempts01-02', plan['retainedOriginalResultIndexSha256'], False), (RESULT, result_digest, False)]
counts = {}
for folder, digest, rooted in entries:
    assert sha(folder / 'index.json') == digest
    indexed = read(folder / 'index.json')['files']
    for row in indexed: verify((ROOT if rooted else folder) / row['path'], row)
    counts[folder.relative_to(ROOT).as_posix()] = len(indexed)

report = read(ROOT / 'artifacts/verification/project-links.json')
assert report['missing'] == [] and report['project_markdown_files'] == 233 and report['local_links_checked'] == 1106
assert report['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT / row['path']) == row['sha256']
DOCS.mkdir(exist_ok=False)
sources = ['PROGRESS.md', 'docs/prompt-to-pat.md', 'docs/io-driver-hub-control.md',
           'scripts/check_project_links.py', 'artifacts/verification/project-links.json']
sources += [(folder / 'index.json').relative_to(ROOT).as_posix() for folder, _, _ in entries]
sources += [(BASE / name).relative_to(ROOT).as_posix() for name in ['selection-plan.json', 'followup-selection-plan.json', 'followup-launch-record.json']]
copies = []
for name in sources:
    src = ROOT / name; dst = DOCS / 'inputs' / name
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    row = dict(source=name, copy=dst.relative_to(ROOT).as_posix(), bytes=src.stat().st_size, sha256=sha(src))
    verify(dst, row); copies.append(row)
write(DOCS / 'index.json', dict(scope='Documentation/link reconciliation after refusal128 selected methods passed across three separate invocations, retaining timeout/setup failures; end-to-end implementation and full qualification remain incomplete.',
    markdownFiles=233, localLinks=1106, missing=[], reportFileHashesVerified=len(report['files']),
    artifactEntriesReverified=counts, files=copies))
print(json.dumps(dict(result=dict(indexSha256=result_digest, files=len(rows), bytes=sum(row['bytes'] for row in rows)),
    documents=dict(indexSha256=sha(DOCS / 'index.json'), copies=len(copies), artifactEntriesVerified=sum(counts.values()), markdownFiles=233, localLinks=1106))))
