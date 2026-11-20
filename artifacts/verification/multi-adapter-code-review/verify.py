#!/usr/bin/env python3
"""Offline receipt integrity and reported-result checks; does not rerun probes."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent


def checked(path, digest, size):
    item = Path(path)
    assert not item.is_absolute() and '..' not in item.parts, path
    raw = (ROOT/item).read_bytes()
    assert len(raw) == size, path
    assert hashlib.sha256(raw).hexdigest() == digest, path


def verify(live=True):
    receipt = json.loads((BASE/'review.json').read_text())
    assert receipt['profile'] == 'hms.multi-adapter-independent-review/1'
    assert receipt['status'] == 'complete'
    for item in receipt['integrity_files']:
        checked(item['path'], item['sha256'], item['bytes'])
    pins = json.loads((BASE/'frozen-sources.json').read_text())
    for item in pins:
        checked(str((BASE/'sources'/item['path']).relative_to(ROOT)), item['sha256'], item['bytes'])
        if live:
            checked(item['path'], item['sha256'], item['bytes'])
    probe = json.loads((BASE/'independent-probe-result.json').read_text())
    assert probe['passed'] and probe['tests'] == 9 and probe['failures'] == probe['errors'] == 0
    assert probe['source_pins_checked_before_and_after'] == len(pins)
    live_result = json.loads((BASE/'realtime-diagnostic.json').read_text())
    assert live_result['passed'] and not live_result['errors'] and len(live_result['requests']) == 9
    assert live_result['source_pins'] == pins
    assert live_result['source_pins_checked_before_and_after'] == len(pins)
    assert live_result['probe_sha256'] == hashlib.sha256((BASE/'realtime_probe.py').read_bytes()).hexdigest()
    assert all(item['state']['executionState'] == 'completed' and not item['state']['resourceClaims']
               for item in live_result['requests'])
    for name, code in [('realtime-before-batched-ingress.json','OBSERVATION_STALE'),
                       ('realtime-batched-concurrent-load.json','DEVICE_UNAVAILABLE'),
                       ('realtime-refresh-lock-concurrent-load.json','OBSERVATION_STALE')]:
        result = json.loads((BASE/name).read_text())
        assert not result['passed'] and result['errors'][0]['code'] == code
    print(json.dumps({'passed':True, 'retained_files':len(receipt['integrity_files']),
                      'source_pins':len(pins), 'current_sources_checked':live,
                      'scope':'Hash and record verification only; no probe, fixture, target or hardware execution.'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--retained-only', action='store_true', help='Verify retained sources if live development has advanced.')
    verify(live=not parser.parse_args().retained_only)
