#!/usr/bin/env python3
"""Offline integrity only; no tests, runtime imports or fixture execution."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
ORIGINAL = BASE.parent


def pin_check(item):
    path = Path(item['path'])
    assert not path.is_absolute() and '..' not in path.parts
    raw = (ROOT/path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item['sha256'], str(path)
    if 'bytes' in item:
        assert len(raw) == item['bytes'], str(path)


def verify():
    receipt = json.loads((BASE/'review.json').read_text())
    assert receipt['profile'] == 'hms.multi-adapter-cli-retry-review/1'
    assert receipt['execution_scope'] == 'Read-only source review and hash checks; no test or runtime execution.'
    pin_check(receipt['original_review'])
    original = json.loads((ORIGINAL/'review.json').read_text())
    for item in original['integrity_files']:
        pin_check(item)
    historic = json.loads((ORIGINAL/'frozen-sources.json').read_text())
    excepted = receipt['historical_support_test']
    assert excepted == 'tests/test_multi_cli.py'
    for item in historic:
        if item['path'] != excepted:
            pin_check(item)
    for item in receipt['current_inputs'] + receipt['integrity_files']:
        pin_check(item)
    assert len(receipt['current_inputs']) == 2
    assert not receipt['blocking_findings']
    print(json.dumps({'passed':True, 'original_retained_files':len(original['integrity_files']),
        'unchanged_original_live_pins':len(historic)-1, 'current_support_inputs':len(receipt['current_inputs']),
        'supplement_files':len(receipt['integrity_files']), 'tests_executed':0}))


if __name__ == '__main__':
    verify()
