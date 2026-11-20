"""Freeze namespace-only adaptations of the already reviewed control harnesses.

Each selection runs once in its own original bounded child. These controls use
the original substituted semantic oracle and never launch a qualification worker.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = BASE.parent / 'pat-vault-catalog'
SOURCE = BASE / 'implementation03'
PIN = 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as out:
        out.write(value if type(value) is str else json.dumps(value, indent=2) + '\n')
def row(p, root): return dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p))

assert sha(SOURCE / 'index.json') == PIN
for item in read(SOURCE / 'index.json')['files']:
    p = ROOT / item['path']
    assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
legacy = sorted(read(SOURCE / 'namespace-map.json')['modules'])
scopes = []
for new, old in enumerate((7, 8, 9, 10, 11, 17, 18, 19, 20, 21), 2):
    template = OLD / ('harness%02d' % old)
    harness = BASE / ('harness%02d' % new)
    assert not harness.exists()
    for item in read(template / 'index.json')['files']:
        p = template / item['path']
        assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
    harness.mkdir()
    for name in ('targets.json', 'README.md'):
        write(harness / name, (template / name).read_text())
    for p in (template / 'references').rglob('*'):
        if p.is_file():
            target = harness / 'references' / p.relative_to(template / 'references')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as out: out.write(p.read_bytes())
    for name in ('run_attempt.py', 'attempt_child.py'):
        before = (template / name).read_text()
        after = before
        if name == 'run_attempt.py':
            after = after.replace("SOURCE = BASE / 'implementation02'", "SOURCE = BASE / 'implementation03'")
            assert 'assert len(inputs) == 301' in after or 'assert len(inputs) == 302' in after
            after = after.replace('assert len(inputs) == 301', 'assert len(inputs) == 304').replace('assert len(inputs) == 302', 'assert len(inputs) == 304')
            after = after.replace("source_pin = read(SOURCE / 'index.json')", "assert sha(SOURCE / 'index.json') == " + repr(PIN) + "\nsource_pin = read(SOURCE / 'index.json')")
        else:
            assert "[str(root), str(root / 'tests'), str(root / 'supervisor')]" in after
            after = after.replace("[str(root), str(root / 'tests'), str(root / 'supervisor')]", "[str(root), str(root / 'tests')]")
            after = after.replace("root / 'supervisor/retention_scan.so'", "root / 'hms_qualification/supervisor/retention_scan.so'")
            after = after.replace("name == 'hms' or name.startswith('hms.')", "name == 'hms' or name.startswith('hms.') or name == 'hms_qualification' or name.startswith('hms_qualification.')")
            needle = "        if origin is not None:\n            add('module:' + name, origin)"
            assert needle in after
            after = after.replace(needle, needle + '\n        if name in ' + repr(legacy) + ":\n            violations.append({'module': name, 'reason': 'legacy_flat_import_forbidden'})")
        ast.parse(after)
        write(harness / name, after)
        write(harness / (name + '.patch'), ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='previous/' + name, tofile='namespaced/' + name)))
    targets = read(harness / 'targets.json')
    write(harness / 'NAMESPACE_SCOPE.json', dict(originalHarness=str(template.relative_to(ROOT)),
        originalIndexSha256=sha(template / 'index.json'), sourceIndexSha256=PIN,
        targets=targets, semanticOracleSubstituted=True, qualificationWorkerAllowed=False,
        physicalExecutionAllowed=False, reviewedBy='primary-agent', independentReview=False,
        changes=['Qualified import root, native artifact path and import-origin audit.',
                 'Exact frozen 304-file namespace candidate; source index pin.'],
        limitsUnchanged=True, failedActualAttemptSuperseded=False))
    write(harness / 'index.json', dict(files=[row(p, harness) for p in sorted(harness.rglob('*')) if p.is_file()]))
    scopes.append(dict(harness=harness.name, original=template.name, indexSha256=sha(harness / 'index.json'), targets=targets))
write(BASE / 'control-selection.json', dict(sourceIndexSha256=PIN, scopes=scopes,
    testCount=sum(len(s['targets']) for s in scopes), actualQualificationReplacement=False))
print(json.dumps(dict(scopes=len(scopes), tests=sum(len(s['targets']) for s in scopes))))
