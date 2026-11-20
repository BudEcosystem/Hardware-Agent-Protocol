"""Verify installed identities, exact new input coverage and the complete suite."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ATTEMPT = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078'
PIN = '86d64218d50e23fd12ec4c9faec2d1baf4819e7b110c6c921d948873a51c5189'

def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def passing(p):
    return [line.split(' ... ')[0] for line in p.read_text().splitlines() if line.endswith(' ... ok')]
def verify(prefix, rows):
    for row in rows:
        p = prefix / row['path']
        assert not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256']

assert not (BASE / 'RUNTIME_RESULTS.json').exists()
assert sha(BASE / 'inputs.json') == PIN
frozen = read(BASE / 'inputs.json')['files']
assert len(frozen) == 244
verify(ROOT, frozen); verify(BASE / 'inputs', frozen)
selected = read(BASE / 'selected-source.json')
assert len(selected['installedLibraryFiles']) == 82
verify(ROOT, selected['installedLibraryFiles'])
verify(BASE / 'selected-source', selected['installedLibraryFiles'])
inspection = read(BASE / 'inspection01.json')
assert inspection == read(BASE / 'references/identity-pins.json')
assert inspection['passed'] and len(inspection['origins']) == 39 and inspection['producerImageFiles'] == 267
assert len(inspection['initializerDriftRefusals']) == 4 and inspection['poisonedLegacyModules'] == 17
assert not inspection['importEffects'] and (BASE / 'inspection01.stderr.txt').read_bytes() == b''
receipt_path = ATTEMPT / 'receipt.json'
receipt = read(receipt_path)
assert receipt['status'] == 'passed' and receipt['passed'] and receipt['tests'] == 866
assert receipt['inputs_stable'] and receipt['compiler_identity_stable']
assert not any(receipt[k] for k in ('failures', 'errors', 'skipped', 'expected_failures',
                                  'unexpected_successes', 'runner_errors', 'failure_reasons'))
for phase in ('files_before', 'files_after'):
    rows = receipt[phase]
    assert [{k:r[k] for k in ('path', 'bytes', 'sha256')} for r in rows] == frozen
    verify(ROOT, rows)
    for row in rows:
        p = ROOT / row['snapshot_path']
        assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
for row in receipt['outputs']: assert sha(ROOT / row['path']) == row['sha256']
old = read(BASE / 'baseline/receipt.json')
assert sha(BASE / 'baseline/receipt.json') == '68c1d8ec28038cc30167b11898c8484b60c94a0fd17b669534eb5a268e8d56c7'
previous = {r['path']: r for r in old['files_after']}
assert [name for name,r in previous.items() if sha(ROOT / name) != r['sha256']] == ['scripts/check_runtime.py']
assert set(r['path'] for r in frozen) - set(previous) == {
    r['path'] for r in selected['installedLibraryFiles']} | {'tests/test_qualification_vault_commit.py'}
old_log = next(ROOT / r['path'] for r in old['outputs'] if r['path'].endswith('/local-runtime-tests.txt'))
old_ids = passing(old_log); ids = passing(ATTEMPT / 'outputs/local-runtime-tests.txt')
assert len(ids) == len(set(ids)) == 866 and len(old_ids) == len(set(old_ids)) == 861
expected_new = set()
for name in selected['newTests']:
    method = name.rsplit(':', 1)[1]
    expected_new.add(method + ' (test_qualification_vault_commit.VaultCommitTests.' + method + ')')
assert len(expected_new) == 5 and set(ids) - set(old_ids) == expected_new
assert [i for i in ids if i not in expected_new] == old_ids
pointer = read(ROOT / 'artifacts/verification/local-runtime-current.json')
assert pointer['status'] == 'passed' and pointer['current_pass']
assert pointer['receipt'] == dict(path=str(receipt_path.relative_to(ROOT)), sha256=sha(receipt_path))
report = dict(passed=True, runtimeReceipt=pointer['receipt'], tests=866, distinctTests=866,
    previousTestIdsPreserved=861, previousTestOrderPreserved=True,
    newHeldVaultCommitTests=sorted(expected_new), stableInputs=244, addedInputs=83,
    changedPreviousInputs=['scripts/check_runtime.py'], unchangedPreviousInputs=160,
    installedLibraryFiles=82, existingProductionFilesUnchanged=50,
    exactQualifiedCandidateLibraryBytes=True, installedIdentityMatchesQualifiedCandidate=True,
    inspectionSha256=sha(BASE / 'inspection01.json'), inputIndexSha256=PIN,
    nativeBinaryAndCSourceSnapshotted=True, originalFullWorkerRepeated=False,
    databaseConnectionsOpenedByAudit=0, publicQualificationMounted=False,
    physicalExecutionPerformed=False, goalStatus='active', auditorSha256=sha(Path(__file__)))
with (BASE / 'RUNTIME_RESULTS.json').open('x') as out:
    json.dump(report, out, indent=2); out.write('\n')
print(json.dumps({k:report[k] for k in ('passed', 'tests', 'previousTestIdsPreserved',
    'stableInputs', 'installedLibraryFiles', 'installedIdentityMatchesQualifiedCandidate')}))
