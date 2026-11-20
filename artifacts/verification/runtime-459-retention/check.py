"""Verify one failed attempt's retained bytes; never rerun tests or devices."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parent
ATTEMPT = ROOT / 'artifacts/verification/runtime-attempts/20261106T203848.199512Z-167d040b9d57'
checks = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, expected):
    if not path.resolve().is_relative_to(ROOT) or sha(path) != expected:
        raise ValueError('Retained byte mismatch: ' + str(path))
    checks.append({'path': str(path.relative_to(ROOT)), 'sha256': expected})


def main():
    receipt_path = ATTEMPT / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if (receipt['tests'], receipt['failures'], receipt['errors'], receipt['skipped'],
            receipt['expected_failures'], receipt['passed']) != (459, 1, 1, 0, 0, False):
        raise ValueError('Unexpected attempt outcome')
    if not receipt['inputs_stable'] or not receipt['compiler_identity_stable'] or receipt['runner_errors']:
        raise ValueError('Attempt source or runner evidence differs')
    before = {r['path']: r['sha256'] for r in receipt['files_before']}
    after = {r['path']: r['sha256'] for r in receipt['files_after']}
    if len(before) != 107 or before != after:
        raise ValueError('Input inventory differs')
    for row in receipt['files_before'] + receipt['files_after']:
        verify(ROOT / row['snapshot_path'], row['sha256'])
    for row in receipt['outputs']:
        verify(ROOT / row['path'], row['sha256'])
    previous = receipt['last_success_before_attempt']
    verify(ROOT / previous['path'], previous['sha256'])
    pointer_path = DEST / 'current-pointer.json'
    if not pointer_path.exists():
        pointer_path.write_bytes((ROOT / 'artifacts/verification/local-runtime-current.json').read_bytes())
    pointer = json.loads(pointer_path.read_text())
    if pointer['status'] != 'failed' or pointer['current_pass'] or pointer['attempt_id'] != receipt['attempt_id']:
        raise ValueError('Archived current pointer differs')
    verify(receipt_path, pointer['receipt']['sha256'])
    report = {
        'schema': 'hms.failed-runtime-retention/1', 'passed_retention_check': True,
        'full_suite_passed': False, 'tests': 459, 'failures': 1, 'errors': 1,
        'input_files': len(before), 'output_files': len(receipt['outputs']),
        'hash_assertions': len(checks), 'files': checks,
        'checker_sha256': sha(Path(__file__)), 'pointer_sha256': sha(pointer_path),
        'scope': 'Exact retained input/output copies for this failed attempt. No live-source equivalence, test rerun, full-runtime pass, physical validation or trust attestation.',
    }
    (DEST / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('passed_retention_check', 'full_suite_passed', 'input_files', 'output_files', 'hash_assertions')}))


if __name__ == '__main__':
    main()
