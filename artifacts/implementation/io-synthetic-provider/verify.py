"""Offline retained-byte verification; does not import or execute staged HMS."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def digest(path):
    data = path.read_bytes(); return len(data),hashlib.sha256(data).hexdigest()

def check_file(root,row):
    relative = Path(row['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root/relative
    assert path.is_file() and not path.is_symlink()
    assert digest(path) == (row['bytes'],row['sha256']), str(path)

def check_attempt(path, *, require_pass=False, receipt=None, before=None):
    receipt = json.loads((path/'result.json').read_text()) if receipt is None else receipt
    before = json.loads((path/'before.json').read_text()) if before is None else before
    after = json.loads((path/'after.json').read_text())
    assert len(before) == receipt['inputCount'] and before == after
    assert len({row['path'] for row in before}) == len(before)
    for row in before:
        check_file(path/'inputs',row)
    packages = json.loads((path/'packages-before.json').read_text())
    assert packages == json.loads((path/'packages-after.json').read_text())
    assert receipt['inputsUnchanged'] is True and receipt['packagesUnchanged'] is True
    assert receipt['importsScopedToSnapshots'] is True and receipt['forbiddenImports'] == []
    assert all(imported.startswith(str(path/'inputs/staged')+'/') for imported in receipt['imports'].values())
    for row in receipt['evidence']:
        check_file(path,row)
    assert len({row['path'] for row in receipt['evidence']}) == len(receipt['evidence'])
    assert {row['path'] for row in receipt['evidence']} == {str(file.relative_to(path)) for file in (path/'evidence').rglob('*') if file.is_file()}
    passed = not any(receipt[key] for key in ('failures','errors','skips','expectedFailures','unexpectedSuccesses')) and receipt['loaderError'] is None
    assert receipt['passed'] is passed
    if require_pass:
        assert passed and receipt['tests'] == 24
        assert len(list((path/'evidence').glob('*/context.json'))) == receipt['tests']
        assert len(list((path/'evidence').glob('*/authority.db'))) == receipt['tests']
    return receipt

def verify():
    index = json.loads((HERE/'index.json').read_text())
    assert len({row['path'] for row in index['files']}) == len(index['files'])
    for row in index['files']:
        check_file(ROOT,row)
    baseline = json.loads((HERE/'baseline/inputs.json').read_text())
    for row in baseline['files']:
        check_file(HERE/'baseline',row)
        if row['path'].startswith(('hms/','schemas/','protocol/','research/')) and row['path'] != 'hms/state_path.py':
            check_file(HERE/'staged',row)
    attempts = sorted((HERE/'attempts').iterdir())
    receipts = [check_attempt(path,require_pass=path == attempts[-1]) for path in attempts]
    before = json.loads((attempts[-1]/'before.json').read_text())
    for row in before:
        check_file(HERE,row)
    # Establish the stated test-only correction rather than assuming it.
    first = {row['path']:row for row in json.loads((attempts[0]/'before.json').read_text())}
    changes = [row['path'] for row in before if first.get(row['path']) != row]
    assert changes == ['test_io_synthetic_provider.py']
    negatives = []
    altered = copy.deepcopy(receipts[-1]); altered['errors'] = 1
    bad_hash = [before[0] | {'sha256':'0'*64},*before[1:]]
    bad_evidence = copy.deepcopy(receipts[-1]); bad_evidence['evidence'] = bad_evidence['evidence'][:-1]
    for name,record,inputs in (('stale_success_flag',altered,None),('omitted_input',None,before[:-1]),
                                ('tampered_input_hash',None,bad_hash),('omitted_evidence',bad_evidence,None)):
        try:
            check_attempt(attempts[-1],require_pass=True,receipt=record,before=inputs)
        except AssertionError:
            negatives.append(name)
        else:
            raise AssertionError('negative accepted: '+name)
    return {'schema':'hms-staged-synthetic-io-verification/1','passed':True,'indexSha256':digest(HERE/'index.json')[1],
        'indexedFiles':len(index['files']),'baselineInputs':len(baseline['files']),'attempts':len(attempts),
        'latestTests':receipts[-1]['tests'],'latestInputCount':receipts[-1]['inputCount'],
        'changedInputsBetweenAttempts':changes,'negativeChecksRejected':negatives,
        'scope':'Retained bytes and recorded attempt consistency only; no staged code executed, no physical/availability/lifecycle qualification.'}

if __name__ == '__main__':
    value = verify()
    (HERE/'verification.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value,indent=2))
