"""Prepare a fresh fixture revision; retain the failed frozen attempt unchanged."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OUT = BASE / 'evaluation02'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


assert sha(BASE / 'inputs.json') == '4701ceda4a10ac8443822753944e0935ddbb6c7688da1c97dcac5a28fb6764e5'
assert read(BASE / 'attempt01/command.json')['inputIndexSha256'] == sha(BASE / 'inputs.json')
assert OUT.is_dir() and not list(OUT.iterdir())
write(BASE / 'CORRECTION_PREPARATION_FAILURE.json', {
    'action': 'Prepare evaluation02 fixture correction', 'status': 'rejected-before-copy',
    'reason': 'The inline correction script transcribed the original input pin incorrectly.',
    'incorrectExpectedPin': '4701ceda4a10ac8443822753944e0ce11856e64ccb5f5dcca93adcabdcbed61c2b',
    'actualPin': sha(BASE / 'inputs.json'), 'originalAttemptCommandPinMatches': True,
    'correctionCopiesWritten': 0, 'childStarted': False, 'databaseConnectionsOpened': 0})
for row in read(BASE / 'inputs.json')['files']:
    source = BASE / row['path']
    assert source.stat().st_size == row['bytes'] and sha(source) == row['sha256']
    name = {'SOURCE_REVIEW.json': 'prior-SOURCE_REVIEW.json',
            'review_and_freeze.py': 'prior-review-and-freeze.py'}.get(row['path'], row['path'])
    target = OUT / name; target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(source.read_bytes())
source = ROOT / 'artifacts/implementation/qualification-package/implementation03/project/hms/pat_io_conflict_capture.py'
source_index = ROOT / 'artifacts/implementation/qualification-package/implementation03/index.json'
assert sha(source_index) == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
row = next(r for r in read(source_index)['files'] if r['path'] == str(source.relative_to(ROOT)))
assert sha(source) == row['sha256']
with (OUT / 'references/pat_io_conflict_capture.py').open('xb') as stream:
    stream.write(source.read_bytes())
profile = next(ast.literal_eval(n.value) for n in ast.walk(ast.parse(source.read_bytes()))
    if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
    and n.targets[0].id == '_record_profile')
assert profile == 'hms.pat.io-trial-record/0.2'
for path in (OUT / 'documents/records').glob('*.json'):
    assert read(path)['profile'] == profile
write(OUT / 'fixture-profile.json', {'legacyProfile': profile,
    'source': str(source.relative_to(ROOT)), 'sourceSha256': sha(source),
    'configurationProfile': 'hms.pat.io-configuration-record/0.1'})
borrowed = read(OUT / 'borrowed-inputs.json')
borrowed.append({'source': str(source.relative_to(ROOT)), 'copy': 'references/pat_io_conflict_capture.py',
                 'bytes': row['bytes'], 'sha256': row['sha256']})
(OUT / 'borrowed-inputs.json').write_text(json.dumps(borrowed, indent=2) + '\n')
old = (OUT / 'child.py').read_text()
new = old.replace("LEGACY = specifications['RECORD_PROFILE']",
                  "LEGACY = json.loads(verify('fixture-profile.json'))['legacyProfile']")
assert new != old; ast.parse(new)
(OUT / 'child.py').write_text(new)
(OUT / 'profile-correction.patch').write_text(''.join(difflib.unified_diff(
    old.splitlines(True), new.splitlines(True), fromfile='attempt01/child.py', tofile='evaluation02/child.py')))
review = (BASE / 'review_and_freeze.py').read_text().replace('ROOT = BASE.parents[2]', 'ROOT = BASE.parents[3]')
review = review.replace("failure = BASE / 'preparation01'", "failure = BASE.parent / 'preparation01'")
review = review.replace('assert len(borrowed) == 68', 'assert len(borrowed) == 69')
review = review.replace("'borrowedInputsVerified': 68", "'borrowedInputsVerified': 69")
extra = '''profile = read(BASE / 'fixture-profile.json')
assert profile['legacyProfile'] == 'hms.pat.io-trial-record/0.2'
profile_source = BASE / 'references/pat_io_conflict_capture.py'
assert sha(profile_source) == profile['sourceSha256']
values = [ast.literal_eval(n.value) for n in ast.walk(ast.parse(profile_source.read_bytes()))
          if isinstance(n, ast.Assign) and len(n.targets) == 1 and
          isinstance(n.targets[0], ast.Name) and n.targets[0].id == '_record_profile']
assert values == [profile['legacyProfile']]
for path in (BASE / 'documents/records').glob('*.json'):
    assert read(path)['profile'] == profile['legacyProfile']

'''
needle = "write('SOURCE_REVIEW.json', {"
assert needle in review
review = review.replace(needle, extra + needle).replace("'captureSqlChanged': False,",
    "'captureSqlChanged': False, 'legacyFixtureProfile': profile['legacyProfile'],\n    'fixtureProfileMatchesRetainedSubclass': True,")
ast.parse(review)
with (OUT / 'review_and_freeze.py').open('x') as stream:
    stream.write(review)
report = {'status': 'failed-before-timing', 'originalInputIndexSha256': sha(BASE / 'inputs.json'),
    'attemptResultSha256': sha(BASE / 'attempt01/result.json'),
    'stderrSha256': sha(BASE / 'attempt01/stderr.log'), 'childState': 'exited', 'exitCode': 1,
    'inputBytesUnchanged': True,
    'failure': 'First diagnostic full-capture table references did not match retained expected references.',
    'staticCause': 'Memory writer used base /0.1 profile; all retained legacy records and pinned conflict subclass use /0.2.',
    'timingSamplesStarted': False, 'timingEvidence': 'Failure traceback occurs at the first diagnostic capture before any timing loop.',
    'qualificationWorkerLaunched': False, 'productionRuntimeChanged': False,
    'memoryOnlyConnectionsRequiredByOriginalChild': True, 'liveDatabaseStateInspected': False,
    'correction': 'New evaluation02 fixture binds the writer profile to the pinned conflict subclass; methods, cache choices and bounds are unchanged.'}
write(BASE / 'FAILED_ATTEMPT_REVIEW.json', report)
write(OUT / 'CORRECTION.json', report)
print(json.dumps({'borrowedInputs': len(borrowed), 'correctedProfile': profile,
                  'originalAttemptPreserved': True, 'newEvaluationExecuted': False}))
