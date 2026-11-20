"""Correct a separately embedded stage path in fresh, retained harness copies."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd()
BASE = ROOT / 'artifacts/implementation/pat-io-recorded-catalog'
PIN = '55e12b130d5c87ad8c5eef53d890692db2e1121a4622e75287d6d8ba2dea8b89'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

assert sha(BASE / 'implementation02/index.json') == PIN
failed = read(BASE / 'harness22/attempts/attempt01/result.json')
assert failed['childState'] == 'not_started' and failed.get('pid') is None and failed.get('scratchPath') is None
assert failed['errors'][0]['message'] == 'Frozen source-preparation index changed'
write(BASE / 'harness-source02-path-failure.json', dict(original='harness22/attempts/attempt01/result.json',
    sourceIndexUnchanged=True, actualSourceIndexSha256=PIN, childStarted=False, databasesOpened=0, workerStarted=False,
    cause="The separately embedded stage = here.parent / 'implementation01' remained old while PREFIX and FROZEN_INDEX correctly selected implementation02",
    correction='Fresh harness42..61 change only that runner path and retain the old harness/attempt'))
prepared = []
for old_number in range(22, 42):
    prior = BASE / ('harness%02d' % old_number)
    harness = BASE / ('harness%02d' % (old_number + 20))
    harness.mkdir()
    for row in read(prior / 'index.json')['files']:
        source = prior / row['path']
        assert sha(source) == row['sha256'] and source.stat().st_size == row['bytes']
        destination = harness / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    path = harness / 'run_attempt.py'
    original = path.read_text()
    marker = "stage = here.parent / 'implementation01'"
    assert original.count(marker) == 1
    changed = original.replace(marker, "stage = here.parent / 'implementation02'")
    assert "PREFIX = 'artifacts/implementation/pat-io-recorded-catalog/implementation02/'" in changed
    assert "FROZEN_INDEX = '" + PIN + "'" in changed
    ast.parse(changed)
    path.write_text(changed)
    (harness / 'source-stage-path.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True))))
    review = read(harness / 'review.json')
    review['reviewed'].append('Runner stage literal, source prefix and index pin all resolve implementation02; the prior pre-child path failure is retained.')
    review['sourceStage'] = 'implementation02'
    review['priorHarnessIndexSha256'] = sha(prior / 'index.json')
    (harness / 'review.json').write_text(json.dumps(review, indent=2) + '\n')
    rows = []
    for path in harness.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            rows.append(dict(path=path.relative_to(harness).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    write(harness / 'index.json', dict(scope=review['scope'], files=sorted(rows, key=lambda row: row['path'])))
    prepared.append(harness.name)
print(json.dumps(dict(prepared=True, sourceIndexSha256=PIN, harnesses=prepared, priorFailureRetained=True)))
