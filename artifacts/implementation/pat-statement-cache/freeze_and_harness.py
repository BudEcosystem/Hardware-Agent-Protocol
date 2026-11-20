"""Freeze one-option candidate and adapt exact previously bounded harnesses."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = BASE.parent / 'qualification-package'
SOURCE = BASE / 'implementation01'
PROJECT = SOURCE / 'project'
OLD_SOURCE = OLD / 'implementation03'
OLD_PIN = 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    body = value if type(value) is bytes else (value if type(value) is str else json.dumps(value, indent=2) + '\n').encode()
    with p.open('xb') as stream: stream.write(body)
def row(p, root): return dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
def verify(index, root, pin=None):
    if pin is not None: assert sha(index) == pin
    rows = read(index)['files']
    for item in rows:
        p = root / item['path']
        assert not p.is_symlink() and p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
    return rows

assert not (SOURCE / 'index.json').exists()
verify(OLD_SOURCE / 'index.json', ROOT, OLD_PIN)
pins = read(BASE / 'inspection01.json')
assert pins['passed'] and not pins['importEffects'] and len(pins['origins']) == 39
assert pins['poisonedLegacyModules'] == 17 and len(pins['initializerDriftRefusals']) == 4
assert pins['producerImageFiles'] == 267
old_pins = read(OLD_SOURCE / 'identity-pins.json')
replacement = {old_pins[k]: pins[k] for k in ('host', 'consumer', 'vault', 'legacy')}
updated = []
for p in sorted((PROJECT / 'tests').glob('*.py')):
    before = p.read_text(); after = before
    for old, new in replacement.items(): after = after.replace(old, new)
    if before != after:
        # Identity expectations are the only test edits. Reverse replacement
        # proves every other literal, assertion and control remains identical.
        reverted = after
        for old, new in replacement.items(): reverted = reverted.replace(new, old)
        assert reverted == before
        p.write_text(after); updated.append(str(p.relative_to(PROJECT)))
project_files = sorted(p for p in PROJECT.rglob('*') if p.is_file())
assert len(project_files) == 304
changed = []
patch = []
for p in project_files:
    name = p.relative_to(PROJECT).as_posix(); original = OLD_SOURCE / 'project' / name
    if p.suffix == '.py': ast.parse(p.read_bytes())
    if p.read_bytes() != original.read_bytes():
        changed.append(name)
        patch.extend(difflib.unified_diff(original.read_text().splitlines(True), p.read_text().splitlines(True),
            fromfile='baseline/' + name, tofile='candidate/' + name))
assert set(changed) == {'hms/journal.py', *updated}
assert len(updated) == 2
write(SOURCE / 'final.patch', ''.join(patch))
write(SOURCE / 'identity-pins.json', pins)
write(SOURCE / 'source-review.json', dict(reviewer='primary-agent', independentReview=False,
    baselineIndexSha256=OLD_PIN, changedProductionFiles=['hms/journal.py'],
    updatedTestIdentityExpectations=updated, otherProjectFilesUnchanged=301,
    authorityCachedStatements=256, boardCacheChanged=False, remainingJournalAstExact=True,
    captureAndGuardMethodsUnchanged=True, namespaceAndWorkerEntryUnchanged=True,
    historicalEvidenceRepinned=False, originalCases=30, workerWallMs=60000, parentSeconds=180,
    publicRuntimeChanged=False, actualExecutionPending=True))
write(SOURCE / 'test-selection.json', (OLD_SOURCE / 'test-selection.json').read_bytes())
write(SOURCE / 'README.md', '# Authority statement cache candidate\n\n'
    'The only production edit is `cached_statements=256` on the Journal connection. '
    'Two current test files receive recomputed identity expectations. All other 301 '
    'project files are exact. [Diff](final.patch), [review](source-review.json), '
    '[identities](identity-pins.json). The namespace map is retained baseline provenance; '
    'the current index defines this candidate. Full integration remains pending.\n')
frozen = [row(p, ROOT) for p in sorted(SOURCE.rglob('*')) if p.is_file()]
write(SOURCE / 'index.json', dict(files=frozen))
pin = sha(SOURCE / 'index.json')

def prepare_harness(template, harness, actual):
    assert not harness.exists()
    template_rows = verify(template / 'index.json', template)
    diffs = []
    for item in template_rows:
        p = template / item['path']; name = item['path']; body = p.read_bytes()
        if name == 'run_attempt.py':
            before = body.decode(); after = before.replace(OLD_PIN, pin)
            if actual:
                old_path = 'artifacts/implementation/qualification-package/implementation03'
                assert after.count(old_path) == 2
                after = after.replace(old_path, str(SOURCE.relative_to(ROOT)))
                assert after.count('!= 312') == 1
                assert after.count("'frozenPreparationInputCount': 312") == 1
                after = after.replace('!= 312', '!= ' + str(len(frozen)))
                after = after.replace("'frozenPreparationInputCount': 312", "'frozenPreparationInputCount': " + str(len(frozen)))
            else:
                assert after.count("SOURCE = BASE / 'implementation03'") == 1
                after = after.replace("SOURCE = BASE / 'implementation03'", "SOURCE = BASE / 'implementation01'")
            ast.parse(after); body = after.encode()
            diffs.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                fromfile='baseline/' + name, tofile='candidate/' + name))
        if actual and name == 'SCOPE.md':
            body = ('# Complete qualification with finite statement cache\n\n'
                'One full thirty-case worker, real reducer, authority-vault publication, catalog '
                'promotion, one simulated application, drift refusal and cold history. Only the '
                'authority Journal cache and resulting implementation identities change. Original '
                '60-second worker / 180-second parent limits and all file, storage, lease, open, '
                'ownership and image constraints remain unchanged. No oracle substitution or '
                'physical devices. Never reopen interrupted worker case databases. Earlier copied '
                'reference and patch files retain their original provenance.\n').encode()
        write(harness / name, body)
    write(harness / 'cache-adaptation.patch', ''.join(diffs))
    write(harness / 'CACHE_SCOPE.json', dict(originalHarness=str(template.relative_to(ROOT)),
        originalIndexSha256=sha(template / 'index.json'), sourceIndexSha256=pin,
        limitsUnchanged=True, attemptChildByteIdentical=True, semanticOracleSubstituted=not actual,
        qualificationWorkerAllowed=actual, physicalExecutionAllowed=False,
        reviewer='primary-agent', independentReview=False))
    write(harness / 'index.json', dict(files=[row(p, harness) for p in sorted(harness.rglob('*')) if p.is_file()]))
    return dict(harness=harness.name, original=template.name, indexSha256=sha(harness / 'index.json'),
                targets=read(harness / 'targets.json'))

actual = prepare_harness(OLD / 'harness01', BASE / 'harness01', True)
controls = []
previous = read(OLD / 'control-selection02.json')
assert previous['testCount'] == 19 and len(previous['scopes']) == 10
for scope in previous['scopes']:
    template = OLD / scope['harness']
    assert sha(template / 'index.json') == scope['indexSha256']
    controls.append(prepare_harness(template, BASE / scope['harness'], False))
write(BASE / 'control-selection.json', dict(sourceIndexSha256=pin, scopes=controls, testCount=19,
    actualQualificationReplacement=False))
write(BASE / 'selected-scope.json', dict(sourceIndexSha256=pin, projectFiles=304,
    frozenFiles=len(frozen), actual=actual, controls=19, actualPending=True))
print(json.dumps(dict(sourceIndexSha256=pin, projectFiles=304, frozenFiles=len(frozen),
    updatedTestFiles=updated, controls=19, actualHarnessIndexSha256=actual['indexSha256'])))
