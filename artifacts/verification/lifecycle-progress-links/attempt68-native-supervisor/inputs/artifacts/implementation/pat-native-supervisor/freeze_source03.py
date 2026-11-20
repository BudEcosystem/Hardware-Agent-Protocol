"""Independently derive consumer identities and freeze the current candidate."""
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
STAGE = BASE / 'implementation01'
PROJECT = STAGE / 'project'
PRIOR = BASE.parent / 'pat-io-proof-batch/implementation01'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
def canonical(value):
    # These identity values contain only strings, small integers, arrays and maps.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()
def package(folder, names):
    return [dict(path=folder + '/' + name, bytes=(PROJECT / folder / name).stat().st_size,
                 sha256=sha(PROJECT / folder / name)) for name in names]
assert not (STAGE / 'index.json').exists()
assert sha(PRIOR / 'index.json') == 'a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5'
assert read(BASE / 'controls01/result.json')['status'] == 'passed'
for row in read(BASE / 'controls01/inputs.json'):
    assert sha(BASE / row['path']) == row['sha256']
old = read(PRIOR / 'identity-pins.json')
assert digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1', sorted(old['sourceRows'], key=lambda row: row['path'])) == old['legacy']
external = {}
selected = read(PRIOR.parent / 'harness02/references/approved-external-roots.json')
metadata = {row['package']: row for row in selected['selectedMetadata']}
for name in ('jsonschema', 'referencing', 'jsonschema-specifications', 'attrs', 'rpds-py', 'typing_extensions', 'idna'):
    pin = metadata[name]
    metadata_path = Path(pin['metadataPath'])
    assert metadata_path.stat().st_size == pin['bytes'] and sha(metadata_path) == pin['sha256']
    distribution = importlib.metadata.PathDistribution(metadata_path.parent)
    assert distribution.version == pin['version']
    for item in distribution.files or []:
        if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:
            continue
        path = Path(distribution.locate_file(item))
        if path.is_file():
            external['dependencies/' + str(item)] = path
rows = []
for row in old['sourceRows']:
    name = row['path']
    previous = external[name] if name.startswith('dependencies/') else PRIOR / 'project' / name
    assert previous.stat().st_size == row['bytes'] and sha(previous) == row['sha256']
    current = external[name] if name.startswith('dependencies/') else PROJECT / name
    rows.append(dict(path=name, bytes=current.stat().st_size, sha256=sha(current)))
for name in ('retention_native.py', 'retention_scanmodule.c', 'retention_native.so'):
    rows += package('supervisor', (name,))
rows.sort(key=lambda row: row['path'])
assert len(rows) == len({row['path'] for row in rows}) == 270
legacy = digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1', rows)
vault = digest(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1', dict(legacyIdentity=legacy,
    sources=package('evidence_vault', ('__init__.py', 'contracts.py', 'connection.py', 'store.py'))))
consumer = digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1', dict(vaultIdentity=vault,
    sources=package('evidence_authority', ('__init__.py', 'contracts.py', 'store.py'))))
test = PROJECT / 'tests/test_vault_original_run.py'
body = test.read_text()
assert body.count(old['consumer']) == 1
test.write_text(body.replace(old['consumer'], consumer))
write(STAGE / 'identity-pins.json', dict(legacy=legacy, vault=vault, consumer=consumer,
    producerImageFiles=265, sourceRows=rows, actualRuntimeEqualityStillRequiresExecution=True))
baseline = read(STAGE / 'baseline-inputs.json')['files']
changed = [row['path'] for row in baseline if sha(PROJECT / row['path']) != row['sha256']]
assert set(changed) == {'supervisor/attempt_ledger.py', 'supervisor/supervisor_contracts.py', 'tests/test_vault_original_run.py'}
write(STAGE / 'source-review.json', dict(reviewer='primary-agent', independentReview=False,
    changedInheritedFiles=changed, newFiles=['supervisor/retention_native.py', 'supervisor/retention_scanmodule.c', 'supervisor/retention_native.so'],
    unchangedInheritedFiles=285, nativeBinaryUnchangedFromBinding=True,
    nativeBinarySha256=sha(PROJECT / 'supervisor/retention_native.so'),
    wrapperControlsSixScopesPassed=True, actualOriginalScopeUnchanged=True,
    caseMatrix=30, workerMaxWallMs=60000, parentMaxSeconds=180,
    nativePerEntryPythonAudit=False, strictNewProfile=True, rootAndOpenedChildChecksStrengthened=True,
    kernelPolicyOverride=False, memoryImageDescriptorBound=1, loaderFailureRetried=False,
    productionRuntimeIntegrated=False))
with (STAGE / 'README.md').open('x') as stream:
    stream.write('# Isolated native supervisor candidate\n\n[Design](../DESIGN.md), [source review](source-review.json), [identities](identity-pins.json). '
                 '285 inherited files remain exact. Two supervisor modules select the native profile and include its three artifacts in identity. '
                 'The original test changes only its consumer pin. Actual qualification is recorded separately.\n')
files = []
for path in sorted(STAGE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix == '.py':
            ast.parse(path.read_bytes())
        files.append(dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=sha(path)))
assert len(files) == 295
write(STAGE / 'index.json', dict(scope='Fresh native-supervisor source, unchanged complete actual test except consumer pin', files=files))
print(json.dumps(dict(projectFiles=291, frozenFiles=295, sourceIndexSha256=sha(STAGE / 'index.json'),
                      legacy=legacy, vault=vault, consumer=consumer)))
