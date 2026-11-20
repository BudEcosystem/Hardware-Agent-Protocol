"""Offline retained-byte/attempt verification; no test, controller or model execution."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def digest(path):
    value = path.read_bytes()
    return len(value), hashlib.sha256(value).hexdigest()

def check_file(root, record):
    relative = Path(record['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root / relative
    assert path.is_file() and not path.is_symlink(), str(path)
    assert digest(path) == (record['bytes'], record['sha256']), str(path)

def check_attempt(path, *, require_pass=False, receipt=None, before=None):
    receipt = receipt or json.loads((path / 'result.json').read_text())
    before = json.loads((path / 'before.json').read_text()) if before is None else before
    after = json.loads((path / 'after.json').read_text())
    assert len(before) == receipt['inputCount'] and before == after
    assert len({row['path'] for row in before}) == len(before)
    for row in before:
        check_file(path / 'inputs', row)
    packages_before = json.loads((path / 'packages-before.json').read_text())
    assert packages_before == json.loads((path / 'packages-after.json').read_text())
    assert receipt['inputsUnchanged'] is True and receipt['packagesUnchanged'] is True
    assert receipt['importsScopedToSnapshots'] is True and receipt['forbiddenImports'] == []
    for name, imported in receipt['imports'].items():
        assert imported.startswith(str(path / 'inputs/staged') + '/') or (
            name == 'hms.retained_original_registry' and imported == str(path / 'inputs/baseline/hms/registry.py'))
    for row in receipt['evidence']:
        check_file(path, row)
    assert len({row['path'] for row in receipt['evidence']}) == len(receipt['evidence'])
    assert {row['path'] for row in receipt['evidence']} == {
        str(file.relative_to(path)) for file in (path / 'evidence').rglob('*') if file.is_file()}
    passed = not any(receipt[key] for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses')) and receipt['loaderError'] is None
    assert receipt['passed'] is passed
    if require_pass:
        assert receipt['passed'] is True and receipt['tests'] >= 26
    return receipt

def verify():
    index = json.loads((HERE / 'index.json').read_text())
    assert len({row['path'] for row in index['files']}) == len(index['files'])
    for row in index['files']:
        check_file(ROOT, row)
    baseline = json.loads((HERE / 'baseline/inputs.json').read_text())
    for row in baseline['files']:
        check_file(HERE / 'baseline', row)
        if row['path'].startswith(('hms/', 'schemas/', 'research/')) and row['path'] != 'hms/registry.py':
            check_file(HERE / 'staged', row)
    attempts = sorted((HERE / 'attempts').iterdir())
    receipts = [check_attempt(path, require_pass=path == attempts[-1]) for path in attempts]
    latest_before = json.loads((attempts[-1] / 'before.json').read_text())
    for row in latest_before:
        check_file(HERE, row)
    negatives = []
    bad = copy.deepcopy(receipts[-1]); bad['errors'] = 1
    for name, altered_receipt, altered_before in (
        ('stale_success_flag', bad, None),
        ('omitted_input', None, latest_before[:-1]),
        ('tampered_input_hash', None, [latest_before[0] | {'sha256': '0' * 64}, *latest_before[1:]]),
    ):
        try:
            check_attempt(attempts[-1], require_pass=True, receipt=altered_receipt, before=altered_before)
        except AssertionError:
            negatives.append(name)
        else:
            raise AssertionError('negative accepted: ' + name)
    return {'schema': 'hms-resource-admission-offline-verification/1', 'passed': True,
        'indexSha256': digest(HERE / 'index.json')[1], 'indexedFiles': len(index['files']),
        'baselineInputs': len(baseline['files']), 'attempts': len(attempts),
        'latestTests': receipts[-1]['tests'], 'latestInputCount': receipts[-1]['inputCount'],
        'negativeChecksRejected': negatives,
        'scope': 'Retained bytes and recorded attempt consistency only; does not rerun tests or establish physical/provider behavior.'}

if __name__ == '__main__':
    value = verify()
    (HERE / 'verification.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value, indent=2))
