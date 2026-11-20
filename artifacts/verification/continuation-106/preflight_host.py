"""Root data-only source freeze check; imports no candidate or runner."""
from pathlib import Path
import difflib
import hashlib
import json
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKET = ROOT/'artifacts/implementation/standing-host-selection-reuse'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    def unique(rows):
        result = {}
        for key, value in rows:
            assert key not in result
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)
def contained(root, name):
    relative = Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root/relative
    assert path.resolve().is_relative_to(root.resolve()) and not path.is_symlink()
    return path

assert sha(PACKET/'SOURCE-REVIEW.json') == '25e1be4db68cec9b639667e034656f45fc985923bdf4bc8a2b8ab8a3a060bdb1'
review = read(PACKET/'SOURCE-REVIEW.json')
rows = review['files']
assert len(rows) == review['inputFiles'] == 283
assert len({row['path'] for row in rows}) == 283
assert sum(row['bytes'] for row in rows) == review['inputBytes'] == 5010312
for row in rows:
    path = contained(PACKET, row['path'])
    assert path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
pins = read(PACKET/'source-pins.json')
assert len(pins['copies']) == 260 and len(pins['originalProvenance']) == 11
for row in pins['copies'] + pins['originalProvenance']:
    source = contained(ROOT, row['source']); target = contained(PACKET, row['copy'])
    assert source.stat().st_size == target.stat().st_size == row['bytes']
    assert sha(source) == sha(target) == row['sha256']
assert review['modifiedProductionFiles'] == ['project/hms/standing_pat.py']
for key in ('parentPacket', 'secondParentPacket', 'proposalPacket'):
    p = ROOT/pins[key]['path']; index = read(p/'index.json')
    assert sha(p/'index.json') == pins[key]['indexSha256']
    expected = {row['path'] for row in index['files']}
    assert {str(f.relative_to(p)) for f in p.rglob('*') if f.is_file()} == expected | {'index.json'}
    for row in index['files']:
        path = contained(p, row['path'])
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
baseline = ROOT/'artifacts/implementation/standing-host-history-cost'
for old, new, patch, left, right in (
    (PACKET/'originals/standing_pat.py', PACKET/'project/hms/standing_pat.py', 'production.patch', 'baseline/hms/standing_pat.py', 'candidate/hms/standing_pat.py'),
    (baseline/'run_checks.py', PACKET/'run_checks.py', 'runner.patch', 'baseline/history-cost/run_checks.py', 'candidate/selection-reuse/run_checks.py')):
    delta = ''.join(difflib.unified_diff(old.read_text().splitlines(True), new.read_text().splitlines(True), fromfile=left, tofile=right))
    assert delta.encode() == (PACKET/patch).read_bytes()
for name in ('production.patch', 'run_checks.py', 'selection_reuse_controls.py'):
    assert (PACKET/name).read_bytes() == (PACKET/'review-history/draft01'/name).read_bytes()
public = ROOT/pins['publicReceipt']['path']
assert sha(public) == pins['publicReceipt']['sha256']
public_rows = read(public)['files']; assert len(public_rows) == 244
for row in public_rows: assert sha(ROOT/row['path']) == row['sha256']
assert not list(PACKET.glob('selection-reuse-*-attempt*'))
result = dict(passed=True, sourceReviewSha256=sha(PACKET/'SOURCE-REVIEW.json'),
    inputsExcludingSelf=283, frozenInputsIncludingSelf=284, inputBytesExcludingSelf=5010312,
    exactReusedFiles=260, originalProvenanceCopies=11, changedProductionFiles=1,
    publicInputsExact=244, productionDeltaRegenerated=True, runnerDeltaRegenerated=True,
    rootFullRead=['production.patch','run_checks.py','runner.patch','selection_reuse_controls.py','README.md','PLAN.md','CONTROL-NOTES.md','project/tests/standing_host_fixture.py'],
    rootFocusedRead='Six reused live controls and their LostReplyHost, FaultStore, opened, active, stop helpers',
    candidateImported=False, candidateExecuted=False, sourceSnapshotOnly=True)
with (HERE/'host-preflight.json').open('x') as out:
    json.dump(result,out,indent=2,sort_keys=True);out.write('\n')
print(json.dumps(result,sort_keys=True))
