"""Freeze namespaced source and adapt the reviewed actual-run harness paths."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation03'
PROJECT = SOURCE / 'project'
OLD = ROOT / 'artifacts/implementation/pat-vault-catalog/implementation03'
TEMPLATE = ROOT / 'artifacts/implementation/pat-vault-catalog/harness23'
HARNESS = BASE / 'harness01'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(value if type(value) is str else json.dumps(value, indent=2) + '\n')
def row(path, root=ROOT):
    return dict(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=sha(path))


assert not (SOURCE / 'index.json').exists() and not HARNESS.exists()
pins = read(BASE / 'inspection04.json')
assert pins['passed'] and len(pins['initializerDriftRefusals']) == 4
old_pins = read(OLD / 'identity-pins.json')
replacements = {
    'sha256:5e9214b37a96f897253ea2f1859090327039f5aaeb9512aa49df880484cf4523': pins['consumer'],
    'sha256:bbb5b7ca4793e17b4baaaf5d2252781ce75f76b86d0d18dd65707b8ad3fc7b1a': pins['host'],
    'sha256:1603d92f5c82955d51bd0537e95dffc048708ac90b28972a66e747511b0c8e03': pins['vault'],
    'sha256:0a736687bb33e7a811b11adfb42adae7b6495965f46e0f818cb22834ae4834fb': pins['legacy'],
}
changed_pins = []
for path in sorted((PROJECT / 'tests').glob('*.py')):
    before = path.read_text(); after = before
    for old, new in replacements.items(): after = after.replace(old, new)
    if before != after:
        path.write_text(after); changed_pins.append(str(path.relative_to(PROJECT)))
core = sorted((PROJECT / 'hms').rglob('*.py'))
assert len(core) == 83 and all(path.read_bytes() == (OLD / 'project' / path.relative_to(PROJECT)).read_bytes() for path in core)
mapping = read(SOURCE / 'namespace-map.json')
final_rows, patch = [], []
for entry in mapping['files']:
    path = PROJECT / entry['path']; original = OLD / 'project' / entry['originalPath']
    final_rows.append(entry | dict(finalSha256=sha(path)))
    if path.suffix == '.py' and path.read_bytes() != original.read_bytes():
        patch.extend(difflib.unified_diff(original.read_text().splitlines(True), path.read_text().splitlines(True),
            fromfile=entry['originalPath'], tofile=entry['path']))
for path in PROJECT.rglob('*.py'): ast.parse(path.read_bytes())
write(SOURCE / 'final.patch', ''.join(patch))
write(SOURCE / 'identity-pins.json', pins)
write(SOURCE / 'source-review.json', dict(reviewer='primary-agent', independentReview=False,
    originalIndexSha256=sha(OLD / 'index.json'), originalHmsFilesUnchanged=83,
    package='hms_qualification', files=final_rows, updatedTestIdentityPins=changed_pins,
    importOnlyInspection=str((BASE / 'inspection04.json').relative_to(ROOT)),
    actualExecutionPending=True, publicRuntimeChanged=False,
    invariants=['No wire fields, database filenames or authority anchors renamed.',
        'Package initializers are included in supervisor identity and exact producer image.',
        'Only fixed protected image root and pinned dependencies enter child import path.',
        'All thirty cases, original deadlines, resource/storage caps and one application remain.']))
write(SOURCE / 'test-selection.json', read(TEMPLATE / 'targets.json'))
write(SOURCE / 'README.md', '# Explicit qualification package candidate\n\n'
    'The namespace and fixed worker entry are updated; all 83 hms modules remain exact. '
    'No public service is enabled. [Review](source-review.json), [identities](identity-pins.json), '
    '[selection](test-selection.json). The actual full worker/application result remains pending.\n')
project_count = len([p for p in PROJECT.rglob('*') if p.is_file()])
assert project_count == 304
frozen = [row(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()]
write(SOURCE / 'index.json', dict(files=frozen))

HARNESS.mkdir()
for name in ('targets.json', 'borrowed-inputs.json'):
    write(HARNESS / name, (TEMPLATE / name).read_text())
for path in sorted((TEMPLATE / 'references').rglob('*')):
    if path.is_file():
        target = HARNESS / 'references' / path.relative_to(TEMPLATE / 'references')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
scope = ('# Full qualification through the explicit package\n\n'
    'One original thirty-case worker, real reducer and authority-vault publication, catalog recording '
    'and promotion, one completed simulated GPIO application, drift refusal and cold vault/bridge history. '
    'Only the namespace, pinned source closure and fixed entry path change. No oracle substitution. '
    'Original bounds: 60-second worker, 180-second parent, six parent SQLite opens, 16 MiB/file, '
    '256 MiB scratch, 8,192 files, 8 MiB log, five-second vault lease and 15 MiB vault. '
    'No physical endpoint, MCU, inference, network or live service. Interrupted case databases are '
    'never opened or repaired. Native image and owned-process accounting guards remain. '
    'Public qualification requires a separately enforceable storage profile.\n')
write(HARNESS / 'SCOPE.md', scope)
for name in ('run_attempt.py', 'attempt_child.py'):
    before = (TEMPLATE / name).read_text(); after = before
    if name == 'run_attempt.py':
        after = after.replace('5ffd155119c12c73d6090a6684973f7f14474ebbfdb0fce228f880476df4e3a9', sha(SOURCE / 'index.json'))
        after = after.replace('artifacts/implementation/pat-vault-catalog/implementation03', str(SOURCE.relative_to(ROOT)))
        after = after.replace('!= 308', '!= ' + str(len(frozen))).replace("'frozenPreparationInputCount': 308", "'frozenPreparationInputCount': " + str(len(frozen)))
        after = after.replace('!= 302', '!= 304').replace("'projectInputCount': 302", "'projectInputCount': 304").replace('exactly 302 files', 'exactly 304 files')
    else:
        after = after.replace("[str(root), str(root / 'tests'), str(root / 'supervisor')]", "[str(root), str(root / 'tests')]")
        after = after.replace("root / 'supervisor/retention_scan.so'", "root / 'hms_qualification/supervisor/retention_scan.so'")
        after = after.replace("entry.parent.parent.parent == expected and re.fullmatch(r'code-[0-9a-f]{64}',entry.parent.parent.name)",
            "entry.parent.parent.name == 'hms_qualification' and entry.parents[3] == expected and re.fullmatch(r'code-[0-9a-f]{64}',entry.parents[2].name)")
        after = after.replace('str(cwd) == str(entry.parent.parent)', 'str(cwd) == str(entry.parents[2])')
        after = after.replace("name == 'hms' or name.startswith('hms.')", "name == 'hms' or name.startswith('hms.') or name == 'hms_qualification' or name.startswith('hms_qualification.')")
        needle = "        if origin is not None:\n            add('module:' + name, origin)"
        assert needle in after
        after = after.replace(needle, needle + '\n        if name in ' + repr(sorted(mapping['modules'])) + ":\n            violations.append({'module': name, 'reason': 'legacy_flat_import_forbidden'})")
    ast.parse(after); write(HARNESS / name, after)
    write(HARNESS / (name + '.patch'), ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='original/' + name, tofile='namespaced/' + name)))
write(HARNESS / 'index.json', dict(files=[row(p, HARNESS) for p in sorted(HARNESS.rglob('*')) if p.is_file()]))
write(BASE / 'selected-scope.json', dict(sourceIndexSha256=sha(SOURCE / 'index.json'),
    harnessIndexSha256=sha(HARNESS / 'index.json'), source=str(SOURCE.relative_to(ROOT)),
    harness=str(HARNESS.relative_to(ROOT)), projectFiles=project_count, frozenFiles=len(frozen), actualPending=True))
print(json.dumps(read(BASE / 'selected-scope.json')))
