"""Retain and adapt the exact existing actual harness; no execution occurs here."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
TEMPLATE = BASE.parent / 'pat-io-proof-batch/harness02'
HARNESS = BASE / 'harness01'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def put(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())
def dump(path, value):
    put(path, json.dumps(value, indent=2) + '\n')
assert not HARNESS.exists()
assert sha(SOURCE / 'index.json') == 'ffe9af2582f56ab198a92f58598d378fc07a3c69cfe223c73b353a91c59c319b'
assert sha(TEMPLATE / 'index.json') == '094098cab10de007e509f99895997915f6956634cb045f0d241ae333a01b08dc'
for row in read(TEMPLATE / 'index.json')['files']:
    assert sha(TEMPLATE / row['path']) == row['sha256']
for row in read(SOURCE / 'index.json')['files']:
    assert sha(ROOT / row['path']) == row['sha256']
borrowed = []
for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json', 'targets.json'):
    source = TEMPLATE / name
    copy = 'references/' + source.name
    put(HARNESS / copy, source.read_bytes())
    borrowed.append(dict(source=str(source.relative_to(ROOT)), copy=copy, bytes=source.stat().st_size, sha256=sha(source)))
    if not name.endswith('.py'):
        if name == 'targets.json':
            put(HARNESS / name, source.read_bytes())
        continue
    old = source.read_text()
    new = old
    if name == 'run_attempt.py':
        new = new.replace('a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5', sha(SOURCE / 'index.json'))
        new = new.replace('artifacts/implementation/pat-io-proof-batch/implementation01/', 'artifacts/implementation/pat-native-supervisor/implementation01/')
        new = re.sub(r'\b288\b', '291', new)
        new = re.sub(r'\b292\b', '295', new)
        new = new.replace("prefix='hms-io-proof-batch-actual-'", "prefix='hms-native-supervisor-actual-'")
    else:
        new = new.replace('import hashlib\n', 'import hashlib\nimport fcntl\nimport stat\n', 1)
        guard = (BASE / 'native_guard.py.inc').read_text()
        new = new.replace('def audit(event, args):\n', guard + '\ndef audit(event, args):\n    if event.startswith(\'hms.retention.\'):\n        native_boundary(event, args)\n        return\n', 1)
        marker = "        path = Path(origin).resolve()\n        key = (label, str(path))"
        replacement = '''        if label == 'module:_hms_retention_native_v1':
            if native_image is None or origin != native_image['origin'] or not verify_native_image(native_image):
                raise RuntimeError('Loaded native module has no exact held image')
            rows.append(dict(source=label, origin=origin, kind='sealed_native_image',
                sha256=NATIVE_DIGEST, artifactOrigin=native_load['artifactOrigin'],
                device=native_image['device'], inode=native_image['inode'], matchesBefore=True))
            return
        path = Path(origin).resolve()
        key = (label, str(path))'''
        assert new.count(marker) == 1
        new = new.replace(marker, replacement)
        marker = "            'records': rows, 'violations': violations, 'prohibitedAttempts': prohibited,"
        assert new.count(marker) == 1
        new = new.replace(marker, marker + "\n            'nativeRetention': dict(load=native_load, image=native_image, scans=list(native_scans.values())),")
    ast.parse(new)
    put(HARNESS / name, new)
    put(HARNESS / (name + '.patch'), ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
        fromfile='frozen-proof-build/' + name, tofile='native-supervisor/' + name)))
dump(HARNESS / 'borrowed-inputs.json', borrowed)
put(HARNESS / 'README.md', '# Native supervisor actual scope\n\n[Source](../implementation01/README.md), [scope](SCOPE.md). The complete original test and its limits are preserved.\n')
put(HARNESS / 'SCOPE.md', '# Exact complete actual scope\n\nOne unchanged original 30-case worker, real reducer, authority-vault import, original-key replay, configuration revision change and vault-only cold history. No source PAT or source-runtime/supervisor cold reopen is added.\n\nOriginal bounds: worker 60 seconds, parent 180 seconds, six parent SQLite opens, 16 MiB single file, 256 MiB retained scratch, 8192 files, 8 MiB log, five-second held snapshot and 15 MiB vault. No altered keys, weakened cases, expanded limits, physical I/O, MCU execution, inference or live services.\n\nThe child authorizes one pinned native memory image and exact supervisor/attempt scan roots. Its audit hooks are cooperative and do not see per-entry native syscalls. Seals and held inode/digest are checked before load and in the final origin report. The image descriptor remains held to process exit. System library closure is not fully attested.\n')
dump(HARNESS / 'review.json', dict(reviewer='primary-agent', independentReview=False,
    sourceIndexSha256=sha(SOURCE / 'index.json'), templateIndexSha256=sha(TEMPLATE / 'index.json'),
    originalScopeAndLimitsUnchanged=True, sixLoaderScopesPassed=True,
    nativeAuditAdded=True, originalAuditBodyPreserved=True, actualScopeNotYetExecuted=True))
rows = [dict(path=str(path.relative_to(HARNESS)), bytes=path.stat().st_size, sha256=sha(path))
        for path in sorted(HARNESS.rglob('*')) if path.is_file()]
dump(HARNESS / 'index.json', dict(scope='Complete original actual worker/import; native image/scan audit added', files=rows))
print(json.dumps(dict(sourceIndexSha256=sha(SOURCE / 'index.json'), harnessIndexSha256=sha(HARNESS / 'index.json'))))
