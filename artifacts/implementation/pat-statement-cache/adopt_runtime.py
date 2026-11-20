"""Apply the sole verified Journal edit, then require a new runtime receipt."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
DEST = BASE / 'public-runtime'
SOURCE = BASE / 'implementation01'
RECEIPT = ROOT / 'artifacts/verification/runtime-attempts/20261108T225058.349199Z-7581b13279cb/receipt.json'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, body):
    p.parent.mkdir(parents=True, exist_ok=True)
    if type(body) is not bytes: body = (json.dumps(body, indent=2) + '\n').encode()
    with p.open('xb') as out: out.write(body)

assert not DEST.exists()
assert sha(RECEIPT) == 'aca07fa6dcdc3a883c3d7266422eaaaeb52d4b5ae223b60756306d39a43e58dc'
receipt = read(RECEIPT)
assert receipt['passed'] and receipt['tests'] == 861 and len(receipt['files_after']) == 161
for row in receipt['files_after']:
    p = ROOT / row['path']
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
result = read(BASE / 'RESULTS.json')
assert result['actualScopePassed'] and result['catalogControls'] == 19
assert result['caseManifests'] == 30 and result['sourceApplicationInvocations'] == 1
assert result['catalogObservation']['oneCompletedApplication']
assert result['sourceIndexSha256'] == sha(SOURCE / 'index.json') == '7ecd42fec5cef9374573ae8b3d0747060bdc8c4cd8ca552e9c3de4d64a2ec23e'
target = ROOT / 'hms/journal.py'
original = (BASE.parent / 'qualification-package/implementation03/project/hms/journal.py').read_bytes()
assert target.read_bytes() == original
candidate = (SOURCE / 'project/hms/journal.py').read_bytes()
assert candidate == original.replace(b'check_same_thread=False, timeout=0.2)',
    b'check_same_thread=False, timeout=0.2, cached_statements=256)')
write(DEST / 'prior/hms/journal.py', original)
write(DEST / 'candidate/hms/journal.py', candidate)
write(DEST / 'runtime-inputs-before.json', receipt['files_after'])
write(DEST / 'PREPARATION.json', dict(previousRuntimeReceipt=str(RECEIPT.relative_to(ROOT)),
    previousReceiptSha256=sha(RECEIPT), previousTests=861, previousInputsVerified=161,
    qualifiedCandidateIndexSha256=sha(SOURCE / 'index.json'),
    completeFlowAuditSha256=sha(BASE / 'RESULTS.json'), catalogControlsAuditSha256=sha(BASE / 'CONTROL_RESULTS.json'),
    onlyChangedFile='hms/journal.py', beforeSha256=sha(target),
    candidateSha256=hashlib.sha256(candidate).hexdigest(), fullRuntimeCheckRequired=True))
target.write_bytes(candidate)
changes = [row['path'] for row in receipt['files_after'] if sha(ROOT / row['path']) != row['sha256']]
assert changes == ['hms/journal.py']
write(DEST / 'APPLIED.json', dict(changedFiles=changes, journalSha256=sha(target),
    candidateBytesExact=True, unchangedRuntimeInputs=160, fullRuntimeCheckPending=True,
    publicQualificationServiceEnabled=False))
print(json.dumps(dict(changedFiles=changes, unchangedRuntimeInputs=160, fullRuntimeCheckPending=True)))
