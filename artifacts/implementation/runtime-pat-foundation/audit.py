"""Read-only integration audit; never execute a worker or open a state database."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    baseline = read(BASE / 'baseline-index.json')
    original = read(BASE / 'baseline-receipt.json')
    assert digest(BASE / 'baseline-receipt.json') == baseline['receipt']['sha256']
    assert original['passed'] and original['tests'] == 748
    for row in baseline['files']:
        assert digest(BASE / 'baseline' / row['path']) == row['sha256']

    selected = read(BASE / 'selected-source.json')
    assert digest(ROOT / selected['sourceIndex']) == selected['sourceIndexSha256']
    production = []
    for row in selected['files']:
        assert digest(ROOT / row['source']) == row['sha256']
        assert digest(BASE / 'selected-source' / row['path']) == row['sha256']
        if row['path'].startswith('hms/'):
            assert digest(ROOT / row['path']) == row['sha256']
            production.append(row['path'])
    assert len(production) == 8

    pointer = read(ROOT / 'artifacts/verification/local-runtime-current.json')
    assert pointer['status'] == 'passed' and pointer['current_pass'] is True
    receipt_path = ROOT / pointer['receipt']['path']
    assert digest(receipt_path) == pointer['receipt']['sha256']
    receipt = read(receipt_path)
    assert receipt['passed'] and receipt['tests'] == 861
    assert receipt['inputs_stable'] and receipt['compiler_identity_stable']
    assert not any(receipt[key] for key in (
        'failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes', 'runner_errors'))
    before = {row['path']: row['sha256'] for row in receipt['files_before']}
    after = {row['path']: row['sha256'] for row in receipt['files_after']}
    assert before == after and len(before) == 161
    for row in receipt['files_before'] + receipt['files_after']:
        assert digest(ROOT / row['snapshot_path']) == row['sha256']
        assert digest(ROOT / row['path']) == row['sha256']
    for row in receipt['outputs']:
        assert digest(ROOT / row['path']) == row['sha256']
    old = {row['path']: row['sha256'] for row in baseline['files']}
    changed = sorted(name for name in old if before.get(name) != old[name])
    assert changed == sorted(production + ['tests/test_pat_compiler.py'])
    added = sorted(before.keys() - old.keys())
    assert len(added) == 10 and all(name.startswith('tests/') for name in added)

    log = (receipt_path.parent / 'outputs/local-runtime-tests.txt').read_text()
    passing = [line.split(' ... ')[0] for line in log.splitlines() if line.endswith(' ... ok')]
    assert len(passing) == len(set(passing)) == 861
    old_log = next(ROOT / row['path'] for row in original['outputs']
                   if row['path'].endswith('/local-runtime-tests.txt')).read_text()
    old_tests = {line.split(' ... ')[0] for line in old_log.splitlines() if line.endswith(' ... ok')}
    assert len(old_tests) == 748 and old_tests <= set(passing)
    focus = read(BASE / 'focused01/result.json')
    assert focus['returncode'] == 1 and focus['inputsStable'] is True
    focus_log = (BASE / 'focused01/output.txt').read_text()
    assert 'Ran 113 tests' in focus_log and 'FAILED (errors=2)' in focus_log

    report = dict(passed=True, runtimeReceipt=pointer['receipt'], tests=861,
        originalTestIdsPreserved=748, newTestIds=113, stableInputs=161,
        changedInputs=changed, addedInputs=added, exactCandidateProductionFiles=production,
        focusedFailurePreserved=True, databasesOpened=False, workersExecuted=False,
        sourceIndexSha256=selected['sourceIndexSha256'], auditorSha256=digest(Path(__file__)))
    output = BASE / 'integration-audit.json'
    with output.open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps({key: report[key] for key in (
        'passed', 'tests', 'originalTestIdsPreserved', 'newTestIds', 'stableInputs')}))


if __name__ == '__main__':
    main()
