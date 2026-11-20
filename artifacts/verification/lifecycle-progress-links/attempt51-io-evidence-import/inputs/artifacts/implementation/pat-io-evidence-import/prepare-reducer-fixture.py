"""Retain a historical complete group as data, never as a new bound attempt."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

ROOT = Path.cwd(); BASE = ROOT / 'artifacts/implementation/pat-io-evidence-import'
PREVIOUS = BASE / 'implementation01'; STAGE = BASE / 'implementation02'
OLD = ROOT / 'artifacts/implementation/pat-io-document-validation/results'
PIN = 'a4e2629f76a0df2e341edcf038502337f6305dac05fcf9b0de5a9d35de360d0c'
SOURCE_PIN = '25678ecd4d7c3daf4719b51d97fa323da2d2cba3b899d72ee77c7e65bb4adb4c'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
assert sha(OLD / 'index.json') == PIN and sha(PREVIOUS / 'index.json') == SOURCE_PIN
prior = json.loads((PREVIOUS / 'index.json').read_bytes())['files']
for row in prior:
    path = ROOT / row['path']; assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
STAGE.mkdir(); shutil.copytree(PREVIOUS / 'project', STAGE / 'project')
old_rows = {row['path']: row for row in json.loads((OLD / 'index.json').read_bytes())['files']}
source = OLD / 'attempt03-passed-reserved-owned/attempt/scratch/test_reserved_owned_group_replays_after_config_and_session_change'
attempt = source / 'supervisor/d8b07e8aaa0e4ca6bfe7cb2dc5447162'
destination = STAGE / 'project/tests/fixtures/recorded-io-group'; destination.mkdir()
retained = []
def copy(path, relative):
    expected = old_rows[path.relative_to(OLD).as_posix()]
    assert sha(path) == expected['sha256'] and path.stat().st_size == expected['bytes']
    target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    retained.append(dict(source=path.relative_to(ROOT).as_posix(), copy=relative, bytes=expected['bytes'], sha256=expected['sha256']))
for group in ('bundle', 'output'):
    for path in sorted((attempt / group).rglob('*')):
        if path.is_file(): copy(path, path.relative_to(attempt).as_posix())
for name in ('input.json', 'worker-return.json'): copy(attempt / name, name)
copy(source / 'run-reservation.json', 'run-reservation.json')
copy(source / 'supervisor/attempts.db', 'original-attempts.db')
# The original authority is legacy v1. This read-only extraction does not
# create, migrate or populate a version2 supervisor ledger or handoff store.
connection = sqlite3.connect((destination / 'original-attempts.db').resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
try:
    row = connection.execute('SELECT request,record,return_bytes FROM qs_attempts WHERE id=?', ('d8b07e8aaa0e4ca6bfe7cb2dc5447162',)).fetchone()
    assert row is not None
    write(destination / 'original-row.json', dict(request=json.loads(row[0]), record=json.loads(row[1]), returned=json.loads(row[2])))
finally: connection.close()
write(destination / 'PROVENANCE.json', dict(kind='pure-reducer-data-fixture', sourceResultsIndexSha256=PIN,
    originalSupervisorVersion=1, realVersion2Authority=False, realHandoff=False,
    publishedToEvidenceStore=False, files=retained,
    syntheticAssociation='Tests construct a visibly synthetic association solely to exercise the pure reducer. It never authenticates an actual bound run.'))
write(STAGE / 'baseline-inputs.json', dict(inheritedSourceIndexSha256=SOURCE_PIN, unchangedInheritedProjectFiles=259,
    historicalFixtureSourceIndexSha256=PIN, fixtureFiles=len(retained)))
print(json.dumps(dict(unchangedInheritedProjectFiles=259, retainedFixtureFiles=len(retained), retainedFixtureBytes=sum(row['bytes'] for row in retained))))
