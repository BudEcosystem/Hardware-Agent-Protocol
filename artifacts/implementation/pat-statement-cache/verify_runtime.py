"""Verify the single new runtime receipt and preserved complete test selection."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ATTEMPT = ROOT / 'artifacts/verification/runtime-attempts/20261109T011608.358669Z-115386951c7c'
OLD = ROOT / 'artifacts/verification/runtime-attempts/20261108T225058.349199Z-7581b13279cb/receipt.json'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def passing(p):
    return [line.split(' ... ')[0] for line in p.read_text().splitlines() if line.endswith(' ... ok')]

assert not (BASE / 'RUNTIME_RESULTS.json').exists()
assert sha(OLD) == 'aca07fa6dcdc3a883c3d7266422eaaaeb52d4b5ae223b60756306d39a43e58dc'
receipt_path = ATTEMPT / 'receipt.json'
receipt = read(receipt_path)
assert receipt['status'] == 'passed' and receipt['passed'] and receipt['tests'] == 861
assert receipt['inputs_stable'] and receipt['compiler_identity_stable']
assert not any(receipt[k] for k in ('failures', 'errors', 'skipped', 'expected_failures',
                                  'unexpected_successes', 'runner_errors', 'failure_reasons'))
before = {r['path']: r['sha256'] for r in receipt['files_before']}
after = {r['path']: r['sha256'] for r in receipt['files_after']}
assert before == after and len(before) == 161
for row in receipt['files_before'] + receipt['files_after']:
    for p in (ROOT / row['path'], ROOT / row['snapshot_path']):
        assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
for row in receipt['outputs']: assert sha(ROOT / row['path']) == row['sha256']
old = read(OLD)
original = {r['path']: r['sha256'] for r in old['files_after']}
assert set(before) == set(original)
assert [name for name in sorted(before) if before[name] != original[name]] == ['hms/journal.py']
current_ids = passing(ATTEMPT / 'outputs/local-runtime-tests.txt')
old_ids = passing(OLD.parent / 'outputs/local-runtime-tests.txt')
assert len(current_ids) == len(set(current_ids)) == len(old_ids) == 861
assert current_ids == old_ids
assert (ROOT / 'hms/journal.py').read_bytes() == (BASE / 'implementation01/project/hms/journal.py').read_bytes()
pointer = read(ROOT / 'artifacts/verification/local-runtime-current.json')
assert pointer['status'] == 'passed' and pointer['current_pass']
assert pointer['receipt'] == dict(path=str(receipt_path.relative_to(ROOT)), sha256=sha(receipt_path))
report = dict(passed=True, runtimeReceipt=pointer['receipt'], tests=861, distinctTests=861,
    previousTestIdsPreserved=861, testSelectionAndOrderUnchanged=True, stableInputs=161,
    changedInputs=['hms/journal.py'], unchangedPreviousInputs=160, addedInputs=[],
    exactQualifiedCandidateJournal=True, databaseConnectionsOpenedByAudit=0,
    qualificationWorkersLaunchedByAudit=0, publicQualificationEnabled=False,
    previousReceiptSha256=sha(OLD), goalStatus='active', auditorSha256=sha(Path(__file__)))
with (BASE / 'RUNTIME_RESULTS.json').open('x') as out:
    json.dump(report, out, indent=2); out.write('\n')
print(json.dumps(report))
